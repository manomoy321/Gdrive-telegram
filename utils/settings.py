import json
import os
from pathlib import Path

SETTINGS_FILE = "settings.json"

DEFAULT_SETTINGS = {
    "download_location": os.path.abspath("gteli"),
    "parallel_downloads": 3,
    "speed_limit": 0  # 0 means unlimited (in MB/s)
}

def get_settings():
    if not os.path.exists(SETTINGS_FILE):
        save_settings(DEFAULT_SETTINGS)
        return DEFAULT_SETTINGS.copy()
    try:
        with open(SETTINGS_FILE, "r") as f:
            data = json.load(f)
            # Merge with defaults to ensure all keys exist
            for k, v in DEFAULT_SETTINGS.items():
                if k not in data:
                    data[k] = v
            # Ensure download_location is resolved to absolute path and valid
            dl_path = data.get("download_location")
            if not dl_path:
                dl_path = os.path.abspath("gteli")
                data["download_location"] = dl_path
            elif not os.path.isabs(dl_path):
                dl_path = os.path.abspath(dl_path)
                data["download_location"] = dl_path
            return data
    except Exception:
        return DEFAULT_SETTINGS.copy()

def save_settings(settings):
    try:
        # Ensure download location exists if it's being set
        dl_path = settings.get("download_location")
        if dl_path:
            if not os.path.isabs(dl_path):
                dl_path = os.path.abspath(dl_path)
                settings["download_location"] = dl_path
            try:
                Path(dl_path).mkdir(parents=True, exist_ok=True)
            except Exception as e:
                print(f"Error creating directory {dl_path}: {e}")
                # Fallback to local gteli
                dl_path = os.path.abspath("gteli")
                Path(dl_path).mkdir(parents=True, exist_ok=True)
                settings["download_location"] = dl_path
        else:
            dl_path = os.path.abspath("gteli")
            Path(dl_path).mkdir(parents=True, exist_ok=True)
            settings["download_location"] = dl_path
            
        with open(SETTINGS_FILE, "w") as f:
            json.dump(settings, f, indent=4)
        return True
    except Exception as e:
        print(f"Error saving settings: {e}")
        return False

