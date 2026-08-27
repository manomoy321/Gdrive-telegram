import os
import time
import asyncio
import re
from pathlib import Path
from utils.logger import Logger
from utils.settings import get_settings

logger = Logger(__name__)

# Reusing DOWNLOAD_PROGRESS from downloader for the UI
from utils.downloader import DOWNLOAD_PROGRESS, PAUSED_TASKS, STOP_DOWNLOAD

# Global semaphore to limit parallel downloads
_download_semaphore = None

def get_semaphore():
    global _download_semaphore
    if _download_semaphore is None:
        settings = get_settings()
        limit = max(1, int(settings.get("parallel_downloads", 3)))
        _download_semaphore = asyncio.Semaphore(limit)
    return _download_semaphore

def update_semaphore(new_limit):
    global _download_semaphore
    _download_semaphore = asyncio.Semaphore(max(1, int(new_limit)))

def sanitize_filename(filename: str) -> str:
    if not filename:
        return f"file_{int(time.time())}"
    # Replace invalid Windows and filesystem chars
    clean = re.sub(r'[<>:"/\\|?*\x00-\x1f]', '_', filename)
    clean = clean.strip('. ')
    if not clean:
        clean = f"file_{int(time.time())}"
    return clean

async def _throttle(chunk_size, start_time, speed_limit_bps):
    if speed_limit_bps <= 0:
        await asyncio.sleep(0)  # Yield to event loop to prevent starvation
        return
    
    elapsed = time.time() - start_time
    expected_time = chunk_size / speed_limit_bps
    
    if elapsed < expected_time:
        await asyncio.sleep(expected_time - elapsed)
    else:
        await asyncio.sleep(0)  # Yield even if no throttling needed

async def download_file_background(client, msg_id, file_name, file_size):
    semaphore = get_semaphore()
    task_id = f"bg_{msg_id}_{time.time_ns()}"
    clean_name = sanitize_filename(file_name)
    
    DOWNLOAD_PROGRESS[task_id] = {
        "id": task_id,
        "status": "queued",
        "current": 0,
        "total": file_size or 0,
        "speed": 0,
        "filename": clean_name,
        "type": "download",
        "stage": "queued",
        "start_time": time.time(),
        "last_update_time": time.time(),
        "last_bytes": 0
    }
    
    logger.info(f"Queued background download task {task_id} for '{clean_name}' (msg_id: {msg_id})")

    async with semaphore:
        if task_id in STOP_DOWNLOAD:
            DOWNLOAD_PROGRESS[task_id]["status"] = "cancelled"
            DOWNLOAD_PROGRESS[task_id]["stage"] = "cancelled"
            return

        file_path = None
        f = None
        try:
            settings = get_settings()
            dl_location = settings.get("download_location")
            if not dl_location:
                dl_location = os.path.abspath("gteli")
                
            try:
                Path(dl_location).mkdir(parents=True, exist_ok=True)
            except Exception as pe:
                logger.warning(f"Could not use download directory '{dl_location}': {pe}. Falling back to ./gteli")
                dl_location = os.path.abspath("gteli")
                Path(dl_location).mkdir(parents=True, exist_ok=True)

            file_path = os.path.join(dl_location, clean_name)
            
            # Ensure unique filename
            base, ext = os.path.splitext(clean_name)
            counter = 1
            while os.path.exists(file_path):
                file_path = os.path.join(dl_location, f"{base}_{counter}{ext}")
                counter += 1
                
            DOWNLOAD_PROGRESS[task_id]["status"] = "downloading"
            DOWNLOAD_PROGRESS[task_id]["stage"] = "downloading"
            DOWNLOAD_PROGRESS[task_id]["file_path"] = file_path
            
            speed_limit_mbps = settings.get("speed_limit", 0)
            speed_limit_bps = speed_limit_mbps * 1024 * 1024
            
            logger.info(f"Starting background download of '{clean_name}' to '{file_path}'")
            
            if client is None:
                from utils.clients import get_client
                client = get_client(premium_required=True)
                
            message = await client.get_messages("me", msg_id)
            if not message:
                raise Exception(f"Message {msg_id} not found in Telegram Saved Messages")
                
            media = message.document or message.video or message.audio or message.photo or message.voice or message.animation or message.video_note
            if not media:
                raise Exception("Message does not contain valid media")
                
            total_size = getattr(media, "file_size", file_size) or file_size or 0
            DOWNLOAD_PROGRESS[task_id]["total"] = total_size
            
            downloaded = 0
            last_update_time = time.time()
            last_downloaded = 0
            
            f = open(file_path, "wb")
            async for chunk in client.stream_media(message):
                # Check pause
                while task_id in PAUSED_TASKS:
                    DOWNLOAD_PROGRESS[task_id]["status"] = "paused"
                    DOWNLOAD_PROGRESS[task_id]["speed"] = 0
                    await asyncio.sleep(1)
                    if task_id not in PAUSED_TASKS:
                        DOWNLOAD_PROGRESS[task_id]["status"] = "downloading"
                        last_update_time = time.time()
                        last_downloaded = downloaded

                # Check cancellation
                if task_id in STOP_DOWNLOAD:
                    DOWNLOAD_PROGRESS[task_id]["status"] = "cancelled"
                    DOWNLOAD_PROGRESS[task_id]["stage"] = "cancelled"
                    DOWNLOAD_PROGRESS[task_id]["speed"] = 0
                    f.close()
                    f = None
                    try:
                        if os.path.exists(file_path):
                            os.remove(file_path)
                    except:
                        pass
                    return

                chunk_start_time = time.time()
                f.write(chunk)
                
                chunk_len = len(chunk)
                downloaded += chunk_len
                DOWNLOAD_PROGRESS[task_id]["current"] = downloaded
                
                await _throttle(chunk_len, chunk_start_time, speed_limit_bps)
                
                now = time.time()
                time_diff = now - last_update_time
                if time_diff >= 0.8:
                    speed = (downloaded - last_downloaded) / time_diff
                    DOWNLOAD_PROGRESS[task_id]["speed"] = speed
                    last_update_time = now
                    last_downloaded = downloaded
            
            if f:
                f.close()
                f = None
                
            DOWNLOAD_PROGRESS[task_id]["status"] = "completed"
            DOWNLOAD_PROGRESS[task_id]["stage"] = "completed"
            DOWNLOAD_PROGRESS[task_id]["current"] = total_size if total_size > 0 else downloaded
            DOWNLOAD_PROGRESS[task_id]["speed"] = 0
            logger.info(f"Completed background download of '{clean_name}' ({downloaded} bytes)")
            
        except Exception as e:
            logger.error(f"Error downloading '{clean_name}' (msg_id: {msg_id}): {e}")
            if f:
                try:
                    f.close()
                except:
                    pass
                f = None
            if file_path and os.path.exists(file_path) and os.path.getsize(file_path) == 0:
                try:
                    os.remove(file_path)
                except:
                    pass
            DOWNLOAD_PROGRESS[task_id]["status"] = "error"
            DOWNLOAD_PROGRESS[task_id]["stage"] = "error"
            DOWNLOAD_PROGRESS[task_id]["speed"] = 0
            DOWNLOAD_PROGRESS[task_id]["error_msg"] = str(e)
