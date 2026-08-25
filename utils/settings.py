import json
import os
from pathlib import Path

SETTINGS_FILE = "settings.json"

DEFAULT_SETTINGS = {
    "download_location": os.path.join(os.getcwd(), "downloads"),
    "parallel_downloads": 3,
    "speed_limit": 0  # 0 means unlimited (in MB/s)
}

def get_settings():
    if not os.path.exists(SETTINGS_FILE):
        save_settings(DEFAULT_SETTINGS)
        return DEFAULT_SETTINGS
    try:
        with open(SETTINGS_FILE, "r") as f:
            data = json.load(f)
            # Merge with defaults to ensure all keys exist
            for k, v in DEFAULT_SETTINGS.items():
                if k not in data:
                    data[k] = v
            return data
    except Exception:
        return DEFAULT_SETTINGS

def save_settings(settings):
    try:
        # Ensure download location exists if it's being set
        dl_path = settings.get("download_location")
        if dl_path:
            Path(dl_path).mkdir(parents=True, exist_ok=True)
            
        with open(SETTINGS_FILE, "w") as f:
            json.dump(settings, f, indent=4)
        return True
    except Exception as e:
        print(f"Error saving settings: {e}")
        return False
