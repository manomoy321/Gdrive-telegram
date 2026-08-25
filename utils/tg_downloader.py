import os
import time
import asyncio
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
        limit = settings.get("parallel_downloads", 3)
        _download_semaphore = asyncio.Semaphore(limit)
    return _download_semaphore

def update_semaphore(new_limit):
    global _download_semaphore
    if _download_semaphore is not None:
        _download_semaphore = asyncio.Semaphore(new_limit)

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
    logger.info(f"Starting background task for {file_name}. Semaphore value: {semaphore._value}")
    
    task_id = f"bg_{msg_id}_{int(time.time())}"
    
    DOWNLOAD_PROGRESS[task_id] = {
        "status": "queued",
        "current": 0,
        "total": file_size or 0,
        "speed": 0,
        "filename": file_name,
        "type": "download",
        "stage": "queued",
        "start_time": time.time(),
        "last_update_time": time.time(),
        "last_bytes": 0
    }

    async with semaphore:
        if task_id in STOP_DOWNLOAD:
            DOWNLOAD_PROGRESS[task_id]["status"] = "cancelled"
            return

        settings = get_settings()
        dl_location = settings.get("download_location", "downloads")
        Path(dl_location).mkdir(parents=True, exist_ok=True)
        
        file_path = os.path.join(dl_location, file_name)
        
        # Ensure unique filename
        base, ext = os.path.splitext(file_name)
        counter = 1
        while os.path.exists(file_path):
            file_path = os.path.join(dl_location, f"{base}_{counter}{ext}")
            counter += 1
            
        DOWNLOAD_PROGRESS[task_id]["status"] = "downloading"
        DOWNLOAD_PROGRESS[task_id]["stage"] = "downloading"
        DOWNLOAD_PROGRESS[task_id]["file_path"] = file_path
        
        speed_limit_mbps = settings.get("speed_limit", 0)
        speed_limit_bps = speed_limit_mbps * 1024 * 1024
        
        downloaded = 0
        last_update_time = time.time()
        last_downloaded = 0
        
        try:
            logger.info(f"Starting background download of {file_name} to {file_path}")
            
            message = await client.get_messages("me", msg_id)
            media = message.document or message.video or message.audio or message.photo
            
            if not media:
                raise Exception("Message does not contain valid media")
                
            total_size = getattr(media, "file_size", file_size)
            DOWNLOAD_PROGRESS[task_id]["total"] = total_size
            
            with open(file_path, "wb") as f:
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
                        DOWNLOAD_PROGRESS[task_id]["speed"] = 0
                        f.close()
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
                        
            DOWNLOAD_PROGRESS[task_id]["status"] = "completed"
            DOWNLOAD_PROGRESS[task_id]["stage"] = "completed"
            DOWNLOAD_PROGRESS[task_id]["current"] = total_size
            DOWNLOAD_PROGRESS[task_id]["speed"] = 0
            logger.info(f"Completed background download of {file_name}")
            
        except Exception as e:
            logger.error(f"Error downloading {file_name}: {e}")
            DOWNLOAD_PROGRESS[task_id]["status"] = "error"
            DOWNLOAD_PROGRESS[task_id]["speed"] = 0
            DOWNLOAD_PROGRESS[task_id]["error_msg"] = str(e)
