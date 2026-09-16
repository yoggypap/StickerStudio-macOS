import os
import shutil
import glob
import uuid
import tempfile
from PIL import Image
from models import ProbeInfo, EditState
from geometry import FrameGeometry
from ffmpeg_utils import Ffmpeg
from patcher import Patcher
from chroma_key import ChromaKey

class ExportResult:
    def __init__(self):
        self.ok = False
        self.error = ""
        self.output_path = ""
        self.size = 0
        self.alpha_in_output = False
        self.fps_warning = False

class ExportPipeline:
    @staticmethod
    def run(ffmpeg: str, source_path: str, info: ProbeInfo, source_has_alpha: bool,
            state: EditState, output_path: str, progress=None) -> ExportResult:
        res = ExportResult()
        dur = state.cut_end - state.cut_start
        if dur < 0.1:
            res.error = "Слишком короткий отрезок"
            return res
            
        keyed = state.key is not None and state.key.enabled
        alpha_out = source_has_alpha or keyed
        res.alpha_in_output = alpha_out
        res.fps_warning = info.fps > 31 and not state.fps30
        
        fps_prefix = "fps=30," if state.fps30 else ""
        
        geometry = FrameGeometry.create(info, state.crop_rect)
        pre_key_filter = geometry.pre_key_filter
        post_key_filter = geometry.post_key_filter
        scale_filter = f"{pre_key_filter},{post_key_filter}" if pre_key_filter else post_key_filter
        
        cut_args = f" -ss {Ffmpeg.inv(state.cut_start)} -t {Ffmpeg.inv(dur)}"
        
        tmp_dir = os.path.join(tempfile.gettempdir(), "sse_" + uuid.uuid4().hex)
        os.makedirs(tmp_dir, exist_ok=True)
        
        try:
            fps = 30.0 if state.fps30 else (info.fps if info.fps > 0 else 30.0)
            
            if progress:
                progress("Подготовка кадров...")
            if keyed:
                seq_dir = os.path.join(tmp_dir, "seq")
                os.makedirs(seq_dir, exist_ok=True)
                
                key_prep_filter = fps_prefix + (f"{pre_key_filter}," if pre_key_filter else "") + "format=rgba"
                seq_pattern = os.path.join(seq_dir, "f%05d.png")
                
                cmd1 = f'-y -hide_banner -loglevel error -i "{source_path}"{cut_args} -vf "{key_prep_filter}" "{seq_pattern}"'
                c1, e1 = Ffmpeg.run(ffmpeg, cmd1)
                if c1 != 0:
                    res.error = "Ошибка обработки: " + Ffmpeg.last_line(e1)
                    return res
                    
                frames = sorted(glob.glob(os.path.join(seq_dir, "f*.png")))
                if not frames:
                    res.error = "Кадры не извлеклись"
                    return res
                    
                total_frames = len(frames)
                for i, f in enumerate(frames):
                    if progress and i % 5 == 0:
                        progress(f"Удаление фона... {int(i * 100 / total_frames)}%")
                    img = Image.open(f).convert('RGBA')
                    img = ChromaKey.apply(img, state.key)
                    img.save(f, 'PNG')
                if progress:
                    progress("Удаление фона... 100%")
                    
                scaled_dir = os.path.join(tmp_dir, "scaled")
                os.makedirs(scaled_dir, exist_ok=True)
                
                scaled_pattern = os.path.join(scaled_dir, "f%05d.png")
                cmd2 = f'-y -hide_banner -loglevel error -framerate {Ffmpeg.inv(fps)} -i "{seq_pattern}" -vf "{post_key_filter}" "{scaled_pattern}"'
                c2, e2 = Ffmpeg.run(ffmpeg, cmd2)
                if c2 != 0:
                    res.error = "Ошибка очистки кромки: " + Ffmpeg.last_line(e2)
                    return res
                    
                scaled_frames = sorted(glob.glob(os.path.join(scaled_dir, "f*.png")))
                if not scaled_frames:
                    res.error = "Не удалось подготовить кромку"
                    return res
                    
                for f in scaled_frames:
                    img = Image.open(f).convert('RGBA')
                    img = ChromaKey.prepare_for_vp9(img, 3)
                    img.save(f, 'PNG')
                    
                encode_input = scaled_pattern
                encode_input_args = f"-framerate {Ffmpeg.inv(fps)} -i "
            else:
                encode_input = source_path
                encode_input_args = "-i "
                
            pix_fmt = "yuva420p" if alpha_out else "yuv420p"
            kbps = int(Ffmpeg.SIZE_TARGET * 8 / dur * 0.93 / 1000.0)
            kbps = max(30, kbps)
            
            out_tmp = os.path.join(tmp_dir, "out.webm")
            best_tmp = os.path.join(tmp_dir, "best.webm")
            best_size = -1
            
            for attempt in range(1, 5):
                if progress:
                    progress(f"Кодирование, попытка {attempt} ({kbps} кбит/с)...")
                pass_log = os.path.join(tmp_dir, f"2p_{attempt}")
                
                vf = "setsar=1" if keyed else fps_prefix + scale_filter
                
                common = (
                    f' {encode_input_args}"{encode_input}"'
                    + ("" if keyed else cut_args)
                    + " -an -sn -map_metadata -1"
                    + ("" if keyed else " -map 0:v:0")
                    + f" -c:v libvpx-vp9 -pix_fmt {pix_fmt}"
                    + f" -b:v {kbps}k -minrate {kbps // 2}k -maxrate {kbps * 3 // 2}k"
                    + f' -vf "{vf}"'
                    + ' -deadline good -cpu-used 0 -aq-mode 1 -sharpness 2'
                    + ' -row-mt 1 -auto-alt-ref 0'
                    + f' -passlogfile "{pass_log}"'
                )
                
                cmd_pass1 = f'-y -hide_banner -loglevel error{common} -pass 1 -f null /dev/null'
                c1, e1 = Ffmpeg.run(ffmpeg, cmd_pass1)
                if c1 != 0:
                    res.error = "Ошибка кодирования: " + Ffmpeg.last_line(e1)
                    return res
                    
                cmd_pass2 = f'-y -hide_banner -loglevel error{common} -pass 2 "{out_tmp}"'
                c2, e2 = Ffmpeg.run(ffmpeg, cmd_pass2)
                if c2 != 0 or not os.path.exists(out_tmp):
                    res.error = "Ошибка кодирования: " + Ffmpeg.last_line(e2)
                    return res
                    
                size = os.path.getsize(out_tmp)
                if size <= Ffmpeg.SIZE_LIMIT and size > best_size:
                    shutil.copy2(out_tmp, best_tmp)
                    best_size = size
                    
                if size <= Ffmpeg.SIZE_LIMIT and size >= Ffmpeg.SIZE_LIMIT * 6 // 10:
                    break
                    
                if size > Ffmpeg.SIZE_LIMIT:
                    kbps = int(kbps * float(Ffmpeg.SIZE_TARGET) / size * 0.92)
                    kbps = max(20, kbps)
                else:
                    if attempt >= 2:
                        break
                    kbps = int(min(6000, kbps * float(Ffmpeg.SIZE_TARGET) / max(size, 1) * 0.95))
                    
            if best_size < 0:
                res.error = "Не удалось ужать в 256 КБ (слишком длинный/сложный ролик)"
                return res
                
            with open(best_tmp, "rb") as f:
                data = bytearray(f.read())
            Patcher.patch_bytes(data)
            with open(output_path, "wb") as f:
                f.write(data)
                
            res.ok = True
            res.output_path = output_path
            res.size = best_size
            return res
            
        except Exception as ex:
            import traceback
            traceback.print_exc()
            res.error = str(ex)
            return res
        finally:
            shutil.rmtree(tmp_dir, ignore_errors=True)
