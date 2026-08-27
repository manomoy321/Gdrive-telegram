from utils.downloader import (
    download_file,
    get_file_info_from_url,
)
import asyncio
from pathlib import Path
from contextlib import asynccontextmanager
import aiofiles
from fastapi import FastAPI, HTTPException, Request, File, UploadFile, Form, Response
from fastapi.responses import FileResponse, JSONResponse
from config import ADMIN_PASSWORD, MAX_FILE_SIZE, STORAGE_CHANNEL
from utils.clients import initialize_clients
from utils.directoryHandler import getRandomID
from utils.extra import auto_ping_website, convert_class_to_dict, reset_cache_dir
from utils.streamer import media_streamer
from utils.uploader import start_file_uploader
from utils.logger import Logger
import urllib.parse


# Startup Event
@asynccontextmanager
async def lifespan(app: FastAPI):
    # Reset the cache directory, delete cache files
    reset_cache_dir()

    # Initialize the clients
    await initialize_clients()

    # Start the website auto ping task
    asyncio.create_task(auto_ping_website())

    yield


app = FastAPI(docs_url=None, redoc_url=None, lifespan=lifespan)
logger = Logger(__name__)


@app.get("/")
async def home_page():
    return FileResponse("website/home.html")


@app.get("/stream")
async def home_page():
    return FileResponse("website/VideoPlayer.html")


@app.get("/static/{file_path:path}")
async def static_files(file_path):
    if "apiHandler.js" in file_path:
        with open(Path("website/static/js/apiHandler.js"), "r", encoding="utf-8") as f:
            content = f.read()
            content = content.replace("MAX_FILE_SIZE__SDGJDG", str(MAX_FILE_SIZE))
        return Response(content=content, media_type="application/javascript")
    return FileResponse(f"website/static/{file_path}")


@app.get("/file")
async def dl_file(request: Request):
    from utils.directoryHandler import DRIVE_DATA

    path = request.query_params["path"]
    file = DRIVE_DATA.get_file(path)
    return await media_streamer(STORAGE_CHANNEL, file.file_id, file.name, request)


@app.get("/sw.js")
async def sw_js():
    return Response("/* No service worker */", media_type="application/javascript")


# Api Routes


@app.post("/api/checkPassword")
async def check_password(request: Request):
    data = await request.json()
    if data["pass"] == ADMIN_PASSWORD:
        return JSONResponse({"status": "ok"})
    return JSONResponse({"status": "Invalid password"})


@app.post("/api/createNewFolder")
async def api_new_folder(request: Request):
    from utils.directoryHandler import DRIVE_DATA

    data = await request.json()

    if data["password"] != ADMIN_PASSWORD:
        return JSONResponse({"status": "Invalid password"})

    logger.info(f"createNewFolder {data}")
    folder_data = DRIVE_DATA.get_directory(data["path"]).contents
    for id in folder_data:
        f = folder_data[id]
        if f.type == "folder":
            if f.name == data["name"]:
                return JSONResponse(
                    {
                        "status": "Folder with the name already exist in current directory"
                    }
                )

    DRIVE_DATA.new_folder(data["path"], data["name"])
    return JSONResponse({"status": "ok"})


@app.post("/api/getDirectory")
async def api_get_directory(request: Request):
    from utils.directoryHandler import DRIVE_DATA

    data = await request.json()

    if data["password"] == ADMIN_PASSWORD:
        is_admin = True
    else:
        is_admin = False

    auth = data.get("auth")

    logger.info(f"getFolder {data}")

    if data["path"] == "/trash":
        data = {"contents": DRIVE_DATA.get_trashed_files_folders()}
        folder_data = convert_class_to_dict(data, isObject=False, showtrash=True)

    elif data["path"] == "/saved_messages":
        return JSONResponse({"status": "ok", "data": {"contents": {}}, "auth_home_path": None})

    elif data["path"] == "/downloads":
        return JSONResponse({"status": "ok", "data": {"contents": {}}, "auth_home_path": None})

    elif "/search_" in data["path"]:
        query = urllib.parse.unquote(data["path"].split("_", 1)[1])
        print(query)
        data = {"contents": DRIVE_DATA.search_file_folder(query)}
        print(data)
        folder_data = convert_class_to_dict(data, isObject=False, showtrash=False)
        print(folder_data)

    elif "/share_" in data["path"]:
        path = data["path"].split("_", 1)[1]
        folder_data, auth_home_path = DRIVE_DATA.get_directory(path, is_admin, auth)
        auth_home_path= auth_home_path.replace("//", "/") if auth_home_path else None
        folder_data = convert_class_to_dict(folder_data, isObject=True, showtrash=False)
        return JSONResponse(
            {"status": "ok", "data": folder_data, "auth_home_path": auth_home_path}
        )

    else:
        folder_data = DRIVE_DATA.get_directory(data["path"])
        folder_data = convert_class_to_dict(folder_data, isObject=True, showtrash=False)
    return JSONResponse({"status": "ok", "data": folder_data, "auth_home_path": None})


SAVE_PROGRESS = {}


@app.post("/api/upload")
async def upload_file(
    file: UploadFile = File(...),
    path: str = Form(...),
    password: str = Form(...),
    id: str = Form(...),
    total_size: str = Form(...),
):
    global SAVE_PROGRESS

    if password != ADMIN_PASSWORD:
        return JSONResponse({"status": "Invalid password"})

    total_size = int(total_size)
    SAVE_PROGRESS[id] = ("running", 0, total_size)

    ext = file.filename.lower().split(".")[-1]

    cache_dir = Path("./cache")
    cache_dir.mkdir(parents=True, exist_ok=True)
    file_location = cache_dir / f"{id}.{ext}"

    file_size = 0

    async with aiofiles.open(file_location, "wb") as buffer:
        while chunk := await file.read(1024 * 1024):  # Read file in chunks of 1MB
            SAVE_PROGRESS[id] = ("running", file_size, total_size)
            file_size += len(chunk)
            if file_size > MAX_FILE_SIZE:
                await buffer.close()
                file_location.unlink()  # Delete the partially written file
                raise HTTPException(
                    status_code=400,
                    detail=f"File size exceeds {MAX_FILE_SIZE} bytes limit",
                )
            await buffer.write(chunk)

    SAVE_PROGRESS[id] = ("completed", file_size, file_size)

    asyncio.create_task(
        start_file_uploader(file_location, id, path, file.filename, file_size)
    )

    return JSONResponse({"id": id, "status": "ok"})


@app.post("/api/getSaveProgress")
async def get_save_progress(request: Request):
    global SAVE_PROGRESS

    data = await request.json()

    if data["password"] != ADMIN_PASSWORD:
        return JSONResponse({"status": "Invalid password"})

    logger.info(f"getUploadProgress {data}")
    try:
        progress = SAVE_PROGRESS[data["id"]]
        return JSONResponse({"status": "ok", "data": progress})
    except:
        return JSONResponse({"status": "not found"})


@app.post("/api/getUploadProgress")
async def get_upload_progress(request: Request):
    from utils.uploader import PROGRESS_CACHE

    data = await request.json()

    if data["password"] != ADMIN_PASSWORD:
        return JSONResponse({"status": "Invalid password"})

    logger.info(f"getUploadProgress {data}")

    try:
        progress = PROGRESS_CACHE[data["id"]]
        return JSONResponse({"status": "ok", "data": progress})
    except:
        return JSONResponse({"status": "not found"})


@app.post("/api/cancelUpload")
async def cancel_upload(request: Request):
    from utils.uploader import STOP_TRANSMISSION
    from utils.downloader import STOP_DOWNLOAD

    data = await request.json()

    if data["password"] != ADMIN_PASSWORD:
        return JSONResponse({"status": "Invalid password"})

    logger.info(f"cancelUpload {data}")
    STOP_TRANSMISSION.append(data["id"])
    STOP_DOWNLOAD.append(data["id"])
    return JSONResponse({"status": "ok"})


@app.post("/api/renameFileFolder")
async def rename_file_folder(request: Request):
    from utils.directoryHandler import DRIVE_DATA

    data = await request.json()

    if data["password"] != ADMIN_PASSWORD:
        return JSONResponse({"status": "Invalid password"})

    logger.info(f"renameFileFolder {data}")
    DRIVE_DATA.rename_file_folder(data["path"], data["name"])
    return JSONResponse({"status": "ok"})


@app.post("/api/trashFileFolder")
async def trash_file_folder(request: Request):
    from utils.directoryHandler import DRIVE_DATA

    data = await request.json()

    if data["password"] != ADMIN_PASSWORD:
        return JSONResponse({"status": "Invalid password"})

    logger.info(f"trashFileFolder {data}")
    DRIVE_DATA.trash_file_folder(data["path"], data["trash"])
    return JSONResponse({"status": "ok"})


@app.post("/api/deleteFileFolder")
async def delete_file_folder(request: Request):
    from utils.directoryHandler import DRIVE_DATA

    data = await request.json()

    if data["password"] != ADMIN_PASSWORD:
        return JSONResponse({"status": "Invalid password"})

    logger.info(f"deleteFileFolder {data}")
    DRIVE_DATA.delete_file_folder(data["path"])
    return JSONResponse({"status": "ok"})


@app.post("/api/getFileInfoFromUrl")
async def getFileInfoFromUrl(request: Request):

    data = await request.json()

    if data["password"] != ADMIN_PASSWORD:
        return JSONResponse({"status": "Invalid password"})

    logger.info(f"getFileInfoFromUrl {data}")
    try:
        file_info = await get_file_info_from_url(data["url"])
        return JSONResponse({"status": "ok", "data": file_info})
    except Exception as e:
        return JSONResponse({"status": str(e)})


@app.post("/api/startFileDownloadFromUrl")
async def startFileDownloadFromUrl(request: Request):
    data = await request.json()

    if data["password"] != ADMIN_PASSWORD:
        return JSONResponse({"status": "Invalid password"})

    logger.info(f"startFileDownloadFromUrl {data}")
    try:
        id = getRandomID()
        asyncio.create_task(
            download_file(data["url"], id, data["path"], data["filename"], data["singleThreaded"])
        )
        return JSONResponse({"status": "ok", "id": id})
    except Exception as e:
        return JSONResponse({"status": str(e)})


@app.post("/api/getFileDownloadProgress")
async def getFileDownloadProgress(request: Request):
    from utils.downloader import DOWNLOAD_PROGRESS

    data = await request.json()

    if data["password"] != ADMIN_PASSWORD:
        return JSONResponse({"status": "Invalid password"})

    logger.info(f"getFileDownloadProgress {data}")

    try:
        progress = DOWNLOAD_PROGRESS[data["id"]]
        return JSONResponse({"status": "ok", "data": progress})
    except:
        return JSONResponse({"status": "not found"})


@app.post("/api/getFolderShareAuth")
async def getFolderShareAuth(request: Request):
    from utils.directoryHandler import DRIVE_DATA

    data = await request.json()

    if data["password"] != ADMIN_PASSWORD:
        return JSONResponse({"status": "Invalid password"})

    logger.info(f"getFolderShareAuth {data}")

    try:
        auth = DRIVE_DATA.get_folder_auth(data["path"])
        return JSONResponse({"status": "ok", "auth": auth})
    except:
        return JSONResponse({"status": "not found"})


@app.post("/api/getGlobalMetrics")
async def get_global_metrics(request: Request):
    data = await request.json()
    if data.get("password") != ADMIN_PASSWORD:
        return JSONResponse({"status": "Invalid password"})
    
    return JSONResponse({
        "status": "ok",
        "speed": 0,
        "downloaded": 0,
        "total": 0
    })


thumbnail_semaphore = None
THUMB_CACHE_DIR = Path("./cache/thumbnails")
THUMB_CACHE_DIR.mkdir(parents=True, exist_ok=True)

@app.get("/api/getThumbnail")
async def api_get_thumbnail(msg_id: int):
    global thumbnail_semaphore
    import asyncio
    if thumbnail_semaphore is None:
        thumbnail_semaphore = asyncio.Semaphore(3)

    cached_thumb = THUMB_CACHE_DIR / f"{msg_id}.jpg"
    if cached_thumb.is_file() and cached_thumb.stat().st_size > 0:
        return FileResponse(cached_thumb, media_type="image/jpeg")

    from utils.clients import premium_clients, get_client
    if len(premium_clients) == 0:
        return Response(status_code=404)
        
    client = get_client(premium_required=True)
    
    async with thumbnail_semaphore:
        try:
            if cached_thumb.is_file() and cached_thumb.stat().st_size > 0:
                return FileResponse(cached_thumb, media_type="image/jpeg")

            msg = await client.get_messages("me", msg_id)
            if not msg:
                return Response(status_code=404)
                
            thumb_obj = None
            if msg.photo:
                thumb_obj = msg.photo.file_id
            elif msg.video and getattr(msg.video, "thumbs", None):
                thumb_obj = msg.video.thumbs[0].file_id
            elif msg.document and getattr(msg.document, "thumbs", None):
                thumb_obj = msg.document.thumbs[0].file_id
            elif msg.audio and getattr(msg.audio, "thumbs", None):
                thumb_obj = msg.audio.thumbs[0].file_id
                
            if not thumb_obj:
                return Response(status_code=404)
                
            thumb = await asyncio.wait_for(client.download_media(thumb_obj, in_memory=True), timeout=15.0)
            if not thumb:
                return Response(status_code=404)
                
            thumb.seek(0)
            data_bytes = thumb.read()
            try:
                with open(cached_thumb, "wb") as f:
                    f.write(data_bytes)
            except Exception:
                pass
                
            return Response(content=data_bytes, media_type="image/jpeg")
        except Exception as e:
            from utils.logger import Logger
            logger = Logger(__name__)
            logger.warning(f"Thumbnail error {msg_id}: {type(e).__name__} - {e}")
            return Response(status_code=404)


@app.post("/api/getSavedMessages")
async def api_get_saved_messages(request: Request):
    data = await request.json()
    if data.get("password") != ADMIN_PASSWORD:
        return JSONResponse({"status": "Invalid password"})
    
    from utils.clients import premium_clients, get_client
    if len(premium_clients) == 0:
        return JSONResponse({"status": "no_user_session"})
    
    client = get_client(premium_required=True)
    limit = int(data.get("limit", 0))  # 0 means all messages
    offset_id = int(data.get("offset_id", 0))
    
    messages = []
    has_more = False
    last_id = offset_id
    count = 0
    
    try:
        kwargs = {}
        if offset_id > 0:
            kwargs["max_id"] = offset_id - 1
            
        async for msg in client.get_chat_history("me", **kwargs):
            last_id = msg.id
            if msg.document or msg.video or msg.audio or msg.photo or msg.voice or msg.animation or msg.video_note:
                media = msg.document or msg.video or msg.audio or msg.photo or msg.voice or msg.animation or msg.video_note
                file_name = getattr(media, "file_name", None)
                media_type = "file"
                has_thumb = False

                if msg.photo:
                    media_type = "photo"
                    has_thumb = True
                    if not file_name:
                        file_name = f"photo_{msg.id}.jpg"
                elif msg.video:
                    media_type = "video"
                    has_thumb = bool(getattr(msg.video, "thumbs", None))
                    if not file_name:
                        file_name = f"video_{msg.id}.mp4"
                elif msg.audio:
                    media_type = "audio"
                    has_thumb = bool(getattr(msg.audio, "thumbs", None))
                    if not file_name:
                        file_name = f"audio_{msg.id}.mp3"
                elif msg.voice:
                    media_type = "voice"
                    has_thumb = False
                    if not file_name:
                        file_name = f"voice_{msg.id}.ogg"
                elif msg.animation:
                    media_type = "animation"
                    has_thumb = bool(getattr(msg.animation, "thumbs", None))
                    if not file_name:
                        file_name = f"animation_{msg.id}.mp4"
                elif msg.video_note:
                    media_type = "video_note"
                    has_thumb = bool(getattr(msg.video_note, "thumbs", None))
                    if not file_name:
                        file_name = f"video_note_{msg.id}.mp4"
                else:
                    has_thumb = bool(getattr(msg.document, "thumbs", None))
                    if not file_name:
                        file_name = f"file_{msg.id}"
                
                messages.append({
                    "id": msg.id,
                    "name": file_name,
                    "media_type": media_type,
                    "has_thumb": has_thumb,
                    "date": msg.date.strftime("%Y-%m-%d %H:%M:%S") if msg.date else "",
                    "size": getattr(media, "file_size", 0) or 0
                })
                count += 1
                if limit > 0 and count >= limit:
                    has_more = True
                    break
                
        return JSONResponse({
            "status": "ok",
            "messages": messages,
            "has_more": has_more,
            "last_id": last_id,
            "total_count": len(messages)
        })
    except Exception as e:
        import traceback
        traceback.print_exc()
        return JSONResponse({"status": "error", "message": str(e)})


@app.post("/api/getTasks")
async def api_get_tasks(request: Request):
    from utils.downloader import DOWNLOAD_PROGRESS
    from utils.uploader import PROGRESS_CACHE
    global SAVE_PROGRESS

    data = await request.json()
    if data.get("password") != ADMIN_PASSWORD:
        return JSONResponse({"status": "Invalid password"})

    tasks = {}
    total_speed = 0
    total_downloaded = 0
    active_count = 0
    
    # Background downloads & URL downloads
    for k, v in DOWNLOAD_PROGRESS.items():
        if isinstance(v, dict):
            task_dict = v.copy()
            task_dict["id"] = k
            if "stage" not in task_dict:
                task_dict["stage"] = task_dict.get("type", "downloading")
            
            speed = task_dict.get("speed", 0) or 0
            current = task_dict.get("current", 0) or 0
            total = task_dict.get("total", 0) or 0
            
            if task_dict.get("status") in ["downloading", "running"]:
                total_speed += speed
                active_count += 1
            total_downloaded += current
            
            # Accurate ETA calculation
            if speed > 0 and total > current:
                task_dict["eta"] = int((total - current) / speed)
            else:
                task_dict["eta"] = 0
                
            tasks[k] = task_dict

    # Upload tasks
    for k, v in PROGRESS_CACHE.items():
        if isinstance(v, dict):
            task_dict = v.copy()
            task_dict["id"] = k
            if "stage" not in task_dict:
                task_dict["stage"] = task_dict.get("type", "uploading")
            speed = task_dict.get("speed", 0) or 0
            if task_dict.get("status") in ["running", "uploading"]:
                active_count += 1
            tasks[k] = task_dict

    for k, v in SAVE_PROGRESS.items():
        if isinstance(v, tuple):
            tasks[k] = {
                "id": k,
                "status": v[0],
                "current": v[1],
                "total": v[2],
                "speed": 0,
                "filename": k,
                "stage": "uploading"
            }

    return JSONResponse({
        "status": "ok",
        "tasks": tasks,
        "metrics": {
            "total_speed": total_speed,
            "total_downloaded": total_downloaded,
            "active_count": active_count,
            "total_count": len(tasks)
        }
    })


@app.post("/api/cancelTask")
async def api_cancel_task(request: Request):
    from utils.downloader import STOP_DOWNLOAD, DOWNLOAD_PROGRESS
    from utils.uploader import STOP_TRANSMISSION, PROGRESS_CACHE

    data = await request.json()
    if data.get("password") != ADMIN_PASSWORD:
        return JSONResponse({"status": "Invalid password"})

    task_id = data.get("id")
    if task_id:
        STOP_DOWNLOAD.append(task_id)
        STOP_TRANSMISSION.append(task_id)
        if task_id in DOWNLOAD_PROGRESS and isinstance(DOWNLOAD_PROGRESS[task_id], dict):
            DOWNLOAD_PROGRESS[task_id]["status"] = "cancelled"
            DOWNLOAD_PROGRESS[task_id]["speed"] = 0
        if task_id in PROGRESS_CACHE and isinstance(PROGRESS_CACHE[task_id], dict):
            PROGRESS_CACHE[task_id]["status"] = "cancelled"
            PROGRESS_CACHE[task_id]["speed"] = 0

    return JSONResponse({"status": "ok"})


@app.post("/api/clearCompletedTasks")
async def api_clear_completed_tasks(request: Request):
    from utils.downloader import DOWNLOAD_PROGRESS
    from utils.uploader import PROGRESS_CACHE
    global SAVE_PROGRESS

    data = await request.json()
    if data.get("password") != ADMIN_PASSWORD:
        return JSONResponse({"status": "Invalid password"})

    to_delete_dl = [k for k, v in DOWNLOAD_PROGRESS.items() if isinstance(v, dict) and v.get("status") in ["completed", "cancelled", "error"]]
    for k in to_delete_dl:
        del DOWNLOAD_PROGRESS[k]

    to_delete_ul = [k for k, v in PROGRESS_CACHE.items() if isinstance(v, dict) and v.get("status") in ["completed", "cancelled", "error"]]
    for k in to_delete_ul:
        del PROGRESS_CACHE[k]

    to_delete_sv = [k for k, v in SAVE_PROGRESS.items() if isinstance(v, tuple) and v[0] in ["completed", "cancelled", "error"]]
    for k in to_delete_sv:
        del SAVE_PROGRESS[k]

    return JSONResponse({"status": "ok"})


@app.post("/api/getSettings")
async def api_get_settings(request: Request):
    data = await request.json()
    if data.get("password") != ADMIN_PASSWORD:
        return JSONResponse({"status": "Invalid password"})
    from utils.settings import get_settings
    return JSONResponse({"status": "ok", "settings": get_settings()})


@app.post("/api/startBackgroundDownload")
async def api_start_background_download(request: Request):
    from utils.clients import premium_clients, get_client
    from utils.tg_downloader import download_file_background
    import asyncio

    data = await request.json()
    if data.get("password") != ADMIN_PASSWORD:
        return JSONResponse({"status": "Invalid password"})

    if len(premium_clients) == 0:
        return JSONResponse({"status": "error", "message": "No user session available"})
        
    msg_ids = data.get("msg_ids", [])
    names = data.get("names", [])
    sizes = data.get("sizes", [])
    
    try:
        for i, msg_id in enumerate(msg_ids):
            name = names[i] if i < len(names) else f"file_{msg_id}"
            size = sizes[i] if i < len(sizes) else 0
            
            client = get_client(premium_required=True)
            asyncio.create_task(
                download_file_background(client, msg_id, name, size)
            )
            
        return JSONResponse({"status": "ok"})
    except Exception as e:
        logger.error(f"Error starting background download: {e}")
        return JSONResponse({"status": "error", "message": str(e)})


@app.post("/api/deleteSavedMessages")
async def api_delete_saved_messages(request: Request):
    data = await request.json()
    if data.get("password") != ADMIN_PASSWORD:
        return JSONResponse({"status": "Invalid password"})
        
    from utils.clients import premium_clients, get_client
    if len(premium_clients) == 0:
        return JSONResponse({"status": "error", "message": "No user session"})
        
    client = get_client(premium_required=True)
    msg_ids = data.get("msg_ids", [])
    
    try:
        await client.delete_messages("me", msg_ids)
        return JSONResponse({"status": "ok"})
    except Exception as e:
        import traceback
        traceback.print_exc()
        return JSONResponse({"status": "error", "message": str(e)})


@app.post("/api/saveToSavedMessages")
async def api_save_to_saved_messages(request: Request):
    data = await request.json()
    if data.get("password") != ADMIN_PASSWORD:
        return JSONResponse({"status": "Invalid password"})
        
    from utils.directoryHandler import DRIVE_DATA
    from utils.clients import premium_clients, get_client
    
    path = data.get("path")
    try:
        file = DRIVE_DATA.get_file(path)
        if not file:
            return JSONResponse({"status": "error", "message": "File not found"})
            
        if len(premium_clients) == 0:
            return JSONResponse({"status": "error", "message": "User session (STRING_SESSIONS) required to save to Saved Messages"})
            
        client = get_client(premium_required=True)
        await client.copy_message(
            chat_id="me",
            from_chat_id=STORAGE_CHANNEL,
            message_id=file.file_id
        )
        return JSONResponse({"status": "ok", "message": "Saved to Telegram Saved Messages"})
    except Exception as e:
        logger.error(f"Error copying file to Saved Messages: {e}")
        return JSONResponse({"status": "error", "message": str(e)})


@app.post("/api/saveSavedMessage")
async def api_save_saved_message(request: Request):
    data = await request.json()
    if data.get("password") != ADMIN_PASSWORD:
        return JSONResponse({"status": "Invalid password"})
        
    from utils.clients import premium_clients, get_client
    from utils.directoryHandler import DRIVE_DATA
    
    if len(premium_clients) == 0:
        return JSONResponse({"status": "error", "message": "No user session available"})
        
    client = get_client(premium_required=True)
    msg_ids = data.get("msg_ids")
    if not msg_ids:
        msg_id = data.get("msg_id")
        msg_ids = [msg_id] if msg_id is not None else []
        
    target_path = data.get("path", "/")
    
    try:
        saved_count = 0
        for msg_id in msg_ids:
            msg = await client.get_messages("me", msg_id)
            if not msg:
                continue
                
            copied_msg = await client.copy_message(
                chat_id=STORAGE_CHANNEL,
                from_chat_id="me",
                message_id=msg_id
            )
            
            media = copied_msg.document or copied_msg.video or copied_msg.audio or copied_msg.photo or copied_msg.voice
            file_name = getattr(media, "file_name", None)
            if not file_name:
                if copied_msg.photo:
                    file_name = f"photo_{msg_id}.jpg"
                elif copied_msg.video:
                    file_name = f"video_{msg_id}.mp4"
                elif copied_msg.audio:
                    file_name = f"audio_{msg_id}.mp3"
                elif copied_msg.voice:
                    file_name = f"voice_{msg_id}.ogg"
                else:
                    file_name = f"file_{msg_id}"
                    
            file_size = getattr(media, "file_size", 0) or 0
            DRIVE_DATA.new_file(target_path, file_name, copied_msg.id, file_size)
            saved_count += 1
            
        return JSONResponse({"status": "ok", "saved_count": saved_count})
    except Exception as e:
        logger.error(f"Error saving message to Drive: {e}")
        return JSONResponse({"status": "error", "message": str(e)})


@app.post("/api/pauseTask")
async def api_pause_task(request: Request):
    from utils.downloader import PAUSED_TASKS as DL_PAUSED_TASKS
    from utils.uploader import PAUSED_TASKS as UL_PAUSED_TASKS
    
    data = await request.json()
    if data.get("password") != ADMIN_PASSWORD:
        return JSONResponse({"status": "Invalid password"})
        
    task_id = data.get("id")
    if task_id:
        DL_PAUSED_TASKS.add(task_id)
        UL_PAUSED_TASKS.add(task_id)
    return JSONResponse({"status": "ok"})


@app.post("/api/resumeTask")
async def api_resume_task(request: Request):
    from utils.downloader import PAUSED_TASKS as DL_PAUSED_TASKS
    from utils.uploader import PAUSED_TASKS as UL_PAUSED_TASKS
    
    data = await request.json()
    if data.get("password") != ADMIN_PASSWORD:
        return JSONResponse({"status": "Invalid password"})
        
    task_id = data.get("id")
    if task_id:
        if task_id in DL_PAUSED_TASKS:
            DL_PAUSED_TASKS.remove(task_id)
        if task_id in UL_PAUSED_TASKS:
            UL_PAUSED_TASKS.remove(task_id)
    return JSONResponse({"status": "ok"})


@app.post("/api/updateSettings")
async def api_update_settings(request: Request):
    data = await request.json()
    if data.get("password") != ADMIN_PASSWORD:
        return JSONResponse({"status": "Invalid password"})
        
    from utils.settings import save_settings, get_settings
    from utils.tg_downloader import update_semaphore
    
    settings = data.get("settings", {})
    if save_settings(settings):
        if "parallel_downloads" in settings:
            update_semaphore(int(settings["parallel_downloads"]))
        return JSONResponse({"status": "ok", "settings": get_settings()})
    return JSONResponse({"status": "error", "message": "Failed to save settings"})


if __name__ == '__main__':
    import uvicorn
    import webbrowser
    import threading
    import time
    
    def open_browser():
        time.sleep(1.5)
        webbrowser.open('http://localhost:8000')
        
    threading.Thread(target=open_browser, daemon=True).start()
    uvicorn.run('main:app', host='0.0.0.0', port=8000, reload=True)
