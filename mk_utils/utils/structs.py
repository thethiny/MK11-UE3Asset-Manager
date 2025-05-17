from ctypes import Array, Structure, addressof, sizeof, string_at, c_byte, c_ubyte
from typing import Any, Type, TypeVar


T = TypeVar("T", bound="Struct")


def hex_s(a: int):
    return f"-{abs(a):X}" if a < 0 else f"{a:X}"


class Struct(Structure):
    _pack_ = 1

    def __str__(self) -> str:
        string = ""
        for name, _ in self._fields_:  # type: ignore
            value = getattr(self, name)
            if isinstance(value, int):
                string += f"{name} = 0x{value:X}"
            elif isinstance(value, Array):
                vals = [f"0x{v:X}" if isinstance(v, int) else str(v) for v in value]
                string += f"{name} = {', '.join(vals)}"
            else:
                string += f"{name} = {value}"

            string += "\n"
        return string.strip("\n")

    @classmethod
    def read(cls: Type[T], file_handle) -> T:
        return cls.read_buffer(file_handle, cls)

    @classmethod
    def read_buffer(cls, file_handle, read_type: Type, signed=False) -> Any:
        if isinstance(read_type, int):
            value = (c_ubyte * read_type).from_buffer_copy(
                file_handle, file_handle.tell()
            )
            file_handle.seek(read_type, 1)
            return int.from_bytes(value, "little", signed=signed)
        else:
            value = read_type.from_buffer_copy(file_handle, file_handle.tell())
            file_handle.seek(sizeof(read_type), 1)
        if issubclass(read_type, Structure):
            return value
        elif hasattr(value, "value"):
            return value.value
        elif isinstance(value, Array) and issubclass(value._type_, (c_ubyte, c_byte)):
            return bytes(value)
        else:
            raise TypeError(f"Unsupported read_type: {read_type}")

    @classmethod
    def _to_little(cls, val, size):
        return val.to_bytes(size, "little") if isinstance(val, int) else bytes(val)

    def serialize(self):
        return string_at(addressof(self), sizeof(self))

    def add_member(self, key, value):
        if hasattr(self, key):
            raise ValueError(
                f"Overwriting existing attribute: {key} in {self.__class__.__name__}"
            )
        setattr(self, key, value)
