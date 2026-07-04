import os
import time
import asyncio
import json
import re

# --- FIX FOR PYTHON 3.14 ON RENDER ---
try:
    asyncio.get_event_loop()
except RuntimeError:
    asyncio.set_event_loop(asyncio.new_event_loop())
# -------------------------------------

import aiohttp
from pyrogram import Client, filters
from pyrogram.types import Message
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

API_ID = os.getenv("API_ID")
API_HASH = os.getenv("API_HASH")
BOT_TOKEN = os.getenv("BOT_TOKEN")

if not all([API_ID, API_HASH, BOT_TOKEN]):
    print("ERROR: API_ID, API_HASH, ya BOT_TOKEN missing hai .env file me!")
    exit(1)

# Pyrogram Client Setup
app = Client(
    "dlbot",
    api_id=API_ID,
    api_hash=API_HASH,
    bot_token=BOT_TOKEN
)

def human_readable_size(size):
    if not size:
        return "0 B"
    for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
        if size < 1024.0:
            return f"{size:.2f} {unit}"
        size /= 1024.0
    return f"{size:.2f} PB"

def progress_bar(current, total):
    if total == 0:
        return "[====================] 100%"
    percentage = current * 100 / total
    completed = int(percentage / 5)
    bar = "█" * completed + "░" * (20 - completed)
    return f"[{bar}] {percentage:.2f}%"

async def progress_for_pyrogram(current, total, ud_type, message, start_time):
    now = time.time()
    diff = now - start_time
    
    # Update har 5 seconds me ya jab complete ho jaye
    if round(diff) % 5 == 0 or current == total:
        if diff == 0:
            diff = 1
            
        speed = current / diff
        if speed == 0:
            speed = 1
            
        time_to_completion = round((total - current) / speed)
        
        progress = f"{ud_type}\n"
        progress += f"{progress_bar(current, total)}\n"
        progress += f"**Size:** {human_readable_size(current)} / {human_readable_size(total)}\n"
        progress += f"**Speed:** {human_readable_size(speed)}/s\n"
        progress += f"**ETA:** {time_to_completion}s"
        
        try:
            await message.edit_text(progress)
        except Exception:
            pass

@app.on_message(filters.command("start"))
async def start_cmd(client, message):
    await message.reply_text("Hello Bhai! Main ek URL Uploader Bot hu.\n\nMujhe koi bhi direct download link ya playlist file (M3U/JSON) bhejiye, main usko download karke aapko Telegram me upload karke de dunga.")

async def process_single_link(client, chat_id, url, custom_name=None, banner_url=None, prefix=""):
    status_msg = await client.send_message(chat_id, f"⏳ {prefix} Link process kar raha hu...\n`{url}`")
    file_name = "downloaded_file"
    
    try:
        # Extract filename from URL or use custom name
        if custom_name:
            file_name = custom_name
        else:
            file_name = url.split("/")[-1].split("?")[0]
            if not file_name:
                file_name = "downloaded_file"
                
        # ensure no invalid characters in filename
        file_name = "".join(c for c in file_name if c.isalnum() or c in (' ', '.', '-', '_')).strip()
        if not file_name:
            file_name = "downloaded_file"

        await status_msg.edit_text(f"📥 {prefix} **Downloading Start:** `{file_name}`...")

        start_time = time.time()
        last_update = time.time()
        
        if ".m3u8" in url.lower() or "m3u8" in file_name.lower():
            import yt_dlp
            import static_ffmpeg
            static_ffmpeg.add_paths()
            
            if file_name.endswith(".m3u8"):
                file_name = file_name[:-5] + ".mp4"
            elif not file_name.endswith(".mp4"):
                file_name += ".mp4"
                
            await status_msg.edit_text(f"📥 {prefix} **Downloading M3U8 Stream:** `{file_name}`\n(Isme thoda time lag sakta hai, please wait...)")
            
            def download_m3u8():
                ydl_opts = {'outtmpl': file_name, 'format': 'best', 'quiet': True}
                with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                    ydl.download([url])
            
            await asyncio.to_thread(download_m3u8)
            
        else:
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
                "Referer": "/".join(url.split("/")[:3]) + "/" # e.g. https://domain.com/
            }
            async with aiohttp.ClientSession() as session:
                async with session.get(url, headers=headers) as response:
                    if response.status != 200:
                        await status_msg.edit_text(f"❌ {prefix} Error: Download fail ho gaya. Status code: {response.status}")
                        return
                    
                    import email.message
                    import mimetypes
                    import urllib.parse
                    
                    content_dispo = response.headers.get('Content-Disposition')
                    if content_dispo:
                        msg = email.message.EmailMessage()
                        msg['content-type'] = content_dispo
                        filename_from_header = msg.get_param('filename', header='content-type')
                        if filename_from_header:
                            file_name = urllib.parse.unquote(filename_from_header)
                            file_name = "".join(c for c in file_name if c.isalnum() or c in (' ', '.', '-', '_')).strip()
                    
                    if "." not in file_name:
                        content_type = response.headers.get('Content-Type', '').split(';')[0]
                        ext = mimetypes.guess_extension(content_type)
                        if ext:
                            if ext == ".jpe": ext = ".jpg"
                            file_name += ext
                    
                    total_size = int(response.headers.get('content-length', 0))
                    downloaded_size = 0
                    
                    with open(file_name, 'wb') as f:
                        async for chunk in response.content.iter_chunked(1024 * 1024): # 1MB chunks
                            f.write(chunk)
                            downloaded_size += len(chunk)
                            
                            now = time.time()
                            # Har 5 second me progress update
                            if (now - last_update) >= 5:
                                last_update = now
                                prog_str = progress_bar(downloaded_size, total_size)
                                speed = downloaded_size / (now - start_time) if (now - start_time) > 0 else 0
                                try:
                                    await status_msg.edit_text(
                                        f"📥 {prefix} **Downloading...**\n"
                                        f"{prog_str}\n"
                                        f"**Size:** {human_readable_size(downloaded_size)} / {human_readable_size(total_size)}\n"
                                        f"**Speed:** {human_readable_size(speed)}/s"
                                    )
                                except Exception:
                                    pass

        await status_msg.edit_text(f"📤 {prefix} Download Complete! Ab Telegram par upload kar raha hu...")
        
        upload_start_time = time.time()
        
        is_video = file_name.lower().endswith(('.mp4', '.mkv', '.webm', '.avi', '.ts'))
        
        # --- THUMBNAIL / BANNER HANDLING ---
        thumb_path = None
        if banner_url:
            try:
                import aiohttp
                async with aiohttp.ClientSession() as session:
                    async with session.get(banner_url) as resp:
                        if resp.status == 200:
                            thumb_path = f"thumb_{time.time()}.jpg"
                            with open(thumb_path, 'wb') as tf:
                                tf.write(await resp.read())
            except Exception as e:
                print("Banner download error:", e)
                thumb_path = None
        # -----------------------------------

        if is_video:
            width, height, duration = 0, 0, 0
            try:
                import subprocess, json as subprocess_json
                probe_cmd = ["ffprobe", "-v", "quiet", "-print_format", "json", "-show_format", "-show_streams", file_name]
                probe_out = subprocess.check_output(probe_cmd).decode("utf-8")
                probe_data = subprocess_json.loads(probe_out)
                video_stream = next((s for s in probe_data.get('streams', []) if s.get('codec_type') == 'video'), None)
                if video_stream:
                    width = int(video_stream.get('width', 0))
                    height = int(video_stream.get('height', 0))
                duration = int(float(probe_data.get('format', {}).get('duration', 0)))
                
                if not thumb_path:
                    thumb_path = file_name + ".jpg"
                    subprocess.call(["ffmpeg", "-i", file_name, "-ss", "00:00:01.000", "-vframes", "1", thumb_path, "-y", "-v", "quiet"])
            except Exception:
                pass

            await client.send_video(
                chat_id=chat_id,
                video=file_name,
                caption=f"{prefix} **File:** `{file_name}`",
                duration=duration,
                width=width,
                height=height,
                thumb=thumb_path if (thumb_path and os.path.exists(thumb_path)) else None,
                progress=progress_for_pyrogram,
                progress_args=(f"📤 {prefix} **Uploading Video...**", status_msg, upload_start_time)
            )
            if thumb_path and os.path.exists(thumb_path):
                os.remove(thumb_path)
        else:
            await client.send_document(
                chat_id=chat_id,
                document=file_name,
                caption=f"{prefix} **File:** `{file_name}`",
                thumb=thumb_path if (thumb_path and os.path.exists(thumb_path)) else None,
                progress=progress_for_pyrogram,
                progress_args=(f"📤 {prefix} **Uploading...**", status_msg, upload_start_time)
            )
            if thumb_path and os.path.exists(thumb_path):
                os.remove(thumb_path)
        
        # Space bachane ke liye file delete karna
        os.remove(file_name)
        await status_msg.delete()
        
    except Exception as e:
        await status_msg.edit_text(f"❌ {prefix} Error aa gaya bhai: `{str(e)}`")
        if os.path.exists(file_name):
            os.remove(file_name)
        if thumb_path and os.path.exists(thumb_path):
            os.remove(thumb_path)

@app.on_message(filters.text & filters.private & ~filters.command("start"))
async def handle_url(client, message: Message):
    text = message.text.strip()
    
    if "|" in text:
        url, custom_name = text.split("|", 1)
        url = url.strip()
        custom_name = custom_name.strip()
    else:
        url = text
        custom_name = None
        
    if not (url.startswith("http://") or url.startswith("https://")):
        await message.reply_text("Kripya ek valid HTTP/HTTPS URL bhejein bhai.\nAgar custom naam chahiye toh aise bhejein:\n`URL | MyVideo.mp4`")
        return

    await process_single_link(client, message.chat.id, url, custom_name, None)

def parse_json_playlist(file_path):
    items = []
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
            if isinstance(data, list):
                for item in data:
                    url = item.get('url') or item.get('stream_url') or item.get('link') or item.get('stream url')
                    name = item.get('name') or item.get('title')
                    banner = item.get('banner') or item.get('image') or item.get('thumb') or item.get('thumbnail') or item.get('logo')
                    if url:
                        items.append((url, name, banner))
    except Exception:
        pass
    return items

def parse_m3u_playlist(file_path):
    items = []
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            lines = f.readlines()
            name = None
            banner = None
            for line in lines:
                line = line.strip()
                if not line:
                    continue
                if line.startswith('#EXTINF:'):
                    # Extract banner / tvg-logo
                    logo_match = re.search(r'tvg-logo="([^"]+)"', line)
                    if logo_match:
                        banner = logo_match.group(1)
                    
                    parts = line.split(',', 1)
                    if len(parts) > 1:
                        name = parts[1].strip()
                elif not line.startswith('#'):
                    if line.startswith('http://') or line.startswith('https://'):
                        items.append((line, name, banner))
                    name = None
                    banner = None
    except Exception:
        pass
    return items

@app.on_message(filters.document & filters.private)
async def handle_document(client, message: Message):
    doc = message.document
    valid_exts = ['.json', '.m3u', '.m3u8', '.txt']
    
    if not doc.file_name:
        await message.reply_text("File ka naam samajh nahi aa raha hai.")
        return
        
    if not any(doc.file_name.lower().endswith(ext) for ext in valid_exts):
        await message.reply_text("Kripya JSON, M3U, ya TXT file bhejein jisme URLs ho.")
        return
        
    status_msg = await message.reply_text("⏳ File download aur process kar raha hu...")
    
    file_path = await message.download()
    
    items = []
    if file_path.lower().endswith('.json'):
        items = parse_json_playlist(file_path)
    elif file_path.lower().endswith('.m3u') or file_path.lower().endswith('.m3u8') or file_path.lower().endswith('.txt'):
        items = parse_m3u_playlist(file_path)
        
        if not items:
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    for line in f:
                        line = line.strip()
                        if line.startswith("http://") or line.startswith("https://"):
                            items.append((line, None, None))
            except:
                pass
                
    os.remove(file_path)
    
    if not items:
        await status_msg.edit_text("❌ File me koi valid URLs nahi mile. JSON/M3U format check karein.")
        return
        
    await status_msg.edit_text(f"✅ File process ho gayi. Total **{len(items)}** links mile hain. Ab ek-ek karke download start kar raha hu...")
    
    for idx, (url, custom_name, banner_url) in enumerate(items, start=1):
        try:
            await process_single_link(client, message.chat.id, url, custom_name, banner_url, f"[{idx}/{len(items)}]")
        except Exception as e:
            await client.send_message(message.chat.id, f"❌ Link {idx} me error aaya: `{str(e)}`\nURL: `{url}`")
            
    await client.send_message(message.chat.id, f"🎉 Saare {len(items)} links process ho gaye!")

from aiohttp import web

async def web_server():
    async def handle(request):
        return web.Response(text="Bot is running smoothly on Render!")
    
    webapp = web.Application()
    webapp.router.add_get('/', handle)
    runner = web.AppRunner(webapp)
    await runner.setup()
    
    port = int(os.environ.get("PORT", 8080))
    site = web.TCPSite(runner, '0.0.0.0', port)
    await site.start()
    print(f"Web server started on port {port}")

async def main():
    await web_server()
    await app.start()
    print("Bot is successfully running! Telegram me jake /start bhejein.")
    while True:
        await asyncio.sleep(3600)

if __name__ == "__main__":
    loop = asyncio.get_event_loop()
    loop.run_until_complete(main())
