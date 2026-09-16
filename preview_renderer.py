import os, tempfile, uuid, glob, subprocess, copy, threading, queue, struct
import numpy as np
from PIL import Image
from PySide6.QtCore import QObject, Signal
from PySide6.QtGui import QImage
from models import ProbeInfo, EditState
from geometry import FrameGeometry
from ffmpeg_utils import Ffmpeg
from chroma_key import ChromaKey

def _save_rgba_bmp(img: Image.Image, path: str):
    if img.mode != 'RGBA':
        img = img.convert('RGBA')
    w, h = img.size
    arr = np.array(img)
    bgra = np.empty_like(arr)
    bgra[..., 0] = arr[..., 2] # B
    bgra[..., 1] = arr[..., 1] # G
    bgra[..., 2] = arr[..., 0] # R
    bgra[..., 3] = arr[..., 3] # A
    bgra = np.ascontiguousarray(bgra[::-1, ...])
    
    header_size = 108
    raw_bytes = bgra.tobytes()
    file_size = 14 + header_size + len(raw_bytes)
    offset = 14 + header_size
    
    bfh = struct.pack('<2sIHHI', b'BM', file_size, 0, 0, offset)
    bvh = struct.pack('<IIIHHIIIIIIIIII',
        header_size, w, h, 1, 32, 3, len(raw_bytes), 2835, 2835, 0, 0,
        0x00FF0000, 0x0000FF00, 0x000000FF, 0xFF000000
    ) + b'\x00' * (header_size - 56)
    
    with open(path, 'wb') as f:
        f.write(bfh)
        f.write(bvh)
        f.write(raw_bytes)


class ExactPreviewRequest:
    def __init__(self):
        self.revision = 0
        self.ffmpeg_path = ""
        self.source_path = ""
        self.info = None
        self.time = 0.0
        self.state = None 

class PlaybackCacheRequest:
    def __init__(self):
        self.revision = 0
        self.ffmpeg_path = ""
        self.source_path = ""
        self.info = None
        self.state = None 

class PreviewRenderer(QObject):
    exact_completed = Signal(int, QImage)
    cache_completed = Signal(int, str, float) 
    
    def __init__(self):
        super().__init__()
        self.q = queue.Queue()
        self.abort_flag = False
        self.ffmpeg_proc = None
        self.thread = threading.Thread(target=self.run, daemon=True)
        self.thread.start()

    def request_exact(self, req: ExactPreviewRequest):
        while not self.q.empty():
            try: self.q.get_nowait()
            except: pass
        self.q.put(req)

    def request_cache(self, req: PlaybackCacheRequest):
        while not self.q.empty():
            try: self.q.get_nowait()
            except: pass
        self.q.put(req)

    def cancel_pending(self):
        while not self.q.empty():
            try: self.q.get_nowait()
            except: pass
        self.abort_flag = True
        if self.ffmpeg_proc:
            try: self.ffmpeg_proc.kill()
            except: pass

    def run(self):
        while True:
            try:
                req = self.q.get()
                self.abort_flag = False
                if type(req).__name__ == "ExactPreviewRequest":
                    self._render_exact(req)
                elif type(req).__name__ == "PlaybackCacheRequest":
                    self._render_cache(req)
            except Exception as e:
                print("WORKER EXCEPTION:", e)

    def _render_exact(self, req: ExactPreviewRequest):
        if not req.source_path or not os.path.exists(req.source_path):
            return
        tmp_dir = os.path.join(tempfile.gettempdir(), "ss_ex_" + uuid.uuid4().hex)
        os.makedirs(tmp_dir, exist_ok=True)
        try:
            geometry = FrameGeometry.create(req.info, req.state.crop_rect)
            pre_key = geometry.pre_key_filter
            post_key = geometry.post_key_filter
            vf = (f"{pre_key}," if pre_key else "") + "format=rgba"
            raw_png = os.path.join(tmp_dir, "raw.png")
            
            cmd1 = [req.ffmpeg_path, '-y', '-nostdin', '-hide_banner', '-loglevel', 'error', 
                    '-ss', Ffmpeg.inv(req.time), '-i', req.source_path,
                    '-vframes', '1', '-vf', vf, raw_png]
            
            if self.abort_flag: return
            self.ffmpeg_proc = subprocess.Popen(cmd1, stderr=subprocess.PIPE, stdout=subprocess.PIPE)
            stdout1, stderr1 = self.ffmpeg_proc.communicate()
            
            if self.ffmpeg_proc.returncode != 0:
                if not self.abort_flag:
                    print("FFMPEG1 ERROR:", stderr1.decode())
                return
                
            self.ffmpeg_proc = None
            if self.abort_flag: return
            if not os.path.exists(raw_png): return
            
            img = Image.open(raw_png).convert('RGBA')
            img = ChromaKey.apply(img, req.state.key)
            
            keyed_raw = os.path.join(tmp_dir, "keyed.rgba")
            with open(keyed_raw, "wb") as f:
                f.write(img.tobytes("raw", "RGBA"))
                
            scaled_png = os.path.join(tmp_dir, "scaled.png")
            if post_key:
                cmd2 = [
                    req.ffmpeg_path, '-y', '-nostdin', '-hide_banner',
                    '-loglevel', 'error',
                    '-f', 'rawvideo',
                    '-pix_fmt', 'rgba',
                    '-s', f'{img.width}x{img.height}',
                    '-i', keyed_raw,
                    '-vf', post_key,
                    scaled_png
                ]

                if self.abort_flag:
                    return

                self.ffmpeg_proc = subprocess.Popen(
                    cmd2,
                    stderr=subprocess.PIPE,
                    stdout=subprocess.PIPE
                )
                stdout, stderr = self.ffmpeg_proc.communicate()

                if self.ffmpeg_proc.returncode != 0:
                    if not self.abort_flag:
                        print('FFMPEG ERROR:', stderr.decode())
                    self.ffmpeg_proc = None
                    return

                self.ffmpeg_proc = None
                if self.abort_flag:
                    return

                if not os.path.exists(scaled_png):
                    return

                img = Image.open(scaled_png).convert('RGBA')
            else:
                img.save(scaled_png, 'PNG')
            
            img = ChromaKey.prepare_for_vp9(img, 3)
            img_data = img.tobytes("raw", "RGBA")
            qimg = QImage(img_data, img.width, img.height, QImage.Format_RGBA8888)
            copied_qimg = qimg.copy()
            self.exact_completed.emit(req.revision, copied_qimg)
        except Exception as e:
            print("RENDER EXACT ERROR:", e)
        finally:
            import shutil
            shutil.rmtree(tmp_dir, ignore_errors=True)

    def _render_cache(self, req: PlaybackCacheRequest):
        if not req.source_path or not os.path.exists(req.source_path):
            return
        tmp_dir = os.path.join(tempfile.gettempdir(), "ss_cache_" + uuid.uuid4().hex)
        os.makedirs(tmp_dir, exist_ok=True)
        try:
            dur = req.state.cut_end - req.state.cut_start
            if dur <= 0: return
            geometry = FrameGeometry.create(req.info, req.state.crop_rect)
            pre_key = geometry.pre_key_filter
            post_key = geometry.post_key_filter
            fps = 30.0 if req.state.fps30 else (req.info.fps if req.info.fps > 0 else 30.0)
            
            final_dir = os.path.join(tempfile.gettempdir(), "ss_ready_" + uuid.uuid4().hex)
            os.makedirs(final_dir, exist_ok=True)

            # ── Fast direct path when Chroma Key is not enabled ──
            # Uses direct FFmpeg native crop -> scale=512:512:flags=lanczos
            if not req.state.key or not req.state.key.enabled:
                vf_filters = [f"fps={Ffmpeg.inv(fps)}"]
                if pre_key:
                    vf_filters.append(pre_key)
                if post_key:
                    vf_filters.append(post_key)
                else:
                    vf_filters.append("scale=512:512:flags=lanczos,setsar=1")
                    
                vf_str = ",".join(vf_filters)
                
                cmd_direct = [
                    req.ffmpeg_path, '-y', '-nostdin', '-hide_banner', '-loglevel', 'error',
                    '-ss', Ffmpeg.inv(req.state.cut_start), '-t', Ffmpeg.inv(dur),
                    '-i', req.source_path,
                    '-vf', vf_str,
                    os.path.join(final_dir, "f%05d.bmp")
                ]
                
                if self.abort_flag: return
                self.ffmpeg_proc = subprocess.Popen(cmd_direct, stderr=subprocess.PIPE, stdout=subprocess.PIPE)
                stdout, stderr = self.ffmpeg_proc.communicate()
                if self.abort_flag:
                    self.ffmpeg_proc = None
                    return
                if self.ffmpeg_proc.returncode != 0:
                    if not self.abort_flag:
                        print("CACHE FFMPEG DIRECT ERROR:", stderr.decode())
                    return
                self.ffmpeg_proc = None
                if self.abort_flag: return
                
                self.cache_completed.emit(req.revision, final_dir, fps)
                return

            # ── Chroma Key path: native crop -> chroma -> Lanczos -> 512 ──
            seq_dir = os.path.join(tmp_dir, "seq")
            os.makedirs(seq_dir, exist_ok=True)
            fps_prefix = f"fps={Ffmpeg.inv(fps)},"
            vf = fps_prefix + (f"{pre_key}," if pre_key else "") + "format=rgba"
            
            cmd1 = [req.ffmpeg_path, '-y', '-nostdin', '-hide_banner', '-loglevel', 'error',
                    '-ss', Ffmpeg.inv(req.state.cut_start), '-t', Ffmpeg.inv(dur),
                    '-i', req.source_path, '-vf', vf, os.path.join(seq_dir, "f%05d.png")]
            
            if self.abort_flag: return
            self.ffmpeg_proc = subprocess.Popen(cmd1, stderr=subprocess.PIPE, stdout=subprocess.PIPE)
            stdout1, stderr1 = self.ffmpeg_proc.communicate()
            if self.abort_flag:
                self.ffmpeg_proc = None
                return
            if self.ffmpeg_proc.returncode != 0:
                if not self.abort_flag:
                    print("CACHE FFMPEG1 ERROR:", stderr1.decode())
                return
                
            self.ffmpeg_proc = None
            if self.abort_flag: return
                
            frames = sorted(glob.glob(os.path.join(seq_dir, "f*.png")))
            if not frames: return
            
            scaled_dir = os.path.join(tmp_dir, "scaled")
            os.makedirs(scaled_dir, exist_ok=True)
            
            raw_path = os.path.join(tmp_dir, "raw_all.rgba")
            with open(raw_path, "wb") as rf:
                for i, f in enumerate(frames):
                    if self.abort_flag: return
                    img = Image.open(f).convert('RGBA')
                    img = ChromaKey.apply(img, req.state.key)
                    rf.write(img.tobytes("raw", "RGBA"))
                
            seq_pattern = raw_path
            
            cmd2 = [req.ffmpeg_path, '-y', '-nostdin', '-hide_banner', '-loglevel', 'error',
                    '-f', 'rawvideo', '-pix_fmt', 'rgba', '-s', f'{img.width}x{img.height}',
                    '-framerate', Ffmpeg.inv(fps), '-i', seq_pattern]
            if post_key:
                cmd2.extend(['-vf', post_key])
            cmd2.append(os.path.join(scaled_dir, "f%05d.png"))
                    
            if self.abort_flag: return
            self.ffmpeg_proc = subprocess.Popen(cmd2, stderr=subprocess.PIPE, stdout=subprocess.PIPE)
            stdout2, stderr2 = self.ffmpeg_proc.communicate()
            if self.abort_flag:
                self.ffmpeg_proc = None
                return
            if self.ffmpeg_proc.returncode != 0:
                if not self.abort_flag:
                    print("CACHE FFMPEG2 ERROR:", stderr2.decode())
                return
                
            self.ffmpeg_proc = None
            if self.abort_flag: return
                
            scaled_frames = sorted(glob.glob(os.path.join(scaled_dir, "f*.png")))
            if not scaled_frames: return
            
            for f in scaled_frames:
                if self.abort_flag: return
                img = Image.open(f).convert('RGBA')
                img = ChromaKey.prepare_for_vp9(img, 3)
                _save_rgba_bmp(img, os.path.join(final_dir, os.path.basename(f)[:-4] + ".bmp"))
                
            self.cache_completed.emit(req.revision, final_dir, fps)
        except Exception as e:
            print("CACHE ERROR:", e)
        finally:
            import shutil
            shutil.rmtree(tmp_dir, ignore_errors=True)
