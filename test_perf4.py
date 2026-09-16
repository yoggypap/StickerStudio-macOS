import sys, time
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import QThread
import numpy as np
from PIL import Image
from chroma_key import ChromaKey

class Worker(QThread):
    def run(self):
        print("Worker running")
        arr = np.random.randint(0, 255, (480, 640, 4), dtype=np.uint8)
        img = Image.fromarray(arr, 'RGBA')
        ChromaKey.prepare_for_vp9(img, 3)
        print("Worker done")

app = QApplication(sys.argv)
w = Worker()
w.start()
time.sleep(1)
