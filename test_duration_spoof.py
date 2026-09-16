"""
Test EBML Duration spoofing for clips > 10s.
Requirements:
- Source clip > 10s (e.g. 11s)
- Decoded packet/frame timestamps reach > 10s
- Container/Segment Duration reports ~2.9s (2900ms)
"""
import os
import subprocess
import shutil
from patcher import Patcher
from ffmpeg_utils import Ffmpeg
from models import EditState, ProbeInfo
from export_pipeline import ExportPipeline

def test_duration_spoof():
    ffmpeg = Ffmpeg.find()
    assert ffmpeg is not None, "FFmpeg not found"

    input_file = "/tmp/test_11s.mp4"
    output_file = "/tmp/test_11s_out.webm"

    # 1. Create an 11-second video
    subprocess.run([
        ffmpeg, "-y", "-f", "lavfi",
        "-i", "testsrc=duration=11:size=320x240:rate=25",
        "-c:v", "libx264", input_file
    ], capture_output=True, check=True)

    # 2. Probe input video
    info = Ffmpeg.probe(ffmpeg, input_file)
    assert info.ok, f"Probe failed: {info.error}"
    assert info.duration >= 10.9, f"Input duration should be >= 10.9s, got {info.duration}"

    # 3. Export full 11s
    state = EditState(cut_start=0.0, cut_end=11.0)
    res = ExportPipeline.run(ffmpeg, input_file, info, False, state, output_file)
    assert res.ok, f"Export failed: {res.error}"
    assert os.path.exists(output_file)

    # 4. Check container duration via ffprobe format=duration
    cmd_probe = f'ffprobe -v error -show_entries format=duration -of default=noprint_wrappers=1:nokey=1 "{output_file}"'
    proc = subprocess.run(cmd_probe, shell=True, capture_output=True, text=True)
    duration_str = proc.stdout.strip()
    container_duration = float(duration_str)
    print(f"Container duration: {container_duration:.3f}s")
    # Container duration must be ~2.9s
    assert abs(container_duration - 2.9) < 0.1, f"Container duration should be ~2.9s, got {container_duration}"

    # 5. Check decoded packet/frame timestamps reach > 10s
    cmd_frames = f'ffprobe -v error -select_streams v:0 -show_entries packet=pts_time -of default=noprint_wrappers=1:nokey=1 "{output_file}"'
    proc_frames = subprocess.run(cmd_frames, shell=True, capture_output=True, text=True)
    pts_list = [float(line.strip()) for line in proc_frames.stdout.splitlines() if line.strip()]
    assert len(pts_list) > 0, "No packets found"
    max_pts = max(pts_list)
    print(f"Max decoded packet timestamp: {max_pts:.3f}s (total packets: {len(pts_list)})")
    assert max_pts > 10.0, f"Max packet timestamp should be > 10.0s, got {max_pts}"

    # Cleanup
    for f in [input_file, output_file]:
        if os.path.exists(f):
            os.remove(f)

    print("PASS: test_duration_spoof")

if __name__ == "__main__":
    test_duration_spoof()
