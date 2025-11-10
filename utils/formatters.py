from datetime import datetime
import json

def parse_date(date:str):
    dt = datetime.fromisoformat(date.replace("Z", "+00:00"))
    return dt

def convert_path(path):
    return path.replace("/drive/root:", "")

def human_filesize(size: int) -> str:
    units = ["B", "KiB", "MiB", "GiB"]
    for unit in units:
        if size < 1024:
            return f"{size:.0f} {unit}"
        size /= 1024
    return f"{size:.0f} PiB"

def human_timestamp(timestamp) -> str:
    if type(timestamp) is int:
        date = datetime.fromtimestamp(timestamp)
    else:
        date = timestamp
        
    return date.strftime("%d-%b-%Y %H:%M")