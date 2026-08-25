import asyncio
from pyrogram import Client
from config import API_ID, API_HASH, STRING_SESSIONS

original_get_me = Client.get_me
cached_me = {}

async def mocked_get_me(self):
    # Pyrogram clients using session string have their auth_key loaded, so we can key by session_string
    # However, self doesn't store session_string by default. We can key by self.name or just a global cache if there's only one.
    # Let's key by API credentials or just use a boolean flag if there's only one.
    # Actually, all instances in our code use STRING_SESSIONS.
    # We can just key by something available or cache universally.
    # Let's see if self has something unique.
    if hasattr(self, 'api_hash'):
        key = self.api_hash
    else:
        key = "default"
        
    if key in cached_me:
        return cached_me[key]
    me = await original_get_me(self)
    cached_me[key] = me
    return me

Client.get_me = mocked_get_me

async def main():
    session = STRING_SESSIONS[0]
    clients = []
    for i in range(10):
        print(f"Starting {i}")
        c = Client(f"test_{i}", api_id=API_ID, api_hash=API_HASH, session_string=session, no_updates=True, sleep_threshold=60)
        await c.start()
        clients.append(c)
        print(f"Started {i}")
        
asyncio.run(main())
