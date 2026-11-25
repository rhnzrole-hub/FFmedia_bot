"""
FF Media Bot - Helper script to generate a Telegram Premium User Session String.
Run this script: python generate_string_session.py
"""

import asyncio
import os
from dotenv import load_dotenv
from hydrogram import Client

load_dotenv()

API_ID = os.getenv("API_ID")
API_HASH = os.getenv("API_HASH")

if not API_ID or not API_HASH:
    print("Please make sure API_ID and API_HASH are set in your .env file!")
    API_ID = input("Enter API_ID: ").strip()
    API_HASH = input("Enter API_HASH: ").strip()

async def main():
    print("\n--- Telegram Premium Session String Generator ---")
    print("Logging into your Telegram account to generate 4GB Session String...\n")
    async with Client(name="session_gen", api_id=int(API_ID), api_hash=API_HASH, in_memory=True) as app:
        session_str = await app.export_session_string()
        me = await app.get_me()
        is_prem = getattr(me, "is_premium", False)
        print("\n" + "=" * 60)
        print(f"Logged in as: {me.first_name} (@{me.username or me.id})")
        print(f"Telegram Premium: {'YES (4 GB Uploads Enabled!)' if is_prem else 'NO'}")
        print("=" * 60)
        print("\nCopy the session string below and add it to your .env file:\n")
        print(f"USER_SESSION_STRING={session_str}\n")
        print("=" * 60)

if __name__ == "__main__":
    asyncio.run(main())
