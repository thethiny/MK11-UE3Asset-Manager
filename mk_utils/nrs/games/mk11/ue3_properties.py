import logging
from ctypes import c_char, c_float, c_ubyte, c_uint32, c_uint64
from typing import Dict, Tuple, Type

from mk_utils.nrs.ue3_common import GUID
from mk_utils.nrs.games.mk11.enums import enumMaps
from mk_utils.utils.structs import Struct

warned_classes = set()

class UProperty:
    def __init__(self) -> None:
        self.name: str = ""
        self.type: str = ""
        self.value: Dict = {}

    @classmethod
    def read_type(cls, file_handle, name_table) -> Tuple[str, str]:
        name = Struct.read_buffer(file_handle, c_uint64)
        name = name_table[name]
        if name == "None":
            return "", ""

        type = Struct.read_buffer(file_handle, c_uint64)
        type = name_table[type]

        return name, type

    @classmethod
    def _fix_property_size(cls):
        if cls == BoolProperty:
            return 4

        raise ValueError(f"Error: Property Size was 0 for {cls}!")

    @classmethod
    def read(
        cls, file_handle, name_table, headers: bool = True, key_name: str = ""
    ):  # cls is the property type
        # property_size = cls.read_headers(file_handle, name_table, headers)
        property_size = Struct.read_buffer(file_handle, c_uint64)
        if property_size == 0:
            property_size = cls._fix_property_size()

        if headers:
            parsed_headers = cls.read_headers(file_handle, name_table)
            s_t = StructPropertyMap.get(parsed_headers.get("struct_type", ""))
            if s_t:
                cls = s_t

        start_tell = file_handle.tell()  # Tell starts after headers

        data = cls.read_data(
            file_handle,
            name_table=name_table,
            headers=headers,
            read_size=property_size,
            key_name=key_name,
            **parsed_headers,
        )

        end_tell = file_handle.tell()
        total_read = end_tell - start_tell

        if property_size != -1 and total_read != property_size:
            raise ValueError(f"Read {total_read} | Expected {property_size}")

        return data

    @classmethod
    def read_headers(cls, file_handle, name_table, *args, **kwargs):
        return {}

    @classmethod
    def read_data(cls, file_handle, name_table, headers, *args, **kwargs):
        raise NotImplementedError(f"Implement me!")

    @classmethod
    def parse_once(cls, file_handle, name_table, headers):
        name, type_ = cls.read_type(file_handle, name_table)

        if not name:
            return None

        type_class = PropertyMap.get(type_, None)
        if not type_class:
            raise NotImplementedError(f"Couldn't match Property Type {type_}!")

        value = type_class.read(
            file_handle, name_table=name_table, headers=True, key_name=name
        )

        return {name: value}


class StrProperty(UProperty):
    @classmethod
    def read_data(cls, file_handle, *args, **kwargs):
        string_size = Struct.read_buffer(file_handle, c_uint32)
        string = Struct.read_buffer(file_handle, c_char * string_size).decode("ascii")

        return string


class NameProperty(UProperty):
    @classmethod
    def read_data(cls, file_handle, name_table, *args, **kwargs):
        name = Struct.read_buffer(file_handle, c_uint64)
        name = name_table[name]

        return name


class IntProperty(UProperty):
    @classmethod
    def read_data(cls, file_handle, read_size, *args, **kwargs):
        value = Struct.read_buffer(file_handle, read_size, signed=True)
        return value


class EnumProperty(UProperty):
    @classmethod
    def read_data(cls, file_handle, read_size, key_name, *args, **kwargs):
        value = Struct.read_buffer(file_handle, read_size)
        enum_class = enumMaps.get(key_name)
        if enum_class:
            return f"{enum_class.__name__}::{enum_class(value).name}"
        return f"{key_name}::{value}"


class DWordProperty(UProperty):
    @classmethod
    def read_data(cls, file_handle, read_size, *args, **kwargs):
        value = Struct.read_buffer(file_handle, read_size)
        return value

class QWordProperty(DWordProperty): ...

class MultiDWordProperty(DWordProperty):
    # This class is just for a very specific usecase and is unofficial
    @classmethod
    def read_data(cls, file_handle, key_size, val_size, *args, **kwargs):
        key = Struct.read_buffer(file_handle, key_size)
        value = Struct.read_buffer(file_handle, val_size)
        return {key: value}


class MapProperty(UProperty):
    @classmethod
    def read_data(
        cls, file_handle, name_table, headers, key_name: str = "", *args, **kwargs
    ):
        elements = Struct.read_buffer(file_handle, c_uint32)
        if key_name in ["mUnlockNameMap"]:  # TMap<FName, int64>
            key_type = NameProperty
            key_args = (name_table,)
            val_type = MultiDWordProperty
            val_args = (c_uint32, c_uint32)
            multi = False
        elif key_name in ["mUnlockTypeMap"]:  # TMultiMap<uchar, FName>
            key_type = DWordProperty
            key_args = (c_ubyte,)
            val_type = NameProperty
            val_args = (name_table,)
            multi = True
        elif key_name in ["DefaultUnlocks"]:  # TMap<FItemDefinitionHandle, int32>
            key_type = StructProperty
            key_args = name_table, headers
            val_type = DWordProperty
            val_args = (c_ubyte,)
            multi = False
        elif key_name in ["NameToItemHandleLookup"]:  # TMap<StrProperty, FItemDefinitionHandle>
            key_type = StrProperty
            key_args = ()
            val_type = StructProperty
            val_args = name_table, headers
            multi = False
        else:
            raise NotImplementedError(f"Unsupported Map {key_name}")

        object = {}
        for i in range(elements):
            key = key_type.read_data(file_handle, *key_args)
            if key_type == StructProperty:
                if isinstance(key, dict) and len(key.keys()) == 1:
                    key = list(key.values())[0]
                else:
                    raise TypeError(
                        f"StructProperty can only be indexed when only 1 key exists!"
                    )
            value = val_type.read_data(file_handle, *val_args)
            if multi:
                object.setdefault(key, []).append(value)
            else:
                if key in object:
                    raise KeyError(
                        f"Error: Key {key} already exists in object but `multi` was False!"
                    )
                object[key] = value

        return object


class FloatProperty(UProperty):
    @classmethod
    def read_data(cls, file_handle, *args, **kwargs):
        value = Struct.read_buffer(file_handle, c_float)
        return value


class BoolProperty(UProperty):
    @classmethod
    def read_data(cls, file_handle, *args, **kwargs):
        value = Struct.read_buffer(file_handle, c_uint32)
        return value == 1


class StructProperty(UProperty):
    @classmethod
    def read_data(cls, file_handle, name_table, headers, *args, **kwargs):
        object = {}
        while True:
            value = cls.parse_once(file_handle, name_table, headers)
            if value is None:
                break
            object.update(value)
        return object

    @classmethod
    def read_headers(cls, file_handle, name_table):
        struct_type = NameProperty.read_data(file_handle, name_table)

        return {
            "struct_type": struct_type,
        }


class FGuid(StructProperty):
    @classmethod
    def read_data(cls, file_handle, *args, **kwargs):
        object = str(Struct.read_buffer(file_handle, GUID))
        return object


class ArrayProperty(UProperty):
    @classmethod
    def read_data(
        cls,
        file_handle,
        name_table,
        headers: bool = True,
        key_name: str = "",
        *args,
        **kwargs,
    ):
        elements_count = Struct.read_buffer(file_handle, c_uint32)

        data = []
        if key_name in ["mUnlockPagesSentForOnline"]:  # TArray<u_long>
            subtype = DWordProperty
            args = (c_uint32,)
        elif key_name in ["mUnlockedByDefault", "mUnlockedForDev"]:  # TArray<FName>
            # subtype = DWordProperty
            # args = c_uint64,
            subtype = NameProperty
            args = (name_table,)
        else:
            if (
                key_name
                not in [  # TArray<subclassOfStructProperty>
                    # MK11UNLOCKTABLE
                    "mUnlockPages",
                    "mUnlocks",
                    # KOLLECTIONITEMDATA
                    "mItems",
                    "mAudioMapping",
                    # MK11ITEMDATABASE
                    "Characters",
                    "Sockets",
                    "DefaultItems",
                    "DefaultCharacterLoadouts",
                    "States",
                    "Challenges",
                    "Attributes",
                    "Slots",
                    "ItemSequences",
                    "Items",
                    "Parameters",
                    "ItemPrerequisites",
                    "VisualAssets",
                    "PlayerStatChallenges",
                ]
                and key_name not in warned_classes
            ):  # Only warn once
                logging.getLogger("Database").warning(
                    f"Type {key_name} is not officially supported! Proceed with caution!"
                )
                warned_classes.add(key_name)
            subtype = StructProperty
            args = name_table, False  # headers = False

        for i in range(elements_count):
            value = subtype.read_data(file_handle, *args)
            data.append(value)

        return data


PropertyMap: Dict[str, Type[UProperty]] = {
    "StrProperty": StrProperty,
    "IntProperty": IntProperty,
    "FloatProperty": FloatProperty,
    "BoolProperty": BoolProperty,
    "StructProperty": StructProperty,
    "ArrayProperty": ArrayProperty,
    "EnumProperty": EnumProperty,
    "DWordProperty": DWordProperty,
    "QWordProperty": QWordProperty,
    "MapProperty": MapProperty,
    "NameProperty": NameProperty,
}

StructPropertyMap: Dict[str, Type[StructProperty]] = {"FGuid": FGuid}
