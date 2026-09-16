import sys, os, time, math, glob, subprocess, shutil
import numpy as np
from PIL import Image, ImageDraw
from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QImage
from PySide6.QtCore import QEventLoop, QTimer, QSize
from models import EditState, KeySettings
from video_doc import VideoDoc
from ffmpeg_utils import Ffmpeg
from preview_renderer import PreviewRenderer, ExactPreviewRequest, PlaybackCacheRequest
from geometry import FrameGeometry

def compute_psnr(img1: np.ndarray, img2: np.ndarray) -> tuple[float, float]:
    """Returns (mae, psnr) for two RGB/RGBA uint8 arrays."""
    diff = np.abs(img1.astype(np.float64) - img2.astype(np.float64))
    mae = float(np.mean(diff))
    mse = float(np.mean(diff ** 2))
    if mse == 0:
        return 0.0, 100.0
    psnr = 10.0 * math.log10((255.0 ** 2) / mse)
    return mae, psnr

def main():
    app = QApplication(sys.argv)
    ffmpeg = Ffmpeg.find()
    assert ffmpeg, "ffmpeg not found"

    tmp_test_dir = "/tmp/ss_test_crop_playback"
    os.makedirs(tmp_test_dir, exist_ok=True)
    frames_dir = os.path.join(tmp_test_dir, "wide_frames")
    os.makedirs(frames_dir, exist_ok=True)

    # 1. Create synthetic ultra-wide 1920x800 video with high-frequency details
    width, height = 1920, 800
    fps = 24
    num_frames = 12
    for i in range(num_frames):
        img = Image.new("RGB", (width, height), (30, 30, 40))
        d = ImageDraw.Draw(img)
        
        # Fine grid / checkerboard
        for y in range(0, height, 40):
            d.line([(0, y), (width, y)], fill=(60, 60, 80), width=1)
        for x in range(0, width, 40):
            d.line([(x, 0), (x, height)], fill=(60, 60, 80), width=1)

        # Center green background for chroma testing
        d.rectangle([600, 100, 1320, 700], fill=(0, 255, 0))

        # Sharp geometric shapes inside the crop area
        d.rectangle([700, 200, 900, 400], fill=(255, 50, 50))
        d.ellipse([1000, 300, 1200, 500], fill=(50, 150, 255))
        d.polygon([(850, 450), (950, 600), (750, 600)], fill=(255, 220, 0))

        # Moving dot
        cx = 700 + (i * 35) % 500
        d.ellipse([cx, 150, cx + 30, 180], fill=(255, 255, 255))

        img.save(os.path.join(frames_dir, f"f_{i:03d}.png"))

    test_vid = os.path.join(tmp_test_dir, "wide_test.mp4")
    subprocess.run(
        f'"{ffmpeg}" -y -hide_banner -loglevel error -framerate {fps} -i "{frames_dir}/f_%03d.png" -c:v libx264 -pix_fmt yuv420p "{test_vid}"',
        shell=True, check=True
    )

    doc = VideoDoc()
    err = doc.load(ffmpeg, test_vid)
    assert not err, f"Failed to load video: {err}"
    assert doc.info.width == 1920 and doc.info.height == 800

    # Square crop in native source coordinates: 800x800 centered
    crop_x = (1920 - 800) // 2 # 560
    crop_y = 0
    crop_w = 800
    crop_h = 800
    doc.state.crop_rect = (crop_x, crop_y, crop_w, crop_h)
    doc.state.cut_start = 0.0
    doc.state.cut_end = 0.45

    print("\n========================================================")
    print("TEST 1: Non-Chroma Cropped Playback vs Exact Preview")
    print("========================================================")
    
    renderer = PreviewRenderer()
    
    # Request exact frame at t = 0.2s
    exact_qimg = None
    loop_exact = QEventLoop()
    def on_exact(rev, qimg):
        nonlocal exact_qimg
        exact_qimg = qimg
        loop_exact.quit()
    renderer.exact_completed.connect(on_exact)

    req_ex = ExactPreviewRequest()
    req_ex.revision = 1
    req_ex.ffmpeg_path = ffmpeg
    req_ex.source_path = doc.source_path
    req_ex.info = doc.info
    req_ex.time = 0.2
    req_ex.state = doc.state
    renderer.request_exact(req_ex)
    QTimer.singleShot(5000, loop_exact.quit)
    loop_exact.exec()

    assert exact_qimg is not None, "Exact preview failed to render"
    assert exact_qimg.width() == 512 and exact_qimg.height() == 512, f"Exact preview size is {exact_qimg.width()}x{exact_qimg.height()}, expected 512x512"

    # Request playback cache
    cache_dir = None
    cache_fps = None
    loop_cache = QEventLoop()
    def on_cache(rev, folder, fps_val):
        nonlocal cache_dir, cache_fps
        cache_dir = folder
        cache_fps = fps_val
        loop_cache.quit()
    renderer.cache_completed.connect(on_cache)

    req_cache = PlaybackCacheRequest()
    req_cache.revision = 1
    req_cache.ffmpeg_path = ffmpeg
    req_cache.source_path = doc.source_path
    req_cache.info = doc.info
    req_cache.state = doc.state
    renderer.request_cache(req_cache)
    QTimer.singleShot(10000, loop_cache.quit)
    loop_cache.exec()

    assert cache_dir is not None and os.path.exists(cache_dir), "Cache failed to generate"
    cached_files = sorted(glob.glob(os.path.join(cache_dir, "f*.bmp")))
    assert len(cached_files) > 0, "No cached BMP frames found"

    # Select frame corresponding to t = 0.2s
    idx = int(round(0.2 * cache_fps))
    idx = max(0, min(len(cached_files) - 1, idx))
    playback_qimg = QImage(cached_files[idx])
    assert not playback_qimg.isNull(), "Failed to load cached playback frame"
    assert playback_qimg.width() == 512 and playback_qimg.height() == 512, f"Playback size is {playback_qimg.width()}x{playback_qimg.height()}, expected 512x512"

    # Convert both to numpy arrays for image quality comparison
    def qimage_to_rgb_array(qimg: QImage) -> np.ndarray:
        converted = qimg.convertToFormat(QImage.Format.Format_RGB888)
        w, h = converted.width(), converted.height()
        b = converted.bits()
        return np.frombuffer(b, dtype=np.uint8).reshape((h, w, 3)).copy()

    exact_arr = qimage_to_rgb_array(exact_qimg)
    playback_arr = qimage_to_rgb_array(playback_qimg)

    # Calculate BEFORE (old method): crop from 512x213 proxy downscale
    # The proxy was 512x213; crop of 800x800 out of 1920x800 gives 213x213 pixels
    proxy_w = 512
    proxy_h = FrameGeometry.even(800 * 512.0 / 1920) # 214
    old_crop_size = int(round(800 * 512.0 / 1920))   # 213
    
    # Simulate old pipeline: downscale exact to 213x213, then upscale back to 512x512 (bilinear)
    sim_old = Image.fromarray(exact_arr).resize((old_crop_size, old_crop_size), Image.Resampling.BILINEAR)
    sim_old_upscaled = sim_old.resize((512, 512), Image.Resampling.BILINEAR)
    old_arr = np.array(sim_old_upscaled)

    mae_old, psnr_old = compute_psnr(old_arr, exact_arr)
    mae_new, psnr_new = compute_psnr(playback_arr, exact_arr)

    print(f"Spatial resolution BEFORE: {old_crop_size} × {old_crop_size} px (upscaled to 512×512)")
    print(f"Spatial resolution AFTER:  {playback_qimg.width()} × {playback_qimg.height()} px (native Lanczos 512×512)")
    print(f"Old proxy crop quality:   MAE = {mae_old:.2f}, PSNR = {psnr_old:.2f} dB")
    print(f"New direct cache quality: MAE = {mae_new:.2f}, PSNR = {psnr_new:.2f} dB")
    
    assert psnr_new >= 35.0, f"Expected PSNR >= 35.0 dB, got {psnr_new:.2f} dB"
    assert psnr_new > psnr_old + 3.0, f"Expected new PSNR to be at least 3 dB higher than old proxy, got {psnr_new:.2f} vs {psnr_old:.2f}"
    print("PASS: Test 1 (Non-chroma cropped playback quality)")

    print("\n========================================================")
    print("TEST 2: Chroma Key Cropped Playback vs Exact Preview")
    print("========================================================")
    
    doc.state.key = KeySettings()
    doc.state.key.enabled = True
    doc.state.key.screen_color_r = 0
    doc.state.key.screen_color_g = 255
    doc.state.key.screen_color_b = 0
    doc.state.key.gain = 100
    doc.state.key.shrink_grow = 0

    exact_key_qimg = None
    loop_exact_key = QEventLoop()
    def on_exact_key(rev, qimg):
        nonlocal exact_key_qimg
        exact_key_qimg = qimg
        loop_exact_key.quit()
    renderer.exact_completed.connect(on_exact_key)

    req_ex_key = ExactPreviewRequest()
    req_ex_key.revision = 2
    req_ex_key.ffmpeg_path = ffmpeg
    req_ex_key.source_path = doc.source_path
    req_ex_key.info = doc.info
    req_ex_key.time = 0.2
    req_ex_key.state = doc.state
    renderer.request_exact(req_ex_key)
    QTimer.singleShot(8000, loop_exact_key.quit)
    loop_exact_key.exec()

    assert exact_key_qimg is not None, "Chroma exact preview failed"

    cache_key_dir = None
    loop_cache_key = QEventLoop()
    def on_cache_key(rev, folder, fps_val):
        nonlocal cache_key_dir
        cache_key_dir = folder
        loop_cache_key.quit()
    renderer.cache_completed.connect(on_cache_key)

    req_cache_key = PlaybackCacheRequest()
    req_cache_key.revision = 2
    req_cache_key.ffmpeg_path = ffmpeg
    req_cache_key.source_path = doc.source_path
    req_cache_key.info = doc.info
    req_cache_key.state = doc.state
    renderer.request_cache(req_cache_key)
    QTimer.singleShot(15000, loop_cache_key.quit)
    loop_cache_key.exec()

    assert cache_key_dir is not None and os.path.exists(cache_key_dir), "Chroma cache failed"
    cached_key_files = sorted(glob.glob(os.path.join(cache_key_dir, "f*.bmp")))
    assert len(cached_key_files) > 0, "No cached chroma frames found"

    playback_key_qimg = QImage(cached_key_files[idx])
    assert not playback_key_qimg.isNull()
    assert playback_key_qimg.width() == 512 and playback_key_qimg.height() == 512

    # Check that alpha is preserved in 32-bit BMP
    def qimage_to_rgba_array(qimg: QImage) -> np.ndarray:
        converted = qimg.convertToFormat(QImage.Format.Format_RGBA8888)
        w, h = converted.width(), converted.height()
        b = converted.bits()
        return np.frombuffer(b, dtype=np.uint8).reshape((h, w, 4)).copy()

    exact_key_arr = qimage_to_rgba_array(exact_key_qimg)
    playback_key_arr = qimage_to_rgba_array(playback_key_qimg)

    mae_key, psnr_key = compute_psnr(playback_key_arr, exact_key_arr)
    print(f"Chroma key playback vs exact: MAE = {mae_key:.2f}, PSNR = {psnr_key:.2f} dB")
    # Verify green region was keyed out (alpha == 0 or low)
    # The green box was at [600, 100, 1320, 700]; in crop [560, 0, 800, 800] it's at [40, 100, 760, 700]
    # Scaled to 512: x ~ 40 * 512/800 = 25, y ~ 100 * 512/800 = 64
    # At (50, 100):
    assert playback_key_arr[100, 50, 3] < 50, f"Expected transparent pixel, got alpha = {playback_key_arr[100, 50, 3]}"
    assert psnr_key >= 35.0, f"Expected chroma PSNR >= 35.0 dB, got {psnr_key:.2f} dB"
    print("PASS: Test 2 (Chroma key cropped playback quality)")

    print("\n========================================================")
    print("TEST 3: GUI PreviewWidget and Cache Integration")
    print("========================================================")
    from gui import MainWindow
    window = MainWindow()
    window.show()
    window.load_video(test_vid)

    # Wait for doc to load
    loop_load = QEventLoop()
    def check_loaded():
        if window.editor.doc:
            loop_load.quit()
    t_load = QTimer()
    t_load.timeout.connect(check_loaded)
    t_load.start(50)
    QTimer.singleShot(5000, loop_load.quit)
    loop_load.exec()
    t_load.stop()

    editor = window.editor
    assert editor.doc is not None

    # Apply crop
    editor.preview.enter_crop_mode()
    editor.preview.crop_sel = editor.preview.original_to_preview((560, 0, 800, 800))
    editor.apply_crop()
    assert editor.doc.state.crop_rect == (560, 0, 800, 800)

    # Verify cache clears on crop
    # Wait for cache completion
    loop_gui_cache = QEventLoop()
    def check_gui_cache():
        if editor.cache_dir != "" and editor.cache_frames:
            loop_gui_cache.quit()
    t_gc = QTimer()
    t_gc.timeout.connect(check_gui_cache)
    t_gc.start(50)
    QTimer.singleShot(5000, loop_gui_cache.quit)
    loop_gui_cache.exec()
    t_gc.stop()

    assert editor.cache_dir != "", "GUI cache dir not set"
    assert len(editor.cache_frames) > 0, "GUI cache frames empty"

    # Show frame and check content size
    editor.show_frame(0.2)
    assert editor.preview.playback_pixmap is not None, "playback_pixmap is None"
    assert editor.preview.playback_pixmap.size() == QSize(512, 512), f"Expected 512x512, got {editor.preview.playback_pixmap.size()}"
    assert editor.preview.content_size() == QSize(512, 512), f"Expected content size 512x512, got {editor.preview.content_size()}"

    # Test playback
    editor.toggle_play()
    assert editor.playing
    assert editor.preview.playback_pixmap is not None, "playback_pixmap must NOT be cleared during playback start"
    editor.toggle_play()
    assert not editor.playing

    print("PASS: Test 3 (GUI PreviewWidget and Cache Integration)")

    # Cleanup
    shutil.rmtree(tmp_test_dir, ignore_errors=True)
    if cache_dir:
        shutil.rmtree(cache_dir, ignore_errors=True)
    if cache_key_dir:
        shutil.rmtree(cache_key_dir, ignore_errors=True)
    editor.clear_cache()
    window.close()

    print("\n========================================================")
    print("ALL CROPPED PLAYBACK QUALITY TESTS PASSED SUCCESSFULLY!")
    print("========================================================\n")
    sys.exit(0)

if __name__ == "__main__":
    main()
