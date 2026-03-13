"""Component database backed by SQLite.

Provides a local cache of common electronic components with their
footprint/package information for PCB generation.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Optional

from src.config import DATA_DIR
from src.utils.logger import get_logger

log = get_logger("pcb.components")

DB_PATH = DATA_DIR / "components.db"

# ---------------------------------------------------------------------------
# Schema
# ---------------------------------------------------------------------------

_CREATE_TABLE = """\
CREATE TABLE IF NOT EXISTS components (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    ref_prefix  TEXT    NOT NULL,          -- R, C, U, D, …
    category    TEXT    NOT NULL,          -- resistor, capacitor, …
    value       TEXT    NOT NULL DEFAULT '',
    package     TEXT    NOT NULL DEFAULT '',
    footprint   TEXT    NOT NULL DEFAULT '',
    pin_count   INTEGER NOT NULL DEFAULT 2,
    description TEXT    NOT NULL DEFAULT '',
    manufacturer TEXT   NOT NULL DEFAULT '',
    mpn         TEXT    NOT NULL DEFAULT '',
    datasheet   TEXT    NOT NULL DEFAULT ''
);
"""

_CREATE_INDEX = """\
CREATE INDEX IF NOT EXISTS idx_components_category ON components(category);
"""

# ---------------------------------------------------------------------------
# Seed data — common components
# ---------------------------------------------------------------------------

_SEED_DATA: list[tuple] = [
    # (ref_prefix, category, value, package, footprint, pin_count, description)
    ("R", "resistor", "100Ω", "0805", "Resistor_SMD:R_0805_2012Metric", 2, "100 Ohm 1/8W"),
    ("R", "resistor", "220Ω", "0805", "Resistor_SMD:R_0805_2012Metric", 2, "220 Ohm 1/8W"),
    ("R", "resistor", "330Ω", "0805", "Resistor_SMD:R_0805_2012Metric", 2, "330 Ohm 1/8W"),
    ("R", "resistor", "1kΩ", "0805", "Resistor_SMD:R_0805_2012Metric", 2, "1k Ohm 1/8W"),
    ("R", "resistor", "4.7kΩ", "0805", "Resistor_SMD:R_0805_2012Metric", 2, "4.7k Ohm 1/8W"),
    ("R", "resistor", "10kΩ", "0805", "Resistor_SMD:R_0805_2012Metric", 2, "10k Ohm 1/8W"),
    ("R", "resistor", "100kΩ", "0805", "Resistor_SMD:R_0805_2012Metric", 2, "100k Ohm 1/8W"),
    ("C", "capacitor", "100nF", "0805", "Capacitor_SMD:C_0805_2012Metric", 2, "100nF ceramic"),
    ("C", "capacitor", "1µF", "0805", "Capacitor_SMD:C_0805_2012Metric", 2, "1uF ceramic"),
    ("C", "capacitor", "10µF", "0805", "Capacitor_SMD:C_0805_2012Metric", 2, "10uF ceramic"),
    ("C", "capacitor", "100µF", "electrolytic", "Capacitor_THT:CP_Radial_D6.3mm_P2.50mm", 2, "100uF electrolytic"),
    ("C", "capacitor", "22pF", "0805", "Capacitor_SMD:C_0805_2012Metric", 2, "22pF ceramic (crystal load)"),
    ("D", "diode", "1N4148", "SOD-323", "Diode_SMD:D_SOD-323", 2, "Small signal diode"),
    ("D", "diode", "1N4007", "SMA", "Diode_SMD:D_SMA", 2, "Rectifier diode 1A 1000V"),
    ("D", "led", "Red LED", "0805", "LED_SMD:LED_0805_2012Metric", 2, "Red LED 2V 20mA"),
    ("D", "led", "Green LED", "0805", "LED_SMD:LED_0805_2012Metric", 2, "Green LED 2.2V 20mA"),
    ("D", "led", "Blue LED", "0805", "LED_SMD:LED_0805_2012Metric", 2, "Blue LED 3.2V 20mA"),
    ("U", "regulator", "LM7805", "TO-220", "Package_TO_SOT_THT:TO-220-3_Vertical", 3, "5V linear regulator"),
    ("U", "regulator", "AMS1117-3.3", "SOT-223", "Package_TO_SOT_SMD:SOT-223-3_TabPin2", 3, "3.3V LDO regulator"),
    ("U", "regulator", "LM317", "TO-220", "Package_TO_SOT_THT:TO-220-3_Vertical", 3, "Adjustable voltage regulator"),
    ("U", "opamp", "LM358", "SOIC-8", "Package_SO:SOIC-8_3.9x4.9mm_P1.27mm", 8, "Dual op-amp"),
    ("U", "microcontroller", "ATmega328P", "TQFP-32", "Package_QFP:TQFP-32_7x7mm_P0.8mm", 32, "AVR 8-bit MCU"),
    ("U", "microcontroller", "STM32F103C8T6", "LQFP-48", "Package_QFP:LQFP-48_7x7mm_P0.5mm", 48, "ARM Cortex-M3 MCU"),
    ("U", "microcontroller", "ESP32-WROOM-32", "module", "RF_Module:ESP32-WROOM-32", 38, "WiFi+BT module"),
    ("Q", "transistor", "2N2222", "SOT-23", "Package_TO_SOT_SMD:SOT-23", 3, "NPN transistor"),
    ("Q", "mosfet", "IRLZ44N", "TO-220", "Package_TO_SOT_THT:TO-220-3_Vertical", 3, "N-ch MOSFET 55V 47A"),
    ("J", "connector", "USB-C", "USB-C", "Connector_USB:USB_C_Receptacle_GCT_USB4105", 24, "USB Type-C receptacle"),
    ("J", "connector", "Conn_01x02", "PinHeader_1x02", "Connector_PinHeader_2.54mm:PinHeader_1x02_P2.54mm_Vertical", 2, "2-pin header"),
    ("J", "connector", "Conn_01x04", "PinHeader_1x04", "Connector_PinHeader_2.54mm:PinHeader_1x04_P2.54mm_Vertical", 4, "4-pin header"),
    ("Y", "crystal", "16MHz", "HC49", "Crystal:Crystal_HC49-4H_Vertical", 2, "16MHz crystal"),
    ("Y", "crystal", "8MHz", "HC49", "Crystal:Crystal_HC49-4H_Vertical", 2, "8MHz crystal"),
    ("L", "inductor", "10µH", "0805", "Inductor_SMD:L_0805_2012Metric", 2, "10uH inductor"),
    ("F", "fuse", "500mA", "1206", "Fuse:Fuse_1206_3216Metric", 2, "500mA resettable fuse"),
    ("SW", "switch", "Tactile", "6mm", "Button_Switch_SMD:SW_SPST_CK_RS282G05A3", 2, "Tactile push button"),
]


# ---------------------------------------------------------------------------
# Database manager
# ---------------------------------------------------------------------------

class ComponentDB:
    """SQLite-backed component lookup database."""

    def __init__(self, db_path: Path | str | None = None):
        self._db_path = Path(db_path) if db_path else DB_PATH
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn: sqlite3.Connection | None = None

    # context manager -------------------------------------------------------

    def __enter__(self) -> ComponentDB:
        self.open()
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    # lifecycle --------------------------------------------------------------

    def open(self) -> None:
        self._conn = sqlite3.connect(str(self._db_path))
        self._conn.row_factory = sqlite3.Row
        self._conn.execute(_CREATE_TABLE)
        self._conn.execute(_CREATE_INDEX)
        self._conn.commit()

        # Seed if empty
        cur = self._conn.execute("SELECT COUNT(*) FROM components")
        if cur.fetchone()[0] == 0:
            self._seed()

    def close(self) -> None:
        if self._conn:
            self._conn.close()
            self._conn = None

    # queries ----------------------------------------------------------------

    def search(
        self,
        *,
        category: str = "",
        value: str = "",
        package: str = "",
        limit: int = 50,
    ) -> list[dict]:
        """Search components by category, value, or package (partial match)."""
        assert self._conn is not None
        clauses: list[str] = []
        params: list[str] = []
        if category:
            clauses.append("category = ?")
            params.append(category.lower())
        if value:
            clauses.append("value LIKE ?")
            params.append(f"%{value}%")
        if package:
            clauses.append("package LIKE ?")
            params.append(f"%{package}%")

        where = " AND ".join(clauses) if clauses else "1=1"
        sql = f"SELECT * FROM components WHERE {where} LIMIT ?"
        params.append(str(limit))
        cur = self._conn.execute(sql, params)
        return [dict(row) for row in cur.fetchall()]

    def get_footprint(self, category: str, package: str) -> str:
        """Return the KiCad footprint string for a given category + package."""
        assert self._conn is not None
        cur = self._conn.execute(
            "SELECT footprint FROM components WHERE category = ? AND package LIKE ? LIMIT 1",
            (category.lower(), f"%{package}%"),
        )
        row = cur.fetchone()
        return row["footprint"] if row else ""

    def all_categories(self) -> list[str]:
        assert self._conn is not None
        cur = self._conn.execute("SELECT DISTINCT category FROM components ORDER BY category")
        return [row["category"] for row in cur.fetchall()]

    # internal ---------------------------------------------------------------

    def _seed(self) -> None:
        """Insert built-in seed components."""
        assert self._conn is not None
        self._conn.executemany(
            "INSERT INTO components (ref_prefix, category, value, package, footprint, pin_count, description) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            _SEED_DATA,
        )
        self._conn.commit()
        log.info("Seeded component database with %d entries.", len(_SEED_DATA))
