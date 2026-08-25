import os
import aiohttp, asyncio
import time
from utils.extra import get_filename
from utils.logger import Logger
from pathlib import Path
from utils.uploader import start_file_uploader
from techzdl import TechZDL

logger = Logger(__name__)

DOWNLOAD_PROGRESS = {}
STOP_DOWNLOAD = []
PAUSED_TASKS = set()

cache_dir = Path("./cache")
cache_dir.mkdir(parents=True, exist_ok=True)


async def download_progress_callback(status, current, total, id):
    global DOWNLOAD_PROGRESS, PAUSED_TASKS

    while id in PAUSED_TASKS:
        if id in DOWNLOAD_PROGRESS and isinstance(DOWNLOAD_PROGRESS[id], dict):
            DOWNLOAD_PROGRESS[id]["status"] = "paused"
            DOWNLOAD_PROGRESS[id]["speed"] = 0
        await asyncio.sleep(1)

    now = time.time()
    
    if id not in DOWNLOAD_PROGRESS or not isinstance(DOWNLOAD_PROGRESS[id], dict):
        DOWNLOAD_PROGRESS[id] = {
            "status": status,
            "current": current,
            "total": total,
            "speed": 0,
            "last_update_time": now,
            "last_bytes_transferred": current,
            "filename": "Unknown",
            "type": "download"
        }
    else:
        last_time = DOWNLOAD_PROGRESS[id].get("last_update_time", now)
        last_bytes = DOWNLOAD_PROGRESS[id].get("last_bytes_transferred", current)
        
        time_diff = now - last_time
        if time_diff >= 1.0:
            speed = (current - last_bytes) / time_diff
            DOWNLOAD_PROGRESS[id]["speed"] = speed
            DOWNLOAD_PROGRESS[id]["last_update_time"] = now
            DOWNLOAD_PROGRESS[id]["last_bytes_transferred"] = current
            
        DOWNLOAD_PROGRESS[id]["status"] = status
        DOWNLOAD_PROGRESS[id]["current"] = current
        DOWNLOAD_PROGRESS[id]["total"] = total


async def download_file(url, id, path, filename, singleThreaded):
    global DOWNLOAD_PROGRESS, STOP_DOWNLOAD

    logger.info(f"Downloading file from {url}")

    try:
        downloader = TechZDL(
            url,
            output_dir=cache_dir,
            debug=False,
            progress_callback=download_progress_callback,
            progress_args=(id,),
            max_retries=5,
            single_threaded=singleThreaded,
        )
        await downloader.start(in_background=True)

        await asyncio.sleep(5)

        while downloader.is_running:
            if id in STOP_DOWNLOAD:
                logger.info(f"Stopping download {id}")
                await downloader.stop()
                return
            await asyncio.sleep(1)

        if downloader.download_success is False:
            raise downloader.download_error

        if id in DOWNLOAD_PROGRESS and isinstance(DOWNLOAD_PROGRESS[id], dict):
            DOWNLOAD_PROGRESS[id]["status"] = "completed"
            DOWNLOAD_PROGRESS[id]["current"] = downloader.total_size
            DOWNLOAD_PROGRESS[id]["total"] = downloader.total_size
            DOWNLOAD_PROGRESS[id]["speed"] = 0
        else:
            DOWNLOAD_PROGRESS[id] = {
                "status": "completed",
                "current": downloader.total_size,
                "total": downloader.total_size,
                "speed": 0,
                "filename": filename,
                "type": "download"
            }

        logger.info(f"File downloaded to {downloader.output_path}")

        asyncio.create_task(
            start_file_uploader(
                downloader.output_path, id, path, filename, downloader.total_size
            )
        )
    except Exception as e:
        if id in DOWNLOAD_PROGRESS and isinstance(DOWNLOAD_PROGRESS[id], dict):
            DOWNLOAD_PROGRESS[id]["status"] = "error"
            DOWNLOAD_PROGRESS[id]["speed"] = 0
        logger.error(f"Failed to download file: {url} {e}")


async def get_file_info_from_url(url):
    downloader = TechZDL(
        url,
        output_dir=cache_dir,
        debug=False,
        progress_callback=download_progress_callback,
        progress_args=(id,),
        max_retries=5,
    )
    file_info = await downloader.get_file_info()
    return {"file_size": file_info["total_size"], "file_name": file_info["filename"]}
