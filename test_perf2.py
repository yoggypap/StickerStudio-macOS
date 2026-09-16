import time
from PIL import Image
from chroma_key import ChromaKey

img = Image.new("RGBA", (640, 480), (0, 255, 0, 255))
t0 = time.time()
ChromaKey.prepare_for_vp9(img, 3)
t1 = time.time()
print("Time vp9:", t1 - t0)
