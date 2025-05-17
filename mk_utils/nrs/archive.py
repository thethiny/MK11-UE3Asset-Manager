from ctypes import addressof, c_byte, c_char, c_uint32, c_uint64, sizeof, string_at
from logging import getLogger
import logging
import os
from typing import Any, Type

from nrs.ue3_common import MK11AssetHeader, MK11Archive
from nrs.compression.oodle import OodleV5
from nrs.games.mk11.enums import CompressionType
from nrs.midway import MidwayAsset
from utils.structs import T, Struct

class MK11AssetSubPackage(Struct):
    __slots__ = ()
    _fields_ = [
        ("decompressed_offset", c_uint64),
        ("decompressed_size", c_uint64), # Excluding Header
        ("compressed_offset", c_uint64),
        ("compressed_size", c_uint64),
    ]

class _MK11AssetPackage(Struct):
    __slots__ = ()
    _fields_ = [
        ("decompressed_offset", c_uint64),
        ("decompressed_size", c_uint64),
        ("compressed_offset", c_uint64),
        ("compressed_size", c_uint64),
        ("entries_count", c_uint32),
    ]

class MK11AssetPackage(Struct):
    _fields_ = [
        ("package_name_length", c_uint32)
    ]

    def __init__(self, *args: Any, **kw: Any) -> None:
        super().__init__(*args, **kw)
        self.subpackages = []

    @classmethod
    def read(cls: Type[T], file_handle) -> T:
        struct = super().read(file_handle)
        struct.add_member("package_name", Struct.read_buffer(file_handle, c_char * struct.package_name_length).decode())
        
        p_struct = _MK11AssetPackage.read(file_handle)
        for n, t in p_struct._fields_: # type: ignore
            struct.add_member(n, getattr(p_struct, n))
        return struct
    
    def serialize(self) -> bytes:
        # Serialize the base field (`package_name_length`)
        base_data = super().serialize()

        # Serialize dynamic name
        name_bytes = self.package_name.encode('ascii') if isinstance(self.package_name, str) else self.package_name

        # Serialize the appended _MK11AssetPackage struct fields
        pkg_struct = _MK11AssetPackage()
        for field_name, _ in pkg_struct._fields_:  # type: ignore
            setattr(pkg_struct, field_name, getattr(self, field_name))

        return base_data + name_bytes + string_at(addressof(pkg_struct), sizeof(pkg_struct))

    
    def __repr__(self) -> str:
        string = ""
        string += f"Package: {self.package_name}"
        return string

    def __str__(self):
        name = getattr(self, "package_name", b"").decode("utf-8", "ignore")
        base = super().__str__()
        return f"{base}\npackage_name = {name}"

class MK11BlockHeader(Struct):
    __slots__ = ()
    _fields_ = [
        ("magic", c_uint32),
        ("padding", c_uint32),
        ("chunk_size", c_uint64),
        ("compressed_size", c_uint64),
        ("decompressed_size", c_uint64),
    ]

class MK11BlockChunkHeader(Struct):
    __slots__ = ()
    _fields_ = [
        ("compressed_size", c_uint64),
        ("decompressed_size", c_uint64),
    ]

class MK11UE3Asset(MK11Archive): # TODO: For each archive type detect its game version and call the appropriate archiver
    def __init__(self, path: str):
        super().__init__(path)

    def parse(self):
        self.header = self.parse_header()
        self.compression_mode = CompressionType(self.header.compression_flag)
        if self.compression_mode >= CompressionType.PS4:
            self.compressor = OodleV5()
        else:
            raise NotImplementedError(f"Only Oodle Compression is supported")

        self.packages = self.parse_packages()
        self.packages_extra = self.parse_packages()
        self.skip(0x18)
        self.file_name = self.parse_file_meta()
        self.psf_tables = self.parse_file_table()
        self.bulk_tables = self.parse_file_table()
        self.meta_size = self.mm.tell() # Size of all header metas

        self.parsed = True
        
    def dump(self, save_path: str):
        save_path = os.path.join(save_path, self.file_name)
        os.makedirs(save_path, exist_ok=True)
        for _ in self.deserialize_packages(save_path): pass

    def deserialize_packages(self, save_path: str = ""):
        for package in self.packages:
            getLogger("FArchive").debug(f"Deserializing Package {package.package_name}")
            yield from self.deserialize_package_entries(package, save_path)

    def deserialize_package_entries(self, package: MK11AssetPackage, save_path: str = ""):
        for i, entry in enumerate(package.entries):
            entry_offset = entry.compressed_offset
            self.mm.seek(entry_offset)
            entry_data = self.deserialize_block()

            if save_path:
                save_path = os.path.join(save_path, "packages", package.package_name)
                os.makedirs(save_path, exist_ok=True)
                with open(os.path.join(save_path, f"file_{i}.bin"), "wb") as f:
                    f.write(entry_data)

            yield entry.decompressed_offset, entry_data

    def parse_packages(self):
        packages_count = Struct.read_buffer(self.mm, c_uint32)
        return list(self.parse_packages_content(packages_count))

    def parse_packages_content(self, count):
        for _ in range(count):
            package = MK11AssetPackage.read(self.mm)
            subpackages = list(self.parse_package_subpackages(package.entries_count))
            package.add_member("entries", subpackages)
            yield package

    def parse_package_subpackages(self, count):
        yield from (MK11AssetSubPackage.read(self.mm) for _ in range(count))

    def deserialize_block(self):
        block = MK11BlockHeader.read(self.mm)
        decompressed_data = self.decompress_block(block)
        return decompressed_data

    def parse_blocks_chunk(self, block: MK11BlockHeader):
        total_read = 0
        chunk_headers = []
        while total_read < block.compressed_size:
            chunk_header = MK11BlockChunkHeader.read(self.mm)
            chunk_headers.append(chunk_header)
            total_read += chunk_header.compressed_size

        for chunk_header in chunk_headers:
            chunk_data = Struct.read_buffer(self.mm, c_byte * chunk_header.compressed_size)
            yield chunk_header, chunk_data

    def decompress_block(self, block: MK11BlockHeader):
        data = b''
        for chunk_header, chunk_data in self.parse_blocks_chunk(block):
            decompressed_chunk = self.compressor.decompress(
                chunk_data, chunk_header.decompressed_size
            )
            data += decompressed_chunk
        return data

    def to_midway(self):
        buffer = self._MidwayBuilder.from_mk11(self)
        return MidwayAsset(buffer)

    class _MidwayBuilder:
        @classmethod
        def from_mk11(cls, mk11: "MK11UE3Asset"):
            if not mk11.parsed:
                logging.getLogger("FArchive").warning(f"MK11 Asset was not parsed. Parsing first.")
                mk11.parse()

            buffer = bytearray()

            buffer += cls._build_header(mk11.header, compression_mode=CompressionType.NONE)
            buffer += cls._build_padding()
            buffer += cls._build_filename_section(mk11.file_name)
            buffer += cls._build_file_tables(mk11.psf_tables)
            buffer += cls._build_file_tables(mk11.bulk_tables)

            for offset, data in mk11.deserialize_packages():
                cls._build_midway_block(buffer, offset, data)

            return buffer

        @classmethod
        def _build_header(cls, header: MK11AssetHeader, compression_mode: int = 0) -> bytes:
            base = header.serialize()[:-4]
            return base + compression_mode.to_bytes(4, "little") + b"\x00" * 8

        @classmethod
        def _build_padding(cls,) -> bytes:
            return b"\x00" * 0x18

        @classmethod
        def _build_filename_section(cls, file_name: str) -> bytes:
            return (len(file_name)+1).to_bytes(4, "little") + file_name.encode(
                "ascii"
            ) + b"\x00" # ZTerm 

        @classmethod
        def _build_file_tables(cls, tables: list) -> bytes:
            out = bytearray(len(tables).to_bytes(4, "little"))
            for table in tables:
                out += table.serialize()
                for entry in table.entries:
                    out += entry.serialize()
            return out

        @classmethod
        def _build_midway_block(cls, buffer: bytearray, offset: int, data: bytes):
            end = offset + len(data)
            buffer_len = len(buffer)

            if offset > buffer_len:
                getLogger("FArchive").warning(f"Offset {offset} is beyond current buffer size {buffer_len}. Padding with zeros.")
                buffer += b"\x00" * (offset - buffer_len)
            elif offset < buffer_len:
                # existing = buffer[offset:end]
                if not any((buffer[offset:end])):
                    getLogger("FArchive").warning(f"Writing to offset {offset} which was already zero-filled. Possibly unordered input.")
                else:
                    raise ValueError(f"[ERROR] Data already exists at offset {offset}! Check your serialization.")

            buffer[offset:end] = data

            return buffer

    def parse_all(self, save_path: str = ""):
        # self = MK11UE3Asset(asset_path)
        self.parse()
        if save_path:
            self.dump(save_path)

        midway_file = self.to_midway()
        if save_path:
            midway_file.to_file(save_path, self.file_name)

        midway_file.parse(resolve=True)
        logging.getLogger("Main").debug("%r", midway_file)

        if save_path:
            midway_file.dump(save_path, "both")

        return midway_file
