import json
from mk_utils.nrs.games.mk11.ue3_properties import UProperty
from mk_utils.nrs.ue3_common import ClassHandler, MK11ExportTableEntry


class DatabaseHandler(ClassHandler):
    HANDLED_TYPES = {
        "mk11unlockdata",
        "mk11kollectioniteminfo",
        "mk11itemdatabase",
    }

    def parse(self):
        data = {}
        while self.mm.tell() != self.mm.size():
            value = UProperty.parse_once(self.mm, self.name_table, True)
            if not value:
                continue
            data.update(value)

        return data
    
    @classmethod
    def make_save_path(cls, export: MK11ExportTableEntry, asset_name: str, save_path: str):
        save_path = super().make_save_path(export, asset_name, save_path)
        return save_path + ".json"

    def save(self, data, export, asset_name, save_dir):
        save_file = self.make_save_path(export, asset_name, save_dir)
        
        with open(save_file, "w+") as f:
            json.dump(data, f, ensure_ascii=False, indent=4)
            
        return save_file
