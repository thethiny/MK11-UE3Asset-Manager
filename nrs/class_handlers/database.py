import json
from nrs.game.PropertyTypes import ClassHandler, UProperty


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

    def save(self, data, export, asset_name, save_dir):
        save_path = super().save(data, export, asset_name, save_dir)
        save_file = save_path + ".json"
        
        with open(save_file, "w+") as f:
            json.dump(data, f, ensure_ascii=False, indent=4)
