import time
import numpy as np
from PIL import Image
from chroma_key import ChromaKey

arr = np.random.randint(0, 255, (480, 640, 4), dtype=np.uint8)
img = Image.fromarray(arr, 'RGBA')
t0 = time.time()
ChromaKey.prepare_for_vp9(img, 3)
t1 = time.time()
print("Time vp9 random:", t1 - t0)
