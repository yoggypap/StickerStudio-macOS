import os
os.environ['OMP_NUM_THREADS'] = '1'
os.environ['OPENBLAS_NUM_THREADS'] = '1'
os.environ['MKL_NUM_THREADS'] = '1'
os.environ['VECLIB_MAXIMUM_THREADS'] = '1'
os.environ['NUMEXPR_NUM_THREADS'] = '1'

import sys, copy, subprocess, shutil, numpy as np
from PIL import Image, ImageDraw, ImageChops
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import Qt, QPointF, QSize, QRectF, QEventLoop, QTimer
from PySide6.QtGui import QImage, QPixmap, QMouseEvent

from models import ProbeInfo, EditState, KeySettings
from video_doc import VideoDoc
from ffmpeg_utils import Ffmpeg
from chroma_key import ChromaKey
from preview_renderer import PreviewRenderer, ExactPreviewRequest
from export_pipeline import ExportPipeline
from preview_widget import PreviewWidget

# ─────────────────────────────────────────────────────────────────────────────
# 1. Synthetic Fixture Helper
# ─────────────────────────────────────────────────────────────────────────────
def create_synthetic_frame(w, h, bg_color=(0, 255, 0)):
    img = Image.new("RGBA", (w, h), (*bg_color, 255))
    draw = ImageDraw.Draw(img)
    # Foreground Red rectangle
    draw.rectangle([w // 8, h // 8, 3 * w // 8, 3 * h // 8], fill=(255, 30, 30, 255))
    # Foreground Blue circle
    draw.ellipse([5 * w // 8, h // 8, 7 * w // 8, 3 * h // 8], fill=(30, 30, 255, 255))
    # Fine details: 1px thin diagonal lines
    for i in range(8):
        draw.line([(w // 4 + i * 4, h // 2), (w // 4 + i * 4 + 30, h // 2 + 60)], fill=(240, 240, 50, 255), width=1)
    # Semi-transparent gradient edge
    for step in range(40):
        alpha = int(255 * (1.0 - step / 40.0))
        draw.line([(w // 2 + step, h // 2), (w // 2 + step, h // 2 + 80)], fill=(255, 128, 0, alpha), width=1)
    # Near-key colors: yellow-green and cyan
    draw.rectangle([w // 8, 3 * h // 4, 2 * w // 8, h - 20], fill=(140, 255, 0, 255))
    draw.rectangle([3 * w // 8, 3 * h // 4, 4 * w // 8, h - 20], fill=(0, 255, 180, 255))
    return img

def create_synthetic_video(path, w, h, frames_count=8, bg_color=(0, 255, 0)):
    temp_dir = f"temp_synth_{w}x{h}"
    os.makedirs(temp_dir, exist_ok=True)
    try:
        for i in range(frames_count):
            frame = create_synthetic_frame(w, h, bg_color)
            frame.convert("RGB").save(os.path.join(temp_dir, f"f_{i:03d}.png"))
        cmd = f'ffmpeg -y -hide_banner -loglevel error -framerate 10 -i "{temp_dir}/f_%03d.png" -c:v libx264 -pix_fmt yuv420p "{path}"'
        subprocess.run(cmd, shell=True, check=True)
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)

# ─────────────────────────────────────────────────────────────────────────────
# Test 1: Direct Chroma Math Ranges, Monotonicity, and Edge Cases
# ─────────────────────────────────────────────────────────────────────────────
def test_chroma_math():
    print("--- Test 1: Chroma Math (Ranges, Monotonicity, Edge Cases) ---")
    w, h = 200, 200
    img = create_synthetic_frame(w, h, (0, 255, 0))

    # A) Gain range 0..200: no NaN/Inf, alpha in [0..255]
    for gain in [0, 25, 50, 100, 150, 200]:
        ks = KeySettings(enabled=True, screen_color_r=0, screen_color_g=255, screen_color_b=0, gain=gain, shrink_grow=0)
        res = ChromaKey.apply(img, ks)
        arr = np.array(res)
        assert not np.isnan(arr).any(), f"NaN at gain={gain}"
        assert not np.isinf(arr).any(), f"Inf at gain={gain}"
        assert arr[:, :, 3].min() >= 0 and arr[:, :, 3].max() <= 255

    # B) Monotonicity: higher gain removes at least as much green as lower gain
    ks_50 = KeySettings(enabled=True, screen_color_r=0, screen_color_g=255, screen_color_b=0, gain=50, shrink_grow=0)
    ks_150 = KeySettings(enabled=True, screen_color_r=0, screen_color_g=255, screen_color_b=0, gain=150, shrink_grow=0)
    arr_50 = np.array(ChromaKey.apply(img, ks_50))[:, :, 3]
    arr_150 = np.array(ChromaKey.apply(img, ks_150))[:, :, 3]
    assert np.count_nonzero(arr_50 > 10) >= np.count_nonzero(arr_150 > 10)

    # C) Shrink / Grow -100..100: shrink reduces opaque mask, grow expands it
    ks_zero = KeySettings(enabled=True, screen_color_r=0, screen_color_g=255, screen_color_b=0, gain=100, shrink_grow=0)
    ks_shrink = KeySettings(enabled=True, screen_color_r=0, screen_color_g=255, screen_color_b=0, gain=100, shrink_grow=-50)
    ks_grow = KeySettings(enabled=True, screen_color_r=0, screen_color_g=255, screen_color_b=0, gain=100, shrink_grow=50)

    nz_zero = np.count_nonzero(np.array(ChromaKey.apply(img, ks_zero))[:, :, 3] > 128)
    nz_shrink = np.count_nonzero(np.array(ChromaKey.apply(img, ks_shrink))[:, :, 3] > 128)
    nz_grow = np.count_nonzero(np.array(ChromaKey.apply(img, ks_grow))[:, :, 3] > 128)

    assert nz_shrink <= nz_zero, f"Shrink failed: {nz_shrink} > {nz_zero}"
    assert nz_grow >= nz_zero, f"Grow failed: {nz_grow} < {nz_zero}"

    # D) Edge fixtures: dark green, uneven green
    for bg_color in [(0, 80, 0), (20, 230, 30)]:
        synth = create_synthetic_frame(200, 200, bg_color)
        ks_bg = KeySettings(enabled=True, screen_color_r=bg_color[0], screen_color_g=bg_color[1], screen_color_b=bg_color[2], gain=110)
        res_bg = np.array(ChromaKey.apply(synth, ks_bg))
        # Background at (5, 5) must be removed
        assert res_bg[5, 5, 3] < 30, f"Background not transparent for bg {bg_color}"
        # Foreground red box at (30, 30) must be preserved
        assert res_bg[30, 30, 3] > 220, f"Foreground corrupted for bg {bg_color}"

    print("PASS: test_chroma_math")

# ─────────────────────────────────────────────────────────────────────────────
# Test 2: Pipette Coordinate Accuracy Across Aspect Ratios & Active Crop
# ─────────────────────────────────────────────────────────────────────────────
def test_pipette_geometries():
    print("--- Test 2: Pipette Coordinate Accuracy (Aspect Ratios & Active Crop) ---")
    app = QApplication.instance() or QApplication(sys.argv)

    cases = [
        (1920, 1080, None, "Landscape 16:9"),
        (1080, 1920, None, "Portrait 9:16"),
        (1080, 1080, None, "Square 1:1"),
        (1920, 1080, (400, 100, 800, 800), "Landscape with Square Crop"),
    ]

    for orig_w, orig_h, crop, label in cases:
        # Create 4 distinct quadrants: RED, BLUE, YELLOW, MAGENTA
        img = Image.new("RGBA", (orig_w, orig_h), (0, 255, 0, 255))
        draw = ImageDraw.Draw(img)
        draw.rectangle([0, 0, orig_w // 2, orig_h // 2], fill=(255, 0, 0, 255))
        draw.rectangle([orig_w // 2, 0, orig_w, orig_h // 2], fill=(0, 0, 255, 255))
        draw.rectangle([0, orig_h // 2, orig_w // 2, orig_h], fill=(255, 255, 0, 255))
        draw.rectangle([orig_w // 2, orig_h // 2, orig_w, orig_h], fill=(255, 0, 255, 255))

        doc = VideoDoc()
        doc.info = ProbeInfo(width=orig_w, height=orig_h, duration=1.0, fps=10.0)
        scale = 512.0 / max(orig_w, orig_h)
        doc.preview_w = int(round(orig_w * scale))
        doc.preview_h = int(round(orig_h * scale))
        if crop:
            doc.state.crop_rect = crop

        preview_img = img.resize((doc.preview_w, doc.preview_h), Image.Resampling.BILINEAR)
        qimg = QImage(preview_img.tobytes("raw", "RGBA"), doc.preview_w, doc.preview_h, QImage.Format_RGBA8888)
        pixmap = QPixmap.fromImage(qimg)

        pw = PreviewWidget()
        pw.resize(600, 500)
        pw.set_frame(doc, pixmap, 0)
        pw.pick_mode = True

        picked = []
        pw.color_picked.connect(lambda r, g, b: picked.append((r, g, b)))
        img_rect = pw.get_image_rect()
        assert not img_rect.isEmpty()

        # Sample the center of each of the 4 quadrants within img_rect
        quadrants = [(0.25, 0.25), (0.75, 0.25), (0.25, 0.75), (0.75, 0.75)]
        for u, v in quadrants:
            picked.clear()
            click_pt = QPointF(img_rect.x() + u * img_rect.width(), img_rect.y() + v * img_rect.height())
            pw.mousePressEvent(QMouseEvent(QMouseEvent.Type.MouseButtonPress, click_pt,
                                          Qt.MouseButton.LeftButton, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier))
            assert len(picked) == 1, f"Failed to pick in {label}"
            pr, pg, pb = picked[0]

            if crop:
                cx = crop[0] + u * crop[2]
                cy = crop[1] + v * crop[3]
            else:
                cx = u * orig_w
                cy = v * orig_h
            er, eg, eb, _ = img.getpixel((int(cx), int(cy)))
            assert abs(pr - er) < 25 and abs(pg - eg) < 25 and abs(pb - eb) < 25, \
                f"Pipette mismatch in {label}: picked ({pr},{pg},{pb}) vs expected ({er},{eg},{eb})"

        # Verify clicking outside img_rect does not sample
        picked.clear()
        out_pt = QPointF(img_rect.right() + 40, img_rect.bottom() + 40)
        pw.mousePressEvent(QMouseEvent(QMouseEvent.Type.MouseButtonPress, out_pt,
                                      Qt.MouseButton.LeftButton, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier))
        assert len(picked) == 0, "Pipette clicked outside img_rect but emitted color"

    print("PASS: test_pipette_geometries")

# ─────────────────────────────────────────────────────────────────────────────
# Test 3: Apply / Cancel / Undo Document State Transitions
# ─────────────────────────────────────────────────────────────────────────────
def test_key_state_lifecycle():
    print("--- Test 3: Apply / Cancel / Undo State Transitions ---")
    doc = VideoDoc()
    doc.state = EditState()
    initial_key = copy.deepcopy(doc.state.key)
    assert not initial_key.enabled

    # Simulate entering Chroma Key mode
    editing_key = KeySettings(enabled=True, screen_color_r=0, screen_color_g=250, screen_color_b=10, gain=140, shrink_grow=15)

    # 1. Cancel transition: state must remain identical to initial
    # (Cancel discards editing_key without pushing undo)
    assert doc.state.key == initial_key, "State modified before apply"

    # 2. Apply transition: doc pushes undo and updates state
    doc.push_undo()
    doc.state.key = copy.deepcopy(editing_key)
    assert doc.state.key.enabled == True
    assert doc.state.key.gain == 140
    assert doc.state.key.shrink_grow == 15

    # 3. Undo transition: pops state from undo stack
    doc.undo()
    assert doc.state.key.enabled == initial_key.enabled
    assert doc.state.key.gain == initial_key.gain

    print("PASS: test_key_state_lifecycle")

# ─────────────────────────────────────────────────────────────────────────────
# Test 4: Export Pipeline Alpha Verification
# ─────────────────────────────────────────────────────────────────────────────
def test_export_pipeline_alpha():
    print("--- Test 4: Export Pipeline Alpha Channel (yuva420p) ---")
    ffmpeg = Ffmpeg.find()
    assert ffmpeg is not None

    test_vid = "chroma_val_test.mp4"
    out_webm = "chroma_val_out.webm"
    create_synthetic_video(test_vid, 640, 480, frames_count=8, bg_color=(0, 255, 0))

    try:
        doc = VideoDoc()
        doc.load(ffmpeg, test_vid)
        doc.state.crop_rect = (60, 60, 360, 360)
        doc.state.key = KeySettings(enabled=True, screen_color_r=0, screen_color_g=255, screen_color_b=0, gain=100, shrink_grow=0)

        res = ExportPipeline.run(ffmpeg, doc.source_path, doc.info, False, doc.state, out_webm)
        assert res.ok, f"Export failed: {res.error}"

        # Verify pixel format has alpha (yuva420p via libvpx-vp9 decoder)
        probe_cmd = f'ffprobe -v error -c:v libvpx-vp9 -select_streams v:0 -show_entries stream=pix_fmt -of default=noprint_wrappers=1:nokey=1 "{out_webm}"'
        pix_fmt = subprocess.check_output(probe_cmd, shell=True).decode().strip()
        assert pix_fmt == "yuva420p", f"Expected yuva420p, got {pix_fmt}"

        # Decode a frame and inspect alpha mask
        frame_png = "chroma_val_frame.png"
        subprocess.run(f'ffmpeg -y -hide_banner -loglevel error -ss 0.2 -c:v libvpx-vp9 -i "{out_webm}" -vframes 1 "{frame_png}"', shell=True, check=True)
        img = Image.open(frame_png).convert("RGBA")
        alpha = np.array(img)[:, :, 3]
        assert np.count_nonzero(alpha < 50) > 1000, "Exported WebM lacks transparency"
        assert np.count_nonzero(alpha > 200) > 1000, "Exported WebM lacks opaque foreground"

        print("PASS: test_export_pipeline_alpha")
    finally:
        for f in [test_vid, out_webm, "chroma_val_frame.png"]:
            if os.path.exists(f): os.remove(f)

# ─────────────────────────────────────────────────────────────────────────────
# Test 5: WYSIWYG Consistency (Exact Preview vs Decoded WebM)
# ─────────────────────────────────────────────────────────────────────────────
def test_wysiwyg_consistency():
    print("--- Test 5: WYSIWYG Consistency (Exact Preview vs Decoded WebM) ---")
    app = QApplication.instance() or QApplication(sys.argv)
    ffmpeg = Ffmpeg.find()
    assert ffmpeg is not None

    test_vid = "chroma_wysiwyg.mp4"
    out_webm = "chroma_wysiwyg.webm"
    create_synthetic_video(test_vid, 640, 480, frames_count=8, bg_color=(0, 255, 0))

    try:
        doc = VideoDoc()
        doc.load(ffmpeg, test_vid)
        doc.state.crop_rect = (50, 50, 400, 400)
        doc.state.key = KeySettings(enabled=True, screen_color_r=0, screen_color_g=255, screen_color_b=0, gain=100, shrink_grow=0)

        # 1. Exact Preview Request
        renderer = PreviewRenderer()
        req = ExactPreviewRequest()
        req.revision = 1
        req.ffmpeg_path = ffmpeg
        req.source_path = doc.source_path
        req.info = doc.info
        req.time = 0.2
        req.state = doc.state

        exact_qimg = []
        renderer.exact_completed.connect(lambda rev, qimg: exact_qimg.append(qimg))
        renderer.request_exact(req)

        loop = QEventLoop()
        def check():
            if exact_qimg: loop.quit()
        t = QTimer()
        t.timeout.connect(check)
        t.start(50)
        QTimer.singleShot(6000, loop.quit)
        loop.exec()

        assert len(exact_qimg) == 1 and exact_qimg[0] is not None, "Exact preview failed"
        ex_pil = Image.frombytes("RGBA", (512, 512), bytes(exact_qimg[0].bits())).convert("RGBA")

        # 2. Export WebM
        res = ExportPipeline.run(ffmpeg, doc.source_path, doc.info, False, doc.state, out_webm)
        assert res.ok, f"Export failed: {res.error}"

        # 3. Decoded WebM Frame
        frame_png = "chroma_wysiwyg_frame.png"
        subprocess.run(f'ffmpeg -y -hide_banner -loglevel error -ss 0.2 -c:v libvpx-vp9 -i "{out_webm}" -vframes 1 "{frame_png}"', shell=True, check=True)
        wb_pil = Image.open(frame_png).convert("RGBA")

        # 4. Compare Exact vs WebM
        diff = ImageChops.difference(ex_pil, wb_pil)
        stat = diff.convert('L')
        hist = stat.histogram()
        total_diff = sum(i * hist[i] for i in range(256))
        avg_diff = total_diff / (512 * 512)
        print(f"Average pixel diff Exact Preview vs WebM: {avg_diff:.2f}")
        assert avg_diff < 15.0, f"WYSIWYG diff too high: {avg_diff}"

        print("PASS: test_wysiwyg_consistency")
    finally:
        for f in [test_vid, out_webm, "chroma_wysiwyg_frame.png"]:
            if os.path.exists(f): os.remove(f)

if __name__ == "__main__":
    test_chroma_math()
    test_pipette_geometries()
    test_key_state_lifecycle()
    test_export_pipeline_alpha()
    test_wysiwyg_consistency()
    print("\nALL 5 CHROMA VALIDATION TESTS PASSED SUCCESSFULLY!")
