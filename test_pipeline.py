import os
import subprocess
import shutil
from models import EditState, ProbeInfo, KeySettings
from ffmpeg_utils import Ffmpeg
from export_pipeline import ExportPipeline

def make_test_video(name, args):
    cmd = f'ffmpeg -y -f lavfi -i "{args}" -c:v libx264 "{name}"'
    subprocess.run(cmd, shell=True, capture_output=True)

def test_pipeline():
    ffmpeg = Ffmpeg.find()
    assert ffmpeg is not None, "FFmpeg not found"
    
    # 1. MP4 H.264 without alpha
    make_test_video("test_24fps.mp4", "testsrc=duration=2:size=1920x1080:rate=24")
    info = Ffmpeg.probe(ffmpeg, "test_24fps.mp4")
    assert info.ok
    assert info.width == 1920 and info.height == 1080
    assert abs(info.fps - 24) < 0.1
    assert not info.has_alpha
    
    st = EditState(cut_start=0, cut_end=1)
    res = ExportPipeline.run(ffmpeg, "test_24fps.mp4", info, info.has_alpha, st, "out1.webm")
    assert res.ok, f"Export failed: {res.error}"
    assert os.path.exists("out1.webm")
    assert res.size <= 262144
    
    # Check output with ffprobe
    probe_out = Ffmpeg.probe(ffmpeg, "out1.webm")
    # probe_out.ok might be False due to patched duration (нулевая длительность)
    assert probe_out.width == 512 and probe_out.height == 288
    
    # 2. MOV with alpha
    cmd = f'ffmpeg -y -f lavfi -i "color=c=red@0.5:duration=2:size=512x512:rate=30" -c:v qtrle -pix_fmt argb "test_alpha.mov"'
    subprocess.run(cmd, shell=True, capture_output=True)
    info2 = Ffmpeg.probe(ffmpeg, "test_alpha.mov")
    assert info2.ok
    assert info2.has_alpha
    
    res2 = ExportPipeline.run(ffmpeg, "test_alpha.mov", info2, info2.has_alpha, st, "out2.webm")
    assert res2.ok
    assert res2.alpha_in_output
    
    # 3. Chroma key export
    make_test_video("test_green.mp4", "color=c=green:duration=2:size=640x480:rate=50")
    info3 = Ffmpeg.probe(ffmpeg, "test_green.mp4")
    assert abs(info3.fps - 50) < 0.1
    
    st_key = EditState(cut_start=0, cut_end=1)
    st_key.key.enabled = True
    st_key.key.screen_color_r = 0
    st_key.key.screen_color_g = 255
    st_key.key.screen_color_b = 0
    st_key.fps30 = True # force 30fps
    
    res3 = ExportPipeline.run(ffmpeg, "test_green.mp4", info3, info3.has_alpha, st_key, "out3.webm")
    assert res3.ok
    assert res3.alpha_in_output
    
    probe_out3 = Ffmpeg.probe(ffmpeg, "out3.webm")
    assert abs(probe_out3.fps - 30) < 0.1
    
    print("All pipeline tests passed!")
    
    # Cleanup
    for f in ["test_24fps.mp4", "out1.webm", "test_alpha.mov", "out2.webm", "test_green.mp4", "out3.webm"]:
        if os.path.exists(f):
            os.remove(f)

if __name__ == '__main__':
    test_pipeline()
