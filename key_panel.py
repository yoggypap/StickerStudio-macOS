from PySide6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel, QSlider, QFrame
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor

# Theme Colors
SURFACE = "#17171B"
SURFACE_RAISED = "#222228"
BORDER_IDLE = "#33333A"
BORDER_HOVER = "#53525B"
TEXT_MAIN = "#F9F8F6"
TEXT_MUTED = "#9F9DA4"
ACCENT = "#FF3E05"
ACCENT_HOVER = "#FF5826"

class KeyPanel(QWidget):
    apply_requested = Signal()
    cancel_requested = Signal()
    params_changed = Signal()
    pick_toggled = Signal(bool)
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("keyPanel")
        self.setStyleSheet("""
            #keyPanel {
                background: transparent;
                border: none;
            }
            QLabel {
                border: none;
                background: transparent;
            }
        """)
        
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 4, 0, 4)
        main_layout.setSpacing(10)
        
        # ─── 1. Compact Color Swatch & Pipette Row ────────────────────────────
        color_card = QFrame()
        color_card.setObjectName("colorCard")
        color_card.setFixedHeight(46)
        color_card.setStyleSheet(f"""
            #colorCard {{
                background-color: {SURFACE};
                border: 1px solid {BORDER_IDLE};
                border-radius: 8px;
            }}
            QLabel {{
                border: none;
                background: transparent;
            }}
        """)
        color_layout = QHBoxLayout(color_card)
        color_layout.setContentsMargins(12, 6, 12, 6)
        color_layout.setSpacing(10)
        
        self.swatch = QLabel()
        self.swatch.setFixedSize(22, 22)
        self.swatch.setStyleSheet("background-color: rgb(0, 255, 0); border-radius: 11px; border: 1.5px solid white;")
        color_layout.addWidget(self.swatch)
        
        color_title = QLabel("Цвет фона")
        color_title.setStyleSheet(f"color: {TEXT_MAIN}; font-size: 12px; font-weight: bold; border: none; background: transparent;")
        color_layout.addWidget(color_title)
        
        color_layout.addStretch(1)
        
        self.pick_btn = QPushButton("Пипетка")
        self.pick_btn.setCheckable(True)
        self.pick_btn.setFixedHeight(28)
        self._update_pick_style(False)
        self.pick_btn.toggled.connect(self._on_pick_toggled)
        color_layout.addWidget(self.pick_btn)
        
        main_layout.addWidget(color_card)
        
        slider_style = f"""
            QSlider {{
                background: transparent;
                border: none;
                height: 22px;
            }}
            QSlider::groove:horizontal {{
                height: 4px;
                background: {BORDER_IDLE};
                border-radius: 2px;
            }}
            QSlider::sub-page:horizontal {{
                background: {ACCENT};
                border-radius: 2px;
            }}
            QSlider::handle:horizontal {{
                background: {TEXT_MAIN};
                border: 1px solid {BORDER_HOVER};
                width: 14px;
                height: 14px;
                margin: -5px 0;
                border-radius: 7px;
            }}
            QSlider::handle:horizontal:hover {{
                background: #FFFFFF;
                border-color: {ACCENT};
            }}
        """

        # ─── 2. Parameter Card: Сила удаления (Gain) ──────────────────────────
        gain_card = QFrame()
        gain_card.setObjectName("gainCard")
        gain_card.setFixedHeight(80)
        gain_card.setStyleSheet(f"""
            #gainCard {{
                background-color: {SURFACE};
                border: 1px solid {BORDER_IDLE};
                border-radius: 8px;
            }}
            QLabel {{
                border: none;
                background: transparent;
            }}
        """)
        gain_layout = QVBoxLayout(gain_card)
        gain_layout.setContentsMargins(12, 10, 12, 10)
        gain_layout.setSpacing(6)
        
        gain_header = QHBoxLayout()
        gain_title = QLabel("Сила удаления")
        gain_title.setStyleSheet(f"color: {TEXT_MAIN}; font-size: 12px; font-weight: bold; border: none; background: transparent;")
        self.gain_val_lbl = QLabel("100")
        self.gain_val_lbl.setStyleSheet(f"color: {ACCENT}; font-size: 12px; font-weight: bold; border: none; background: transparent;")
        gain_header.addWidget(gain_title)
        gain_header.addStretch(1)
        gain_header.addWidget(self.gain_val_lbl)
        gain_layout.addLayout(gain_header)
        
        self.gain_slider = QSlider(Qt.Horizontal)
        self.gain_slider.setRange(0, 200)
        self.gain_slider.setValue(100)
        self.gain_slider.setStyleSheet(slider_style)
        self.gain_slider.valueChanged.connect(self._on_gain)
        gain_layout.addWidget(self.gain_slider)
        
        main_layout.addWidget(gain_card)
        
        # ─── 3. Parameter Card: Край маски (Shrink / Grow) ────────────────────
        shrink_card = QFrame()
        shrink_card.setObjectName("shrinkCard")
        shrink_card.setFixedHeight(80)
        shrink_card.setStyleSheet(f"""
            #shrinkCard {{
                background-color: {SURFACE};
                border: 1px solid {BORDER_IDLE};
                border-radius: 8px;
            }}
            QLabel {{
                border: none;
                background: transparent;
            }}
        """)
        shrink_layout = QVBoxLayout(shrink_card)
        shrink_layout.setContentsMargins(12, 10, 12, 10)
        shrink_layout.setSpacing(6)
        
        shrink_header = QHBoxLayout()
        shrink_title = QLabel("Край маски")
        shrink_title.setStyleSheet(f"color: {TEXT_MAIN}; font-size: 12px; font-weight: bold; border: none; background: transparent;")
        self.shrink_val_lbl = QLabel("0")
        self.shrink_val_lbl.setStyleSheet(f"color: {TEXT_MUTED}; font-size: 12px; font-weight: bold; border: none; background: transparent;")
        shrink_header.addWidget(shrink_title)
        shrink_header.addStretch(1)
        shrink_header.addWidget(self.shrink_val_lbl)
        shrink_layout.addLayout(shrink_header)
        
        self.shrink_slider = QSlider(Qt.Horizontal)
        self.shrink_slider.setRange(-100, 100)
        self.shrink_slider.setValue(0)
        self.shrink_slider.setStyleSheet(slider_style)
        self.shrink_slider.valueChanged.connect(self._on_shrink)
        shrink_layout.addWidget(self.shrink_slider)
        
        main_layout.addWidget(shrink_card)
        
        # Compatibility label aliases
        self.gain_lbl = self.gain_val_lbl
        self.shrink_lbl = self.shrink_val_lbl
        
        main_layout.addStretch(1)
        
        # ─── 4. Action Buttons ────────────────────────────────────────────────
        btns_layout = QHBoxLayout()
        btns_layout.setSpacing(8)
        
        self.apply_btn = QPushButton("Применить")
        self.apply_btn.setFixedHeight(40)
        self.apply_btn.setMinimumWidth(100)
        self.apply_btn.setStyleSheet(f"""
            QPushButton {{
                color: {TEXT_MAIN};
                background-color: {ACCENT};
                border-radius: 6px;
                padding: 0 12px;
                font-weight: bold;
                font-size: 12px;
                border: none;
            }}
            QPushButton:hover {{
                background-color: {ACCENT_HOVER};
            }}
        """)
        self.apply_btn.clicked.connect(self.apply_requested.emit)
        
        self.cancel_btn = QPushButton("Отмена")
        self.cancel_btn.setFixedHeight(40)
        self.cancel_btn.setMinimumWidth(80)
        self.cancel_btn.setStyleSheet(f"""
            QPushButton {{
                color: {TEXT_MAIN};
                background-color: {BORDER_IDLE};
                border-radius: 6px;
                padding: 0 12px;
                font-size: 12px;
                border: none;
            }}
            QPushButton:hover {{
                background-color: {BORDER_HOVER};
            }}
        """)
        self.cancel_btn.clicked.connect(self.cancel_requested.emit)
        
        btns_layout.addWidget(self.apply_btn)
        btns_layout.addWidget(self.cancel_btn)
        main_layout.addLayout(btns_layout)

    def _update_pick_style(self, checked: bool):
        if checked:
            self.pick_btn.setText("Пипетка (Вкл)")
            self.pick_btn.setStyleSheet(f"""
                QPushButton {{
                    color: {TEXT_MAIN};
                    background-color: {ACCENT};
                    border: none;
                    border-radius: 6px;
                    padding: 0 12px;
                    font-size: 11px;
                    font-weight: bold;
                }}
            """)
        else:
            self.pick_btn.setText("Пипетка")
            self.pick_btn.setStyleSheet(f"""
                QPushButton {{
                    color: {TEXT_MAIN};
                    background-color: {SURFACE_RAISED};
                    border: 1px solid {BORDER_IDLE};
                    border-radius: 6px;
                    padding: 0 12px;
                    font-size: 11px;
                }}
                QPushButton:hover {{
                    border-color: {BORDER_HOVER};
                }}
            """)

    def _on_pick_toggled(self, v):
        self._update_pick_style(v)
        self.pick_toggled.emit(v)
        
    def _on_gain(self, v):
        self.gain_val_lbl.setText(str(v))
        self.params_changed.emit()
        
    def _on_shrink(self, v):
        sign = "+" if v > 0 else ""
        self.shrink_val_lbl.setText(f"{sign}{v}")
        if v != 0:
            self.shrink_val_lbl.setStyleSheet(f"color: {ACCENT}; font-size: 12px; font-weight: bold; border: none; background: transparent;")
        else:
            self.shrink_val_lbl.setStyleSheet(f"color: {TEXT_MUTED}; font-size: 12px; font-weight: bold; border: none; background: transparent;")
        self.params_changed.emit()
        
    def set_color(self, r, g, b):
        self.swatch.setStyleSheet(f"background-color: rgb({r}, {g}, {b}); border-radius: 11px; border: 1.5px solid white;")
        
    def get_gain(self):
        return self.gain_slider.value()

    def get_shrink(self):
        return self.shrink_slider.value()

    def set_gain(self, v):
        self.gain_slider.setValue(v)
        self.gain_val_lbl.setText(str(v))

    def set_shrink(self, v):
        self.shrink_slider.setValue(v)
        sign = "+" if v > 0 else ""
        self.shrink_val_lbl.setText(f"{sign}{v}")
