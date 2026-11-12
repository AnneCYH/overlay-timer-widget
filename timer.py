#!/usr/bin/env python3
import sys
import os
from PyQt6.QtCore import Qt, QTimer, QUrl, QEvent
from PyQt6.QtWidgets import (
    QApplication, QWidget, QHBoxLayout, 
    QLabel, QLineEdit, QPushButton, QFileDialog, QMenu,
    QStackedLayout
)
from PyQt6.QtMultimedia import QAudioOutput, QMediaPlayer

class OverlayTimerWidget(QWidget):
    # Scale configurations: (font_px, edit_width, accent_btn_size, icon_btn_size, pill_radius, btn_radius, margin_h, margin_v, spacing)
    SIZES = {
        "small":  {"font": 19, "edit_w": 86,  "accent_w": 32, "icon_w": 28, "pill_r": 22, "btn_r": 14, "pad_h": 14, "pad_v": 8,  "space": 10},
        "medium": {"font": 26, "edit_w": 115, "accent_w": 42, "icon_w": 36, "pill_r": 28, "btn_r": 18, "pad_h": 18, "pad_v": 10, "space": 12},
        "large":  {"font": 36, "edit_w": 155, "accent_w": 52, "icon_w": 44, "pill_r": 34, "btn_r": 22, "pad_h": 22, "pad_v": 14, "space": 16},
    }

    def __init__(self):
        super().__init__()
        self.default_seconds = 25 * 60
        self.remaining_seconds = self.default_seconds
        self.is_running = False
        self.play_tick_sound = True
        self.current_size = "small"

        # Dynamically evaluate the snap environment base path or fall back to local file directory
        snap_path = os.environ.get('SNAP', os.path.dirname(os.path.abspath(__file__)))
        
        # Match where override-build copies the audio files: $CRAFT_PART_INSTALL/bin/
        # Check both the explicit snap layout bin directory and the fallback script directory
        snap_bin_dir = os.path.join(snap_path, "bin")
        if os.path.exists(os.path.join(snap_bin_dir, "tick.mp3")):
            base_dir = snap_bin_dir
        else:
            base_dir = os.path.dirname(os.path.abspath(__file__))

        self.tick_sound_path = os.path.join(base_dir, "tick.mp3")
        self.alarm_sound_path = os.path.join(base_dir, "alarm.mp3")

        # Audio pipeline
        self.tick_output = QAudioOutput()
        self.tick_player = QMediaPlayer()
        self.tick_player.setAudioOutput(self.tick_output)
        self.tick_player.setLoops(QMediaPlayer.Loops.Infinite)

        self.alarm_output = QAudioOutput()
        self.alarm_player = QMediaPlayer()
        self.alarm_player.setAudioOutput(self.alarm_output)

        self.timer = QTimer(self)
        self.timer.timeout.connect(self.tick)

        self.init_ui()
        self.load_sound_sources()

        # Global event filter for drag and double-click
        QApplication.instance().installEventFilter(self)

    def init_ui(self):
        self.setWindowFlags(
            Qt.WindowType.WindowStaysOnTopHint |
            Qt.WindowType.FramelessWindowHint |
            Qt.WindowType.SubWindow
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)

        self.main_layout = QHBoxLayout()
        self.setLayout(self.main_layout)

        # Time container (Display / Inline Edit)
        self.time_container = QWidget(self)
        self.time_stack = QStackedLayout(self.time_container)
        self.time_stack.setContentsMargins(0, 0, 0, 0)

        # 1. Time Display Label
        self.label = QLabel(self.format_time(), self)
        self.label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.label.setToolTip("Double-click to edit duration")
        self.time_stack.addWidget(self.label)

        # 2. Time Input Field
        self.edit_input = QLineEdit(self)
        self.edit_input.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.edit_input.returnPressed.connect(self.finish_inline_edit)
        self.time_stack.addWidget(self.edit_input)

        self.main_layout.addWidget(self.time_container)

        # Play / Pause button
        self.play_pause_btn = QPushButton("▶", self)
        self.play_pause_btn.setObjectName("accentBtn")
        self.play_pause_btn.clicked.connect(self.toggle_timer)
        self.main_layout.addWidget(self.play_pause_btn)

        # Reset button
        self.reset_btn = QPushButton("↺", self)
        self.reset_btn.setToolTip("Reset")
        self.reset_btn.clicked.connect(self.reset_timer)
        self.main_layout.addWidget(self.reset_btn)

        # Audio settings button
        self.sound_btn = QPushButton("⚙", self)
        self.sound_btn.setToolTip("Settings & Options")
        self.sound_btn.clicked.connect(self.show_settings_menu)
        self.main_layout.addWidget(self.sound_btn)

        # Close button
        self.close_btn = QPushButton("✕", self)
        self.close_btn.setObjectName("closeBtn")
        self.close_btn.setToolTip("Close")
        self.close_btn.clicked.connect(self.exit_app)
        self.main_layout.addWidget(self.close_btn)

        # Apply current size metrics and theme
        self.apply_size(self.current_size)

    def apply_size(self, size_key):
        """Dynamically scales all elements, fonts, radiuses, and padding."""
        self.current_size = size_key
        cfg = self.SIZES[size_key]

        # Layout margins and spacing
        self.main_layout.setContentsMargins(cfg["pad_h"], cfg["pad_v"], cfg["pad_h"], cfg["pad_v"])
        self.main_layout.setSpacing(cfg["space"])

        # Widget element sizes
        self.edit_input.setFixedWidth(cfg["edit_w"])
        self.play_pause_btn.setFixedSize(cfg["accent_w"], cfg["accent_w"])
        for btn in (self.reset_btn, self.sound_btn, self.close_btn):
            btn.setFixedSize(cfg["icon_w"], cfg["icon_w"])

        # Font & button sizing formulas
        icon_font_size = max(12, int(cfg["icon_w"] * 0.44))
        accent_font_size = max(13, int(cfg["accent_w"] * 0.42))

        # Re-apply styles with size variables
        badge_style = f"""
            font-family: 'Ubuntu', 'Liberation Sans', sans-serif;
            font-size: {cfg["font"]}px;
            font-weight: 700;
            color: #FFFFFF;
            background-color: rgba(22, 22, 22, 0.92);
            border-radius: 8px;
            padding: 4px 10px;
        """

        self.label.setStyleSheet(f"""
            QLabel {{
                {badge_style}
                border: 1px solid rgba(255, 255, 255, 0.16);
            }}
            QLabel:hover {{
                border: 1px solid #E95420;
            }}
        """)

        self.edit_input.setStyleSheet(f"""
            QLineEdit {{
                {badge_style}
                border: 1.5px solid #E95420;
                selection-background-color: #E95420;
            }}
        """)

        self.setStyleSheet(f"""
            OverlayTimerWidget {{
                background-color: rgba(38, 38, 38, 0.88);
                border-radius: {cfg["pill_r"]}px;
                border: 1px solid rgba(255, 255, 255, 0.15);
            }}
            QPushButton {{
                background-color: rgba(255, 255, 255, 0.09);
                color: #DFDBCE;
                border: 1px solid rgba(255, 255, 255, 0.05);
                border-radius: {cfg["btn_r"]}px;
                font-size: {icon_font_size}px;
                font-weight: 500;
            }}
            QPushButton:hover {{
                background-color: rgba(255, 255, 255, 0.18);
                color: #FFFFFF;
            }}
            QPushButton#accentBtn {{
                background-color: #E95420;
                color: #FFFFFF;
                border: none;
                border-radius: {cfg["accent_w"] // 2}px;
                font-size: {accent_font_size}px;
            }}
            QPushButton#accentBtn:hover {{
                background-color: #F06E3F;
            }}
            QPushButton#closeBtn:hover {{
                background-color: #C7162B;
                color: #FFFFFF;
            }}
            QMenu {{
                background-color: #2D2D2D;
                border: 1px solid rgba(255, 255, 255, 0.12);
                border-radius: 8px;
                padding: 4px;
                color: #DFDBCE;
                font-size: 13px;
            }}
            QMenu::item {{
                padding: 6px 16px;
                border-radius: 4px;
            }}
            QMenu::item:selected {{
                background-color: #E95420;
                color: #FFFFFF;
            }}
            QMenu::separator {{
                height: 1px;
                background-color: rgba(255, 255, 255, 0.1);
                margin: 4px 6px;
            }}
        """)

        # Shrink/expand capsule to wrap newly sized children
        self.adjustSize()

    def eventFilter(self, watched, event):
        """Native system dragging and double-click inline edit."""
        if watched == self.label and event.type() == QEvent.Type.MouseButtonDblClick:
            self.start_inline_edit()
            return True

        if event.type() == QEvent.Type.MouseButtonPress and event.button() == Qt.MouseButton.LeftButton:
            if watched in (self, self.label, self.time_container):
                window_handle = self.windowHandle()
                if window_handle:
                    window_handle.startSystemMove()
                    return True

        return super().eventFilter(watched, event)

    def start_inline_edit(self):
        self.edit_input.setText(self.format_time())
        self.time_stack.setCurrentIndex(1)
        self.edit_input.setFocus()
        self.edit_input.selectAll()

    def finish_inline_edit(self):
        text = self.edit_input.text().strip()
        seconds = self.parse_time_input(text)

        if seconds is not None and seconds > 0:
            self.timer.stop()
            self.is_running = False
            self.tick_player.stop()
            self.play_pause_btn.setText("▶")

            self.default_seconds = seconds
            self.remaining_seconds = seconds
            self.label.setText(self.format_time())

        self.time_stack.setCurrentIndex(0)

    def parse_time_input(self, text):
        try:
            if ":" in text:
                parts = text.split(":")
                mins = int(parts[0])
                secs = int(parts[1])
                return mins * 60 + secs
            else:
                mins = int(text)
                return mins * 60
        except ValueError:
            return None

    def load_sound_sources(self):
        if os.path.exists(self.tick_sound_path):
            self.tick_player.setSource(QUrl.fromLocalFile(self.tick_sound_path))
        if os.path.exists(self.alarm_sound_path):
            self.alarm_player.setSource(QUrl.fromLocalFile(self.alarm_sound_path))

    def format_time(self):
        mins, secs = divmod(self.remaining_seconds, 60)
        return f"{mins:02d}:{secs:02d}"

    def toggle_timer(self):
        if self.time_stack.currentIndex() == 1:
            self.finish_inline_edit()

        if self.is_running:
            self.timer.stop()
            self.play_pause_btn.setText("▶")
            self.tick_player.pause()
        else:
            self.timer.start(1000)
            self.play_pause_btn.setText("⏸")
            if self.play_tick_sound and self.tick_player.source().isValid():
                self.tick_player.play()

        self.is_running = not self.is_running

    def reset_timer(self):
        if self.time_stack.currentIndex() == 1:
            self.time_stack.setCurrentIndex(0)

        self.timer.stop()
        self.is_running = False
        self.remaining_seconds = self.default_seconds
        self.label.setText(self.format_time())
        self.play_pause_btn.setText("▶")
        self.tick_player.stop()

    def tick(self):
        if self.remaining_seconds > 0:
            self.remaining_seconds -= 1
            self.label.setText(self.format_time())
        else:
            self.timer.stop()
            self.is_running = False
            self.play_pause_btn.setText("▶")
            self.tick_player.stop()

            if self.alarm_player.source().isValid():
                self.alarm_player.setPosition(0)
                self.alarm_player.play()

    def show_settings_menu(self):
        menu = QMenu(self)

        # Widget Size Submenu
        size_menu = menu.addMenu("Widget Size")
        for key, name in [("small", "Small (Default)"), ("medium", "Medium"), ("large", "Large")]:
            action = size_menu.addAction(name)
            action.setCheckable(True)
            action.setChecked(self.current_size == key)
            action.triggered.connect(lambda checked, k=key: self.apply_size(k))

        menu.addSeparator()

        # Audio options
        tick_label = "Mute Ticking Loop" if self.play_tick_sound else "Enable Ticking Loop"
        action_toggle_tick = menu.addAction(tick_label)
        action_toggle_tick.triggered.connect(self.toggle_tick_mute)

        menu.addSeparator()

        action_custom_tick = menu.addAction("Change Ticking Audio...")
        action_custom_tick.triggered.connect(self.choose_tick_sound)

        action_custom_alarm = menu.addAction("Change Alarm Sound...")
        action_custom_alarm.triggered.connect(self.choose_alarm_sound)

        menu.exec(self.sound_btn.mapToGlobal(self.sound_btn.rect().bottomLeft()))

    def toggle_tick_mute(self):
        self.play_tick_sound = not self.play_tick_sound
        if not self.play_tick_sound:
            self.tick_player.pause()
        elif self.is_running:
            self.tick_player.play()

    def choose_tick_sound(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Select Ticking Audio Loop", "", "Audio Files (*.wav *.mp3 *.ogg)"
        )
        if path:
            self.tick_sound_path = path
            self.tick_player.setSource(QUrl.fromLocalFile(path))
            if self.is_running and self.play_tick_sound:
                self.tick_player.play()

    def choose_alarm_sound(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Select Alarm Audio", "", "Audio Files (*.wav *.mp3 *.ogg)"
        )
        if path:
            self.alarm_sound_path = path
            self.alarm_player.setSource(QUrl.fromLocalFile(path))

    def exit_app(self):
        self.timer.stop()
        self.tick_player.stop()
        self.alarm_player.stop()
        self.close()
        QApplication.quit()

if __name__ == "__main__":
    app = QApplication(sys.argv)
    widget = OverlayTimerWidget()
    widget.show()
    sys.exit(app.exec())
