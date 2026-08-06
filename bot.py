import os
import time
import asyncio
import json
import re
import requests
import base64
import urllib.parse
from Cryptodome.Cipher import AES
from Cryptodome.Util.Padding import unpad

# --- FIX FOR PYTHON 3.14 ON RENDER ---
try:
    asyncio.get_event_loop()
except RuntimeError:
    asyncio.set_event_loop(asyncio.new_event_loop())
# -------------------------------------

import aiohttp
from pyrogram import Client, filters
from pyrogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
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

active_processes = {}

def decrypt_shemaroo_url(url_line):
    params_str = url_line.replace('shemaroomovies-', '')
    if params_str.startswith('&'):
        params_str = params_str[1:]
    
    if 'type=' in url_line or 'catalog_id=' in url_line:
        params = dict(urllib.parse.parse_qsl(params_str))
        catalog_id = params.get('catalog_id', '')
        content_id = params.get('content_id', '')
        category = params.get('category', '')
        content_def = params.get('content_def', '')
        body = f"catalog_id={catalog_id}&content_id={content_id}&category={category}&content_def={content_def}&user_agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/146.0.0.0 Safari/537.36"
    else:
        content_id = params_str
        body = f"catalog_id=5b62b824c1df412e5c000000&content_id={content_id}&category=all&content_def=AVOD"

    url = "https://www.shemaroome.com/users/user_all_lists"
    headers = {
        "accept": "*/*",
        "accept-language": "en-IN,en-GB;q=0.9,en-US;q=0.8,en;q=0.7",
        "content-type": "application/x-www-form-urlencoded; charset=UTF-8",
        "sec-ch-ua": '"Not(A:Brand";v="99", "Google Chrome";v="133", "Chromium";v="133"',
        "sec-ch-ua-mobile": "?0",
        "sec-ch-ua-platform": '"Windows"',
        "sec-fetch-dest": "empty",
        "sec-fetch-mode": "cors",
        "sec-fetch-site": "same-origin",
        "x-requested-with": "XMLHttpRequest",
        "Referer": "https://www.shemaroome.com/",
        "Referrer-Policy": "strict-origin-when-cross-origin"
    }

    try:
        response = requests.post(url, headers=headers, data=body, timeout=15)
        response.raise_for_status()
        data = response.json()
        
        if "new_play_url" in data and "key" in data:
            ciphertext = base64.b64decode(data["new_play_url"])
            key = base64.b64decode(data["key"])
            iv = bytes.fromhex("00000000000000000000000000000000")
            
            cipher = AES.new(key, AES.MODE_CBC, iv)
            decrypted = cipher.decrypt(ciphertext)
            
            try:
                decrypted_url = unpad(decrypted, AES.block_size).decode('utf-8')
            except ValueError:
                decrypted_url = decrypted.decode('utf-8').rstrip('\x00')
                
            stream_key = data.get("stream_key", "")
            return decrypted_url, stream_key, data
        else:
            print("Shemaroo API Error: No new_play_url/key found")
            return None, None, None
    except Exception as e:
        print("Shemaroo API Error:", e)
        return None, None, None

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

async def safe_edit_text(msg, text):
    try:
        await msg.edit_text(text)
    except Exception:
        pass

@app.on_message(filters.command("stop"))
async def stop_cmd(client, message):
    chat_id = message.chat.id
    if active_processes.get(chat_id, False):
        active_processes[chat_id] = False
        await message.reply_text("🛑 Process ko rok di gai hai. Current download turant band ho jayega.")
    else:
        await message.reply_text("❌ Koi active process nahi hai rukne ke liye.")

@app.on_callback_query(filters.regex("^stop_process$"))
async def stop_process_cb(client, callback_query: CallbackQuery):
    chat_id = callback_query.message.chat.id
    if active_processes.get(chat_id, False):
        active_processes[chat_id] = False
        await callback_query.answer("🛑 Stopping... (Current download turant ruk jayega)", show_alert=True)
        try:
            await callback_query.message.edit_reply_markup(None)
        except Exception:
            pass
    else:
        await callback_query.answer("❌ Koi process chal nahi raha.", show_alert=True)

async def process_single_link(client, chat_id, url, custom_name=None, banner_url=None, prefix="", quality_text=None, stream_key=None, banner_path=None):
    status_msg = await client.send_message(chat_id, f"⏳ {prefix} Link process kar raha hu...\n`{url}`")
    file_name = "downloaded_file"
    
    try:
        thumb_path = banner_path
        # Extract filename from URL or use custom name
        if custom_name:
            file_name = custom_name
        else:
            import urllib.parse
            parsed_url = urllib.parse.urlparse(url)
            
            # Check if there is a 'url' parameter in query (common for proxies)
            query_params = urllib.parse.parse_qs(parsed_url.query)
            target_url = url
            if 'url' in query_params:
                target_url = query_params['url'][0]
                parsed_url = urllib.parse.urlparse(target_url)
                
            file_name = urllib.parse.unquote(parsed_url.path.split('/')[-1])
            if not file_name:
                file_name = "downloaded_file"
                
        # ensure no invalid characters in filename
        file_name = "".join(c for c in file_name if c.isalnum() or c in (' ', '.', '-', '_')).strip()
        if not file_name or file_name == "." or file_name.startswith(".mp4"):
            file_name = "downloaded_file"

        await safe_edit_text(status_msg, f"📥 {prefix} **Downloading Start:** `{file_name}`...")

        start_time = time.time()
        last_update = time.time()
        
        if ".m3u8" in url.lower() or "m3u8" in file_name.lower():
            if file_name.endswith(".m3u8"):
                file_name = file_name[:-5] + ".mp4"
            elif not file_name.endswith(".mp4"):
                file_name += ".mp4"
                
            await safe_edit_text(status_msg, f"📥 {prefix} **Downloading M3U8 Stream:** `{file_name}`\n(Isme thoda time lag sakta hai, please wait...)")
            
            def download_m3u8():
                import yt_dlp
                import static_ffmpeg
                static_ffmpeg.add_paths()
                ydl_opts = {
                    'outtmpl': file_name, 
                    'format': 'bestvideo+bestaudio/best', 
                    'quiet': True, 
                    'socket_timeout': 30,
                    'nopart': True,
                    'concurrent_fragment_downloads': 1
                }
                if stream_key:
                    ydl_opts['http_headers'] = {'stream_key': stream_key}
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
                        await safe_edit_text(status_msg, f"❌ {prefix} Error: Download fail ho gaya. Status code: {response.status}")
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
                            new_file_name = urllib.parse.unquote(filename_from_header)
                            new_file_name = "".join(c for c in new_file_name if c.isalnum() or c in (' ', '.', '-', '_')).strip()
                            if new_file_name:
                                file_name = new_file_name
                    
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
                            if not active_processes.get(chat_id, True):
                                raise Exception("Download stopped by user.")
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

        await safe_edit_text(status_msg, f"📤 {prefix} Download Complete! File check kar raha hu...")
        
        upload_start_time = time.time()
        
        is_video = file_name.lower().endswith(('.mp4', '.mkv', '.webm', '.avi', '.ts'))
        is_image = file_name.lower().endswith(('.png', '.jpg', '.jpeg', '.webp', '.gif'))
        
        clean_name = os.path.splitext(file_name)[0]
        clean_name = clean_name.replace('.', ' ').replace('-', ' ').replace('_', ' ')
        clean_name = re.sub(r'\s+', ' ', clean_name).strip()
        
        caption_text = f"**{clean_name}**"
        if quality_text:
            caption_text += f"\n\n**Quality:** {quality_text}"
        
        # --- THUMBNAIL / BANNER HANDLING ---
        if banner_url and not thumb_path:
            try:
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

        import math
        file_size = os.path.getsize(file_name) if os.path.exists(file_name) else 0
        max_size = 1950 * 1024 * 1024 # 1950 MB

        upload_items = [file_name]

        if file_size > max_size:
            if is_video:
                await safe_edit_text(status_msg, f"✂️ {prefix} Video 2GB se badi hai ({(file_size/(1024*1024)):.2f}MB). Parts me split kar raha hu, kripya pratiksha karein...")
                duration_for_split = 0
                try:
                    import subprocess, json as subprocess_json
                    probe_cmd = ["ffprobe", "-v", "quiet", "-print_format", "json", "-show_format", file_name]
                    probe_out = subprocess.check_output(probe_cmd).decode("utf-8")
                    probe_data = subprocess_json.loads(probe_out)
                    duration_for_split = float(probe_data.get('format', {}).get('duration', 0))
                except Exception as e:
                    print("Error getting duration for split:", e)
                    
                if duration_for_split > 0:
                    # Calculate segment duration to keep each part under ~1900MB
                    num_parts = math.ceil(file_size / (1900 * 1024 * 1024))
                    segment_time = int(duration_for_split / num_parts)
                    
                    base_name, ext = os.path.splitext(file_name)
                    split_pattern = f"{base_name}_part%03d{ext}"
                    
                    split_cmd = [
                        "ffmpeg", "-i", file_name, 
                        "-c", "copy", "-map", "0", "-f", "segment", 
                        "-segment_time", str(segment_time), 
                        "-reset_timestamps", "1", 
                        split_pattern
                    ]
                    
                    try:
                        subprocess.run(split_cmd, check=True)
                        import glob
                        part_files = sorted(glob.glob(f"{base_name}_part*{ext}"))
                        if part_files:
                            upload_items = part_files
                    except Exception as e:
                        print("Error during video splitting:", e)
            else:
                await safe_edit_text(status_msg, f"✂️ {prefix} File 2GB se badi hai. Parts me split kar raha hu...")
                base_name, ext = os.path.splitext(file_name)
                chunk_size = 1900 * 1024 * 1024
                num_parts = math.ceil(file_size / chunk_size)
                parts = []
                try:
                    with open(file_name, 'rb') as f:
                        for i in range(1, num_parts + 1):
                            part_name = f"{base_name}_part{i:03d}{ext}"
                            with open(part_name, 'wb') as chunk_file:
                                chunk_file.write(f.read(chunk_size))
                            parts.append(part_name)
                    if parts:
                        upload_items = parts
                except Exception as e:
                    print("Error splitting document:", e)

        total_parts = len(upload_items)

        for part_idx, current_file in enumerate(upload_items, 1):
            if not os.path.exists(current_file):
                continue
                
            current_caption = caption_text
            if total_parts > 1:
                current_caption += f"\n\n**Part {part_idx} of {total_parts}**"

            part_label = f" (Part {part_idx}/{total_parts})" if total_parts > 1 else ""

            if is_video:
                width, height, duration = 0, 0, 0
                current_thumb = thumb_path
                try:
                    import subprocess, json as subprocess_json
                    probe_cmd = ["ffprobe", "-v", "quiet", "-print_format", "json", "-show_format", "-show_streams", current_file]
                    probe_out = subprocess.check_output(probe_cmd).decode("utf-8")
                    probe_data = subprocess_json.loads(probe_out)
                    video_stream = next((s for s in probe_data.get('streams', []) if s.get('codec_type') == 'video'), None)
                    if video_stream:
                        width = int(video_stream.get('width', 0))
                        height = int(video_stream.get('height', 0))
                    duration = int(float(probe_data.get('format', {}).get('duration', 0)))
                    
                    if not current_thumb:
                        current_thumb = current_file + ".jpg"
                        subprocess.call(["ffmpeg", "-i", current_file, "-ss", "00:00:01.000", "-vframes", "1", current_thumb, "-y", "-v", "quiet"])
                except Exception:
                    pass

                await client.send_video(
                    chat_id=chat_id,
                    video=current_file,
                    caption=current_caption,
                    duration=duration,
                    width=width,
                    height=height,
                    thumb=current_thumb if (current_thumb and os.path.exists(current_thumb)) else None,
                    progress=progress_for_pyrogram,
                    progress_args=(f"📤 {prefix} **Uploading Video{part_label}...**", status_msg, time.time())
                )
                if current_thumb and current_thumb != thumb_path and os.path.exists(current_thumb):
                    os.remove(current_thumb)
            elif is_image:
                await client.send_photo(
                    chat_id=chat_id,
                    photo=current_file,
                    caption=current_caption,
                    progress=progress_for_pyrogram,
                    progress_args=(f"📤 {prefix} **Uploading Photo{part_label}...**", status_msg, time.time())
                )
            else:
                await client.send_document(
                    chat_id=chat_id,
                    document=current_file,
                    caption=current_caption,
                    thumb=thumb_path if (thumb_path and os.path.exists(thumb_path)) else None,
                    progress=progress_for_pyrogram,
                    progress_args=(f"📤 {prefix} **Uploading{part_label}...**", status_msg, time.time())
                )
            
            # Delete part file after upload if it was a split part
            if current_file != file_name and os.path.exists(current_file):
                os.remove(current_file)

        # Space bachane ke liye original file delete karna
        if os.path.exists(file_name):
            os.remove(file_name)
        if thumb_path and os.path.exists(thumb_path):
            os.remove(thumb_path)
            
        await status_msg.delete()
        
    except Exception as e:
        err_msg = str(e).replace('`', '').replace('*', '')[:300]
        await safe_edit_text(status_msg, f"❌ {prefix} Error aa gaya bhai: `{err_msg}`")
        if os.path.exists(file_name):
            os.remove(file_name)
        if thumb_path and os.path.exists(thumb_path):
            os.remove(thumb_path)

@app.on_message(filters.text & filters.private & ~filters.command(["start", "stop"]))
async def handle_message(client, message: Message):
    text = message.text.strip()
    
    custom_name = None
    banner_url = None
    url = ""
    
    # Parse multi-line format
    lines = [line.strip() for line in text.split('\n') if line.strip()]
    if len(lines) >= 3:
        custom_name = lines[0]
        banner_url = lines[1]
        url = lines[2]
    elif len(lines) == 2:
        custom_name = lines[0]
        url = lines[1]
    else:
        # Fallback to original | split or single line
        if "|" in text:
            url, custom_name = text.split("|", 1)
            url = url.strip()
            custom_name = custom_name.strip()
        else:
            url = text

    # Basic validation to see if URL is in the correct place, swap if user put URL first
    if not (url.startswith("http://") or url.startswith("https://")):
        if len(lines) >= 2 and (lines[0].startswith("http://") or lines[0].startswith("https://")):
            url = lines[0]
            if len(lines) == 2:
                custom_name = lines[1]
            else:
                banner_url = lines[1]
                custom_name = lines[2]
        else:
            await message.reply_text("Kripya ek valid HTTP/HTTPS URL bhejein bhai.\n\n**Format (3 Lines):**\n`Video Name`\n`Banner Image URL (optional)`\n`Download URL`")
            return
            
    stream_key = None
    
    if "shemaroomovies-" in url or "&catalog_id=" in url:
        await message.reply_text("⏳ Shemaroo link decrypt ho raha hai...")
        sm_url, s_key, _ = decrypt_shemaroo_url(url)
        if sm_url:
            url = sm_url
            stream_key = s_key
            if not custom_name:
                custom_name = "Shemaroo_Video.mp4"
        else:
            await message.reply_text("❌ Shemaroo link decrypt nahi ho paya. Invalid ID/Token.")
            return

    await process_single_link(client, message.chat.id, url, custom_name, banner_url, "", None, stream_key)

def parse_json_playlist(file_path):
    items = []
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
            
            # Skymovies format (Hot-Short-Film etc)
            if isinstance(data, dict) and "Data" in data and isinstance(data["Data"], list):
                for item in data["Data"]:
                    name = item.get('name') or item.get('title')
                    poster = item.get('poster') or item.get('banner')
                    downloads = item.get('downloads')
                    
                    if isinstance(downloads, dict):
                        items.append({
                            'type': 'movie_bundle',
                            'name': name,
                            'poster': poster,
                            'downloads': downloads
                        })
            
            # Standard list format
            elif isinstance(data, list):
                for item in data:
                    url = item.get('url') or item.get('stream_url') or item.get('link') or item.get('stream url')
                    name = item.get('name') or item.get('title')
                    banner = item.get('banner') or item.get('image') or item.get('thumb') or item.get('thumbnail') or item.get('logo')
                    if url:
                        items.append((url, name, banner))
    except Exception as e:
        print(f"JSON Parse Error: {e}")
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
        
    reply_markup = InlineKeyboardMarkup(
        [[InlineKeyboardButton("🛑 Stop Process", callback_data="stop_process")]]
    )
    await status_msg.edit_text(f"✅ File process ho gayi. Total **{len(items)}** links mile hain. Ab ek-ek karke download start kar raha hu...", reply_markup=reply_markup)
    
    active_processes[message.chat.id] = True
    
    for idx, item in enumerate(items, start=1):
        if not active_processes.get(message.chat.id, True):
            await client.send_message(message.chat.id, "🛑 Process ko user dwara stop kar diya gaya hai.")
            break
        try:
            if isinstance(item, tuple):
                url, custom_name, banner_url = item
                await process_single_link(client, message.chat.id, url, custom_name, banner_url, f"[{idx}/{len(items)}]")
            elif isinstance(item, dict) and item.get('type') == 'movie_bundle':
                name = item.get('name', 'Unknown')
                poster = item.get('poster')
                downloads = item.get('downloads', {})
                
                # Send poster as photo
                if poster:
                    try:
                        await client.send_photo(message.chat.id, photo=poster, caption=f"**{name}**")
                    except Exception as e:
                        await client.send_message(message.chat.id, f"**{name}**\n(Poster Error: `{e}`)")
                else:
                    await client.send_message(message.chat.id, f"**{name}**")
                    
                # Download each URL
                for q_name, d_url in downloads.items():
                    if not active_processes.get(message.chat.id, True):
                        break
                    custom_file_name = f"{name}.mp4"
                    custom_file_name = "".join(c for c in custom_file_name if c.isalnum() or c in (' ', '.', '-', '_')).strip()
                    await process_single_link(client, message.chat.id, d_url, custom_file_name, None, f"[{idx}/{len(items)}]", q_name)
        except Exception as e:
            await client.send_message(message.chat.id, f"❌ Link {idx} me error aaya: `{str(e)}`")
            
        # Har file ke baad thoda delay takki Telegram block/flood-wait na kare
        await asyncio.sleep(3)
            
    if active_processes.get(message.chat.id, False):
        await client.send_message(message.chat.id, f"🎉 Saare {len(items)} links process ho gaye!")
    
    active_processes.pop(message.chat.id, None)

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
