import os
import shutil
import tempfile
import uuid
import glob
from typing import Callable
from models import ProbeInfo, EditState
from ffmpeg_utils import Ffmpeg

class VideoDoc:
    MAX_INPUT_SECONDS = 180.0
    MAX_CUT_SECONDS = 6.0
    MIN_CUT_SECONDS = 0.5
    STICKER_SIDE = 512

    def __init__(self):
        self.source_path = ""
        self.info = None
        self.source_has_alpha = False
        
        self.frames = [] # list of bytes
        self.preview_fps = 30.0
        self.preview_w = 0
        self.preview_h = 0
        
        self.state = EditState()
        self.undo_stack = []

    def push_undo(self):
        import copy
        self.undo_stack.append(copy.deepcopy(self.state))
        if len(self.undo_stack) > 50:
            self.undo_stack.pop(0)

    def undo(self) -> bool:
        if not self.undo_stack: return False
        self.state = self.undo_stack.pop()
        return True

    def load(self, ffmpeg: str, path: str, progress: Callable[[int, str], None] = None) -> str:
        self.source_path = path
        self.info = Ffmpeg.probe(ffmpeg, path)
        if not self.info.ok:
            return f"Не удалось открыть видео: {self.info.error}"
        if self.info.duration > self.MAX_INPUT_SECONDS:
            return f"Видео длиннее {int(self.MAX_INPUT_SECONDS)} секунд. Для стикера загрузите ролик покороче."
            
        self.source_has_alpha = self.info.has_alpha
        
        self.state.cut_start = 0.0
        self.state.cut_end = min(self.info.duration, self.MAX_CUT_SECONDS)
        if self.state.cut_end - self.state.cut_start < self.MIN_CUT_SECONDS:
            self.state.cut_end = min(self.info.duration, self.state.cut_start + self.MIN_CUT_SECONDS)
            
        # Preview dimensions — match FrameGeometry STICKER_SIDE (up to 512 px)
        from geometry import FrameGeometry
        side = FrameGeometry.STICKER_SIDE
        if self.info.width >= self.info.height:
            pw = min(side, self.info.width)
            ph = FrameGeometry.even(float(self.info.height) * pw / self.info.width)
        else:
            ph = min(side, self.info.height)
            pw = FrameGeometry.even(float(self.info.width) * ph / self.info.height)
            
        self.preview_w = pw
        self.preview_h = ph
        
        self.preview_fps = self.info.fps if 0 < self.info.fps <= 30 else 30.0
        expected = int(self.info.duration * self.preview_fps) + 2
        
        tmp_dir = os.path.join(tempfile.gettempdir(), "sst_" + uuid.uuid4().hex)
        os.makedirs(tmp_dir, exist_ok=True)
        try:
            ext = "png" if self.source_has_alpha else "jpg"
            quality = "" if self.source_has_alpha else " -q:v 2"
            out_pattern = os.path.join(tmp_dir, f"f%05d.{ext}")
            
            args = f'-y -hide_banner -loglevel error -i "{path}" -vf "fps={Ffmpeg.inv(self.preview_fps)},scale={pw}:{ph}:flags=lanczos"{quality} "{out_pattern}"'
            
            if progress:
                progress(0, "Подготовка превью…")
                
            code, err = Ffmpeg.run(ffmpeg, args)
            if code != 0:
                return f"Не удалось прочитать видео: {Ffmpeg.last_line(err)}"
                
            files = sorted(glob.glob(os.path.join(tmp_dir, f"f*.{ext}")))
            if not files:
                return "Не удалось извлечь кадры из видео"
                
            self.frames = []
            for f in files:
                with open(f, "rb") as file:
                    self.frames.append(file.read())
                    
            if progress:
                progress(100, "Готово")
            return None
        finally:
            shutil.rmtree(tmp_dir, ignore_errors=True)
