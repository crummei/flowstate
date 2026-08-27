import json
import os
from src.paths import DATA_DIR

CONFIG_FILE = os.path.join(DATA_DIR, "config.json")
PERSONALITIES_FILE = os.path.join(DATA_DIR, "personalities.json")

defaults = {
    "is_localhost": False,
    "TTS_enabled": False,
    "delay_per_word": 0.1,
    "human_delay_min": 1.5,
    "human_delay_max": 4.0,
    "human_wpm": 150,
    "temperature": 0.6,
    "API_MODEL": "meta-llama/llama-3.3-70b-instruct",
    "LOCAL_MODEL": "",
    "whitelist": [485481984211288093, 1022513154623811655],
}

def load_config():
    if os.path.exists(CONFIG_FILE):
        with open(CONFIG_FILE, "r", encoding="utf-8") as f:
            saved_settings = json.load(f)
            
    else:
        saved_settings = {}

    merged = defaults.copy()
    for k, v in saved_settings.items():
        if v is not None and (not isinstance(v, str) or v.strip() != ""):
            merged[k] = v

    if merged != saved_settings:
        save_config(merged)

    return merged

def save_config(config_data):
    os.makedirs(os.path.dirname(CONFIG_FILE), exist_ok=True)
    with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
        json.dump(config_data, f, indent=4)

def load_personalities():
    if os.path.exists(PERSONALITIES_FILE):
        with open(PERSONALITIES_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}

def save_personalities(personalities_data):
    os.makedirs(os.path.dirname(PERSONALITIES_FILE), exist_ok=True)
    with open(PERSONALITIES_FILE, 'w', encoding='utf-8') as f:
        json.dump(personalities_data, f, indent=4)

