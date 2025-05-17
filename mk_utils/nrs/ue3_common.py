import os
import logging

from ctypes import c_char, c_int32, c_ubyte, c_uint32, c_uint16, c_uint64
from typing import Any, Union, Iterable, List, Tuple, Type, TypedDict

from mk_utils.utils.filereader import FileReader
from mk_utils.utils.structs import Struct, hex_s
from requests.utils import CaseInsensitiveDict


class GUID(Struct):
    __slots__ = ()
    _fields_ = [
        ("Data1", c_uint32),
        ("Data2", c_uint16),
        ("Data3", c_uint16),
        ("Data4", c_ubyte * 8),
    ]

    def __str__(self):
        d1 = f"{self.Data1:08X}"
        d2 = f"{self.Data2:04X}"
        d3 = f"{self.Data3:04X}"
        d4 = "".join(f"{b:02X}" for b in self.Data4)
        return f"{d1}-{d2}-{d3}-{d4[:4]}-{d4[4:]}"


class MK11TableMeta(Struct):
    _fields_ = [
        ("entries", c_uint32),
        ("offset", c_uint64),
    ]


class MK11AssetHeader(Struct):
    _fields_ = [
        # Headers / FileSummary
        ("magic", c_uint32),
        ("file_version", c_uint16),
        ("licensee_version", c_uint16),
        ("exports_location", c_uint32),  # 2nd Package (Package) / Header End
        ("shader_version", c_uint32),
        ("engine_version", c_uint32),
        ("midway_team_four_cc", c_char * 4),
        ("midway_team_engine_version", c_uint32),
        ("cook_version", c_uint32),
        # Package
        ("main_package", c_char * 4),
        ("package_flags", c_uint32),
        # End FileSummary
        # Tables
        ("name_table", MK11TableMeta),
        # ("name_table_entries", c_uint32),
        # ("name_table_offset", c_uint64),  # 1st Package
        ("export_table", MK11TableMeta),
        # ("export_table_entries", c_uint32),
        # ("export_table_offset", c_uint64),
        ("import_table", MK11TableMeta),
        # ("import_table_entries", c_uint32),
        # ("import_table_offset", c_uint64),
        ("bulk_data_offset", c_uint64),
        ("guid", GUID),
        ("compression_flag", c_uint32),
        # ("packages_count", c_uint32),
    ]

class MK11AssetExternalTable(Struct):
    def __init__(self, *args: Any, **kw: Any) -> None:
        super().__init__(*args, **kw)

        self.unk_1 = c_uint32
        self.unk_2 = c_uint32
        self.name_length = c_uint32
        self.name = c_char
        self.entries_count = c_uint32

    @classmethod
    def read(cls, file_handle):
        struct = cls()
        struct.unk_1 = cls.read_buffer(file_handle, struct.unk_1)
        struct.unk_2 = cls.read_buffer(file_handle, struct.unk_2)
        struct.name_length = cls.read_buffer(file_handle, struct.name_length)
        struct.name = cls.read_buffer(file_handle, struct.name * struct.name_length)
        struct.entries_count = cls.read_buffer(file_handle, struct.entries_count)
        return struct

    def serialize(self) -> bytes:
        data = b''
        data += self._to_little(self.unk_1, 4)
        data += self._to_little(self.unk_2, 4)
        data += self._to_little(self.name_length, 4)
        data += self.name.encode('ascii') if isinstance(self.name, str) else self.name # type: ignore
        data += self._to_little(self.entries_count, 4)
        return data


class MK11ExternalTableEntry(Struct):
    __slots__ = ()
    _fields_ = [
        ("decompressed_size", c_uint64),
        ("compressed_size", c_uint64),
        ("decompressed_offset", c_uint64),
        ("compressed_offset", c_uint64),
    ]


class MK11Archive(FileReader):
    def __init__(self, source):
        super().__init__(source)
        self.parsed = False
    
    def read_buffer(self, size):
        return Struct.read_buffer(self.mm, size)

    def parse_header(self):
        header = MK11AssetHeader.read(self.mm)
        return header

    def parse_file_meta(self) -> str:
        file_name_length = Struct.read_buffer(self.mm, c_uint32)
        file_name = Struct.read_buffer(
            self.mm, c_char * file_name_length
        ).decode()
        return file_name

    def parse_file_table(self):
        tables_count = Struct.read_buffer(self.mm, c_uint32)
        tables = list(self.parse_filetable_tables(tables_count))
        return tables

    def parse_filetable_tables(self, count):
        for _ in range(count):
            table = MK11AssetExternalTable.read(self.mm)
            entries = list(self.parse_filetable_table_entries(table.entries_count))
            table.add_member("entries", entries)
            yield table

    def parse_filetable_table_entries(self, count):
        yield from (MK11ExternalTableEntry.read(self.mm) for _ in range(count))    

class UETableEntryBase: # TODO: To be moved to UE_Common
    @property
    def file_name(self):
        raise NotImplementedError(f"Abstract Class Method not implemented!")

    @property
    def file_dir(self):
        raise NotImplementedError(f"Abstract Class Method not implemented!")

    @property
    def full_name(self): 
        raise NotImplementedError(f"Abstract Class Method not implemented!")

    @property
    def path(self): 
        raise NotImplementedError(f"Abstract Class Method not implemented!")

class MK11TableEntry(Struct):
    @classmethod
    def resolve_object(
        cls, value, import_table: list, export_table: list
    ) -> Union["MK11NoneTableEntry", "MK11ImportTableEntry", "MK11ExportTableEntry"]:
        if value == 0:
            return MK11NoneTableEntry()
        if value < 0:
            value = -(value + 1)
            import_: MK11ImportTableEntry = import_table[value]
            return import_
        if value > 0:
            value -= 1
            export_: MK11ExportTableEntry = export_table[value]
            return export_

        raise ValueError(f"Impossible Situation")
    
    def __init__(self, *args: Any, **kw: Any) -> None:
        super().__init__(*args, **kw)
        self.name: str = ""

    def __new__(cls):
        obj = super().__new__(cls)
        setattr(obj, "name", "")
        return obj

class MK11NoneTableEntry(MK11TableEntry):
    def __bool__(self):
        return False


class MK11ExportTableEntry(MK11TableEntry, UETableEntryBase):
    _fields_ = [
        ("object_class", c_int32), # 0 = None, > 0 = exports[i-1], < 0 = imports[abs(i)-1]
        ("object_outer_class", c_int32), # 0 = None, > 0 = exports[i-1], < 0 = imports[abs(i)-1]
        ("object_name", c_int32), # names[i]
        ("object_name_suffix", c_uint32),
        ("object_super", c_int32), # 0 = None, > 0 = exports[i-1], < 0 = imports[abs(i)-1]
        ("object_flags", c_uint64),
        ("object_guid", GUID),
        ("object_main_package", c_uint32), # names[i]
        ("unk_1", c_uint32),
        ("object_size", c_uint32),
        ("object_offset", c_uint64),
        ("unk_2", c_uint64),
        ("unk_3", c_uint32),
    ]

    @property
    def file_name(self):
        name = self.name
        if self.suffix:
            name += f".{self.suffix}"
        if self.class_:
            name += f".{self.class_.name}"
        return name

    @property
    def file_dir(self):
        dir = f"/{self.package}/" # TODO: Package should not be present, instead it should be part of a map file that links packages
        dir += self.path
        return dir

    @property
    def full_name(self):
        full_name = self.file_dir
        full_name += self.file_name
        return full_name

    @property
    def path(self):
        path = []

        super_ = self.class_outer
        while super_:
            path.append(super_.name)
            super_ = super_.class_outer

        if not path:
            return ''

        return "/".join(path[::-1]) + '/'

    def __str__(self):
        string = ""
        if self.package:
            string += f"[{self.package}] "
        string += self.path
        string += self.file_name
        if self.class_super:
            string +=f' : {self.class_super.name}'
        return string

    def __repr__(self) -> str:
        return (
            f"package={hex_s(self.object_main_package)} "
            f"folder={hex_s(self.object_outer_class)} "
            f"class={hex_s(self.object_class)} "
            f"super={hex_s(self.object_super)} "
            f"name={hex_s(self.object_name)}: {self.name}"
        )

    def resolve(self, name_table: list, import_table: list, export_table: list):
        object_class = self.resolve_object(self.object_class, import_table, export_table)
        object_outer_class = self.resolve_object(self.object_outer_class, import_table, export_table)
        name = name_table[self.object_name]
        object_super = self.resolve_object(self.object_super, import_table, export_table)
        package = name_table[self.object_main_package]

        self.class_ = object_class # File Extension
        self.class_outer = object_outer_class # Unknown
        self.name = name
        self.suffix = self.object_name_suffix
        self.class_super = object_super # Unknown
        self.package = package # MK11 Metadata

        logging.getLogger("Common").debug(f"Resolved Export: {self.full_name}")

        # self.file = "" # Either Bulk, UPK, PSF... etc # I think this is in another function


class MK11ImportTableEntry(MK11TableEntry, UETableEntryBase):
    _fields_ = [
        ("import_class_package", c_int32), # Package/Other/HeaderData
        ("import_name", c_int32),
        ("import_name_suffix", c_int32),
        ("import_outer_class", c_int32),
        ("object_name", c_int32), # 1 when root, 0 else
    ]

    @property
    def full_name(self):
        name = self.path
        name += self.name
        if self.suffix:
            name += f".{self.suffix}"

        return name

    @property
    def path(self):
        path = []

        super_ = self.package
        while super_:
            path.append(super_.name)
            super_ = super_.package

        if not path:
            return '/'

        return '/' + '/'.join(path[::-1]) + '/'

    def __str__(self):
        string = ""
        string += self.path
        string += self.name
        if self.outer_class:
            string += f" : {self.outer_class.name}"
        if self.unknown:
            string += f" -- {self.object_name}"
        return string

    def __repr__(self) -> str:
        return (
            f"folder={hex_s(self.import_class_package)} "
            f"outer={hex_s(self.import_outer_class)} "
            f"unknown={hex_s(self.object_name)} "
            f"{hex_s(self.import_name)}: {self.name}"
        )

    def resolve(self, name_table: list, import_table: list, export_table: list):
        self.package = self.resolve_object(self.import_class_package, import_table, export_table)
        self.name = name_table[self.import_name]
        self.suffix = self.import_name_suffix
        self.outer_class = self.resolve_object(self.import_outer_class, import_table, export_table) # Uknown
        self.unknown = self.resolve_object(self.object_name, import_table, export_table) # Unknown

        logging.getLogger("Common").debug(f"Resolved Import: {self.full_name}")


class ClassHandler(FileReader): # TODO: To be moved later to UE_Common or UE_Utils
    HANDLED_TYPES: Iterable = {}

    def __init__(self, file_path, name_table: List[str]) -> None:
        super().__init__(file_path)

        self.name_table = name_table

    def parse(self):
        raise NotImplementedError(f"Implement me")

    @classmethod
    def make_save_path(cls, export: UETableEntryBase, asset_name: str, save_path: str):
        if not save_path:
            raise ValueError(f"Missing save_path!")

        save_path = os.path.join(save_path, asset_name, "parsed_exports", export.path.lstrip("/"))
        os.makedirs(save_path, exist_ok=True)
        return os.path.join(save_path, export.file_name)

    def save(self, data: Any, export: UETableEntryBase, asset_name: str, save_path: str) -> str:
        raise NotImplementedError(f"Implement me")

    @classmethod
    def register_handlers(cls):
        for type_ in cls.HANDLED_TYPES:
            logging.getLogger("ClassHandler").debug(f"Type {type_} handled by {cls}.")
            assign_handlers(cls, type_)


class ClassHandlerItemType(TypedDict):
    handler_class: Type[ClassHandler]
    args: Tuple[Any, ...]


ClassHandlerType = CaseInsensitiveDict[ClassHandlerItemType]
class_handlers: ClassHandlerType = CaseInsensitiveDict()


def assign_handlers(handler: Type[ClassHandler], handler_class: str, *handler_args: Any):
    if handler_class in class_handlers:
        raise ValueError(f"Clashing with handler {handler_class}")

    class_handlers[handler_class] = {
        "handler_class": handler,
        "args": handler_args,
    }


def get_handlers(): # TODO: This should accept a GAME and handle the registration and class_handlers should be per game
    return class_handlers
