"""Internationalization — simple key-based translation system."""

from __future__ import annotations

from PySide6.QtCore import QObject, Signal

_TRANSLATIONS: dict[str, dict[str, str]] = {
    "tr": {
        # ── App / Main Window ──
        "app_title": "AI PCB Generator",
        "menu_file": "Dosya",
        "menu_edit": "Düzenle",
        "menu_view": "Görünüm",
        "menu_help": "Yardım",
        "action_new_project": "Yeni Proje",
        "action_open_project": "Proje Aç...",
        "action_save_project": "Proje Kaydet",
        "action_export": "Dışa Aktar...",
        "action_exit": "Çıkış",
        "action_settings": "Ayarlar...",
        "action_zoom_in": "Yakınlaştır",
        "action_zoom_out": "Uzaklaştır",
        "action_about": "Hakkında",
        "toolbar_main": "Ana Araç Çubuğu",
        "toolbar_new": "📄 Yeni",
        "toolbar_open": "📂 Aç",
        "toolbar_save": "💾 Kaydet",
        "toolbar_export": "📦 Dışa Aktar",
        "toolbar_settings": "⚙ Ayarlar",
        "tab_schematic": "📐 Şematik",
        "tab_pcb_layout": "🔧 PCB Layout",
        "status_ready": "Hazır — Bir devre tanımlayarak başlayın.",
        "status_drc_issues": "DRC: {errors} hata, {warnings} uyarı",
        "status_drc_pass": "DRC geçti — sorun yok ✅",
        "status_new_project": "Yeni proje oluşturuldu.",
        "status_project_loaded": "Proje yüklendi: {name}",
        "status_project_saved": "Proje kaydedildi: {path}",
        "dialog_open_project": "Proje Aç",
        "dialog_save_project": "Proje Kaydet",
        "file_filter_project": "AI PCB Proje (*.apcb);;JSON (*.json)",
        "file_filter_apcb": "AI PCB Proje (*.apcb)",
        "dialog_error": "Hata",
        "dialog_warning": "Uyarı",
        "error_load_project": "Proje yüklenemedi:\n{error}",
        "error_save_project": "Kayıt başarısız:\n{error}",
        "warning_no_circuit": "Kaydedilecek bir devre yok.",
        "warning_design_first": "Önce bir devre tasarlayın.",
        "about_title": "AI PCB Generator Hakkında",
        "about_text": (
            "<h2>AI PCB Generator</h2>"
            "<p>Versiyon 0.1.0</p>"
            "<p>Doğal dil ile PCB tasarımı yapan AI destekli açık kaynak araç.</p>"
            "<p>Lisans: MIT</p>"
        ),

        # ── Input Panel ──
        "title_circuit_desc": "🔌 Devre Tanımı",
        "subtitle_circuit": "Devrenizi doğal dilde tanımlayın, AI tasarlasın.",
        "label_template": "Şablon:",
        "placeholder_circuit": (
            "Örnek: 5V USB-C girişli, 3.3V LDO regülatörlü, "
            "3 LED göstergeli ve I2C header'lı sensör kartı tasarla..."
        ),
        "button_design": "⚡ Tasarla",
        "button_clear": "Temizle",
        "warning_enter_desc": "⚠ Lütfen bir devre tanımı girin.",
        "status_starting_ai": "AI motoru başlatılıyor...",
        "progress_engine_start": "AI motoru çalışıyor...",
        "progress_designing": "Devre tasarlanıyor...",
        "progress_validating": "Doğrulama yapılıyor...",
        "error_unexpected": "Beklenmeyen hata: {error}",
        "success_circuit": "✅ {name} — {components} komponent, {nets} bağlantı",
        "error_circuit": "❌ Hata: {error}",
        "status_circuit_created": "Devre oluşturuldu: {name}",
        "tpl_empty": "Boş",
        "tpl_led": "LED Devresi",
        "tpl_led_desc": "5V güç kaynağı ile çalışan, akım sınırlayıcı dirençli basit kırmızı LED devresi.",
        "tpl_vreg": "Voltaj Regülatörü",
        "tpl_vreg_desc": (
            "12V girişten 5V ve 3.3V çıkış üreten voltaj regülatörü devresi. "
            "Giriş ve çıkışlarda bypass kapasitörleri olsun. LED gösterge ekle."
        ),
        "tpl_arduino": "Arduino Shield",
        "tpl_arduino_desc": (
            "Arduino Uno uyumlu shield. 2 adet buton, 3 adet LED, "
            "I2C header ve bir potansiyometre içersin."
        ),
        "tpl_sensor": "Sensör Modülü",
        "tpl_sensor_desc": (
            "I2C arayüzlü sıcaklık ve nem sensörü modülü. "
            "3.3V regülatör, bypass kapasitörleri ve 4-pin header içersin."
        ),
        "tpl_motor": "Motor Sürücü",
        "tpl_motor_desc": (
            "L298N çift H-köprü motor sürücü devresi. 12V güç girişi, "
            "5V regülatör, PWM giriş headerleri ve flyback diyotları olsun."
        ),
        "tpl_usbc": "USB-C Güç",
        "tpl_usbc_desc": (
            "USB-C girişli 5V güç kaynağı kartı. ESD koruması, "
            "polarity koruması, güç LED göstergesi ve 2 adet çıkış headerı."
        ),

        # ── Settings Dialog ──
        "settings_title": "Ayarlar",
        "settings_heading": "⚙ Uygulama Ayarları",
        "group_openai": "OpenAI Yapılandırması",
        "group_ai_provider": "AI Sağlayıcı",
        "label_provider": "Sağlayıcı:",
        "label_base_url": "API URL:",
        "label_api_key": "API Key:",
        "label_model": "Model:",
        "label_max_tokens": "Maks Token:",
        "group_paths": "Dosya Yolları",
        "label_kicad": "KiCad:",
        "label_kicad_3d": "KiCad 3D:",
        "label_freerouting": "Freerouting:",
        "label_ngspice": "NgSpice:",
        "placeholder_kicad": "C:\\Program Files\\KiCad\\9.0",
        "placeholder_kicad_3d": "Otomatik algılanır (boş bırakılabilir)",
        "placeholder_freerouting": "freerouting.jar yolu",
        "placeholder_ngspice": "ngspice çalıştırılabilir dosya yolu",
        "tool_found": "✅ Bulundu",
        "tool_not_found": "❌ Bulunamadı",
        "tool_bundled": "✅ Gömülü (vendor)",
        "label_tool_status": "Araç Durumu:",
        "group_ui": "Arayüz",
        "label_language": "Dil:",
        "label_theme": "Tema:",
        "theme_dark": "Koyu (Dark)",
        "theme_light": "Açık (Light)",
        "button_cancel": "İptal",
        "button_save": "💾 Kaydet",
        "dialog_select_folder": "Klasör Seç",
        "dialog_select_file": "Dosya Seç",
        "dialog_saved": "Kaydedildi",
        "success_settings_saved": "Ayarlar başarıyla kaydedildi.\nDil ve tema değişiklikleri hemen uygulandı.",
        "warning_zero_nets": "⚠ '{name}' devresi bağlantısız üretildi ({count} komponent, 0 net). Lütfen Ayarlar'dan Maks Token değerini 8192+ yapıp tekrar deneyin.",

        # ── Component Panel ──
        "title_bom": "📋 Komponent Listesi (BOM)",
        "header_ref": "Ref",
        "header_value": "Değer",
        "header_category": "Kategori",
        "header_package": "Paket",
        "header_pins": "Pin",
        "header_description": "Açıklama",
        "header_mpn": "Üretici P/N",
        "button_export_bom": "📥 BOM Dışa Aktar (CSV)",
        "dialog_save_bom": "BOM Kaydet",
        "file_filter_csv": "CSV dosyaları (*.csv)",
        "label_component_count": "{count} komponent",

        # ── Export Dialog ──
        "export_title": "Dışa Aktar",
        "export_heading": "📦 Dışa Aktar: {name}",
        "label_output_folder": "Kayıt klasörü:",
        "group_output_formats": "Çıktı Formatları",
        "checkbox_kicad": "KiCad PCB (.kicad_pcb)",
        "checkbox_svg": "SVG Görsel (.svg)",
        "checkbox_gerber": "Gerber Dosyaları (üretim için)",
        "checkbox_json": "JSON Veri (.json)",
        "group_options": "Seçenekler",
        "checkbox_autoroute": "Otomatik rotalama (Freerouting)",
        "button_export": "⚡ Dışa Aktar",
        "dialog_select_output": "Kayıt Klasörü Seç",
        "warning_select_folder": "Lütfen kayıt klasörü seçin.",
        "warning_select_format": "En az bir çıktı formatı seçin.",
        "progress_creating_pcb": "PCB oluşturuluyor...",
        "progress_routing": "Otomatik rotalama (Freerouting)...",
        "progress_drc": "DRC kontrolleri...",
        "progress_kicad": "KiCad PCB dosyası üretiliyor...",
        "progress_svg": "SVG görsel üretiliyor...",
        "progress_json": "JSON verisi üretiliyor...",
        "progress_gerber": "Gerber dosyaları üretiliyor...",
        "success_exported": "✅ {count} dosya başarıyla dışa aktarıldı!",
        "dialog_success": "Başarılı",
        "message_exported": "{count} dosya dışa aktarıldı:\n\n",
        "error_export": "❌ Hata: {error}",

        # ── PCB View ──
        "label_layers": "Katmanlar:",

        # ── 3D View ──
        "tab_3d_view": "🎲 3D Görünüm",
        "view3d_title": "3D Görünüm",
        "view3d_components": "Komponentler",
        "view3d_traces": "Bakir Yollar",
        "view3d_silkscreen": "Silkscreen",
        "view3d_3d_models": "3D Modeller",
        "view3d_wires": "Kablolar",
        "view3d_reset": "Sıfırla",
        "view3d_no_board": "Önce bir devre tasarımı oluşturun",
        "view3d_hint": "Left: Rotate | Right: Pan | Wheel: Zoom",

        # ── Simulation ──
        "tab_simulation": "⚡ Simülasyon",
        "sim_analysis_type": "Analiz Türü",
        "sim_dc_op": "DC Çalışma Noktası",
        "sim_transient": "Geçici Analiz",
        "sim_ac_sweep": "AC Frekans Taraması",
        "sim_dc_sweep": "DC Tarama",
        "sim_run": "▶ Simülasyonu Çalıştır",
        "sim_running": "Simülasyon çalışıyor...",
        "sim_complete": "✅ Simülasyon tamamlandı",
        "sim_error": "❌ Simülasyon hatası: {error}",
        "sim_no_ngspice": "NgSpice bulunamadı — dahili çözücü kullanılıyor",
        "sim_no_circuit": "Önce bir devre tasarlayın, sonra simülasyonu çalıştırın",
        "sim_signals": "Sinyaller",
        "sim_parameters": "Parametreler",
        "sim_time_step": "Zaman Adımı (dt)",
        "sim_time_stop": "Bitiş Zamanı",
        "sim_freq_start": "Başlangıç Frekansı",
        "sim_freq_stop": "Bitiş Frekansı",
        "sim_source": "Kaynak",

        # ── Schematic Editor ──
        "action_undo": "Geri Al",
        "action_redo": "Yinele",
        "action_delete": "Sil",
        "toolbar_wire": "🔗 Kablo Çiz",
        "palette_title": "🧩 Komponent Paleti",
        "palette_search": "Komponent ara...",
        "edit_component_title": "Komponent Düzenle",
        "edit_ref_label": "Referans:",
        "edit_value_label": "Değer:",

        # ── AI Co-Pilot / ERC ──
        "copilot_title": "🤖 AI Co-Pilot",
        "copilot_run_erc": "🔍 ERC Çalıştır",
        "copilot_no_issues": "✅ Sorun bulunamadı — devre temiz!",
        "copilot_issues_found": "⚠ {errors} hata, {warnings} uyarı bulundu",
        "erc_unconnected_power": "{ref} üzerindeki güç pini ({pin}) bağlı değil",
        "erc_unconnected_pin": "{ref} üzerindeki {pin} pini bağlı değil",
        "erc_led_no_resistor": "{ref} LED'inin akım sınırlayıcı direnci yok",
        "erc_fix_add_resistor": "Seri direnç ekle",
        "erc_no_ground": "Devrede toprak (GND) bağlantısı yok",
        "erc_fix_add_ground": "GND net'i ekle",
        "erc_no_power": "Devrede güç kaynağı bulunamadı",
        "erc_multiple_outputs": "{net} net'inde birden fazla çıkış: {outputs}",
        "erc_no_decoupling": "{ref} IC'sinin dekuplaj kapasitörü yok",
        "erc_fix_add_cap": "100nF dekuplaj kapasitörü ekle",
        "erc_single_pin_net": "{net} net'ine yalnızca bir pin bağlı",

        # ── Design Review / DFM ──
        "tab_design_review": "🔍 Tasarım İnceleme",
        "review_title": "🔍 AI Tasarım İnceleme & DFM Analizi",
        "review_run": "🔬 Analiz Çalıştır",
        "review_score_title": "DFM Üretilebilirlik Skoru",
        "review_no_board": "Önce bir devre tasarlayın, ardından DFM analizi çalıştırın",
        "review_col_issue": "Sorun",
        "review_col_recommendation": "Öneri",
        "review_grade_excellent": "Mükemmel",
        "review_grade_good": "İyi",
        "review_grade_fair": "Orta",
        "review_grade_poor": "Zayıf",
        "review_summary": "{grade} — {critical} kritik, {warnings} uyarı, {info} bilgi",
        "review_all_pass": "✅ Tüm DFM kontrolleri geçti — tasarım üretime hazır!",
    },

    "en": {
        # ── App / Main Window ──
        "app_title": "AI PCB Generator",
        "menu_file": "File",
        "menu_edit": "Edit",
        "menu_view": "View",
        "menu_help": "Help",
        "action_new_project": "New Project",
        "action_open_project": "Open Project...",
        "action_save_project": "Save Project",
        "action_export": "Export...",
        "action_exit": "Exit",
        "action_settings": "Settings...",
        "action_zoom_in": "Zoom In",
        "action_zoom_out": "Zoom Out",
        "action_about": "About",
        "toolbar_main": "Main Toolbar",
        "toolbar_new": "📄 New",
        "toolbar_open": "📂 Open",
        "toolbar_save": "💾 Save",
        "toolbar_export": "📦 Export",
        "toolbar_settings": "⚙ Settings",
        "tab_schematic": "📐 Schematic",
        "tab_pcb_layout": "🔧 PCB Layout",
        "status_ready": "Ready — Start by describing a circuit.",
        "status_drc_issues": "DRC: {errors} error(s), {warnings} warning(s)",
        "status_drc_pass": "DRC passed — no issues ✅",
        "status_new_project": "New project created.",
        "status_project_loaded": "Project loaded: {name}",
        "status_project_saved": "Project saved: {path}",
        "dialog_open_project": "Open Project",
        "dialog_save_project": "Save Project",
        "file_filter_project": "AI PCB Project (*.apcb);;JSON (*.json)",
        "file_filter_apcb": "AI PCB Project (*.apcb)",
        "dialog_error": "Error",
        "dialog_warning": "Warning",
        "error_load_project": "Failed to load project:\n{error}",
        "error_save_project": "Save failed:\n{error}",
        "warning_no_circuit": "No circuit to save.",
        "warning_design_first": "Design a circuit first.",
        "about_title": "About AI PCB Generator",
        "about_text": (
            "<h2>AI PCB Generator</h2>"
            "<p>Version 0.1.0</p>"
            "<p>AI-powered open-source tool for PCB design using natural language.</p>"
            "<p>License: MIT</p>"
        ),

        # ── Input Panel ──
        "title_circuit_desc": "🔌 Circuit Description",
        "subtitle_circuit": "Describe your circuit in natural language, let AI design it.",
        "label_template": "Template:",
        "placeholder_circuit": (
            "Example: Design a sensor board with USB-C 5V input, "
            "3.3V LDO regulator, 3 status LEDs and I2C header..."
        ),
        "button_design": "⚡ Design",
        "button_clear": "Clear",
        "warning_enter_desc": "⚠ Please enter a circuit description.",
        "status_starting_ai": "Starting AI engine...",
        "progress_engine_start": "AI engine running...",
        "progress_designing": "Designing circuit...",
        "progress_validating": "Validating...",
        "error_unexpected": "Unexpected error: {error}",
        "success_circuit": "✅ {name} — {components} components, {nets} nets",
        "error_circuit": "❌ Error: {error}",
        "status_circuit_created": "Circuit created: {name}",
        "tpl_empty": "Empty",
        "tpl_led": "LED Circuit",
        "tpl_led_desc": "Simple red LED circuit with current-limiting resistor, powered by 5V supply.",
        "tpl_vreg": "Voltage Regulator",
        "tpl_vreg_desc": (
            "Voltage regulator circuit producing 5V and 3.3V from 12V input. "
            "Include bypass capacitors on input and output. Add LED indicator."
        ),
        "tpl_arduino": "Arduino Shield",
        "tpl_arduino_desc": (
            "Arduino Uno compatible shield with 2 buttons, 3 LEDs, "
            "I2C header and a potentiometer."
        ),
        "tpl_sensor": "Sensor Module",
        "tpl_sensor_desc": (
            "I2C temperature and humidity sensor module. "
            "3.3V regulator, bypass capacitors and 4-pin header."
        ),
        "tpl_motor": "Motor Driver",
        "tpl_motor_desc": (
            "L298N dual H-bridge motor driver circuit. 12V power input, "
            "5V regulator, PWM input headers and flyback diodes."
        ),
        "tpl_usbc": "USB-C Power",
        "tpl_usbc_desc": (
            "USB-C input 5V power supply board. ESD protection, "
            "polarity protection, power LED indicator and 2 output headers."
        ),

        # ── Settings Dialog ──
        "settings_title": "Settings",
        "settings_heading": "⚙ Application Settings",
        "group_openai": "OpenAI Configuration",
        "group_ai_provider": "AI Provider",
        "label_provider": "Provider:",
        "label_base_url": "API URL:",
        "label_api_key": "API Key:",
        "label_model": "Model:",
        "label_max_tokens": "Max Tokens:",
        "group_paths": "File Paths",
        "label_kicad": "KiCad:",
        "label_kicad_3d": "KiCad 3D:",
        "label_freerouting": "Freerouting:",
        "label_ngspice": "NgSpice:",
        "placeholder_kicad": "C:\\Program Files\\KiCad\\9.0",
        "placeholder_kicad_3d": "Auto-detected (leave empty)",
        "placeholder_freerouting": "Path to freerouting.jar",
        "placeholder_ngspice": "Path to ngspice executable",
        "tool_found": "✅ Found",
        "tool_not_found": "❌ Not found",
        "tool_bundled": "✅ Bundled (vendor)",
        "label_tool_status": "Tool Status:",
        "group_ui": "Interface",
        "label_language": "Language:",
        "label_theme": "Theme:",
        "theme_dark": "Dark",
        "theme_light": "Light",
        "button_cancel": "Cancel",
        "button_save": "💾 Save",
        "dialog_select_folder": "Select Folder",
        "dialog_select_file": "Select File",
        "dialog_saved": "Saved",
        "success_settings_saved": "Settings saved successfully.\nLanguage and theme changes applied immediately.",
        "warning_zero_nets": "⚠ '{name}' circuit was generated with no connections ({count} components, 0 nets). Increase Max Tokens to 8192+ in Settings and try again.",

        # ── Component Panel ──
        "title_bom": "📋 Component List (BOM)",
        "header_ref": "Ref",
        "header_value": "Value",
        "header_category": "Category",
        "header_package": "Package",
        "header_pins": "Pins",
        "header_description": "Description",
        "header_mpn": "MPN",
        "button_export_bom": "📥 Export BOM (CSV)",
        "dialog_save_bom": "Save BOM",
        "file_filter_csv": "CSV files (*.csv)",
        "label_component_count": "{count} components",

        # ── Export Dialog ──
        "export_title": "Export",
        "export_heading": "📦 Export: {name}",
        "label_output_folder": "Output folder:",
        "group_output_formats": "Output Formats",
        "checkbox_kicad": "KiCad PCB (.kicad_pcb)",
        "checkbox_svg": "SVG Image (.svg)",
        "checkbox_gerber": "Gerber Files (for manufacturing)",
        "checkbox_json": "JSON Data (.json)",
        "group_options": "Options",
        "checkbox_autoroute": "Auto-route (Freerouting)",
        "button_export": "⚡ Export",
        "dialog_select_output": "Select Output Folder",
        "warning_select_folder": "Please select an output folder.",
        "warning_select_format": "Select at least one output format.",
        "progress_creating_pcb": "Creating PCB...",
        "progress_routing": "Auto-routing (Freerouting)...",
        "progress_drc": "Running DRC checks...",
        "progress_kicad": "Generating KiCad PCB file...",
        "progress_svg": "Generating SVG image...",
        "progress_json": "Generating JSON data...",
        "progress_gerber": "Generating Gerber files...",
        "success_exported": "✅ {count} files exported successfully!",
        "dialog_success": "Success",
        "message_exported": "{count} files exported:\n\n",
        "error_export": "❌ Error: {error}",

        # ── PCB View ──
        "label_layers": "Layers:",

        # ── 3D View ──
        "tab_3d_view": "🎲 3D View",
        "view3d_title": "3D View",
        "view3d_components": "Components",
        "view3d_traces": "Copper Traces",
        "view3d_silkscreen": "Silkscreen",
        "view3d_3d_models": "3D Models",
        "view3d_wires": "Wires",
        "view3d_reset": "Reset",
        "view3d_no_board": "Design a circuit first",
        "view3d_hint": "Left: Rotate | Right: Pan | Wheel: Zoom",

        # ── Simulation ──
        "tab_simulation": "⚡ Simulation",
        "sim_analysis_type": "Analysis Type",
        "sim_dc_op": "DC Operating Point",
        "sim_transient": "Transient Analysis",
        "sim_ac_sweep": "AC Frequency Sweep",
        "sim_dc_sweep": "DC Sweep",
        "sim_run": "▶ Run Simulation",
        "sim_running": "Simulation running...",
        "sim_complete": "✅ Simulation complete",
        "sim_error": "❌ Simulation error: {error}",
        "sim_no_ngspice": "NgSpice not found — using built-in solver",
        "sim_no_circuit": "Design a circuit first, then run simulation",
        "sim_signals": "Signals",
        "sim_parameters": "Parameters",
        "sim_time_step": "Time Step (dt)",
        "sim_time_stop": "Stop Time",
        "sim_freq_start": "Start Frequency",
        "sim_freq_stop": "Stop Frequency",
        "sim_source": "Source",

        # ── Schematic Editor ──
        "action_undo": "Undo",
        "action_redo": "Redo",
        "action_delete": "Delete",
        "toolbar_wire": "🔗 Draw Wire",
        "palette_title": "🧩 Component Palette",
        "palette_search": "Search components...",
        "edit_component_title": "Edit Component",
        "edit_ref_label": "Reference:",
        "edit_value_label": "Value:",

        # ── AI Co-Pilot / ERC ──
        "copilot_title": "🤖 AI Co-Pilot",
        "copilot_run_erc": "🔍 Run ERC",
        "copilot_no_issues": "✅ No issues found — circuit is clean!",
        "copilot_issues_found": "⚠ {errors} error(s), {warnings} warning(s) found",
        "erc_unconnected_power": "Power pin ({pin}) on {ref} is unconnected",
        "erc_unconnected_pin": "Pin {pin} on {ref} is unconnected",
        "erc_led_no_resistor": "LED {ref} has no current-limiting resistor",
        "erc_fix_add_resistor": "Add series resistor",
        "erc_no_ground": "Circuit has no ground (GND) connection",
        "erc_fix_add_ground": "Add GND net",
        "erc_no_power": "No power source found in circuit",
        "erc_multiple_outputs": "Multiple outputs on net {net}: {outputs}",
        "erc_no_decoupling": "IC {ref} has no decoupling capacitor",
        "erc_fix_add_cap": "Add 100nF decoupling capacitor",
        "erc_single_pin_net": "Net {net} has only one pin connected",

        # ── Design Review / DFM ──
        "tab_design_review": "🔍 Design Review",
        "review_title": "🔍 AI Design Review & DFM Analysis",
        "review_run": "🔬 Run Analysis",
        "review_score_title": "DFM Manufacturability Score",
        "review_no_board": "Design a circuit first, then run DFM analysis",
        "review_col_issue": "Issue",
        "review_col_recommendation": "Recommendation",
        "review_grade_excellent": "Excellent",
        "review_grade_good": "Good",
        "review_grade_fair": "Fair",
        "review_grade_poor": "Poor",
        "review_summary": "{grade} — {critical} critical, {warnings} warning(s), {info} info",
        "review_all_pass": "✅ All DFM checks passed — design is manufacturing-ready!",
    },
}


class Translator(QObject):
    """Singleton translator with live language switching."""

    language_changed = Signal()

    _instance: Translator | None = None

    def __init__(self):
        super().__init__()
        self._lang = "tr"

    @classmethod
    def instance(cls) -> Translator:
        if cls._instance is None:
            cls._instance = Translator()
        return cls._instance

    @property
    def language(self) -> str:
        return self._lang

    def set_language(self, lang: str) -> None:
        lang = lang.lower()
        if lang not in _TRANSLATIONS:
            lang = "tr"
        if lang != self._lang:
            self._lang = lang
            self.language_changed.emit()

    def t(self, key: str, **kwargs: object) -> str:
        """Translate a key, optionally formatting with kwargs."""
        text = _TRANSLATIONS.get(self._lang, {}).get(key)
        if text is None:
            text = _TRANSLATIONS["tr"].get(key, key)
        if kwargs:
            text = text.format(**kwargs)
        return text


def tr(key: str, **kwargs: object) -> str:
    """Module-level shortcut for translation."""
    return Translator.instance().t(key, **kwargs)
