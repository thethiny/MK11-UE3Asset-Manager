import logging
from typing import List, Tuple, Union

from mk_utils.nrs.archive import MK11UE3Asset
from mk_utils.nrs.ue3_common import get_handlers

ClassHandlers = get_handlers()

def extract_all(files: List[Union[Tuple[str, str], str]], output_dir: str = "extracted", overwrite = False):
    saved = []
    for info in files:
        file, psf_source = info if not isinstance(info, str) else (info, "")
        logging.getLogger("Scripts::Extractors").info(f"Parsing {file}")

        mk11_asset = MK11UE3Asset(file, psf_source)
        midway_file = mk11_asset.parse_all(save_path=output_dir)

        for export in midway_file.export_table:
            file_type = export.class_.name
            handler = ClassHandlers.get(file_type)
            if not handler:
                continue

            handler_class = handler["handler_class"]

            saved_file = midway_file.parse_and_save_export(export, handler_class, output_dir, overwrite)
            saved.append(saved_file)
    return saved
