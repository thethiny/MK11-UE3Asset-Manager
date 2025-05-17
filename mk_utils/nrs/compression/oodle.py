import ctypes
from enum import IntEnum
from typing import Optional

from nrs.compression.base import CompressionBase

class OodleCompressionCodecs(IntEnum):
    MK11 = 7
    KRAKEN = 8
    MERMAID = 9
    MEDIAN = 10
    SELKIE = 11
    HYDRA = 12
    LEVIATHAN = 13


class OodleV5(CompressionBase):
    DEFAULT_COMPRESSION_MODE = OodleCompressionCodecs.MK11
    DEFAULT_COMPRESSION_LEVEL = 7

    def __init__(self, dll_path: str = "./oo2core_5_win64.dll"):
        try:
            self.oodle = ctypes.WinDLL(dll_path)
        except FileNotFoundError:
            raise FileNotFoundError(f"Oodle Dll does not exist in {dll_path}!") from None

        self.oodle.OodleLZ_Compress.argtypes = [
            ctypes.c_uint32,  # codec
            ctypes.c_char_p,
            ctypes.c_uint64,  # src_buf, src_len
            ctypes.c_char_p,
            ctypes.c_int64,  # dst_buf, level
            ctypes.c_void_p,
            ctypes.c_int64,
            ctypes.c_int64,  # opts, offs, unused
            ctypes.c_void_p,
            ctypes.c_int64,  # scratch, scratch_size
        ]
        self.oodle.OodleLZ_Compress.restype = ctypes.c_int

        self.oodle.OodleLZ_Decompress.argtypes = [
            ctypes.c_char_p,
            ctypes.c_int64,  # src_buf, src_len
            ctypes.c_char_p,
            ctypes.c_uint64,  # dst_buf, dst_size
            ctypes.c_int,
            ctypes.c_int,
            ctypes.c_int,  # fuzz, crc, verbose
            ctypes.c_void_p,
            ctypes.c_size_t,  # dst_base, e
            ctypes.c_void_p,
            ctypes.c_void_p,  # cb, cb_ctx
            ctypes.c_void_p,
            ctypes.c_size_t,  # scratch, scratch_size
            ctypes.c_int,  # threadPhase
        ]
        self.oodle.OodleLZ_Decompress.restype = ctypes.c_int

    def decompress(self, chunk: bytes, output_size: int) -> bytes:
        src = ctypes.create_string_buffer(chunk)
        dst = ctypes.create_string_buffer(output_size)

        result = self.oodle.OodleLZ_Decompress(
            src, len(chunk), dst, output_size, 0, 0, 0, None, 0, None, None, None, 0, 0
        )
        if result <= 0:
            raise RuntimeError("Decompression failed")

        return dst.raw[:result]

    def compress(self, chunk: bytes, codec: Optional[int] = None, level: Optional[int] = None) -> bytes:
        if codec is None:
            codec = self.DEFAULT_COMPRESSION_MODE
        if level is None:
            level = self.DEFAULT_COMPRESSION_LEVEL

        src = ctypes.create_string_buffer(chunk)
        dst_buf_size = len(chunk) + 256  # extra padding
        dst = ctypes.create_string_buffer(dst_buf_size)

        result = self.oodle.OodleLZ_Compress(
            codec, src, len(chunk), dst, level, None, 0, 0, None, 0
        )
        if result <= 0:
            raise RuntimeError("Compression failed")

        return dst.raw[:result]
