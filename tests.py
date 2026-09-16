import unittest
import numpy as np
import os
import shutil
import tempfile
from PIL import Image
from models import ProbeInfo, EditState, KeySettings
from geometry import FrameGeometry
from chroma_key import ChromaKey
from patcher import Patcher
from ffmpeg_utils import Ffmpeg
from export_pipeline import ExportPipeline

class TestStickerStudio(unittest.TestCase):
    def test_geometry_crop_scale(self):
        info = ProbeInfo(width=1920, height=1080)
        g = FrameGeometry.create(info, None)
        self.assertIsNone(g.crop)
        self.assertEqual(g.output_size_w, 512)
        self.assertEqual(g.output_size_h, 288)

        info = ProbeInfo(width=1080, height=1920)
        g = FrameGeometry.create(info, None)
        self.assertEqual(g.output_size_w, 288)
        self.assertEqual(g.output_size_h, 512)
        
        info = ProbeInfo(width=3840, height=2160)
        g = FrameGeometry.create(info, None)
        self.assertEqual(g.output_size_w, 512)
        self.assertEqual(g.output_size_h, 288)

        info = ProbeInfo(width=1280, height=720)
        g = FrameGeometry.create(info, None)
        self.assertEqual(g.output_size_w, 512)
        self.assertEqual(g.output_size_h, 288)

        info = ProbeInfo(width=512, height=512)
        g = FrameGeometry.create(info, None)
        self.assertEqual(g.output_size_w, 512)
        self.assertEqual(g.output_size_h, 512)

        info = ProbeInfo(width=513, height=513)
        g = FrameGeometry.create(info, None)
        self.assertEqual(g.output_size_w, 512)
        self.assertEqual(g.output_size_h, 512)

    def test_chroma_key_basic(self):
        arr = np.zeros((100, 100, 4), dtype=np.uint8)
        arr[:, :] = [0, 255, 0, 255]
        arr[40:60, 40:60] = [255, 0, 0, 255]
        
        img = Image.fromarray(arr, 'RGBA')
        k = KeySettings(enabled=True, screen_color_r=0, screen_color_g=255, screen_color_b=0)
        out_img = ChromaKey.apply(img, k)
        out_arr = np.array(out_img)
        
        self.assertEqual(tuple(out_arr[50, 50]), (255, 0, 0, 255))
        self.assertEqual(out_arr[0, 0, 3], 0)

    def test_chroma_key_gradient(self):
        arr = np.zeros((100, 100, 4), dtype=np.uint8)
        for x in range(100):
            arr[:, x] = [x * 2, 255 - x * 2, 0, 255]
        img = Image.fromarray(arr, 'RGBA')
        k = KeySettings(enabled=True, gain=100)
        out_img = ChromaKey.apply(img, k)
        out_arr = np.array(out_img)
        self.assertEqual(out_arr[50, 0, 3], 0)
        self.assertEqual(out_arr[50, 99, 3], 255)

    def test_chroma_key_noise(self):
        np.random.seed(42)
        arr = np.random.randint(0, 256, (100, 100, 4), dtype=np.uint8)
        arr[..., 3] = 255
        img = Image.fromarray(arr, 'RGBA')
        k = KeySettings(enabled=True)
        out_img = ChromaKey.apply(img, k)
        self.assertIsNotNone(out_img)

    def test_chroma_key_edge(self):
        arr = np.zeros((100, 100, 4), dtype=np.uint8)
        arr[:, :] = [0, 255, 0, 255]
        arr[0:10, 0:10] = [255, 0, 0, 255]
        img = Image.fromarray(arr, 'RGBA')
        k = KeySettings(enabled=True)
        out_img = ChromaKey.apply(img, k)
        out_arr = np.array(out_img)
        self.assertEqual(tuple(out_arr[5, 5]), (255, 0, 0, 255))

    def test_ebml_patcher(self):
        # Legacy
        data = bytearray([0x1A, 0x45, 0xdf, 0xa3, 0x44, 0x89, 0x50, 0x40, 0x40, 0x00, 0x00])
        res = Patcher.patch_bytes(data)
        self.assertEqual(res, Patcher.APPLIED)
        self.assertEqual(data[6:10], Patcher.LEGACY)

        # Float
        data = bytearray([0x44, 0x89, 0x84, 0x40, 0x40, 0x00, 0x00])
        res = Patcher.patch_bytes(data)
        self.assertEqual(res, Patcher.APPLIED)
        self.assertEqual(data[3:7], Patcher.FLOAT1)
        self.assertEqual(Patcher.patch_bytes(data), Patcher.ALREADY_PATCHED)

        # Double
        data = bytearray([0x44, 0x89, 0x88, 0x40, 0x40, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00])
        res = Patcher.patch_bytes(data)
        self.assertEqual(res, Patcher.APPLIED)
        self.assertEqual(data[3:11], Patcher.DOUBLE1)
        self.assertEqual(Patcher.patch_bytes(data), Patcher.ALREADY_PATCHED)

if __name__ == '__main__':
    unittest.main()
