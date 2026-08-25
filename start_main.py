import os
from dotenv import load_dotenv, set_key

def setup_env():
    env_file = ".env"
    if not os.path.exists(env_file):
        open(env_file, 'a').close()

    load_dotenv(env_file)

    prompts = [
        ("API_ID", "Enter your Telegram API_ID: ", None),
        ("API_HASH", "Enter your Telegram API_HASH: ", None),
        ("BOT_TOKENS", "Enter your Telegram Bot Token(s) (comma separated): ", None),
        ("STRING_SESSIONS", "Enter your User String Session (optional, leave blank to skip): ", ""),
        ("STORAGE_CHANNEL", "Enter your Storage Channel ID (e.g. -100...): ", None),
        ("DATABASE_BACKUP_MSG_ID", "Enter your Database Backup Message ID (enter 0 if you don't have one): ", "0"),
        ("ADMIN_PASSWORD", "Enter an Admin Password for the Web UI [default: admin]: ", "admin")
    ]

    updated = False
    for key, prompt_msg, default in prompts:
        val = os.getenv(key)
        if not val:
            if default is not None:
                user_input = input(prompt_msg)
                val = user_input if user_input.strip() else default
            else:
                while not val:
                    val = input(prompt_msg).strip()
            set_key(env_file, key, val)
            os.environ[key] = val
            updated = True
    
    if updated:
        print("Configuration saved to .env file.")

if __name__ == "__main__":
    setup_env()
    try:
        import uvicorn
        import webbrowser
        import threading
        import time
        
        def open_browser():
            time.sleep(1.5)
            webbrowser.open("http://localhost:8000")
            
        threading.Thread(target=open_browser, daemon=True).start()
        uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
    except KeyboardInterrupt:
        print("\nServer stopped successfully.")
