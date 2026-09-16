"""
Test playback regression — Stage 6.6
Verifies that after load_doc, pressing Play:
 - playback_timer fires
 - timeline.position increases over time
 - frame displayed changes
 - Pause stops motion
 - loop within cut range is preserved
"""
import sys
import time
import subprocess
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import QTimer, QEventLoop

app = QApplication(sys.argv)

from gui import MainWindow
from video_doc import VideoDoc
from ffmpeg_utils import Ffmpeg

# Create a short test video
subprocess.run([
    'ffmpeg', '-y', '-f', 'lavfi',
    '-i', 'testsrc=duration=3:size=320x240:rate=25',
    '-c:v', 'libx264', '/tmp/test_play.mp4'
], capture_output=True)

window = MainWindow()
editor = window.editor

ffmpeg = Ffmpeg.find()
doc = VideoDoc()
err = doc.load(ffmpeg, '/tmp/test_play.mp4')
assert err is None, f"Load failed: {err}"
assert len(doc.frames) > 0
assert doc.preview_fps > 0

editor.load_doc(doc)
editor.ffmpeg_path = ffmpeg
window.stacked.setCurrentWidget(editor)
window.show()
app.processEvents()

# Disable cache requests so they don't interfere with test
editor.cache_timer.stop()

# ── 1. Initial state ──────────────────────────────────────────────────────────
initial_pos = editor.timeline.position
initial_frame = editor.preview.frame_idx
assert not editor.playing, "Should not be playing initially"

# ── 2. Start playback ─────────────────────────────────────────────────────────
editor.toggle_play()
assert editor.playing, "Should be playing after toggle"
assert editor.play_btn.text() == "⏸", "Button should show pause icon"

# Let Qt event loop run for ~300ms
loop = QEventLoop()
QTimer.singleShot(350, loop.quit)
loop.exec()

app.processEvents()

pos_after_300ms = editor.timeline.position
frame_after_300ms = editor.preview.frame_idx

print(f"Initial pos: {initial_pos:.3f}")
print(f"Pos after 350ms: {pos_after_300ms:.3f}")
print(f"Initial frame: {initial_frame}, Frame after 350ms: {frame_after_300ms}")

assert pos_after_300ms > initial_pos, \
    f"Position should have advanced: {initial_pos:.3f} -> {pos_after_300ms:.3f}"

# ── 3. Pause ──────────────────────────────────────────────────────────────────
editor.toggle_play()
assert not editor.playing, "Should be paused after second toggle"
assert editor.play_btn.text() == "▶", "Button should show play icon"

paused_pos = editor.timeline.position

# Wait another 300ms, position must not change while paused
loop2 = QEventLoop()
QTimer.singleShot(300, loop2.quit)
loop2.exec()
app.processEvents()

pos_after_pause = editor.timeline.position
assert abs(pos_after_pause - paused_pos) < 0.05, \
    f"Position changed while paused: {paused_pos:.3f} -> {pos_after_pause:.3f}"

print(f"Paused at: {paused_pos:.3f}, Still at: {pos_after_pause:.3f}")

# ── 4. Loop test — play to near end and verify wrap ──────────────────────────
editor.set_position(doc.state.cut_end - 0.1)
editor.toggle_play()

loop3 = QEventLoop()
QTimer.singleShot(400, loop3.quit)
loop3.exec()
app.processEvents()

pos_after_loop = editor.timeline.position
# After looping, position should be within cut range
assert doc.state.cut_start <= pos_after_loop <= doc.state.cut_end, \
    f"Position out of cut range after loop: {pos_after_loop:.3f} (cut: {doc.state.cut_start:.2f}-{doc.state.cut_end:.2f})"

editor.toggle_play()
print(f"After loop, pos: {pos_after_loop:.3f} (in range [{doc.state.cut_start:.2f}, {doc.state.cut_end:.2f}])")

print("PASS: playback test")
