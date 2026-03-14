<p align="center">
  <img src="logo.png" alt="AI PCB Generator Logo" width="380"/>
</p>

<h1 align="center">🚀 AI PCB Generator</h1>

<p align="center">
  <strong>The world's first fully AI-powered, open-source PCB design suite.</strong><br/>
  From natural language to production-ready PCBs — in minutes, not weeks.
</p>

<p align="center">
  <em>Describe your circuit in plain English or Turkish → AI generates the full schematic → auto-places components → routes traces → simulates the circuit → runs DFM analysis → exports Gerber files → orders from JLCPCB with one click.</em>
</p>

<p align="center">

![Python](https://img.shields.io/badge/Python-3.10+-3776AB?logo=python&logoColor=white)
![License](https://img.shields.io/badge/License-MIT-green)
![Qt](https://img.shields.io/badge/GUI-PySide6%2FQt6-41CD52?logo=qt&logoColor=white)
![KiCad](https://img.shields.io/badge/KiCad-9.0-314CB0)
![NgSpice](https://img.shields.io/badge/SPICE-NgSpice%2045-orange)
![Platform](https://img.shields.io/badge/Platform-Windows%20%7C%20macOS%20%7C%20Linux-lightgrey)

[![Buy Me A Coffee](https://img.shields.io/badge/Buy%20Me%20A%20Coffee-Support-FFDD00?logo=buymeacoffee&logoColor=black)](https://buymeacoffee.com/otis21)

</p>

---

## 🌟 Why AI PCB Generator?

Traditional PCB design takes **days or weeks** — you need to learn complex EDA tools, manually draw schematics, place components, route traces, run checks, and generate manufacturing files.

**AI PCB Generator does all of this in under 5 minutes.** Just describe what you want in plain text, and the AI handles everything from circuit design to production-ready output.

> 💬 *"Design a motor driver board with L298N, 12V input, 5V regulator, PWM headers, and flyback diodes"*
>
> ⚡ **Result:** Complete schematic + PCB layout + 3D view + SPICE simulation + DFM analysis + Gerber ZIP — ready to order.

---

## ✨ Key Features

### 🧠 AI-Powered Circuit Design
Type a description in **natural language** and the AI generates a complete circuit specification — components, pin connections, net assignments, footprints, and placement. Supports **OpenAI GPT-4o**, **Google Gemini**, **Anthropic Claude**, or any OpenAI-compatible API.

### 📐 Interactive Drag & Drop Schematic Editor
Full-featured schematic editor with **drag-and-drop** component placement, **real-time wire drawing**, undo/redo, and a searchable component palette with 18+ categories. Edit AI-generated designs or build from scratch.

### 🤖 AI Co-Pilot with ERC Engine
Built-in **Electrical Rules Check** with 8 automated rules — unconnected power pins, missing resistors on LEDs, no ground, multiple output conflicts, missing decoupling capacitors, and more. Smart **pin alias matching** (VIN↔IN, GND↔VSS) eliminates false positives.

### ⚡ Real-Time SPICE Simulation
Simulate your circuit **before manufacturing** with integrated **NgSpice 45** support:
- **DC Operating Point** — Node voltages and branch currents
- **Transient Analysis** — Time-domain waveforms
- **AC Frequency Sweep** — Bode plots and frequency response
- **DC Sweep** — Transfer characteristics

Built-in **MNA (Modified Nodal Analysis) solver** works even without NgSpice installed — no external tools required for basic simulations.

### 🔍 AI Design Review & DFM Analysis
**12 manufacturing-focused checks** powered by industry standards (IPC-2221):

| Check | Description |
|-------|-------------|
| DFM-001 | Power trace current capacity validation |
| DFM-002 | Annular ring verification (via & pad) |
| DFM-003 | Acid trap detection (acute-angle junctions) |
| DFM-004 | Thermal relief recommendations |
| DFM-005 | Silkscreen over pad detection |
| DFM-006 | Component spacing for pick-and-place |
| DFM-007 | Board dimension validation |
| DFM-008 | Via aspect ratio check |
| DFM-009 | Copper balance analysis |
| DFM-010 | Solder bridge risk detection |
| DFM-011 | Minimum drill size verification |
| DFM-012 | Differential pair length mismatch |

Each issue comes with a **0-100 manufacturability score**, severity rating (Critical/Warning/Info), and actionable **fix recommendations**.

### 🏭 One-Click PCB Manufacturing
Go from design to **production order** with a single click:

- **Manufacturer Profiles** — JLCPCB, PCBWay, OSH Park with real capability limits
- **Live Cost Estimation** — PCB cost + SMT assembly breakdown, updated as you change quantity
- **Production Package** — Generates everything you need:
  - 📦 **Gerber ZIP** — Ready to upload to any manufacturer
  - 📋 **BOM CSV** — JLCPCB-compatible Bill of Materials
  - 📍 **Pick & Place CPL** — Component placement for SMT assembly
  - 🔧 **KiCad PCB** — For further editing in KiCad
- **Lead Time Display** — Know exactly when your boards will arrive
- **Capability Validation** — Warns if your design exceeds manufacturer limits

### 🖥️ Professional 3D PCB Viewer
Realistic isometric **3D visualization** with:
- KiCad `.wrl` 3D model loading (VRML 2.0 parser)
- 18+ built-in component models (resistors, capacitors, ICs, connectors, LEDs...)
- Layer toggles (copper, silkscreen, 3D models, wires)
- Smooth rotation, pan, and zoom controls

### 🔧 PCB Layout Engine
- KiCad-quality **EDA-style** layout rendering
- Grid-based auto-placement with intelligent grouping
- **Freerouting** integration for automatic trace routing
- Layer support (F.Cu, B.Cu, inner layers)
- Real-time **DRC** (Design Rule Check) with pad clearance, trace width, via drill validation

### 📦 Multi-Format Export
- **KiCad** `.kicad_pcb` — Open directly in KiCad 9.0
- **Gerber** RS-274X + Excellon drill — Standard manufacturing format
- **SVG** — High-quality vector graphics
- **JSON** — Full circuit data for automation

### 🛠️ Bundled Vendor Tools
All critical tools come **pre-bundled** — no separate installation needed:

| Tool | Version | Status |
|------|---------|--------|
| NgSpice | 45.2 | ✅ Bundled in `vendor/` |
| Freerouting | 2.1.0 | ✅ Bundled in `vendor/` |
| KiCad | 9.0 | 🔍 Auto-detected |

Run `python setup_vendor.py` to download vendor tools automatically.

### 🌐 Multi-Language & Theming
- Full **Turkish** and **English** UI
- **Dark** and **Light** themes
- Live language switching — no restart needed

---

## 🏗 Architecture

```
  User Input (Natural Language)
          │
          ▼
  ┌─────────────────┐
  │   AI Engine      │  GPT-4o / Gemini / Claude / Any LLM
  │   (OpenAI API)   │
  └────────┬────────┘
           │  CircuitSpec (Pydantic JSON)
           ▼
  ┌─────────────────┐     ┌──────────────────┐
  │  Schematic       │────▶│  AI Co-Pilot     │
  │  Editor          │     │  (8 ERC Rules)   │
  └────────┬────────┘     └──────────────────┘
           │
           ▼
  ┌─────────────────┐     ┌──────────────────┐
  │  PCB Generator   │────▶│  DRC Engine      │
  │  + Auto-Router   │     │  (6 Checks)      │
  └────────┬────────┘     └──────────────────┘
           │
           ▼
  ┌─────────────────┐     ┌──────────────────┐
  │  SPICE Simulator │     │  DFM Analysis    │
  │  (NgSpice/MNA)   │     │  (12 Checks)     │
  └────────┬────────┘     └────────┬─────────┘
           │                       │
           ▼                       ▼
  ┌─────────────────────────────────────────┐
  │         Production Output               │
  │  Gerber ZIP │ BOM CSV │ CPL │ KiCad PCB │
  └──────────────────┬──────────────────────┘
                     │
                     ▼
  ┌─────────────────────────────────────────┐
  │     One-Click Manufacturing             │
  │  JLCPCB  │  PCBWay  │  OSH Park        │
  └─────────────────────────────────────────┘
```

---

## 📋 Requirements

| Software | Version | Required? | Description |
|----------|---------|-----------|-------------|
| **Python** | 3.10+ | ✅ Required | Core runtime |
| **AI API Key** | — | ✅ Required | OpenAI, Gemini, Claude, or compatible |
| **KiCad** | 9.0+ | ⚡ Recommended | 3D models & advanced export |
| **Java** | 11+ | 🔧 Optional | For Freerouting auto-routing |
| **NgSpice** | 45+ | 📦 Bundled | SPICE simulation (auto-downloaded) |
| **Freerouting** | 2.1+ | 📦 Bundled | Auto-routing (auto-downloaded) |

---

## 🚀 Installation

### 1. Clone the repository
```bash
git clone https://github.com/22507260/AI-PCB-Generator.git
cd AI-PCB-Generator
```

### 2. Create virtual environment & install
```bash
python -m venv venv

# Windows
venv\Scripts\activate

# macOS/Linux
source venv/bin/activate

pip install -r requirements.txt
```

### 3. Download vendor tools (NgSpice + Freerouting)
```bash
python setup_vendor.py
```

### 4. Configure API Key
```bash
copy .env.example .env    # Windows
# cp .env.example .env    # macOS/Linux

# Edit .env and add your AI API key:
# OPENAI_API_KEY=sk-...
```

### 5. Launch
```bash
python main.py
```

---

## 📖 Usage

### ⚡ Quick Start (5-Step Workflow)

1. **Describe** — Type your circuit in the left panel:
   ```
   Design a sensor board with USB-C 5V input,
   3.3V LDO regulator, 3 status LEDs and I2C header.
   ```
2. **Generate** — Click **⚡ Design** → AI creates the full schematic
3. **Simulate** — Switch to **⚡ Simulation** tab → Run DC/Transient/AC analysis
4. **Review** — Check the **🔍 Design Review** tab → Fix any DFM issues
5. **Manufacture** — Click **🏭 Manufacture** → Generate Gerber ZIP + BOM + CPL → Order

### 🎯 Built-in Templates

| Template | Description |
|----------|-------------|
| 💡 LED Circuit | Simple LED + current-limiting resistor |
| 🔋 Voltage Regulator | 12V → 5V → 3.3V with bypass capacitors |
| 🎮 Arduino Shield | 2 buttons + 3 LEDs + I2C + potentiometer |
| 🌡️ Sensor Module | I2C temperature/humidity + 3.3V regulator |
| ⚙️ Motor Driver | L298N dual H-bridge + PWM + flyback diodes |
| 🔌 USB-C Power | USB-C input + ESD + polarity protection |

### ⌨️ Keyboard Shortcuts

| Shortcut | Action |
|----------|--------|
| `Ctrl+N` | New Project |
| `Ctrl+O` | Open Project |
| `Ctrl+S` | Save Project |
| `Ctrl+E` | Export (KiCad/Gerber/SVG/JSON) |
| `Ctrl+M` | One-Click Manufacture |
| `Ctrl+Z` | Undo |
| `Ctrl+Y` | Redo |
| `Ctrl+,` | Settings |

---

## 📁 Project Structure

```
AI-PCB-Generator/
├── main.py                         # Application entry point
├── setup_vendor.py                 # Vendor tool downloader (NgSpice, Freerouting)
├── requirements.txt                # Python dependencies
├── src/
│   ├── app.py                      # QApplication bootstrap
│   ├── config.py                   # Settings (pydantic-settings + .env)
│   ├── vendor.py                   # Vendor tool auto-discovery
│   ├── ai/
│   │   ├── schemas.py              # Pydantic data models (CircuitSpec, etc.)
│   │   ├── client.py               # LLM API wrapper (OpenAI-compatible)
│   │   ├── prompts.py              # System prompts + few-shot examples
│   │   └── parser.py               # AI output validation & repair
│   ├── pcb/
│   │   ├── generator.py            # Board generation + auto-placement
│   │   ├── router.py               # Freerouting integration
│   │   ├── exporter.py             # KiCad / Gerber / SVG / JSON export
│   │   ├── rules.py                # DRC engine (6 design rule checks)
│   │   ├── dfm.py                  # DFM analysis engine (12 checks)
│   │   ├── manufacturing.py        # One-Click manufacturing pipeline
│   │   └── components.py           # Component database
│   ├── simulation/
│   │   ├── engine.py               # NgSpice + built-in MNA solver
│   │   └── netlist.py              # SPICE netlist generator
│   ├── gui/
│   │   ├── main_window.py          # Main window (6-tab layout)
│   │   ├── input_panel.py          # AI input + template selector
│   │   ├── schematic_view.py       # Drag & Drop schematic editor
│   │   ├── pcb_view.py             # KiCad-quality PCB layout viewer
│   │   ├── view3d.py               # 3D PCB viewer (VRML/OpenGL)
│   │   ├── simulation_view.py      # SPICE simulation UI + plots
│   │   ├── ai_copilot.py           # AI Co-Pilot + ERC engine
│   │   ├── design_review.py        # DFM analysis panel + scoring
│   │   ├── manufacturing_dialog.py # One-Click manufacturing dialog
│   │   ├── component_panel.py      # BOM table
│   │   ├── component_palette.py    # Drag & Drop component palette
│   │   ├── export_dialog.py        # Multi-format export dialog
│   │   ├── settings_dialog.py      # Settings + tool status
│   │   ├── i18n.py                 # Turkish/English translations
│   │   └── theme.py                # Dark/Light theme engine
│   ├── models/
│   │   ├── model_registry.py       # KiCad 3D model mapping
│   │   └── vrml_parser.py          # VRML 2.0 mesh parser
│   └── utils/
│       ├── logger.py               # Structured logging
│       ├── file_io.py              # Project save/load (.apcb)
│       └── validators.py           # Input validation
├── vendor/                         # Bundled tools (auto-downloaded)
│   ├── Spice64/                    # NgSpice 45.2
│   └── freerouting-2.1.0.jar      # Freerouting
├── data/
│   └── templates/                  # Built-in circuit templates
├── assets/                         # Icons, fonts, styles
└── tests/                          # Unit & integration tests
```

---

## 🧪 Testing

```bash
pip install -e ".[dev]"
pytest
```

---

## 📊 Feature Comparison

| Feature | AI PCB Generator | KiCad | EasyEDA | Altium |
|---------|:---------------:|:-----:|:-------:|:------:|
| AI Natural Language Design | ✅ | ❌ | ❌ | ❌ |
| Drag & Drop Schematic | ✅ | ✅ | ✅ | ✅ |
| SPICE Simulation | ✅ | ✅ | ❌ | ✅ |
| DFM Analysis (12 checks) | ✅ | ❌ | ❌ | ✅ |
| One-Click Manufacturing | ✅ | ❌ | ✅ | ❌ |
| AI Co-Pilot (ERC + fixes) | ✅ | ❌ | ❌ | ❌ |
| 3D PCB Viewer | ✅ | ✅ | ✅ | ✅ |
| Cost Estimation | ✅ | ❌ | ✅ | ❌ |
| Open Source | ✅ | ✅ | ❌ | ❌ |
| Free | ✅ | ✅ | ⚠️ | ❌ |

---

## 🤝 Contributing

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/awesome-feature`)
3. Commit your changes (`git commit -m 'feat: add awesome feature'`)
4. Push the branch (`git push origin feature/awesome-feature`)
5. Open a Pull Request

---

## 📄 License

MIT License — see the [LICENSE](LICENSE) file for details.

---

<p align="center">
  <strong>Built with ❤️ using Python, PySide6/Qt6, and AI</strong><br/>
  <sub>Star ⭐ this repo if you find it useful!</sub><br/><br/>
  <a href="https://buymeacoffee.com/otis21">
    <img src="https://img.buymeacoffee.com/button-api/?text=Buy me a coffee&emoji=☕&slug=otis21&button_colour=FFDD00&font_colour=000000&font_family=Poppins&outline_colour=000000&coffee_colour=ffffff" alt="Buy Me A Coffee" />
  </a>
</p>
