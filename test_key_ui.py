import PySide6

import os
os.environ['OMP_NUM_THREADS'] = '1'
os.environ['OPENBLAS_NUM_THREADS'] = '1'
os.environ['MKL_NUM_THREADS'] = '1'
os.environ['VECLIB_MAXIMUM_THREADS'] = '1'
os.environ['NUMEXPR_NUM_THREADS'] = '1'
import sys, os
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import Qt, QPoint, QPointF
from PySide6.QtGui import QMouseEvent, QImage
from PySide6.QtTest import QTest
from gui import MainWindow
from models import KeySettings
import subprocess

app = QApplication(sys.argv)
window = MainWindow()

test_vid = "wysiwyg_test.mp4"
window.show()
window.load_video(test_vid)
for _ in range(200):
    if window.editor.doc: break
    QTest.qWait(50)

editor = window.editor
preview = editor.preview

# Open key panel
editor.toggle_key_panel()
assert editor.key_panel.isVisible()
assert editor.editing_key is not None
assert editor.editing_key.gain == 100
assert editor.editing_key.shrink_grow == 0
assert editor.editing_key.screen_color_r == 0
assert editor.editing_key.screen_color_g == 255
assert editor.editing_key.screen_color_b <= 10

# Change Gain
editor.key_panel.gain_slider.setValue(150)
assert editor.editing_key.gain == 150
# fast preview update (bump_key was called)
print(preview.key_version)

# Change Shrink
editor.key_panel.shrink_slider.setValue(-20)
assert editor.editing_key.shrink_grow == -20

# Pick Mode
editor.key_panel.pick_btn.setChecked(True)
assert preview.pick_mode == True

# Click to pick color
img_rect = preview.get_image_rect()
# Click on the red square we drew in test_wysiwyg (top left 100, 100 on 640x480)
# Map 150, 150 from 640x480 to widget coordinates
mapped_x = img_rect.x() + 150.0 / 640.0 * img_rect.width()
mapped_y = img_rect.y() + 150.0 / 480.0 * img_rect.height()
pt = QPointF(mapped_x, mapped_y)

press = QMouseEvent(QMouseEvent.Type.MouseButtonPress, pt, Qt.MouseButton.LeftButton, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier)
preview.mousePressEvent(press)

assert editor.editing_key.screen_color_r >= 240
assert editor.editing_key.screen_color_g <= 10
assert editor.editing_key.screen_color_b <= 10
assert preview.pick_mode == False

# Click outside
editor.key_panel.pick_btn.setChecked(True)
out_pt = QPointF(img_rect.right() + 50, img_rect.top() - 50)
press2 = QMouseEvent(QMouseEvent.Type.MouseButtonPress, out_pt, Qt.MouseButton.LeftButton, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier)
preview.mousePressEvent(press2)
assert preview.pick_mode == True # didn't cancel because clicked outside!

# Cancel
editor.key_panel.pick_btn.setChecked(False)

# Apply
editor.key_panel.apply_btn.clicked.emit()
assert not editor.key_panel.isVisible()
assert editor.doc.state.key.gain == 150

# Undo
editor.undo()
assert editor.doc.state.key is None or not editor.doc.state.key.enabled

# Fast Preview validation
editor.toggle_key_panel()
editor.key_panel.gain_slider.setValue(120)
bmp = preview.current_pixmap()
assert bmp is not None
# The exact timer is running, let's wait 300ms

# Wait using real event loop instead of QTest.qWait to prevent macOS Accelerate deadlock
loop = PySide6.QtCore.QEventLoop()
def check_exact():
    if preview.exact_pixmap is not None:
        loop.quit()

timer = PySide6.QtCore.QTimer()
timer.timeout.connect(check_exact)
timer.start(50)
PySide6.QtCore.QTimer.singleShot(5000, loop.quit)
loop.exec()

assert preview.exact_pixmap is not None


# Playback cache check
editor.toggle_play()
assert editor.playing
# Wait for cache to build
loop2 = PySide6.QtCore.QEventLoop()
def check_cache():
    if editor.cache_dir != "":
        loop2.quit()

timer2 = PySide6.QtCore.QTimer()
timer2.timeout.connect(check_cache)
timer2.start(50)
PySide6.QtCore.QTimer.singleShot(120000, loop2.quit)
loop2.exec()

assert editor.cache_dir != ""
import glob
assert len(glob.glob(os.path.join(editor.cache_dir, "*.bmp"))) > 0

# Stop
editor.toggle_play()

print("All UI tests passed!")
app.quit()
