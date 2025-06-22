from ctypes import c_uint32, c_uint64
from enum import IntEnum
import json
import logging
import os
from mk_utils.nrs.games.mk11.class_handlers.bc7 import make_dds_data, make_png_data
from mk_utils.nrs.games.mk11.ue3_properties import UProperty
from mk_utils.nrs.ue3_common import ClassHandler, MK11ExportTableEntry
from mk_utils.utils.structs import Struct

class TextureAddress(IntEnum):
    TA_Wrap = 0
    TA_Clamp = 1
    TA_Mirror = 2
    TA_BlackBorder = 3
    TA_MAX = 4

class EPixelFormat(IntEnum):
    PF_Unknown = 0
    PF_A32B32G32R32F = 1
    PF_A8R8G8B8 = 2
    PF_G8 = 3
    PF_G16 = 4
    PF_DXT1 = 5
    PF_DXT3 = 6
    PF_DXT5 = 7
    PF_UYVY = 8
    PF_FloatRGB = 9
    PF_FloatRGBA = 10
    PF_DepthStencil = 11
    PF_ShadowDepth = 12
    PF_FilteredShadowDepth = 13
    PF_R32F = 14
    PF_FloatRGBA_Full = 15
    PF_R16G16_UNORM = 16
    PF_R16G16_SNORM = 17
    PF_R16G16_FLOAT = 18
    PF_G32R32F = 19
    PF_A2B10G10R10 = 20
    PF_BC6 = 21
    PF_BC7 = 22
    PF_A16B16G16R16 = 23
    PF_D24 = 24
    PF_R16F = 25
    PF_R16_UNORM = 26
    PF_BC5 = 27
    PF_V8U8 = 28
    PF_A1 = 29
    PF_FloatR11G11B10 = 30
    PF_X24S8 = 31
    PF_R8 = 32
    PF_R8_UInt = 33
    PF_G8R8 = 34
    PF_R32G32B32A32 = 35
    PF_R8G8B8A8_Signed = 36
    PF_S8 = 37
    PF_FloatR9G9B9E5 = 38
    PF_A8R8G8B8_SRGB = 39
    PF_Depth16Stencil = 40
    PF_R32_UInt = 41
    PF_BC4 = 42
    PF_B4G4R4A4 = 43
    PF_R16_UInt = 44
    PF_R16G16B16A16_UInt = 45
    PF_R32G32_UInt = 46
    PF_D32 = 47
    PF_FloatRGB_Full = 48
    PF_R16G16_UInt = 49
    PF_COUNT = 50

class TextureQualitySettings(IntEnum):
    TQ_QualityProduction = 0
    TQ_QualityHighest = 1
    TQ_QualityFastest = 2
    TQ_Max = 3    

class TextureGroup(IntEnum):
    TEXTUREGROUP_World = 0
    TEXTUREGROUP_WorldNormalMap = 1
    TEXTUREGROUP_Character = 2
    TEXTUREGROUP_CharacterCAP = 3
    TEXTUREGROUP_CharacterNormalMap = 4
    TEXTUREGROUP_CharacterCAPNormalMap = 5
    TEXTUREGROUP_CharacterDetailSmall = 6
    TEXTUREGROUP_CharacterDetailLarge = 7
    TEXTUREGROUP_Weapon = 8
    TEXTUREGROUP_WeaponNormalMap = 9
    TEXTUREGROUP_Effects = 10
    TEXTUREGROUP_Skybox = 11
    TEXTUREGROUP_UI = 12
    TEXTUREGROUP_LightAndShadowMap = 13
    TEXTUREGROUP_RenderTarget = 14
    TEXTUREGROUP_Floor = 15
    TEXTUREGROUP_FullTesting = 16
    TEXTUREGROUP_MobileFlattened = 17
    TEXTUREGROUP_NoMips = 18
    TEXTUREGROUP_System = 19
    TEXTUREGROUP_MAX = 20

class Texture2DHandler(ClassHandler):
    HANDLED_TYPES = {
        "Texture2D",
    }

    enums = {
        "Format": EPixelFormat,
        "AddressX": TextureAddress,
        "AddressY": TextureAddress,
        "LODGroup": TextureGroup,
        "TextureQuality": TextureQualitySettings,
    }

    def parse(self):
        metadata = {}
        while self.mm.tell() != self.mm.size():
            value = UProperty.parse_once(self.mm, self.name_table, True)
            if value is None:
                break
            k, v = next(iter(value.items()))
            if isinstance(v, str) and "::" in v:
                enum_class, enum_value = v.split("::", 1)
                # enum_class = enum_class.strip()
                enum_value = int(enum_value.strip())
                if k in self.enums:
                    cls = self.enums[k]
                    value[k] = f"{cls.__name__}::{cls(enum_value).name}"

            metadata.update(value)

        # Data parsing
        self.mm.seek(20, 1)
        unk_1 = Struct.read_buffer(self.mm, c_uint32)
        self.mm.seek(0x18, 1)
        unk_2 = Struct.read_buffer(self.mm, c_uint32)
        self.mm.seek(0x10, 1)
        mips_count = Struct.read_buffer(self.mm, c_uint32)
        mips = {}
        for index in range(mips_count):
            key = Struct.read_buffer(self.mm, c_uint64)        
            mip_index = Struct.read_buffer(self.mm, c_uint32)
            unk = Struct.read_buffer(self.mm, c_uint32)
            image_size = Struct.read_buffer(self.mm, c_uint64)

            self.mm.seek(4, 1)
            image_width = Struct.read_buffer(self.mm, c_uint32)
            image_height = Struct.read_buffer(self.mm, c_uint32)

            mips[mip_index] = {
                "key": key,
                "index": mip_index,
                "unk": unk,
                "size": image_size,
                "width": image_width,
                "height": image_height
            }

        return {
            "meta": metadata,
            "mips": mips,
            "unks": [unk_1, unk_2],
            "resolution": {
                "size": image_size,
                "width": image_width,
                "height": image_height,
            }
        }

    @classmethod
    def make_save_path(
        cls, export: MK11ExportTableEntry, asset_name: str, save_path: str
    ):
        save_path = super().make_save_path(export, asset_name, save_path)
        return save_path.rsplit(".", 1)[0].strip() + ".json"

    @classmethod
    def make_texture_path(
        cls, export: MK11ExportTableEntry, asset_name: str, save_path: str
    ):
        save_path = super().make_save_path(export, asset_name, save_path)
        return save_path.rsplit(".", 1)[0].strip() + ".dds"

    @classmethod
    def get_dds_path(cls, asset_name, package, bulk_key, file_folder, kind):
        file_path = os.path.join(file_folder, asset_name, kind + "s", package, f'{bulk_key:0>8X}')
        return file_path

    def save(self, data, export, asset_name, save_dir, instance, *args, **kwargs):
        image_file = self.make_texture_path(export, asset_name, save_dir)
        format = EPixelFormat[data["meta"]["Format"].split("::")[-1]]
        bulk_key = data["meta"]["CookedBulkDataOwnerKey"]

        if bulk_key in instance.psf_map:
            bulk_pack = instance.psf_map[bulk_key]
            kind = "psf"
        elif bulk_key in instance.bulk_map:
            bulk_pack = instance.bulk_map[bulk_key]
            kind = "bulk"
        else:
            raise ValueError(f"Couldn't find bulk_key {bulk_key:0>8X}")

        package_name = bulk_pack.package_name.decode()

        if format in {
            EPixelFormat.PF_BC4,
            EPixelFormat.PF_BC5,
            EPixelFormat.PF_BC6,
            EPixelFormat.PF_BC7,
        }:
            raw_bytes_folder = self.get_dds_path(asset_name, package_name, bulk_key, save_dir, kind)
            dxgi_map = {
                EPixelFormat.PF_BC4: 80,   # DXGI_FORMAT_BC4_UNORM
                EPixelFormat.PF_BC5: 83,   # DXGI_FORMAT_BC5_UNORM
                EPixelFormat.PF_BC6: 95,  # DXGI_FORMAT_BC6H_UF16
                EPixelFormat.PF_BC7: 98,   # DXGI_FORMAT_BC7_UNORM
            }
            dxgi_format = dxgi_map[format]
            if format == EPixelFormat.PF_BC4:
                image_data = make_dds_data(
                    raw_bytes_folder,
                    data["meta"]["SizeX"],
                    data["meta"]["SizeY"],
                    dxgi_format=dxgi_format,
                )
                png_data = None
            else:
                image_data, png_data = make_png_data(
                    raw_bytes_folder,
                    data["meta"]["SizeX"],
                    data["meta"]["SizeY"],
                    dxgi_format=dxgi_format
                )
        else:
            logging.getLogger("Texture2DHandler").warning(f"Texture2D Format {format.name} is not yet supported!")
            return

        if image_data:
            with open(image_file, "wb") as f:
                f.write(image_data)
        if png_data:
            png_data.save(image_file.rsplit(".", 1)[0] + ".png")

        save_file = self.make_save_path(export, asset_name, save_dir)
        # Save json last cuz it's what determines success
        with open(save_file, "w+") as f:
            json.dump(data, f, ensure_ascii=False, indent=4)

        return save_file
