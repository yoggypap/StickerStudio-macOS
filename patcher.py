class Patcher:
    NOT_FOUND = -1
    APPLIED = 0
    ALREADY_PATCHED = 1

    LEGACY = bytes([0x84, 0x45, 0x35, 0x40])          # size=4 + float 2900.0 (first 3 bytes)
    FLOAT1 = bytes([0x45, 0x35, 0x40, 0x00])          # IEEE-754 float  2900.0
    DOUBLE1 = bytes([0x40, 0xA6, 0xA8, 0x00, 0x00, 0x00, 0x00, 0x00])  # IEEE-754 double 2900.0

    @staticmethod
    def patch_bytes(data: bytearray) -> int:
        idx = -1
        for i in range(len(data) - 1):
            if data[i] == 0x44 and data[i+1] == 0x89:
                idx = i
                break
                
        if idx < 0 or idx + 6 > len(data):
            return Patcher.NOT_FOUND
            
        size_byte = data[idx + 2]
        
        if size_byte == 0x84:
            if Patcher.starts_with(data, idx + 3, Patcher.FLOAT1[:3]):
                return Patcher.ALREADY_PATCHED
            if idx + 3 + 4 > len(data):
                return Patcher.NOT_FOUND
            data[idx + 3 : idx + 3 + 4] = Patcher.FLOAT1
            return Patcher.APPLIED
            
        if size_byte == 0x88 and idx + 3 + 8 <= len(data):
            if Patcher.starts_with(data, idx + 3, Patcher.DOUBLE1[:4]):
                return Patcher.ALREADY_PATCHED
            data[idx + 3 : idx + 3 + 8] = Patcher.DOUBLE1
            return Patcher.APPLIED
            
        if Patcher.starts_with(data, idx + 2, Patcher.LEGACY):
            return Patcher.ALREADY_PATCHED
            
        data[idx + 2 : idx + 2 + 4] = Patcher.LEGACY
        return Patcher.APPLIED

    @staticmethod
    def starts_with(data: bytearray, offset: int, pattern: bytes) -> bool:
        if offset + len(pattern) > len(data):
            return False
        return data[offset:offset+len(pattern)] == pattern
