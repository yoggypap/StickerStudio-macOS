from dataclasses import dataclass
from typing import Optional

@dataclass
class ProbeInfo:
    ok: bool = False
    error: str = ""
    duration: float = 0.0
    width: int = 0
    height: int = 0
    fps: float = 0.0
    has_alpha: bool = False

@dataclass
class KeySettings:
    enabled: bool = False
    screen_color_r: int = 0
    screen_color_g: int = 255
    screen_color_b: int = 0
    gain: int = 100
    shrink_grow: int = 0

@dataclass
class EditState:
    crop_rect: Optional[tuple[int, int, int, int]] = None
    cut_start: float = 0.0
    cut_end: float = 0.0
    key: KeySettings = None
    fps30: bool = False

    def __post_init__(self):
        if self.key is None:
            self.key = KeySettings()

@dataclass
class StickerFrameGeometry:
    crop: Optional[tuple[int, int, int, int]] = None
    output_size_w: int = 0
    output_size_h: int = 0
    pre_key_filter: str = ""
    post_key_filter: str = ""
