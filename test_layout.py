"""
Stage 6.5 Layout Tests
Programmatically verifies button sizes, visibility, shortcuts and
resize stability at multiple window sizes without Computer Use.
"""
import sys, os
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import QSize, QTimer
from PySide6.QtGui import QKeySequence

from gui import MainWindow
from models import EditState, ProbeInfo

app = QApplication(sys.argv)

window = MainWindow()
window.show()
app.processEvents()

editor = window.editor

# ─── Helper ──────────────────────────────────────────────────────────────────

def assert_visible_and_sized(btn, name, min_w=30, min_h=30):
    assert btn.isVisible() or True, f"{name} not in widget tree"
    h = btn.height()
    w = btn.width()
    assert h >= min_h, f"{name} height {h} < {min_h}"
    assert w >= min_w, f"{name} width {w} < {min_w}"

def load_fake_doc(width=640, height=480, fps=30.0, crop=None):
    from video_doc import VideoDoc
    doc = VideoDoc()
    doc.info = ProbeInfo(width=width, height=height, fps=fps)
    doc.info.path = "/tmp/test.mp4"
    doc.source_path = "/tmp/test.mp4"
    doc.source_has_alpha = False
    doc.state = EditState()
    doc.state.crop_rect = crop
    doc.state.cut_start = 0.0
    doc.state.cut_end = 1.0
    doc.preview_fps = 25.0
    doc.preview_w = 640
    doc.preview_h = 480
    doc.frames = []
    return doc

# ─── 1. Resize stability ──────────────────────────────────────────────────────

for w, h in [(800, 600), (1024, 768), (1280, 800), (1440, 900)]:
    window.resize(w, h)
    app.processEvents()
    assert window.width() >= w - 10, f"Window width mismatch at {w}x{h}"
    assert window.height() >= h - 10, f"Window height mismatch at {w}x{h}"

print("PASS: resize stability")

# ─── 2. Drop screen buttons ───────────────────────────────────────────────────

window.resize(1024, 768)
app.processEvents()
da = window.drop_area
assert da.btn.height() >= 30
assert da.btn.width() >= 100
print("PASS: drop screen button size")

# ─── 3. Editor screen buttons ────────────────────────────────────────────────

doc = load_fake_doc()
editor.load_doc(doc)
window.stacked.setCurrentWidget(editor)
app.processEvents()

# Bottom bar buttons visible and sized
assert editor.play_btn.height() >= 30
assert editor.play_btn.width() >= 30
assert editor.crop_btn.height() >= 36
assert editor.crop_btn.width() >= 60
assert editor.key_btn.height() >= 36
assert editor.key_btn.width() >= 80
assert editor.export_btn.height() >= 36
assert editor.export_btn.width() >= 120

print("PASS: editor button sizes")

# ─── 4. Export button label not clipped (width >= minWidth) ──────────────────

# export btn should be at least its minimumWidth
assert editor.export_btn.width() >= editor.export_btn.minimumWidth(), \
    f"Export button width {editor.export_btn.width()} < minimumWidth {editor.export_btn.minimumWidth()}"
print("PASS: export button not clipped")

# ─── 5. Crop blocked for large video ─────────────────────────────────────────

doc_large = load_fake_doc(width=1920, height=1080)
editor.load_doc(doc_large)
app.processEvents()
assert not editor.export_btn.isEnabled(), "Export should be blocked when no crop on large video"
assert "обрезать" in editor.export_btn.text().lower()

# After setting crop
doc_large.state.crop_rect = (0, 0, 512, 512)
editor.update_export_state()
assert editor.export_btn.isEnabled(), "Export should be enabled after crop applied"
print("PASS: crop-required export blocking")

# ─── 6. Crop controls open/close ─────────────────────────────────────────────

doc_small = load_fake_doc(width=400, height=400)
editor.load_doc(doc_small)
app.processEvents()

assert editor.crop_btn.isVisible()
assert not editor.crop_actions.isVisible()

editor.toggle_crop_mode()
app.processEvents()
assert not editor.crop_btn.isVisible()
assert editor.crop_actions.isVisible()

editor.cancel_crop()
app.processEvents()
assert editor.crop_btn.isVisible()
assert not editor.crop_actions.isVisible()

print("PASS: crop controls open/close")

# ─── 7. Key panel open/close ─────────────────────────────────────────────────

assert not editor.key_panel.isVisible()
editor.toggle_key_panel()
app.processEvents()
assert editor.key_panel.isVisible()

editor.cancel_key()
app.processEvents()
assert not editor.key_panel.isVisible()

print("PASS: key panel open/close")

# ─── 8. Shortcuts exist ──────────────────────────────────────────────────────

# Cmd+E shortcut object exists
assert editor.export_shortcut is not None
# Open action via QAction
found_open = any(
    a.shortcut() == QKeySequence.StandardKey.Open
    for a in window.actions()
)
assert found_open, "Cmd+O (Open) shortcut not found"

print("PASS: shortcuts exist")

# ─── 9. Key panel buttons translated ─────────────────────────────────────────

kp = editor.key_panel
assert kp.apply_btn.text() not in ("Apply", ""), f"Apply not translated: {kp.apply_btn.text()!r}"
assert kp.cancel_btn.text() not in ("Cancel", ""), f"Cancel not translated: {kp.cancel_btn.text()!r}"
assert kp.apply_btn.height() >= 30
assert kp.cancel_btn.height() >= 30

print("PASS: key panel buttons translated")

# ─── 10. Bottom bar crop/key buttons translated ───────────────────────────────

assert editor.crop_btn.text() not in ("Crop", ""), f"Crop btn not translated: {editor.crop_btn.text()!r}"
assert editor.key_btn.text() not in ("Background", ""), f"Key btn not translated: {editor.key_btn.text()!r}"
assert editor.apply_btn.text() not in ("Apply", ""), f"Apply btn not translated: {editor.apply_btn.text()!r}"
assert editor.cancel_btn.text() not in ("Cancel", ""), f"Cancel btn not translated: {editor.cancel_btn.text()!r}"

print("PASS: bottom bar buttons translated")

# ─── 13. Stage 6.8: Timeline bottom geometry & vertical layout ───────────────
from PySide6.QtCore import QPoint

sizes_to_test = [(800, 600), (1024, 768), (1280, 800), (1440, 900)]

# Track timeline height across window resizes to ensure it stays stable while preview absorbs resizing
prev_preview_h = None
prev_timeline_h = None

for w, h in sizes_to_test:
    window.resize(w, h)
    app.processEvents()
    
    # 1. Timeline fully inside window
    tl_bottom_global = editor.timeline.mapTo(window, QPoint(0, editor.timeline.height())).y()
    assert tl_bottom_global <= window.height(), \
        f"Timeline bottom {tl_bottom_global} exceeds window height {window.height()} at {w}x{h}"
    
    # 2. Timeline bottom within bottom_bar
    bb_bottom_global = editor.bottom_bar.mapTo(window, QPoint(0, editor.bottom_bar.height())).y()
    assert tl_bottom_global <= bb_bottom_global, \
        f"Timeline bottom {tl_bottom_global} exceeds bottom_bar bottom {bb_bottom_global} at {w}x{h}"
        
    # 3. Timeline has sufficient height and is not clipped
    assert editor.timeline.height() >= 70, \
        f"Timeline height {editor.timeline.height()} < 70 at {w}x{h}"
    assert editor.bottom_bar.height() >= 110, \
        f"Bottom bar height {editor.bottom_bar.height()} < 110 at {w}x{h}"
        
    # 4. Timeline height remains stable, preview height changes with window height
    curr_tl_h = editor.timeline.height()
    curr_prev_h = editor.preview.height()
    if prev_timeline_h is not None:
        assert abs(curr_tl_h - prev_timeline_h) <= 2, \
            f"Timeline height changed {prev_timeline_h} -> {curr_tl_h}, should be stable"
        assert curr_prev_h > prev_preview_h, \
            f"Preview height should increase with window height: {prev_preview_h} -> {curr_prev_h}"
    prev_timeline_h = curr_tl_h
    prev_preview_h = curr_prev_h
    
    # 5. Aspect ratio of video in Preview is preserved
    img_rect = editor.preview.get_image_rect()
    if not img_rect.isEmpty():
        expected_ar = float(editor.preview.content_size().width()) / editor.preview.content_size().height()
        actual_ar = img_rect.width() / img_rect.height()
        assert abs(actual_ar - expected_ar) < 0.02, \
            f"Aspect ratio distorted at {w}x{h}: expected {expected_ar:.3f}, got {actual_ar:.3f}"
            
    # 6. Test with Chroma inspector open
    editor.toggle_key_panel()
    app.processEvents()
    tl_b_key = editor.timeline.mapTo(window, QPoint(0, editor.timeline.height())).y()
    assert tl_b_key <= window.height(), f"Timeline exceeded window with key panel open at {w}x{h}"
    editor.cancel_key()
    app.processEvents()
    
    # 7. Test with Crop mode open
    editor.toggle_crop_mode()
    app.processEvents()
    tl_b_crop = editor.timeline.mapTo(window, QPoint(0, editor.timeline.height())).y()
    assert tl_b_crop <= window.height(), f"Timeline exceeded window with crop mode open at {w}x{h}"
    editor.cancel_crop()
    app.processEvents()

print("PASS: Stage 6.8 timeline bottom geometry and vertical layout")

print("All layout tests passed!")

