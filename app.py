import sys
import os
from models import EditState, ProbeInfo, KeySettings
from ffmpeg_utils import Ffmpeg
from export_pipeline import ExportPipeline

def main():
    if len(sys.argv) < 3:
        print("Usage: python3 app.py <input_video> <output.webm> [crop=x:y:size] [cut=start:end] [key=RRGGBB:gain:shrink] [fps30]")
        sys.exit(1)
        
    input_path = sys.argv[1]
    output_path = sys.argv[2]
    
    ffmpeg = Ffmpeg.find()
    if not ffmpeg:
        print("Error: ffmpeg not found in PATH")
        sys.exit(2)
        
    info = Ffmpeg.probe(ffmpeg, input_path)
    if not info.ok:
        print(f"Error probing video: {info.error}")
        sys.exit(3)
        
    print(f"Video info: {info.width}x{info.height}, {info.duration}s, {info.fps}fps, alpha={info.has_alpha}")
    
    st = EditState()
    st.cut_start = 0
    st.cut_end = min(info.duration, 6.0)
    
    for arg in sys.argv[3:]:
        if arg.startswith("crop="):
            parts = arg[5:].split(':')
            x, y, s = int(parts[0]), int(parts[1]), int(parts[2])
            st.crop_rect = (x, y, s, s)
        elif arg.startswith("cut="):
            parts = arg[4:].split(':')
            start, end = float(parts[0]), float(parts[1])
            st.cut_start = start
            st.cut_end = end
            if st.cut_end - st.cut_start > 6.0:
                st.cut_end = st.cut_start + 6.0
        elif arg == "fps30":
            st.fps30 = True
        elif arg.startswith("key="):
            parts = arg[4:].split(':')
            rgb = int(parts[0], 16)
            st.key.enabled = True
            st.key.screen_color_r = (rgb >> 16) & 255
            st.key.screen_color_g = (rgb >> 8) & 255
            st.key.screen_color_b = rgb & 255
            if len(parts) > 1:
                st.key.gain = int(parts[1])
            if len(parts) > 2:
                st.key.shrink_grow = int(parts[2])
                
    print("Exporting...")
    res = ExportPipeline.run(ffmpeg, input_path, info, info.has_alpha, st, output_path)
    
    if res.ok:
        print(f"Success! Output: {res.output_path}, Size: {res.size} bytes, Alpha: {res.alpha_in_output}")
    else:
        print(f"Error: {res.error}")
        sys.exit(1)

if __name__ == "__main__":
    main()
