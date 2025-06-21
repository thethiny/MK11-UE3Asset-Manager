import struct
from pathlib import Path
from typing import Sequence, Union, List

BLOCK_BYTES = 16  # BC7 block = 16 bytes (4×4 px)


def _collect_mip_files(src: Union[str, Path, Sequence[Union[str, Path]]]) -> List[Path]:
    if isinstance(src, (str, Path)):
        p = Path(src)
        if p.is_dir():
            mip_files = [f for f in p.iterdir() if f.is_file() and f.stem.isdigit()]
            if not mip_files:
                raise FileNotFoundError(f"No numeric mip files found in {p}")
            return sorted(mip_files, key=lambda f: int(f.stem))
        return [p]  # single file

    return [Path(f) for f in src]


def _make_header(w: int, h: int, mips: int, dxgi: int, array_size: int) -> bytes:
    # DDS header constants
    DDSD_CAPS = 0x1
    DDSD_HEIGHT = 0x2
    DDSD_WIDTH = 0x4
    DDSD_PIXELFORMAT = 0x1000
    DDSD_LINEARSIZE = 0x80000
    DDSD_MIPMAPCOUNT = 0x20000

    DDSCAPS_TEXTURE = 0x1000
    DDSCAPS_MIPMAP = 0x400000
    DDSCAPS_COMPLEX = 0x8

    flags = DDSD_CAPS | DDSD_HEIGHT | DDSD_WIDTH | DDSD_PIXELFORMAT | DDSD_LINEARSIZE
    caps = DDSCAPS_TEXTURE
    if mips > 1:
        flags |= DDSD_MIPMAPCOUNT
        caps |= DDSCAPS_MIPMAP | DDSCAPS_COMPLEX

    # Size in bytes of the top mip level
    blocks_w = (w + 3) // 4
    blocks_h = (h + 3) // 4
    linear_size = blocks_w * blocks_h * BLOCK_BYTES

    header = struct.pack(
        "<4s I 6I 11I 8I 5I",
        b"DDS ",
        124,
        flags,
        h,
        w,
        linear_size,
        0,
        mips,
        *(0,) * 11,  # reserved1[11]
        32,
        0x4,
        struct.unpack("<I", b"DX10")[0],
        *(0,) * 5,  # bit masks (unused for BC formats)
        caps,
        0,
        0,
        0,
        0,
    )
    dx10 = struct.pack("<5I", dxgi, 3, 0, array_size, 0)  # 3 = TEXTURE2D
    return header + dx10


def make_bc7_dds_data(source: Union[str, Path, Sequence[Union[str, Path]]],
    width: int,
    height: int,
    dxgi_format: int = 98,
    array_size: int = 1,
): 
    mip_files = _collect_mip_files(source)
    mip_count = len(mip_files)
    data = b""
    for mip in mip_files:
        data += mip.read_bytes()

    header = _make_header(width, height, mip_count, dxgi_format, array_size)

    return header + data


def write_bc7_dds(
    source: Union[str, Path, Sequence[Union[str, Path]]],
    width: int,
    height: int,
    dxgi_format: int = 98,
    array_size: int = 1,
    output: Union[str, Path, None] = None,
) -> Path:
    """
    Wrap raw BC7 block data (and optional mip files) in a DDS container.

    Returns the Path of the created .dds file.
    """
    mip_files = _collect_mip_files(source)
    mip_count = len(mip_files)
    data = b"".join(f.read_bytes() for f in mip_files)

    header = _make_header(width, height, mip_count, dxgi_format, array_size)

    if output is None:
        base = mip_files[0] if mip_files else Path(source)  # type: ignore
        out_name = base.stem + ".dds" if base.is_file() else base.name + ".dds"
        output = base.parent / out_name

    Path(output).write_bytes(header + data)
    return Path(output)
