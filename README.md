# FF Media Bot 🚀

A high-performance Telegram Media Bot designed for handling videos, audios, and documents, with support for up to **4 GB** file uploads (via Telegram Premium MTProto API).

---

## 📋 Features
- **Welcome & Profile Information:** Interactive `/start` menu in English.
- **Media Engine Ready:** Architecture built on **Hydrogram MTProto** (modern Pyrogram fork with full Python 3.12 - 3.14 compatibility).
- **4 GB Support:** Ready for Telegram Premium MTProto sessions.
- **Inline Navigation:** Interactive menu buttons (Help, About, Status).

---

## 🛠️ Setup Instructions

### 1. Requirements
Python 3.9+ (Fully compatible with Python 3.14).

### 2. Install Dependencies
```bash
py -m pip install -r requirements.txt
```

### 3. Get Your Telegram Credentials
1. **API_ID & API_HASH:**
   - Go to [my.telegram.org](https://my.telegram.org)
   - Log in with your Telegram account.
   - Go to **API development tools** and create an application to obtain `api_id` and `api_hash`.
2. **BOT_TOKEN:**
   - Open Telegram and message [@BotFather](https://t.me/BotFather).
   - Send `/newbot`, choose a name and username.
   - Copy the generated `HTTP API Token`.

### 4. Configure Environment Variables
Copy `.env.example` to `.env`:
```bash
copy .env.example .env
```
Open `.env` and fill in your actual credentials:
```env
API_ID=12345678
API_HASH=abcdef1234567890abcdef1234567890
BOT_TOKEN=1234567890:ABCdefGHIjklMNOpqrsTUVwxyz
```

### 5. Run the Bot
```bash
py main.py
```
---

## 💡 Note on 4 GB Uploads:
Standard Telegram Bot API limits uploads to 50 MB (or 2 GB with custom Bot API server). 
Because this bot is built on **Hydrogram (MTProto)**, it can natively communicate with Telegram's client protocol. In subsequent steps, we will attach your Telegram Premium session to unlock the full **4 GB** upload capability.

---

## 📜 Project Rules
All core rules, UX principles, and guidelines established for this bot are documented in [PROJECT_RULES.md](PROJECT_RULES.md).
