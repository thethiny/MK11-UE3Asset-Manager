import logging

from nrs.game.PropertyTypes import get_handlers
from nrs.archive import MK11UE3Asset

ClassHandlers = get_handlers()

OUTPUT_DIR = "extracted"

file_in = [
    "Databases/MK11UNLOCKTABLE.xxx",
    "Databases/KOLLECTIONITEMDATA.xxx",
    "Databases/MK11ItemDatabase.xxx",
]

logging.basicConfig(level=logging.DEBUG)

if __name__ == "__main__":
    for file in file_in:
        logging.getLogger("Main").info(f"Parsing {file}")

        mk11_asset = MK11UE3Asset(file)
        midway_file = mk11_asset.parse_all(save_path=OUTPUT_DIR)

        for export in midway_file.export_table:
            file_type = export.class_.name            
            handler = ClassHandlers.get(file_type)
            if not handler:
                continue

            handler_class = handler["handler_class"]
            # handler_args = handler["args"]

            midway_file.parse_and_save_export(export, handler_class, OUTPUT_DIR)

