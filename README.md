<p align="center">
  <img src="logo.png" alt="AI PCB Generator Logo" width="200"/>
</p>

<h1 align="center">AI PCB Generator</h1>

<p align="center">Doğal dil ile PCB tasarımı yapan AI destekli açık kaynak masaüstü uygulaması.</p>

Devre gereksinimlerinizi Türkçe veya İngilizce olarak yazın → AI şematik oluşturur → komponent seçer → PCB layout çıkarır → üretim-hazır dosyalar üretir.

![Python](https://img.shields.io/badge/Python-3.10+-blue)
![License](https://img.shields.io/badge/License-MIT-green)
![Qt](https://img.shields.io/badge/GUI-PySide6%2FQt6-41CD52)

---

## ✨ Özellikler

- **🧠 AI ile Devre Tasarımı** — Doğal dil girdisi → tam devre spesifikasyonu (OpenAI GPT-4o)
- **📐 Otomatik Şematik** — Komponent ve bağlantıları görsel olarak oluşturur
- **🔧 PCB Layout** — Otomatik komponent yerleşimi ve trace routing
- **📦 Çoklu Export** — KiCad (.kicad_pcb), Gerber, SVG, JSON formatlarında çıktı
- **🔍 DRC** — Design Rule Check ile üretim öncesi hata kontrolü
- **📋 BOM** — Bill of Materials oluşturma ve CSV export
- **🎨 Modern UI** — Dark/Light tema, Türkçe/İngilizce arayüz
- **💾 Proje Kaydetme** — .apcb formatında proje dosyaları
- **📚 Hazır Şablonlar** — LED devresi, voltaj regülatörü, sensör modülü vb.

---

## 🏗 Mimari

```
Kullanıcı Girdisi (Doğal Dil)
        ↓
   [OpenAI GPT-4o]  →  CircuitSpec (JSON)
        ↓
   [SKiDL Netlist]  →  Komponent + Net oluşturma
        ↓
   [Auto-Placement] →  Grid-based yerleşim
        ↓
   [Freerouting]    →  Otomatik trace routing
        ↓
   [DRC Engine]     →  Design Rule Check
        ↓
   [Export]         →  .kicad_pcb / Gerber / SVG / JSON
```

---

## 📋 Gereksinimler

| Yazılım | Versiyon | Gerekli? | Açıklama |
|---------|----------|----------|----------|
| **Python** | 3.10+ | ✅ Zorunlu | Ana programlama dili |
| **OpenAI API Key** | — | ✅ Zorunlu | AI devre tasarımı için |
| **KiCad** | 8.0+ | ⚡ Önerilen | Gelişmiş PCB export için |
| **Java** | 11+ | 🔧 Opsiyonel | Freerouting otomatik rotalama için |
| **Freerouting** | 2.0+ | 🔧 Opsiyonel | Otomatik trace routing |

---

## 🚀 Kurulum

### 1. Depoyu klonla
```bash
git clone https://github.com/22507260/AI-PCB-Generator.git
cd AI-PCB-Generator
```

### 2. Sanal ortam oluştur
```bash
python -m venv venv

# Windows
venv\Scripts\activate

# macOS/Linux
source venv/bin/activate
```

### 3. Bağımlılıkları kur
```bash
pip install -r requirements.txt
```

### 4. API Key ayarla
```bash
# .env.example dosyasını kopyala
copy .env.example .env    # Windows
# cp .env.example .env    # macOS/Linux

# .env dosyasını düzenle ve OpenAI API key'ini ekle
```

### 5. Uygulamayı başlat
```bash
python main.py
```

---

## 📖 Kullanım

### Hızlı Başlangıç

1. Uygulamayı açın (`python main.py`)
2. Sol paneldeki metin alanına devre tanımınızı yazın:
   ```
   5V USB-C girişli, 3.3V LDO regülatörlü,
   3 LED göstergeli sensör kartı tasarla.
   ```
3. **⚡ Tasarla** butonuna tıklayın
4. AI devreyi tasarlayacak ve şematik + PCB layout'u gösterecek
5. **📦 Dışa Aktar** ile dosyaları kaydedin

### Şablon Kullanımı

Sol paneldeki "Şablon" açılır menüsünden hazır devre şablonlarından birini seçebilirsiniz:
- **LED Devresi** — Basit LED + direnç
- **Voltaj Regülatörü** — 12V→5V→3.3V
- **Arduino Shield** — Buton + LED + I2C
- **Sensör Modülü** — I2C sıcaklık/nem sensörü
- **Motor Sürücü** — L298N H-köprü
- **USB-C Güç** — USB-C güç kaynağı

### Proje Dosyaları

- **Kaydet:** `Ctrl+S` → `.apcb` formatında proje dosyası
- **Aç:** `Ctrl+O` → `.apcb` dosyasını yükle
- **Dışa Aktar:** `Ctrl+E` → KiCad, Gerber, SVG, JSON

---

## 📁 Proje Yapısı

```
ai-pcb-generator/
├── main.py                    # Uygulama giriş noktası
├── requirements.txt           # Python bağımlılıkları
├── pyproject.toml             # Proje meta verisi
├── .env.example               # Örnek konfigürasyon
├── src/
│   ├── app.py                 # QApplication bootstrap
│   ├── config.py              # Ayarlar (pydantic-settings)
│   ├── ai/
│   │   ├── schemas.py         # Pydantic veri modelleri
│   │   ├── client.py          # OpenAI API wrapper
│   │   ├── prompts.py         # System prompt + few-shot
│   │   └── parser.py          # AI çıktı doğrulama
│   ├── pcb/
│   │   ├── generator.py       # Board oluşturma + yerleşim
│   │   ├── router.py          # Freerouting entegrasyonu
│   │   ├── exporter.py        # KiCad/Gerber/SVG/JSON export
│   │   ├── components.py      # SQLite komponent veritabanı
│   │   └── rules.py           # DRC motoru
│   ├── gui/
│   │   ├── main_window.py     # Ana pencere
│   │   ├── input_panel.py     # AI giriş paneli
│   │   ├── schematic_view.py  # Şematik görüntüleyici
│   │   ├── pcb_view.py        # PCB layout görüntüleyici
│   │   ├── component_panel.py # BOM tablosu
│   │   ├── export_dialog.py   # Export dialogu
│   │   ├── settings_dialog.py # Ayarlar dialogu
│   │   └── theme.py           # Dark/Light tema
│   └── utils/
│       ├── logger.py          # Logging
│       ├── file_io.py         # Proje kaydet/yükle
│       └── validators.py      # Girdi doğrulama
├── data/
│   └── templates/             # Hazır devre şablonları (JSON)
├── assets/                    # İkonlar, stiller
└── tests/                     # Unit testler
```

---

## 🧪 Test

```bash
pip install -e ".[dev]"
pytest
```

---

## 🤝 Katkıda Bulunma

1. Fork yapın
2. Feature branch oluşturun (`git checkout -b feature/awesome-feature`)
3. Değişikliklerinizi commit edin (`git commit -m 'feat: add awesome feature'`)
4. Branch'i push edin (`git push origin feature/awesome-feature`)
5. Pull Request açın

---

## 📄 Lisans

MIT License — detaylar için [LICENSE](LICENSE) dosyasına bakın.

---

## 🙏 Teşekkürler

- [OpenAI](https://openai.com/) — GPT-4o AI modeli
- [KiCad](https://www.kicad.org/) — Açık kaynak EDA
- [Freerouting](https://github.com/freerouting/freerouting) — Otomatik PCB routing
- [Qt/PySide6](https://www.qt.io/) — GUI framework
