import os
import sys
from dotenv import load_dotenv

load_dotenv()

API_ID = os.getenv("API_ID")
API_HASH = os.getenv("API_HASH")
BOT_TOKEN = os.getenv("BOT_TOKEN")

if not API_ID or not API_HASH or not BOT_TOKEN:
    # Notice for local setup
    pass
else:
    try:
        API_ID = int(API_ID)
    except ValueError:
        print("ERROR: API_ID must be an integer!")
        sys.exit(1)
