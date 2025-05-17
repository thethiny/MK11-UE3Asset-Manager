import os

def split_path(full_path: str):
    path = os.path.dirname(full_path)
    file_name = os.path.basename(full_path)
    name, extension = os.path.splitext(file_name)
    return path, name, extension
