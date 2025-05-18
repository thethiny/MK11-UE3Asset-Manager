from ctypes import c_int32, c_int64, c_uint32, c_wchar
from genericpath import isfile
import logging
import os
from Crypto.Cipher import AES

from assets.mk_utils.utils import split_path
from assets.mk_utils.utils.filereader import FileReader
from assets.mk_utils.utils.structs import Struct


class LocalizationParser(FileReader):
    AES_KEY = b"\x93\xbb\x69\xdf\x37\xd5\x38\x57\xb8\x6b\x20\xe1\x45\xcb\xa0\x61\xdd\x7d\xcf\xed\x3a\xac\xf2\xdb\x29\x35\x91\x6c\x27\x66\x0b\xaf"
    CIPHER = AES.new(AES_KEY, AES.MODE_ECB)

    def __init__(self, localization_file: str, decrypted_out_dir: str = "", aes_key: bytes = b"") -> None:
        super().__init__(localization_file)

        self.locale = os.path.splitext(localization_file)[1][1:].upper()

        val_1, val_2 = Struct.read_buffer(self.mm, c_int32, signed=True), Struct.read_buffer(self.mm, c_int32, signed=True)
        self.mm.seek(-8, 2)
        val_3 = Struct.read_buffer(self.mm, c_int64)
        if val_1 < 0 or val_2 > 0 or val_3 != 0:  # Change this later
            logging.getLogger("LocalizationParser").debug("Encrypted File Detected")
            self.decrypt(decrypted_out_dir, aes_key)

    def decrypt(self, save_dir: str = "", aes_key: bytes = b""):
        if aes_key:
            cipher = AES.new(aes_key, AES.MODE_ECB)
        else:
            cipher = self.CIPHER
        
        padded_len = (len(self.mm) + 15) & ~15
        padded_data = self.mm[:].ljust(padded_len, b"\x00")
        decrypted = cipher.decrypt(padded_data)

        if save_dir:
            file_out_dir = os.path.join(save_dir, "Localization", "decrypted")
            os.makedirs(file_out_dir, exist_ok = True) 
            file_out = os.path.join(file_out_dir, f"Coalesced.{self.locale}")
            with open(file_out, "wb") as f:
                f.write(decrypted)
                logging.getLogger("LocalizationParser").debug(f"File written to {file_out}")

        self.close()
        super().__init__(decrypted)

    def extract_files(self, save_dir: str = "extracted"):#, merge: bool = False): # If merge is true then all files extract into the same fodler
        # On save files should be padded to 0x16 for proper AES
        text_sections_count = Struct.read_buffer(self.mm, c_uint32)
        # file_out_dir = os.path.join(save_dir, "Localization", "merged" if merge else self.locale, "contents")
        file_out_dir = os.path.join(save_dir, "Localization", "contents")
        for i in range(0, text_sections_count, 2):
            path_length = abs(Struct.read_buffer(self.mm, c_int32, signed=True))
            file_path: str = Struct.read_buffer(self.mm, c_wchar * path_length)
            
            logging.getLogger("LocalizationParser").debug(f"Extracting file {i:0>2}: {file_path}")

            content_length = abs(Struct.read_buffer(self.mm, c_int32, signed=True))
            content: str = Struct.read_buffer(self.mm, c_wchar * content_length)

            if save_dir:
                path, name, extension = split_path(file_path)
                full_out_path = os.path.join(file_out_dir, path)
                os.makedirs(full_out_path, exist_ok=True)
                
                file_out = os.path.join(full_out_path, f"{name}{extension}")
                with open(file_out, "w+", encoding="utf-16-le", newline="") as f:
                    f.write(content) # On save requires null terminator 00 00
                    
            yield file_path, content
