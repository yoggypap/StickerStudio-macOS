import math
from PySide6.QtCore import Qt, Signal, QRect, QRectF, QPoint
from PySide6.QtGui import QPainter, QColor, QPen, QBrush, QImage, QPixmap, QPainterPath
from PySide6.QtWidgets import QWidget

# Theme Colors
BACK_MAIN = "#0B0B0D"
BACK_HEADER = "#18181C"
SURFACE = "#17171B"
ACCENT = "#FF3E05"
ACCENT2 = "#FF7E49"
TEXT_MUTED = "#9F9DA4"
TEXT_SOFT = "#D7D4CF"

class TimelineControl(QWidget):
    seek_requested = Signal(float)
    cut_changing = Signal()
    cut_committed = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumHeight(80)
        self.doc = None
        self.position = 0.0
        
        self.drag_mode = 0 # 0=none, 1=left, 2=right, 3=window, 4=seek
        self.drag_offset = 0.0
        self.pre_drag_start = 0.0
        self.pre_drag_end = 0.0
        
        self.hover_x = -1
        self.strip_pixmap = None
        self.setMouseTracking(True)
        self.setCursor(Qt.PointingHandCursor)

    def set_doc(self, doc):
        self.doc = doc
        self.strip_pixmap = None
        self.update()

    def set_position(self, pos):
        self.position = pos
        self.update()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.strip_pixmap = None

    def time_to_x(self, t):
        if not self.doc or self.doc.info.duration <= 0: return 0
        tr = self.track_rect()
        return tr.left() + int(t / self.doc.info.duration * tr.width())

    def x_to_time(self, x):
        if not self.doc or self.doc.info.duration <= 0: return 0
        tr = self.track_rect()
        p = (x - tr.left()) / tr.width()
        p = max(0.0, min(1.0, p))
        return p * self.doc.info.duration

    def track_rect(self):
        m = 8
        return QRect(m, 26, max(20, self.width() - m * 2), max(12, self.height() - 34))

    def scrub_rect(self):
        m = 8
        return QRect(m, 0, max(20, self.width() - m * 2), 22)

    def _ensure_strip(self, tr: QRect):
        if not self.doc or not self.doc.frames:
            return
        if self.strip_pixmap and self.strip_pixmap.size() == tr.size():
            return
        
        img = QImage(tr.width(), tr.height(), QImage.Format_ARGB32)
        img.fill(QColor(BACK_HEADER))
        
        painter = QPainter(img)
        painter.setRenderHint(QPainter.SmoothPixmapTransform)
        
        th = tr.height()
        tw = max(8, int(th * self.doc.preview_w / max(1, self.doc.preview_h)))
        n = int(math.ceil(tr.width() / tw))
        
        for i in range(n):
            t = (i + 0.5) / n * self.doc.info.duration
            frame_idx = int(t * self.doc.preview_fps)
            frame_idx = max(0, min(len(self.doc.frames) - 1, frame_idx))
            
            f_bytes = self.doc.frames[frame_idx]
            qimg = QImage.fromData(f_bytes)
            if not qimg.isNull():
                dst = QRect(i * tw, 0, tw, th)
                painter.drawImage(dst, qimg)
                
        painter.end()
        self.strip_pixmap = QPixmap.fromImage(img)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        
        if not self.doc:
            return

        tr = self.track_rect()
        sr = self.scrub_rect()
        
        x1 = self.time_to_x(self.doc.state.cut_start)
        x2 = self.time_to_x(self.doc.state.cut_end)
        
        # Scrub rail
        rail_y = sr.top() + 11
        painter.setPen(QPen(QColor(TEXT_MUTED), 1))
        painter.drawLine(sr.left(), rail_y, sr.right(), rail_y)
        
        painter.setPen(QPen(QColor(ACCENT2), 2))
        painter.drawLine(x1, rail_y, x2, rail_y)
        
        # Ticks
        painter.setPen(QPen(QColor(TEXT_MUTED), 1))
        for i in range(9):
            tx = sr.left() + int(i * sr.width() / 8)
            half = 4 if i % 2 == 0 else 2
            painter.drawLine(tx, rail_y - half, tx, rail_y + half)
            
        if self.hover_x >= 0 and self.drag_mode == 0:
            d = 6
            painter.setBrush(QBrush(QColor(TEXT_SOFT)))
            painter.setPen(Qt.NoPen)
            painter.drawEllipse(self.hover_x - d//2, rail_y - d//2, d, d)

        # Filmstrip
        self._ensure_strip(tr)
        
        path = QPainterPath()
        path.addRoundedRect(tr, 6, 6)
        
        painter.save()
        painter.setClipPath(path)
        if self.strip_pixmap:
            painter.drawPixmap(tr.x(), tr.y(), self.strip_pixmap)
            
        # Dim outside
        painter.setBrush(QBrush(QColor(11, 11, 13, 165))) # BACK_MAIN with alpha
        painter.setPen(Qt.NoPen)
        if x1 > tr.left():
            painter.drawRect(tr.left(), tr.top(), x1 - tr.left(), tr.height())
        if x2 < tr.right():
            painter.drawRect(x2, tr.top(), tr.right() - x2, tr.height())
        
        painter.restore()
        
        # Cut Window Frame
        painter.setPen(QPen(QColor(ACCENT), 2))
        painter.setBrush(Qt.NoBrush)
        win_path = QPainterPath()
        win_path.addRoundedRect(QRectF(x1, tr.y(), max(4, x2 - x1), tr.height()), 4, 4)
        painter.drawPath(win_path)
        
        # Handles
        hw = 10
        hh = tr.height() + 10
        for hx in (x1, x2):
            hr = QRectF(hx - hw / 2, tr.y() - 5, hw, hh)
            hp = QPainterPath()
            hp.addRoundedRect(hr, hw/2, hw/2)
            painter.setPen(Qt.NoPen)
            painter.setBrush(QBrush(QColor(ACCENT)))
            painter.drawPath(hp)
            
            # Notches
            painter.setPen(QPen(QColor(255, 255, 255, 190), 1.5))
            cy = tr.y() + tr.height() / 2
            painter.drawLine(int(hx - 2), int(cy - 4), int(hx - 2), int(cy + 4))
            painter.drawLine(int(hx + 2), int(cy - 4), int(hx + 2), int(cy + 4))
            
        # Playhead
        px = self.time_to_x(self.position)
        painter.setPen(QPen(QColor(ACCENT2), 1.5))
        painter.drawLine(px, rail_y, px, tr.bottom() + 2)
        
        knob = 10
        painter.setPen(QPen(QColor(SURFACE), 1))
        painter.setBrush(QBrush(QColor(ACCENT2)))
        painter.drawEllipse(px - knob//2, rail_y - knob//2, knob, knob)

    def mousePressEvent(self, event):
        if not self.doc: return
        x = event.position().x()
        y = event.position().y()
        t = self.x_to_time(x)
        
        self.pre_drag_start = self.doc.state.cut_start
        self.pre_drag_end = self.doc.state.cut_end
        
        x1 = self.time_to_x(self.doc.state.cut_start)
        x2 = self.time_to_x(self.doc.state.cut_end)
        
        tr = self.track_rect()
        hw = 10
        
        if y >= tr.top() - 5 and y <= tr.bottom() + 5:
            if abs(x - x1) <= hw:
                self.drag_mode = 1
            elif abs(x - x2) <= hw:
                self.drag_mode = 2
            elif x > x1 and x < x2:
                self.drag_mode = 3
                self.drag_offset = t - self.doc.state.cut_start
        
        if self.drag_mode == 0:
            self.drag_mode = 4
            self.seek_requested.emit(t)

    def mouseMoveEvent(self, event):
        if not self.doc: return
        x = event.position().x()
        self.hover_x = x
        
        if self.drag_mode == 0:
            self.update()
            return
            
        t = self.x_to_time(x)
        
        if self.drag_mode == 4:
            self.seek_requested.emit(t)
        elif self.drag_mode == 3:
            dur = self.pre_drag_end - self.pre_drag_start
            new_start = t - self.drag_offset
            new_start = max(0.0, min(self.doc.info.duration - dur, new_start))
            self.doc.state.cut_start = new_start
            self.doc.state.cut_end = new_start + dur
            self.cut_changing.emit()
            self.update()
        elif self.drag_mode == 1:
            dur = self.doc.state.cut_end - t
            if dur > self.doc.MAX_CUT_SECONDS: t = self.doc.state.cut_end - self.doc.MAX_CUT_SECONDS
            if dur < self.doc.MIN_CUT_SECONDS: t = self.doc.state.cut_end - self.doc.MIN_CUT_SECONDS
            self.doc.state.cut_start = max(0.0, t)
            self.cut_changing.emit()
            self.update()
        elif self.drag_mode == 2:
            dur = t - self.doc.state.cut_start
            if dur > self.doc.MAX_CUT_SECONDS: t = self.doc.state.cut_start + self.doc.MAX_CUT_SECONDS
            if dur < self.doc.MIN_CUT_SECONDS: t = self.doc.state.cut_start + self.doc.MIN_CUT_SECONDS
            self.doc.state.cut_end = min(self.doc.info.duration, t)
            self.cut_changing.emit()
            self.update()

    def mouseReleaseEvent(self, event):
        if self.drag_mode in (1, 2, 3):
            self.cut_committed.emit()
        self.drag_mode = 0
        self.update()
