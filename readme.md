# Telegram URL Uploader Bot

Yeh ek simple Telegram bot hai jo kisi bhi direct link se file download karke aapko Telegram me hi send kar deta hai. Isme Pyrogram aur aiohttp ka use kiya gaya hai jis-se fast downloading aur uploading hoti hai (up to 2GB files support).

## Setup Kaise Karein?

1. **Python Install Karein:** Aapke system me Python 3.8+ hona chahiye.
2. **Requirements Install Karein:**
   ```bash
   pip install -r requirements.txt
   ```
3. **API Keys aur Token Setup:**
   * `.env` file ko open karein.
   * Apna `API_ID` aur `API_HASH` daalein (Jo aapko [my.telegram.org](https://my.telegram.org) se milega).
   * Apna `BOT_TOKEN` daalein (Jo aapko Telegram par [@BotFather](https://t.me/BotFather) se milega).

4. **Bot Run Karein:**
   ```bash
   python bot.py
   ```

5. Telegram par jayein aur apne bot ko `/start` bhejein. Fir usko koi bhi file ki direct URL bhejein.
