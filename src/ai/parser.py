"""Post-processing and validation of AI-generated CircuitSpec objects."""

from __future__ import annotations

from src.ai.schemas import CircuitSpec, ComponentSpec, NetSpec, PinRef
from src.utils.logger import get_logger

log = get_logger("ai.parser")


class ValidationWarning:
    """A non-fatal issue found during validation."""

    def __init__(self, message: str, severity: str = "warning"):
        self.message = message
        self.severity = severity  # "warning" or "info"

    def __repr__(self) -> str:
        return f"[{self.severity.upper()}] {self.message}"


class CircuitValidator:
    """Validate and auto-fix an AI-generated CircuitSpec."""

    def __init__(self, spec: CircuitSpec):
        self.spec = spec
        self.warnings: list[ValidationWarning] = []

    def validate(self) -> CircuitSpec:
        """Run all validation passes and return the (possibly corrected) spec."""
        self._ensure_component_pins()
        self._check_unique_refs()
        self._check_net_references()
        self._clean_degenerate_nets()

        if not self.spec.nets:
            self.warnings.append(
                ValidationWarning(
                    "No nets were generated — all components are disconnected. "
                    "Try increasing Max Tokens (8192+) in Settings and retry."
                )
            )

        self._check_power_nets()
        self._check_bypass_caps()
        self._assign_positions()

        if self.warnings:
            log.warning(
                "Validation completed with %d warnings:", len(self.warnings)
            )
            for w in self.warnings:
                log.warning("  %s", w)
        else:
            log.info("Validation passed with no warnings.")

        return self.spec

    # ------------------------------------------------------------------
    # Pin generation for components missing pins
    # ------------------------------------------------------------------

    _DEFAULT_PIN_COUNTS: dict[str, int] = {
        "resistor": 2, "capacitor": 2, "inductor": 2,
        "diode": 2, "led": 2, "fuse": 2, "crystal": 2, "switch": 2,
        "transistor": 3, "mosfet": 3, "sensor": 3,
        "opamp": 5, "regulator": 3,
        "connector": 2, "relay": 4, "transformer": 4,
    }

    def _ensure_component_pins(self) -> None:
        """Auto-generate pins for components that have an empty pins list."""
        for comp in self.spec.components:
            if comp.pins:
                continue
            cat = comp.category.value if hasattr(comp.category, 'value') else str(comp.category)
            n_pins = self._DEFAULT_PIN_COUNTS.get(cat, 2)
            # Try to infer from package name (e.g. DIP-8 → 8 pins)
            pkg = (comp.package or "").upper()
            for token in pkg.replace("-", " ").replace("_", " ").split():
                if token.isdigit():
                    n_pins = max(int(token), 2)
                    break
            from src.ai.schemas import PinSpec
            comp.pins = [PinSpec(number=str(i + 1), name=str(i + 1)) for i in range(n_pins)]
            self.warnings.append(
                ValidationWarning(
                    f"Component '{comp.ref}' had no pins — auto-generated {n_pins} pins",
                    severity="info",
                )
            )

    # ------------------------------------------------------------------
    # Checks
    # ------------------------------------------------------------------

    def _check_unique_refs(self) -> None:
        """Ensure all component reference designators are unique."""
        refs = [c.ref for c in self.spec.components]
        seen: set[str] = set()
        for ref in refs:
            if ref in seen:
                self.warnings.append(
                    ValidationWarning(f"Duplicate reference designator: {ref}")
                )
            seen.add(ref)

    def _check_net_references(self) -> None:
        """Verify every net pin-ref points to an existing component + pin.

        Auto-fixes bad references:
        1. Match pin by name if number doesn't match.
        2. Assign first unused pin if no name match.
        3. Remove connections to non-existent components.
        """
        # Build lookup structures
        comp_pins: dict[str, set[str]] = {}  # ref -> set of pin numbers
        comp_pin_name_map: dict[str, dict[str, str]] = {}  # ref -> {name_lower: number}
        for comp in self.spec.components:
            comp_pins[comp.ref] = {p.number for p in comp.pins}
            name_map: dict[str, str] = {}
            for p in comp.pins:
                if p.name:
                    name_map[p.name.lower()] = p.number
                # Also map the number itself as a name (identity)
                name_map[p.number.lower()] = p.number
            comp_pin_name_map[comp.ref] = name_map

        # Track which pins are already used per component per net
        used_pins: dict[str, set[str]] = {ref: set() for ref in comp_pins}

        for net in self.spec.nets:
            conns_to_remove: list[PinRef] = []
            for pin_ref in net.connections:
                if pin_ref.ref not in comp_pins:
                    self.warnings.append(
                        ValidationWarning(
                            f"Net '{net.name}': removing unknown component '{pin_ref.ref}'",
                            severity="warning",
                        )
                    )
                    conns_to_remove.append(pin_ref)
                    continue

                available = comp_pins[pin_ref.ref]
                if pin_ref.pin in available:
                    used_pins[pin_ref.ref].add(pin_ref.pin)
                    continue  # valid

                # Try matching by pin name (case-insensitive)
                name_map = comp_pin_name_map[pin_ref.ref]
                matched_number = name_map.get(pin_ref.pin.lower())
                if matched_number and matched_number in available:
                    old_pin = pin_ref.pin
                    pin_ref.pin = matched_number
                    used_pins[pin_ref.ref].add(matched_number)
                    self.warnings.append(
                        ValidationWarning(
                            f"Net '{net.name}': auto-fixed '{pin_ref.ref}' pin "
                            f"'{old_pin}' → '{matched_number}' (name match)",
                            severity="info",
                        )
                    )
                    continue

                # Assign first unused pin on component
                unused = available - used_pins[pin_ref.ref]
                if unused:
                    assigned = sorted(unused)[0]
                    old_pin = pin_ref.pin
                    pin_ref.pin = assigned
                    used_pins[pin_ref.ref].add(assigned)
                    self.warnings.append(
                        ValidationWarning(
                            f"Net '{net.name}': auto-fixed '{pin_ref.ref}' pin "
                            f"'{old_pin}' → '{assigned}' (first unused)",
                            severity="info",
                        )
                    )
                else:
                    # All pins used — pick first pin as fallback
                    fallback = sorted(available)[0]
                    old_pin = pin_ref.pin
                    pin_ref.pin = fallback
                    self.warnings.append(
                        ValidationWarning(
                            f"Net '{net.name}': auto-fixed '{pin_ref.ref}' pin "
                            f"'{old_pin}' → '{fallback}' (fallback, all used)",
                            severity="info",
                        )
                    )

            # Remove connections referencing non-existent components
            for bad in conns_to_remove:
                net.connections.remove(bad)

    def _clean_degenerate_nets(self) -> None:
        """Remove nets that ended up with fewer than 2 connections after validation."""
        nets_to_remove: list[NetSpec] = []
        for net in self.spec.nets:
            if len(net.connections) < 2:
                self.warnings.append(
                    ValidationWarning(
                        f"Net '{net.name}' has {len(net.connections)} connection(s) — removing",
                        severity="warning",
                    )
                )
                nets_to_remove.append(net)
        for net in nets_to_remove:
            self.spec.nets.remove(net)

    def _check_power_nets(self) -> None:
        """Warn if common power nets (VCC, GND) are missing."""
        net_names = {n.name.upper() for n in self.spec.nets}
        if not any(n in net_names for n in ("GND", "VSS", "GROUND")):
            self.warnings.append(
                ValidationWarning("No GND/VSS net found — most circuits need a ground reference.")
            )
        if not any(
            n in net_names for n in ("VCC", "VDD", "3V3", "5V", "12V", "+5V", "+3.3V", "VIN")
        ):
            self.warnings.append(
                ValidationWarning("No power supply net found (VCC/VDD/VIN).")
            )

    def _check_bypass_caps(self) -> None:
        """Warn if ICs exist without nearby bypass capacitors."""
        ic_refs = {
            c.ref
            for c in self.spec.components
            if c.category in ("ic", "regulator", "opamp", "microcontroller")
        }
        if not ic_refs:
            return

        cap_refs = {c.ref for c in self.spec.components if c.category == "capacitor"}
        # Check if any capacitor shares a power net with an IC
        ic_power_nets = set()
        for net in self.spec.nets:
            has_ic = any(p.ref in ic_refs for p in net.connections)
            has_cap = any(p.ref in cap_refs for p in net.connections)
            if has_ic and net.name.upper() in ("VCC", "VDD", "3V3", "5V"):
                ic_power_nets.add(net.name)
                if not has_cap:
                    self.warnings.append(
                        ValidationWarning(
                            f"Power net '{net.name}' has ICs but no bypass capacitor.",
                            severity="info",
                        )
                    )

    def _assign_positions(self) -> None:
        """Auto-assign grid positions to components that have x=0, y=0."""
        unplaced = [c for c in self.spec.components if c.x_mm == 0 and c.y_mm == 0]
        if not unplaced:
            return

        cols = max(3, int(len(unplaced) ** 0.5) + 1)
        spacing = 25.0  # mm between component centers
        margin = 10.0

        for i, comp in enumerate(unplaced):
            col = i % cols
            row = i // cols
            comp.x_mm = margin + col * spacing
            comp.y_mm = margin + row * spacing

        log.info("Auto-placed %d components on a %d-column grid.", len(unplaced), cols)


def validate_circuit(spec: CircuitSpec) -> tuple[CircuitSpec, list[ValidationWarning]]:
    """Convenience function: validate and return (spec, warnings)."""
    validator = CircuitValidator(spec)
    validated = validator.validate()
    return validated, validator.warnings
