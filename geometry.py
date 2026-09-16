from typing import Optional
from models import ProbeInfo, StickerFrameGeometry

class FrameGeometry:
    STICKER_SIDE = 512

    @staticmethod
    def even(value: float) -> int:
        n = int(round(value))
        if n % 2 != 0:
            n -= 1
        return max(2, n)

    @staticmethod
    def create(info: ProbeInfo, crop_rect: Optional[tuple[int, int, int, int]]) -> StickerFrameGeometry:
        g = StickerFrameGeometry()
        if not info:
            return g

        if crop_rect is not None:
            cr_x, cr_y, cr_w, cr_h = crop_rect
            cx = max(0, min(cr_x, info.width - 2))
            cy = max(0, min(cr_y, info.height - 2))
            cw = max(2, min(cr_w, info.width - cx))
            ch = max(2, min(cr_h, info.height - cy))
            
            g.crop = (cx, cy, cw, ch)
            g.output_size_w = FrameGeometry.STICKER_SIDE
            g.output_size_h = FrameGeometry.STICKER_SIDE
            g.pre_key_filter = f"crop={cw}:{ch}:{cx}:{cy}"
        else:
            if info.width >= info.height:
                w = FrameGeometry.STICKER_SIDE
                h = FrameGeometry.even(info.height * float(FrameGeometry.STICKER_SIDE) / info.width)
            else:
                h = FrameGeometry.STICKER_SIDE
                w = FrameGeometry.even(info.width * float(FrameGeometry.STICKER_SIDE) / info.height)
                
            g.crop = None
            g.output_size_w = w
            g.output_size_h = h
            g.pre_key_filter = ""
            
        g.post_key_filter = f"scale={g.output_size_w}:{g.output_size_h}:flags=lanczos,setsar=1"
        return g
