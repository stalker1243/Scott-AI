"""
Красивый лаунчер Скотта (Qt / PySide6) с лёгкими анимациями.

Запуск:
    cd backend
    python -m pip install -r launcher/requirements_ui.txt
    python launcher/launcher_qt.py

Лаунчер читает/пишет backend/config.json и запускает режимы.
Поддерживает сворачивание в трей.
"""

from __future__ import annotations

import math
import os
import shutil
import subprocess
import sys
from pathlib import Path

# Добавляем backend в sys.path для импорта модулей
BACKEND_DIR = Path(__file__).resolve().parent.parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from PySide6 import QtCore, QtGui, QtWidgets

try:
    # Нормальный путь, когда модуль есть как отдельный файл/пакет
    from config_store import AppConfig, load_config, save_config
except ModuleNotFoundError:
    # Резервный вариант: минимальная реализация прямо в лаунчере,
    # чтобы EXE/переносимые сборки не падали, даже если модуль не найден.
    from dataclasses import dataclass, asdict
    import json

    @dataclass
    class AppConfig:  # type: ignore[override]
        user_name: str = ""
        user_title: str = "сэр"
        preferred_voice_gender: str = "male"
        voice_preset: str = "scott_brutal_ru"
        llm_provider: str = "ollama"
        llm_model: str = "qwen2.5:7b"
        llm_temperature: float = 0.4
        llm_max_tokens: int = 160
        asr_model_size: str = "tiny"
        asr_language: str = "ru"
        asr_device: str = "cpu"
        input_device_id: int = -1
        memory_path: str = "./data/memory.jsonl"
        offline_game_limit_minutes: int = 90
        activity_advice_cooldown_minutes: int = 20
        enable_power_confirmation: bool = True
        assistant_memory_path: str = "./data/assistant_profile.json"
        ui_font_family: str = "Segoe UI"
        ui_font_size: int = 14
        ui_accent_color: str = "#72A0FF"
        ui_text_color: str = "#EAF0FF"
        ui_panel_opacity_left: int = 75
        ui_panel_opacity_right: int = 80

    def load_config(path: Path) -> AppConfig:  # type: ignore[override]
        try:
            if not path.exists():
                return AppConfig()
            data = json.loads(path.read_text(encoding="utf-8"))
            cfg = AppConfig()
            for k, v in data.items():
                if hasattr(cfg, k):
                    setattr(cfg, k, v)
            return cfg
        except Exception:
            return AppConfig()

    def save_config(cfg: AppConfig, path: Path) -> None:  # type: ignore[override]
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(asdict(cfg), ensure_ascii=False, indent=2), encoding="utf-8")

from tts_core import list_available_voices
from system_control import SystemController
from system_control.app_discovery import scan_installed_apps, AppMatch


ASSETS_DIR = BACKEND_DIR / "assets"


class GlassButton(QtWidgets.QPushButton):
    """Кнопка с лёгкими анимациями (hover/press)."""

    def __init__(self, text: str, min_height: int = 44):
        super().__init__(text)
        self.setCursor(QtGui.QCursor(QtCore.Qt.CursorShape.PointingHandCursor))
        self.setMinimumHeight(min_height)
        self._anim = QtCore.QPropertyAnimation(self, b"geometry", self)
        self._anim.setDuration(140)
        self._anim.setEasingCurve(QtCore.QEasingCurve.Type.OutCubic)

    def enterEvent(self, event):  # noqa: N802
        g = self.geometry()
        target = QtCore.QRect(g.x(), g.y() - 1, g.width(), g.height() + 2)
        self._anim.stop()
        self._anim.setStartValue(g)
        self._anim.setEndValue(target)
        self._anim.start()
        super().enterEvent(event)

    def leaveEvent(self, event):  # noqa: N802
        g = self.geometry()
        target = QtCore.QRect(g.x(), g.y() + 1, g.width(), max(self.minimumHeight(), g.height() - 2))
        self._anim.stop()
        self._anim.setStartValue(g)
        self._anim.setEndValue(target)
        self._anim.start()
        super().leaveEvent(event)


class LogoGlow(QtWidgets.QWidget):
    """Виджет логотипа с неоновым кольцом и пульсацией."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(132, 132)
        self._pix: QtGui.QPixmap | None = None
        self._phase = 0.0
        self._glow = 0.6
        self._accent = QtGui.QColor(114, 160, 255)

        self._timer = QtCore.QTimer(self)
        self._timer.timeout.connect(self._tick)
        self._timer.start(33)

    def setPixmap(self, pix: QtGui.QPixmap | None) -> None:
        self._pix = pix
        self.update()

    def setAccent(self, c: QtGui.QColor) -> None:  # noqa: N802
        self._accent = QtGui.QColor(c)
        self.update()

    def setGlow(self, v: float) -> None:  # noqa: N802
        self._glow = max(0.0, min(1.0, float(v)))
        self.update()

    def glow(self) -> float:  # noqa: D401
        return float(self._glow)

    glow = QtCore.Property(float, glow, setGlow)

    def _tick(self) -> None:
        self._phase += 0.06
        # мягкая пульсация 0.45..0.95
        self._glow = 0.70 + 0.25 * float(math.sin(self._phase))
        self.update()

    def paintEvent(self, event):  # noqa: N802
        p = QtGui.QPainter(self)
        p.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing, True)

        r = self.rect()
        cx, cy = r.center().x(), r.center().y()

        # фон (glass)
        bg = QtGui.QColor(255, 255, 255, 12)
        border = QtGui.QColor(255, 255, 255, 26)
        p.setPen(QtGui.QPen(border, 1))
        p.setBrush(QtGui.QBrush(bg))
        p.drawRoundedRect(r.adjusted(1, 1, -1, -1), 18, 18)

        # неоновое кольцо
        base_alpha = int(120 * self._glow)
        ring_color = QtGui.QColor(self._accent.red(), self._accent.green(), self._accent.blue(), base_alpha)
        pen = QtGui.QPen(ring_color, 4)
        pen.setCapStyle(QtCore.Qt.PenCapStyle.RoundCap)
        p.setPen(pen)
        ring_rect = r.adjusted(8, 8, -8, -8)
        # вращающаяся дуга + блик
        start = int((self._phase * 120) % 360) * 16
        span = 220 * 16
        p.drawArc(ring_rect, start, span)

        # подсветка-дымка
        glow = QtGui.QRadialGradient(cx, cy, r.width() * 0.55)
        glow.setColorAt(0.0, QtGui.QColor(self._accent.red(), self._accent.green(), self._accent.blue(), int(85 * self._glow)))
        glow.setColorAt(1.0, QtGui.QColor(self._accent.red(), self._accent.green(), self._accent.blue(), 0))
        p.setPen(QtCore.Qt.PenStyle.NoPen)
        p.setBrush(glow)
        p.drawEllipse(r.adjusted(10, 10, -10, -10))

        # логотип
        if self._pix is not None and not self._pix.isNull():
            pm = self._pix.scaled(96, 96, QtCore.Qt.AspectRatioMode.KeepAspectRatio, QtCore.Qt.TransformationMode.SmoothTransformation)
            x = cx - pm.width() // 2
            y = cy - pm.height() // 2
            p.drawPixmap(x, y, pm)
        else:
            p.setPen(QtGui.QColor(234, 240, 255, 160))
            p.drawText(r, QtCore.Qt.AlignmentFlag.AlignCenter, "LOGO")


class Launcher(QtWidgets.QWidget):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("Scott Launcher")
        # Увеличенный размер: 1200x750
        self.setFixedSize(1200, 750)

        self.cfg = load_config(BACKEND_DIR / "config.json")
        self.process: subprocess.Popen | None = None
        self._daemon_pid_file = BACKEND_DIR / "data" / "daemon.pid"
        self._daemon_auto_started = False  # Флаг для автозапуска
        self._is_running = False  # Состояние Скотта
        # Локальный контроллер ОС для быстрых действий прямо из лаунчера
        self.sys_controller = SystemController()
        # Кэш найденных приложений (для вкладки "Приложения")
        self._apps_cache: list[AppMatch] = []

        # Создаём системный трей
        self._setup_tray()

        self._build_ui()
        self._keep_only_core_tabs()
        self._apply_style()
        self._start_bg_animation()
        self._sync_runtime_state()
        # Автозапуск отключён - пользователь включает вручную

        # Сигналы темы
        self.btn_accent.clicked.connect(self._pick_accent_color)
        self.btn_text_color.clicked.connect(self._pick_text_color)
        self.btn_theme_apply.clicked.connect(self._apply_theme_from_controls)
        self.cmb_font.currentIndexChanged.connect(self._apply_theme_from_controls)
        self.spin_font.valueChanged.connect(self._apply_theme_from_controls)
        self.sld_left_op.valueChanged.connect(self._apply_theme_from_controls)
        self.sld_right_op.valueChanged.connect(self._apply_theme_from_controls)

        # Сигналы менеджера приложений (если вкладка присутствует)
        if hasattr(self, "txt_app_search"):
            self.txt_app_search.textChanged.connect(self._filter_apps)
            self.btn_scan_apps.clicked.connect(self._scan_apps)
            self.btn_app_launch.clicked.connect(self._launch_selected_app)
            self.btn_app_to_fav.clicked.connect(self._add_selected_to_fav)
            self.btn_app_from_fav.clicked.connect(self._remove_selected_from_fav)
            self.lst_apps.itemDoubleClicked.connect(lambda _: self._launch_selected_app())

    def _setup_tray(self) -> None:
        """Настройка системного трея."""
        if not QtWidgets.QSystemTrayIcon.isSystemTrayAvailable():
            return

        self.tray_icon = QtWidgets.QSystemTrayIcon(self)
        self.tray_icon.setIcon(self.style().standardIcon(QtWidgets.QStyle.StandardPixmap.SP_ComputerIcon))

        # Меню трея
        tray_menu = QtWidgets.QMenu()
        
        show_action = tray_menu.addAction("Показать лаунчер")
        show_action.triggered.connect(self.show)
        
        tray_menu.addSeparator()

        voice_action = tray_menu.addAction("Включить голосовой режим")
        voice_action.triggered.connect(lambda: self.start("voice_assistant_daemon.py"))
        self.voice_tray_action = voice_action

        text_action = tray_menu.addAction("Открыть текстовый режим")
        text_action.triggered.connect(lambda: self.start("text_chat_gui.py"))
        self.text_tray_action = text_action

        stop_action = tray_menu.addAction("Остановить ассистента")
        stop_action.triggered.connect(self.stop)
        self.stop_tray_action = stop_action

        tray_menu.addSeparator()
        status_action = tray_menu.addAction("Статус: проверка...")
        status_action.setEnabled(False)
        self.status_tray_action = status_action
        
        tray_menu.addSeparator()
        
        quit_action = tray_menu.addAction("Выход")
        quit_action.triggered.connect(QtWidgets.QApplication.quit)
        
        self.tray_icon.setContextMenu(tray_menu)
        self.tray_icon.activated.connect(self._tray_activated)
        self.tray_icon.show()

    def _tray_activated(self, reason: QtWidgets.QSystemTrayIcon.ActivationReason) -> None:
        """Обработка клика по иконке трея."""
        if reason == QtWidgets.QSystemTrayIcon.ActivationReason.DoubleClick:
            self.show()
            self.raise_()
            self.activateWindow()

    def closeEvent(self, event: QtGui.QCloseEvent) -> None:  # noqa: N802
        """При закрытии окна - сворачиваем в трей."""
        if QtWidgets.QSystemTrayIcon.isSystemTrayAvailable():
            event.ignore()
            self.hide()
            self.tray_icon.showMessage(
                "Scott",
                "Лаунчер свёрнут в трей. Ассистент продолжает работать в фоне.",
                QtWidgets.QSystemTrayIcon.MessageIcon.Information,
                2000
            )
        else:
            event.accept()

    def _refresh_mics(self) -> None:
        self.cmb_mic.clear()
        self.cmb_mic.addItem("Автовыбор (по умолчанию)", -1)
        try:
            import sounddevice as sd  # type: ignore

            devices = sd.query_devices()
            for i, d in enumerate(devices):
                if d.get("max_input_channels", 0) > 0:
                    name = d.get("name", "Unknown")
                    self.cmb_mic.addItem(f"id={i} • {name}", i)
        except Exception:
            self.cmb_mic.addItem("Не удалось получить список (sounddevice)", -1)

        cur = int(getattr(self.cfg, "input_device_id", -1))
        idx = self.cmb_mic.findData(cur)
        if idx >= 0:
            self.cmb_mic.setCurrentIndex(idx)

    def _build_ui(self) -> None:
        root = QtWidgets.QVBoxLayout(self)
        root.setContentsMargins(30, 30, 30, 30)
        root.setSpacing(20)

        # Верхняя панель: логотип, статус, заголовок
        top_panel = QtWidgets.QHBoxLayout()
        top_panel.setSpacing(20)

        # Логотип
        self.logo = LogoGlow()
        self._load_logo()
        top_panel.addWidget(self.logo, alignment=QtCore.Qt.AlignmentFlag.AlignLeft)

        # Заголовок и статус
        header_layout = QtWidgets.QVBoxLayout()
        header_layout.setSpacing(8)

        title = QtWidgets.QLabel("MALTRUAND")
        title.setObjectName("title")
        subtitle = QtWidgets.QLabel("Лаунчер • Режимы • Настройки • Управление ОС")
        subtitle.setObjectName("subtitle")
        
        # Status badge (Online/Running)
        self.badge = QtWidgets.QLabel("● READY")
        self.badge.setObjectName("badge")

        header_layout.addWidget(title)
        header_layout.addWidget(subtitle)
        header_layout.addWidget(self.badge, alignment=QtCore.Qt.AlignmentFlag.AlignLeft)

        top_panel.addLayout(header_layout)
        top_panel.addStretch(1)

        root.addLayout(top_panel)

        # Основная панель: левая (управление) и правая (настройки)
        main_panel = QtWidgets.QHBoxLayout()
        main_panel.setSpacing(20)

        # Левая панель: большая кнопка управления + режимы
        left = QtWidgets.QFrame()
        left.setObjectName("leftPanel")
        left_l = QtWidgets.QVBoxLayout(left)
        left_l.setContentsMargins(24, 24, 24, 24)
        left_l.setSpacing(14)

        # Основная кнопка голосового режима
        self.btn_main_toggle = GlassButton("ВКЛЮЧИТЬ ГОЛОСОВОЙ РЕЖИМ", min_height=92)
        self.btn_main_toggle.setObjectName("mainToggleButton")
        self.btn_main_toggle.setFont(QtGui.QFont("Segoe UI", 18, QtGui.QFont.Weight.Bold))
        self.btn_main_toggle.clicked.connect(self._toggle_daemon)
        left_l.addWidget(self.btn_main_toggle)

        # Отдельная кнопка выключения (по просьбе пользователя)
        self.btn_power_off = GlassButton("⏻ ВЫКЛЮЧИТЬ", min_height=46)
        self.btn_power_off.setObjectName("powerOffButton")
        self.btn_power_off.clicked.connect(self.stop)
        left_l.addWidget(self.btn_power_off)

        # Статус
        self.status = QtWidgets.QLabel("Готово к запуску.")
        self.status.setObjectName("status")
        self.status.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
        left_l.addWidget(self.status)

        # Режимы работы
        modes_label = QtWidgets.QLabel("Режимы работы:")
        modes_label.setObjectName("sectionHeader")
        left_l.addWidget(modes_label)

        modes_box = QtWidgets.QFrame()
        modes_box.setObjectName("modesBox")
        btn_row = QtWidgets.QVBoxLayout(modes_box)
        btn_row.setContentsMargins(10, 10, 10, 10)
        btn_row.setSpacing(8)

        self.btn_text = GlassButton("ТЕКСТОВЫЙ РЕЖИМ", min_height=54)

        self.btn_text.clicked.connect(lambda: self.start("text_mode_qt.py"))

        btn_row.addWidget(self.btn_text)

        left_l.addWidget(modes_box)
        left_l.addStretch(1)
        main_panel.addWidget(left, 1)

        # Правая панель: настройки + управление ОС
        right = QtWidgets.QFrame()
        right.setObjectName("rightPanel")
        right_l = QtWidgets.QVBoxLayout(right)
        right_l.setContentsMargins(24, 24, 24, 24)
        right_l.setSpacing(16)

        # Вкладки для настройки и управления ОС
        tabs = QtWidgets.QTabWidget()
        tabs.setObjectName("tabs")

        # Вкладка 1: Настройки
        settings_tab = QtWidgets.QWidget()
        settings_layout = QtWidgets.QVBoxLayout(settings_tab)
        settings_layout.setContentsMargins(12, 12, 12, 12)
        settings_layout.setSpacing(12)

        form = QtWidgets.QFormLayout()
        form.setLabelAlignment(QtCore.Qt.AlignmentFlag.AlignLeft)
        form.setFormAlignment(QtCore.Qt.AlignmentFlag.AlignTop)
        form.setHorizontalSpacing(12)
        form.setVerticalSpacing(12)

        voices = sorted(list_available_voices().keys())
        self.cmb_voice = QtWidgets.QComboBox()
        self.cmb_voice.addItems(voices)
        self.cmb_voice.setCurrentText(self.cfg.voice_preset)
        self.txt_user_name = QtWidgets.QLineEdit(getattr(self.cfg, "user_name", ""))
        self.txt_user_name.setPlaceholderText("Например: Алексей")
        self.cmb_user_title = QtWidgets.QComboBox()
        self.cmb_user_title.addItems(["сэр", "мадам", "друг"])
        self.cmb_user_title.setCurrentText(getattr(self.cfg, "user_title", "сэр"))
        self.cmb_voice_gender = QtWidgets.QComboBox()
        self.cmb_voice_gender.addItems(["male", "female"])
        self.cmb_voice_gender.setCurrentText(getattr(self.cfg, "preferred_voice_gender", "male"))

        self.cmb_provider = QtWidgets.QComboBox()
        self.cmb_provider.addItems(["ollama", "dummy", "openai"])
        self.cmb_provider.setCurrentText(self.cfg.llm_provider)

        self.txt_model = QtWidgets.QLineEdit(self.cfg.llm_model)

        self.spin_max_tokens = QtWidgets.QSpinBox()
        self.spin_max_tokens.setRange(64, 1024)
        self.spin_max_tokens.setValue(int(getattr(self.cfg, "llm_max_tokens", 160)))

        self.spin_temp = QtWidgets.QDoubleSpinBox()
        self.spin_temp.setRange(0.0, 1.5)
        self.spin_temp.setSingleStep(0.1)
        self.spin_temp.setValue(float(getattr(self.cfg, "llm_temperature", 0.4)))

        self.cmb_asr = QtWidgets.QComboBox()
        self.cmb_asr.addItems(["tiny", "base", "small", "medium", "large"])
        self.cmb_asr.setCurrentText(self.cfg.asr_model_size)

        self.cmb_lang = QtWidgets.QComboBox()
        self.cmb_lang.addItems(["ru", "en"])
        self.cmb_lang.setCurrentText(self.cfg.asr_language or "ru")

        self.cmb_device = QtWidgets.QComboBox()
        self.cmb_device.addItems(["cpu", "cuda"])
        self.cmb_device.setCurrentText(self.cfg.asr_device)

        form.addRow("Голос:", self.cmb_voice)
        form.addRow("Как вас называть:", self.txt_user_name)
        form.addRow("Обращение:", self.cmb_user_title)
        form.addRow("Пол голоса:", self.cmb_voice_gender)
        form.addRow("LLM provider:", self.cmb_provider)
        form.addRow("LLM model:", self.txt_model)
        form.addRow("LLM max_tokens:", self.spin_max_tokens)
        form.addRow("LLM temperature:", self.spin_temp)
        form.addRow("Whisper model:", self.cmb_asr)
        form.addRow("Язык ASR:", self.cmb_lang)
        form.addRow("ASR device:", self.cmb_device)

        settings_layout.addLayout(form)

        # Оформление (шрифт/цвета)
        theme_group = QtWidgets.QGroupBox("🎨 Оформление")
        theme_form = QtWidgets.QFormLayout(theme_group)
        theme_form.setHorizontalSpacing(12)
        theme_form.setVerticalSpacing(10)

        self.cmb_font = QtWidgets.QComboBox()
        self.cmb_font.addItems(["Segoe UI", "Arial", "Calibri", "Consolas", "Tahoma", "Verdana"])
        self.cmb_font.setCurrentText(getattr(self.cfg, "ui_font_family", "Segoe UI"))

        self.spin_font = QtWidgets.QSpinBox()
        self.spin_font.setRange(11, 20)
        self.spin_font.setValue(int(getattr(self.cfg, "ui_font_size", 14)))

        self.btn_accent = GlassButton("Выбрать цвет")
        self.lbl_accent = QtWidgets.QLabel(getattr(self.cfg, "ui_accent_color", "#72A0FF"))
        self.lbl_accent.setObjectName("hint")
        accent_row = QtWidgets.QHBoxLayout()
        accent_row.addWidget(self.btn_accent)
        accent_row.addWidget(self.lbl_accent)
        accent_row.addStretch(1)

        self.btn_text_color = GlassButton("Выбрать цвет")
        self.lbl_text_color = QtWidgets.QLabel(getattr(self.cfg, "ui_text_color", "#EAF0FF"))
        self.lbl_text_color.setObjectName("hint")
        text_color_row = QtWidgets.QHBoxLayout()
        text_color_row.addWidget(self.btn_text_color)
        text_color_row.addWidget(self.lbl_text_color)
        text_color_row.addStretch(1)

        self.sld_left_op = QtWidgets.QSlider(QtCore.Qt.Orientation.Horizontal)
        self.sld_left_op.setRange(40, 95)
        self.sld_left_op.setValue(int(getattr(self.cfg, "ui_panel_opacity_left", 75)))
        self.sld_right_op = QtWidgets.QSlider(QtCore.Qt.Orientation.Horizontal)
        self.sld_right_op.setRange(40, 95)
        self.sld_right_op.setValue(int(getattr(self.cfg, "ui_panel_opacity_right", 80)))

        theme_form.addRow("Шрифт:", self.cmb_font)
        theme_form.addRow("Размер:", self.spin_font)
        theme_form.addRow("Акцент:", accent_row)
        theme_form.addRow("Цвет текста:", text_color_row)
        theme_form.addRow("Прозрачность (левая):", self.sld_left_op)
        theme_form.addRow("Прозрачность (правая):", self.sld_right_op)

        self.btn_theme_apply = GlassButton("✨ Применить оформление")
        theme_apply_row = QtWidgets.QHBoxLayout()
        theme_apply_row.addWidget(self.btn_theme_apply)
        theme_apply_row.addStretch(1)
        theme_form.addRow("", theme_apply_row)

        settings_layout.addWidget(theme_group)

        mic_group = QtWidgets.QGroupBox("🎙 Микрофон")
        mic_form = QtWidgets.QFormLayout(mic_group)
        mic_form.setHorizontalSpacing(12)
        mic_form.setVerticalSpacing(10)
        self.cmb_mic = QtWidgets.QComboBox()
        self.btn_mic_refresh = GlassButton("Обновить")
        mic_row = QtWidgets.QHBoxLayout()
        mic_row.addWidget(self.cmb_mic, 1)
        mic_row.addWidget(self.btn_mic_refresh)
        mic_form.addRow("Устройство ввода:", mic_row)
        settings_layout.addWidget(mic_group)

        self.btn_save = GlassButton("💾 Сохранить настройки")
        self.btn_save.clicked.connect(self.save)
        settings_layout.addWidget(self.btn_save)

        settings_layout.addStretch(1)
        tabs.addTab(settings_tab, "⚙️ Настройки")

        # Профиль
        profile_tab = QtWidgets.QWidget()
        profile_l = QtWidgets.QVBoxLayout(profile_tab)
        profile_l.setContentsMargins(12, 12, 12, 12)
        profile_l.setSpacing(12)
        prof_hint = QtWidgets.QLabel("Профиль влияет на обращения и советы ассистента.")
        prof_hint.setObjectName("hint")
        prof_hint.setWordWrap(True)
        profile_l.addWidget(prof_hint)

        prof_form = QtWidgets.QFormLayout()
        prof_form.setHorizontalSpacing(12)
        prof_form.setVerticalSpacing(10)
        prof_form.addRow("Как вас называть:", self.txt_user_name)
        prof_form.addRow("Обращение:", self.cmb_user_title)
        prof_form.addRow("Пол голоса:", self.cmb_voice_gender)
        profile_l.addLayout(prof_form)
        profile_l.addStretch(1)
        tabs.addTab(profile_tab, "👤 Профиль")

        # Быстрые команды
        quick_tab = QtWidgets.QWidget()
        quick_l = QtWidgets.QVBoxLayout(quick_tab)
        quick_l.setContentsMargins(12, 12, 12, 12)
        quick_l.setSpacing(12)
        quick_hint = QtWidgets.QLabel("Быстрые команды выполняются сразу.")
        quick_hint.setObjectName("hint")
        quick_hint.setWordWrap(True)
        quick_l.addWidget(quick_hint)

        grid = QtWidgets.QGridLayout()
        grid.setHorizontalSpacing(10)
        grid.setVerticalSpacing(8)
        quick_l.addLayout(grid)

        def add_btn(r: int, c: int, label: str, cmd: str) -> None:
            b = GlassButton(label, min_height=44)
            b.clicked.connect(lambda: self._run_quick_command(cmd))
            grid.addWidget(b, r, c)

        add_btn(0, 0, "Chrome", "открой chrome")
        add_btn(0, 1, "YouTube", "открой сайт youtube")
        add_btn(0, 2, "Курс $", "какой сейчас курс доллара")
        add_btn(1, 0, "Громче", "сделай громче")
        add_btn(1, 1, "Тише", "сделай тише")
        add_btn(1, 2, "Mute", "выключи звук")
        add_btn(2, 0, "Пауза", "пауза")
        add_btn(2, 1, "Следующий", "следующий трек")
        add_btn(2, 2, "Предыдущий", "предыдущий трек")
        add_btn(3, 0, "Рабочий стол", "покажи рабочий стол")
        add_btn(3, 1, "Lock", "заблокируй экран")
        add_btn(3, 2, "Совет", "дай совет")
        quick_l.addStretch(1)
        tabs.addTab(quick_tab, "⚡ Быстрые")

        # Вкладка 2: Управление ОС
        os_tab = QtWidgets.QWidget()
        os_layout = QtWidgets.QVBoxLayout(os_tab)
        os_layout.setContentsMargins(12, 12, 12, 12)
        os_layout.setSpacing(12)

        os_info = QtWidgets.QLabel(
            "Скотт может управлять вашей системой:\n\n"
            "• Открывать программы и папки\n"
            "• Управлять громкостью (громче/тише/выключить)\n"
            "• Управлять окнами (свернуть/развернуть/закрепить)\n"
            "• Управлять медиа (пауза/следующий/предыдущий)\n"
            "• Создавать папки и документы\n"
            "• Искать и читать файлы\n"
            "• Открывать сайты\n\n"
            "Просто скажите команду голосом или в текстовом режиме — "
            "или используйте быстрые кнопки ниже."
        )
        os_info.setObjectName("hint")
        os_info.setWordWrap(True)
        os_layout.addWidget(os_info)

        # Группа быстрых действий
        quick_group = QtWidgets.QGroupBox("Быстрые команды")
        quick_layout = QtWidgets.QGridLayout(quick_group)
        quick_layout.setHorizontalSpacing(10)
        quick_layout.setVerticalSpacing(8)

        # Первый ряд: запуск приложений / папок
        btn_chrome = GlassButton("🌐 Открыть Chrome")
        btn_chrome.clicked.connect(lambda: self._run_quick_command("открой google chrome"))
        btn_explorer = GlassButton("🗂 Открыть рабочий стол")
        btn_explorer.clicked.connect(lambda: self._run_quick_command("открой рабочий стол"))
        btn_downloads = GlassButton("⬇ Открыть загрузки")
        btn_downloads.clicked.connect(lambda: self._run_quick_command("открой загрузки"))

        quick_layout.addWidget(btn_chrome, 0, 0)
        quick_layout.addWidget(btn_explorer, 0, 1)
        quick_layout.addWidget(btn_downloads, 0, 2)

        # Второй ряд: звук
        btn_vol_up = GlassButton("🔊 Громче")
        btn_vol_up.clicked.connect(lambda: self._run_quick_command("сделай громче"))
        btn_vol_down = GlassButton("🔉 Тише")
        btn_vol_down.clicked.connect(lambda: self._run_quick_command("сделай тише"))
        btn_mute = GlassButton("🔇 Выключить звук")
        btn_mute.clicked.connect(lambda: self._run_quick_command("выключи звук"))

        quick_layout.addWidget(btn_vol_up, 1, 0)
        quick_layout.addWidget(btn_vol_down, 1, 1)
        quick_layout.addWidget(btn_mute, 1, 2)

        # Третий ряд: медиа
        btn_play_pause = GlassButton("⏯ Пауза/Плей")
        btn_play_pause.clicked.connect(lambda: self._run_quick_command("пауза"))
        btn_next = GlassButton("⏭ Следующий трек")
        btn_next.clicked.connect(lambda: self._run_quick_command("следующий трек"))
        btn_prev = GlassButton("⏮ Предыдущий трек")
        btn_prev.clicked.connect(lambda: self._run_quick_command("предыдущий трек"))

        quick_layout.addWidget(btn_play_pause, 2, 0)
        quick_layout.addWidget(btn_next, 2, 1)
        quick_layout.addWidget(btn_prev, 2, 2)

        # Четвёртый ряд: система
        btn_desktop = GlassButton("🖥 Показать рабочий стол")
        btn_desktop.clicked.connect(lambda: self._run_quick_command("покажи рабочий стол"))
        btn_lock = GlassButton("🔒 Заблокировать экран")
        btn_lock.clicked.connect(lambda: self._run_quick_command("заблокируй экран"))
        btn_restart = GlassButton("🔄 Перезагрузка")
        btn_restart.clicked.connect(lambda: self._run_quick_command("перезагрузи компьютер"))
        btn_shutdown = GlassButton("⏻ Выключение")
        btn_shutdown.clicked.connect(lambda: self._run_quick_command("выключи компьютер"))

        quick_layout.addWidget(btn_desktop, 3, 0)
        quick_layout.addWidget(btn_lock, 3, 1)
        quick_layout.addWidget(btn_restart, 3, 2)
        quick_layout.addWidget(btn_shutdown, 3, 3)

        os_layout.addWidget(quick_group)

        os_layout.addStretch(1)
        tabs.addTab(os_tab, "🖥️ Управление ОС")

        # Вкладка 3: Приложения
        apps_tab = QtWidgets.QWidget()
        apps_layout = QtWidgets.QVBoxLayout(apps_tab)
        apps_layout.setContentsMargins(12, 12, 12, 12)
        apps_layout.setSpacing(10)

        apps_info = QtWidgets.QLabel(
            "📦 Менеджер приложений\n\n"
            "Здесь можно просмотреть список установленных программ (по данным системы), "
            "запускать их в один клик и добавлять в избранное."
        )
        apps_info.setObjectName("hint")
        apps_info.setWordWrap(True)
        apps_layout.addWidget(apps_info)

        # Поиск
        search_row = QtWidgets.QHBoxLayout()
        self.txt_app_search = QtWidgets.QLineEdit()
        self.txt_app_search.setPlaceholderText("Поиск по имени приложения...")
        search_row.addWidget(self.txt_app_search)
        self.btn_scan_apps = GlassButton("🔄 Обновить список")
        search_row.addWidget(self.btn_scan_apps)
        apps_layout.addLayout(search_row)

        # Списки: найденные и избранные
        lists_row = QtWidgets.QHBoxLayout()

        left_col = QtWidgets.QVBoxLayout()
        lbl_all = QtWidgets.QLabel("Найденные приложения:")
        lbl_all.setObjectName("sectionHeader")
        self.lst_apps = QtWidgets.QListWidget()
        self.lst_apps.setSelectionMode(QtWidgets.QAbstractItemView.SelectionMode.SingleSelection)
        left_col.addWidget(lbl_all)
        left_col.addWidget(self.lst_apps)

        right_col = QtWidgets.QVBoxLayout()
        lbl_fav = QtWidgets.QLabel("Избранное:")
        lbl_fav.setObjectName("sectionHeader")
        self.lst_fav = QtWidgets.QListWidget()
        self.lst_fav.setSelectionMode(QtWidgets.QAbstractItemView.SelectionMode.SingleSelection)
        right_col.addWidget(lbl_fav)
        right_col.addWidget(self.lst_fav)

        lists_row.addLayout(left_col, 3)
        lists_row.addLayout(right_col, 2)
        apps_layout.addLayout(lists_row)

        # Кнопки действий
        btn_row = QtWidgets.QHBoxLayout()
        self.btn_app_launch = GlassButton("▶ Запустить выбранное")
        self.btn_app_to_fav = GlassButton("⭐ В избранное")
        self.btn_app_from_fav = GlassButton("❌ Удалить из избранного")
        btn_row.addWidget(self.btn_app_launch)
        btn_row.addWidget(self.btn_app_to_fav)
        btn_row.addWidget(self.btn_app_from_fav)
        btn_row.addStretch(1)
        apps_layout.addLayout(btn_row)

        apps_layout.addStretch(1)
        tabs.addTab(apps_tab, "📦 Приложения")

        # Вкладка 3: Озвучка видео
        dubbing_tab = QtWidgets.QWidget()
        dubbing_layout = QtWidgets.QVBoxLayout(dubbing_tab)
        dubbing_layout.setContentsMargins(12, 12, 12, 12)
        dubbing_layout.setSpacing(12)

        dubbing_info = QtWidgets.QLabel(
            "🎬 Озвучка видео/мультфильмов/фильмов\n\n"
            "1. Выберите видео файл\n"
            "2. Назначьте голоса персонажам (для диалогов)\n"
            "3. Либо просто введите текст рассказчика — он озвучит всё видео одним голосом\n"
            "4. Сгенерируйте новую озвучку\n\n"
            "Голоса персонажей и рассказчика можно сохранять и переиспользовать."
        )
        dubbing_info.setObjectName("hint")
        dubbing_info.setWordWrap(True)
        dubbing_layout.addWidget(dubbing_info)

        # Выбор видео файла
        video_group = QtWidgets.QGroupBox("Видео файл")
        video_layout = QtWidgets.QVBoxLayout(video_group)
        
        video_path_layout = QtWidgets.QHBoxLayout()
        self.txt_video_path = QtWidgets.QLineEdit()
        self.txt_video_path.setPlaceholderText("Путь к видео файлу...")
        btn_browse_video = GlassButton("📁 Выбрать")
        btn_browse_video.clicked.connect(self._browse_video_file)
        video_path_layout.addWidget(self.txt_video_path)
        video_path_layout.addWidget(btn_browse_video)
        video_layout.addLayout(video_path_layout)
        
        dubbing_layout.addWidget(video_group)

        # Управление персонажами
        chars_group = QtWidgets.QGroupBox("Голоса персонажей")
        chars_layout = QtWidgets.QVBoxLayout(chars_group)
        
        # Список персонажей
        self.characters_list = QtWidgets.QListWidget()
        self.characters_list.setMaximumHeight(150)
        chars_layout.addWidget(self.characters_list)
        
        # Кнопки управления персонажами
        chars_btn_layout = QtWidgets.QHBoxLayout()
        btn_add_char = GlassButton("➕ Добавить")
        btn_add_char.clicked.connect(self._add_character)
        btn_remove_char = GlassButton("➖ Удалить")
        btn_remove_char.clicked.connect(self._remove_character)
        chars_btn_layout.addWidget(btn_add_char)
        chars_btn_layout.addWidget(btn_remove_char)
        chars_layout.addLayout(chars_btn_layout)
        
        dubbing_layout.addWidget(chars_group)

        # Текст рассказчика
        narrator_group = QtWidgets.QGroupBox("Рассказчик (простая озвучка видео)")
        narrator_layout = QtWidgets.QVBoxLayout(narrator_group)

        narrator_hint = QtWidgets.QLabel(
            "Если вы не хотите размечать диалоги по персонажам, "
            "можно просто ввести здесь текст, которым озвучить происходящее на видео."
        )
        narrator_hint.setObjectName("hint")
        narrator_hint.setWordWrap(True)
        narrator_layout.addWidget(narrator_hint)

        self.txt_narration = QtWidgets.QPlainTextEdit()
        self.txt_narration.setPlaceholderText(
            "Например: «Робот входит в комнату, поворачивается к камере и говорит свою речь...»"
        )
        self.txt_narration.setMaximumHeight(120)
        narrator_layout.addWidget(self.txt_narration)

        narrator_voice_layout = QtWidgets.QHBoxLayout()
        narrator_voice_label = QtWidgets.QLabel("Голос рассказчика:")
        self.cmb_narrator_voice = QtWidgets.QComboBox()
        narrator_voices = sorted(list_available_voices().keys())
        self.cmb_narrator_voice.addItems(narrator_voices)
        narrator_voice_layout.addWidget(narrator_voice_label)
        narrator_voice_layout.addWidget(self.cmb_narrator_voice)
        narrator_layout.addLayout(narrator_voice_layout)

        dubbing_layout.addWidget(narrator_group)

        # Кнопка генерации озвучки
        btn_generate = GlassButton("🎬 Сгенерировать озвучку")
        btn_generate.clicked.connect(self._generate_dubbing)
        dubbing_layout.addWidget(btn_generate)

        dubbing_layout.addStretch(1)
        tabs.addTab(dubbing_tab, "🎬 Озвучка видео")

        right_l.addWidget(tabs)

        hint = QtWidgets.QLabel(
            "💡 Совет: Закройте окно — лаунчер свернётся в трей.\n"
            "Скотт продолжит работать в фоне."
        )
        hint.setObjectName("hint")
        right_l.addWidget(hint)

        main_panel.addWidget(right, 1)
        root.addLayout(main_panel)

        # Микрофон: загрузка + кнопка обновления
        self.btn_mic_refresh.clicked.connect(self._refresh_mics)
        self._refresh_mics()

    def _keep_only_core_tabs(self) -> None:
        """Оставляет вкладки: Настройки/Профиль/Быстрые."""
        tabs = self.findChild(QtWidgets.QTabWidget, "tabs")
        if tabs is None:
            return
        allowed = {"⚙️ Настройки", "👤 Профиль", "⚡ Быстрые"}
        i = 0
        while i < tabs.count():
            if tabs.tabText(i) not in allowed:
                tabs.removeTab(i)
                continue
            i += 1

    def _apply_style(self) -> None:
        # Брутальный тёмно-технологичный стиль
        font_family = getattr(self.cfg, "ui_font_family", "Segoe UI") or "Segoe UI"
        font_size = int(getattr(self.cfg, "ui_font_size", 14) or 14)
        left_op = int(getattr(self.cfg, "ui_panel_opacity_left", 75) or 75)
        right_op = int(getattr(self.cfg, "ui_panel_opacity_right", 80) or 80)
        r, g, b = self._accent_rgb()
        tr, tg, tb = self._text_rgb()
        style = f"""
            QWidget {{
              color: rgb({tr},{tg},{tb});
              font-family: {font_family};
              font-size: {font_size}px;
              background: transparent;
            }}
            #leftPanel {{
              border-radius: 14px;
              background: rgba(12, 20, 16, {left_op/100:.2f});
              border: 1px solid rgba({r},{g},{b},0.35);
            }}
            #rightPanel {{
              border-radius: 14px;
              background: rgba(10, 16, 14, {right_op/100:.2f});
              border: 1px solid rgba({r},{g},{b},0.28);
            }}
            #modesBox {{
              border-radius: 10px;
              background: rgba(0,0,0,0.28);
              border: 1px solid rgba({r},{g},{b},0.20);
            }}
            #title {{ font-size: 40px; font-weight: 900; letter-spacing: 4px; }}
            #subtitle {{ color: rgba({tr},{tg},{tb},0.66); font-size: 12px; }}
            #sectionHeader {{ font-size: 16px; font-weight: 700; }}
            #status {{ color: rgba({tr},{tg},{tb},0.80); font-size: 15px; }}
            #hint {{ color: rgba({tr},{tg},{tb},0.55); font-size: 12px; }}
            #badge {{
              padding: 6px 12px;
              border-radius: 999px;
              background: rgba({r},{g},{b},0.12);
              border: 1px solid rgba({r},{g},{b},0.35);
              color: rgba({tr},{tg},{tb},0.90);
              font-weight: 700;
              letter-spacing: 1px;
            }}

            QComboBox, QLineEdit {{
              background: rgba(0,0,0,0.35);
              border: 1px solid rgba({r},{g},{b},0.25);
              border-radius: 8px;
              padding: 8px 10px;
            }}
            QComboBox::drop-down {{ border: none; }}

            QPushButton {{
              background: qlineargradient(x1:0,y1:0,x2:1,y2:1, stop:0 rgba(46,56,50,0.95), stop:1 rgba(26,34,30,0.95));
              border: 1px solid rgba({r},{g},{b},0.45);
              border-radius: 10px;
              padding: 10px 16px;
              font-weight: 700;
              letter-spacing: 0.4px;
            }}
            QPushButton:hover {{
              background: qlineargradient(x1:0,y1:0,x2:1,y2:1, stop:0 rgba(62,76,66,0.98), stop:1 rgba(34,44,38,0.98));
              border: 1px solid rgba({r},{g},{b},0.70);
            }}
            QPushButton:pressed {{
              background: rgba({r},{g},{b},0.18);
            }}
            #powerOffButton {{
              background: qlineargradient(x1:0,y1:0,x2:1,y2:1, stop:0 rgba(60,20,20,0.85), stop:1 rgba(28,10,10,0.92));
              border: 1px solid rgba(255,80,80,0.55);
              border-radius: 10px;
              font-weight: 800;
              letter-spacing: 1px;
            }}
            #powerOffButton:hover {{
              border: 1px solid rgba(255,120,120,0.85);
              background: qlineargradient(x1:0,y1:0,x2:1,y2:1, stop:0 rgba(80,28,28,0.92), stop:1 rgba(38,14,14,0.96));
            }}
            #mainToggleButton {{
              background: qlineargradient(x1:0,y1:0,x2:1,y2:1, stop:0 rgba({r},{g},{b},0.32), stop:1 rgba(30,40,34,0.95));
              border: 2px solid rgba({r},{g},{b},0.85);
              border-radius: 12px;
              padding: 22px;
              font-weight: 900;
              letter-spacing: 1px;
            }}
            #mainToggleButton:hover {{
              background: qlineargradient(x1:0,y1:0,x2:1,y2:1, stop:0 rgba({r},{g},{b},0.45), stop:1 rgba(22,30,50,0.98));
              border: 2px solid rgba({r},{g},{b},1.00);
            }}
            #mainToggleButton:pressed {{
              background: rgba({r},{g},{b},0.22);
            }}

            QTabWidget::pane {{
              border: 1px solid rgba(255,255,255,0.08);
              border-radius: 12px;
              background: rgba(10, 14, 28, 0.60);
            }}
            QTabBar::tab {{
              background: rgba(20, 24, 40, 0.50);
              color: rgba(234,240,255,0.70);
              padding: 10px 20px;
              border-top-left-radius: 8px;
              border-top-right-radius: 8px;
              margin-right: 2px;
            }}
            QTabBar::tab:selected {{
              background: rgba({r},{g},{b},0.15);
              color: rgba(234,240,255,0.95);
            }}
            QGroupBox {{
              border: 1px solid rgba(255,255,255,0.10);
              border-radius: 12px;
              margin-top: 12px;
              padding-top: 12px;
              font-weight: 600;
            }}
            QGroupBox::title {{
              subcontrol-origin: margin;
              left: 10px;
              padding: 0 5px;
            }}
            QListWidget {{
              background: rgba(255,255,255,0.04);
              border: 1px solid rgba(255,255,255,0.10);
              border-radius: 10px;
              padding: 4px;
            }}
            QListWidget::item {{
              padding: 6px;
              border-radius: 6px;
              margin: 2px;
            }}
            QListWidget::item:selected {{
              background: rgba({r},{g},{b},0.20);
            }}
            """
        self.setStyleSheet(style)
        # Прокидываем акцент в логотип
        self.logo.setAccent(QtGui.QColor(r, g, b))

    def _accent_rgb(self) -> tuple[int, int, int]:
        """Возвращает RGB акцентного цвета из конфига (hex '#RRGGBB')."""
        raw = (getattr(self.cfg, "ui_accent_color", "#72A0FF") or "#72A0FF").strip()
        c = QtGui.QColor(raw)
        if not c.isValid():
            c = QtGui.QColor("#72A0FF")
        return int(c.red()), int(c.green()), int(c.blue())

    def _text_rgb(self) -> tuple[int, int, int]:
        """Возвращает RGB текста из конфига (hex '#RRGGBB')."""
        raw = (getattr(self.cfg, "ui_text_color", "#EAF0FF") or "#EAF0FF").strip()
        c = QtGui.QColor(raw)
        if not c.isValid():
            c = QtGui.QColor("#EAF0FF")
        return int(c.red()), int(c.green()), int(c.blue())

    def _pick_accent_color(self) -> None:
        cur = QtGui.QColor(self.lbl_accent.text().strip() or "#72A0FF")
        c = QtWidgets.QColorDialog.getColor(cur, self, "Выбор акцентного цвета")
        if not c.isValid():
            return
        self.lbl_accent.setText(c.name().upper())
        self._apply_theme_from_controls()

    def _pick_text_color(self) -> None:
        cur = QtGui.QColor(self.lbl_text_color.text().strip() or "#EAF0FF")
        c = QtWidgets.QColorDialog.getColor(cur, self, "Выбор цвета текста")
        if not c.isValid():
            return
        self.lbl_text_color.setText(c.name().upper())
        self._apply_theme_from_controls()

    def _apply_theme_from_controls(self) -> None:
        """Применить оформление сразу (без сохранения на диск)."""
        self.cfg.ui_font_family = self.cmb_font.currentText()
        self.cfg.ui_font_size = int(self.spin_font.value())
        self.cfg.ui_accent_color = str(self.lbl_accent.text()).strip() or "#72A0FF"
        self.cfg.ui_text_color = str(self.lbl_text_color.text()).strip() or "#EAF0FF"
        self.cfg.ui_panel_opacity_left = int(self.sld_left_op.value())
        self.cfg.ui_panel_opacity_right = int(self.sld_right_op.value())
        self._apply_style()

    # --- Менеджер приложений ---

    def _scan_apps(self) -> None:
        """Сканирует установленные приложения и наполняет список."""
        self.status.setText("🔎 Поиск установленных приложений...")
        QtWidgets.QApplication.setOverrideCursor(QtCore.Qt.CursorShape.BusyCursor)
        try:
            apps = scan_installed_apps(limit=256)
            self._apps_cache = apps
            self._rebuild_apps_list()
            self.status.setText(f"Найдено приложений: {len(apps)}")
        except Exception as e:
            self.status.setText(f"⚠️ Не удалось получить список приложений: {e}")
        finally:
            QtWidgets.QApplication.restoreOverrideCursor()

    def _rebuild_apps_list(self) -> None:
        """Перестроить список приложений с учётом фильтра."""
        self.lst_apps.clear()
        if not self._apps_cache:
            return
        text = (self.txt_app_search.text() or "").strip().lower()
        for app in self._apps_cache:
            if text and text not in app.name.lower():
                continue
            item = QtWidgets.QListWidgetItem(app.name)
            item.setToolTip(app.command)
            item.setData(QtCore.Qt.ItemDataRole.UserRole, app)
            self.lst_apps.addItem(item)

    def _filter_apps(self, _text: str) -> None:
        self._rebuild_apps_list()

    def _current_app_from_list(self, lst: QtWidgets.QListWidget) -> AppMatch | None:
        item = lst.currentItem()
        if item is None:
            return None
        app = item.data(QtCore.Qt.ItemDataRole.UserRole)
        if isinstance(app, AppMatch):
            return app
        # если по какой-то причине там нет AppMatch, восстановим из текста
        name = item.text()
        cmd = item.toolTip() or name
        return AppMatch(name=name, command=cmd, source="UI")

    def _launch_selected_app(self) -> None:
        app = self._current_app_from_list(self.lst_apps)
        if app is None:
            self.status.setText("Выбери приложение для запуска.")
            return
        try:
            subprocess.Popen(app.command)
            self.status.setText(f"Открываю {app.name}...")
        except Exception as e:
            self.status.setText(f"⚠️ Не удалось запустить {app.name}: {e}")

    def _add_selected_to_fav(self) -> None:
        app = self._current_app_from_list(self.lst_apps)
        if app is None:
            self.status.setText("Сначала выбери приложение в левом списке.")
            return
        # проверяем, нет ли уже такого в избранном
        for i in range(self.lst_fav.count()):
            it = self.lst_fav.item(i)
            if it.text().lower() == app.name.lower():
                self.status.setText("Уже в избранном.")
                return
        fav_item = QtWidgets.QListWidgetItem(app.name)
        fav_item.setToolTip(app.command)
        fav_item.setData(QtCore.Qt.ItemDataRole.UserRole, app)
        self.lst_fav.addItem(fav_item)
        self.status.setText(f"Добавлено в избранное: {app.name}")

    def _remove_selected_from_fav(self) -> None:
        row = self.lst_fav.currentRow()
        if row < 0:
            self.status.setText("Сначала выбери приложение в избранном.")
            return
        name = self.lst_fav.item(row).text()
        self.lst_fav.takeItem(row)
        self.status.setText(f"Убрано из избранного: {name}")

    def _run_quick_command(self, text: str) -> None:
        """Выполнить быструю команду ОС через локальный SystemController."""
        try:
            result = self.sys_controller.handle_command(text)
            if result.handled:
                # Показать сообщение в статусе и в виде всплывающего уведомления
                msg = result.message or "Команда выполнена."
                self.status.setText(msg)
                if hasattr(self, "tray_icon") and self.tray_icon is not None:
                    self.tray_icon.showMessage(
                        "Scott • Быстрая команда",
                        msg,
                        QtWidgets.QSystemTrayIcon.MessageIcon.Information,
                        1500,
                    )
            else:
                self.status.setText("Команда не распознана.")
        except Exception as e:
            self.status.setText(f"⚠️ Ошибка при выполнении команды: {e}")

    def _load_logo(self) -> None:
        # Пользователь может положить assets/logo.png (или .jpg)
        for name in ("logo.png", "logo.jpg", "logo.jpeg", "logo.webp"):
            p = ASSETS_DIR / name
            if p.exists():
                pm = QtGui.QPixmap(str(p))
                if not pm.isNull():
                    self.logo.setPixmap(pm)
                    return
        # fallback: текст
        self.logo.setPixmap(None)

    def _start_bg_animation(self) -> None:
        # Лёгкая анимация "свечения" через градиент на фоне окна
        self._phase = 0.0
        self._timer = QtCore.QTimer(self)
        self._timer.timeout.connect(self._tick_bg)
        self._timer.start(33)  # ~30fps

    def _tick_bg(self) -> None:
        self._phase += 0.03
        a = 70 + int(30 * (1 + math.sin(self._phase)))
        b = 50 + int(35 * (1 + math.cos(self._phase * 0.8)))
        # рисуем фон через палитру окна
        grad = QtGui.QLinearGradient(0, 0, self.width(), self.height())
        grad.setColorAt(0.0, QtGui.QColor(18, 24, 48, 255))
        grad.setColorAt(0.5, QtGui.QColor(24, 18, 44, 255))
        grad.setColorAt(1.0, QtGui.QColor(18, 26, 46, 255))
        # "неоновая дымка"
        r, g, b = self._accent_rgb()
        glow = QtGui.QRadialGradient(self.width() * 0.25, self.height() * 0.22, self.width() * 0.8)
        glow.setColorAt(0.0, QtGui.QColor(r, g, b, a))
        glow.setColorAt(1.0, QtGui.QColor(r, g, b, 0))

        pm = QtGui.QPixmap(self.size())
        pm.fill(QtCore.Qt.GlobalColor.transparent)
        p = QtGui.QPainter(pm)
        p.fillRect(self.rect(), grad)
        p.setCompositionMode(QtGui.QPainter.CompositionMode.CompositionMode_Screen)
        p.fillRect(self.rect(), glow)
        p.end()

        pal = self.palette()
        pal.setBrush(QtGui.QPalette.ColorRole.Window, QtGui.QBrush(pm))
        self.setAutoFillBackground(True)
        self.setPalette(pal)

    def save(self) -> None:
        gender = self.cmb_voice_gender.currentText()
        voice_by_gender = {"male": "scott_brutal_ru", "female": "robot_light_female"}
        selected_voice = self.cmb_voice.currentText()
        if selected_voice not in voice_by_gender.values():
            selected_voice = voice_by_gender.get(gender, selected_voice)
        mic_id = int(self.cmb_mic.currentData()) if hasattr(self, "cmb_mic") else int(getattr(self.cfg, "input_device_id", -1))
        self.cfg = AppConfig(
            user_name=self.txt_user_name.text().strip(),
            user_title=self.cmb_user_title.currentText(),
            preferred_voice_gender=gender,
            voice_preset=selected_voice,
            llm_provider=self.cmb_provider.currentText(),
            llm_model=self.txt_model.text().strip(),
            llm_temperature=float(self.spin_temp.value()) if hasattr(self, "spin_temp") else float(getattr(self.cfg, "llm_temperature", 0.4)),
            llm_max_tokens=int(self.spin_max_tokens.value()) if hasattr(self, "spin_max_tokens") else int(getattr(self.cfg, "llm_max_tokens", 160)),
            asr_model_size=self.cmb_asr.currentText(),
            asr_language=self.cmb_lang.currentText(),
            asr_device=self.cmb_device.currentText(),
            input_device_id=mic_id,
            memory_path=str(self.cfg.memory_path),
            offline_game_limit_minutes=int(getattr(self.cfg, "offline_game_limit_minutes", 90)),
            activity_advice_cooldown_minutes=int(getattr(self.cfg, "activity_advice_cooldown_minutes", 20)),
            enable_power_confirmation=bool(getattr(self.cfg, "enable_power_confirmation", True)),
            assistant_memory_path=str(getattr(self.cfg, "assistant_memory_path", "./data/assistant_profile.json")),
            ui_font_family=self.cmb_font.currentText(),
            ui_font_size=int(self.spin_font.value()),
            ui_accent_color=str(self.lbl_accent.text()).strip() or "#72A0FF",
            ui_text_color=str(self.lbl_text_color.text()).strip() or "#EAF0FF",
            ui_panel_opacity_left=int(self.sld_left_op.value()),
            ui_panel_opacity_right=int(self.sld_right_op.value()),
        )
        save_config(self.cfg, BACKEND_DIR / "config.json")
        self.status.setText("✅ Настройки сохранены.")

    def _toggle_daemon(self) -> None:
        """Переключение состояния Скотта (включить/выключить)."""
        self._sync_runtime_state()
        if self._is_running:
            self.stop()
        else:
            self.start("voice_assistant_daemon.py")

    def start(self, script: str) -> None:
        if self.process and self.process.poll() is None:
            self.status.setText("⚠️ Сначала останови текущий режим.")
            return
        self.save()
        script_path = BACKEND_DIR / script
        is_daemon_mode = script == "voice_assistant_daemon.py"
        is_gui_mode = script in {"voice_assistant_daemon.py", "text_mode_qt.py", "text_chat_gui.py"}
        python_bin = self._resolve_python_bin(prefer_windowless=is_gui_mode)
        cmd = [python_bin, str(script_path)]
        try:
            if is_daemon_mode:
                running_pid = self._read_daemon_pid()
                if running_pid and self._is_pid_running(running_pid):
                    self.status.setText("ℹ️ Голосовой режим уже запущен в фоне.")
                    self._sync_runtime_state()
                    return
            creationflags = 0
            if is_daemon_mode:
                creationflags |= getattr(subprocess, "CREATE_NO_WINDOW", 0)
                creationflags |= getattr(subprocess, "DETACHED_PROCESS", 0)
                creationflags |= getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
            env = dict(os.environ)
            env.setdefault("MALTRUAND_HEADLESS", "1" if is_daemon_mode else "0")
            env.setdefault("MALTRUAND_VOICE_NO_WAKE", "0")
            env.setdefault("MALTRUAND_ALLOW_DIRECT_COMMANDS", "0")
            env.setdefault("MALTRUAND_DAEMON_ASR_MODEL", "base")
            env.setdefault("MALTRUAND_FORCE_CHUNK_LISTEN", "0")
            if is_daemon_mode:
                env.setdefault("PYTHONUNBUFFERED", "1")
            mic_id = int(getattr(self.cfg, "input_device_id", -1))
            if is_daemon_mode and mic_id >= 0:
                env["MALTRUAND_INPUT_DEVICE"] = str(mic_id)
            popen_kwargs = {
                "cwd": str(BACKEND_DIR),
                "creationflags": creationflags,
                "env": env,
            }
            if is_daemon_mode:
                log_path = BACKEND_DIR / "data" / "daemon.log"
                log_path.parent.mkdir(parents=True, exist_ok=True)
                daemon_log = open(log_path, "a", encoding="utf-8", errors="replace")
                popen_kwargs["stdout"] = daemon_log
                popen_kwargs["stderr"] = daemon_log
                popen_kwargs["stdin"] = subprocess.DEVNULL

            self.process = subprocess.Popen(cmd, **popen_kwargs)
            self._is_running = True
            if is_daemon_mode:
                self._write_daemon_pid(self.process.pid)
            self.status.setText(f"▶ Скотт запущен: {script}")
            self.badge.setText("● RUNNING")
            self.btn_main_toggle.setText("⏹ ВЫКЛЮЧИТЬ ГОЛОСОВОЙ РЕЖИМ")
            self.btn_main_toggle.setObjectName("mainToggleButton")
            self.btn_main_toggle.style().unpolish(self.btn_main_toggle)
            self.btn_main_toggle.style().polish(self.btn_main_toggle)
            self._sync_runtime_state()
        except Exception as e:
            self.status.setText(f"❌ Не удалось запустить: {e}")
            self.badge.setText("● ERROR")
            self._is_running = False

    def _resolve_python_bin(self, prefer_windowless: bool) -> str:
        """Надёжный выбор интерпретатора даже в EXE-режиме лаунчера."""
        if not prefer_windowless:
            return sys.executable

        candidates = []
        exe_path = Path(sys.executable)
        candidates.append(exe_path.with_name("pythonw.exe"))
        candidates.append(exe_path.with_name("python.exe"))
        pyw = shutil.which("pythonw")
        if pyw:
            candidates.append(Path(pyw))
        py = shutil.which("python")
        if py:
            candidates.append(Path(py))

        for c in candidates:
            try:
                if c.exists() and c.is_file():
                    return str(c)
            except Exception:
                continue
        return sys.executable


    def stop(self) -> None:
        """Остановка Скотта (дежурного режима)."""
        stopped = False
        pid = self._read_daemon_pid()
        if pid and self._is_pid_running(pid):
            try:
                subprocess.run(["taskkill", "/PID", str(pid), "/T", "/F"], check=False, capture_output=True)
                stopped = True
            except Exception:
                pass

        if self.process and self.process.poll() is None:
            try:
                self.process.terminate()
                stopped = True
            except Exception:
                pass

        if not stopped:
            self.status.setText("Нет запущенного процесса.")
            self._sync_runtime_state()
            return
        try:
            QtCore.QTimer.singleShot(1000, lambda: self._force_stop())
            self.status.setText("⏹ Останавливаю Скотта...")
            self.badge.setText("● STOPPING")
        except Exception as e:
            self.status.setText(f"⚠️ Не удалось остановить: {e}")
            self.badge.setText("● ERROR")

    def _force_stop(self) -> None:
        """Принудительная остановка процесса."""
        if self.process and self.process.poll() is None:
            try:
                self.process.kill()
            except Exception:
                pass
        self._clear_daemon_pid()
        self._is_running = False
        self.status.setText("⏹ Скотт остановлен.")
        self.badge.setText("● READY")
        self.btn_main_toggle.setText("🎙 ВКЛЮЧИТЬ ГОЛОСОВОЙ РЕЖИМ")
        self.btn_main_toggle.setObjectName("mainToggleButton")
        self.btn_main_toggle.style().unpolish(self.btn_main_toggle)
        self.btn_main_toggle.style().polish(self.btn_main_toggle)
        self._sync_runtime_state()

    def _write_daemon_pid(self, pid: int) -> None:
        self._daemon_pid_file.parent.mkdir(parents=True, exist_ok=True)
        self._daemon_pid_file.write_text(str(pid), encoding="utf-8")

    def _read_daemon_pid(self) -> Optional[int]:
        if not self._daemon_pid_file.exists():
            return None
        try:
            raw = self._daemon_pid_file.read_text(encoding="utf-8").strip()
            return int(raw) if raw.isdigit() else None
        except Exception:
            return None

    def _clear_daemon_pid(self) -> None:
        try:
            self._daemon_pid_file.unlink(missing_ok=True)
        except Exception:
            pass

    def _is_pid_running(self, pid: int) -> bool:
        if pid <= 0:
            return False
        try:
            os.kill(pid, 0)
            return True
        except OSError:
            return False
        except Exception:
            return False

    def _sync_runtime_state(self) -> None:
        pid = self._read_daemon_pid()
        running = bool(pid and self._is_pid_running(pid))
        self._is_running = running
        if running:
            self.badge.setText("● RUNNING")
            self.status.setText("Голосовой режим активен в фоне.")
            self.btn_main_toggle.setText("⏹ ВЫКЛЮЧИТЬ ГОЛОСОВОЙ РЕЖИМ")
            if hasattr(self, "status_tray_action"):
                self.status_tray_action.setText(f"Статус: активен (PID {pid})")
        else:
            self.badge.setText("● READY")
            self.btn_main_toggle.setText("🎙 ВКЛЮЧИТЬ ГОЛОСОВОЙ РЕЖИМ")
            if hasattr(self, "status_tray_action"):
                self.status_tray_action.setText("Статус: выключен")

    def _browse_video_file(self) -> None:
        """Выбор видео файла."""
        from PySide6.QtWidgets import QFileDialog
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Выберите видео файл",
            "",
            "Video Files (*.mp4 *.avi *.mkv *.mov *.wmv);;All Files (*)"
        )
        if file_path:
            self.txt_video_path.setText(file_path)

    def _add_character(self) -> None:
        """Добавление персонажа с голосом."""
        from PySide6.QtWidgets import QDialog, QDialogButtonBox
        
        dialog = QDialog(self)
        dialog.setWindowTitle("Добавить персонажа")
        dialog.setMinimumWidth(300)
        
        layout = QtWidgets.QFormLayout(dialog)
        
        name_edit = QtWidgets.QLineEdit()
        name_edit.setPlaceholderText("Имя персонажа")
        layout.addRow("Имя:", name_edit)
        
        voice_combo = QtWidgets.QComboBox()
        voices = sorted(list_available_voices().keys())
        voice_combo.addItems(voices)
        layout.addRow("Голос:", voice_combo)
        
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        layout.addRow(buttons)
        
        if dialog.exec() == QDialog.DialogCode.Accepted:
            name = name_edit.text().strip()
            voice = voice_combo.currentText()
            if name:
                item = QtWidgets.QListWidgetItem(f"{name} → {voice}")
                item.setData(QtCore.Qt.ItemDataRole.UserRole, (name, voice))
                self.characters_list.addItem(item)

    def _remove_character(self) -> None:
        """Удаление выбранного персонажа."""
        current = self.characters_list.currentItem()
        if current:
            self.characters_list.takeItem(self.characters_list.row(current))

    def _generate_dubbing(self) -> None:
        """Генерация озвучки видео."""
        video_path = Path(self.txt_video_path.text().strip())
        if not video_path.exists():
            self.status.setText("❌ Видео файл не найден!")
            return

        narration_text = self.txt_narration.toPlainText().strip()

        if self.characters_list.count() == 0 and not narration_text:
            self.status.setText("❌ Добавьте персонажа или введите текст для озвучки!")
            return

        # Собираем персонажей
        try:
            from video_dubbing.engine import CharacterVoice, VideoDubber, DubbingConfig, DialogueLine
            
            characters = {}
            for i in range(self.characters_list.count()):
                item = self.characters_list.item(i)
                name, voice_preset = item.data(QtCore.Qt.ItemDataRole.UserRole)
                characters[name] = CharacterVoice(
                    character_name=name,
                    voice_preset=voice_preset,
                    language="ru"
                )
            
            # Создаём конфигурацию (пока без диалогов - позже можно добавить загрузку субтитров)
            output_path = video_path.parent / f"{video_path.stem}_dubbed{video_path.suffix}"
            
            config = DubbingConfig(
                video_path=video_path,
                output_path=output_path,
                characters=characters,
                dialogues=[],  # TODO: загрузка субтитров и разметки диалогов
                narration_text=narration_text or None,
                narration_voice_preset=self.cmb_narrator_voice.currentText() if narration_text else None,
                narration_language="ru",
            )
            
            self.status.setText("🎬 Генерация озвучки... (это может занять время)")
            
            dubber = VideoDubber()
            result_path = dubber.generate_dubbing(config)
            self.status.setText(f"✅ Озвучка завершена: {result_path}")
        except Exception as e:
            self.status.setText(f"❌ Ошибка: {e}")


def main() -> None:
    app = QtWidgets.QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)  # Не закрывать приложение при закрытии окна
    
    w = Launcher()
    w.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()

