import asyncio, config
from pathlib import Path
from pyrogram import Client
from utils.directoryHandler import backup_drive_data, loadDriveData
from utils.logger import Logger
import os
import signal

logger = Logger(__name__)

multi_clients = {}
premium_clients = {}
work_loads = {}
premium_work_loads = {}
main_bot = None


async def initialize_clients():
    global multi_clients, work_loads, premium_clients, premium_work_loads
    logger.info("Initializing Clients")

    session_cache_path = Path(f"./cache")
    session_cache_path.parent.mkdir(parents=True, exist_ok=True)

    from utils.settings import get_settings
    settings = get_settings()
    num_parallel = settings.get("parallel_downloads", 3)

    all_tokens = dict((i, t) for i, t in enumerate(config.BOT_TOKENS, start=1))
    
    unique_sessions = list(dict.fromkeys([s for s in config.STRING_SESSIONS if s]))
    all_sessions = dict(
        (i, s) for i, s in enumerate(unique_sessions, start=len(all_tokens) + 1)
    )

    # Monkey patch Pyrogram's get_me to avoid FloodWaits on duplicate sessions
    original_get_me = Client.get_me
    cached_me = {}

    async def mocked_get_me(self):
        key = getattr(self, "my_unique_token", self.name)
        if key not in cached_me:
            cached_me[key] = asyncio.create_task(original_get_me(self))
        return await cached_me[key]

    Client.get_me = mocked_get_me

    async def start_client(client_id, token, type):
        try:
            logger.info(f"Starting - {type.title()} Client {client_id}")

            if type == "bot":
                client = Client(
                    name=str(client_id),
                    api_id=config.API_ID,
                    api_hash=config.API_HASH,
                    bot_token=token,
                    workdir=session_cache_path,
                )
                client.my_unique_token = token
                client.loop = asyncio.get_running_loop()
                await client.start()
                await client.send_message(
                    config.STORAGE_CHANNEL,
                    f"Started - {type.title()} Client {client_id}",
                )
                multi_clients[client_id] = client
                work_loads[client_id] = 0
            elif type == "user":
                client_inst = Client(
                    name=str(client_id),
                    api_id=config.API_ID,
                    api_hash=config.API_HASH,
                    session_string=token,
                    sleep_threshold=config.SLEEP_THRESHOLD,
                    workdir=session_cache_path,
                    in_memory=True,
                    no_updates=True,
                )
                client_inst.my_unique_token = token
                client = await client_inst.start()
                await client.send_message(
                    config.STORAGE_CHANNEL,
                    f"Started - {type.title()} Client {client_id}",
                )
                premium_clients[client_id] = client
                premium_work_loads[client_id] = 0

            logger.info(f"Started - {type.title()} Client {client_id}")
        except Exception as e:
            logger.error(
                f"Failed To Start {type.title()} Client - {client_id} Error: {e}"
            )

    await asyncio.gather(
        *(
            [
                start_client(client_id, client, "bot")
                for client_id, client in all_tokens.items()
            ]
            + [
                start_client(client_id, client, "user")
                for client_id, client in all_sessions.items()
            ]
        )
    )
    if len(multi_clients) == 0 and len(premium_clients) == 0:
        logger.error("No Clients Were Initialized")
        os._exit(1)
        
    if len(multi_clients) == 0:
        logger.warning("No Bot Clients Initialized! Falling back to User Clients for all operations.")
        logger.info("No Premium Clients Were Initialized")

    logger.info("Clients Initialized")

    # Load the drive data
    await loadDriveData()

    # Start the backup drive data task
    asyncio.create_task(backup_drive_data())


def get_client(premium_required=False) -> Client:
    global multi_clients, work_loads, premium_clients, premium_work_loads

    if (premium_required or len(multi_clients) == 0) and len(premium_clients) > 0:
        index = min(premium_work_loads, key=premium_work_loads.get)
        premium_work_loads[index] += 1
        return premium_clients[index]

    index = min(work_loads, key=work_loads.get)
    work_loads[index] += 1
    return multi_clients[index]
