import shutil
import subprocess
import os
from patcher import Patcher

# 1. Create a raw webm without patcher
cmd = 'ffmpeg -y -f lavfi -i "color=c=blue:duration=2:size=100x100:rate=10" -c:v libvpx-vp9 "raw.webm"'
subprocess.run(cmd, shell=True, capture_output=True)

# 2. Make copy
shutil.copy2("raw.webm", "patched.webm")

# 3. Apply patch
with open("patched.webm", "rb") as f:
    data = bytearray(f.read())
    
Patcher.patch_bytes(data)

with open("patched.webm", "wb") as f:
    f.write(data)
    
# 4. Read bytes around 44 89
with open("raw.webm", "rb") as f:
    raw_data = bytearray(f.read())
    
idx = -1
for i in range(len(raw_data) - 1):
    if raw_data[i] == 0x44 and raw_data[i+1] == 0x89:
        idx = i
        break
        
print(f"Raw bytes around 44 89: {raw_data[idx:idx+12].hex()}")
print(f"Patched bytes around 44 89: {data[idx:idx+12].hex()}")

# 5. FFprobe
print("Raw probe:")
subprocess.run('ffprobe -v error -show_entries format=duration -of default=noprint_wrappers=1:nokey=1 raw.webm', shell=True)

print("Patched probe:")
subprocess.run('ffprobe -v error -show_entries format=duration -of default=noprint_wrappers=1:nokey=1 patched.webm', shell=True)

# Try decoding
print("Raw decode:")
res1 = subprocess.run('ffmpeg -v error -i raw.webm -f null -', shell=True)
print("Return code:", res1.returncode)

print("Patched decode:")
res2 = subprocess.run('ffmpeg -v error -i patched.webm -f null -', shell=True)
print("Return code:", res2.returncode)

