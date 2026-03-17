"""Settings dialog — API keys, paths, and preferences."""

from __future__ import annotations

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QFormLayout,
    QGroupBox, QLineEdit, QPushButton, QComboBox,
    QLabel, QFileDialog, QMessageBox, QApplication, QSpinBox,
)
from PySide6.QtCore import Qt

from src.config import get_settings, ROOT_DIR
from src.gui.i18n import tr, Translator
from src.gui.theme import DARK_THEME, LIGHT_THEME, ThemeManager
from src.vendor import get_tool_status
from src.utils.env_file import merge_env_values
from src.utils.logger import get_logger

log = get_logger("gui.settings_dialog")


class SettingsDialog(QDialog):
    """Application settings dialog."""

    # Provider presets: (display_name, base_url, default_models)
    _PROVIDERS = [
        ("OpenAI",          "",                                    ["gpt-4o", "gpt-4o-mini", "gpt-4-turbo", "gpt-3.5-turbo", "o1", "o1-mini"]),
        ("Ollama (Local)",   "http://localhost:11434/v1",            ["llama3.1", "llama3.2", "qwen2.5", "mistral", "deepseek-r1", "gemma2", "codellama"]),
        ("Groq",            "https://api.groq.com/openai/v1",      ["llama-3.3-70b-versatile", "llama-3.1-8b-instant", "mixtral-8x7b-32768", "gemma2-9b-it"]),
        ("OpenRouter",      "https://openrouter.ai/api/v1",        ["openai/gpt-4o", "anthropic/claude-3.5-sonnet", "meta-llama/llama-3.1-70b-instruct", "google/gemini-pro"]),
        ("Together AI",     "https://api.together.xyz/v1",         ["meta-llama/Llama-3.3-70B-Instruct-Turbo", "mistralai/Mixtral-8x7B-Instruct-v0.1", "Qwen/Qwen2.5-72B-Instruct-Turbo"]),
        ("LM Studio (Local)", "http://localhost:1234/v1",           ["local-model"]),
        ("DeepSeek",        "https://api.deepseek.com/v1",         ["deepseek-chat", "deepseek-reasoner"]),
        ("Custom",          "",                                    []),
    ]

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumSize(550, 450)
        self._setup_ui()
        self._load_current()
        self._retranslate()
        Translator.instance().language_changed.connect(self._retranslate)

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(12)

        self._title_label = QLabel()
        self._title_label.setObjectName("titleLabel")
        layout.addWidget(self._title_label)

        # --- AI Provider ---
        self._ai_group = QGroupBox()
        ai_form = QFormLayout(self._ai_group)

        self._provider_combo = QComboBox()
        for name, _, _ in self._PROVIDERS:
            self._provider_combo.addItem(name)
        self._provider_combo.currentIndexChanged.connect(self._on_provider_changed)
        self._lbl_provider = QLabel()
        ai_form.addRow(self._lbl_provider, self._provider_combo)

        self._base_url = QLineEdit()
        self._base_url.setPlaceholderText("https://api.example.com/v1")
        self._lbl_base_url = QLabel()
        ai_form.addRow(self._lbl_base_url, self._base_url)

        self._api_key = QLineEdit()
        self._api_key.setEchoMode(QLineEdit.EchoMode.Password)
        self._api_key.setPlaceholderText("sk-...")
        self._lbl_api_key = QLabel()
        ai_form.addRow(self._lbl_api_key, self._api_key)

        self._model_combo = QComboBox()
        self._model_combo.setEditable(True)
        self._lbl_model = QLabel()
        ai_form.addRow(self._lbl_model, self._model_combo)

        self._max_tokens_spin = QSpinBox()
        self._max_tokens_spin.setRange(1024, 32768)
        self._max_tokens_spin.setSingleStep(1024)
        self._max_tokens_spin.setValue(8192)
        self._lbl_max_tokens = QLabel()
        ai_form.addRow(self._lbl_max_tokens, self._max_tokens_spin)

        layout.addWidget(self._ai_group)

        # --- Paths ---
        self._path_group = QGroupBox()
        path_form = QFormLayout(self._path_group)

        kicad_row = QHBoxLayout()
        self._kicad_path = QLineEdit()
        kicad_row.addWidget(self._kicad_path, 1)
        kicad_browse = QPushButton("📁")
        kicad_browse.setMaximumWidth(40)
        kicad_browse.clicked.connect(lambda: self._browse(self._kicad_path))
        kicad_row.addWidget(kicad_browse)
        self._lbl_kicad = QLabel()
        path_form.addRow(self._lbl_kicad, kicad_row)

        kicad_3d_row = QHBoxLayout()
        self._kicad_3d_path = QLineEdit()
        kicad_3d_row.addWidget(self._kicad_3d_path, 1)
        kicad_3d_browse = QPushButton("📁")
        kicad_3d_browse.setMaximumWidth(40)
        kicad_3d_browse.clicked.connect(lambda: self._browse(self._kicad_3d_path))
        kicad_3d_row.addWidget(kicad_3d_browse)
        self._lbl_kicad_3d = QLabel()
        path_form.addRow(self._lbl_kicad_3d, kicad_3d_row)

        fr_row = QHBoxLayout()
        self._fr_path = QLineEdit()
        fr_row.addWidget(self._fr_path, 1)
        fr_browse = QPushButton("📁")
        fr_browse.setMaximumWidth(40)
        fr_browse.clicked.connect(lambda: self._browse_file(self._fr_path, "JAR (*.jar)"))
        fr_row.addWidget(fr_browse)
        self._lbl_freerouting = QLabel()
        path_form.addRow(self._lbl_freerouting, fr_row)

        ngspice_row = QHBoxLayout()
        self._ngspice_path = QLineEdit()
        ngspice_row.addWidget(self._ngspice_path, 1)
        ngspice_browse = QPushButton("📁")
        ngspice_browse.setMaximumWidth(40)
        ngspice_browse.clicked.connect(lambda: self._browse_file(self._ngspice_path, "Executable (*.exe);;All (*)"))
        ngspice_row.addWidget(ngspice_browse)
        self._lbl_ngspice = QLabel()
        path_form.addRow(self._lbl_ngspice, ngspice_row)

        # Tool status indicators
        self._tool_status_label = QLabel()
        self._tool_status_label.setWordWrap(True)
        self._tool_status_label.setStyleSheet("font-size: 12px; padding: 4px;")
        path_form.addRow("", self._tool_status_label)

        layout.addWidget(self._path_group)

        # --- UI ---
        self._ui_group = QGroupBox()
        ui_form = QFormLayout(self._ui_group)

        self._lang_combo = QComboBox()
        self._lang_combo.addItems(["Türkçe", "English"])
        self._lbl_lang = QLabel()
        ui_form.addRow(self._lbl_lang, self._lang_combo)

        self._theme_combo = QComboBox()
        self._lbl_theme = QLabel()
        ui_form.addRow(self._lbl_theme, self._theme_combo)

        layout.addWidget(self._ui_group)

        layout.addStretch()

        # Buttons
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()

        self._cancel_btn = QPushButton()
        self._cancel_btn.setObjectName("secondaryButton")
        self._cancel_btn.clicked.connect(self.reject)
        btn_layout.addWidget(self._cancel_btn)

        self._save_btn = QPushButton()
        self._save_btn.setMinimumWidth(120)
        self._save_btn.clicked.connect(self._save)
        btn_layout.addWidget(self._save_btn)

        layout.addLayout(btn_layout)

    def _load_current(self):
        """Load current settings into the form."""
        settings = get_settings()
        if settings.openai_api_key:
            self._api_key.setText(settings.openai_api_key)

        # Detect provider from base_url
        base_url = settings.openai_base_url.strip()
        provider_idx = len(self._PROVIDERS) - 1  # default to Custom
        for i, (_, url, _) in enumerate(self._PROVIDERS):
            if url and base_url == url:
                provider_idx = i
                break
            elif i == 0 and not base_url:  # empty = OpenAI
                provider_idx = 0
                break
        self._provider_combo.setCurrentIndex(provider_idx)
        self._base_url.setText(base_url)
        self._on_provider_changed(provider_idx)

        self._max_tokens_spin.setValue(settings.openai_max_tokens)

        # Set model (after provider populates model list)
        idx = self._model_combo.findText(settings.openai_model)
        if idx >= 0:
            self._model_combo.setCurrentIndex(idx)
        else:
            self._model_combo.setEditText(settings.openai_model)

        self._kicad_path.setText(settings.kicad_path)
        self._kicad_3d_path.setText(settings.kicad_3dmodels_path)
        self._fr_path.setText(settings.freerouting_jar)
        self._ngspice_path.setText(settings.ngspice_path)
        self._update_tool_status()
        self._lang_combo.setCurrentIndex(0 if settings.language == "tr" else 1)
        self._theme_combo.setCurrentIndex(0 if settings.theme == "dark" else 1)

    def _on_provider_changed(self, index: int):
        """Update base URL and model presets when provider changes."""
        if index < 0 or index >= len(self._PROVIDERS):
            return
        name, url, models = self._PROVIDERS[index]
        is_custom = (index == len(self._PROVIDERS) - 1)

        # Set base URL (editable only for Custom)
        self._base_url.setReadOnly(not is_custom)
        if not is_custom:
            self._base_url.setText(url)

        # Update model presets
        current_model = self._model_combo.currentText()
        self._model_combo.clear()
        if models:
            self._model_combo.addItems(models)
        # Restore if it was in the list, otherwise keep typed value
        idx = self._model_combo.findText(current_model)
        if idx >= 0:
            self._model_combo.setCurrentIndex(idx)
        elif current_model:
            self._model_combo.setEditText(current_model)

    def _retranslate(self):
        """Update all labels to the current language."""
        self.setWindowTitle(tr("settings_title"))
        self._title_label.setText(tr("settings_heading"))
        self._ai_group.setTitle(tr("group_ai_provider"))
        self._lbl_provider.setText(tr("label_provider"))
        self._lbl_base_url.setText(tr("label_base_url"))
        self._lbl_api_key.setText(tr("label_api_key"))
        self._lbl_model.setText(tr("label_model"))
        self._lbl_max_tokens.setText(tr("label_max_tokens"))
        self._path_group.setTitle(tr("group_paths"))
        self._lbl_kicad.setText(tr("label_kicad"))
        self._kicad_path.setPlaceholderText(tr("placeholder_kicad"))
        self._lbl_kicad_3d.setText(tr("label_kicad_3d"))
        self._kicad_3d_path.setPlaceholderText(tr("placeholder_kicad_3d"))
        self._lbl_freerouting.setText(tr("label_freerouting"))
        self._fr_path.setPlaceholderText(tr("placeholder_freerouting"))
        self._lbl_ngspice.setText(tr("label_ngspice"))
        self._ngspice_path.setPlaceholderText(tr("placeholder_ngspice"))
        self._update_tool_status()
        self._ui_group.setTitle(tr("group_ui"))
        self._lbl_lang.setText(tr("label_language"))
        self._lbl_theme.setText(tr("label_theme"))
        self._theme_combo.clear()
        self._theme_combo.addItems([tr("theme_dark"), tr("theme_light")])
        # Restore selection after clear
        settings = get_settings()
        self._theme_combo.setCurrentIndex(0 if settings.theme == "dark" else 1)
        self._cancel_btn.setText(tr("button_cancel"))
        self._save_btn.setText(tr("button_save"))

    def _update_tool_status(self):
        """Refresh tool detection status indicators."""
        status = get_tool_status()
        parts = []
        for name, info in status.items():
            if info["found"]:
                if "vendor" in info.get("path", ""):
                    label = tr("tool_bundled")
                else:
                    label = tr("tool_found")
            else:
                label = tr("tool_not_found")
            parts.append(f"<b>{name}:</b> {label}")
        self._tool_status_label.setText("<br>".join(parts))

    def _save(self):
        """Write settings to .env file."""
        env_path = ROOT_DIR / ".env"
        api_key = self._api_key.text().strip()
        base_url = self._base_url.text().strip()
        kicad = self._kicad_path.text().strip()
        kicad_3d = self._kicad_3d_path.text().strip()
        fr = self._fr_path.text().strip()
        ngspice = self._ngspice_path.text().strip()
        lang = "tr" if self._lang_combo.currentIndex() == 0 else "en"
        theme = "dark" if self._theme_combo.currentIndex() == 0 else "light"

        updates: dict[str, str | None] = {
            "OPENAI_API_KEY": api_key or None,
            "OPENAI_BASE_URL": base_url or None,
            "OPENAI_MODEL": self._model_combo.currentText(),
            "OPENAI_MAX_TOKENS": str(self._max_tokens_spin.value()),
            "KICAD_PATH": kicad or None,
            "KICAD_3DMODELS_PATH": kicad_3d or None,
            "FREEROUTING_JAR": fr or None,
            "NGSPICE_PATH": ngspice or None,
            "LANGUAGE": lang,
            "THEME": theme,
            "LOG_LEVEL": "INFO",
        }
        ordered_keys = [
            "OPENAI_API_KEY",
            "OPENAI_BASE_URL",
            "OPENAI_MODEL",
            "OPENAI_MAX_TOKENS",
            "KICAD_PATH",
            "KICAD_3DMODELS_PATH",
            "FREEROUTING_JAR",
            "NGSPICE_PATH",
            "LANGUAGE",
            "THEME",
            "LOG_LEVEL",
        ]

        existing_text = env_path.read_text(encoding="utf-8") if env_path.exists() else ""
        merged = merge_env_values(existing_text, updates, ordered_keys=ordered_keys)
        env_path.write_text(merged, encoding="utf-8")

        # Clear settings cache so changes take effect
        get_settings.cache_clear()

        # Apply theme immediately
        app = QApplication.instance()
        if app:
            if theme == "dark":
                app.setStyleSheet(DARK_THEME)
            else:
                app.setStyleSheet(LIGHT_THEME)
        ThemeManager.instance().set_dark(theme == "dark")

        # Apply language immediately
        Translator.instance().set_language(lang)

        log.info("Settings saved to %s", env_path)
        QMessageBox.information(self, tr("dialog_saved"), tr("success_settings_saved"))
        self.accept()

    def _browse(self, line_edit: QLineEdit):
        d = QFileDialog.getExistingDirectory(self, tr("dialog_select_folder"))
        if d:
            line_edit.setText(d)

    def _browse_file(self, line_edit: QLineEdit, filter_str: str):
        f, _ = QFileDialog.getOpenFileName(self, tr("dialog_select_file"), "", filter_str)
        if f:
            line_edit.setText(f)
