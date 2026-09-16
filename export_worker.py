import threading
import copy
from PySide6.QtCore import QObject, Signal
from export_pipeline import ExportPipeline, ExportResult
from models import EditState
from video_doc import VideoDoc

class ExportRequest:
    def __init__(
        self,
        ffmpeg_path,
        source_path,
        info,
        source_has_alpha,
        output_path,
        snapshot
    ):
        self.ffmpeg_path = ffmpeg_path
        self.source_path = source_path
        self.info = copy.deepcopy(info)
        self.source_has_alpha = source_has_alpha
        self.output_path = output_path
        self.snapshot = copy.deepcopy(snapshot)

class ExportWorker(QObject):
    progress = Signal(str)
    finished = Signal(ExportResult)
    
    def __init__(self):
        super().__init__()
        
    def start_export(self, req: ExportRequest):
        thread = threading.Thread(target=self._run_export, args=(req,), daemon=True)
        thread.start()
        
    def _run_export(self, req: ExportRequest):
        try:
            def on_progress(msg):
                self.progress.emit(msg)
                
            res = ExportPipeline.run(
                req.ffmpeg_path,
                req.source_path,
                req.info,
                req.source_has_alpha,
                req.snapshot,
                req.output_path,
                progress=on_progress
            )
            self.finished.emit(res)
        except Exception as e:
            res = ExportResult()
            res.ok = False
            res.error = str(e)
            self.finished.emit(res)
