import asyncio
from pyrogram import Client
from config import API_ID, API_HASH, STRING_SESSIONS

async def main():
    session = STRING_SESSIONS[0]
    clients = []
    for i in range(10):
        print(f"Starting {i}")
        c = Client(f"test_{i}", api_id=API_ID, api_hash=API_HASH, session_string=session, no_updates=True)
        await c.start()
        clients.append(c)
        print(f"Started {i}")
        
asyncio.run(main())
