import asyncio
import os
from dotenv import load_dotenv
from pyrogram import Client

async def generate_session():
    load_dotenv()
    
    api_id = os.getenv("API_ID")
    api_hash = os.getenv("API_HASH")
    
    if not api_id or not api_hash:
        print("API_ID and API_HASH not found in .env. Please configure them first.")
        return
        
    print(f"Using API_ID: {api_id}")
    print("Initializing Pyrogram client...")
    
    app = Client("user_session", api_id=int(api_id), api_hash=api_hash, in_memory=True)
    
    await app.start()
    
    session_string = await app.export_session_string()
    print("\n" + "="*50)
    print("SUCCESS! Here is your STRING_SESSION:")
    print("="*50 + "\n")
    print(session_string)
    print("\n" + "="*50)
    print("Copy this string and add it to your .env file as:")
    print(f"STRING_SESSIONS={session_string}")
    
    await app.stop()

if __name__ == "__main__":
    asyncio.run(generate_session())
