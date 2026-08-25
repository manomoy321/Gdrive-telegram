from utils.clients import get_client
from pyrogram import Client
from pyrogram.types import Message
from config import STORAGE_CHANNEL
import os
import time
import asyncio
from utils.logger import Logger
from urllib.parse import unquote_plus

logger = Logger(__name__)
PROGRESS_CACHE = {}
STOP_TRANSMISSION = []
PAUSED_TASKS = set()


async def progress_callback(current, total, id, client: Client, file_path):
    global PROGRESS_CACHE, STOP_TRANSMISSION, PAUSED_TASKS

    while id in PAUSED_TASKS:
        if id in PROGRESS_CACHE and isinstance(PROGRESS_CACHE[id], dict):
            PROGRESS_CACHE[id]["status"] = "paused"
            PROGRESS_CACHE[id]["speed"] = 0
        await asyncio.sleep(1)

    now = time.time()
    
    if id not in PROGRESS_CACHE or not isinstance(PROGRESS_CACHE[id], dict):
        PROGRESS_CACHE[id] = {
            "status": "running",
            "current": current,
            "total": total,
            "speed": 0,
            "last_update_time": now,
            "last_bytes_transferred": current,
            "filename": os.path.basename(file_path),
            "type": "upload"
        }
    else:
        last_time = PROGRESS_CACHE[id].get("last_update_time", now)
        last_bytes = PROGRESS_CACHE[id].get("last_bytes_transferred", current)
        
        time_diff = now - last_time
        if time_diff >= 1.0:
            speed = (current - last_bytes) / time_diff
            PROGRESS_CACHE[id]["speed"] = speed
            PROGRESS_CACHE[id]["last_update_time"] = now
            PROGRESS_CACHE[id]["last_bytes_transferred"] = current
            
        PROGRESS_CACHE[id]["status"] = "running"
        PROGRESS_CACHE[id]["current"] = current
        PROGRESS_CACHE[id]["total"] = total

    if id in STOP_TRANSMISSION:
        logger.info(f"Stopping transmission {id}")
        client.stop_transmission()
        try:
            os.remove(file_path)
        except:
            pass


async def start_file_uploader(
    file_path, id, directory_path, filename, file_size, delete=True
):
    global PROGRESS_CACHE
    from utils.directoryHandler import DRIVE_DATA

    logger.info(f"Uploading file {file_path} {id}")

    if file_size > 1.98 * 1024 * 1024 * 1024:
        # Use premium client for files larger than 2 GB
        client: Client = get_client(premium_required=True)
    else:
        client: Client = get_client()

    PROGRESS_CACHE[id] = {
        "status": "running",
        "current": 0,
        "total": file_size,
        "speed": 0,
        "last_update_time": time.time(),
        "last_bytes_transferred": 0,
        "filename": filename,
        "type": "upload"
    }

    message: Message = await client.send_document(
        STORAGE_CHANNEL,
        file_path,
        progress=progress_callback,
        progress_args=(id, client, file_path),
        disable_notification=True,
    )
    size = (
        message.photo
        or message.document
        or message.video
        or message.audio
        or message.sticker
    ).file_size

    filename = unquote_plus(filename)

    DRIVE_DATA.new_file(directory_path, filename, message.id, size)
    if id in PROGRESS_CACHE and isinstance(PROGRESS_CACHE[id], dict):
        PROGRESS_CACHE[id]["status"] = "completed"
        PROGRESS_CACHE[id]["current"] = size
        PROGRESS_CACHE[id]["total"] = size
        PROGRESS_CACHE[id]["speed"] = 0
    else:
        PROGRESS_CACHE[id] = {
            "status": "completed",
            "current": size,
            "total": size,
            "speed": 0,
            "filename": filename,
            "type": "upload"
        }

    logger.info(f"Uploaded file {file_path} {id}")

    if delete:
        try:
            os.remove(file_path)
        except Exception as e:
            pass
