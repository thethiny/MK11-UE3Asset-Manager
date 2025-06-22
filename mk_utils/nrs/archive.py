from ctypes import addressof, c_char, c_uint32, c_uint64, sizeof, string_at
from logging import getLogger
import logging
import os
from typing import Any, Type

from mk_utils.nrs.ue3_common import MK11AssetHeader, MK11Archive
from mk_utils.nrs.games.mk11.enums import CompressionType
from mk_utils.nrs.midway import MidwayAsset
from mk_utils.utils.structs import T, Struct

class MK11AssetSubPackage(Struct):
    __slots__ = ()
    _fields_ = [
        ("decompressed_offset", c_uint64),
        ("decompressed_size", c_uint64), # Excluding Header
        ("compressed_offset", c_uint64),
        ("compressed_size", c_uint64),
    ]
    
    def __len__(self):
        return self.entries_count

class _MK11AssetPackage(Struct):
    __slots__ = ()
    _fields_ = [
        ("decompressed_offset", c_uint64),
        ("decompressed_size", c_uint64),
        ("compressed_offset", c_uint64),
        ("compressed_size", c_uint64),
        ("entries_count", c_uint32),
    ]

    def __len__(self):
        return self.entries_count


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


class MK11UE3Asset(MK11Archive): # TODO: For each archive type detect its game version and call the appropriate archiver
    def __init__(self, path: str, extra_path: str = ""):
        super().__init__(path, extra_path)

    def parse(self, skip_bulk: bool = False):
        self.header = self.parse_header()
        self.compression_mode = CompressionType(self.header.compression_flag)
        self.compressor = self.get_compressor(self.compression_mode)

        self.packages = self.parse_packages()
        self.packages_extra = self.parse_packages() # Same as psf_table but one is in UE3 Asset one is in Midway Asset
        self.skip(0x18)
        self.file_name = self.parse_file_name()
        if not skip_bulk:
            self.psf_tables = self.parse_file_table("psf") # Total count must match packages_extra and they should belong in there
            self.bulk_tables = self.parse_file_table("bulk")
            self.meta_size = self.mm.tell() # Size of all header metas

            self.validate_psf_with_extra()

        self.parsed = True

    def validate_psf_with_extra(self):
        def entry_pairs(psf_tables):
            for psf_table in psf_tables:
                for psf_entry in psf_table.entries:
                    yield psf_entry

        def pkg_pairs(packages_extra):
            for pkg_table in packages_extra:
                for pkg_entry in pkg_table.entries:
                    yield pkg_entry

        psf_iter = entry_pairs(self.psf_tables)
        pkg_iter = pkg_pairs(self.packages_extra)

        for idx, (psf_entry, pkg_entry) in enumerate(zip(psf_iter, pkg_iter)):
            compressed_match = psf_entry.compressed_offset == pkg_entry.compressed_offset
            if not compressed_match:
                raise ValueError(f"Index {idx} {psf_entry.compressed_offset == pkg_entry.compressed_offset=}")

            decompressed_match = psf_entry.decompressed_offset == pkg_entry.decompressed_offset
            if not decompressed_match:
                # I think it's safe to ignore this because the package contains the 
                # decompressed offset in case some other file uses the package and finds that it's already decompressed.
                # This allows the game to skip the decompression process all over again and just reference a cached file that has
                # everything already decompressed.
                # In other words: if pgk->decompressed_offset exists -> use, else decompress.
                getLogger("FArchive").warning(f"Index {idx} {psf_entry.decompressed_offset == pkg_entry.decompressed_offset=}")

        try:
            next(psf_iter)
            raise ValueError("psf_tables has extra entries not matched in packages_extra")
        except StopIteration:
            pass

        try:
            next(pkg_iter)
            raise ValueError("packages_extra has extra entries not matched in psf_tables")
        except StopIteration:
            pass

    def dump(self, save_path: str):
        save_path = os.path.join(save_path, self.file_name)
        os.makedirs(save_path, exist_ok=True)
        for _ in self.deserialize_packages(False, save_path): pass

        # for _ in self.deserialize_packages(True, save_path): pass # Disabled to to it using too much space for no reason

    def deserialize_packages(self, is_extra: bool = False, save_path: str = ""):
        for package in self.packages_extra if is_extra else self.packages:
            getLogger("FArchive").debug(f"Deserializing{' Extra ' if is_extra else ' '}Package {package.package_name}")
            yield from self.deserialize_package_entries(package, is_extra, save_path)

    def deserialize_package_entries(self, package: MK11AssetPackage, is_extra: bool = False, save_path: str = ""):
        for i, entry in enumerate(package.entries):
            entry_offset = entry.compressed_offset
            self.mm.seek(entry_offset)
            entry_data = self.deserialize_block()

            if save_path:
                export_path = os.path.join(save_path, "packages_extra" if is_extra else "packages", package.package_name)
                os.makedirs(export_path, exist_ok=True)
                with open(os.path.join(export_path, f"file_{i}.bin"), "wb") as f:
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
        return super().deserialize_block(self.mm, self.compressor)
    #     block = MK11BlockHeader.read(self.mm)
    #     decompressed_data = self.decompress_block(block)
    #     return decompressed_data

    # def parse_blocks_chunk(self, block: MK11BlockHeader):
    #     total_read = 0
    #     chunk_headers = []
    #     while total_read < block.compressed_size:
    #         chunk_header = MK11BlockChunkHeader.read(self.mm)
    #         chunk_headers.append(chunk_header)
    #         total_read += chunk_header.compressed_size

    #     for chunk_header in chunk_headers:
    #         chunk_data = Struct.read_buffer(self.mm, c_byte * chunk_header.compressed_size)
    #         yield chunk_header, chunk_data

    # def decompress_block(self, block: MK11BlockHeader):
    #     data = b''
    #     for chunk_header, chunk_data in self.parse_blocks_chunk(block):
    #         decompressed_chunk = self.compressor.decompress(
    #             chunk_data, chunk_header.decompressed_size
    #         )
    #         data += decompressed_chunk
    #     return data

    def to_midway(self, skip_bulk: bool = False):
        buffer = self._MidwayBuilder.from_mk11(self, skip_bulk)
        return MidwayAsset(buffer, self.psf_source)

    class _MidwayBuilder:
        @classmethod
        def from_mk11(cls, mk11: "MK11UE3Asset", skip_bulk: bool = False):
            if not mk11.parsed:
                logging.getLogger("FArchive").warning(f"MK11 Asset was not parsed. Parsing first.")
                mk11.parse(skip_bulk=skip_bulk)

            buffer = bytearray()

            buffer += cls._build_header(mk11.header, compression_mode=CompressionType.NONE)
            buffer += cls._build_padding()
            buffer += cls._build_filename_section(mk11.file_name)
            if not skip_bulk:
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
                out += Struct._to_little(table.compression_flag, 4)
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

    def parse_all(self, save_path: str = "", skip_bulk: bool = False):
        # self = MK11UE3Asset(asset_path)
        self.parse(skip_bulk=skip_bulk)
        if save_path:
            self.dump(save_path)

        midway_file = self.to_midway(skip_bulk=skip_bulk)
        if save_path:
            midway_file.to_file(save_path, self.file_name)

        midway_file.parse(resolve=True, skip_bulk=skip_bulk)
        logging.getLogger("Main").debug("%r", midway_file)

        if save_path:
            midway_file.dump(save_path, "both")

        return midway_file
