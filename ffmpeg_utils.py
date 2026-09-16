import sys
import os
import shutil
import subprocess
import re
from models import ProbeInfo

class Ffmpeg:
    SIZE_LIMIT = 262144
    SIZE_TARGET = 250 * 1024

    @staticmethod
    def find() -> str | None:
        # In frozen macOS .app bundle, Contents/Resources/ffmpeg is the primary and mandatory location
        if getattr(sys, 'frozen', False):
            app_res = os.path.normpath(os.path.join(os.path.dirname(sys.executable), "..", "Resources", "ffmpeg"))
            if os.path.exists(app_res) and os.access(app_res, os.X_OK):
                return app_res
            meipass_res = os.path.join(getattr(sys, '_MEIPASS', ''), "ffmpeg")
            if os.path.exists(meipass_res) and os.access(meipass_res, os.X_OK):
                return meipass_res

        base_dir = os.path.dirname(os.path.abspath(__file__))
        
        # 1. Check local bin folder (for development)
        local_bin = os.path.join(base_dir, "bin", "ffmpeg")
        if os.path.exists(local_bin) and os.access(local_bin, os.X_OK):
            return local_bin
            
        # 2. Check macOS .app bundle structure (for production)
        # Assuming script runs from MyApp.app/Contents/MacOS/
        app_res = os.path.join(base_dir, "..", "Resources", "ffmpeg")
        if os.path.exists(app_res) and os.access(app_res, os.X_OK):
            return os.path.normpath(app_res)
            
        # 3. Fallback to system ffmpeg
        return shutil.which("ffmpeg")

    @staticmethod
    def run(ffmpeg: str, args: str) -> tuple[int, str]:
        cmd = f'"{ffmpeg}" {args}'
        try:
            process = subprocess.run(cmd, shell=True, capture_output=True, text=True)
            return process.returncode, process.stderr
        except Exception as e:
            return -1, str(e)

    @staticmethod
    def probe(ffmpeg: str, input_path: str) -> ProbeInfo:
        info = ProbeInfo()
        code, log = Ffmpeg.run(ffmpeg, f'-hide_banner -i "{input_path}"')
        
        md = re.search(r'Duration:\s+(\d+):(\d+):(\d+(?:\.\d+)?)', log)
        if not md:
            info.error = "не удалось определить длительность (файл повреждён?)"
            return info
            
        info.duration = (
            int(md.group(1)) * 3600 +
            int(md.group(2)) * 60 +
            float(md.group(3))
        )
        
        mv = re.search(r'Stream #\d+:\d+.*?: Video: (.+)', log)
        if not mv:
            info.error = "видеопоток не найден"
            return info
            
        vline = mv.group(1)
        mdim = re.search(r'[, ](\d{2,5})x(\d{2,5})[ ,\[]', vline)
        if not mdim:
            info.error = "не удалось определить разрешение"
            return info
            
        info.width = int(mdim.group(1))
        info.height = int(mdim.group(2))
        
        mfps = re.search(r'(\d+(?:\.\d+)?)\s*fps', vline)
        if mfps:
            info.fps = float(mfps.group(1))
            
        alpha_fmts = ["yuva", "rgba", "argb", "bgra", "abgr", "gbrap", "ya8", "ya16"]
        for fmt in alpha_fmts:
            if fmt in vline:
                info.has_alpha = True
                break
                
        if info.duration <= 0.05:
            info.error = "нулевая длительность"
            return info
            
        info.ok = True
        return info

    @staticmethod
    def last_line(s: str) -> str:
        if not s:
            return "ffmpeg завершился с ошибкой"
        lines = [line.strip() for line in s.replace('\r', '').split('\n') if line.strip()]
        if lines:
            return lines[-1]
        return "ffmpeg завершился с ошибкой"

    @staticmethod
    def inv(v: float) -> str:
        return format(v, ".3f")
