import sys, os, time, subprocess
from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QImage
from PySide6.QtCore import QTimer, QCoreApplication
from models import EditState, KeySettings
from video_doc import VideoDoc
from ffmpeg_utils import Ffmpeg
from preview_renderer import PreviewRenderer, ExactPreviewRequest
from export_pipeline import ExportPipeline
from PIL import Image, ImageChops, ImageMath
import math

# Create synthetic video: green background, red object, soft edge
# We can use ffmpeg drawbox/drawtext or just python to generate a short image sequence and encode it
frames_dir = "wysiwyg_frames"
os.makedirs(frames_dir, exist_ok=True)
for i in range(10):
    img = Image.new("RGB", (640, 480), (0, 255, 0)) # Green bg
    # Red object with soft edges
    import PIL.ImageDraw as ImageDraw
    d = ImageDraw.Draw(img)
    # Draw some red box
    d.rectangle([100, 100, 300, 300], fill=(255, 0, 0))
    # Draw semi-transparent gradient
    for x in range(300, 350):
        alpha = int(255 * (1.0 - (x - 300) / 50.0))
        d.line([(x, 100), (x, 300)], fill=(255, 0, 0))
        
    # Blue object
    d.ellipse([400, 200, 500, 300], fill=(0, 0, 255))
    img.save(f"{frames_dir}/f_{i:03d}.png")

test_vid = "wysiwyg_test.mp4"
subprocess.run(f'ffmpeg -y -hide_banner -loglevel error -framerate 10 -i "{frames_dir}/f_%03d.png" -c:v libx264 -pix_fmt yuv420p {test_vid}', shell=True)

app = QCoreApplication(sys.argv)
ffmpeg = Ffmpeg.find()

doc = VideoDoc()
doc.load(ffmpeg, test_vid)
doc.state.cut_start = 0.0
doc.state.cut_end = 0.5
doc.state.crop_rect = (50, 50, 400, 400)
doc.state.key = KeySettings()
doc.state.key.enabled = True
doc.state.key.screen_color_r = 0
doc.state.key.screen_color_g = 255
doc.state.key.screen_color_b = 0
doc.state.key.gain = 100
doc.state.key.shrink_grow = 5

req = ExactPreviewRequest()
req.revision = 1
req.ffmpeg_path = ffmpeg
req.source_path = doc.source_path
req.info = doc.info
req.time = 0.2
req.state = doc.state

renderer = PreviewRenderer()
exact_qimg = None

def on_exact(rev, qimg):
    global exact_qimg
    exact_qimg = qimg
    app.quit()
    
renderer.exact_completed.connect(on_exact)
renderer.request_exact(req)

# Start event loop with timeout
QTimer.singleShot(10000, app.quit)
app.exec()

if exact_qimg is None:
    print("Exact preview failed to render")
    sys.exit(1)

exact_qimg.save("wysiwyg_exact.png")

# Now export
out_webm = "wysiwyg_out.webm"
res = ExportPipeline.run(ffmpeg, doc.source_path, doc.info, False, doc.state, out_webm)
if not res.ok:
    print("Export failed:", res.error)
    sys.exit(1)

# Extract frame from webm
webm_frame = "wysiwyg_webm_frame.png"
subprocess.run(f'ffmpeg -y -hide_banner -loglevel error -ss 0.2 -i {out_webm} -vframes 1 {webm_frame}', shell=True)

# Compare exact_qimg and webm_frame
img_ex = Image.open("wysiwyg_exact.png").convert("RGBA")
img_wb = Image.open(webm_frame).convert("RGBA")

# Ensure size match
assert img_ex.size == img_wb.size, f"Size mismatch: {img_ex.size} vs {img_wb.size}"
assert img_ex.size == (512, 512), "Should be 512x512"

# Compute diff
diff = ImageChops.difference(img_ex, img_wb)
stat = diff.convert('L')
hist = stat.histogram()
# calculate average pixel difference
total = sum(i * hist[i] for i in range(256))
avg_diff = total / (512 * 512)
print(f"Average pixel difference between Exact Preview and VP9 WebM: {avg_diff:.2f}")

# It shouldn't be identical because VP9 is lossy, but should be < 5.0
assert avg_diff < 15.0, f"Too much difference: {avg_diff}"

print("WYSIWYG test passed!")
