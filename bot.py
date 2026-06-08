import os
import time
import asyncio

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
    await message.reply_text("Hello Bhai! Main ek URL Uploader Bot hu.\n\nMujhe koi bhi direct download link (jaise .mkv, .mp4, .zip) bhejiye, main usko download karke aapko Telegram me upload karke de dunga.")

@app.on_message(filters.text & filters.private & ~filters.command("start"))
async def handle_url(client, message: Message):
    url = message.text.strip()
    
    if not (url.startswith("http://") or url.startswith("https://")):
        await message.reply_text("Kripya ek valid HTTP/HTTPS URL bhejein bhai.")
        return

    status_msg = await message.reply_text("⏳ Link process kar raha hu...")
    file_name = "downloaded_file"
    
    try:
        # Extract filename from URL
        file_name = url.split("/")[-1].split("?")[0]
        if not file_name:
            file_name = "downloaded_file"

        await status_msg.edit_text(f"📥 **Downloading Start:** `{file_name}`...")

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
                
            await status_msg.edit_text(f"📥 **Downloading M3U8 Stream:** `{file_name}`\n(Isme thoda time lag sakta hai, please wait...)")
            
            def download_m3u8():
                ydl_opts = {'outtmpl': file_name, 'format': 'best', 'quiet': True}
                with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                    ydl.download([url])
            
            await asyncio.to_thread(download_m3u8)
            
        else:
            async with aiohttp.ClientSession() as session:
                async with session.get(url) as response:
                    if response.status != 200:
                        await status_msg.edit_text(f"❌ Error: Download fail ho gaya. Status code: {response.status}")
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
                                speed = downloaded_size / (now - start_time)
                                try:
                                    await status_msg.edit_text(
                                        f"📥 **Downloading...**\n"
                                        f"{prog_str}\n"
                                        f"**Size:** {human_readable_size(downloaded_size)} / {human_readable_size(total_size)}\n"
                                        f"**Speed:** {human_readable_size(speed)}/s"
                                    )
                                except Exception:
                                    pass

        await status_msg.edit_text("📤 Download Complete! Ab Telegram par upload kar raha hu...")
        
        upload_start_time = time.time()
        
        # Uploading to Telegram
        is_video = file_name.lower().endswith(('.mp4', '.mkv', '.webm', '.avi'))
        
        if is_video:
            await client.send_video(
                chat_id=message.chat.id,
                video=file_name,
                caption=f"**File:** `{file_name}`",
                progress=progress_for_pyrogram,
                progress_args=("📤 **Uploading Video...**", status_msg, upload_start_time)
            )
        else:
            await client.send_document(
                chat_id=message.chat.id,
                document=file_name,
                caption=f"**File:** `{file_name}`",
                progress=progress_for_pyrogram,
                progress_args=("📤 **Uploading...**", status_msg, upload_start_time)
            )
        
        # Space bachane ke liye file delete karna
        os.remove(file_name)
        await status_msg.delete()
        
    except Exception as e:
        await status_msg.edit_text(f"❌ Error aa gaya bhai: `{str(e)}`")
        if os.path.exists(file_name):
            os.remove(file_name)

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
