import asyncio
from pyrogram.types import Message
import time

def test_string():
    url = "https://st22.video.xxxa.net/movies/teamskeetc69/teamskeetc69.m3u8"
    file_name = url.split("/")[-1].split("?")[0]
    file_name = "".join(c for c in file_name if c.isalnum() or c in (' ', '.', '-', '_')).strip()
    print(f"📥 **Downloading Start:** `{file_name}`...")
    print(f"📥 **Downloading M3U8 Stream:** `{file_name}`\n(Isme thoda time lag sakta hai, please wait...)")

test_string()
