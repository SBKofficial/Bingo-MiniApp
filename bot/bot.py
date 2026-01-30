import os
import time
import requests
from dotenv import load_dotenv

load_dotenv()
BOT_TOKEN = os.getenv("BOT_TOKEN")
load_dotenv(".env.runtime")
API_URL = os.getenv("API_URL")

# IMPORTANT: GitHub Pages URL will be configured later
# For now, it will look for the index.html relative to where you host it
# You must update this after enabling GitHub Pages
GITHUB_URL = "https://YOUR_GITHUB_USERNAME.github.io/bingo_project"
BASE_URL = f"https://api.telegram.org/bot{BOT_TOKEN}"

def get_updates(offset=None):
    url = f"{BASE_URL}/getUpdates?timeout=10"
    if offset: url += f"&offset={offset}"
    try:
        return requests.get(url).json()
    except:
        return {}

def main():
    print("🤖 Bot Started!")
    offset = 0
    while True:
        updates = get_updates(offset)
        if "result" in updates:
            for u in updates["result"]:
                offset = u["update_id"] + 1
                if "message" in u:
                    chat_id = u["message"]["chat"]["id"]
                    text = u["message"].get("text", "")
                    if text == "/start":
                        # Send the Play Button
                        final_url = f"{GITHUB_URL}/index.html?api={API_URL}"
                        data = {
                            "chat_id": chat_id,
                            "text": "🚀 Bingo Server Online! Click to play:",
                            "reply_markup": {
                                "inline_keyboard": [[{"text": "🎮 Play Bingo", "web_app": {"url": final_url}}]]
                            }
                        }
                        requests.post(f"{BASE_URL}/sendMessage", json=data)
        time.sleep(1)

if __name__ == "__main__":
    main()
                      
