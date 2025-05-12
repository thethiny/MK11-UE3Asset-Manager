from ctypes import c_char, c_uint32
from logging import getLogger
import logging
import os
from pathlib import Path
from typing import Literal, Sequence, Type, Union

from nrs.ue3_common import MK11Archive, MK11ExportTableEntry, MK11ImportTableEntry, MK11TableEntry, MK11TableMeta
from nrs.game.enums import CompressionType
from utils.structs import T, Struct


class MidwayAsset(MK11Archive):
    def close(self):
        self.mm.close()
        if getattr(self, "owns_file", False) and self.file:
            self.file.close()

    def to_file(self, folder: Union[str, Path], file_name: str):
        if not file_name:
            raise ValueError(f"Please provide a file name to dump to without an extension")

        path = Path(folder, file_name)
        path.mkdir(parents=True, exist_ok=True)
        with open(path / f"{file_name}.upk", "wb") as f:
            f.write(self.mm[:])

    def parse(self, resolve: bool = True):
        # File Summary
        self.parse_summary()
        self.file_name = self.parse_file_meta()
        self.psf_tables = self.parse_file_table()
        self.bulk_tables = self.parse_file_table()
        self.meta_size = self.mm.tell()  # Size of all header metas
        if self.meta_size != self.header.name_table.offset:
            raise ValueError(f"Size of header did not match expected! Size: {self.meta_size}, Expected: {self.header.name_table.offset}.")

        self.name_table = list(self.parse_name_table())
        if self.mm.tell() != self.header.import_table.offset:
            getLogger("Midway").warning(f"Position expected to reach Import Table but {self.header.import_table.offset - self.mm.tell()} bytes remain!")

        self.export_table = list(self.parse_uobject_table(self.header.export_table, MK11ExportTableEntry))
        if self.mm.tell() != self.header.exports_location:
            getLogger("Midway").warning(f"Position expected to reach Exports but {self.header.exports_location - self.mm.tell()} bytes remain!")

        self.import_table = list(self.parse_uobject_table(self.header.import_table, MK11ImportTableEntry))
        if self.mm.tell() != self.header.export_table.offset:
            getLogger("Midway").warning(f"Position expected to reach Export Table but {self.header.export_table.offset - self.mm.tell()} bytes remain!")

        if resolve:
            self.resolve_table_info(self.import_table)
            self.resolve_table_info(self.export_table)

        errors = self.validate_exports()
        if errors:
            getLogger("Midway").warning(f"{len(errors)} Export issues detected! Proceed with caution.")

        self.parsed = True

    def dump(self, save_dir: str, format: Union[Literal["both"], bool]):
        """
        save_dir: str = Path to save into
        format: str | bool = save str (True), repr (False), or both "both"
        """
        if not save_dir:
            raise ValueError(f"save_dir was invalid! Provide a folder to dump into.")

        logging.getLogger("Main").info(f"Saving {self.file_name}'s data to {save_dir}")

        self.dump_exports(save_dir)
        if format != True:
            self.dump_tables(save_dir)
        if format != False:
            self.dump_tables(save_dir, formatted=True)

    def dump_exports(self, save_dir: str = "extracted"):
        output_dir = os.path.join(save_dir, self.file_name, "exports")
        for export in self.export_table:
            write_path = os.path.join(output_dir, export.file_dir.lstrip("/"))
            os.makedirs(write_path, exist_ok=True)

            data = self.read_export(export)
            file_out = os.path.join(write_path, export.file_name)
            logging.getLogger("Midway").debug(f"Saving export {export.full_name} to {file_out}")
            with open(file_out, "wb") as f:
                f.write(data)

    def read_export(self, export: MK11ExportTableEntry):
        self.mm.seek(export.object_offset, 0)
        data = self.mm.read(export.object_size)
        return data

    def validate_exports(self):
        errors = []

        start = self.header.exports_location
        end = (
            self.header.bulk_location
            if hasattr(self.header, "bulk_location")
            else self.mm.size()
        )

        used_ranges = []

        for export in self.export_table:
            offset = export.object_offset
            size = export.object_size

            # 1. Offset bounds check
            if not (start <= offset < end):
                errors.append(
                    f"{export.full_name}: Offset 0x{offset:X} out of bounds [{start:X}, {end:X})"
                )
                continue

            # 2. Size bounds check
            if offset + size > end:
                errors.append(
                    f"{export.full_name}: Size 0x{size:X} at 0x{offset:X} exceeds end 0x{end:X}"
                )
                continue

            # 3. Overlap check
            for o_start, o_end, o_name in used_ranges:
                if offset < o_end and offset + size > o_start:
                    errors.append(
                        f"{export.full_name} [0x{offset:X}–0x{offset+size:X}) overlaps with {o_name} [0x{o_start:X}–0x{o_end:X})"
                    )
                    break

            used_ranges.append((offset, offset + size, export.full_name))

        # Sort ranges by offset
        used_ranges.sort()

        # 4. Gap check
        current = start
        for o_start, o_end, o_name in used_ranges:
            if o_start > current:
                errors.append(f"Unused gap: [0x{current:X}–0x{o_start:X}) before {o_name}")
            current = max(current, o_end)

        # 5. Early finish check
        if current < end:
            errors.append(
                f"Export data ends early at 0x{current:X}, expected up to 0x{end:X}"
            )

        return errors

    def parse_name_table(self):
        self.mm.seek(self.header.name_table.offset)
        for i in range(self.header.name_table.entries):
            name_length = self.read_buffer(c_uint32)
            name = self.read_buffer(c_char * name_length)
            yield name.decode('ascii')

    def parse_uobject_table(self, table: MK11TableMeta, type_: Type[T]):
        self.mm.seek(table.offset)
        for i in range(table.entries):
            entry: T = Struct.read_buffer(self.mm, type_)
            yield entry

    def resolve_table_info(self, table):
        for entry in table:
            entry.resolve(self.name_table, self.import_table, self.export_table)

    def parse_summary(self):
        self.header = self.parse_header()
        self.compression_mode = CompressionType(self.header.compression_flag)
        self.packages_count = self.parse_packages()
        self.packages_extra_count = self.parse_packages()
        self.skip(0x18)
        self.summary_size = self.mm.tell()
        self.validate_file()

    def parse_packages(self):
        packages_count = self.read_buffer(c_uint32)
        return packages_count

    def validate_file(self):
        if self.header.magic != 0x9E2A83C1:
            getLogger("Midway").error("File Magic Failed!")
            return False

        if self.header.midway_team_four_cc != b"MK11":
            getLogger("Midway").error("Midway Four CC Failed!")
            return False

        if self.header.main_package != b"MAIN":
            getLogger("Midway").error(f"Package Type is not supported: {self.header.main_package}")
            return False

        if self.compression_mode != CompressionType.NONE:
            getLogger("Midway").error(f"Compression Type was not reset to NONE!")
            return False

        if self.packages_count != 0:
            getLogger("Midway").error(f"Expected 0 Packages but received {self.packages_count}!")
            return False

        if self.packages_extra_count != 0:
            getLogger("Midway").error(f"Expected 0 Packages but received {self.packages_extra_count}!")
            return False

        return True

    def __str__(self):
        strings = []
        strings.append(f"Midway Asset File: {self.file_name}")
        strings.append(f"Compression Mode: {CompressionType(self.header.compression_flag).name}")
        strings.append(f"{self.packages_count} Packages | {self.packages_extra_count} Extra Packages")
        strings.append(f"{len(self.name_table)} Names")
        strings.append(f"{len(self.import_table)} Imports")
        strings.append(f"{len(self.export_table)} Exports")

        return '\n'.join(strings)

    def dump_tables(self, location, formatted: bool = False):
        self.dump_names(location)
        self.dump_table(location, self.import_table, formatted)
        self.dump_table(location, self.export_table, formatted)

    def dump_names(self, location):
        location = os.path.join(location, self.file_name)
        os.makedirs(location, exist_ok=True)

        file_out = os.path.join(location, "nametable.txt")
        logging.getLogger("Midway").debug(f"Saving {self.file_name}'s Name Table to {file_out}")
        with open(file_out, "w+", encoding="utf-8") as f:
            for i, name in enumerate(self.name_table):
                f.write(f"{hex(i)[2:].upper()}:\t{name}\n")

    def dump_table(self, location, table: Sequence[MK11TableEntry], formatted: bool = False):
        if not table:
            return
        location = os.path.join(location, self.file_name)
        os.makedirs(location, exist_ok=True)

        if isinstance(table[0], MK11ExportTableEntry):
            file = "exporttable"
        elif isinstance(table[0], MK11ImportTableEntry):
            file = "importtable"
        else:
            raise TypeError(f"Invalid type: {type(table[0])}")

        if formatted:
            func = str
            file += ".parsed"
        else:
            func = repr

        file_out = os.path.join(location, f"{file}.txt")
        logging.getLogger("Midway").debug(f"Saving {self.file_name}'s {table[0].__class__.__name__} to {file_out} with formatting {'on' if formatted else 'off'}")

        with open(file_out, "w+", encoding="utf-8") as f:
            for i, entry in enumerate(table):
                f.write(f"{hex(i)[2:].upper()}:\t{func(entry)}\n")

    def parse_and_save_export(self, export: MK11ExportTableEntry, handler, save_dir: str):
        export_data = self.read_export(export)
        handler_obj = handler(export_data, self.name_table)
        parsed = handler_obj.parse()

        handler_obj.save(parsed, export, self.file_name, save_dir)
