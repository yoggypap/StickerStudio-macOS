import sys, time, os, copy, glob
from PySide6.QtCore import Qt, Signal, QSize, QByteArray, QTimer, QThread, QPoint, QPointF, QRectF, QRect, QEvent
from PySide6.QtGui import (QColor, QPalette, QFont, QAction, QKeySequence, QPixmap, QImage, QShortcut, 
                           QFontDatabase, QPainter, QBrush, QPen, QRadialGradient, QPainterPath)
from PySide6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, 
                               QHBoxLayout, QLabel, QPushButton, QFileDialog, 
                               QStackedWidget, QFrame, QSizePolicy, QMessageBox)

from video_doc import VideoDoc
from ffmpeg_utils import Ffmpeg
from timeline import TimelineControl
from preview_widget import PreviewWidget
from key_panel import KeyPanel
from preview_renderer import PreviewRenderer, ExactPreviewRequest, PlaybackCacheRequest
from models import KeySettings
from export_worker import ExportWorker, ExportRequest
from export_pipeline import ExportResult

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

def get_resource_path(filename: str) -> str:
    if getattr(sys, 'frozen', False):
        # 1. Check Contents/Resources/
        res_dir = os.path.normpath(os.path.join(os.path.dirname(sys.executable), "..", "Resources"))
        cand = os.path.join(res_dir, filename)
        if os.path.exists(cand):
            return cand
        # 2. Check sys._MEIPASS (Contents/MacOS)
        meipass = getattr(sys, '_MEIPASS', os.path.dirname(sys.executable))
        cand = os.path.join(meipass, filename)
        if os.path.exists(cand):
            return cand
    cand = os.path.join(BASE_DIR, filename)
    return cand

LOGO_PATH = get_resource_path("uxlive-logo.png")

_fonts_loaded = False
def ensure_fonts():
    global _fonts_loaded
    if _fonts_loaded or QApplication.instance() is None:
        return
    f1 = get_resource_path("phosphor-icons.ttf")
    f2 = get_resource_path("phosphor-icons-fill.ttf")
    if os.path.exists(f1):
        QFontDatabase.addApplicationFont(f1)
    if os.path.exists(f2):
        QFontDatabase.addApplicationFont(f2)
    _fonts_loaded = True

class Icons:
    BACK = chr(0xE058)
    UNDO = chr(0xE038)
    CROP = chr(0xE1D4)
    BACKGROUND = chr(0xE6B6)
    PLAY = chr(0xE3D0)
    PAUSE = chr(0xE39E)
    EXPORT = chr(0xEAF0)
    LOCK = chr(0xE2FA)
    CHECK = chr(0xE182)
    CLOSE = chr(0xE4F6)
    VIDEO_UPLOAD = chr(0xE4C0)
    FILE_VIDEO = chr(0xEA22)
    EYEDROPPER = chr(0xE568)

# Theme Colors (Matching original UX Live / Sticker Studio)
BACK_MAIN = "#0B0B0D"
BACK_PANEL = "#121215"
BACK_HEADER = "#18181C"
STAGE = "#0E0E11"
TEXT_MAIN = "#F9F8F6"
TEXT_MUTED = "#9F9DA4"
TEXT_SOFT = "#D7D4CF"
ACCENT = "#FF3E05"
ACCENT_HOVER = "#FF5826"
ACCENT_PRESSED = "#D93400"
SURFACE = "#17171B"
SURFACE_RAISED = "#222228"
BORDER_IDLE = "#33333A"
BORDER_HOVER = "#53525B"
OK_COLOR = "#63D89E"
WARN_COLOR = "#F7C55F"

class LoaderThread(QThread):
    progress = Signal(int, str)
    finished = Signal(str, object)
    
    def __init__(self, ffmpeg, path):
        super().__init__()
        self.ffmpeg = ffmpeg
        self.path = path
        
    def run(self):
        doc = VideoDoc()
        err = doc.load(self.ffmpeg, self.path, lambda p, text: self.progress.emit(p, text))
        self.finished.emit(err or "", doc)

class ToolRailButton(QPushButton):
    def __init__(self, icon_char: str, label_text: str, parent=None):
        ensure_fonts()
        super().__init__(parent)
        self._raw_text = label_text
        self.setCheckable(True)
        self.setCursor(Qt.PointingHandCursor)
        self.setFixedSize(82, 68)
        self.setObjectName("toolRailBtn")
        
        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 8, 4, 8)
        layout.setSpacing(4)
        layout.setAlignment(Qt.AlignCenter)
        
        self.icon_lbl = QLabel(icon_char)
        self.icon_lbl.setAlignment(Qt.AlignCenter)
        self.icon_lbl.setStyleSheet("font-family: 'Phosphor'; font-size: 22px; color: #F9F8F6; background: transparent; border: none;")
        
        self.text_lbl = QLabel(label_text)
        self.text_lbl.setAlignment(Qt.AlignCenter)
        self.text_lbl.setStyleSheet("font-size: 11px; font-weight: bold; color: #F9F8F6; background: transparent; border: none;")
        
        layout.addWidget(self.icon_lbl)
        layout.addWidget(self.text_lbl)
        
        self.setStyleSheet(f"""
            QPushButton#toolRailBtn {{
                background-color: {SURFACE};
                border: 1px solid {BORDER_IDLE};
                border-radius: 10px;
            }}
            QPushButton#toolRailBtn:hover {{
                background-color: {SURFACE_RAISED};
                border-color: {BORDER_HOVER};
            }}
            QPushButton#toolRailBtn:checked {{
                background-color: #2A1914;
                border: 1px solid {ACCENT};
            }}
        """)

    def text(self):
        return self._raw_text

    def setText(self, text: str):
        self._raw_text = text
        self.text_lbl.setText(text)

class StatusRowWidget(QFrame):
    def __init__(self, parent=None):
        ensure_fonts()
        super().__init__(parent)
        self.setFixedHeight(44)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 6, 12, 6)
        layout.setSpacing(10)
        
        self.icon_box = QFrame()
        self.icon_box.setFixedSize(28, 28)
        ib_layout = QVBoxLayout(self.icon_box)
        ib_layout.setContentsMargins(0, 0, 0, 0)
        ib_layout.setAlignment(Qt.AlignCenter)
        
        self.icon_lbl = QLabel()
        self.icon_lbl.setAlignment(Qt.AlignCenter)
        self.icon_lbl.setStyleSheet("font-family: 'Phosphor'; font-size: 15px; border: none; background: transparent;")
        ib_layout.addWidget(self.icon_lbl)
        
        self.caption_lbl = QLabel()
        self.caption_lbl.setStyleSheet(f"font-size: 12px; font-weight: bold; color: {TEXT_MAIN}; border: none; background: transparent;")
        
        self.value_lbl = QLabel()
        self.value_lbl.setStyleSheet("font-size: 12px; border: none; background: transparent;")
        self.value_lbl.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        
        layout.addWidget(self.icon_box)
        layout.addWidget(self.caption_lbl)
        layout.addStretch(1)
        layout.addWidget(self.value_lbl)

    def set_status(self, caption: str, value: str, icon_char: str, tone_color: str, strong: bool = False):
        self.caption_lbl.setText(caption)
        self.value_lbl.setText(value)
        font_weight = "bold" if strong else "normal"
        self.value_lbl.setStyleSheet(f"font-size: 12px; font-weight: {font_weight}; color: {tone_color}; border: none; background: transparent;")
        self.icon_lbl.setText(icon_char)
        self.icon_lbl.setStyleSheet(f"font-family: 'Phosphor'; font-size: 15px; color: {tone_color}; border: none; background: transparent;")
        
        if strong:
            r = int(tone_color[1:3], 16)
            g = int(tone_color[3:5], 16)
            b = int(tone_color[5:7], 16)
            bg_color = f"rgba({r}, {g}, {b}, 0.15)"
            border_color = tone_color
        else:
            bg_color = SURFACE
            border_color = BORDER_IDLE
            
        self.setStyleSheet(f"StatusRowWidget {{ background-color: {bg_color}; border: 1px solid {border_color}; border-radius: 8px; }}")
        
        r = int(tone_color[1:3], 16)
        g = int(tone_color[3:5], 16)
        b = int(tone_color[5:7], 16)
        box_bg = f"rgba({r}, {g}, {b}, 0.22)"
        self.icon_box.setStyleSheet(f"background-color: {box_bg}; border-radius: 6px; border: none;")

class DropArea(QFrame):
    file_dropped = Signal(str)
    clicked = Signal()

    def __init__(self, parent=None):
        ensure_fonts()
        super().__init__(parent)
        self.setAcceptDrops(True)
        self.setCursor(Qt.PointingHandCursor)
        self.setFixedSize(440, 380)
        self.setObjectName("dropArea")
        self.active = False
        self.hover = False
        
        layout = QVBoxLayout(self)
        layout.setAlignment(Qt.AlignCenter)
        layout.setContentsMargins(28, 28, 28, 24)
        layout.setSpacing(0)
        
        # Icon tile
        self.icon_tile = QFrame()
        self.icon_tile.setFixedSize(76, 76)
        tile_layout = QVBoxLayout(self.icon_tile)
        tile_layout.setContentsMargins(0, 0, 0, 0)
        tile_layout.setAlignment(Qt.AlignCenter)
        self.icon_lbl = QLabel(Icons.FILE_VIDEO)
        self.icon_lbl.setAlignment(Qt.AlignCenter)
        self.icon_lbl.setStyleSheet(f"font-family: 'Phosphor'; font-size: 36px; color: {ACCENT_HOVER}; background: transparent; border: none;")
        tile_layout.addWidget(self.icon_lbl)
        
        # Labels
        self.title_label = QLabel("Перетащите видео сюда")
        self.title_label.setStyleSheet(f"color: {TEXT_MAIN}; font-size: 18px; font-weight: bold; background: transparent; border: none;")
        self.title_label.setAlignment(Qt.AlignCenter)
        
        self.subtitle_label = QLabel("или выберите файл с компьютера")
        self.subtitle_label.setStyleSheet(f"color: {TEXT_MUTED}; font-size: 13px; background: transparent; border: none;")
        self.subtitle_label.setAlignment(Qt.AlignCenter)
        
        # Action button
        self.btn = QPushButton("Выбрать видео")
        self.btn.setFixedSize(228, 48)
        self.btn.setStyleSheet(f"""
            QPushButton {{
                background-color: {ACCENT};
                color: #FFFFFF;
                border-radius: 10px;
                font-weight: bold;
                font-size: 14px;
                border: none;
            }}
            QPushButton:hover {{
                background-color: {ACCENT_HOVER};
            }}
            QPushButton:pressed {{
                background-color: {ACCENT_PRESSED};
            }}
        """)
        self.btn.clicked.connect(self.clicked.emit)
        
        # Formats chip
        self.formats_label = QLabel("MOV    /    WEBM    /    MP4")
        self.formats_label.setStyleSheet(f"color: {TEXT_MUTED}; font-size: 11px; font-weight: bold; background: transparent; border: none;")
        self.formats_label.setAlignment(Qt.AlignCenter)
        
        layout.addWidget(self.icon_tile, 0, Qt.AlignCenter)
        layout.addSpacing(18)
        layout.addWidget(self.title_label)
        layout.addSpacing(4)
        layout.addWidget(self.subtitle_label)
        layout.addSpacing(22)
        layout.addWidget(self.btn, 0, Qt.AlignCenter)
        layout.addSpacing(26)
        layout.addWidget(self.formats_label)
        
        self.setStyleSheet("""
            QFrame#dropArea {
                background-color: transparent;
                border: none;
            }
            QLabel {
                background: transparent;
                border: none;
            }
        """)
        self.update_style(False)

    def enterEvent(self, event):
        self.hover = True
        self.update()
        super().enterEvent(event)

    def leaveEvent(self, event):
        self.hover = False
        self.update()
        super().leaveEvent(event)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)
        
        rect = QRectF(0.5, 0.5, self.width() - 1.0, self.height() - 1.0)
        path = QPainterPath()
        path.addRoundedRect(rect, 16.0, 16.0)
        
        bg_color = QColor("#2A1914") if self.active else QColor("#151519")
        painter.fillPath(path, QBrush(bg_color))
        
        border_color = QColor(ACCENT) if self.active else (QColor(BORDER_HOVER) if self.hover else QColor(BORDER_IDLE))
        pen_width = 2.0 if self.active else 1.0
        pen = QPen(border_color, pen_width)
        painter.strokePath(path, pen)

    def update_style(self, active: bool):
        self.active = active
        tile_bg = "#682F18" if active else "#412319"
        self.icon_tile.setStyleSheet(f"""
            background-color: {tile_bg};
            border: 1px solid rgba(255, 62, 5, 0.35);
            border-radius: 16px;
        """)
        if active:
            self.title_label.setText("Отпустите для импорта")
            self.subtitle_label.setText("Файл откроется сразу после загрузки")
        else:
            self.title_label.setText("Перетащите видео сюда")
            self.subtitle_label.setText("или выберите файл с компьютера")
        self.update()

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
            self.update_style(True)
        else:
            event.ignore()

    def dragLeaveEvent(self, event):
        self.update_style(False)

    def dropEvent(self, event):
        self.update_style(False)
        urls = event.mimeData().urls()
        if urls:
            path = urls[0].toLocalFile()
            self.file_dropped.emit(path)

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.clicked.emit()

class GlowCardContainer(QWidget):
    """
    Container widget wrapping DropArea that renders a soft, diffuse ambient glow
    centered strictly underneath DropArea based on the card's local geometry.
    Hierarchy: GlowCardContainer -> DropArea.
    """
    def __init__(self, drop_area: DropArea, parent=None):
        super().__init__(parent)
        self.drop_area = drop_area
        self.drop_area.setParent(self)
        self.setAcceptDrops(True)
        
        self.pad_x = 75
        self.pad_y = 65
        
        card_w = self.drop_area.width()
        card_h = self.drop_area.height()
        self.setFixedSize(card_w + self.pad_x * 2, card_h + self.pad_y * 2)
        
        layout = QVBoxLayout(self)
        layout.setContentsMargins(self.pad_x, self.pad_y, self.pad_x, self.pad_y)
        layout.setSpacing(0)
        layout.addWidget(self.drop_area)
        
        self.setStyleSheet("background: transparent; border: none;")

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)
        
        # Center is strictly and physically the center of the DropArea card
        cx = self.width() / 2.0
        cy = self.height() / 2.0
        rx = self.width() / 2.0
        ry = self.height() / 2.0
        
        painter.save()
        painter.translate(cx, cy)
        painter.scale(1.0, ry / rx)
        
        grad = QRadialGradient(0, 0, rx)
        grad.setColorAt(0.00, QColor(255, 62, 5, 80))
        grad.setColorAt(0.55, QColor(255, 62, 5, 52))
        grad.setColorAt(0.72, QColor(255, 62, 5, 28))
        grad.setColorAt(0.88, QColor(255, 62, 5, 10))
        grad.setColorAt(1.00, QColor(255, 62, 5, 0))
        
        painter.setPen(Qt.NoPen)
        painter.setBrush(QBrush(grad))
        painter.drawEllipse(QPointF(0, 0), rx, rx)
        painter.restore()

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
            self.drop_area.update_style(True)
        else:
            event.ignore()

    def dragLeaveEvent(self, event):
        self.drop_area.update_style(False)

    def dropEvent(self, event):
        self.drop_area.dropEvent(event)

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.drop_area.clicked.emit()

class EditorView(QWidget):
    back_requested = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.doc = None
        self.setObjectName("editorWidget")
        self.setStyleSheet(f"""
            #editorWidget {{
                background-color: {BACK_MAIN};
            }}
            QLabel {{
                border: none;
                background: transparent;
            }}
        """)
        self.setFocusPolicy(Qt.StrongFocus)
        
        root_layout = QVBoxLayout(self)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)
        
        # ─── 1. TOP HEADER TOOLBAR ───────────────────────────────────────────
        self.header_bar = QWidget()
        self.header_bar.setObjectName("headerBar")
        self.header_bar.setFixedHeight(60)
        self.header_bar.setStyleSheet(f"#headerBar {{ background-color: {BACK_HEADER}; border-bottom: 1px solid {BORDER_IDLE}; }}")
        header_layout = QHBoxLayout(self.header_bar)
        header_layout.setContentsMargins(16, 6, 16, 6)
        header_layout.setSpacing(14)
        
        # Logo badge
        self.logo_lbl = QLabel()
        if os.path.exists(LOGO_PATH):
            self.logo_lbl.setPixmap(QPixmap(LOGO_PATH).scaled(32, 32, Qt.KeepAspectRatio, Qt.SmoothTransformation))
        self.logo_lbl.setFixedSize(32, 32)
        header_layout.addWidget(self.logo_lbl)
        
        # Brand label
        brand_layout = QVBoxLayout()
        brand_layout.setSpacing(1)
        brand_title = QLabel("uxlive")
        brand_title.setStyleSheet(f"color: {TEXT_MAIN}; font-size: 14px; font-weight: bold;")
        brand_sub = QLabel("Sticker Studio / Telegram  /  Port by @yoggypub")
        brand_sub.setStyleSheet(f"color: {TEXT_MUTED}; font-size: 11px;")
        brand_layout.addWidget(brand_title)
        brand_layout.addWidget(brand_sub)
        header_layout.addLayout(brand_layout)
        
        # Source chip
        self.source_chip = QFrame()
        self.source_chip.setObjectName("sourceChip")
        self.source_chip.setStyleSheet(f"#sourceChip {{ background-color: {SURFACE}; border: 1px solid {BORDER_IDLE}; border-radius: 8px; }}")
        chip_layout = QVBoxLayout(self.source_chip)
        chip_layout.setContentsMargins(12, 4, 12, 4)
        chip_layout.setSpacing(2)
        self.file_label = QLabel("Файл не выбран")
        self.file_label.setStyleSheet(f"color: {TEXT_MAIN}; font-size: 12px; font-weight: bold;")
        self.file_meta_label = QLabel("—")
        self.file_meta_label.setStyleSheet(f"color: {TEXT_MUTED}; font-size: 11px;")
        chip_layout.addWidget(self.file_label)
        chip_layout.addWidget(self.file_meta_label)
        header_layout.addWidget(self.source_chip)
        
        header_layout.addStretch(1)
        
        # Back & Undo buttons
        self.btn_back = QPushButton("←  Новое видео")
        self.btn_back.setFixedHeight(36)
        self.btn_back.setCursor(Qt.PointingHandCursor)
        self.btn_back.setStyleSheet(f"""
            QPushButton {{
                color: {TEXT_MAIN};
                background-color: transparent;
                border: 1px solid {BORDER_IDLE};
                border-radius: 6px;
                padding: 0 14px;
                font-size: 12px;
            }}
            QPushButton:hover {{
                background-color: {SURFACE};
                border-color: {BORDER_HOVER};
            }}
        """)
        self.btn_back.clicked.connect(self.back_requested.emit)
        
        self.btn_undo = QPushButton("↩  Отменить")
        self.btn_undo.setFixedHeight(36)
        self.btn_undo.setCursor(Qt.PointingHandCursor)
        self.btn_undo.clicked.connect(self.undo)
        
        header_layout.addWidget(self.btn_back)
        header_layout.addWidget(self.btn_undo)
        
        root_layout.addWidget(self.header_bar, 0)
        
        # ─── 2. WORKSPACE (Tool Rail + Main Column + Inspector) ───────────────
        workspace = QWidget()
        workspace_layout = QHBoxLayout(workspace)
        workspace_layout.setContentsMargins(0, 0, 0, 0)
        workspace_layout.setSpacing(0)
        
        # A) Left Tool Rail
        self.tool_rail = QWidget()
        self.tool_rail.setObjectName("toolRail")
        self.tool_rail.setFixedWidth(88)
        self.tool_rail.setStyleSheet(f"#toolRail {{ background-color: {BACK_PANEL}; border-right: 1px solid {BORDER_IDLE}; }}")
        tool_layout = QVBoxLayout(self.tool_rail)
        tool_layout.setContentsMargins(3, 16, 3, 16)
        tool_layout.setSpacing(12)
        tool_layout.setAlignment(Qt.AlignTop | Qt.AlignHCenter)
        
        self.crop_btn = ToolRailButton(Icons.CROP, "Обрезать")
        self.crop_btn.clicked.connect(self.toggle_crop_mode)
        
        self.key_btn = ToolRailButton(Icons.BACKGROUND, "Убрать фон")
        self.key_btn.clicked.connect(self.toggle_key_panel)
        
        tool_layout.addWidget(self.crop_btn)
        tool_layout.addWidget(self.key_btn)
        tool_layout.addStretch(1)
        
        workspace_layout.addWidget(self.tool_rail, 0)
        
        # B) Center Main Column
        center_col = QWidget()
        center_layout = QVBoxLayout(center_col)
        center_layout.setContentsMargins(0, 0, 0, 0)
        center_layout.setSpacing(0)
        
        # Stage (Preview)
        stage_host = QWidget()
        stage_host.setObjectName("stageHost")
        stage_host.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        stage_host.setStyleSheet(f"#stageHost {{ background-color: {STAGE}; }}")
        stage_layout = QVBoxLayout(stage_host)
        stage_layout.setContentsMargins(14, 8, 14, 8)
        stage_layout.setSpacing(4)
        
        stage_header = QHBoxLayout()
        stage_title = QLabel("Предпросмотр")
        stage_title.setStyleSheet(f"color: {TEXT_MAIN}; font-size: 13px; font-weight: bold;")
        self.stage_meta = QLabel("Холст  /  512 × 512")
        self.stage_meta.setStyleSheet(f"color: {TEXT_MUTED}; font-size: 11px;")
        stage_header.addWidget(stage_title)
        stage_header.addStretch(1)
        stage_header.addWidget(self.stage_meta)
        stage_layout.addLayout(stage_header)
        
        self.preview = PreviewWidget()
        self.preview.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.preview.setMinimumSize(100, 100)
        self.preview.crop_changed.connect(self.on_crop_changed)
        self.preview.color_picked.connect(self.on_color_picked)
        stage_layout.addWidget(self.preview, 1)
        
        center_layout.addWidget(stage_host, 1)
        
        # Bottom Bar (Timeline + Play)
        self.bottom_bar = QWidget()
        self.bottom_bar.setObjectName("bottomBar")
        self.bottom_bar.setFixedHeight(120)
        self.bottom_bar.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Fixed)
        self.bottom_bar.setStyleSheet(f"#bottomBar {{ background-color: {SURFACE}; border-top: 1px solid {BORDER_IDLE}; }}")
        bottom_layout = QVBoxLayout(self.bottom_bar)
        bottom_layout.setContentsMargins(16, 8, 16, 10)
        bottom_layout.setSpacing(6)
        
        # Timeline header row
        time_hdr = QHBoxLayout()
        timeline_title = QLabel("Фрагмент")
        timeline_title.setStyleSheet(f"color: {TEXT_MUTED}; font-size: 11px; font-weight: bold;")
        self.time_label = QLabel("0.00 / 0.00")
        self.time_label.setStyleSheet(f"color: {TEXT_MUTED}; font-size: 12px;")
        time_hdr.addWidget(timeline_title)
        time_hdr.addStretch(1)
        time_hdr.addWidget(self.time_label)
        bottom_layout.addLayout(time_hdr)
        
        # Controls row
        ctrl_row = QHBoxLayout()
        ctrl_row.setSpacing(10)
        
        self.play_btn = QPushButton("▶")
        self.play_btn.setFixedSize(42, 42)
        self.play_btn.setStyleSheet(f"""
            QPushButton {{
                font-size: 18px;
                color: {TEXT_MAIN};
                background-color: {ACCENT};
                border-radius: 21px;
                border: none;
            }}
            QPushButton:hover {{
                background-color: {ACCENT_HOVER};
            }}
        """)
        self.play_btn.clicked.connect(self.toggle_play)
        
        self.timeline = TimelineControl()
        self.timeline.seek_requested.connect(self.on_seek)
        self.timeline.cut_changing.connect(self.on_cut_changing)
        self.timeline.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        self.timeline.setMinimumWidth(150)
        
        ctrl_row.addWidget(self.play_btn)
        ctrl_row.addWidget(self.timeline, 1)
        bottom_layout.addLayout(ctrl_row)
        
        center_layout.addWidget(self.bottom_bar, 0)
        workspace_layout.addWidget(center_col, 1)
        
        # C) Right Inspector Panel
        self.inspector = QWidget()
        self.inspector.setObjectName("inspectorPanel")
        self.inspector.setFixedWidth(320)
        self.inspector.setStyleSheet(f"#inspectorPanel {{ background-color: {BACK_PANEL}; border-left: 1px solid {BORDER_IDLE}; }}")
        inspector_layout = QVBoxLayout(self.inspector)
        inspector_layout.setContentsMargins(16, 16, 16, 16)
        inspector_layout.setSpacing(12)
        
        # Inspector title
        self.inspector_title = QLabel("Готовность")
        self.inspector_title.setStyleSheet(f"color: {TEXT_MAIN}; font-size: 17px; font-weight: bold;")
        self.inspector_caption = QLabel("Параметры перед экспортом")
        self.inspector_caption.setStyleSheet(f"color: {TEXT_MUTED}; font-size: 11px;")
        inspector_layout.addWidget(self.inspector_title)
        inspector_layout.addWidget(self.inspector_caption)
        
        # Stacked / Contextual Content
        # Mode 1: Default readiness view
        self.inspector_default = QWidget()
        default_layout = QVBoxLayout(self.inspector_default)
        default_layout.setContentsMargins(0, 4, 0, 4)
        default_layout.setSpacing(10)

        # 1. Readiness Card
        readiness_card = QFrame()
        readiness_card.setObjectName("readinessCard")
        readiness_card.setStyleSheet(f"""
            #readinessCard {{
                background-color: {SURFACE_RAISED};
                border: 1px solid {BORDER_IDLE};
                border-radius: 12px;
            }}
            QLabel {{
                border: none;
                background: transparent;
            }}
        """)
        rc_layout = QVBoxLayout(readiness_card)
        rc_layout.setContentsMargins(12, 12, 12, 12)
        rc_layout.setSpacing(8)
        
        self.readiness_status_row = StatusRowWidget()
        self.readiness_status_row.set_status("Статус", "проверка", Icons.CHECK, TEXT_MUTED, strong=True)
        
        self.readiness_title = QLabel("Подготовка проекта")
        self.readiness_title.setStyleSheet(f"color: {TEXT_MAIN}; font-size: 13px; font-weight: bold;")
        
        self.readiness_detail = QLabel("Проверяю параметры исходника")
        self.readiness_detail.setStyleSheet(f"color: {TEXT_MUTED}; font-size: 11px;")
        self.readiness_detail.setWordWrap(True)
        
        rc_layout.addWidget(self.readiness_status_row)
        rc_layout.addWidget(self.readiness_title)
        rc_layout.addWidget(self.readiness_detail)
        default_layout.addWidget(readiness_card)
        
        # 2. Check Rows
        self.crop_status_row = StatusRowWidget()
        self.crop_status_row.set_status("Квадрат 1:1", "проверка", Icons.CROP, TEXT_MUTED)
        
        self.key_status_row = StatusRowWidget()
        self.key_status_row.set_status("Фон", "без обработки", Icons.BACKGROUND, TEXT_MUTED)
        
        self.duration_status_row = QLabel()
        self.duration_status_row.hide()
        
        default_layout.addWidget(self.crop_status_row)
        default_layout.addWidget(self.key_status_row)
        
        # 3. Source Info Box
        source_card = QFrame()
        source_card.setObjectName("sourceCard")
        source_card.setStyleSheet(f"""
            #sourceCard {{
                background-color: {SURFACE};
                border: 1px solid {BORDER_IDLE};
                border-radius: 8px;
            }}
            QLabel {{
                border: none;
                background: transparent;
            }}
        """)
        sc_layout = QVBoxLayout(source_card)
        sc_layout.setContentsMargins(14, 10, 14, 10)
        sc_layout.setSpacing(4)
        sc_title = QLabel("Исходник")
        sc_title.setStyleSheet(f"color: {TEXT_MAIN}; font-size: 12px; font-weight: bold;")
        self.source_info_label = QLabel("—")
        self.source_info_label.setStyleSheet(f"color: {TEXT_MUTED}; font-size: 11px;")
        sc_layout.addWidget(sc_title)
        sc_layout.addWidget(self.source_info_label)
        default_layout.addWidget(source_card)
        
        default_layout.addStretch(1)
        inspector_layout.addWidget(self.inspector_default, 1)
        
        # Mode 2: Crop Actions view
        self.crop_actions = QWidget()
        crop_layout = QVBoxLayout(self.crop_actions)
        crop_layout.setContentsMargins(0, 4, 0, 4)
        crop_layout.setSpacing(12)
        
        crop_hint_card = QFrame()
        crop_hint_card.setObjectName("cropHintCard")
        crop_hint_card.setStyleSheet(f"""
            #cropHintCard {{
                background-color: {SURFACE};
                border: 1px solid {BORDER_IDLE};
                border-radius: 8px;
            }}
            QLabel {{
                border: none;
                background: transparent;
            }}
        """)
        ch_layout = QVBoxLayout(crop_hint_card)
        ch_layout.setContentsMargins(14, 14, 14, 14)
        ch_layout.setSpacing(8)
        ch_title = QLabel("Кадрирование")
        ch_title.setStyleSheet(f"color: {TEXT_MAIN}; font-size: 12px; font-weight: bold;")
        ch_desc = QLabel("Выделите квадратную зону для стикера 512 × 512.\n\nПеретаскивайте рамку за центр или меняйте размер за угловые маркеры.")
        ch_desc.setStyleSheet(f"color: {TEXT_MUTED}; font-size: 11px;")
        ch_desc.setWordWrap(True)
        ch_layout.addWidget(ch_title)
        ch_layout.addWidget(ch_desc)
        crop_layout.addWidget(crop_hint_card)
        
        crop_btns = QHBoxLayout()
        crop_btns.setSpacing(8)
        self.apply_btn = QPushButton("Применить")
        self.apply_btn.setFixedHeight(40)
        self.apply_btn.setMinimumWidth(100)
        self.apply_btn.setStyleSheet(f"color: {TEXT_MAIN}; background-color: {ACCENT}; border-radius: 6px; font-weight: bold; font-size: 12px; border: none;")
        self.apply_btn.clicked.connect(self.apply_crop)
        
        self.cancel_btn = QPushButton("Отмена")
        self.cancel_btn.setFixedHeight(40)
        self.cancel_btn.setMinimumWidth(80)
        self.cancel_btn.setStyleSheet(f"color: {TEXT_MAIN}; background-color: {BORDER_IDLE}; border-radius: 6px; font-size: 12px; border: none;")
        self.cancel_btn.clicked.connect(self.cancel_crop)
        
        crop_btns.addWidget(self.apply_btn)
        crop_btns.addWidget(self.cancel_btn)
        crop_layout.addLayout(crop_btns)
        crop_layout.addStretch(1)
        
        inspector_layout.addWidget(self.crop_actions, 1)
        self.crop_actions.hide()
        
        # Mode 3: Key Panel view
        self.key_panel = KeyPanel()
        self.key_panel.hide()
        self.key_panel.apply_requested.connect(self.apply_key)
        self.key_panel.cancel_requested.connect(self.cancel_key)
        self.key_panel.params_changed.connect(self.on_key_params_changed)
        self.key_panel.pick_toggled.connect(self.on_pick_toggled)
        inspector_layout.addWidget(self.key_panel, 1)
        
        # Bottom Export Area in Inspector
        self.status_label = QLabel("")
        self.status_label.setStyleSheet(f"color: {TEXT_MUTED}; font-size: 11px;")
        self.status_label.setWordWrap(True)
        inspector_layout.addWidget(self.status_label)
        
        self.export_btn = QPushButton("Экспортировать WebM")
        self.export_btn.setFixedHeight(48)
        self.export_btn.setMinimumWidth(180)
        self.export_btn.setCursor(Qt.PointingHandCursor)
        self.export_btn.setStyleSheet(f"""
            QPushButton {{
                color: #FFFFFF;
                background-color: {ACCENT};
                border-radius: 8px;
                font-weight: bold;
                font-size: 13px;
                border: none;
            }}
            QPushButton:hover {{
                background-color: {ACCENT_HOVER};
            }}
            QPushButton:pressed {{
                background-color: {ACCENT_PRESSED};
            }}
        """)
        self.export_btn.clicked.connect(self.request_export)
        inspector_layout.addWidget(self.export_btn)
        
        workspace_layout.addWidget(self.inspector, 0)
        root_layout.addWidget(workspace, 1)
        
        # Export Shortcut
        self.export_shortcut = QShortcut(QKeySequence("Ctrl+E"), self)
        self.export_shortcut.activated.connect(self.request_export)
        self.export_shortcut.setEnabled(False)

        # Undo Shortcut (Cmd+Z / Ctrl+Z)
        self.undo_shortcut = QShortcut(QKeySequence.StandardKey.Undo, self)
        self.undo_shortcut.activated.connect(self.undo)
        
        self.export_worker = ExportWorker()
        self.export_worker.progress.connect(self.on_export_progress)
        self.export_worker.finished.connect(self.on_export_finished)
        self.exporting = False
        
        # Playback & Renderer state
        self.playback_timer = QTimer(self)
        self.playback_timer.timeout.connect(self.on_playback_tick)
        self.playing = False
        self.play_start_real = 0.0
        self.play_start_pos = 0.0
        
        self.editing_key = None
        self.ffmpeg_path = ""
        
        self.exact_timer = QTimer(self)
        self.exact_timer.setSingleShot(True)
        self.exact_timer.timeout.connect(self.request_exact_preview)
        
        self.cache_timer = QTimer(self)
        self.cache_timer.setSingleShot(True)
        self.cache_timer.timeout.connect(self.request_playback_cache)
        
        self.exact_revision = 0
        self.cache_revision = 0
        
        self.exact_renderer = PreviewRenderer()
        self.exact_renderer.exact_completed.connect(self.on_exact_completed)
        
        self.playback_renderer = PreviewRenderer()
        self.playback_renderer.cache_completed.connect(self.on_cache_completed)
        
        self.cache_dir = ""
        self.cache_fps = 30.0
        self.cache_frames = []

    def clear_cache(self):
        self.cache_revision += 1
        self.playback_renderer.cancel_pending()
        if self.cache_dir:
            import shutil
            shutil.rmtree(self.cache_dir, ignore_errors=True)
            self.cache_dir = ""
        self.cache_frames = []
        self.preview.set_playback_image(None)

    def get_ffmpeg(self):
        if not self.ffmpeg_path:
            from ffmpeg_utils import Ffmpeg
            self.ffmpeg_path = Ffmpeg.find()
        return self.ffmpeg_path

    def schedule_exact(self, ms=160):
        if self.playing:
            return
        self.exact_revision += 1
        self.exact_timer.start(max(1, ms))
        self.exact_renderer.cancel_pending()
        self.preview.clear_exact()

    def cancel_exact(self, clear=True):
        self.exact_revision += 1
        self.exact_timer.stop()
        self.exact_renderer.cancel_pending()
        if clear:
            self.preview.clear_exact()

    def request_exact_preview(self):
        if not self.doc or self.playing or self.preview.crop_mode:
            return
        ffmpeg = self.get_ffmpeg()
        if not ffmpeg:
            return
        
        req = ExactPreviewRequest()
        req.revision = self.exact_revision
        req.ffmpeg_path = ffmpeg
        req.source_path = self.doc.source_path
        req.info = self.doc.info
        req.time = self.timeline.position
        req.state = copy.deepcopy(self.doc.state)
        if self.preview.active_key:
            req.state.key = copy.deepcopy(self.preview.active_key)
        else:
            req.state.key = KeySettings()
        
        self.exact_renderer.request_exact(req)

    def on_exact_completed(self, rev, qimg):
        if rev != self.exact_revision or not self.doc or self.playing or self.preview.crop_mode:
            return
        self.preview.set_exact_image(qimg)

    def schedule_cache(self, ms=360):
        self.cache_revision += 1
        self.cache_timer.start(max(1, ms))
        self.playback_renderer.cancel_pending()

    def request_playback_cache(self):
        if not self.doc:
            return
        ffmpeg = self.get_ffmpeg()
        if not ffmpeg:
            return
        
        req = PlaybackCacheRequest()
        req.revision = self.cache_revision
        req.ffmpeg_path = ffmpeg
        req.source_path = self.doc.source_path
        req.info = self.doc.info
        req.state = copy.deepcopy(self.doc.state)
        if self.preview.active_key:
            req.state.key = copy.deepcopy(self.preview.active_key)
        else:
            req.state.key = KeySettings()
            
        self.playback_renderer.request_cache(req)

    def on_cache_completed(self, rev, folder_path, fps):
        if rev != self.cache_revision:
            import shutil
            shutil.rmtree(folder_path, ignore_errors=True)
            return
        
        if self.cache_dir and self.cache_dir != folder_path:
            import shutil
            shutil.rmtree(self.cache_dir, ignore_errors=True)
            
        self.cache_dir = folder_path
        self.cache_fps = fps
        self.cache_frames = sorted([
            os.path.join(folder_path, f)
            for f in os.listdir(folder_path)
            if f.startswith("f") and (f.endswith(".bmp") or f.endswith(".png"))
        ])
        if self.doc:
            self.show_frame(self.timeline.position)

    def toggle_key_panel(self):
        if not self.doc:
            return
        if self.preview.crop_mode:
            self.cancel_crop()
        
        if self.doc.state.key and self.doc.state.key.enabled:
            self.editing_key = copy.deepcopy(self.doc.state.key)
        else:
            self.editing_key = KeySettings()
            
        self.editing_key.enabled = True
        
        self.key_panel.set_gain(self.editing_key.gain)
        self.key_panel.set_shrink(self.editing_key.shrink_grow)
        self.key_panel.set_color(self.editing_key.screen_color_r, self.editing_key.screen_color_g, self.editing_key.screen_color_b)
        
        self.inspector_title.setText("Chroma Key")
        self.inspector_caption.setText("Удаление однотонного фона")
        self.inspector_default.hide()
        self.crop_actions.hide()
        self.export_btn.hide()
        self.key_panel.show()
        
        self.preview.active_key = self.editing_key
        self.preview.bump_key()
        
        self.schedule_exact(120)
        self.schedule_cache(320)

    def apply_key(self):
        self.doc.push_undo()
        self.doc.state.key = copy.deepcopy(self.editing_key)
        self.key_panel.hide()
        self.inspector_default.show()
        self.export_btn.show()
        self.inspector_title.setText("Готовность")
        self.inspector_caption.setText("Параметры перед экспортом")
        self.preview.pick_mode = False
        self.key_panel.pick_btn.setChecked(False)
        self.update_export_state()
        self.clear_cache()
        self.schedule_exact(1)
        self.schedule_cache(1)

    def cancel_key(self):
        self.key_panel.hide()
        self.inspector_default.show()
        self.export_btn.show()
        self.inspector_title.setText("Готовность")
        self.inspector_caption.setText("Параметры перед экспортом")
        self.preview.pick_mode = False
        self.key_panel.pick_btn.setChecked(False)
        self.preview.active_key = self.doc.state.key
        self.preview.bump_key()
        self.clear_cache()
        self.schedule_exact(1)
        self.schedule_cache(1)
        self.update_export_state()

    def on_key_params_changed(self):
        if not self.editing_key:
            return
        self.editing_key.gain = self.key_panel.get_gain()
        self.editing_key.shrink_grow = self.key_panel.get_shrink()
        self.preview.bump_key()
        self.schedule_exact(160)
        self.schedule_cache(360)

    def on_pick_toggled(self, state):
        self.preview.pick_mode = state
        if state:
            if self.playing:
                self.toggle_play()
            self.cancel_exact(True)
        else:
            self.schedule_exact(120)

    def on_color_picked(self, r, g, b):
        self.preview.pick_mode = False
        self.key_panel.pick_btn.setChecked(False)
        if not self.editing_key:
            return
        
        self.editing_key.screen_color_r = r
        self.editing_key.screen_color_g = g
        self.editing_key.screen_color_b = b
        
        self.key_panel.set_color(r, g, b)
        self.preview.bump_key()
        self.schedule_exact(160)
        self.schedule_cache(360)

    def toggle_crop_mode(self):
        if not self.doc:
            return
        if self.playing:
            self.toggle_play()
        self.cancel_exact(True)
        self.crop_btn.hide()
        self.inspector_default.hide()
        self.key_panel.hide()
        self.export_btn.hide()
        self.crop_actions.show()
        self.inspector_title.setText("Кадрирование")
        self.inspector_caption.setText("Квадратная зона для Telegram")
        self.preview.enter_crop_mode()

    def apply_crop(self):
        self.clear_cache()
        self.preview.apply_crop()
        self.crop_actions.hide()
        self.crop_btn.show()
        self.inspector_default.show()
        self.export_btn.show()
        self.inspector_title.setText("Готовность")
        self.inspector_caption.setText("Параметры перед экспортом")
        self.update_export_state()
        self.schedule_exact(1)
        self.schedule_cache(1)

    def cancel_crop(self):
        self.clear_cache()
        self.preview.cancel_crop()
        self.crop_actions.hide()
        self.crop_btn.show()
        self.inspector_default.show()
        self.export_btn.show()
        self.inspector_title.setText("Готовность")
        self.inspector_caption.setText("Параметры перед экспортом")
        self.update_export_state()
        self.schedule_exact(1)
        self.schedule_cache(1)

    def on_crop_changed(self):
        self.show_frame(self.timeline.position)
        self.update_export_state()
        
    def undo(self):
        if self.key_panel.isVisible():
            self.cancel_key()
            return
        if self.doc and self.doc.undo():
            self.clear_cache()
            self.preview.active_key = self.doc.state.key
            self.preview.bump_key()
            self.update_export_state()
            self.show_frame(self.timeline.position)
            self.timeline.set_position(self.timeline.position)
            self.schedule_exact(1)
            self.schedule_cache(1)

    def update_undo_state(self):
        can_undo = bool(self.doc and self.doc.undo_stack)
        self.btn_undo.setEnabled(can_undo)
        if can_undo:
            self.btn_undo.setStyleSheet(f"""
                QPushButton {{
                    color: {TEXT_MAIN};
                    background-color: {SURFACE};
                    border: 1px solid {BORDER_IDLE};
                    border-radius: 6px;
                    padding: 0 14px;
                    font-size: 12px;
                }}
                QPushButton:hover {{
                    border-color: {BORDER_HOVER};
                    background-color: {SURFACE_RAISED};
                }}
            """)
        else:
            self.btn_undo.setStyleSheet(f"""
                QPushButton {{
                    color: #53525B;
                    background-color: transparent;
                    border: 1px solid #222228;
                    border-radius: 6px;
                    padding: 0 14px;
                    font-size: 12px;
                }}
            """)

    def update_export_state(self):
        if not self.doc:
            return
            
        self.update_undo_state()
        
        blocked = (self.doc.info.width > 512 or self.doc.info.height > 512) and self.doc.state.crop_rect is None
        crop_applied = self.doc.state.crop_rect is not None
        
        # 1. Readiness Card
        if blocked:
            self.readiness_status_row.set_status("Статус", "нужна обрезка", Icons.LOCK, WARN_COLOR, strong=True)
            self.readiness_title.setText("Остался один шаг")
            self.readiness_detail.setText("Выберите квадрат 1:1 для стикера.")
        else:
            self.readiness_status_row.set_status("Статус", "можно экспортировать", Icons.CHECK, OK_COLOR, strong=True)
            self.readiness_title.setText("Все проверки пройдены")
            self.readiness_detail.setText("WebM будет собран под лимит 256 КБ.")
            
        # 2. Check Rows
        if crop_applied:
            self.crop_status_row.set_status("Квадрат 1:1", "выбран", Icons.CHECK, OK_COLOR)
        elif blocked:
            self.crop_status_row.set_status("Квадрат 1:1", "обязателен", Icons.CROP, WARN_COLOR)
        else:
            self.crop_status_row.set_status("Квадрат 1:1", "не требуется", Icons.CROP, TEXT_MUTED)
            
        if self.doc.source_has_alpha:
            self.key_status_row.set_status("Альфа-канал", "сохранится", Icons.CHECK, OK_COLOR)
        elif self.doc.state.key and self.doc.state.key.enabled:
            self.key_status_row.set_status("Фон", "удалён", Icons.CHECK, OK_COLOR)
        else:
            self.key_status_row.set_status("Фон", "без обработки", Icons.BACKGROUND, TEXT_MUTED)
            
        # 3. Canvas & Source Meta
        if crop_applied:
            self.stage_meta.setText("Холст  /  512 × 512")
        else:
            self.stage_meta.setText(f"Холст  /  {self.doc.info.width} × {self.doc.info.height}")
            
        dur = max(0.1, self.doc.state.cut_end - self.doc.state.cut_start)
        fps_str = f"{self.doc.info.fps:.0f} fps" if self.doc.info.fps > 0 else "fps: нет данных"
        self.source_info_label.setText(f"{self.doc.info.width} × {self.doc.info.height}  /  {dur:.1f} с  /  {fps_str}")
        self.duration_status_row.setText(f"• Длительность: {dur:.1f} с (лимит {int(self.doc.MAX_CUT_SECONDS)} с)")
        
        # 4. Tool buttons state
        self.crop_btn.setChecked(crop_applied)
        self.key_btn.setChecked(bool(self.doc.state.key and self.doc.state.key.enabled))
        
        # 5. Export button & Status hint
        if not self.exporting:
            if blocked:
                self.status_label.setText("Обрезка обязательна: исходник больше 512 px.")
                self.status_label.setStyleSheet(f"color: {WARN_COLOR}; font-size: 11px;")
                self.export_btn.setText("Сначала обрезать кадр")
                self.export_btn.setEnabled(False)
                self.export_shortcut.setEnabled(False)
                self.export_btn.setStyleSheet(f"""
                    QPushButton {{
                        color: {TEXT_MUTED};
                        background-color: {SURFACE};
                        border: 1px solid {BORDER_IDLE};
                        border-radius: 8px;
                        font-weight: bold;
                        font-size: 13px;
                    }}
                """)
            else:
                self.status_label.setText("Готово к экспорту. Результат появится рядом с исходником.")
                self.status_label.setStyleSheet(f"color: {TEXT_MUTED}; font-size: 11px;")
                self.export_btn.setText("Экспортировать WebM")
                self.export_btn.setEnabled(True)
                self.export_shortcut.setEnabled(True)
                self.export_btn.setStyleSheet(f"""
                    QPushButton {{
                        color: #FFFFFF;
                        background-color: {ACCENT};
                        border-radius: 8px;
                        font-weight: bold;
                        font-size: 13px;
                        border: none;
                    }}
                    QPushButton:hover {{
                        background-color: {ACCENT_HOVER};
                    }}
                    QPushButton:pressed {{
                        background-color: {ACCENT_PRESSED};
                    }}
                """)

    def request_export(self):
        if not self.doc or self.exporting or not self.export_btn.isEnabled():
            return
        
        if (self.doc.info.width > 512 or self.doc.info.height > 512) and self.doc.state.crop_rect is None:
            return
            
        snapshot = copy.deepcopy(self.doc.state)
        
        if self.doc.info.fps > 31:
            reply = QMessageBox.question(
                self, 'Высокая частота кадров',
                f'У видео {self.doc.info.fps} fps, это выше лимита Telegram (30). Telegram может отклонить такой стикер. Пересчитать видео в 30 fps?',
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.Yes
            )
            if reply == QMessageBox.StandardButton.Yes:
                snapshot.fps30 = True
            else:
                snapshot.fps30 = False
                
        self.exporting = True
        self.export_btn.setEnabled(False)
        self.export_shortcut.setEnabled(False)
        self.export_btn.setText("Экспортирую...")
        
        ffmpeg = self.get_ffmpeg()
        if not ffmpeg:
            self.exporting = False
            self.update_export_state()
            return
            
        base, _ = os.path.splitext(self.doc.source_path)
        out_path = f"{base}_sticker.webm"
        
        req = ExportRequest(
            ffmpeg,
            self.doc.source_path,
            self.doc.info,
            self.doc.source_has_alpha,
            out_path,
            snapshot
        )
        self.export_worker.start_export(req)
        
    def on_export_progress(self, msg):
        if self.exporting:
            self.export_btn.setText(msg)
            self.status_label.setText(msg)
            
    def on_export_finished(self, res: ExportResult):
        self.exporting = False
        self.update_export_state()
        
        if not res.ok:
            self.status_label.setText(f"✗ Ошибка: {res.error}")
            QMessageBox.critical(self, "Ошибка экспорта", f"✗ {res.error}")
        else:
            kb = res.size // 1024
            alpha_str = "с альфой" if res.alpha_in_output else "без альфы"
            msg = f"✓ Готово → {os.path.basename(res.output_path)} ({kb} КБ, {alpha_str})"
            if res.fps_warning:
                msg += "\n\nЧастота выше 30 fps, Telegram может отклонить файл."
            self.status_label.setText(msg)
            QMessageBox.information(self, "Экспорт завершён", msg)

    def load_doc(self, doc):
        self.clear_cache()
        self.doc = doc
        self.timeline.set_doc(doc)
        self.preview.active_key = doc.state.key
        self.preview.bump_key()
        self.set_position(doc.state.cut_start)
        self.setFocus()
        
        # Update header source chip
        filename = os.path.basename(doc.source_path) if doc.source_path else "video"
        self.file_label.setText(filename)
        fps_str = f"{doc.info.fps:.0f} fps" if doc.info.fps > 0 else "fps: нет данных"
        self.file_meta_label.setText(f"{doc.info.width} × {doc.info.height}  /  {doc.info.duration:.1f} с  /  {fps_str}")
        self.update_undo_state()
        
        self.update_export_state()
        self.schedule_exact(1)
        self.schedule_cache(1)

    def set_position(self, t):
        if not self.doc:
            return
        t = max(self.doc.state.cut_start, min(self.doc.state.cut_end, t))
        self.timeline.set_position(t)
        self.show_frame(t)
        
        total = self.doc.state.cut_end - self.doc.state.cut_start
        current = t - self.doc.state.cut_start
        self.time_label.setText(f"{current:.2f} / {total:.2f}")

    def show_frame(self, t):
        if not self.doc or not self.doc.frames:
            return
        
        if self.cache_dir and self.cache_frames:
            dt = t - self.doc.state.cut_start
            frame_idx = int(round(dt * self.cache_fps))
            frame_idx = max(0, min(len(self.cache_frames) - 1, frame_idx))
            fpath = self.cache_frames[frame_idx]
            if os.path.exists(fpath):
                qimg = QImage(fpath)
                if not qimg.isNull():
                    self.preview.set_playback_image(qimg)
                    self.preview.set_frame(self.doc, self.preview.pixmap, frame_idx)
                    return
                        
        self.preview.set_playback_image(None)
        
        frame_idx = int(t * self.doc.preview_fps)
        frame_idx = max(0, min(len(self.doc.frames) - 1, frame_idx))
        
        byte_arr = QByteArray(self.doc.frames[frame_idx])
        img = QImage.fromData(byte_arr)
        pixmap = QPixmap.fromImage(img)
        self.preview.set_frame(self.doc, pixmap, frame_idx)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if self.doc:
            self.show_frame(self.timeline.position)

    def toggle_play(self):
        if not self.doc:
            return
        if self.playing:
            self.playing = False
            self.play_btn.setText("▶")
            self.playback_timer.stop()
            self.preview.set_playing(False)
            self.schedule_exact(80)
        else:
            if not self.cache_dir and self.cache_timer.isActive():
                self.cache_timer.stop()
                self.request_playback_cache()
            self.playing = True
            self.play_btn.setText("⏸")
            self.play_start_real = time.monotonic()
            self.play_start_pos = self.timeline.position
            if self.play_start_pos >= self.doc.state.cut_end - 0.01:
                self.play_start_pos = self.doc.state.cut_start
            self.playback_timer.start(1000 // int(self.doc.preview_fps))
            self.cancel_exact(True)
            self.preview.set_playing(True)
            self.show_frame(self.timeline.position)

    def on_playback_tick(self):
        if not self.doc:
            return
        now = time.monotonic()
        elapsed = now - self.play_start_real
        new_pos = self.play_start_pos + elapsed
        
        duration = max(0.01, self.doc.state.cut_end - self.doc.state.cut_start)
        if new_pos >= self.doc.state.cut_end:
            new_pos = self.doc.state.cut_start + (new_pos - self.doc.state.cut_start) % duration
            self.play_start_real = now
            self.play_start_pos = new_pos
            
        self.set_position(new_pos)

    def on_seek(self, t):
        self.set_position(t)
        self.schedule_exact(160)

    def on_cut_changing(self):
        self.set_position(self.timeline.position)
        self.update_export_state()
        self.schedule_exact(160)
        self.schedule_cache(360)

    def keyPressEvent(self, event):
        if event.key() == Qt.Key_Space:
            self.toggle_play()
        elif event.key() == Qt.Key_C:
            self.toggle_crop_mode()
        elif event.key() == Qt.Key_B:
            self.toggle_key_panel()
        elif event.key() == Qt.Key_Z and (event.modifiers() & (Qt.ControlModifier | Qt.MetaModifier)):
            self.undo()
        elif event.key() == Qt.Key_Left:
            if self.doc:
                self.set_position(self.timeline.position - 1.0 / self.doc.preview_fps)
                self.schedule_exact(160)
        elif event.key() == Qt.Key_Right:
            if self.doc:
                self.set_position(self.timeline.position + 1.0 / self.doc.preview_fps)
                self.schedule_exact(160)
        else:
            super().keyPressEvent(event)


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Sticker Studio — Port by @yoggypub")
        self.setMinimumSize(800, 600)
        self.resize(1024, 768)
        self.setStyleSheet(f"""
            QMainWindow {{
                background-color: {BACK_MAIN};
            }}
            QLabel {{
                border: none;
                background: transparent;
            }}
        """)
        
        self.stacked = QStackedWidget()
        self.setCentralWidget(self.stacked)
        self.loader = None
        
        # --- Drop Screen ---
        ensure_fonts()
        self.drop_screen = QWidget()
        self.drop_screen.setStyleSheet(f"background-color: {BACK_MAIN};")
        drop_layout = QVBoxLayout(self.drop_screen)
        drop_layout.setContentsMargins(0, 0, 0, 0)
        drop_layout.setSpacing(0)
        
        # Header
        header_widget = QWidget()
        header_widget.setFixedHeight(58)
        header_widget.setStyleSheet(f"background-color: {BACK_HEADER};")
        header_layout = QHBoxLayout(header_widget)
        header_layout.setContentsMargins(24, 8, 24, 8)
        header_layout.setSpacing(12)
        
        # Logo badge
        logo_lbl = QLabel()
        if os.path.exists(LOGO_PATH):
            logo_lbl.setPixmap(QPixmap(LOGO_PATH).scaled(36, 36, Qt.KeepAspectRatio, Qt.SmoothTransformation))
        logo_lbl.setFixedSize(36, 36)
        header_layout.addWidget(logo_lbl)
        
        # Title & Subtitle
        hdr_titles = QVBoxLayout()
        hdr_titles.setSpacing(1)
        title = QLabel("Sticker Studio")
        title.setStyleSheet(f"color: {TEXT_MAIN}; font-size: 16px; font-weight: bold;")
        caption = QLabel("uxlive / видеостикеры Telegram  /  Port by @yoggypub")
        caption.setStyleSheet(f"color: {TEXT_MUTED}; font-size: 11px;")
        hdr_titles.addWidget(title)
        hdr_titles.addWidget(caption)
        header_layout.addLayout(hdr_titles)
        
        header_layout.addStretch(1)
        
        # Right info
        right_badge = QLabel("Telegram WebM / обработка локально")
        right_badge.setStyleSheet(f"color: {TEXT_MUTED}; font-size: 12px;")
        header_layout.addWidget(right_badge)
        
        drop_layout.addWidget(header_widget)
        
        # Header divider line
        header_divider = QFrame()
        header_divider.setFixedHeight(1)
        header_divider.setStyleSheet(f"background-color: {BORDER_IDLE}; border: none;")
        drop_layout.addWidget(header_divider)
        
        # Center 2-Column Area
        center_container = QWidget()
        center_layout = QHBoxLayout(center_container)
        center_layout.setContentsMargins(28, 16, 28, 16)
        center_layout.setSpacing(36)
        center_layout.setAlignment(Qt.AlignCenter)
        
        # Left Hero Column
        hero_widget = QWidget()
        hero_widget.setMaximumWidth(460)
        hero_layout = QVBoxLayout(hero_widget)
        hero_layout.setAlignment(Qt.AlignVCenter | Qt.AlignLeft)
        hero_layout.setContentsMargins(0, 0, 0, 0)
        hero_layout.setSpacing(0)
        
        hero_title = QLabel("Соберите стикер\nиз любого видео")
        hero_title.setStyleSheet(f"color: {TEXT_MAIN}; font-size: 32px; font-weight: bold;")
        
        hero_desc = QLabel("Точная обрезка, чистый фон и готовый WebM для Telegram.\nВсё локально, без лишних шагов.")
        hero_desc.setStyleSheet(f"color: {TEXT_MUTED}; font-size: 14px;")
        hero_desc.setWordWrap(True)
        
        hero_layout.addWidget(hero_title)
        hero_layout.addSpacing(16)
        hero_layout.addWidget(hero_desc)
        hero_layout.addSpacing(28)
        
        # 3 Benefit Rows
        max_sec = int(getattr(Ffmpeg, 'MAX_CUT_SECONDS', getattr(VideoDoc, 'MAX_CUT_SECONDS', 6)))
        benefits = [
            ("512 × 512", "квадратный холст"),
            (f"До {max_sec} секунд", "точный фрагмент"),
            ("До 256 КБ", "лимит Telegram"),
        ]
        
        for val_text, cap_text in benefits:
            row = QWidget()
            r_lay = QHBoxLayout(row)
            r_lay.setContentsMargins(0, 5, 0, 5)
            r_lay.setSpacing(10)
            
            icon_box = QFrame()
            icon_box.setFixedSize(22, 22)
            icon_box.setStyleSheet(f"background-color: rgba(255, 62, 5, 0.16); border: 1px solid rgba(255, 62, 5, 0.35); border-radius: 11px;")
            ib_lay = QVBoxLayout(icon_box)
            ib_lay.setContentsMargins(0, 0, 0, 0)
            ib_lay.setAlignment(Qt.AlignCenter)
            
            icon_lbl = QLabel(Icons.CHECK)
            icon_lbl.setStyleSheet(f"font-family: 'Phosphor'; font-size: 13px; color: {ACCENT_HOVER}; border: none; background: transparent;")
            ib_lay.addWidget(icon_lbl)
            
            val_lbl = QLabel(val_text)
            val_lbl.setStyleSheet(f"color: {TEXT_MAIN}; font-size: 13px; font-weight: bold; border: none; background: transparent;")
            
            sep_lbl = QLabel("—")
            sep_lbl.setStyleSheet(f"color: {TEXT_MUTED}; font-size: 13px; border: none; background: transparent;")
            
            cap_lbl = QLabel(cap_text)
            cap_lbl.setStyleSheet(f"color: {TEXT_MUTED}; font-size: 13px; border: none; background: transparent;")
            
            r_lay.addWidget(icon_box)
            r_lay.addWidget(val_lbl)
            r_lay.addWidget(sep_lbl)
            r_lay.addWidget(cap_lbl)
            r_lay.addStretch(1)
            hero_layout.addWidget(row)
            
        # Right Drop Area Column
        self.drop_area = DropArea()
        self.drop_area.file_dropped.connect(self.load_video)
        self.drop_area.clicked.connect(self.pick_file)
        self.glow_card_container = GlowCardContainer(self.drop_area)
        
        center_layout.addStretch(1)
        center_layout.addWidget(hero_widget, 0, Qt.AlignVCenter)
        center_layout.addWidget(self.glow_card_container, 0, Qt.AlignVCenter)
        center_layout.addStretch(1)
        
        drop_layout.addStretch(1)
        drop_layout.addWidget(center_container)
        
        # Status / progress label (empty during idle)
        self.status_label = QLabel("")
        self.status_label.setStyleSheet(f"color: {TEXT_MUTED}; font-size: 12px;")
        self.status_label.setAlignment(Qt.AlignCenter)
        drop_layout.addWidget(self.status_label)
        drop_layout.addStretch(1)
        
        self.stacked.addWidget(self.drop_screen)
        
        # --- Editor Screen ---
        self.editor = EditorView()
        self.editor.back_requested.connect(self.show_drop_screen)
        self.stacked.addWidget(self.editor)
        
        # Shortcuts
        open_action = QAction("Open", self)
        open_action.setShortcut(QKeySequence.StandardKey.Open)
        open_action.triggered.connect(self.pick_file)
        self.addAction(open_action)
        
        self.ffmpeg = Ffmpeg.find()
        print(f"[FFMPEG RESOLVED] {self.ffmpeg}", flush=True)
        if not self.ffmpeg:
            self.status_label.setText("⚠ ffmpeg не найден. Положите его рядом с программой.")
            self.status_label.setStyleSheet(f"color: {ACCENT}; font-size: 14px;")

    def show_drop_screen(self):
        if self.editor.playing:
            self.editor.toggle_play()
        self.status_label.setText("")
        self.stacked.setCurrentWidget(self.drop_screen)

    def pick_file(self):
        if self.loader and self.loader.isRunning():
            return
        path, _ = QFileDialog.getOpenFileName(self, "Выберите видео", "", "Видео (*.mov *.webm *.mp4 *.m4v *.avi *.mkv);;Все файлы (*.*)")
        if path:
            self.load_video(path)

    def load_video(self, path: str):
        if not self.ffmpeg:
            return
        if self.loader and self.loader.isRunning():
            return
        
        self.status_label.setText("Открываю видео…")
        self.status_label.setStyleSheet(f"color: {TEXT_MUTED}; font-size: 14px;")
        self.drop_area.setEnabled(False)
        
        if self.editor.doc:
            if self.editor.playing:
                self.editor.toggle_play()
            self.editor.doc = None
            self.editor.preview.set_frame(None, None)
        
        self.loader = LoaderThread(self.ffmpeg, path)
        self.loader.progress.connect(self.on_load_progress)
        self.loader.finished.connect(self.on_load_finished)
        self.loader.start()

    def on_load_progress(self, p, text):
        self.status_label.setText(f"{text} ({p}%)")

    def on_load_finished(self, err, doc):
        self.drop_area.setEnabled(True)
        if err:
            self.status_label.setText(f"✗ {err}")
            self.status_label.setStyleSheet(f"color: {ACCENT}; font-size: 14px;")
        else:
            self.status_label.setText("")
            self.editor.load_doc(doc)
            self.stacked.setCurrentWidget(self.editor)

    def closeEvent(self, event):
        if hasattr(self, 'editor') and self.editor:
            self.editor.clear_cache()
            if hasattr(self.editor, 'exact_renderer') and self.editor.exact_renderer:
                self.editor.exact_renderer.cancel_pending()
            if hasattr(self.editor, 'playback_renderer') and self.editor.playback_renderer:
                self.editor.playback_renderer.cancel_pending()
        super().closeEvent(event)

if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())
