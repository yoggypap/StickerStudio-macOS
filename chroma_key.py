import numpy as np
from PIL import Image
from scipy.ndimage import minimum_filter, maximum_filter, correlate1d, correlate
from models import KeySettings

class ChromaKey:
    @staticmethod
    def apply(img: Image.Image, k: KeySettings) -> Image.Image:
        if not img or not k or not k.enabled:
            return img
            
        if img.mode != 'RGBA':
            img = img.convert('RGBA')
            
        arr = np.array(img, dtype=np.float64)
        h, w = arr.shape[:2]
        
        keyR = k.screen_color_r / 255.0
        keyG = k.screen_color_g / 255.0
        keyB = k.screen_color_b / 255.0
        keyU = -0.100644 * keyR - 0.338572 * keyG + 0.439216 * keyB + 0.501961
        keyV = 0.439216 * keyR - 0.398942 * keyG - 0.040274 * keyB + 0.501961
        
        similarity = 0.18 + max(0, min(200, k.gain)) * 0.0021
        smoothness = 0.085
        spillRange = 0.11
        
        r = arr[..., 0] / 255.0
        g = arr[..., 1] / 255.0
        b = arr[..., 2] / 255.0
        
        u = -0.100644 * r - 0.338572 * g + 0.439216 * b + 0.501961
        v = 0.439216 * r - 0.398942 * g - 0.040274 * b + 0.501961
        
        du = u - keyU
        dv = v - keyV
        distance = np.sqrt(du*du + dv*dv)
        
        dist_up = np.roll(distance, 1, axis=0)
        dist_up[0, :] = distance[0, :]
        
        dist_down = np.roll(distance, -1, axis=0)
        dist_down[-1, :] = distance[-1, :]
        
        dist_left = np.roll(distance, 1, axis=1)
        dist_left[:, 0] = distance[:, 0]
        
        dist_right = np.roll(distance, -1, axis=1)
        dist_right[:, -1] = distance[:, -1]
        
        filtered = (distance + 2.0 * (dist_left + dist_right + dist_up + dist_down)) / 9.0
        
        effective_distance = np.where(distance >= similarity + smoothness, np.maximum(filtered, distance), filtered)
        base_mask = effective_distance - similarity
        
        def saturate(val):
            return np.clip(val, 0.0, 1.0)
            
        matte = np.power(saturate(base_mask / smoothness), 1.5)
        alpha = np.round(matte * 255.0).astype(np.uint8)
        spill_keep = np.power(saturate(base_mask / spillRange), 1.5)
        
        iters = min(3, abs(k.shrink_grow) // 34 + (1 if abs(k.shrink_grow) > 0 else 0))
        if iters > 0:
            grow = k.shrink_grow > 0
            for _ in range(iters):
                if grow:
                    alpha = maximum_filter(alpha, size=3, mode='nearest')
                else:
                    alpha = minimum_filter(alpha, size=3, mode='nearest')
                    
        unblurred = alpha.copy()
        kernel = np.ones((3, 3), dtype=int)
        sum_alpha = correlate(alpha.astype(int), kernel, mode='constant', cval=0)
        valid_counts = correlate(np.ones_like(alpha, dtype=int), kernel, mode='constant', cval=0)
        blurred = (sum_alpha // valid_counts).astype(np.uint8)
        
        alpha = np.where(unblurred >= 240, unblurred, blurred)
        
        luma = r * 0.2126 + g * 0.7152 + b * 0.0722
        keep = spill_keep
        
        new_b = np.clip(np.round((luma * (1.0 - keep) + b * keep) * 255.0), 0, 255).astype(np.uint8)
        new_g = np.clip(np.round((luma * (1.0 - keep) + g * keep) * 255.0), 0, 255).astype(np.uint8)
        new_r = np.clip(np.round((luma * (1.0 - keep) + r * keep) * 255.0), 0, 255).astype(np.uint8)
        
        src_a = arr[..., 3].astype(np.uint16)
        new_a = (alpha.astype(np.uint16) * src_a // 255).astype(np.uint8)
        
        out_arr = np.empty((h, w, 4), dtype=np.uint8)
        out_arr[..., 0] = new_r
        out_arr[..., 1] = new_g
        out_arr[..., 2] = new_b
        out_arr[..., 3] = new_a
        
        out_arr = ChromaKey.protect_transparent_colors(out_arr, 1)
        
        return Image.fromarray(out_arr, 'RGBA')

    @staticmethod
    def protect_transparent_colors(arr: np.ndarray, radius: int) -> np.ndarray:
        if radius <= 0 or arr.shape[0] <= 0 or arr.shape[1] <= 0:
            return arr
            
        h, w = arr.shape[:2]
        
        filled = arr[..., 3] >= 192
        red = arr[..., 0].copy()
        green = arr[..., 1].copy()
        blue = arr[..., 2].copy()
        
        for _ in range(radius):
            add = np.zeros((h, w), dtype=bool)
            nr = red.copy()
            ng = green.copy()
            nb = blue.copy()
            
            filled_int = filled.astype(int)
            kernel = np.ones((3, 3), dtype=int)
            
            n_filled_neighbors = correlate(filled_int, kernel, mode='constant', cval=0)
            
            sum_r = correlate((red * filled_int).astype(int), kernel, mode='constant', cval=0)
            sum_g = correlate((green * filled_int).astype(int), kernel, mode='constant', cval=0)
            sum_b = correlate((blue * filled_int).astype(int), kernel, mode='constant', cval=0)
            
            mask = (~filled) & (n_filled_neighbors > 0)
            
            nr[mask] = (sum_r[mask] // n_filled_neighbors[mask]).astype(np.uint8)
            ng[mask] = (sum_g[mask] // n_filled_neighbors[mask]).astype(np.uint8)
            nb[mask] = (sum_b[mask] // n_filled_neighbors[mask]).astype(np.uint8)
            add = mask
            
            red = nr
            green = ng
            blue = nb
            
            if not np.any(add):
                break
            filled |= add
            
        out_arr = arr.copy()
        mask1 = filled & (out_arr[..., 3] < 192)
        out_arr[mask1, 0] = red[mask1]
        out_arr[mask1, 1] = green[mask1]
        out_arr[mask1, 2] = blue[mask1]
        
        mask2 = (~filled) & (out_arr[..., 3] <= 2)
        out_arr[mask2, 0] = 0
        out_arr[mask2, 1] = 0
        out_arr[mask2, 2] = 0
        
        return out_arr

    @staticmethod
    def prepare_for_vp9(img: Image.Image, color_radius: int) -> Image.Image:
        if not img: return img
        if img.mode != 'RGBA':
            img = img.convert('RGBA')
        arr = np.array(img)
        
        source_a = arr[..., 3].astype(int)
        
        kernel1d = np.array([1, 2, 1], dtype=int)
        
        weighted_y = correlate1d(source_a, kernel1d, axis=0, mode='constant', cval=0)
        weighted = correlate1d(weighted_y, kernel1d, axis=1, mode='constant', cval=0)
        
        ones = np.ones_like(source_a)
        total_y = correlate1d(ones, kernel1d, axis=0, mode='constant', cval=0)
        total = correlate1d(total_y, kernel1d, axis=1, mode='constant', cval=0)
        
        total[total == 0] = 1
        blurred = weighted // total
        feather = (blurred * 2 + 1) // 3
        
        mask = feather > source_a
        arr[mask, 3] = feather[mask]
        
        arr = ChromaKey.protect_transparent_colors(arr, color_radius)
        return Image.fromarray(arr, 'RGBA')
