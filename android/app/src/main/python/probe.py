import json
from pathlib import Path

from PIL import Image
from rapidfuzz import fuzz, process
import requests

from playlist_manager import PlaylistManager


def dependencies():
    image = Image.new("RGB", (1, 1), "red")
    match = process.extractOne("RetroArch", ["RetroArch"], scorer=fuzz.ratio)
    return f"RapidFuzz {match[1]:.0f} · Pillow {image.getpixel((0, 0))} · Requests {requests.__version__}"


def preview(path, output):
    playlist = PlaylistManager(path)
    if playlist.data.get("retroarch_assistant_probe") is not True or len(playlist.items) != 1:
        raise ValueError("请选择包含标记且只有一条记录的测试列表")

    entry = playlist.items[0]
    label, launch_path = entry.get("label"), entry.get("path")
    if not isinstance(label, str) or not label or not isinstance(launch_path, str) or not launch_path:
        raise ValueError("测试条目需要名称和 RetroArch 启动路径")
    new_label = label if label.endswith(" [RAA]") else label + " [RAA]"
    playlist.update_label(0, new_label)
    playlist.save(Path(output))
    return json.dumps({"before": label, "after": new_label, "launchPath": launch_path}, ensure_ascii=False)
