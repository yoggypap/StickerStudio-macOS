#!/usr/bin/env python3
import os
import sys
import shutil
import subprocess
import hashlib

EXPECTED_FFMPEG_SHA256 = "eaf91238e104dd0e262bc6510e25061855cc99a6955a721b0ac99660d58c473d"

def sha256_file(filepath: str) -> str:
    h = hashlib.sha256()
    with open(filepath, "rb") as f:
        while chunk := f.read(65536):
            h.update(chunk)
    return h.hexdigest()

def run_cmd(cmd: list[str], cwd=None):
    print(f"==> Running: {' '.join(cmd)}")
    res = subprocess.run(cmd, cwd=cwd)
    if res.returncode != 0:
        print(f"Error: command failed with code {res.returncode}")
        sys.exit(res.returncode)

def main():
    base_dir = os.path.dirname(os.path.abspath(__file__))
    os.chdir(base_dir)

    print("==================================================")
    print("Building Sticker Studio.app (arm64, 6s)")
    print("==================================================")

    # 1. Verify source FFmpeg
    src_ffmpeg = os.path.join(base_dir, "bin", "ffmpeg")
    if not os.path.exists(src_ffmpeg):
        print("Error: bin/ffmpeg not found!")
        sys.exit(1)

    src_sha = sha256_file(src_ffmpeg)
    print(f"Source bin/ffmpeg SHA256: {src_sha}")
    if src_sha != EXPECTED_FFMPEG_SHA256:
        print(f"Error: FFmpeg SHA mismatch! Expected {EXPECTED_FFMPEG_SHA256}, got {src_sha}")
        sys.exit(1)

    # 2. Clean old packaging outputs
    for d in ["build", "dist"]:
        if os.path.exists(d):
            print(f"Cleaning {d}/...")
            shutil.rmtree(d, ignore_errors=True)

    # 3. Ensure AppIcon.icns exists
    if not os.path.exists("AppIcon.icns"):
        print("Creating AppIcon.icns from uxlive-logo.png...")
        os.makedirs("icon.iconset", exist_ok=True)
        subprocess.run(["sips", "-z", "16", "16", "uxlive-logo.png", "--out", "icon.iconset/icon_16x16.png"], check=True)
        subprocess.run(["sips", "-z", "32", "32", "uxlive-logo.png", "--out", "icon.iconset/icon_16x16@2x.png"], check=True)
        subprocess.run(["sips", "-z", "32", "32", "uxlive-logo.png", "--out", "icon.iconset/icon_32x32.png"], check=True)
        subprocess.run(["sips", "-z", "64", "64", "uxlive-logo.png", "--out", "icon.iconset/icon_32x32@2x.png"], check=True)
        subprocess.run(["iconutil", "-c", "icns", "icon.iconset", "-o", "AppIcon.icns"], check=True)
        shutil.rmtree("icon.iconset", ignore_errors=True)

    # 4. Run PyInstaller
    pyinstaller_bin = shutil.which("pyinstaller")
    if not pyinstaller_bin:
        for cand in [
            os.path.join(base_dir, ".venv", "bin", "pyinstaller"),
            os.path.join(base_dir, "..", "StickerStudio_Python", ".venv", "bin", "pyinstaller"),
        ]:
            if os.path.exists(cand):
                pyinstaller_bin = cand
                break
    if not pyinstaller_bin:
        pyinstaller_bin = "pyinstaller"

    run_cmd([pyinstaller_bin, "StickerStudio.spec", "--noconfirm"])

    app_dir = os.path.join(base_dir, "dist", "Sticker Studio.app")
    if not os.path.exists(app_dir):
        print(f"Error: app bundle {app_dir} was not created!")
        sys.exit(1)

    # 5. Place FFmpeg in Contents/Resources/
    res_dir = os.path.join(app_dir, "Contents", "Resources")
    os.makedirs(res_dir, exist_ok=True)

    dst_ffmpeg = os.path.join(res_dir, "ffmpeg")
    print(f"Copying production FFmpeg to {dst_ffmpeg}...")
    shutil.copy2(src_ffmpeg, dst_ffmpeg)
    os.chmod(dst_ffmpeg, 0o755)

    # Also copy assets into Resources
    for asset in ["phosphor-icons.ttf", "phosphor-icons-fill.ttf", "uxlive-logo.png", "AppIcon.icns"]:
        if os.path.exists(asset):
            shutil.copy2(asset, os.path.join(res_dir, asset))

    # 6. Verify bundled FFmpeg SHA256
    bundled_sha = sha256_file(dst_ffmpeg)
    print(f"Bundled FFmpeg SHA256: {bundled_sha}")
    if bundled_sha != EXPECTED_FFMPEG_SHA256:
        print("Error: Bundled FFmpeg SHA mismatch!")
        sys.exit(1)

    # 7. Ad-hoc codesign
    print("Applying ad-hoc code signature...")
    run_cmd(["codesign", "--force", "--deep", "--sign", "-", app_dir])

    # 8. Verify codesign
    print("Verifying code signature...")
    run_cmd(["codesign", "--verify", "--deep", "--strict", "--verbose=2", app_dir])

    print("\n==================================================")
    print("BUILD SUCCESSFUL!")
    print(f"App Bundle: {app_dir}")
    print("==================================================")

if __name__ == "__main__":
    main()
