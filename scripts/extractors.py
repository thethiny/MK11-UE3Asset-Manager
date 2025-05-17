import logging
from typing import List

from nrs.archive import MK11UE3Asset
from nrs.ue3_common import get_handlers

ClassHandlers = get_handlers()

def extract_all(files: List[str], output_dir: str = "extracted"):
    saved = []
    for file in files:
        logging.getLogger("Scripts::Extractors").info(f"Parsing {file}")

        mk11_asset = MK11UE3Asset(file)
        midway_file = mk11_asset.parse_all(save_path=output_dir)


        for export in midway_file.export_table:
            file_type = export.class_.name
            handler = ClassHandlers.get(file_type)
            if not handler:
                continue

            handler_class = handler["handler_class"]

            saved_file = midway_file.parse_and_save_export(export, handler_class, output_dir)
            saved.append(saved_file)
    return saved