<p align="center">
  <img src="logo.png" alt="AI PCB Generator Logo" width="380"/>
</p>

<h1 align="center">AI PCB Generator</h1>

<p align="center">An open-source, AI-powered desktop application that generates PCB designs from natural language descriptions.</p>

<p align="center">
Describe your circuit requirements in plain English (or Turkish) → AI generates the schematic → selects components → produces the PCB layout → exports production-ready files.
</p>

<p align="center">

![Python](https://img.shields.io/badge/Python-3.10+-blue)
![License](https://img.shields.io/badge/License-MIT-green)
![Qt](https://img.shields.io/badge/GUI-PySide6%2FQt6-41CD52)

</p>

---

## ✨ Features

- **🧠 AI-Powered Circuit Design** — Natural language input → full circuit specification (OpenAI GPT-4o)
- **📐 Automatic Schematic Generation** — Visual component placement with maze-routed connections
- **🔧 PCB Layout** — Automatic component placement and trace routing
- **🖥️ 3D PCB Viewer** — Realistic isometric 3D view with 18+ component types
- **📦 Multi-Format Export** — KiCad (.kicad_pcb), Gerber, SVG, JSON output
- **🔍 DRC** — Design Rule Check for pre-production error detection
- **📋 BOM** — Bill of Materials generation with CSV export
- **🎨 Modern UI** — Dark/Light theme, English/Turkish interface
- **💾 Project Files** — Save/load projects in .apcb format
- **📚 Built-in Templates** — LED circuit, voltage regulator, motor driver, sensor module, and more

---

## 🏗 Architecture

```
User Input (Natural Language)
        ↓
   [OpenAI GPT-4o]  →  CircuitSpec (JSON)
        ↓
   [SKiDL Netlist]  →  Component + Net generation
        ↓
   [Auto-Placement] →  Grid-based layout
        ↓
   [Freerouting]    →  Automatic trace routing
        ↓
   [DRC Engine]     →  Design Rule Check
        ↓
   [Export]         →  .kicad_pcb / Gerber / SVG / JSON
```

---

## 📋 Requirements

| Software | Version | Required? | Description |
|----------|---------|-----------|-------------|
| **Python** | 3.10+ | ✅ Required | Main programming language |
| **OpenAI API Key** | — | ✅ Required | For AI circuit design |
| **KiCad** | 8.0+ | ⚡ Recommended | For advanced PCB export & 3D models |
| **Java** | 11+ | 🔧 Optional | For Freerouting auto-routing |
| **Freerouting** | 2.0+ | 🔧 Optional | Automatic trace routing |

---

## 🚀 Installation

### 1. Clone the repository
```bash
git clone https://github.com/22507260/AI-PCB-Generator.git
cd AI-PCB-Generator
```

### 2. Create a virtual environment
```bash
python -m venv venv

# Windows
venv\Scripts\activate

# macOS/Linux
source venv/bin/activate
```

### 3. Install dependencies
```bash
pip install -r requirements.txt
```

### 4. Set up API Key
```bash
# Copy the example env file
copy .env.example .env    # Windows
# cp .env.example .env    # macOS/Linux

# Edit .env and add your OpenAI API key
```

### 5. Run the application
```bash
python main.py
```

---

## 📖 Usage

### Quick Start

1. Launch the app (`python main.py`)
2. Type your circuit description in the left panel:
   ```
   Design a sensor board with 5V USB-C input,
   3.3V LDO regulator, and 3 LED indicators.
   ```
3. Click the **⚡ Design** button
4. The AI will generate the schematic + PCB layout
5. Click **📦 Export** to save your files

### Templates

Select from built-in circuit templates in the "Template" dropdown:
- **LED Circuit** — Simple LED + resistor
- **Voltage Regulator** — 12V→5V→3.3V
- **Arduino Shield** — Buttons + LEDs + I2C
- **Sensor Module** — I2C temperature/humidity sensor
- **Motor Driver** — L298N dual H-bridge
- **USB-C Power** — USB-C power supply

### Project Files

- **Save:** `Ctrl+S` → Save as `.apcb` project file
- **Open:** `Ctrl+O` → Load `.apcb` file
- **Export:** `Ctrl+E` → KiCad, Gerber, SVG, JSON

---

## 📁 Project Structure

```
AI-PCB-Generator/
├── main.py                    # Application entry point
├── requirements.txt           # Python dependencies
├── pyproject.toml             # Project metadata
├── .env.example               # Example configuration
├── src/
│   ├── app.py                 # QApplication bootstrap
│   ├── config.py              # Settings (pydantic-settings)
│   ├── ai/
│   │   ├── schemas.py         # Pydantic data models
│   │   ├── client.py          # OpenAI API wrapper
│   │   ├── prompts.py         # System prompt + few-shot examples
│   │   └── parser.py          # AI output validation
│   ├── pcb/
│   │   ├── generator.py       # Board generation + placement
│   │   ├── router.py          # Freerouting integration
│   │   ├── exporter.py        # KiCad/Gerber/SVG/JSON export
│   │   ├── components.py      # SQLite component database
│   │   └── rules.py           # DRC engine
│   ├── gui/
│   │   ├── main_window.py     # Main window
│   │   ├── input_panel.py     # AI input panel
│   │   ├── schematic_view.py  # Schematic viewer
│   │   ├── pcb_view.py        # PCB layout viewer
│   │   ├── view3d.py          # 3D PCB viewer
│   │   ├── component_panel.py # BOM table
│   │   ├── export_dialog.py   # Export dialog
│   │   ├── settings_dialog.py # Settings dialog
│   │   └── theme.py           # Dark/Light theme
│   ├── models/
│   │   ├── model_registry.py  # KiCad 3D model mapping
│   │   └── vrml_parser.py     # VRML 2.0 mesh parser
│   └── utils/
│       ├── logger.py          # Logging
│       ├── file_io.py         # Project save/load
│       └── validators.py      # Input validation
├── data/
│   └── templates/             # Built-in circuit templates (JSON)
├── assets/                    # Icons, styles
└── tests/                     # Unit tests
```

---

## 🧪 Testing

```bash
pip install -e ".[dev]"
pytest
```

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
