import sys
import os
import copy
from PySide6.QtWidgets import QApplication, QMessageBox
from PySide6.QtCore import QTimer
from PySide6.QtGui import QKeySequence

from gui import MainWindow
from models import EditState, ProbeInfo
from video_doc import VideoDoc
from export_worker import ExportRequest
from export_pipeline import ExportResult

app = QApplication(sys.argv)
window = MainWindow()

# We will mock QMessageBox and ExportWorker
msg_box_args = []
def mock_question(parent, title, text, buttons, default):
    msg_box_args.append((title, text))
    if True:
        return QMessageBox.StandardButton.Yes if getattr(window, "mock_msg_box_reply_yes", True) else QMessageBox.StandardButton.No
    return None

def mock_critical(parent, title, text):
    msg_box_args.append(("critical", title, text))

def mock_info(parent, title, text):
    msg_box_args.append(("info", title, text))

QMessageBox.question = mock_question
QMessageBox.critical = mock_critical
QMessageBox.information = mock_info

worker_calls = []
class MockExportWorker:
    def __init__(self):
        self.progress = window.editor.export_worker.progress
        self.finished = window.editor.export_worker.finished
    def start_export(self, req: ExportRequest):
        worker_calls.append(req)

window.editor.export_worker.start_export = MockExportWorker().start_export

# 1. Normal export blocked by crop requirement
doc = VideoDoc()
doc.info = ProbeInfo(width=600, height=600, fps=30)
doc.source_path = "/tmp/test.mp4"
doc.state.crop_rect = None
window.editor.load_doc(doc)

print(window.editor.export_btn.text())
assert window.editor.export_btn.text() == "Сначала обрезать кадр"
assert not window.editor.export_btn.isEnabled()
assert not window.editor.export_shortcut.isEnabled()
assert window.editor.export_shortcut.key() == QKeySequence("Ctrl+E")
assert window.editor.export_shortcut.key().toString(QKeySequence.SequenceFormat.NativeText) in ("⌘E", "Ctrl+E")
# Triggering shortcut while disabled must not start export
window.editor.export_shortcut.activated.emit()
assert len(worker_calls) == 0

# Apply crop
window.editor.doc.state.crop_rect = (0, 0, 400, 400)
window.editor.update_export_state()
assert window.editor.export_btn.text() == "Экспортировать WebM"
assert window.editor.export_btn.isEnabled()
assert window.editor.export_shortcut.isEnabled()

# Click export
window.mock_msg_box_reply_yes = True
window.editor.export_btn.clicked.emit()
assert window.editor.exporting == True
assert window.editor.export_btn.text() == "Экспортирую..."
assert not window.editor.export_btn.isEnabled()
assert not window.editor.export_shortcut.isEnabled()

assert len(worker_calls) == 1
req = worker_calls[0]
assert req.output_path == "/tmp/test_sticker.webm"
assert req.snapshot.fps30 == False # since info.fps was 30

# Click again should be ignored
window.editor.export_btn.clicked.emit()
assert len(worker_calls) == 1

# Send progress
window.editor.export_worker.progress.emit("Удаление фона... 50%")
assert window.editor.export_btn.text() == "Удаление фона... 50%"

# Finish ok
res = ExportResult()
res.ok = True
res.size = 150000
res.alpha_in_output = True
res.output_path = "/tmp/test_sticker.webm"
window.editor.export_worker.finished.emit(res)
assert window.editor.exporting == False
assert window.editor.export_btn.text() == "Экспортировать WebM"
assert window.editor.export_btn.isEnabled()

assert len(msg_box_args) == 1
assert msg_box_args[0][0] == "info"
assert "146 КБ" in msg_box_args[0][2]
assert "с альфой" in msg_box_args[0][2]
msg_box_args.clear()
worker_calls.clear()

# 2. 60 FPS Export -> Say YES
doc.info.fps = 60
window.mock_msg_box_reply_yes = True
window.editor.export_btn.clicked.emit()
assert len(msg_box_args) == 1
assert "Высокая частота" in msg_box_args[0][0]
req = worker_calls[0]
assert req.snapshot.fps30 == True
assert window.editor.doc.state.fps30 == False # MUST NOT mutate original
msg_box_args.clear()
worker_calls.clear()

# Finish error
res = ExportResult()
res.ok = False
res.error = "Test Error"
window.editor.export_worker.finished.emit(res)
assert window.editor.exporting == False
assert len(msg_box_args) == 1
assert msg_box_args[0][0] == "critical"
assert "Test Error" in msg_box_args[0][2]
msg_box_args.clear()

# 3. 60 FPS Export -> Say NO
window.mock_msg_box_reply_yes = False
window.editor.export_shortcut.activated.emit() # test shortcut
assert len(msg_box_args) == 1
req = worker_calls[0]
assert req.snapshot.fps30 == False
msg_box_args.clear()
worker_calls.clear()

res = ExportResult()
res.ok = True
res.size = 100000
res.fps_warning = True
res.output_path = "/tmp/test_sticker.webm"
window.editor.export_worker.finished.emit(res)
assert len(msg_box_args) == 1
assert "Частота выше 30 fps" in msg_box_args[0][2]
msg_box_args.clear()

print("All export UI tests passed!")
