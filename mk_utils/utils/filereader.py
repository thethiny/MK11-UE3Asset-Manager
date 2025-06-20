import mmap
from pathlib import Path
from typing import Union


class FileReader:
    def __init__(self, source: Union[bytes, str, Path, mmap.mmap, "FileReader"]):
        if isinstance(source, (str, Path)):
            self.file = open(source, "rb")
            self.mm = mmap.mmap(self.file.fileno(), 0, access=mmap.ACCESS_READ)
            self.owns_file = True
        elif isinstance(source, (bytes, bytearray)):
            self.file = None
            self.mm = mmap.mmap(-1, len(source))
            self.mm.write(source)
            self.mm.seek(0)
            self.owns_file = False
        elif isinstance(source, mmap.mmap):
            self.file = None
            self.mm = source
            self.owns_file = False
        elif isinstance(source, FileReader):
            self.file = source.file
            self.mm = source.mm
            self.owns_file = source.owns_file
        else:
            raise TypeError("Expected a file path or bytes.")

    def close(self):
        self.mm.close()
        if self.file:
            self.file.close()

    def __del__(self):
        try:
            self.close()
        except Exception:
            pass

    def tell(self):
        return hex(self.mm.tell())

    def skip(self, amt):
        self.mm.seek(amt, 1)
