import copy
from PIL import Image

from PySide6.QtCore import Qt, QRect, QRectF, QPointF, QSize, Signal
from PySide6.QtGui import QPainter, QColor, QPen, QBrush, QPixmap, QImage
from PySide6.QtWidgets import QWidget
from chroma_key import ChromaKey

class PreviewWidget(QWidget):
    crop_changed = Signal()
    color_picked = Signal(int, int, int)
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.doc = None
        self.pixmap = None
        self.playing = False
        
        self.crop_mode = False
        self.crop_sel = QRectF() # In PREVIEW coordinates
        
        self.drag_mode = -1
        self.drag_anchor = QPointF()
        self.drag_offset = QPointF()
        
        self.frame_idx = 0
        self.active_key = None
        self.key_version = 0
        self.keyed_idx = -1
        self.keyed_version = -1
        self.keyed_pixmap = None
        
        self.exact_pixmap = None
        self.playback_pixmap = None
        self._pick_mode = False
        
        self.setMouseTracking(True)

    @property
    def pick_mode(self) -> bool:
        return self._pick_mode

    @pick_mode.setter
    def pick_mode(self, val: bool):
        self._pick_mode = bool(val)
        if self._pick_mode:
            self.setCursor(Qt.CrossCursor)
        else:
            self.unsetCursor()
        self.update()

    def sizeHint(self):
        return QSize(400, 300)

    def minimumSizeHint(self):
        return QSize(100, 100)

    def set_frame(self, doc, pixmap, frame_idx=0):
        self.doc = doc
        self.pixmap = pixmap
        self.frame_idx = frame_idx
        self.update()

    def set_exact_image(self, qimg: QImage):
        if not self.playing:
            self.exact_pixmap = QPixmap.fromImage(qimg)
            self.update()

    def clear_exact(self):
        self.exact_pixmap = None
        self.update()

    def set_playing(self, val: bool):
        self.playing = val
        if val:
            self.clear_exact()
        self.update()

    def set_playback_image(self, qimg: QImage):
        if qimg is None:
            self.playback_pixmap = None
        else:
            self.playback_pixmap = QPixmap.fromImage(qimg)
        self.update()

    def bump_key(self):
        self.key_version += 1
        self.update()

    def current_pixmap(self):
        if not self.pixmap:
            return None
        if self.pick_mode:
            return self.pixmap
        if not self.active_key or not getattr(self.active_key, 'enabled', False):
            return self.pixmap
            
        if self.keyed_idx != self.frame_idx or self.keyed_version != self.key_version:
            img = self.pixmap.toImage()
            if img.format() != QImage.Format_RGBA8888:
                img = img.convertToFormat(QImage.Format_RGBA8888)
                
            w = img.width()
            h = img.height()
            ptr = img.bits()
            pil_img = Image.frombytes("RGBA", (w, h), bytes(ptr))
            keyed = ChromaKey.apply(pil_img, self.active_key)
            
            res_img = QImage(keyed.tobytes("raw", "RGBA"), w, h, QImage.Format_RGBA8888)
            self.keyed_pixmap = QPixmap.fromImage(res_img)
            self.keyed_idx = self.frame_idx
            self.keyed_version = self.key_version
            
        return self.keyed_pixmap

    def enter_crop_mode(self):
        if not self.doc:
            return
        self.crop_mode = True
        self.clear_exact()
        if self.doc.state.crop_rect:
            self.crop_sel = self.original_to_preview(self.doc.state.crop_rect)
        else:
            s = min(self.doc.preview_w, self.doc.preview_h)
            self.crop_sel = QRectF((self.doc.preview_w - s) / 2.0, (self.doc.preview_h - s) / 2.0, s, s)
        self.update()

    def apply_crop(self):
        if not self.doc:
            return
        self.doc.push_undo()
        self.doc.state.crop_rect = self.preview_to_original(self.crop_sel)
        self.crop_mode = False
        self.crop_changed.emit()
        self.update()

    def cancel_crop(self):
        self.crop_mode = False
        self.update()

    def original_to_preview(self, rect_tuple):
        scale = self.doc.preview_w / float(self.doc.info.width)
        return QRectF(rect_tuple[0] * scale, rect_tuple[1] * scale, rect_tuple[2] * scale, rect_tuple[3] * scale)

    def preview_to_original(self, rect: QRectF):
        scale = float(self.doc.info.width) / self.doc.preview_w
        s = int(round(rect.width() * scale))
        return (int(round(rect.x() * scale)), int(round(rect.y() * scale)), s, s)

    def content_size(self):
        if not self.doc:
            if self.pixmap:
                return self.pixmap.size()
            return QSize(4, 3)
            
        use_exact = not self.crop_mode and not self.playing and not self.pick_mode and self.exact_pixmap is not None
        use_playback = not use_exact and not self.crop_mode and not self.pick_mode and self.playback_pixmap is not None
        
        if use_exact:
            return self.exact_pixmap.size()
        if use_playback:
            return self.playback_pixmap.size()
            
        if not self.crop_mode and self.doc.state.crop_rect:
            # Crop is applied, so displayed content is a square
            s = int(round(self.doc.state.crop_rect[2] * self.doc.preview_w / float(self.doc.info.width)))
            return QSize(max(2, s), max(2, s))
            
        return QSize(self.doc.preview_w, self.doc.preview_h)

    def get_image_rect(self):
        c = self.content_size()
        if c.width() <= 0 or c.height() <= 0:
            return QRectF()
            
        widget_ar = self.width() / float(max(1, self.height()))
        img_ar = c.width() / float(max(1, c.height()))
        
        if img_ar > widget_ar:
            w = float(self.width())
            h = w / img_ar
            x = 0.0
            y = (self.height() - h) / 2.0
        else:
            h = float(self.height())
            w = h * img_ar
            y = 0.0
            x = (self.width() - w) / 2.0
            
        return QRectF(x, y, w, h)

    def preview_to_widget(self, rect: QRectF, img_rect: QRectF):
        scale = img_rect.width() / float(self.doc.preview_w)
        return QRectF(img_rect.x() + rect.x() * scale, img_rect.y() + rect.y() * scale, 
                      rect.width() * scale, rect.height() * scale)

    def widget_to_preview(self, point: QPointF, img_rect: QRectF):
        scale = float(self.doc.preview_w) / img_rect.width()
        return QPointF((point.x() - img_rect.x()) * scale, (point.y() - img_rect.y()) * scale)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.SmoothPixmapTransform)
        painter.setRenderHint(QPainter.Antialiasing)
        
        # Dark stage background
        painter.fillRect(self.rect(), QColor("#0E0E11"))
        
        # Grid lines
        step = 36
        grid_pen = QPen(QColor(255, 255, 255, 12), 1)
        painter.setPen(grid_pen)
        for x in range(step, self.width(), step):
            painter.drawLine(x, 0, x, self.height())
        for y in range(step, self.height(), step):
            painter.drawLine(0, y, self.width(), y)
            
        if not self.doc and not self.pixmap:
            return
            
        img_rect = self.get_image_rect()
        if img_rect.isEmpty():
            return
            
        # Draw transparency checkerboard inside img_rect
        cell = 12
        b1 = QColor(33, 33, 38)
        b2 = QColor(44, 44, 50)
        painter.fillRect(img_rect, b1)
        rx = int(img_rect.x())
        ry = int(img_rect.y())
        rw = int(img_rect.width())
        rh = int(img_rect.height())
        for yy in range(ry, ry + rh, cell):
            row_idx = (yy - ry) // cell
            for xx in range(rx + (row_idx % 2) * cell, rx + rw, cell * 2):
                bw = min(cell, rx + rw - xx)
                bh = min(cell, ry + rh - yy)
                painter.fillRect(QRect(xx, yy, bw, bh), b2)
                
        use_exact = not self.crop_mode and not self.playing and not self.pick_mode and self.exact_pixmap is not None
        use_playback = not use_exact and not self.crop_mode and not self.pick_mode and self.playback_pixmap is not None
        
        bmp = self.exact_pixmap if use_exact else (self.playback_pixmap if use_playback else self.current_pixmap())
        if not bmp:
            return
            
        if not use_exact and not use_playback and not self.crop_mode and self.doc and self.doc.state.crop_rect:
            cr = self.doc.state.crop_rect
            scale = bmp.width() / float(self.doc.info.width)
            src_rect = QRectF(cr[0] * scale, cr[1] * scale, cr[2] * scale, cr[3] * scale)
            painter.drawPixmap(img_rect, bmp, src_rect)
        else:
            painter.drawPixmap(img_rect, bmp, QRectF(bmp.rect()))
            
        if self.crop_mode:
            w_crop = self.preview_to_widget(self.crop_sel, img_rect)
            
            # Dark dimming outside crop area
            painter.setPen(Qt.NoPen)
            painter.setBrush(QBrush(QColor(11, 11, 13, 165)))
            painter.drawRect(QRectF(img_rect.left(), img_rect.top(), img_rect.width(), max(0.0, w_crop.top() - img_rect.top())))
            painter.drawRect(QRectF(img_rect.left(), w_crop.bottom(), img_rect.width(), max(0.0, img_rect.bottom() - w_crop.bottom())))
            painter.drawRect(QRectF(img_rect.left(), w_crop.top(), max(0.0, w_crop.left() - img_rect.left()), w_crop.height()))
            painter.drawRect(QRectF(w_crop.right(), w_crop.top(), max(0.0, img_rect.right() - w_crop.right()), w_crop.height()))
            
            # Accent frame
            painter.setPen(QPen(QColor("#FF3E05"), 2))
            painter.setBrush(Qt.NoBrush)
            painter.drawRect(w_crop)
            
            # Rule of thirds dashed lines
            rule_pen = QPen(QColor(255, 255, 255, 90), 1, Qt.DashLine)
            painter.setPen(rule_pen)
            third_w = w_crop.width() / 3.0
            third_h = w_crop.height() / 3.0
            painter.drawLine(QPointF(w_crop.left() + third_w, w_crop.top()), QPointF(w_crop.left() + third_w, w_crop.bottom()))
            painter.drawLine(QPointF(w_crop.left() + third_w * 2, w_crop.top()), QPointF(w_crop.left() + third_w * 2, w_crop.bottom()))
            painter.drawLine(QPointF(w_crop.left(), w_crop.top() + third_h), QPointF(w_crop.right(), w_crop.top() + third_h))
            painter.drawLine(QPointF(w_crop.left(), w_crop.top() + third_h * 2), QPointF(w_crop.right(), w_crop.top() + third_h * 2))
            
            # Corner handles
            h_size = 10
            painter.setBrush(QBrush(QColor("#FF3E05")))
            painter.setPen(Qt.NoPen)
            for p in [w_crop.topLeft(), w_crop.topRight(), w_crop.bottomLeft(), w_crop.bottomRight()]:
                painter.drawEllipse(p, h_size / 2, h_size / 2)

    def mousePressEvent(self, event):
        img_rect = self.get_image_rect()
        pos = event.position()
        
        if self.pick_mode:
            if img_rect.contains(pos) and self.pixmap:
                u = (pos.x() - img_rect.x()) / max(1.0, img_rect.width())
                v = (pos.y() - img_rect.y()) / max(1.0, img_rect.height())
                if not self.crop_mode and self.doc and self.doc.state.crop_rect:
                    cr = self.doc.state.crop_rect
                    scale = self.pixmap.width() / float(max(1, self.doc.info.width))
                    src_x = cr[0] * scale
                    src_y = cr[1] * scale
                    src_w = cr[2] * scale
                    src_h = cr[3] * scale
                    x = src_x + u * src_w
                    y = src_y + v * src_h
                else:
                    x = u * self.pixmap.width()
                    y = v * self.pixmap.height()
                
                img = self.pixmap.toImage()
                ix = max(0, min(img.width() - 1, int(x)))
                iy = max(0, min(img.height() - 1, int(y)))
                color = img.pixelColor(ix, iy)
                self.color_picked.emit(color.red(), color.green(), color.blue())
            return
            
        if not self.crop_mode:
            return
            
        ip = self.widget_to_preview(pos, img_rect)
        corners = [
            self.crop_sel.topLeft(),
            self.crop_sel.topRight(),
            self.crop_sel.bottomRight(),
            self.crop_sel.bottomLeft()
        ]
        grab_widget = 15
        for i in range(4):
            corner_widget = self.preview_to_widget(QRectF(corners[i], QPointF(corners[i].x(), corners[i].y())), img_rect).topLeft()
            if abs(pos.x() - corner_widget.x()) <= grab_widget and abs(pos.y() - corner_widget.y()) <= grab_widget:
                self.drag_mode = i
                self.drag_anchor = corners[(i + 2) % 4]
                return
                
        w_crop = self.preview_to_widget(self.crop_sel, img_rect)
        if w_crop.contains(pos):
            self.drag_mode = 4
            self.drag_offset = QPointF(ip.x() - self.crop_sel.x(), ip.y() - self.crop_sel.y())
            return
            
        self.drag_mode = -1

    def mouseMoveEvent(self, event):
        if not self.crop_mode:
            return
            
        img_rect = self.get_image_rect()
        ip = self.widget_to_preview(event.position(), img_rect)
        
        w = float(self.doc.preview_w)
        h = float(self.doc.preview_h)
        
        ip.setX(max(0.0, min(w, ip.x())))
        ip.setY(max(0.0, min(h, ip.y())))
        
        if getattr(self, 'drag_mode', -1) == -1:
            return
            
        if self.drag_mode == 4:
            nx = ip.x() - self.drag_offset.x()
            ny = ip.y() - self.drag_offset.y()
            nx = max(0.0, min(w - self.crop_sel.width(), nx))
            ny = max(0.0, min(h - self.crop_sel.height(), ny))
            self.crop_sel.moveTo(nx, ny)
        else:
            ax = self.drag_anchor.x()
            ay = self.drag_anchor.y()
            s = max(abs(ip.x() - ax), abs(ip.y() - ay))
            max_w = (w - ax) if ip.x() >= ax else ax
            max_h = (h - ay) if ip.y() >= ay else ay
            MIN_SEL = 32.0
            s = max(MIN_SEL, min(s, min(max_w, max_h)))
            nx = ax if ip.x() >= ax else ax - s
            ny = ay if ip.y() >= ay else ay - s
            self.crop_sel = QRectF(nx, ny, s, s)
            
        self.update()

    def mouseReleaseEvent(self, event):
        self.drag_mode = -1
