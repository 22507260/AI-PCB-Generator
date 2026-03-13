"""Prompt templates for the AI circuit design engine.

The system prompt instructs GPT-4o to act as an expert electronics
engineer that outputs structured JSON matching our CircuitSpec schema.
"""

from __future__ import annotations

from src.ai.schemas import CircuitSpec

# ---------------------------------------------------------------------------
# JSON schema (exported for structured output mode)
# ---------------------------------------------------------------------------

CIRCUIT_SPEC_SCHEMA = CircuitSpec.model_json_schema()

# ---------------------------------------------------------------------------
# System prompt
# ---------------------------------------------------------------------------

SYSTEM_PROMPT = """\
You are an expert electronics engineer and PCB designer AI assistant.

## Your task
Given a natural-language description of an electronic circuit, you MUST produce
a complete, physically-realizable circuit specification in **JSON** format.

## Rules
1. Select real, commonly-available components with correct values.
2. Every component MUST have a unique reference designator (R1, C1, U1, …).
3. Every component MUST list **ALL** of its pins in the "pins" array with correct
   sequential pin numbers starting from "1" (e.g. a resistor has pins "1" and "2",
   an NE555 has pins "1" through "8", a voltage regulator has "1", "2", "3").
   **Never** leave the pins array empty.
4. Every net MUST connect at least 2 pins using the **exact** ref and pin number
   values from the component's pins array. Use pin **numbers** ("1", "2") NOT names.
5. **Every pin on every component** MUST appear in at least one net. If a pin is
   unused, connect it to an appropriate net (e.g. NC pins to GND via resistor, or
   create a dedicated net). No floating pins.
6. Include **power nets** (VCC, GND, etc.) and **bypass/decoupling capacitors**.
7. Choose appropriate **packages** (0805 for passives, SOT-23 for small ICs, etc.)
   unless the user specifies otherwise.
8. Provide a reasonable **board size** based on component count and spacing.
9. Set **design constraints** (trace width, clearance) appropriate for the
   voltage/current levels in the circuit.
10. The JSON MUST validate against the provided schema with no extra keys.
11. If the user's description is ambiguous, make reasonable engineering choices
    and note them in the description field.
12. **CRITICAL**: The `nets` array MUST be complete and non-empty. **NEVER** output
    an empty or truncated `nets` array. If the circuit is complex, shorten the
    `description` field to save tokens but include **every net**. A circuit with
    no nets cannot be rendered or manufactured.

## Component categories
Use one of: resistor, capacitor, inductor, diode, led, transistor, mosfet,
ic, regulator, opamp, microcontroller, connector, crystal, relay,
transformer, fuse, switch, sensor, other.

## Pin electrical types
Use one of: input, output, power_in, power_out, passive, bidirectional.

## Output format
Return ONLY the JSON object. No markdown fences, no extra text.
"""

# ---------------------------------------------------------------------------
# Few-shot examples (user/assistant pairs)
# ---------------------------------------------------------------------------

FEW_SHOT_EXAMPLES = [
    {
        "role": "user",
        "content": "Simple LED circuit with a 5V power supply, red LED, and current-limiting resistor.",
    },
    {
        "role": "assistant",
        "content": """\
{
  "name": "Simple LED Circuit",
  "description": "A basic circuit with a 5V supply, 330Ω current-limiting resistor, and a red LED. The resistor limits current to approximately 10mA.",
  "components": [
    {
      "ref": "J1",
      "value": "Conn_01x02",
      "category": "connector",
      "package": "PinHeader_1x02_P2.54mm",
      "description": "2-pin power input connector (5V and GND)",
      "pins": [
        {"number": "1", "name": "VIN", "electrical_type": "power_in"},
        {"number": "2", "name": "GND", "electrical_type": "power_in"}
      ]
    },
    {
      "ref": "R1",
      "value": "330Ω",
      "category": "resistor",
      "package": "0805",
      "description": "Current limiting resistor for LED (5V - 2V) / 330Ω ≈ 9mA",
      "pins": [
        {"number": "1", "name": "1", "electrical_type": "passive"},
        {"number": "2", "name": "2", "electrical_type": "passive"}
      ]
    },
    {
      "ref": "D1",
      "value": "Red LED",
      "category": "led",
      "package": "LED_0805",
      "description": "Standard red LED, Vf ≈ 2V",
      "pins": [
        {"number": "1", "name": "A", "electrical_type": "passive"},
        {"number": "2", "name": "K", "electrical_type": "passive"}
      ]
    }
  ],
  "nets": [
    {"name": "VCC", "connections": [{"ref": "J1", "pin": "1"}, {"ref": "R1", "pin": "1"}]},
    {"name": "LED_A", "connections": [{"ref": "R1", "pin": "2"}, {"ref": "D1", "pin": "1"}]},
    {"name": "GND", "connections": [{"ref": "D1", "pin": "2"}, {"ref": "J1", "pin": "2"}]}
  ],
  "board": {"width_mm": 30.0, "height_mm": 20.0, "layers": 2, "thickness_mm": 1.6},
  "constraints": {"trace_width_mm": 0.3, "clearance_mm": 0.2, "via_diameter_mm": 0.8, "via_drill_mm": 0.4}
}""",
    },
    {
        "role": "user",
        "content": "LM7805 5V voltage regulator circuit with input/output connectors and bypass capacitors.",
    },
    {
        "role": "assistant",
        "content": """\
{
  "name": "LM7805 5V Voltage Regulator",
  "description": "Linear 5V regulator from 7-12V input. Includes input/output bypass caps.",
  "components": [
    {
      "ref": "J1", "value": "Conn_01x02", "category": "connector",
      "package": "PinHeader_1x02_P2.54mm", "description": "Power input connector",
      "pins": [
        {"number": "1", "name": "VIN", "electrical_type": "power_in"},
        {"number": "2", "name": "GND", "electrical_type": "power_in"}
      ]
    },
    {
      "ref": "U1", "value": "LM7805", "category": "regulator",
      "package": "TO-220-3", "description": "5V 1.5A positive linear voltage regulator",
      "pins": [
        {"number": "1", "name": "IN",  "electrical_type": "power_in"},
        {"number": "2", "name": "GND", "electrical_type": "power_in"},
        {"number": "3", "name": "OUT", "electrical_type": "power_out"}
      ]
    },
    {
      "ref": "C1", "value": "100nF", "category": "capacitor",
      "package": "0805", "description": "Input bypass capacitor",
      "pins": [
        {"number": "1", "name": "1", "electrical_type": "passive"},
        {"number": "2", "name": "2", "electrical_type": "passive"}
      ]
    },
    {
      "ref": "C2", "value": "10uF", "category": "capacitor",
      "package": "0805", "description": "Output bypass capacitor",
      "pins": [
        {"number": "1", "name": "1", "electrical_type": "passive"},
        {"number": "2", "name": "2", "electrical_type": "passive"}
      ]
    },
    {
      "ref": "J2", "value": "Conn_01x02", "category": "connector",
      "package": "PinHeader_1x02_P2.54mm", "description": "5V output connector",
      "pins": [
        {"number": "1", "name": "5V",  "electrical_type": "power_out"},
        {"number": "2", "name": "GND", "electrical_type": "power_in"}
      ]
    }
  ],
  "nets": [
    {"name": "VIN",     "connections": [{"ref": "J1", "pin": "1"}, {"ref": "U1", "pin": "1"}, {"ref": "C1", "pin": "1"}]},
    {"name": "GND",     "connections": [{"ref": "J1", "pin": "2"}, {"ref": "U1", "pin": "2"}, {"ref": "C1", "pin": "2"}, {"ref": "C2", "pin": "2"}, {"ref": "J2", "pin": "2"}]},
    {"name": "VOUT_5V", "connections": [{"ref": "U1", "pin": "3"}, {"ref": "C2", "pin": "1"}, {"ref": "J2", "pin": "1"}]}
  ],
  "board": {"width_mm": 40.0, "height_mm": 30.0, "layers": 2, "thickness_mm": 1.6},
  "constraints": {"trace_width_mm": 0.5, "clearance_mm": 0.2, "via_diameter_mm": 0.8, "via_drill_mm": 0.4}
}""",
    },
]

# ---------------------------------------------------------------------------
# Helper: build full message list
# ---------------------------------------------------------------------------

def build_messages(user_prompt: str) -> list[dict[str, str]]:
    """Construct the full message history for the OpenAI API call."""
    messages: list[dict[str, str]] = [
        {"role": "system", "content": SYSTEM_PROMPT},
    ]
    messages.extend(FEW_SHOT_EXAMPLES)
    messages.append({"role": "user", "content": user_prompt})
    return messages
