from ctypes import c_char, c_uint32
from logging import getLogger
import logging
import mmap
import os
from pathlib import Path
from typing import Literal, Sequence, Type, Union

from mk_utils.nrs.ue3_common import ClassHandler, MK11Archive, MK11AssetExternalTable, MK11ExportTableEntry, MK11ImportTableEntry, MK11TableEntry, MK11TableMeta
from mk_utils.nrs.games.mk11.enums import CompressionType
from mk_utils.utils.structs import T, Struct
from mk_utils.utils.filereader import FileReader


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

    def get_psf_reader(self):
        if not self.psf_source:
            return
        if isinstance(self.psf_source, str) and os.path.isdir(self.psf_source):
            return FileReader(os.path.join(self.psf_source, self.file_name + ".psf"))
        else:
            return FileReader(self.psf_source)

    def parse(self, resolve: bool = True, skip_bulk: bool = False):
        # File Summary
        self.parse_summary()
        self.file_name = self.parse_file_name()
        if not skip_bulk:
            self.psf_tables = self.parse_file_table("psf")
            self.bulk_tables = self.parse_file_table("bulk")
            self.psf_map = self.generate_map_from_table(self.psf_tables)
            self.bulk_map = self.generate_map_from_table(self.bulk_tables)
            if self.psf_tables:
                self.psf_reader = self.get_psf_reader()
                
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
            self.print_resolves(self.import_table)
            self.print_resolves(self.export_table)

        errors = self.validate_exports(skip_bulk=skip_bulk)
        if errors:
            getLogger("Midway").warning(f"{len(errors)} Export issues detected! Proceed with caution.")
            if len(errors) < 5:
                for error in errors:
                    getLogger("Midway").error(error)
                    
        if not skip_bulk:
            errors = self.validate_bulks()
            if errors:
                getLogger("Midway").warning(f"{len(errors)} Bulk Data issues detected! Proceed with caution.")
                if len(errors) < 5:
                    for error in errors:
                        getLogger("Midway").error(error)

            errors = self.validate_psfs()
            if errors:
                getLogger("Midway").warning(
                    f"{len(errors)} Bulk Data issues detected! Proceed with caution."
                )
                if len(errors) < 5:
                    for error in errors:
                        getLogger("Midway").error(error)

        self.parsed = True

    def dump(self, save_dir: str, format: Union[Literal["both"], bool]):
        """
        save_dir: str = Path to save into
        format: str | bool = save str (True), repr (False), or both "both"
        """
        if not save_dir:
            raise ValueError(f"save_dir was invalid! Provide a folder to dump into.")

        logging.getLogger("Main").info(f"Saving {self.file_name}'s data to {save_dir}")

        if format != True:
            self.dump_tables(save_dir)
        if format != False:
            self.dump_tables(save_dir, formatted=True)
        self.dump_extra_tables(save_dir)

        self.dump_exports(save_dir)
        self.dump_bulks(save_dir)
        self.dump_psfs(save_dir) # Unsure if like this or combine

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

    def _dump_table_entries(self, tables, kind: str, save_dir: str):
        output_dir = os.path.join(save_dir, self.file_name, kind + 's')

        if kind == "psf":
            mm_source = self.psf_reader.mm if self.psf_reader else None
            if not mm_source:
                raise ValueError("Missing mm source for PSF file!")
        else:
            mm_source = self.mm

        for i, table in enumerate(tables):
            if not table.entries:
                continue

            compression_flag = table.compression_flag
            package = table.package_name.decode()  # type: ignore
            package_dir = os.path.join(output_dir, package)
            key = table.reference_key

            out_dir = os.path.join(package_dir, f"{key:0>8X}")
            os.makedirs(out_dir, exist_ok=True)

            logging.getLogger("Midway").debug(
                f"Saving {kind.upper()} {i} - {key:0>8X} with {len(table.entries)} entries to {out_dir}"
            )

            for j, entry in enumerate(table.entries): # TODO: I think these should be combined into 1 file, need to check
                if entry.location != kind:
                    raise ValueError("Mismatch element with location!")

                offset = entry.decompressed_offset
                size = entry.decompressed_size

                if compression_flag:
                    mm_source.seek(offset, 0)
                    data = self.deserialize_block(mm_source, compression_flag)
                else:
                    mm_source.seek(offset, 0)
                    data = mm_source.read(size)

                with open(os.path.join(out_dir, str(j)), "wb") as f:
                    f.write(data)

    def dump_bulks(self, save_dir: str = "extracted"):
        if not self.bulk_tables:
            return
        self._dump_table_entries(self.bulk_tables, "bulk", save_dir)

    def dump_psfs(self, save_dir: str = "extracted"):
        if not self.psf_tables:
            return
        if not self.psf_source:
            raise ValueError("No PSF file to read from!")
        if not self.psf_reader:
            raise ValueError("PSF Reader was not initialized!")

        self._dump_table_entries(self.psf_tables, "psf", save_dir)

    def read_export(self, export: MK11ExportTableEntry):
        self.mm.seek(export.object_offset, 0)
        data = self.mm.read(export.object_size)
        return data

    def validate_exports(self, skip_bulk: bool = False):
        if not self.export_table:          # nothing → nothing to check
            return []

        start = self.header.exports_location
        end = getattr(self.header, "bulk_location", self.mm.size()) # TODO: This is not bulks location this is psf location, which in MK11 is end of file
        errors = []

        # ── flatten & sort (offset, size, name) ──────────────────────────────────
        exports = sorted(
            (e.object_offset, e.object_size, e.full_name) for e in self.export_table
        )

        prev_off, prev_end, prev_name = start, start, None   # active range

        for off, sz, name in exports:
            # 1-2. bounds
            if not (start <= off < end):
                errors.append(f"{name}: Offset 0x{off:X} out of bounds [{start:X}, {end:X})")
                continue
            if off + sz > end:
                errors.append(f"{name}: Size 0x{sz:X} at 0x{off:X} exceeds end 0x{end:X}")
                continue

            # 3. overlap / gap  (compare only with active range)
            if off < prev_end:   # overlap
                errors.append(
                    f"{name} [0x{off:X}–0x{off+sz:X}) overlaps with "
                    f"{prev_name} [0x{prev_off:X}–0x{prev_end:X})"
                )
            elif off > prev_end: # gap
                errors.append(f"Unused gap: [0x{prev_end:X}–0x{off:X}) before {name}")

            # extend coverage window if needed
            if off + sz > prev_end:
                prev_off, prev_end, prev_name = off, off + sz, name

        # 4. early-finish
        if prev_end < end:
            if not skip_bulk and self.bulk_tables:
                first_bulk = self.bulk_tables[0].entries[0].decompressed_offset
                if first_bulk != prev_end:
                    errors.append(
                        f"Export data ends early at 0x{prev_end:X}, expected bulk at 0x{first_bulk:X}"
                    )
            else:
                errors.append(f"Export data ends early at 0x{prev_end:X}, expected 0x{end:X}")

        return errors

    def validate_bulks(self):
        """Return a list of validation errors for bulk tables."""
        if not self.bulk_tables:  # no data → no errors
            return []

        start = self.bulk_tables[0].entries[0].decompressed_offset
        end = self.mm.size()
        errors = []

        # ---- 1. Flatten & sort --------------------------------------------------
        entries = sorted(  # (offset, size)
            (e.decompressed_offset, e.decompressed_size)
            for tbl in self.bulk_tables
            for e in tbl.entries
        )

        # ---- 2. Single sweep ----------------------------------------------------
        prev_end = start
        for off, sz in entries:
            # bounds
            if not (start <= off < end):
                errors.append(f"Offset 0x{off:X} out of bounds [{start:X}, {end:X})")
                continue
            if off + sz > end:
                errors.append(f"Size 0x{sz:X} at 0x{off:X} exceeds end 0x{end:X}")
                continue

            # overlap or gap (only compare with previous interval)
            if off < prev_end:  # overlap
                errors.append(
                    f"[0x{off:X}–0x{off+sz:X}) overlaps with " f"[0x{off:X}–0x{prev_end:X})"
                )
            elif off > prev_end:  # gap
                errors.append(f"Unused gap: [0x{prev_end:X}–0x{off:X})")

            prev_end = max(prev_end, off + sz)

        # ---- 3. Early-finish check ---------------------------------------------
        if prev_end < end:
            errors.append(f"Export data ends early at 0x{prev_end:X}, expected 0x{end:X}")

        return errors

    def validate_psfs(self):
        """Return a list of validation errors for psf tables."""
        if not self.psf_tables:  # no data → no errors
            return []

        source_mm = self.psf_reader
        if not source_mm:
            return []
        source_mm = source_mm.mm

        start = self.psf_tables[0].entries[0].decompressed_offset
        end = source_mm.size()
        errors = []

        # ---- 1. Flatten & sort --------------------------------------------------
        entries = sorted(  # (offset, size)
            (e.decompressed_offset, e.decompressed_size)
            for tbl in self.psf_tables
            for e in tbl.entries
        )

        # ---- 2. Single sweep ----------------------------------------------------
        prev_end = start
        for off, sz in entries:
            # bounds
            if not (start <= off < end):
                errors.append(f"Offset 0x{off:X} out of bounds [{start:X}, {end:X})")
                continue
            if off + sz > end:
                errors.append(f"Size 0x{sz:X} at 0x{off:X} exceeds end 0x{end:X}")
                continue

            # overlap or gap (only compare with previous interval)
            if off < prev_end:  # overlap
                errors.append(
                    f"[0x{off:X}–0x{off+sz:X}) overlaps with "
                    f"[0x{off:X}–0x{prev_end:X})"
                )
            elif off > prev_end:  # gap
                errors.append(f"Unused gap: [0x{prev_end:X}–0x{off:X})")

            prev_end = max(prev_end, off + sz)

        # ---- 3. Early-finish check ---------------------------------------------
        if prev_end < end:
            errors.append(
                f"Export data ends early at 0x{prev_end:X}, expected 0x{end:X}"
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

    def print_resolves(self, table):
        for entry in table:
            logging.getLogger("Common").debug(f"Resolved {entry.__class__.__name__}: {entry.full_name}")

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

    def dump_extra_tables(self, location):
        self.dump_extra_table(location, self.psf_tables, "psf")
        self.dump_extra_table(location, self.bulk_tables, "bulk")

    def dump_names(self, location):
        location = os.path.join(location, self.file_name)
        os.makedirs(location, exist_ok=True)

        file_out = os.path.join(location, "nametable.txt")
        logging.getLogger("Midway").debug(f"Saving {self.file_name}'s Name Table to {file_out}")
        with open(file_out, "w+", encoding="utf-8") as f:
            for i, name in enumerate(self.name_table):
                f.write(f"{hex(i)[2:].upper()}:\t{name}\n")

    def dump_extra_table(self, location, table: Sequence[MK11AssetExternalTable], table_type):
        if not table:
            return

        location = os.path.join(location, self.file_name)
        os.makedirs(location, exist_ok=True)

        # json_path = os.path.join(location, f"{table_type}map.json")
        # logging.getLogger("Midway").debug(f"Saving {self.file_name}'s {table[0].__class__.__name__}::{table_type.upper()} Map to {json_path}")
        # with open(json_path, "w+", encoding="utf-8") as f:
        #     json.dump(self.psf_map if table_type == "psf" else self.bulk_map, f)

        file_path = os.path.join(location, f"{table_type}table.txt")
        logging.getLogger("Midway").debug(f"Saving {self.file_name}'s {table[0].__class__.__name__}::{table_type.upper()} to {file_path}")

        # neg = -1 & 0xFFFFFFFFFFFFFFFF
        with open(file_path, "w+", encoding="utf-8") as f:
            counter = 0
            for i, table_entry in enumerate(table):
                package = table_entry.package_name.decode() # type: ignore
                compression_flag = table_entry.compression_flag
                compression = CompressionType(compression_flag).name
                table_key = table_entry.reference_key
                f.write(f"{i:0>4X} - {package} - {table_key:0>8X} ({len(table_entry.entries)}):\n")
                for j, entry in enumerate(table_entry.entries):
                    c_off, d_off, c_size, d_size = entry.compressed_offset, entry.decompressed_offset, entry.compressed_size, entry.decompressed_size
                    location = entry.location
                    string = ""
                    string += f"\t{j:X}: [{counter:0>4X}] {c_off:0>8X} {c_size:0>8X} - {d_off:0>8X} {d_size:0>8X} | "

                    string += f"Compression: {compression}"
                    string += " | "

                    string += location.upper()

                    f.write(string + "\n")
                    counter += 1
                f.write("\n")

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

    def parse_and_save_export(self, export: MK11ExportTableEntry, handler: Type[ClassHandler], save_dir: str, overwrite: bool = False):
        if overwrite == False:
            out_file = handler.make_save_path(export, self.file_name, save_dir)
            if os.path.isfile(out_file):
                logging.getLogger("Midway").debug(f"File {out_file} already exists and overwrite is False...")
                logging.getLogger("Midway").info(f"Skipping {export.file_name}...")
                return out_file

        export_data = self.read_export(export)
        handler_obj = handler(export_data, self.name_table)

        parsed = handler_obj.parse()

        saved_file = handler_obj.save(parsed, export, self.file_name, save_dir, self)
        return saved_file
