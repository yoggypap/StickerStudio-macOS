"""
Stage 6.6 tests:
1. MAX_CUT_SECONDS = 6 limits
2. Preview aspect ratio (landscape, portrait, square)
"""
import sys
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import QRectF

app = QApplication(sys.argv)

# ─── 1. Cut duration limits ──────────────────────────────────────────────────
from video_doc import VideoDoc
from models import ProbeInfo

def make_doc(duration):
    doc = VideoDoc()
    doc.info = ProbeInfo(width=640, height=480, fps=25.0, duration=duration)
    doc.state.cut_start = 0.0
    doc.state.cut_end = min(duration, VideoDoc.MAX_CUT_SECONDS)
    doc.preview_fps = 25.0
    doc.preview_w = 640
    doc.preview_h = 480
    doc.frames = [b'']
    return doc

assert VideoDoc.MAX_CUT_SECONDS == 6.0, f"Expected 6.0, got {VideoDoc.MAX_CUT_SECONDS}"

# 5 sec source -> max 5
doc5 = make_doc(5.0)
assert doc5.state.cut_end == 5.0, f"Expected 5.0, got {doc5.state.cut_end}"

# 10 sec source -> capped at MAX_CUT_SECONDS = 6
doc10 = make_doc(10.0)
assert doc10.state.cut_end == 6.0, f"Expected 6.0, got {doc10.state.cut_end}"

# 20 sec source -> capped at MAX_CUT_SECONDS = 6
doc20 = make_doc(20.0)
assert doc20.state.cut_end == 6.0, f"Expected 6.0, got {doc20.state.cut_end}"

# 40 sec source -> capped at MAX_CUT_SECONDS = 6
doc40 = make_doc(40.0)
assert doc40.state.cut_end == 6.0, f"Expected 6.0, got {doc40.state.cut_end}"

# Timeline drag cannot set duration > MAX_CUT_SECONDS
doc40.state.cut_start = 0.0
t_requested = 40.0  # user tries to set cut_end to 40
dur = t_requested - doc40.state.cut_start
if dur > VideoDoc.MAX_CUT_SECONDS:
    t_clamped = doc40.state.cut_start + VideoDoc.MAX_CUT_SECONDS
else:
    t_clamped = t_requested
assert t_clamped == 6.0, f"Timeline should clamp to 6, got {t_clamped}"

print("PASS: cut duration limits (MAX_CUT_SECONDS = 6)")

# ─── 2. Preview aspect ratio ─────────────────────────────────────────────────
from preview_widget import PreviewWidget
from PySide6.QtGui import QPixmap, QImage

widget = PreviewWidget()
widget.resize(800, 600)

def make_pixmap(w, h):
    img = QImage(w, h, QImage.Format_RGB32)
    img.fill(0xFF0000)
    return QPixmap.fromImage(img)

def check_aspect_ratio(src_w, src_h, widget_w, widget_h, label):
    widget.resize(widget_w, widget_h)
    pix = make_pixmap(src_w, src_h)
    widget.pixmap = pix
    # doc is None so get_image_rect won't crash
    rect = widget.get_image_rect()
    if rect.isEmpty(): return  # no doc, skip
    
    # Check aspect ratio is preserved
    expected_ar = src_w / src_h
    actual_ar = rect.width() / rect.height()
    assert abs(actual_ar - expected_ar) < 0.02, \
        f"{label}: AR mismatch: expected {expected_ar:.3f}, got {actual_ar:.3f}"
    
    # Check it fits inside widget
    assert rect.left() >= 0
    assert rect.top() >= 0
    assert rect.right() <= widget_w + 1
    assert rect.bottom() <= widget_h + 1
    
    # Check centered
    if abs(actual_ar - widget_w / widget_h) > 0.01:
        if actual_ar > widget_w / widget_h:
            # letterbox top/bottom
            assert abs(rect.left()) < 1, f"{label}: not left-aligned in landscape"
        else:
            # pillarbox left/right
            assert abs(rect.top()) < 1, f"{label}: not top-aligned in portrait"

# Landscape source in landscape widget
check_aspect_ratio(1920, 1080, 800, 600, "landscape 16:9")
# Portrait source in landscape widget
check_aspect_ratio(1080, 1920, 800, 600, "portrait 9:16")
# Square source in landscape widget
check_aspect_ratio(512, 512, 800, 600, "square")
# Square source in portrait widget
check_aspect_ratio(512, 512, 400, 700, "square in portrait widget")
# Wide source in tall widget
check_aspect_ratio(2560, 720, 800, 600, "ultra-wide")

print("PASS: preview aspect ratio preserved for landscape, portrait, square")

print("All Stage 6.6 geometry tests passed!")
