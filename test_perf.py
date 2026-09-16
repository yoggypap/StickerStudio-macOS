import time
from PIL import Image
from models import KeySettings
from chroma_key import ChromaKey

img = Image.new("RGBA", (640, 480), (0, 255, 0, 255))
k = KeySettings()
k.enabled = True

t0 = time.time()
ChromaKey.apply(img, k)
t1 = time.time()
print("Time:", t1 - t0)
