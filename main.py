import asyncio
import logging
import os
import re
import shlex
import shutil
import signal
import sys
import time
from typing import Optional

# Ensure an active asyncio event loop exists (required for Python 3.12, 3.13, 3.14+)
try:
    loop = asyncio.get_event_loop()
except RuntimeError:
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

# Force-terminate handler for Windows console Ctrl+C (SIGINT / SIGBREAK)
def handle_exit(signum, frame):
    print("\n[Ctrl+C detected! Stopping FF Media Bot immediately...]")
    os._exit(0)

signal.signal(signal.SIGINT, handle_exit)
signal.signal(signal.SIGTERM, handle_exit)
if hasattr(signal, "SIGBREAK"):
    signal.signal(signal.SIGBREAK, handle_exit)

# Logging configuration
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - [%(levelname)s] - %(name)s - %(message)s",
)
logger = logging.getLogger("FFMediaBot")

from hydrogram import Client, filters, StopTransmission
from hydrogram.types import (
    Message,
    CallbackQuery,
)

import config

# Apply high-speed cryptography (TgCrypto C-accelerated engine / PyCryptodome fallback)
import speedups
speedups.apply_speedups()

import hydrogram.session.session as hsession
# Extend MTProto session wait timeout to 60s for reliable large file downloads without timing out
hsession.Session.WAIT_TIMEOUT = 60
hsession.Session.MAX_RETRIES = 10

from helpers import (
    detect_media,
    humanbytes,
    format_duration,
    remove_audio_metadata_title,
    ProgressTracker,
    CANCELLED_TASKS,
    ACTIVE_PROGRESS,
    parse_time_range,
    trim_audio_file,
    trim_audio_file_with_progress,
    refresh_progress_display,
    build_custom_ffmpeg_command,
    execute_ffmpeg_command,
    execute_ffmpeg_with_progress,
    get_media_duration,
    detect_expected_duration,
    download_media_with_retry,
    get_user_thumbnail,
    save_user_thumbnail,
    delete_user_thumbnail,
    get_user_settings,
    toggle_user_upload_mode,
    get_settings_text,
    build_audio_merger_text,
    merge_audio_files_with_progress,
    get_audio_ffprobe_info,
    format_ffprobe_audio_info,
    extract_video_streams,
    format_video_metadata_text,
    apply_video_stream_metadata,
    apply_all_video_metadata,
    get_all_streams_flat,
    format_stream_remover_text,
    remove_streams_from_video,
    get_stream_extension,
    format_stream_extractor_text,
    extract_single_stream,
    build_video_merge_audio_text,
    merge_audio_into_video,
    build_video_merge_subtitle_text,
    merge_subtitles_into_video,
    trim_video_file,
    trim_video_file_with_progress,
    build_video_merger_text,
    fast_merge_video_files,
    format_ffprobe_video_info,
    get_video_dimensions,
    MAX_BOT_UPLOAD_SIZE,
    build_file_too_large_text,
)
from keyboards import (
    get_start_keyboard,
    get_back_keyboard,
    get_audio_keyboard,
    get_audio_trimmer_keyboard,
    get_back_to_audio_keyboard,
    get_back_to_trimmer_keyboard,
    get_audio_merger_keyboard,
    get_video_keyboard,
    get_back_to_video_keyboard,
    get_video_metadata_keyboard,
    get_back_to_metadata_keyboard,
    get_stream_remover_keyboard,
    get_stream_extractor_keyboard,
    get_video_merge_audio_keyboard,
    get_video_merge_subtitle_keyboard,
    get_video_merger_keyboard,
    get_video_trimmer_keyboard,
    get_back_to_video_trimmer_keyboard,
    get_file_keyboard,
    get_back_to_file_keyboard,
    get_cancel_process_keyboard,
    get_settings_keyboard,
)

# Validate configuration
if not config.API_ID or not config.API_HASH or not config.BOT_TOKEN:
    logger.error("API_ID, API_HASH, or BOT_TOKEN is missing! Please configure your .env file.")
    sys.exit(1)

# Initialize Hydrogram Client with robust connection settings
app = Client(
    name="ff_media_bot",
    api_id=config.API_ID,
    api_hash=config.API_HASH,
    bot_token=config.BOT_TOKEN,
    workers=16,
    max_concurrent_transmissions=8,
    sleep_threshold=60,
)

# In-memory dictionary for active user input states
# Structure: {user_id: {"action": str, "menu_msg_id": int, "media_msg_id": int, "chat_id": int}}
USER_STATES = {}

# Text templates (English)
START_TEXT = """
👋 **Hello, {first_name}!**

Welcome to **FF Media Bot** — your all-in-one assistant for media files!

⚡ **What I can do:**
• 🎬 **Process Videos:** Compress, rename, convert, and stream media files.
• 🎵 **Handle Audios:** Rename, merge, trim, custom FFmpeg commands, strip metadata.
• 📁 **Document & File Handling:** Manage archives, documents, and heavy data.
• 🖼️ **Custom Thumbnails:** Send any photo to set it as your media thumbnail!
• 🚀 **Large File Support:** Capable of handling up to **2 GB** files via high-speed Telegram MTProto!

Send me any **Audio**, **Video**, or **Document** to get started!
"""

ABOUT_TEXT = """
🤖 **About FF Media Bot**

• **Bot Name:** FF Media Bot
• **Version:** 1.5.0
• **Engine:** Hydrogram MTProto Framework (Python 3.14 Compatible)
• **Acceleration:** PyCryptodome AES-NI (~470x faster transfers)
• **Upload Limit:** Up to 4 GB (Telegram Premium enabled)
• **Interface:** Single-Message Dynamic Navigation
• **Language:** English
• **Status:** Active & Ready
"""

HELP_TEXT = """
ℹ️ **Help & Commands**

• `/start` - Start the bot and view welcome screen
• `/help` - Show this help guide
• `/about` - Information about the bot and its limits
• `/showthumb` - View your current custom thumbnail
• `/delthumb` - Delete your saved custom thumbnail
• `/settings` - Configure media upload format (Audio/Video or File)

💡 **How to use:**
1. Send an **Audio** file (`.mp3`, `.m4a`, `.wav`, etc.) to open the **Audio Tools Menu**.
2. Send a **Video** file (`.mp4`, `.mkv`, etc.) to open the **Video Tools Menu**.
3. Send any **Document** to open the **File Tools Menu**.
4. Send any **Photo** to set it as your custom thumbnail for all media!
All menus operate directly inside a single message.
"""


async def get_fresh_media_message(client: Client, chat_id: int, message_id: int) -> Optional[Message]:
    """Fetches fresh Message object with up-to-date file_reference from Telegram servers."""
    try:
        msg = await client.get_messages(chat_id=chat_id, message_ids=message_id)
        return msg
    except Exception as e:
        logger.error(f"Error fetching fresh message {message_id}: {e}")
        return None


def build_audio_menu_text(message: Message) -> str:
    """Builds the main audio menu text using original message info if available."""
    target = message.reply_to_message if message.reply_to_message else message
    media_type, info = detect_media(target)

    if media_type == "audio" and info:
        title = info.get("title", "Unknown Title")
        performer = info.get("performer", "Unknown Artist")
        file_name = info.get("file_name", "audio.mp3")
        file_size_str = humanbytes(info.get("file_size", 0))
        duration_str = format_duration(info.get("duration", 0))
        mime_type = info.get("mime_type", "audio/mpeg")

        return (
            f"🎵 **Audio Management Menu**\n\n"
            f"• **Title:** `{title}`\n"
            f"• **Performer:** `{performer}`\n"
            f"• **File Name:** `{file_name}`\n"
            f"• **Size:** `{file_size_str}`\n"
            f"• **Duration:** `{duration_str}`\n"
            f"• **Format:** `{mime_type}`\n\n"
            f"👇 **Choose an operation for this audio below:**"
        )
    return (
        "🎵 **Audio Management Menu**\n\n"
        "Choose an operation for your audio file below:"
    )


def build_video_menu_text(message: Message) -> str:
    """Builds the main video menu text."""
    target = message.reply_to_message if message.reply_to_message else message
    media_type, info = detect_media(target)

    if media_type == "video" and info:
        file_name = info.get("file_name", "video.mp4")
        file_size = info.get("file_size", 0)
        file_size_str = humanbytes(file_size)
        duration_str = format_duration(info.get("duration", 0))
        width = info.get("width")
        height = info.get("height")
        resolution = f"{width}x{height}" if width and height else "Unknown"
        mime_type = info.get("mime_type", "video/mp4")

        limit_warn = ""
        if file_size > MAX_BOT_UPLOAD_SIZE:
            limit_warn = (
                "\n\n⚠️ **Ogohlantirish:** Ushbu fayl hajmi **2 GB dan katta**! "
                "Telegram botlari faqat 2 GB (2000 MiB) gacha bo'lgan fayllarni qayta yuklay oladi. "
                "2 GB dan katta natijaviy fayllarni Telegram bot orqali yuborib bo'lmaydi."
            )

        return (
            f"🎬 **Video Management Menu**\n\n"
            f"• **File Name:** `{file_name}`\n"
            f"• **Size:** `{file_size_str}`\n"
            f"• **Duration:** `{duration_str}`\n"
            f"• **Resolution:** `{resolution}`\n"
            f"• **Format:** `{mime_type}`"
            f"{limit_warn}\n\n"
            f"👇 **Choose an operation for this video below:**"
        )
    return (
        "🎬 **Video Management Menu**\n\n"
        "Choose an operation for your video file below:"
    )


def build_file_menu_text(message: Message) -> str:
    """Builds the main file menu text."""
    target = message.reply_to_message if message.reply_to_message else message
    media_type, info = detect_media(target)

    if media_type == "file" and info:
        file_name = info.get("file_name", "document")
        file_size = info.get("file_size", 0)
        file_size_str = humanbytes(file_size)
        mime_type = info.get("mime_type", "Unknown")

        limit_warn = ""
        if file_size > MAX_BOT_UPLOAD_SIZE:
            limit_warn = (
                "\n\n⚠️ **Ogohlantirish:** Ushbu fayl hajmi **2 GB dan katta**! "
                "Telegram botlari faqat 2 GB gacha bo'lgan fayllarni qayta yuklay oladi."
            )

        return (
            f"📁 **File Management Menu**\n\n"
            f"• **File Name:** `{file_name}`\n"
            f"• **Size:** `{file_size_str}`\n"
            f"• **Type:** `{mime_type}`"
            f"{limit_warn}\n\n"
            f"👇 **Choose an operation for this file below:**"
        )
    return (
        "📁 **File Management Menu**\n\n"
        "Choose an operation for your file below:"
    )


@app.on_message(filters.command("start") & filters.private)
async def start_handler(client: Client, message: Message):
    """Handles the /start command."""
    user = message.from_user
    first_name = user.first_name if user else "Friend"
    await message.reply_text(
        text=START_TEXT.format(first_name=first_name),
        reply_markup=get_start_keyboard(),
        disable_web_page_preview=True,
    )


@app.on_message(filters.command("help") & filters.private)
async def help_command_handler(client: Client, message: Message):
    """Handles the /help command."""
    await message.reply_text(
        text=HELP_TEXT,
        reply_markup=get_back_keyboard(),
        disable_web_page_preview=True,
    )


@app.on_message(filters.command("about") & filters.private)
async def about_command_handler(client: Client, message: Message):
    """Handles the /about command."""
    await message.reply_text(
        text=ABOUT_TEXT,
        reply_markup=get_back_keyboard(),
        disable_web_page_preview=True,
    )


@app.on_message(filters.command("showthumb") & filters.private)
async def show_thumbnail_handler(client: Client, message: Message):
    """Displays the user's current custom thumbnail."""
    user = message.from_user
    user_id = user.id if user else 0
    thumb_path = get_user_thumbnail(user_id)
    if thumb_path:
        await message.reply_photo(
            photo=thumb_path,
            caption=(
                "🖼️ **Your Current Custom Thumbnail**\n\n"
                "This thumbnail will be automatically attached to all your outgoing media files.\n\n"
                "• Send another photo to replace it\n"
                "• Send /delthumb to delete it"
            ),
        )
    else:
        await message.reply_text(
            "ℹ️ **No Custom Thumbnail Found!**\n\n"
            "You have not set a custom thumbnail yet.\n"
            "Simply send me any photo to set it as your thumbnail!"
        )


@app.on_message(filters.command("delthumb") & filters.private)
async def delete_thumbnail_handler(client: Client, message: Message):
    """Deletes the user's saved custom thumbnail."""
    user = message.from_user
    user_id = user.id if user else 0
    deleted = delete_user_thumbnail(user_id)
    if deleted:
        await message.reply_text(
            "🗑️ **Custom Thumbnail Deleted!**\n\n"
            "Your saved thumbnail has been removed. Outgoing media files will no longer use a custom thumbnail."
        )
    else:
        await message.reply_text(
            "ℹ️ **No Custom Thumbnail Found!**\n\n"
            "You do not have a custom thumbnail set."
        )


@app.on_message(filters.command("settings") & filters.private)
async def settings_command_handler(client: Client, message: Message):
    """Handles the /settings command to configure upload formats."""
    user = message.from_user
    user_id = user.id if user else 0
    settings = get_user_settings(user_id)
    await message.reply_text(
        text=get_settings_text(settings),
        reply_markup=get_settings_keyboard(settings["upload_audio"], settings["upload_video"]),
        quote=True,
    )



@app.on_message(filters.photo & filters.private)
async def photo_thumbnail_handler(client: Client, message: Message):
    """Saves any photo sent by the user as their custom thumbnail for future media files."""
    user = message.from_user
    user_id = user.id if user else 0

    temp_dir = os.path.join("downloads", f"{user_id}_thumb_{int(time.time())}")
    os.makedirs(temp_dir, exist_ok=True)
    temp_input = os.path.join(temp_dir, "input_photo.jpg")

    status_msg = await message.reply_text("📥 **Saving your custom thumbnail...**", quote=True)
    try:
        downloaded = await client.download_media(message=message, file_name=temp_input)
        if downloaded and os.path.exists(downloaded):
            saved_thumb = save_user_thumbnail(user_id, downloaded)
            if saved_thumb:
                await status_msg.edit_text(
                    "🖼️ **Custom Thumbnail Saved Successfully!**\n\n"
                    "This image will now be used as the thumbnail for all your processed media files (Audio, Video, Documents).\n\n"
                    "• View thumbnail: /showthumb\n"
                    "• Delete thumbnail: /delthumb"
                )
            else:
                await status_msg.edit_text("❌ **Failed to process thumbnail!** Please try another image.")
        else:
            await status_msg.edit_text("❌ **Failed to download image!** Please try again.")
    except Exception as e:
        logger.error(f"Error saving thumbnail for user {user_id}: {e}", exc_info=True)
        await status_msg.edit_text(f"❌ **Error saving thumbnail:** `{e}`")
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)


@app.on_message(
    filters.private
    & (
        filters.audio
        | filters.voice
        | filters.video
        | filters.animation
        | filters.video_note
        | filters.document
    )
)
async def media_handler(client: Client, message: Message):
    """
    Detects whether incoming media is Audio, Video, or File,
    and opens the corresponding interactive single-message menu.
    If the user has an active Audio Merger session, incoming audio is queued directly
    and updates the existing menu message without opening new menus!
    """
    user = message.from_user
    user_id = user.id if user else 0

    # Intercept media if user is assembling an Audio Merger queue
    if user_id in USER_STATES and USER_STATES[user_id].get("action") == "audio_merger":
        media_type, info = detect_media(message)
        state = USER_STATES[user_id]
        if media_type != "audio":
            warn = await message.reply_text(
                "⚠️ **Only audio files can be added to the merge queue!**",
                quote=True,
            )
            await asyncio.sleep(4)
            try:
                await warn.delete()
            except Exception:
                pass
            return

        tracks = state.setdefault("tracks", [])
        tracks.append({
            "msg_id": message.id,
            "file_name": info.get("file_name", f"Track {len(tracks) + 1}.mp3"),
            "duration": info.get("duration", 0),
            "file_size": info.get("file_size", 0),
        })

        menu_msg = await get_fresh_media_message(client, state["chat_id"], state["menu_msg_id"])
        if menu_msg:
            try:
                await menu_msg.edit_text(
                    text=build_audio_merger_text(tracks),
                    reply_markup=get_audio_merger_keyboard(len(tracks)),
                )
            except Exception as e:
                logger.error(f"Error updating audio merger menu: {e}")
        return

    # Intercept media if user is assembling a Video Audio Muxer queue
    if user_id in USER_STATES and USER_STATES[user_id].get("action") == "video_merge_audio":
        media_type, info = detect_media(message)
        state = USER_STATES[user_id]
        if media_type != "audio":
            warn = await message.reply_text(
                "⚠️ **Only audio files can be added to the video audio tracks queue!**",
                quote=True,
            )
            await asyncio.sleep(4)
            try:
                await warn.delete()
            except Exception:
                pass
            return

        tracks = state.setdefault("audio_tracks", [])
        tracks.append({
            "msg_id": message.id,
            "file_name": info.get("file_name", f"Audio Track {len(tracks) + 1}.mp3"),
            "duration": info.get("duration", 0),
            "file_size": info.get("file_size", 0),
        })

        menu_msg = await get_fresh_media_message(client, state["chat_id"], state["menu_msg_id"])
        if menu_msg:
            try:
                await menu_msg.edit_text(
                    text=build_video_merge_audio_text(state.get("file_name", "Video"), tracks),
                    reply_markup=get_video_merge_audio_keyboard(len(tracks)),
                )
            except Exception as e:
                logger.error(f"Error updating video audio merger menu: {e}")
        return

    # Intercept media if user is assembling a Video Merger queue (Fast Copy)
    if user_id in USER_STATES and USER_STATES[user_id].get("action") == "video_merger":
        media_type, info = detect_media(message)
        state = USER_STATES[user_id]
        if media_type != "video":
            warn = await message.reply_text(
                "⚠️ **Only video files can be added to the video merge queue!**",
                quote=True,
            )
            await asyncio.sleep(4)
            try:
                await warn.delete()
            except Exception:
                pass
            return

        videos = state.setdefault("videos", [])
        videos.append({
            "msg_id": message.id,
            "file_name": info.get("file_name", f"Video {len(videos) + 1}.mp4"),
            "duration": info.get("duration", 0),
            "file_size": info.get("file_size", 0),
        })

        menu_msg = await get_fresh_media_message(client, state["chat_id"], state["menu_msg_id"])
        if menu_msg:
            try:
                await menu_msg.edit_text(
                    text=build_video_merger_text(videos),
                    reply_markup=get_video_merger_keyboard(len(videos)),
                )
            except Exception as e:
                logger.error(f"Error updating video merger menu: {e}")
        return

    # Intercept media if user is assembling a Video Subtitle Muxer queue
    if user_id in USER_STATES and USER_STATES[user_id].get("action") == "video_merge_subtitle":
        state = USER_STATES[user_id]
        doc = message.document
        file_name = doc.file_name if doc else ""
        file_size = doc.file_size if doc else getattr(message.video or message.audio, "file_size", 0)

        # Check if user sent non-document or unsupported file
        ext = os.path.splitext(file_name)[1].lower() if file_name else ""
        valid_sub_exts = {".srt", ".ass", ".ssa", ".vtt", ".sub", ".txt"}
        if not doc or ext not in valid_sub_exts:
            warn = await message.reply_text(
                "⚠️ **Please send a subtitle file (`.srt`, `.ass`, `.vtt`, `.ssa`, `.sub`)!**",
                quote=True,
            )
            await asyncio.sleep(4)
            try:
                await warn.delete()
            except Exception:
                pass
            return

        tracks = state.setdefault("subtitle_tracks", [])
        tracks.append({
            "msg_id": message.id,
            "file_name": file_name,
            "file_size": file_size,
        })

        menu_msg = await get_fresh_media_message(client, state["chat_id"], state["menu_msg_id"])
        if menu_msg:
            try:
                await menu_msg.edit_text(
                    text=build_video_merge_subtitle_text(state.get("file_name", "Video"), tracks),
                    reply_markup=get_video_merge_subtitle_keyboard(len(tracks)),
                )
            except Exception as e:
                logger.error(f"Error updating video subtitle merger menu: {e}")
        return

    media_type, _ = detect_media(message)

    if media_type == "audio":
        await message.reply_text(
            text=build_audio_menu_text(message),
            reply_markup=get_audio_keyboard(),
            quote=True,
        )

    elif media_type == "video":
        await message.reply_text(
            text=build_video_menu_text(message),
            reply_markup=get_video_keyboard(),
            quote=True,
        )

    elif media_type == "file":
        await message.reply_text(
            text=build_file_menu_text(message),
            reply_markup=get_file_keyboard(),
            quote=True,
        )


@app.on_callback_query()
async def callback_handler(client: Client, query: CallbackQuery):
    """
    Handles all inline button clicks.
    Everything is updated in-place inside the SAME message!
    """
    data = query.data
    user = query.from_user
    first_name = user.first_name if user else "Friend"

    # --- REFRESH CURRENT TRANSMISSION DISPLAY ---
    if data.startswith("refresh_"):
        task_id = data.split("refresh_", 1)[1]
        await refresh_progress_display(query, task_id)
        return

    # --- CANCEL CURRENT TRANSMISSION ---
    elif data.startswith("cancel_"):
        task_id = data.split("cancel_", 1)[1]
        CANCELLED_TASKS.add(task_id)
        ACTIVE_PROGRESS.pop(task_id, None)
        back_kb = get_back_to_audio_keyboard()
        if user and user.id in USER_STATES:
            popped_state = USER_STATES.pop(user.id, None)
            if popped_state:
                popped_action = popped_state.get("action", "")
                if popped_action.startswith("video"):
                    back_kb = get_back_to_video_keyboard()
                if popped_state.get("temp_dir"):
                    shutil.rmtree(popped_state["temp_dir"], ignore_errors=True)
        await query.answer("Cancelling process...", show_alert=False)
        await query.message.edit_text(
            "🚫 **Process Cancelled!**\n\nThe operation was aborted by user.",
            reply_markup=back_kb,
        )
        return

    # --- SETTINGS TOGGLES ---
    elif data == "toggle_setting_audio":
        user_id = user.id if user else 0
        new_mode = toggle_user_upload_mode(user_id, "audio")
        settings = get_user_settings(user_id)
        mode_label = "File" if new_mode == "file" else "Audio"
        await query.answer(f"Audio upload set to: Upload as {mode_label}")
        await query.message.edit_text(
            text=get_settings_text(settings),
            reply_markup=get_settings_keyboard(settings["upload_audio"], settings["upload_video"]),
        )
        return

    elif data == "toggle_setting_video":
        user_id = user.id if user else 0
        new_mode = toggle_user_upload_mode(user_id, "video")
        settings = get_user_settings(user_id)
        mode_label = "File" if new_mode == "file" else "Video"
        await query.answer(f"Video upload set to: Upload as {mode_label}")
        await query.message.edit_text(
            text=get_settings_text(settings),
            reply_markup=get_settings_keyboard(settings["upload_audio"], settings["upload_video"]),
        )
        return

    elif data in ("close_settings", "cancel_settings"):
        await query.answer()
        message_ids = [query.message.id]
        if query.message.reply_to_message_id:
            message_ids.append(query.message.reply_to_message_id)
        elif query.message.reply_to_message:
            message_ids.append(query.message.reply_to_message.id)

        try:
            await client.delete_messages(
                chat_id=query.message.chat.id,
                message_ids=message_ids,
            )
        except Exception as e:
            logger.warning(f"Error deleting messages on close_settings: {e}")
            try:
                await query.message.delete()
            except Exception:
                pass
            if query.message.reply_to_message:
                try:
                    await query.message.reply_to_message.delete()
                except Exception:
                    pass
        return

    # --- HOME / START MENU NAVIGATION ---
    elif data == "home":
        if user:
            USER_STATES.pop(user.id, None)
        await query.message.edit_text(
            text=START_TEXT.format(first_name=first_name),
            reply_markup=get_start_keyboard(),
            disable_web_page_preview=True,
        )
        await query.answer()
        return

    elif data == "help":
        await query.message.edit_text(
            text=HELP_TEXT,
            reply_markup=get_back_keyboard(),
            disable_web_page_preview=True,
        )
        await query.answer()
        return

    elif data == "about":
        await query.message.edit_text(
            text=ABOUT_TEXT,
            reply_markup=get_back_keyboard(),
            disable_web_page_preview=True,
        )
        await query.answer()
        return

    elif data == "status":
        await query.answer("⚡ Bot server is running smoothly! Ready for 4 GB media tasks.", show_alert=True)
        return

    elif data == "close_menu":
        if user:
            USER_STATES.pop(user.id, None)
        try:
            # Delete both the bot's menu message and the user's original media message
            message_ids_to_delete = [query.message.id]
            if query.message.reply_to_message_id:
                message_ids_to_delete.append(query.message.reply_to_message_id)
            elif query.message.reply_to_message:
                message_ids_to_delete.append(query.message.reply_to_message.id)

            await client.delete_messages(
                chat_id=query.message.chat.id,
                message_ids=message_ids_to_delete,
            )
        except Exception as e:
            logger.warning(f"Error deleting messages on close_menu: {e}")
            try:
                await query.message.delete()
            except Exception:
                pass
        await query.answer("Menu and media closed.")
        return

    # --- AUDIO MENU IN-PLACE ACTIONS ---
    elif data == "audio_rename":
        media_msg_id = query.message.reply_to_message_id or (
            query.message.reply_to_message.id if query.message.reply_to_message else None
        )
        if user:
            USER_STATES[user.id] = {
                "action": "audio_rename",
                "menu_msg_id": query.message.id,
                "media_msg_id": media_msg_id,
                "chat_id": query.message.chat.id,
            }

        await query.message.edit_text(
            text=(
                "✏️ **Audio Rename Mode**\n\n"
                "Please type the new name for this audio file directly in this chat.\n\n"
                "💡 **Example:** `MyTrack.mp3` or `My_Favorite_Song`\n\n"
                "*(Press the button below to cancel)*"
            ),
            reply_markup=get_back_to_audio_keyboard(),
        )
        await query.answer()
        return

    elif data == "audio_merger":
        media_msg_id = query.message.reply_to_message_id or (
            query.message.reply_to_message.id if query.message.reply_to_message else None
        )
        if not media_msg_id:
            await query.answer("Original audio message not found!", show_alert=True)
            return

        target = await get_fresh_media_message(client, query.message.chat.id, media_msg_id)
        if not target:
            await query.answer("Could not fetch media from Telegram!", show_alert=True)
            return

        media_type, info = detect_media(target)
        if media_type != "audio":
            await query.answer("This file is not recognized as audio!", show_alert=True)
            return

        initial_track = {
            "msg_id": media_msg_id,
            "file_name": info.get("file_name", "Track 1.mp3"),
            "duration": info.get("duration", 0),
            "file_size": info.get("file_size", 0),
        }
        if user:
            USER_STATES[user.id] = {
                "action": "audio_merger",
                "menu_msg_id": query.message.id,
                "chat_id": query.message.chat.id,
                "tracks": [initial_track],
            }

        await query.message.edit_text(
            text=build_audio_merger_text([initial_track]),
            reply_markup=get_audio_merger_keyboard(1),
        )
        await query.answer()
        return

    elif data == "reset_audio_merger":
        if user and user.id in USER_STATES:
            state = USER_STATES[user.id]
            tracks = state.get("tracks", [])
            if tracks:
                state["tracks"] = [tracks[0]]
                await query.message.edit_text(
                    text=build_audio_merger_text(state["tracks"]),
                    reply_markup=get_audio_merger_keyboard(1),
                )
                await query.answer("Queue reset to initial track.", show_alert=False)
                return
        await query.answer("Session expired. Please start over.", show_alert=True)
        return

    elif data == "start_audio_merge":
        if not user or user.id not in USER_STATES:
            await query.answer("Merge session expired. Please start over.", show_alert=True)
            return

        state = USER_STATES[user.id]
        if state.get("action") != "audio_merger":
            await query.answer("No active merge session found.", show_alert=True)
            return

        tracks = list(state.get("tracks", []))
        if len(tracks) < 2:
            await query.answer("Please send at least 2 audio files to merge!", show_alert=True)
            return

        # Clear state now that merge execution has begun
        USER_STATES.pop(user.id, None)

        task_id = f"{user.id}_{query.message.id}"
        CANCELLED_TASKS.discard(task_id)

        await query.answer("Starting audio merge process...")
        temp_dir = os.path.join("downloads", f"{user.id}_merge_{int(time.time())}")
        os.makedirs(temp_dir, exist_ok=True)

        downloaded_paths = []
        try:
            # 1. Sequentially download each queued track
            for idx, tr in enumerate(tracks, start=1):
                if task_id in CANCELLED_TASKS:
                    return

                await query.message.edit_text(
                    f"📥 **Downloading Track {idx}/{len(tracks)}...**\n\nStarting download: `{tr.get('file_name', 'audio')}`",
                    reply_markup=get_cancel_process_keyboard(task_id),
                )

                tracker_down = ProgressTracker(
                    client=client,
                    message=query.message,
                    task_id=task_id,
                    action_name=f"📥 **Downloading Track {idx}/{len(tracks)}...**",
                    interval=8.0,
                    is_upload=False,
                )

                target_msg = await get_fresh_media_message(client, query.message.chat.id, tr["msg_id"])
                if not target_msg:
                    await query.message.edit_text(
                        f"❌ **Failed to fetch track {idx} from Telegram!**\nOne of the queued audios may have been deleted.",
                        reply_markup=get_back_to_audio_keyboard(),
                    )
                    return

                sanitized_name = re.sub(r'[\/:*?"<>|]', '_', tr.get("file_name", f"track_{idx}.mp3"))
                target_dest = os.path.join(temp_dir, f"track_{idx}_{sanitized_name}")

                downloaded = await download_media_with_retry(
                    client=client,
                    message=target_msg,
                    file_name=target_dest,
                    progress=tracker_down,
                )

                if task_id in CANCELLED_TASKS:
                    return

                if not downloaded or not os.path.exists(downloaded):
                    await query.message.edit_text(
                        f"❌ **Failed to download track {idx} (`{tr.get('file_name')}`)!**",
                        reply_markup=get_back_to_audio_keyboard(),
                    )
                    return

                downloaded_paths.append(downloaded)

            if task_id in CANCELLED_TASKS:
                return

            # Determine output extension based on inputs
            extensions = [os.path.splitext(p)[1].lower() for p in downloaded_paths]
            if all(ext == ".m4a" for ext in extensions):
                out_ext = ".m4a"
            elif all(ext == ".flac" for ext in extensions):
                out_ext = ".flac"
            elif all(ext == ".wav" for ext in extensions):
                out_ext = ".wav"
            else:
                out_ext = ".mp3"

            base_name = os.path.splitext(tracks[0].get("file_name", "audio"))[0]
            clean_base = re.sub(r'[\/:*?"<>|]', '_', base_name)
            output_filename = f"{clean_base}_merged{out_ext}"
            output_file = os.path.join(temp_dir, output_filename)

            total_expected_duration = sum(tr.get("duration", 0) for tr in tracks)

            await query.message.edit_text(
                f"⚙️ **Merging {len(downloaded_paths)} Audio Tracks...**\n\nInitializing FFmpeg filter...",
                reply_markup=get_cancel_process_keyboard(task_id),
            )

            # 2. Merge audio files using FFmpeg filter_complex with live progress
            success = await merge_audio_files_with_progress(
                input_paths=downloaded_paths,
                output_path=output_file,
                total_duration=total_expected_duration,
                message=query.message,
                task_id=task_id,
            )

            if task_id in CANCELLED_TASKS:
                return

            if not success or not os.path.exists(output_file) or os.path.getsize(output_file) == 0:
                await query.message.edit_text(
                    "❌ **FFmpeg Audio Merge failed!**\nPlease check your input audio files.",
                    reply_markup=get_back_to_audio_keyboard(),
                )
                return

            # Accurate duration check
            out_duration = get_media_duration(output_file)
            if out_duration == 0 and total_expected_duration > 0:
                out_duration = int(total_expected_duration)

            out_size = os.path.getsize(output_file)
            user_thumb = get_user_thumbnail(user.id)

            await query.message.edit_text(
                "📤 **Uploading Merged Audio...**\n\nPreparing upload to Telegram...",
                reply_markup=get_cancel_process_keyboard(task_id),
            )

            tracker_up = ProgressTracker(
                client=client,
                message=query.message,
                task_id=task_id,
                action_name="📤 **Uploading Merged Audio...**",
                interval=8.0,
                is_upload=True,
            )

            caption = (
                f"🔀 **Audio Merge Completed!** ({len(tracks)} Tracks)\n\n"
                f"• **File Name:** `{output_filename}`\n"
                f"• **Duration:** `{format_duration(out_duration)}`\n"
                f"• **Size:** `{humanbytes(out_size)}`"
            )

            user_settings = get_user_settings(user.id)
            if user_settings.get("upload_audio") == "file":
                await client.send_document(
                    chat_id=query.message.chat.id,
                    document=output_file,
                    caption=caption,
                    file_name=output_filename,
                    thumb=user_thumb,
                    force_document=True,
                    progress=tracker_up,
                )
            else:
                await client.send_audio(
                    chat_id=query.message.chat.id,
                    audio=output_file,
                    caption=caption,
                    duration=out_duration,
                    file_name=output_filename,
                    thumb=user_thumb,
                    progress=tracker_up,
                )

            # Delete the menu message upon successful upload (Single-Message Rule)
            try:
                await query.message.delete()
            except Exception:
                pass

        except StopTransmission:
            logger.info(f"Merge task {task_id} was stopped by user.")
        except Exception as e:
            logger.error(f"Error during Audio Merge: {e}", exc_info=True)
            try:
                await query.message.edit_text(
                    f"❌ **An error occurred during audio merge:** `{e}`",
                    reply_markup=get_back_to_audio_keyboard(),
                )
            except Exception:
                pass
        finally:
            CANCELLED_TASKS.discard(task_id)
            ACTIVE_PROGRESS.pop(task_id, None)
            shutil.rmtree(temp_dir, ignore_errors=True)
        return


    elif data == "audio_rm_title":
        media_msg_id = query.message.reply_to_message_id or (
            query.message.reply_to_message.id if query.message.reply_to_message else None
        )
        if not media_msg_id:
            await query.answer("Original audio message not found!", show_alert=True)
            return

        target = await get_fresh_media_message(client, query.message.chat.id, media_msg_id)
        if not target:
            await query.answer("Could not fetch media from Telegram!", show_alert=True)
            return

        media_type, info = detect_media(target)
        if media_type != "audio":
            await query.answer("This file is not recognized as audio!", show_alert=True)
            return

        task_id = f"{user.id}_{query.message.id}"
        CANCELLED_TASKS.discard(task_id)

        await query.answer("Starting metadata title removal...")
        await query.message.edit_text(
            "📥 **Downloading Audio...**\n\nStarting download, please wait...",
            reply_markup=get_cancel_process_keyboard(task_id),
        )

        temp_dir = os.path.join("downloads", f"{user.id}_rmtitle_{int(time.time())}")
        os.makedirs(temp_dir, exist_ok=True)

        try:
            tracker_down = ProgressTracker(
                client=client,
                message=query.message,
                task_id=task_id,
                action_name="📥 **Downloading Audio...**",
                interval=8.0,
                is_upload=False,
            )

            # Download using the fresh message with retry support
            downloaded_file = await download_media_with_retry(
                client=client,
                message=target,
                file_name=os.path.join(temp_dir, info.get("file_name", "audio.mp3")),
                progress=tracker_down,
            )

            if task_id in CANCELLED_TASKS:
                return

            if not downloaded_file or not os.path.exists(downloaded_file):
                await query.message.edit_text(
                    "❌ **Failed to download the audio file!**",
                    reply_markup=get_back_to_audio_keyboard(),
                )
                return

            await query.message.edit_text(
                "⚙️ **Processing Audio...**\n\n"
                "Stripping metadata title with FFmpeg & Mutagen...",
                reply_markup=get_cancel_process_keyboard(task_id),
            )

            cleaned_file = remove_audio_metadata_title(downloaded_file)

            if task_id in CANCELLED_TASKS:
                return

            tracker_up = ProgressTracker(
                client=client,
                message=query.message,
                task_id=task_id,
                action_name="📤 **Uploading Cleaned Audio...**",
                interval=8.0,
                is_upload=True,
            )

            caption = "🏷️ **Metadata title removed successfully!**"
            orig_performer = info.get("performer") if info.get("performer") != "Unknown Artist" else None
            out_duration = get_media_duration(cleaned_file) or info.get("duration", 0)

            user_thumb = get_user_thumbnail(query.from_user.id) if query.from_user else None

            user_settings = get_user_settings(query.from_user.id if query.from_user else 0)
            if user_settings.get("upload_audio") == "file":
                await client.send_document(
                    chat_id=query.message.chat.id,
                    document=cleaned_file,
                    caption=caption,
                    thumb=user_thumb,
                    force_document=True,
                    progress=tracker_up,
                )
            else:
                await client.send_audio(
                    chat_id=query.message.chat.id,
                    audio=cleaned_file,
                    caption=caption,
                    title="",
                    performer=orig_performer,
                    duration=out_duration,
                    thumb=user_thumb,
                    progress=tracker_up,
                )

            # Delete the progress message if completed normally
            if task_id not in CANCELLED_TASKS:
                try:
                    await query.message.delete()
                except Exception:
                    pass

        except StopTransmission:
            logger.info(f"Task {task_id} successfully cancelled by user.")
            try:
                await query.message.edit_text(
                    "🚫 **Process Cancelled!**\n\nThe operation was aborted by the user.",
                    reply_markup=get_back_to_audio_keyboard(),
                )
            except Exception:
                pass
            return

        except Exception as e:
            if task_id in CANCELLED_TASKS:
                return
            logger.error(f"Error in audio_rm_title: {e}", exc_info=True)
            await query.message.edit_text(
                f"❌ **An error occurred:** `{e}`",
                reply_markup=get_back_to_audio_keyboard(),
            )
        finally:
            CANCELLED_TASKS.discard(task_id)
            ACTIVE_PROGRESS.pop(task_id, None)
            shutil.rmtree(temp_dir, ignore_errors=True)
        return


    elif data == "audio_ffprobe":
        media_msg_id = query.message.reply_to_message_id or (
            query.message.reply_to_message.id if query.message.reply_to_message else None
        )
        if not media_msg_id:
            await query.answer("Original audio message not found!", show_alert=True)
            return

        target = await get_fresh_media_message(client, query.message.chat.id, media_msg_id)
        if not target:
            await query.answer("Could not fetch media from Telegram!", show_alert=True)
            return

        media_type, info = detect_media(target)
        if media_type != "audio":
            await query.answer("This file is not recognized as audio!", show_alert=True)
            return

        task_id = f"{user.id}_{query.message.id}"
        CANCELLED_TASKS.discard(task_id)

        await query.answer("Starting FFprobe analysis...")
        await query.message.edit_text(
            "📥 **Downloading Audio for FFprobe Analysis...**\n\nStarting download, please wait...",
            reply_markup=get_cancel_process_keyboard(task_id),
        )

        temp_dir = os.path.join("downloads", f"{user.id}_ffprobe_{int(time.time())}")
        os.makedirs(temp_dir, exist_ok=True)

        try:
            tracker_down = ProgressTracker(
                client=client,
                message=query.message,
                task_id=task_id,
                action_name="📥 **Downloading Audio for FFprobe Analysis...**",
                interval=8.0,
                is_upload=False,
            )

            orig_file_name = info.get("file_name", "audio.mp3")
            dest_file = os.path.join(temp_dir, orig_file_name)

            downloaded_file = await download_media_with_retry(
                client=client,
                message=target,
                file_name=dest_file,
                progress=tracker_down,
            )

            if task_id in CANCELLED_TASKS:
                return

            if not downloaded_file or not os.path.exists(downloaded_file):
                await query.message.edit_text(
                    "❌ **Failed to download the audio file!**",
                    reply_markup=get_back_to_audio_keyboard(),
                )
                return

            await query.message.edit_text(
                "⚙️ **Analyzing Audio with FFprobe...**\n\nExtracting detailed stream & metadata parameters...",
                reply_markup=get_cancel_process_keyboard(task_id),
            )

            probe_data = get_audio_ffprobe_info(downloaded_file)
            if not probe_data:
                await query.message.edit_text(
                    "❌ **FFprobe failed to inspect the audio file!**",
                    reply_markup=get_back_to_audio_keyboard(),
                )
                return

            analysis_text = format_ffprobe_audio_info(probe_data, fallback_name=orig_file_name)
            await query.message.edit_text(
                text=analysis_text,
                reply_markup=get_back_to_audio_keyboard(),
            )

        except StopTransmission:
            logger.info(f"FFprobe task {task_id} was stopped by user.")
        except Exception as e:
            logger.error(f"Error during FFprobe analysis: {e}", exc_info=True)
            try:
                await query.message.edit_text(
                    f"❌ **An error occurred during FFprobe analysis:** `{e}`",
                    reply_markup=get_back_to_audio_keyboard(),
                )
            except Exception:
                pass
        finally:
            CANCELLED_TASKS.discard(task_id)
            ACTIVE_PROGRESS.pop(task_id, None)
            shutil.rmtree(temp_dir, ignore_errors=True)
        return


    elif data == "audio_trimmer":
        if user:
            USER_STATES.pop(user.id, None)
        trimmer_text = (
            "✂️ **Audio Trimmer Options**\n\n"
            "Please choose your preferred trimming method:\n\n"
            "• ⚡ **Fast Copy:** Stream copy mode. Ultra-fast cut without re-encoding, 100% original quality preserved.\n\n"
            "• 🎯 **Frame Accuracy:** Precise cut down to frame/millisecond. Re-encodes audio boundaries if needed.\n\n"
            "Select an option below:"
        )
        await query.message.edit_text(
            text=trimmer_text,
            reply_markup=get_audio_trimmer_keyboard(),
        )
        await query.answer()
        return

    elif data == "trim_mode_fast":
        media_msg_id = query.message.reply_to_message_id or (
            query.message.reply_to_message.id if query.message.reply_to_message else None
        )
        if user:
            USER_STATES[user.id] = {
                "action": "trim_fast",
                "menu_msg_id": query.message.id,
                "media_msg_id": media_msg_id,
                "chat_id": query.message.chat.id,
            }

        await query.message.edit_text(
            text=(
                "⚡ **Fast Copy Mode Selected**\n\n"
                "Stream copy mode cuts audio in seconds with zero quality loss.\n\n"
                "Please type the start and end timestamp in chat:\n"
                "• Format: `HH:MM:SS - HH:MM:SS` or `MM:SS - MM:SS`\n"
                "💡 **Example:** `00:15 - 01:45`\n\n"
                "*(Press below to switch mode or go back)*"
            ),
            reply_markup=get_back_to_trimmer_keyboard(),
        )
        await query.answer()
        return

    elif data == "trim_mode_accurate":
        media_msg_id = query.message.reply_to_message_id or (
            query.message.reply_to_message.id if query.message.reply_to_message else None
        )
        if user:
            USER_STATES[user.id] = {
                "action": "trim_accurate",
                "menu_msg_id": query.message.id,
                "media_msg_id": media_msg_id,
                "chat_id": query.message.chat.id,
            }

        await query.message.edit_text(
            text=(
                "🎯 **Frame Accuracy Mode Selected**\n\n"
                "Millisecond-accurate cutting with boundary precision.\n\n"
                "Please type the exact timestamps in chat:\n"
                "• Format: `HH:MM:SS.xxx - HH:MM:SS.xxx` or `MM:SS - MM:SS`\n"
                "💡 **Example:** `00:15.500 - 01:45.250`\n\n"
                "*(Press below to switch mode or go back)*"
            ),
            reply_markup=get_back_to_trimmer_keyboard(),
        )
        await query.answer()
        return

    elif data == "audio_ffmpeg":
        media_msg_id = query.message.reply_to_message_id or (
            query.message.reply_to_message.id if query.message.reply_to_message else None
        )
        if user:
            USER_STATES[user.id] = {
                "action": "audio_ffmpeg",
                "menu_msg_id": query.message.id,
                "media_msg_id": media_msg_id,
                "chat_id": query.message.chat.id,
            }

        ffmpeg_info_text = (
            "💻 **Custom FFmpeg Command Mode**\n\n"
            "Please type your custom FFmpeg arguments or command directly in chat!\n\n"
            "💡 **Popular Examples:**\n"
            "• `-af \"volume=1.5\"` *(Boost audio volume by 50%)*\n"
            "• `-af \"atempo=1.25\"` *(Speed up audio 1.25x without changing pitch)*\n"
            "• `-b:a 320k` *(Re-encode to 320 kbps high bitrate)*\n"
            "• `-af \"bass=g=6\"` *(Boost bass by +6dB)*\n"
            "• `-af \"lowpass=f=3000\"` *(Lo-Fi / muffled audio filter)*\n"
            "• `-af \"aecho=0.8:0.88:60:0.4\"` *(Echo effect)*\n"
            "• Or full syntax: `ffmpeg -i in.mp3 -b:a 192k out.mp3`\n\n"
            "*(Input and output paths will be mapped automatically)*"
        )
        await query.message.edit_text(
            text=ffmpeg_info_text,
            reply_markup=get_back_to_audio_keyboard(),
        )
        await query.answer()
        return

    elif data == "audio_menu_back":
        if user:
            USER_STATES.pop(user.id, None)
        # Restore main Audio Management Menu in the same message
        await query.message.edit_text(
            text=build_audio_menu_text(query.message),
            reply_markup=get_audio_keyboard(),
        )
        await query.answer()
        return

    # --- VIDEO MENU IN-PLACE ACTIONS ---
    elif data == "video_rename":
        media_msg_id = query.message.reply_to_message_id or (
            query.message.reply_to_message.id if query.message.reply_to_message else None
        )
        if media_msg_id:
            target_msg = await get_fresh_media_message(client, query.message.chat.id, media_msg_id)
            if target_msg:
                _, t_info = detect_media(target_msg)
                if t_info.get("file_size", 0) > MAX_BOT_UPLOAD_SIZE:
                    await query.answer(
                        "⚠️ Ushbu fayl 2 GB dan katta! Telegram botlari 2 GB dan katta fayllarni qayta yuklay olmaydi.",
                        show_alert=True,
                    )
                    return

        if user:
            USER_STATES[user.id] = {
                "action": "video_rename",
                "menu_msg_id": query.message.id,
                "media_msg_id": media_msg_id,
                "chat_id": query.message.chat.id,
            }

        await query.message.edit_text(
            text=(
                "✏️ **Video Rename Mode**\n\n"
                "Please type the new name for this video file directly in this chat.\n\n"
                "💡 **Example:** `Movie.mp4` or `My_Video`\n\n"
                "*(Press the button below to cancel)*"
            ),
            reply_markup=get_back_to_video_keyboard(),
        )
        await query.answer()
        return

    elif data == "video_metadata":
        media_msg_id = query.message.reply_to_message_id or (
            query.message.reply_to_message.id if query.message.reply_to_message else None
        )
        if not media_msg_id:
            await query.answer("Original video message not found!", show_alert=True)
            return

        target = await get_fresh_media_message(client, query.message.chat.id, media_msg_id)
        if not target:
            await query.answer("Could not fetch media from Telegram!", show_alert=True)
            return

        media_type, info = detect_media(target)
        if media_type != "video":
            await query.answer("This file is not recognized as video!", show_alert=True)
            return

        task_id = f"{user.id}_{query.message.id}"
        CANCELLED_TASKS.discard(task_id)

        await query.answer("Downloading video for metadata analysis...")
        await query.message.edit_text(
            "📥 **Downloading Video for Metadata Analysis...**\n\nStarting download, please wait...",
            reply_markup=get_cancel_process_keyboard(task_id),
        )

        temp_dir = os.path.join("downloads", f"{user.id}_vmeta_{int(time.time())}")
        os.makedirs(temp_dir, exist_ok=True)
        cleanup_needed = True

        try:
            tracker_down = ProgressTracker(
                client=client,
                message=query.message,
                task_id=task_id,
                action_name="📥 **Downloading Video for Metadata Analysis...**",
                interval=8.0,
                is_upload=False,
            )

            orig_file_name = info.get("file_name", "video.mp4")
            dest_file = os.path.join(temp_dir, re.sub(r'[\\/:*?"<>|]', '_', orig_file_name))

            downloaded = await download_media_with_retry(
                client=client,
                message=target,
                file_name=dest_file,
                progress=tracker_down,
            )

            if task_id in CANCELLED_TASKS:
                return

            if not downloaded or not os.path.exists(downloaded):
                await query.message.edit_text(
                    "❌ **Failed to download the video file!**",
                    reply_markup=get_back_to_video_keyboard(),
                )
                return

            await query.message.edit_text(
                "⚙️ **Analyzing Video with FFprobe...**\n\nExtracting streams & metadata...",
                reply_markup=get_cancel_process_keyboard(task_id),
            )

            probe_data = get_audio_ffprobe_info(downloaded)
            if not probe_data:
                await query.message.edit_text(
                    "❌ **FFprobe failed to inspect the video file!**",
                    reply_markup=get_back_to_video_keyboard(),
                )
                return

            streams = extract_video_streams(probe_data)
            pending_metadata = {"global_title": None, "streams": {}}
            metadata_text = format_video_metadata_text(
                probe_data,
                fallback_name=orig_file_name,
                pending_metadata=pending_metadata,
            )
            # Telegram message limit safety
            if len(metadata_text) > 4000:
                metadata_text = metadata_text[:3990] + "\n\n*... (truncated)*"

            # Store state with downloaded file for later editing
            if user:
                USER_STATES[user.id] = {
                    "action": "video_metadata",
                    "menu_msg_id": query.message.id,
                    "media_msg_id": media_msg_id,
                    "chat_id": query.message.chat.id,
                    "temp_dir": temp_dir,
                    "downloaded_path": downloaded,
                    "probe_data": probe_data,
                    "streams": streams,
                    "file_name": orig_file_name,
                    "pending_metadata": pending_metadata,
                }
                cleanup_needed = False  # File kept for editing

            await query.message.edit_text(
                text=metadata_text,
                reply_markup=get_video_metadata_keyboard(
                    streams["audio"],
                    streams["subtitle"],
                    has_changes=False,
                    pending_metadata=pending_metadata,
                ),
            )

        except StopTransmission:
            logger.info(f"Metadata analysis task {task_id} was stopped by user.")
        except Exception as e:
            logger.error(f"Error during video metadata analysis: {e}", exc_info=True)
            try:
                await query.message.edit_text(
                    f"❌ **An error occurred during metadata analysis:** `{e}`",
                    reply_markup=get_back_to_video_keyboard(),
                )
            except Exception:
                pass
        finally:
            CANCELLED_TASKS.discard(task_id)
            ACTIVE_PROGRESS.pop(task_id, None)
            if cleanup_needed:
                shutil.rmtree(temp_dir, ignore_errors=True)
        return

    elif data.startswith("vmeta_"):
        if not user or user.id not in USER_STATES:
            await query.answer("Session expired. Please start over.", show_alert=True)
            return

        state = USER_STATES[user.id]
        downloaded = state.get("downloaded_path", "")
        if not downloaded or not os.path.exists(downloaded):
            await query.answer("Downloaded file expired. Please start over.", show_alert=True)
            USER_STATES.pop(user.id, None)
            if state.get("temp_dir"):
                shutil.rmtree(state["temp_dir"], ignore_errors=True)
            return

        stream_code = data[6:]  # 'v', 'a0', 's1', etc.

        # 1. Video Title Edit
        if stream_code == "v":
            state["action"] = "video_metadata_edit_title"
            cur_title = state.get("pending_metadata", {}).get("global_title") or "Not set"
            await query.message.edit_text(
                text=(
                    "🎬 **Edit Video Title**\n\n"
                    f"• **Current Title:** `{cur_title}`\n\n"
                    "Please type the new title for this video directly in chat.\n\n"
                    "💡 **Example:** `Avatar: The Way of Water (2022)`\n\n"
                    "*(Press below to return without changing)*"
                ),
                reply_markup=get_back_to_metadata_keyboard(),
            )
            await query.answer()
            return

        # 2. Audio or Subtitle Stream Edit
        stream_type = stream_code[0]  # 'a' or 's'
        try:
            stream_idx = int(stream_code[1:])
        except ValueError:
            await query.answer("Invalid stream reference!", show_alert=True)
            return

        type_label = "Audio" if stream_type == "a" else "Subtitle"
        stream_key = f"{stream_type}:{stream_idx}"
        cur_stream_info = state.get("pending_metadata", {}).get("streams", {}).get(stream_key, {})
        cur_title = cur_stream_info.get("title", "N/A")
        cur_lang = cur_stream_info.get("language", "und")

        state["action"] = "video_metadata_edit_stream"
        state["stream_type"] = stream_type
        state["stream_idx"] = stream_idx

        await query.message.edit_text(
            text=(
                f"✏️ **Edit {type_label} Stream #{stream_idx + 1} Metadata**\n\n"
                f"• **Current:** Title: `{cur_title}` | Lang: `{cur_lang}`\n\n"
                f"Please type the new **Title** and **Language Code** in this format:\n\n"
                f"`Title|Language`\n\n"
                f"💡 **Example:** `AsilMedia|uzb`\n\n"
                f"• **Title:** Label for this {type_label.lower()} track\n"
                f"• **Language:** ISO 639 code (`uzb`, `eng`, `rus`, `jpn`, `tur`...)\n\n"
                f"*(Press below to return to Metadata Editor)*"
            ),
            reply_markup=get_back_to_metadata_keyboard(),
        )
        await query.answer()
        return

    elif data == "video_metadata_apply":
        # Apply all pending metadata changes using FFmpeg stream copy
        if not user or user.id not in USER_STATES:
            await query.answer("Session expired. Please start over.", show_alert=True)
            return

        state = USER_STATES[user.id]
        downloaded = state.get("downloaded_path", "")
        vid_temp_dir = state.get("temp_dir", "")
        saved_file_name = state.get("file_name", "video.mp4")
        pending_metadata = state.get("pending_metadata", {})

        has_changes = bool(
            pending_metadata.get("global_title") is not None
            or pending_metadata.get("streams")
        )

        if not has_changes:
            await query.answer("No metadata changes made yet!", show_alert=True)
            return

        if not downloaded or not os.path.exists(downloaded):
            await query.answer("Downloaded file expired. Please start over.", show_alert=True)
            USER_STATES.pop(user.id, None)
            if vid_temp_dir:
                shutil.rmtree(vid_temp_dir, ignore_errors=True)
            return

        # Clear state as export process begins
        USER_STATES.pop(user.id, None)
        task_id = f"{user.id}_{query.message.id}"
        CANCELLED_TASKS.discard(task_id)

        base_name, ext = os.path.splitext(saved_file_name)
        if not ext:
            ext = ".mp4"
        output_name = f"{base_name}_meta{ext}"
        output_path = os.path.join(vid_temp_dir, re.sub(r'[\\/:*?"<>|]', '_', output_name))

        await query.answer("Applying metadata changes with FFmpeg...")
        await query.message.edit_text(
            "⚙️ **Applying All Metadata Changes...**\n\n"
            "Processing stream tags with FFmpeg (stream copy, 100% quality preserved)...",
            reply_markup=get_cancel_process_keyboard(task_id),
        )

        try:
            success, err_msg = apply_all_video_metadata(
                input_path=downloaded,
                output_path=output_path,
                pending_metadata=pending_metadata,
            )

            if task_id in CANCELLED_TASKS:
                return

            if not success or not os.path.exists(output_path):
                short_err = err_msg if len(err_msg) < 400 else err_msg[-400:]
                await query.message.edit_text(
                    f"❌ **FFmpeg Metadata Application Failed!**\n\n```text\n{short_err}\n```",
                    reply_markup=get_back_to_video_keyboard(),
                )
                return

            tracker_up = ProgressTracker(
                client=client,
                message=query.message,
                task_id=task_id,
                action_name="📤 **Uploading Updated Video...**",
                interval=8.0,
                is_upload=True,
            )

            # Build summary caption
            summary_lines = ["🏷️ **Video Metadata Updated Successfully!**\n"]
            if pending_metadata.get("global_title"):
                summary_lines.append(f"• **Title:** `{pending_metadata['global_title']}`")
            for sk, sinfo in pending_metadata.get("streams", {}).items():
                stype, snum = sk.split(":")
                t_label = "Audio" if stype == "a" else ("Sub" if stype == "s" else "Video")
                summary_lines.append(f"• **{t_label} #{int(snum) + 1}:** `{sinfo.get('title')}` (`{sinfo.get('language')}`)")

            caption = "\n".join(summary_lines)
            if len(caption) > 1000:
                caption = caption[:990] + "..."

            out_size = os.path.getsize(output_path)
            if out_size > MAX_BOT_UPLOAD_SIZE:
                ACTIVE_PROGRESS.pop(task_id, None)
                await query.message.edit_text(
                    text=build_file_too_large_text(out_size),
                    reply_markup=get_back_to_video_keyboard(),
                )
                return

            user_thumb = get_user_thumbnail(user.id)
            out_duration = get_media_duration(output_path)
            vid_w, vid_h = get_video_dimensions(output_path)

            target_msg = await get_fresh_media_message(client, query.message.chat.id, state.get("media_msg_id"))
            vid_info = target_msg.video if target_msg and target_msg.video else None
            if not vid_w and vid_info:
                vid_w = vid_info.width or 0
                vid_h = vid_info.height or 0

            user_settings = get_user_settings(user.id)
            if user_settings.get("upload_video") != "file":
                await client.send_video(
                    chat_id=query.message.chat.id,
                    video=output_path,
                    caption=caption,
                    file_name=saved_file_name,
                    duration=out_duration or (vid_info.duration if vid_info else 0),
                    width=vid_w or 0,
                    height=vid_h or 0,
                    thumb=user_thumb,
                    supports_streaming=True,
                    progress=tracker_up,
                )
            else:
                await client.send_document(
                    chat_id=query.message.chat.id,
                    document=output_path,
                    caption=caption,
                    file_name=saved_file_name,
                    thumb=user_thumb,
                    force_document=True,
                    progress=tracker_up,
                )

            # Delete the menu message
            if task_id not in CANCELLED_TASKS:
                try:
                    await query.message.delete()
                except Exception:
                    pass

        except StopTransmission:
            logger.info(f"Metadata apply task {task_id} cancelled.")
            try:
                await query.message.edit_text(
                    "🚫 **Process Cancelled!**",
                    reply_markup=get_back_to_video_keyboard(),
                )
            except Exception:
                pass
        except Exception as e:
            logger.error(f"Error during video metadata apply: {e}", exc_info=True)
            await query.message.edit_text(
                f"❌ **Error applying metadata:** `{e}`",
                reply_markup=get_back_to_video_keyboard(),
            )
        finally:
            CANCELLED_TASKS.discard(task_id)
            ACTIVE_PROGRESS.pop(task_id, None)
            if vid_temp_dir:
                shutil.rmtree(vid_temp_dir, ignore_errors=True)
        return

    elif data == "video_metadata_back":
        # Return to metadata display from edit prompt
        if not user or user.id not in USER_STATES:
            await query.answer("Session expired.", show_alert=True)
            return

        state = USER_STATES[user.id]
        probe_data = state.get("probe_data")
        streams = state.get("streams")
        orig_name = state.get("file_name", "video.mp4")
        pending_metadata = state.get("pending_metadata", {})

        if probe_data and streams:
            state["action"] = "video_metadata"
            metadata_text = format_video_metadata_text(
                probe_data,
                fallback_name=orig_name,
                pending_metadata=pending_metadata,
            )
            if len(metadata_text) > 4000:
                metadata_text = metadata_text[:3990] + "\n\n*... (truncated)*"

            has_changes = bool(
                pending_metadata.get("global_title") is not None
                or pending_metadata.get("streams")
            )

            await query.message.edit_text(
                text=metadata_text,
                reply_markup=get_video_metadata_keyboard(
                    streams["audio"],
                    streams["subtitle"],
                    has_changes=has_changes,
                    pending_metadata=pending_metadata,
                ),
            )
        else:
            await query.message.edit_text(
                "❌ **Session data not found!** Please try again.",
                reply_markup=get_back_to_video_keyboard(),
            )
            USER_STATES.pop(user.id, None)
        await query.answer()
        return

    elif data == "video_stream_remover":
        media_msg_id = query.message.reply_to_message_id or (
            query.message.reply_to_message.id if query.message.reply_to_message else None
        )
        if not media_msg_id:
            await query.answer("Original video message not found!", show_alert=True)
            return

        target = await get_fresh_media_message(client, query.message.chat.id, media_msg_id)
        if not target:
            await query.answer("Could not fetch media from Telegram!", show_alert=True)
            return

        media_type, info = detect_media(target)
        if media_type != "video":
            await query.answer("This file is not recognized as video!", show_alert=True)
            return

        # Check if we already have the downloaded file from an active state
        existing_state = USER_STATES.get(user.id, {}) if user else {}
        existing_downloaded = existing_state.get("downloaded_path")
        existing_temp_dir = existing_state.get("temp_dir")
        existing_probe = existing_state.get("probe_data")

        orig_file_name = info.get("file_name", "video.mp4")

        if existing_downloaded and os.path.exists(existing_downloaded) and existing_probe:
            downloaded = existing_downloaded
            temp_dir = existing_temp_dir
            probe_data = existing_probe
            cleanup_needed = False
        else:
            task_id = f"{user.id}_{query.message.id}"
            CANCELLED_TASKS.discard(task_id)

            await query.answer("Downloading video for Stream Remover...")
            await query.message.edit_text(
                "📥 **Downloading Video for Stream Analysis...**\n\nStarting download, please wait...",
                reply_markup=get_cancel_process_keyboard(task_id),
            )

            temp_dir = os.path.join("downloads", f"{user.id}_vrem_{int(time.time())}")
            os.makedirs(temp_dir, exist_ok=True)
            cleanup_needed = True

            try:
                tracker_down = ProgressTracker(
                    client=client,
                    message=query.message,
                    task_id=task_id,
                    action_name="📥 **Downloading Video for Stream Analysis...**",
                    interval=8.0,
                    is_upload=False,
                )

                dest_file = os.path.join(temp_dir, re.sub(r'[\\/:*?"<>|]', '_', orig_file_name))
                downloaded = await download_media_with_retry(
                    client=client,
                    message=target,
                    file_name=dest_file,
                    progress=tracker_down,
                )

                if task_id in CANCELLED_TASKS:
                    return

                if not downloaded or not os.path.exists(downloaded):
                    await query.message.edit_text(
                        "❌ **Failed to download the video file!**",
                        reply_markup=get_back_to_video_keyboard(),
                    )
                    return

                await query.message.edit_text(
                    "⚙️ **Analyzing Video Streams with FFprobe...**\n\nIdentifying all audio, video, and subtitle tracks...",
                    reply_markup=get_cancel_process_keyboard(task_id),
                )

                probe_data = get_audio_ffprobe_info(downloaded)
                if not probe_data:
                    await query.message.edit_text(
                        "❌ **FFprobe failed to inspect the video file!**",
                        reply_markup=get_back_to_video_keyboard(),
                    )
                    return

            except StopTransmission:
                logger.info(f"Stream remover download {task_id} was stopped by user.")
                return
            except Exception as e:
                logger.error(f"Error downloading for stream remover: {e}", exc_info=True)
                await query.message.edit_text(
                    f"❌ **An error occurred during preparation:** `{e}`",
                    reply_markup=get_back_to_video_keyboard(),
                )
                return
            finally:
                CANCELLED_TASKS.discard(task_id)
                ACTIVE_PROGRESS.pop(task_id, None)

        streams_flat = get_all_streams_flat(probe_data)
        selected_indices = set()

        if user:
            USER_STATES[user.id] = {
                "action": "video_stream_remover",
                "menu_msg_id": query.message.id,
                "media_msg_id": media_msg_id,
                "chat_id": query.message.chat.id,
                "temp_dir": temp_dir,
                "downloaded_path": downloaded,
                "probe_data": probe_data,
                "streams": streams_flat,
                "selected_indices": selected_indices,
                "file_name": orig_file_name,
            }

        remover_text = format_stream_remover_text(probe_data, selected_indices, fallback_name=orig_file_name)
        if len(remover_text) > 4000:
            remover_text = remover_text[:3990] + "\n\n*... (truncated)*"

        await query.message.edit_text(
            text=remover_text,
            reply_markup=get_stream_remover_keyboard(streams_flat, selected_indices),
        )
        return

    elif data.startswith("vrem_toggle_"):
        if not user or user.id not in USER_STATES:
            await query.answer("Session expired. Please start over.", show_alert=True)
            return

        state = USER_STATES[user.id]
        if state.get("action") != "video_stream_remover":
            await query.answer("Invalid session state.", show_alert=True)
            return

        try:
            target_idx = int(data.split("vrem_toggle_", 1)[1])
        except ValueError:
            await query.answer("Invalid stream index!", show_alert=True)
            return

        selected_indices = state.setdefault("selected_indices", set())
        streams_flat = state.get("streams", [])
        total_streams = len(streams_flat)

        if target_idx in selected_indices:
            selected_indices.remove(target_idx)
            await query.answer("Stream unmarked.")
        else:
            # Safety check: prevent selecting ALL streams (must keep at least 1)
            if len(selected_indices) + 1 >= total_streams:
                await query.answer("⚠️ You cannot remove all streams! At least 1 stream must be kept.", show_alert=True)
                return
            selected_indices.add(target_idx)
            await query.answer("Stream marked for removal.")

        probe_data = state.get("probe_data", {})
        orig_file_name = state.get("file_name", "video.mp4")

        remover_text = format_stream_remover_text(probe_data, selected_indices, fallback_name=orig_file_name)
        if len(remover_text) > 4000:
            remover_text = remover_text[:3990] + "\n\n*... (truncated)*"

        await query.message.edit_text(
            text=remover_text,
            reply_markup=get_stream_remover_keyboard(streams_flat, selected_indices),
        )
        return

    elif data == "vrem_apply":
        if not user or user.id not in USER_STATES:
            await query.answer("Session expired. Please start over.", show_alert=True)
            return

        state = USER_STATES[user.id]
        if state.get("action") != "video_stream_remover":
            await query.answer("No active stream removal session found.", show_alert=True)
            return

        selected_indices = state.get("selected_indices", set())
        if not selected_indices:
            await query.answer("Please select at least 1 stream to remove!", show_alert=True)
            return

        downloaded = state.get("downloaded_path")
        vid_temp_dir = state.get("temp_dir")
        saved_file_name = state.get("file_name", "video.mp4")

        if not downloaded or not os.path.exists(downloaded):
            await query.answer("Downloaded file expired. Please start over.", show_alert=True)
            USER_STATES.pop(user.id, None)
            if vid_temp_dir:
                shutil.rmtree(vid_temp_dir, ignore_errors=True)
            return

        # Clear state as removal execution starts
        USER_STATES.pop(user.id, None)
        task_id = f"{user.id}_{query.message.id}"
        CANCELLED_TASKS.discard(task_id)

        base_name, ext = os.path.splitext(saved_file_name)
        if not ext:
            ext = ".mp4"
        output_name = f"{base_name}_stripped{ext}"
        output_path = os.path.join(vid_temp_dir, re.sub(r'[\\/:*?"<>|]', '_', output_name))

        remove_list = sorted(list(selected_indices))
        streams_flat = state.get("streams", [])
        removed_desc = []
        for s_idx in remove_list:
            match = next((s for s in streams_flat if s["index"] == s_idx), None)
            if match:
                removed_desc.append(f"#{s_idx} ({match['type'].capitalize()} {match['codec_name']})")
            else:
                removed_desc.append(f"#{s_idx}")

        await query.answer("Removing selected streams with FFmpeg...")
        await query.message.edit_text(
            f"⚙️ **Removing {len(remove_list)} Stream(s)...**\n\n"
            f"• **Removed:** {', '.join(removed_desc)}\n\n"
            "Processing with FFmpeg stream-copy (lossless & fast)...",
            reply_markup=get_cancel_process_keyboard(task_id),
        )

        try:
            success, err_msg = remove_streams_from_video(
                input_path=downloaded,
                output_path=output_path,
                remove_indices=remove_list,
            )

            if task_id in CANCELLED_TASKS:
                return

            if not success or not os.path.exists(output_path):
                short_err = err_msg if len(err_msg) < 400 else err_msg[-400:]
                await query.message.edit_text(
                    f"❌ **Stream Removal Failed!**\n\n```text\n{short_err}\n```",
                    reply_markup=get_back_to_video_keyboard(),
                )
                return

            tracker_up = ProgressTracker(
                client=client,
                message=query.message,
                task_id=task_id,
                action_name="📤 **Uploading Cleaned Video...**",
                interval=8.0,
                is_upload=True,
            )

            caption = (
                f"🗑️ **Stream Removal Completed!**\n\n"
                f"• **Removed Streams:** `{', '.join(removed_desc)}`\n"
                f"• **Remaining Size:** `{humanbytes(os.path.getsize(output_path))}`"
            )

            out_size = os.path.getsize(output_path)
            if out_size > MAX_BOT_UPLOAD_SIZE:
                ACTIVE_PROGRESS.pop(task_id, None)
                await query.message.edit_text(
                    text=build_file_too_large_text(out_size),
                    reply_markup=get_back_to_video_keyboard(),
                )
                return

            user_thumb = get_user_thumbnail(user.id)
            out_duration = get_media_duration(output_path)
            vid_w, vid_h = get_video_dimensions(output_path)

            target_msg = await get_fresh_media_message(client, query.message.chat.id, state.get("media_msg_id"))
            vid_info = target_msg.video if target_msg and target_msg.video else None
            if not vid_w and vid_info:
                vid_w = vid_info.width or 0
                vid_h = vid_info.height or 0

            user_settings = get_user_settings(user.id)
            if user_settings.get("upload_video") != "file":
                await client.send_video(
                    chat_id=query.message.chat.id,
                    video=output_path,
                    caption=caption,
                    file_name=saved_file_name,
                    duration=out_duration or (vid_info.duration if vid_info else 0),
                    width=vid_w or 0,
                    height=vid_h or 0,
                    thumb=user_thumb,
                    supports_streaming=True,
                    progress=tracker_up,
                )
            else:
                await client.send_document(
                    chat_id=query.message.chat.id,
                    document=output_path,
                    caption=caption,
                    file_name=saved_file_name,
                    thumb=user_thumb,
                    force_document=True,
                    progress=tracker_up,
                )

            # Delete the menu message
            if task_id not in CANCELLED_TASKS:
                try:
                    await query.message.delete()
                except Exception:
                    pass

        except StopTransmission:
            logger.info(f"Stream removal task {task_id} cancelled.")
            try:
                await query.message.edit_text(
                    "🚫 **Process Cancelled!**",
                    reply_markup=get_back_to_video_keyboard(),
                )
            except Exception:
                pass
        except Exception as e:
            logger.error(f"Error during stream removal: {e}", exc_info=True)
            await query.message.edit_text(
                f"❌ **Error removing streams:** `{e}`",
                reply_markup=get_back_to_video_keyboard(),
            )
        finally:
            CANCELLED_TASKS.discard(task_id)
            ACTIVE_PROGRESS.pop(task_id, None)
            if vid_temp_dir:
                shutil.rmtree(vid_temp_dir, ignore_errors=True)
        return

    elif data == "video_stream_extractor":
        media_msg_id = query.message.reply_to_message_id or (
            query.message.reply_to_message.id if query.message.reply_to_message else None
        )
        if not media_msg_id:
            await query.answer("Original video message not found!", show_alert=True)
            return

        target = await get_fresh_media_message(client, query.message.chat.id, media_msg_id)
        if not target:
            await query.answer("Could not fetch media from Telegram!", show_alert=True)
            return

        media_type, info = detect_media(target)
        if media_type != "video":
            await query.answer("This file is not recognized as video!", show_alert=True)
            return

        # Check existing state for pre-downloaded file
        existing_state = USER_STATES.get(user.id, {}) if user else {}
        existing_downloaded = existing_state.get("downloaded_path")
        existing_temp_dir = existing_state.get("temp_dir")
        existing_probe = existing_state.get("probe_data")

        orig_file_name = info.get("file_name", "video.mp4")

        if existing_downloaded and os.path.exists(existing_downloaded) and existing_probe:
            downloaded = existing_downloaded
            temp_dir = existing_temp_dir
            probe_data = existing_probe
        else:
            task_id = f"{user.id}_{query.message.id}"
            CANCELLED_TASKS.discard(task_id)

            await query.answer("Downloading video for Stream Extractor...")
            await query.message.edit_text(
                "📥 **Downloading Video for Stream Extraction...**\n\nStarting download, please wait...",
                reply_markup=get_cancel_process_keyboard(task_id),
            )

            temp_dir = os.path.join("downloads", f"{user.id}_vext_{int(time.time())}")
            os.makedirs(temp_dir, exist_ok=True)

            try:
                tracker_down = ProgressTracker(
                    client=client,
                    message=query.message,
                    task_id=task_id,
                    action_name="📥 **Downloading Video for Stream Extraction...**",
                    interval=8.0,
                    is_upload=False,
                )

                dest_file = os.path.join(temp_dir, re.sub(r'[\\/:*?"<>|]', '_', orig_file_name))
                downloaded = await download_media_with_retry(
                    client=client,
                    message=target,
                    file_name=dest_file,
                    progress=tracker_down,
                )

                if task_id in CANCELLED_TASKS:
                    return

                if not downloaded or not os.path.exists(downloaded):
                    await query.message.edit_text(
                        "❌ **Failed to download the video file!**",
                        reply_markup=get_back_to_video_keyboard(),
                    )
                    return

                await query.message.edit_text(
                    "⚙️ **Analyzing Video Streams with FFprobe...**\n\nIdentifying all available tracks...",
                    reply_markup=get_cancel_process_keyboard(task_id),
                )

                probe_data = get_audio_ffprobe_info(downloaded)
                if not probe_data:
                    await query.message.edit_text(
                        "❌ **FFprobe failed to inspect the video file!**",
                        reply_markup=get_back_to_video_keyboard(),
                    )
                    return

            except StopTransmission:
                logger.info(f"Stream extractor download {task_id} was stopped by user.")
                return
            except Exception as e:
                logger.error(f"Error downloading for stream extractor: {e}", exc_info=True)
                await query.message.edit_text(
                    f"❌ **An error occurred during preparation:** `{e}`",
                    reply_markup=get_back_to_video_keyboard(),
                )
                return
            finally:
                CANCELLED_TASKS.discard(task_id)
                ACTIVE_PROGRESS.pop(task_id, None)

        streams_flat = get_all_streams_flat(probe_data)
        selected_indices = set()

        if user:
            USER_STATES[user.id] = {
                "action": "video_stream_extractor",
                "menu_msg_id": query.message.id,
                "media_msg_id": media_msg_id,
                "chat_id": query.message.chat.id,
                "temp_dir": temp_dir,
                "downloaded_path": downloaded,
                "probe_data": probe_data,
                "streams": streams_flat,
                "selected_indices": selected_indices,
                "file_name": orig_file_name,
            }

        extractor_text = format_stream_extractor_text(probe_data, selected_indices, fallback_name=orig_file_name)
        if len(extractor_text) > 4000:
            extractor_text = extractor_text[:3990] + "\n\n*... (truncated)*"

        await query.message.edit_text(
            text=extractor_text,
            reply_markup=get_stream_extractor_keyboard(streams_flat, selected_indices),
        )
        return

    elif data.startswith("vext_toggle_"):
        if not user or user.id not in USER_STATES:
            await query.answer("Session expired. Please start over.", show_alert=True)
            return

        state = USER_STATES[user.id]
        if state.get("action") != "video_stream_extractor":
            await query.answer("Invalid session state.", show_alert=True)
            return

        try:
            target_idx = int(data.split("vext_toggle_", 1)[1])
        except ValueError:
            await query.answer("Invalid stream index!", show_alert=True)
            return

        selected_indices = state.setdefault("selected_indices", set())
        if target_idx in selected_indices:
            selected_indices.remove(target_idx)
            await query.answer("Stream unmarked.")
        else:
            selected_indices.add(target_idx)
            await query.answer("Stream marked for extraction.")

        probe_data = state.get("probe_data", {})
        streams_flat = state.get("streams", [])
        orig_file_name = state.get("file_name", "video.mp4")

        extractor_text = format_stream_extractor_text(probe_data, selected_indices, fallback_name=orig_file_name)
        if len(extractor_text) > 4000:
            extractor_text = extractor_text[:3990] + "\n\n*... (truncated)*"

        await query.message.edit_text(
            text=extractor_text,
            reply_markup=get_stream_extractor_keyboard(streams_flat, selected_indices),
        )
        return

    elif data == "vext_apply":
        if not user or user.id not in USER_STATES:
            await query.answer("Session expired. Please start over.", show_alert=True)
            return

        state = USER_STATES[user.id]
        if state.get("action") != "video_stream_extractor":
            await query.answer("No active extraction session found.", show_alert=True)
            return

        selected_indices = state.get("selected_indices", set())
        if not selected_indices:
            await query.answer("Please select at least 1 stream to extract!", show_alert=True)
            return

        downloaded = state.get("downloaded_path")
        vid_temp_dir = state.get("temp_dir")
        saved_file_name = state.get("file_name", "video.mp4")
        streams_flat = state.get("streams", [])

        if not downloaded or not os.path.exists(downloaded):
            await query.answer("Downloaded file expired. Please start over.", show_alert=True)
            USER_STATES.pop(user.id, None)
            if vid_temp_dir:
                shutil.rmtree(vid_temp_dir, ignore_errors=True)
            return

        # Clear state as extraction begins
        USER_STATES.pop(user.id, None)
        task_id = f"{user.id}_{query.message.id}"
        CANCELLED_TASKS.discard(task_id)

        extract_list = sorted(list(selected_indices))
        total_extract = len(extract_list)
        base_name, orig_ext = os.path.splitext(saved_file_name)
        clean_base = re.sub(r'[\\/:*?"<>|]', '_', base_name)

        user_thumb = get_user_thumbnail(user.id)

        try:
            for item_num, s_idx in enumerate(extract_list, start=1):
                if task_id in CANCELLED_TASKS:
                    return

                # Find stream details
                st = next((s for s in streams_flat if s["index"] == s_idx), None)
                ctype = st["type"] if st else "audio"
                cname = st["codec_name"] if st else "aac"
                type_num = st.get("type_num", 1) if st else 1
                lang = st.get("language", "und") if st else "und"
                title = st.get("title", "") if st else ""

                ext = get_stream_extension(ctype, cname, orig_ext)
                type_prefix = "audio" if ctype == "audio" else ("sub" if ctype == "subtitle" else "video")
                lang_suffix = f"_{lang}" if lang and lang != "und" else ""
                out_filename = f"{clean_base}_{type_prefix}_{type_num}{lang_suffix}{ext}"
                out_path = os.path.join(vid_temp_dir, out_filename)

                await query.message.edit_text(
                    f"⚙️ **Extracting Stream {item_num}/{total_extract}...**\n\n"
                    f"• **Stream #{s_idx}:** {ctype.capitalize()} #{type_num} (`{cname}`)\n"
                    f"• **Output:** `{out_filename}`\n\n"
                    "Extracting with FFmpeg...",
                    reply_markup=get_cancel_process_keyboard(task_id),
                )

                success, err_msg = extract_single_stream(
                    input_path=downloaded,
                    output_path=out_path,
                    stream_index=s_idx,
                    codec_type=ctype,
                    codec_name=cname,
                )

                if task_id in CANCELLED_TASKS:
                    return

                if not success or not os.path.exists(out_path) or os.path.getsize(out_path) == 0:
                    short_err = err_msg if len(err_msg) < 300 else err_msg[-300:]
                    logger.warning(f"Failed to extract stream #{s_idx}: {short_err}")
                    continue

                out_size = os.path.getsize(out_path)
                if out_size > MAX_BOT_UPLOAD_SIZE:
                    ACTIVE_PROGRESS.pop(task_id, None)
                    await query.message.edit_text(
                        text=build_file_too_large_text(out_size),
                        reply_markup=get_back_to_video_keyboard(),
                    )
                    return

                tracker_up = ProgressTracker(
                    client=client,
                    message=query.message,
                    task_id=task_id,
                    action_name=f"📤 **Uploading Stream {item_num}/{total_extract}...**",
                    interval=8.0,
                    is_upload=True,
                )

                caption = (
                    f"📤 **Extracted Stream #{s_idx}** ({item_num}/{total_extract})\n\n"
                    f"• **Type:** `{ctype.capitalize()}` (`{cname}`)\n"
                    f"• **File:** `{out_filename}`\n"
                    f"• **Size:** `{humanbytes(out_size)}`"
                )
                if title:
                    caption += f"\n• **Title:** `{title}`"

                out_duration = get_media_duration(out_path)

                user_settings = get_user_settings(user.id)
                audio_as_file = user_settings.get("upload_audio") == "file"
                video_as_file = user_settings.get("upload_video") == "file"

                if ctype == "audio" and not audio_as_file:
                    await client.send_audio(
                        chat_id=query.message.chat.id,
                        audio=out_path,
                        caption=caption,
                        file_name=out_filename,
                        duration=out_duration,
                        thumb=user_thumb,
                        progress=tracker_up,
                    )
                elif ctype == "video" and not video_as_file:
                    vid_w, vid_h = get_video_dimensions(out_path)
                    await client.send_video(
                        chat_id=query.message.chat.id,
                        video=out_path,
                        caption=caption,
                        file_name=out_filename,
                        duration=out_duration,
                        width=vid_w or 0,
                        height=vid_h or 0,
                        thumb=user_thumb,
                        supports_streaming=True,
                        progress=tracker_up,
                    )
                else:
                    await client.send_document(
                        chat_id=query.message.chat.id,
                        document=out_path,
                        caption=caption,
                        file_name=out_filename,
                        thumb=user_thumb,
                        force_document=True,
                        progress=tracker_up,
                    )

            # Delete the menu message once all extractions are uploaded
            if task_id not in CANCELLED_TASKS:
                try:
                    await query.message.delete()
                except Exception:
                    pass

        except StopTransmission:
            logger.info(f"Stream extraction task {task_id} cancelled.")
            try:
                await query.message.edit_text(
                    "🚫 **Process Cancelled!**",
                    reply_markup=get_back_to_video_keyboard(),
                )
            except Exception:
                pass
        except Exception as e:
            logger.error(f"Error during stream extraction: {e}", exc_info=True)
            await query.message.edit_text(
                f"❌ **Error extracting streams:** `{e}`",
                reply_markup=get_back_to_video_keyboard(),
            )
        finally:
            CANCELLED_TASKS.discard(task_id)
            ACTIVE_PROGRESS.pop(task_id, None)
            if vid_temp_dir:
                shutil.rmtree(vid_temp_dir, ignore_errors=True)
        return

    elif data == "video_merge_audio":
        media_msg_id = query.message.reply_to_message_id or (
            query.message.reply_to_message.id if query.message.reply_to_message else None
        )
        if not media_msg_id:
            await query.answer("Original video message not found!", show_alert=True)
            return

        target = await get_fresh_media_message(client, query.message.chat.id, media_msg_id)
        if not target:
            await query.answer("Could not fetch media from Telegram!", show_alert=True)
            return

        media_type, info = detect_media(target)
        if media_type != "video":
            await query.answer("This file is not recognized as video!", show_alert=True)
            return

        orig_file_name = info.get("file_name", "video.mp4")

        if user:
            USER_STATES[user.id] = {
                "action": "video_merge_audio",
                "video_msg_id": media_msg_id,
                "menu_msg_id": query.message.id,
                "chat_id": query.message.chat.id,
                "file_name": orig_file_name,
                "audio_tracks": [],
            }

        await query.message.edit_text(
            text=build_video_merge_audio_text(orig_file_name, []),
            reply_markup=get_video_merge_audio_keyboard(0),
        )
        await query.answer()
        return

    elif data == "reset_video_audio_merge":
        if user and user.id in USER_STATES:
            state = USER_STATES[user.id]
            state["audio_tracks"] = []
            orig_file_name = state.get("file_name", "video.mp4")
            await query.message.edit_text(
                text=build_video_merge_audio_text(orig_file_name, []),
                reply_markup=get_video_merge_audio_keyboard(0),
            )
            await query.answer("Audio queue reset.")
            return
        await query.answer("Session expired. Please start over.", show_alert=True)
        return

    elif data == "start_video_audio_merge":
        if not user or user.id not in USER_STATES:
            await query.answer("Merge session expired. Please start over.", show_alert=True)
            return

        state = USER_STATES[user.id]
        if state.get("action") != "video_merge_audio":
            await query.answer("No active audio muxing session found.", show_alert=True)
            return

        tracks = list(state.get("audio_tracks", []))
        if not tracks:
            await query.answer("Please send at least 1 audio file first!", show_alert=True)
            return

        video_msg_id = state.get("video_msg_id")
        orig_video_name = state.get("file_name", "video.mp4")

        USER_STATES.pop(user.id, None)
        task_id = f"{user.id}_{query.message.id}"
        CANCELLED_TASKS.discard(task_id)

        await query.answer("Starting video audio merge process...")
        temp_dir = os.path.join("downloads", f"{user.id}_vmux_{int(time.time())}")
        os.makedirs(temp_dir, exist_ok=True)

        downloaded_audio_paths = []

        try:
            # 1. Download the target video
            await query.message.edit_text(
                f"📥 **Downloading Target Video...**\n\nStarting download: `{orig_video_name}`",
                reply_markup=get_cancel_process_keyboard(task_id),
            )

            tracker_vid = ProgressTracker(
                client=client,
                message=query.message,
                task_id=task_id,
                action_name="📥 **Downloading Target Video...**",
                interval=8.0,
                is_upload=False,
            )

            target_msg = await get_fresh_media_message(client, query.message.chat.id, video_msg_id)
            if not target_msg:
                await query.message.edit_text(
                    "❌ **Failed to fetch the target video from Telegram!**",
                    reply_markup=get_back_to_video_keyboard(),
                )
                return

            clean_vid_name = re.sub(r'[\\/:*?"<>|]', '_', orig_video_name)
            video_dest = os.path.join(temp_dir, f"source_{clean_vid_name}")

            downloaded_video = await download_media_with_retry(
                client=client,
                message=target_msg,
                file_name=video_dest,
                progress=tracker_vid,
            )

            if task_id in CANCELLED_TASKS:
                return

            if not downloaded_video or not os.path.exists(downloaded_video):
                await query.message.edit_text(
                    "❌ **Failed to download the target video!**",
                    reply_markup=get_back_to_video_keyboard(),
                )
                return

            # 2. Sequentially download each queued audio track
            for idx, tr in enumerate(tracks, start=1):
                if task_id in CANCELLED_TASKS:
                    return

                await query.message.edit_text(
                    f"📥 **Downloading Audio Track {idx}/{len(tracks)}...**\n\nStarting download: `{tr.get('file_name', 'audio')}`",
                    reply_markup=get_cancel_process_keyboard(task_id),
                )

                tracker_audio = ProgressTracker(
                    client=client,
                    message=query.message,
                    task_id=task_id,
                    action_name=f"📥 **Downloading Audio Track {idx}/{len(tracks)}...**",
                    interval=8.0,
                    is_upload=False,
                )

                tr_msg = await get_fresh_media_message(client, query.message.chat.id, tr["msg_id"])
                if not tr_msg:
                    await query.message.edit_text(
                        f"❌ **Failed to fetch audio track {idx} from Telegram!**",
                        reply_markup=get_back_to_video_keyboard(),
                    )
                    return

                clean_tr_name = re.sub(r'[\\/:*?"<>|]', '_', tr.get("file_name", f"track_{idx}.mp3"))
                audio_dest = os.path.join(temp_dir, f"audio_{idx}_{clean_tr_name}")

                downloaded_audio = await download_media_with_retry(
                    client=client,
                    message=tr_msg,
                    file_name=audio_dest,
                    progress=tracker_audio,
                )

                if task_id in CANCELLED_TASKS:
                    return

                if not downloaded_audio or not os.path.exists(downloaded_audio):
                    await query.message.edit_text(
                        f"❌ **Failed to download audio track {idx} (`{tr.get('file_name')}`)!**",
                        reply_markup=get_back_to_video_keyboard(),
                    )
                    return

                downloaded_audio_paths.append(downloaded_audio)

            if task_id in CANCELLED_TASKS:
                return

            # 3. Mux audio tracks into the video using FFmpeg stream copy
            base_name, orig_ext = os.path.splitext(orig_video_name)
            if not orig_ext:
                orig_ext = ".mp4"
            output_filename = f"{clean_vid_name.rsplit('.', 1)[0]}_muxed{orig_ext}"
            output_file = os.path.join(temp_dir, output_filename)

            await query.message.edit_text(
                f"⚙️ **Muxing {len(downloaded_audio_paths)} Audio Track(s) into Video...**\n\n"
                "• New audios mapped as primary tracks.\n"
                "• Original video audio placed as last track.\n"
                "Processing with FFmpeg (stream copy, zero quality loss)...",
                reply_markup=get_cancel_process_keyboard(task_id),
            )

            success, err_msg = merge_audio_into_video(
                video_path=downloaded_video,
                audio_paths=downloaded_audio_paths,
                output_path=output_file,
                has_orig_audio=True,
            )

            if task_id in CANCELLED_TASKS:
                return

            if not success or not os.path.exists(output_file) or os.path.getsize(output_file) == 0:
                short_err = err_msg if len(err_msg) < 400 else err_msg[-400:]
                await query.message.edit_text(
                    f"❌ **FFmpeg Audio Muxing Failed!**\n\n```text\n{short_err}\n```",
                    reply_markup=get_back_to_video_keyboard(),
                )
                return

            out_size = os.path.getsize(output_file)
            if out_size > MAX_BOT_UPLOAD_SIZE:
                ACTIVE_PROGRESS.pop(task_id, None)
                await query.message.edit_text(
                    text=build_file_too_large_text(out_size),
                    reply_markup=get_back_to_video_keyboard(),
                )
                return

            out_duration = get_media_duration(output_file) or get_media_duration(downloaded_video)
            vid_w, vid_h = get_video_dimensions(output_file)
            user_thumb = get_user_thumbnail(user.id)

            await query.message.edit_text(
                "📤 **Uploading Video with New Audio Tracks...**\n\nPreparing upload to Telegram...",
                reply_markup=get_cancel_process_keyboard(task_id),
            )

            tracker_up = ProgressTracker(
                client=client,
                message=query.message,
                task_id=task_id,
                action_name="📤 **Uploading Video with New Audio Tracks...**",
                interval=8.0,
                is_upload=True,
            )

            caption = (
                f"🎵 **Audio Tracks Merged Successfully!**\n\n"
                f"• **File:** `{output_filename}`\n"
                f"• **Added Tracks:** `{len(downloaded_audio_paths)}`\n"
                f"• **Duration:** `{format_duration(out_duration)}`\n"
                f"• **Size:** `{humanbytes(out_size)}`"
            )

            user_settings = get_user_settings(user.id)
            if user_settings.get("upload_video") != "file":
                vid_info = target_msg.video if target_msg and target_msg.video else None
                if not vid_w and vid_info:
                    vid_w = vid_info.width or 0
                    vid_h = vid_info.height or 0
                await client.send_video(
                    chat_id=query.message.chat.id,
                    video=output_file,
                    caption=caption,
                    file_name=output_filename,
                    duration=out_duration or (vid_info.duration if vid_info else 0),
                    width=vid_w or 0,
                    height=vid_h or 0,
                    thumb=user_thumb,
                    supports_streaming=True,
                    progress=tracker_up,
                )
            else:
                await client.send_document(
                    chat_id=query.message.chat.id,
                    document=output_file,
                    caption=caption,
                    file_name=output_filename,
                    thumb=user_thumb,
                    force_document=True,
                    progress=tracker_up,
                )

            # Delete the menu message
            if task_id not in CANCELLED_TASKS:
                try:
                    await query.message.delete()
                except Exception:
                    pass

        except StopTransmission:
            logger.info(f"Video audio merge task {task_id} cancelled.")
            try:
                await query.message.edit_text(
                    "🚫 **Process Cancelled!**",
                    reply_markup=get_back_to_video_keyboard(),
                )
            except Exception:
                pass
        except Exception as e:
            logger.error(f"Error during video audio merge: {e}", exc_info=True)
            await query.message.edit_text(
                f"❌ **An error occurred during audio merge:** `{e}`",
                reply_markup=get_back_to_video_keyboard(),
            )
        finally:
            CANCELLED_TASKS.discard(task_id)
            ACTIVE_PROGRESS.pop(task_id, None)
            shutil.rmtree(temp_dir, ignore_errors=True)
        return


    elif data == "video_trimmer":
        if user:
            USER_STATES.pop(user.id, None)
        trimmer_text = (
            "✂️ **Video Trimmer Options**\n\n"
            "Please choose your preferred trimming method:\n\n"
            "• ⚡ **Fast Copy:** Stream copy mode. Ultra-fast cut without re-encoding, 100% original quality preserved.\n\n"
            "• 🎯 **Frame Accuracy:** Precise cut down to frame/millisecond. Re-encodes boundary frames for exact cut.\n\n"
            "Select an option below:"
        )
        await query.message.edit_text(
            text=trimmer_text,
            reply_markup=get_video_trimmer_keyboard(),
        )
        await query.answer()
        return

    elif data == "video_trim_mode_fast":
        media_msg_id = query.message.reply_to_message_id or (
            query.message.reply_to_message.id if query.message.reply_to_message else None
        )
        if user:
            USER_STATES[user.id] = {
                "action": "video_trim_fast",
                "menu_msg_id": query.message.id,
                "media_msg_id": media_msg_id,
                "chat_id": query.message.chat.id,
            }

        await query.message.edit_text(
            text=(
                "⚡ **Fast Copy Mode Selected**\n\n"
                "Stream copy mode cuts video in seconds with zero quality loss.\n\n"
                "Please type the start and end timestamp in chat:\n"
                "• Format: `HH:MM:SS - HH:MM:SS` or `MM:SS - MM:SS`\n"
                "💡 **Example:** `00:15 - 01:45`\n\n"
                "*(Press below to switch mode or go back)*"
            ),
            reply_markup=get_back_to_video_trimmer_keyboard(),
        )
        await query.answer()
        return

    elif data == "video_trim_mode_accurate":
        media_msg_id = query.message.reply_to_message_id or (
            query.message.reply_to_message.id if query.message.reply_to_message else None
        )
        if user:
            USER_STATES[user.id] = {
                "action": "video_trim_accurate",
                "menu_msg_id": query.message.id,
                "media_msg_id": media_msg_id,
                "chat_id": query.message.chat.id,
            }

        await query.message.edit_text(
            text=(
                "🎯 **Frame Accuracy Mode Selected**\n\n"
                "Millisecond-accurate cutting with frame boundary precision.\n\n"
                "Please type the exact timestamps in chat:\n"
                "• Format: `HH:MM:SS.xxx - HH:MM:SS.xxx` or `MM:SS - MM:SS`\n"
                "💡 **Example:** `00:15.500 - 01:45.250`\n\n"
                "*(Press below to switch mode or go back)*"
            ),
            reply_markup=get_back_to_video_trimmer_keyboard(),
        )
        await query.answer()
        return

    elif data == "video_merger":
        media_msg_id = query.message.reply_to_message_id or (
            query.message.reply_to_message.id if query.message.reply_to_message else None
        )
        if not media_msg_id:
            await query.answer("Original video message not found!", show_alert=True)
            return

        target = await get_fresh_media_message(client, query.message.chat.id, media_msg_id)
        if not target:
            await query.answer("Could not fetch media from Telegram!", show_alert=True)
            return

        media_type, info = detect_media(target)
        if media_type != "video":
            await query.answer("This file is not recognized as video!", show_alert=True)
            return

        initial_video = {
            "msg_id": media_msg_id,
            "file_name": info.get("file_name", "Video 1.mp4"),
            "duration": info.get("duration", 0),
            "file_size": info.get("file_size", 0),
        }
        if user:
            USER_STATES[user.id] = {
                "action": "video_merger",
                "menu_msg_id": query.message.id,
                "chat_id": query.message.chat.id,
                "videos": [initial_video],
            }

        await query.message.edit_text(
            text=build_video_merger_text([initial_video]),
            reply_markup=get_video_merger_keyboard(1),
        )
        await query.answer()
        return

    elif data == "reset_video_merger":
        if user and user.id in USER_STATES:
            state = USER_STATES[user.id]
            videos = state.get("videos", [])
            if videos:
                state["videos"] = [videos[0]]
                await query.message.edit_text(
                    text=build_video_merger_text(state["videos"]),
                    reply_markup=get_video_merger_keyboard(1),
                )
                await query.answer("Queue reset to initial video.", show_alert=False)
                return
        await query.answer("Session expired. Please start over.", show_alert=True)
        return

    elif data == "start_video_merge":
        if not user or user.id not in USER_STATES:
            await query.answer("Merge session expired. Please start over.", show_alert=True)
            return

        state = USER_STATES[user.id]
        if state.get("action") != "video_merger":
            await query.answer("No active video merge session found.", show_alert=True)
            return

        videos = list(state.get("videos", []))
        if len(videos) < 2:
            await query.answer("Please send at least 2 video files to merge!", show_alert=True)
            return

        USER_STATES.pop(user.id, None)
        task_id = f"{user.id}_{query.message.id}"
        CANCELLED_TASKS.discard(task_id)

        await query.answer("Starting Fast Copy video merge...")
        temp_dir = os.path.join("downloads", f"{user.id}_vmerge_{int(time.time())}")
        os.makedirs(temp_dir, exist_ok=True)

        downloaded_paths = []
        try:
            # 1. Sequentially download each queued video
            for idx, v in enumerate(videos, start=1):
                if task_id in CANCELLED_TASKS:
                    return

                await query.message.edit_text(
                    f"📥 **Downloading Video {idx}/{len(videos)}...**\n\nStarting download: `{v.get('file_name', 'video')}`",
                    reply_markup=get_cancel_process_keyboard(task_id),
                )

                tracker_down = ProgressTracker(
                    client=client,
                    message=query.message,
                    task_id=task_id,
                    action_name=f"📥 **Downloading Video {idx}/{len(videos)}...**",
                    interval=8.0,
                    is_upload=False,
                )

                target_msg = await get_fresh_media_message(client, query.message.chat.id, v["msg_id"])
                if not target_msg:
                    await query.message.edit_text(
                        f"❌ **Failed to fetch video {idx} from Telegram!**\nOne of the queued videos may have been deleted.",
                        reply_markup=get_back_to_video_keyboard(),
                    )
                    return

                clean_v_name = re.sub(r'[\\/:*?"<>|]', '_', v.get("file_name", f"video_{idx}.mp4"))
                target_dest = os.path.join(temp_dir, f"video_{idx}_{clean_v_name}")

                downloaded = await download_media_with_retry(
                    client=client,
                    message=target_msg,
                    file_name=target_dest,
                    progress=tracker_down,
                )

                if task_id in CANCELLED_TASKS:
                    return

                if not downloaded or not os.path.exists(downloaded):
                    await query.message.edit_text(
                        f"❌ **Failed to download video {idx} (`{v.get('file_name')}`)!**",
                        reply_markup=get_back_to_video_keyboard(),
                    )
                    return

                downloaded_paths.append(downloaded)

            if task_id in CANCELLED_TASKS:
                return

            base_name = os.path.splitext(videos[0].get("file_name", "video"))[0]
            clean_base = re.sub(r'[\\/:*?"<>|]', '_', base_name)
            output_filename = f"{clean_base}_merged.mp4"
            output_file = os.path.join(temp_dir, output_filename)

            total_expected_duration = sum(v.get("duration", 0) for v in videos)

            await query.message.edit_text(
                f"⚙️ **Merging {len(downloaded_paths)} Videos (Fast Copy)...**\n\n"
                "Concatenating with FFmpeg stream-copy (zero quality loss)...",
                reply_markup=get_cancel_process_keyboard(task_id),
            )

            # 2. Fast merge videos using Concat demuxer
            success, err_msg = fast_merge_video_files(downloaded_paths, output_file)

            if task_id in CANCELLED_TASKS:
                return

            if not success or not os.path.exists(output_file) or os.path.getsize(output_file) == 0:
                short_err = err_msg if len(err_msg) < 400 else err_msg[-400:]
                await query.message.edit_text(
                    f"❌ **Fast Copy Video Merge Failed!**\n\n```text\n{short_err}\n```\n"
                    "*(Note: Fast Copy requires identical codecs and resolutions)*",
                    reply_markup=get_back_to_video_keyboard(),
                )
                return

            out_duration = get_media_duration(output_file)
            if out_duration == 0 and total_expected_duration > 0:
                out_duration = int(total_expected_duration)

            out_size = os.path.getsize(output_file)
            if out_size > MAX_BOT_UPLOAD_SIZE:
                ACTIVE_PROGRESS.pop(task_id, None)
                await query.message.edit_text(
                    text=build_file_too_large_text(out_size),
                    reply_markup=get_back_to_video_keyboard(),
                )
                return

            user_thumb = get_user_thumbnail(user.id)
            vid_w, vid_h = get_video_dimensions(output_file)

            await query.message.edit_text(
                "📤 **Uploading Merged Video...**\n\nPreparing upload to Telegram...",
                reply_markup=get_cancel_process_keyboard(task_id),
            )

            tracker_up = ProgressTracker(
                client=client,
                message=query.message,
                task_id=task_id,
                action_name="📤 **Uploading Merged Video...**",
                interval=8.0,
                is_upload=True,
            )

            caption = (
                f"🔀 **Video Merge Completed!** ({len(videos)} Videos)\n\n"
                f"• **File Name:** `{output_filename}`\n"
                f"• **Duration:** `{format_duration(out_duration)}`\n"
                f"• **Size:** `{humanbytes(out_size)}`\n"
                "• **Method:** `⚡ Fast Copy (Lossless)`"
            )

            # Use first video's info for width/height if ffprobe couldn't extract
            if not vid_w:
                first_msg = await get_fresh_media_message(client, query.message.chat.id, videos[0]["msg_id"])
                if first_msg and first_msg.video:
                    vid_w = first_msg.video.width or 0
                    vid_h = first_msg.video.height or 0

            user_settings = get_user_settings(user.id)
            if user_settings.get("upload_video") != "file":
                await client.send_video(
                    chat_id=query.message.chat.id,
                    video=output_file,
                    caption=caption,
                    duration=out_duration,
                    width=vid_w or 0,
                    height=vid_h or 0,
                    file_name=output_filename,
                    thumb=user_thumb,
                    supports_streaming=True,
                    progress=tracker_up,
                )
            else:
                await client.send_document(
                    chat_id=query.message.chat.id,
                    document=output_file,
                    caption=caption,
                    file_name=output_filename,
                    thumb=user_thumb,
                    force_document=True,
                    progress=tracker_up,
                )

            if task_id not in CANCELLED_TASKS:
                try:
                    await query.message.delete()
                except Exception:
                    pass

        except StopTransmission:
            logger.info(f"Video merge task {task_id} cancelled.")
            try:
                await query.message.edit_text(
                    "🚫 **Process Cancelled!**",
                    reply_markup=get_back_to_video_keyboard(),
                )
            except Exception:
                pass
        except Exception as e:
            logger.error(f"Error during video merge: {e}", exc_info=True)
            await query.message.edit_text(
                f"❌ **An error occurred during video merge:** `{e}`",
                reply_markup=get_back_to_video_keyboard(),
            )
        finally:
            CANCELLED_TASKS.discard(task_id)
            ACTIVE_PROGRESS.pop(task_id, None)
            shutil.rmtree(temp_dir, ignore_errors=True)
        return


    elif data == "video_merge_subtitle":
        media_msg_id = query.message.reply_to_message_id or (
            query.message.reply_to_message.id if query.message.reply_to_message else None
        )
        if not media_msg_id:
            await query.answer("Original video message not found!", show_alert=True)
            return

        target = await get_fresh_media_message(client, query.message.chat.id, media_msg_id)
        if not target:
            await query.answer("Could not fetch media from Telegram!", show_alert=True)
            return

        media_type, info = detect_media(target)
        if media_type != "video":
            await query.answer("This file is not recognized as video!", show_alert=True)
            return

        orig_file_name = info.get("file_name", "video.mp4")

        if user:
            USER_STATES[user.id] = {
                "action": "video_merge_subtitle",
                "video_msg_id": media_msg_id,
                "menu_msg_id": query.message.id,
                "chat_id": query.message.chat.id,
                "file_name": orig_file_name,
                "subtitle_tracks": [],
            }

        await query.message.edit_text(
            text=build_video_merge_subtitle_text(orig_file_name, []),
            reply_markup=get_video_merge_subtitle_keyboard(0),
        )
        await query.answer()
        return

    elif data == "reset_video_subtitle_merge":
        if user and user.id in USER_STATES:
            state = USER_STATES[user.id]
            state["subtitle_tracks"] = []
            orig_file_name = state.get("file_name", "video.mp4")
            await query.message.edit_text(
                text=build_video_merge_subtitle_text(orig_file_name, []),
                reply_markup=get_video_merge_subtitle_keyboard(0),
            )
            await query.answer("Subtitle queue reset.")
            return
        await query.answer("Session expired. Please start over.", show_alert=True)
        return

    elif data == "start_video_subtitle_merge":
        if not user or user.id not in USER_STATES:
            await query.answer("Merge session expired. Please start over.", show_alert=True)
            return

        state = USER_STATES[user.id]
        if state.get("action") != "video_merge_subtitle":
            await query.answer("No active subtitle muxing session found.", show_alert=True)
            return

        tracks = list(state.get("subtitle_tracks", []))
        if not tracks:
            await query.answer("Please send at least 1 subtitle file first!", show_alert=True)
            return

        video_msg_id = state.get("video_msg_id")
        orig_video_name = state.get("file_name", "video.mp4")

        USER_STATES.pop(user.id, None)
        task_id = f"{user.id}_{query.message.id}"
        CANCELLED_TASKS.discard(task_id)

        await query.answer("Starting video subtitle merge process...")
        temp_dir = os.path.join("downloads", f"{user.id}_vsub_{int(time.time())}")
        os.makedirs(temp_dir, exist_ok=True)

        downloaded_sub_paths = []

        try:
            # 1. Download the target video
            await query.message.edit_text(
                f"📥 **Downloading Target Video...**\n\nStarting download: `{orig_video_name}`",
                reply_markup=get_cancel_process_keyboard(task_id),
            )

            tracker_vid = ProgressTracker(
                client=client,
                message=query.message,
                task_id=task_id,
                action_name="📥 **Downloading Target Video...**",
                interval=8.0,
                is_upload=False,
            )

            target_msg = await get_fresh_media_message(client, query.message.chat.id, video_msg_id)
            if not target_msg:
                await query.message.edit_text(
                    "❌ **Failed to fetch the target video from Telegram!**",
                    reply_markup=get_back_to_video_keyboard(),
                )
                return

            clean_vid_name = re.sub(r'[\\/:*?"<>|]', '_', orig_video_name)
            video_dest = os.path.join(temp_dir, f"source_{clean_vid_name}")

            downloaded_video = await download_media_with_retry(
                client=client,
                message=target_msg,
                file_name=video_dest,
                progress=tracker_vid,
            )

            if task_id in CANCELLED_TASKS:
                return

            if not downloaded_video or not os.path.exists(downloaded_video):
                await query.message.edit_text(
                    "❌ **Failed to download the target video!**",
                    reply_markup=get_back_to_video_keyboard(),
                )
                return

            # 2. Sequentially download each queued subtitle track
            for idx, tr in enumerate(tracks, start=1):
                if task_id in CANCELLED_TASKS:
                    return

                await query.message.edit_text(
                    f"📥 **Downloading Subtitle Track {idx}/{len(tracks)}...**\n\nStarting download: `{tr.get('file_name', 'sub')}`",
                    reply_markup=get_cancel_process_keyboard(task_id),
                )

                tracker_sub = ProgressTracker(
                    client=client,
                    message=query.message,
                    task_id=task_id,
                    action_name=f"📥 **Downloading Subtitle Track {idx}/{len(tracks)}...**",
                    interval=8.0,
                    is_upload=False,
                )

                tr_msg = await get_fresh_media_message(client, query.message.chat.id, tr["msg_id"])
                if not tr_msg:
                    await query.message.edit_text(
                        f"❌ **Failed to fetch subtitle track {idx} from Telegram!**",
                        reply_markup=get_back_to_video_keyboard(),
                    )
                    return

                clean_tr_name = re.sub(r'[\\/:*?"<>|]', '_', tr.get("file_name", f"sub_{idx}.srt"))
                sub_dest = os.path.join(temp_dir, f"sub_{idx}_{clean_tr_name}")

                downloaded_sub = await download_media_with_retry(
                    client=client,
                    message=tr_msg,
                    file_name=sub_dest,
                    progress=tracker_sub,
                )

                if task_id in CANCELLED_TASKS:
                    return

                if not downloaded_sub or not os.path.exists(downloaded_sub):
                    await query.message.edit_text(
                        f"❌ **Failed to download subtitle track {idx} (`{tr.get('file_name')}`)!**",
                        reply_markup=get_back_to_video_keyboard(),
                    )
                    return

                downloaded_sub_paths.append(downloaded_sub)

            if task_id in CANCELLED_TASKS:
                return

            # 3. Mux subtitle tracks into the video using FFmpeg stream copy
            base_name, orig_ext = os.path.splitext(orig_video_name)
            if not orig_ext:
                orig_ext = ".mp4"
            output_filename = f"{clean_vid_name.rsplit('.', 1)[0]}_subbed{orig_ext}"
            output_file = os.path.join(temp_dir, output_filename)

            await query.message.edit_text(
                f"⚙️ **Muxing {len(downloaded_sub_paths)} Subtitle Track(s) into Video...**\n\n"
                "• New subtitles mapped as primary tracks.\n"
                "• Original video subtitles (if any) kept.\n"
                "Processing with FFmpeg (stream copy, zero quality loss)...",
                reply_markup=get_cancel_process_keyboard(task_id),
            )

            success, final_output_file, err_msg = merge_subtitles_into_video(
                video_path=downloaded_video,
                subtitle_paths=downloaded_sub_paths,
                output_path=output_file,
                has_orig_sub=True,
            )

            if task_id in CANCELLED_TASKS:
                return

            if not success or not os.path.exists(final_output_file) or os.path.getsize(final_output_file) == 0:
                short_err = err_msg if len(err_msg) < 400 else err_msg[-400:]
                await query.message.edit_text(
                    f"❌ **FFmpeg Subtitle Muxing Failed!**\n\n```text\n{short_err}\n```",
                    reply_markup=get_back_to_video_keyboard(),
                )
                return

            out_size = os.path.getsize(final_output_file)
            if out_size > MAX_BOT_UPLOAD_SIZE:
                ACTIVE_PROGRESS.pop(task_id, None)
                await query.message.edit_text(
                    text=build_file_too_large_text(out_size),
                    reply_markup=get_back_to_video_keyboard(),
                )
                return

            out_filename = os.path.basename(final_output_file)
            out_duration = get_media_duration(final_output_file) or get_media_duration(downloaded_video)
            vid_w, vid_h = get_video_dimensions(final_output_file)
            user_thumb = get_user_thumbnail(user.id)

            await query.message.edit_text(
                "📤 **Uploading Video with New Subtitle Tracks...**\n\nPreparing upload to Telegram...",
                reply_markup=get_cancel_process_keyboard(task_id),
            )

            tracker_up = ProgressTracker(
                client=client,
                message=query.message,
                task_id=task_id,
                action_name="📤 **Uploading Video with New Subtitle Tracks...**",
                interval=8.0,
                is_upload=True,
            )

            caption = (
                f"💬 **Subtitle Tracks Merged Successfully!**\n\n"
                f"• **File:** `{out_filename}`\n"
                f"• **Added Subtitles:** `{len(downloaded_sub_paths)}` track(s)\n"
                f"• **Duration:** `{format_duration(out_duration)}`\n"
                f"• **Size:** `{humanbytes(out_size)}`"
            )

            user_settings = get_user_settings(user.id)
            if user_settings.get("upload_video") != "file":
                vid_info = target_msg.video if target_msg and target_msg.video else None
                if not vid_w and vid_info:
                    vid_w = vid_info.width or 0
                    vid_h = vid_info.height or 0
                await client.send_video(
                    chat_id=query.message.chat.id,
                    video=final_output_file,
                    caption=caption,
                    file_name=out_filename,
                    duration=out_duration or (vid_info.duration if vid_info else 0),
                    width=vid_w or 0,
                    height=vid_h or 0,
                    thumb=user_thumb,
                    supports_streaming=True,
                    progress=tracker_up,
                )
            else:
                await client.send_document(
                    chat_id=query.message.chat.id,
                    document=final_output_file,
                    caption=caption,
                    file_name=out_filename,
                    thumb=user_thumb,
                    force_document=True,
                    progress=tracker_up,
                )

            if task_id not in CANCELLED_TASKS:
                try:
                    await query.message.delete()
                except Exception:
                    pass

        except StopTransmission:
            logger.info(f"Video subtitle merge task {task_id} cancelled.")
            try:
                await query.message.edit_text(
                    "🚫 **Process Cancelled!**",
                    reply_markup=get_back_to_video_keyboard(),
                )
            except Exception:
                pass
        except Exception as e:
            logger.error(f"Error during video subtitle merge: {e}", exc_info=True)
            await query.message.edit_text(
                f"❌ **An error occurred during video subtitle merge:** `{e}`",
                reply_markup=get_back_to_video_keyboard(),
            )
        finally:
            CANCELLED_TASKS.discard(task_id)
            ACTIVE_PROGRESS.pop(task_id, None)
            shutil.rmtree(temp_dir, ignore_errors=True)
        return

    elif data == "video_ffmpeg":
        media_msg_id = query.message.reply_to_message_id or (
            query.message.reply_to_message.id if query.message.reply_to_message else None
        )
        if user:
            USER_STATES[user.id] = {
                "action": "video_ffmpeg",
                "menu_msg_id": query.message.id,
                "media_msg_id": media_msg_id,
                "chat_id": query.message.chat.id,
            }

        ffmpeg_info_text = (
            "💻 **Custom Video FFmpeg Command Mode**\n\n"
            "Please type your custom FFmpeg arguments or command directly in chat!\n\n"
            "💡 **Popular Examples:**\n"
            "• `-vf \"scale=1280:720\"` *(Downscale video to 720p HD)*\n"
            "• `-c:v libx264 -crf 23 -preset fast` *(Re-encode with H.264 compression)*\n"
            "• `-an` *(Remove all audio tracks / mute video)*\n"
            "• `-vf \"setpts=0.5*PTS\" -af \"atempo=2.0\"` *(Speed up 2x with audio)*\n"
            "• `-vf \"transpose=1\"` *(Rotate video 90 degrees clockwise)*\n"
            "• Or full syntax: `ffmpeg -i in.mp4 -vf scale=720:-1 out.mp4`\n\n"
            "*(Input and output paths will be mapped automatically)*"
        )
        await query.message.edit_text(
            text=ffmpeg_info_text,
            reply_markup=get_back_to_video_keyboard(),
        )
        await query.answer()
        return

    elif data == "video_ffprobe":
        media_msg_id = query.message.reply_to_message_id or (
            query.message.reply_to_message.id if query.message.reply_to_message else None
        )
        if not media_msg_id:
            await query.answer("Original video message not found!", show_alert=True)
            return

        target = await get_fresh_media_message(client, query.message.chat.id, media_msg_id)
        if not target:
            await query.answer("Could not fetch media from Telegram!", show_alert=True)
            return

        media_type, info = detect_media(target)
        if media_type != "video":
            await query.answer("This file is not recognized as video!", show_alert=True)
            return

        # Check existing state for pre-downloaded file
        existing_state = USER_STATES.get(user.id, {}) if user else {}
        existing_downloaded = existing_state.get("downloaded_path")
        existing_probe = existing_state.get("probe_data")
        orig_file_name = info.get("file_name", "video.mp4")

        if existing_downloaded and os.path.exists(existing_downloaded) and existing_probe:
            analysis_text = format_ffprobe_video_info(existing_probe, fallback_name=orig_file_name)
            if len(analysis_text) > 4000:
                analysis_text = analysis_text[:3990] + "\n\n*... (truncated)*"
            await query.message.edit_text(
                text=analysis_text,
                reply_markup=get_back_to_video_keyboard(),
            )
            await query.answer()
            return

        task_id = f"{user.id}_{query.message.id}"
        CANCELLED_TASKS.discard(task_id)

        await query.answer("Starting FFprobe video analysis...")
        await query.message.edit_text(
            "📥 **Downloading Video for FFprobe Analysis...**\n\nStarting download, please wait...",
            reply_markup=get_cancel_process_keyboard(task_id),
        )

        temp_dir = os.path.join("downloads", f"{user.id}_vffprobe_{int(time.time())}")
        os.makedirs(temp_dir, exist_ok=True)

        try:
            tracker_down = ProgressTracker(
                client=client,
                message=query.message,
                task_id=task_id,
                action_name="📥 **Downloading Video for FFprobe Analysis...**",
                interval=8.0,
                is_upload=False,
            )

            dest_file = os.path.join(temp_dir, re.sub(r'[\\/:*?"<>|]', '_', orig_file_name))
            downloaded = await download_media_with_retry(
                client=client,
                message=target,
                file_name=dest_file,
                progress=tracker_down,
            )

            if task_id in CANCELLED_TASKS:
                return

            if not downloaded or not os.path.exists(downloaded):
                await query.message.edit_text(
                    "❌ **Failed to download the video file!**",
                    reply_markup=get_back_to_video_keyboard(),
                )
                return

            await query.message.edit_text(
                "⚙️ **Analyzing Video with FFprobe...**\n\nExtracting detailed streams, codecs & metadata...",
                reply_markup=get_cancel_process_keyboard(task_id),
            )

            probe_data = get_audio_ffprobe_info(downloaded)
            if not probe_data:
                await query.message.edit_text(
                    "❌ **FFprobe failed to inspect the video file!**",
                    reply_markup=get_back_to_video_keyboard(),
                )
                return

            analysis_text = format_ffprobe_video_info(probe_data, fallback_name=orig_file_name)
            if len(analysis_text) > 4000:
                analysis_text = analysis_text[:3990] + "\n\n*... (truncated)*"

            await query.message.edit_text(
                text=analysis_text,
                reply_markup=get_back_to_video_keyboard(),
            )

        except StopTransmission:
            logger.info(f"Video FFprobe task {task_id} was stopped by user.")
        except Exception as e:
            logger.error(f"Error during video FFprobe analysis: {e}", exc_info=True)
            try:
                await query.message.edit_text(
                    f"❌ **An error occurred during FFprobe analysis:** `{e}`",
                    reply_markup=get_back_to_video_keyboard(),
                )
            except Exception:
                pass
        finally:
            CANCELLED_TASKS.discard(task_id)
            ACTIVE_PROGRESS.pop(task_id, None)
            shutil.rmtree(temp_dir, ignore_errors=True)
        return


    elif data == "video_menu_back":
        if user:
            state = USER_STATES.pop(user.id, None)
            if state and state.get("temp_dir"):
                shutil.rmtree(state["temp_dir"], ignore_errors=True)
        await query.message.edit_text(
            text=build_video_menu_text(query.message),
            reply_markup=get_video_keyboard(),
        )
        await query.answer()
        return

    # --- FILE MENU IN-PLACE ACTIONS ---
    elif data == "file_rename":
        await query.message.edit_text(
            text=(
                "✏️ **File Rename Mode**\n\n"
                "Please send the new file name with extension (e.g. `Document.pdf`).\n\n"
                "*(Press below to return)*"
            ),
            reply_markup=get_back_to_file_keyboard(),
        )
        await query.answer()
        return

    elif data == "file_as_video":
        await query.message.edit_text(
            text=build_video_menu_text(query.message),
            reply_markup=get_video_keyboard(),
        )
        await query.answer()
        return

    elif data == "file_as_audio":
        await query.message.edit_text(
            text=build_audio_menu_text(query.message),
            reply_markup=get_audio_keyboard(),
        )
        await query.answer()
        return

    elif data == "file_menu_back":
        await query.message.edit_text(
            text=build_file_menu_text(query.message),
            reply_markup=get_file_keyboard(),
        )
        await query.answer()
        return

    await query.answer()


@app.on_message(filters.text & filters.private & ~filters.command(["start", "help", "about", "showthumb", "delthumb", "settings"]))
async def text_input_handler(client: Client, message: Message):
    """
    Handles user text inputs when waiting for audio rename, trimming intervals, or custom FFmpeg commands.
    Maintains Single-Message navigation by updating the original menu message.
    """
    user_id = message.from_user.id if message.from_user else 0
    if user_id not in USER_STATES:
        return

    state = USER_STATES[user_id]
    action = state.get("action")
    chat_id = state.get("chat_id")
    menu_msg_id = state.get("menu_msg_id")
    media_msg_id = state.get("media_msg_id")

    # Fetch the menu message
    menu_msg = await get_fresh_media_message(client, chat_id, menu_msg_id)
    if not menu_msg:
        USER_STATES.pop(user_id, None)
        return

    # Delete the user's typed input text message immediately to keep chat clean (Single-Message Rule)
    try:
        await message.delete()
    except Exception:
        pass

    # Fetch fresh original media message
    target = await get_fresh_media_message(client, chat_id, media_msg_id)
    if not target:
        back_kb = get_back_to_video_keyboard() if action.startswith("video") else get_back_to_audio_keyboard()
        await menu_msg.edit_text(
            "❌ **Original media message not found!**\nPlease send the file again.",
            reply_markup=back_kb,
        )
        USER_STATES.pop(user_id, None)
        return

    media_type, info = detect_media(target)
    if action.startswith("video"):
        orig_name = info.get("file_name", "video.mp4")
        _, orig_ext = os.path.splitext(orig_name)
        if not orig_ext:
            orig_ext = ".mp4"
    else:
        orig_name = info.get("file_name", "audio.mp3")
        _, orig_ext = os.path.splitext(orig_name)
        if not orig_ext:
            orig_ext = ".mp3"

    task_id = f"{user_id}_{menu_msg_id}"
    CANCELLED_TASKS.discard(task_id)

    # 1. AUDIO RENAME HANDLING
    if action == "audio_rename":
        USER_STATES.pop(user_id, None)
        raw_name = message.text.strip()
        # Add extension if omitted
        if not os.path.splitext(raw_name)[1]:
            new_file_name = f"{raw_name}{orig_ext}"
        else:
            new_file_name = raw_name

        temp_dir = os.path.join("downloads", f"{user_id}_rename_{int(time.time())}")
        os.makedirs(temp_dir, exist_ok=True)

        try:
            tracker_down = ProgressTracker(
                client=client,
                message=menu_msg,
                task_id=task_id,
                action_name="📥 **Downloading Audio for Rename...**",
                interval=8.0,
                is_upload=False,
            )

            await menu_msg.edit_text(
                "📥 **Downloading Audio...**\n\nStarting download for rename...",
                reply_markup=get_cancel_process_keyboard(task_id),
            )

            downloaded = await download_media_with_retry(
                client=client,
                message=target,
                file_name=os.path.join(temp_dir, orig_name),
                progress=tracker_down,
            )

            if task_id in CANCELLED_TASKS:
                return

            if not downloaded or not os.path.exists(downloaded):
                await menu_msg.edit_text(
                    "❌ **Failed to download the audio file!**",
                    reply_markup=get_back_to_audio_keyboard(),
                )
                return

            # Rename file locally
            renamed_path = os.path.join(temp_dir, new_file_name)
            os.rename(downloaded, renamed_path)

            tracker_up = ProgressTracker(
                client=client,
                message=menu_msg,
                task_id=task_id,
                action_name="📤 **Uploading Renamed Audio...**",
                interval=8.0,
                is_upload=True,
            )

            caption = f"✏️ **Renamed to:** `{new_file_name}`"
            out_duration = get_media_duration(renamed_path) or info.get("duration", 0)
            orig_performer = info.get("performer") if info.get("performer") != "Unknown Artist" else None

            user_thumb = get_user_thumbnail(user_id)

            user_settings = get_user_settings(user_id)
            if user_settings.get("upload_audio") == "file":
                await client.send_document(
                    chat_id=chat_id,
                    document=renamed_path,
                    caption=caption,
                    file_name=new_file_name,
                    thumb=user_thumb,
                    force_document=True,
                    progress=tracker_up,
                )
            else:
                await client.send_audio(
                    chat_id=chat_id,
                    audio=renamed_path,
                    caption=caption,
                    file_name=new_file_name,
                    performer=orig_performer,
                    duration=out_duration,
                    thumb=user_thumb,
                    progress=tracker_up,
                )

            # Delete the menu message
            if task_id not in CANCELLED_TASKS:
                try:
                    await menu_msg.delete()
                except Exception:
                    pass

        except StopTransmission:
            logger.info(f"Rename task {task_id} cancelled.")
            try:
                await menu_msg.edit_text(
                    "🚫 **Process Cancelled!**",
                    reply_markup=get_back_to_audio_keyboard(),
                )
            except Exception:
                pass
        except Exception as e:
            logger.error(f"Error during audio rename: {e}", exc_info=True)
            await menu_msg.edit_text(
                f"❌ **Error during rename:** `{e}`",
                reply_markup=get_back_to_audio_keyboard(),
            )
        finally:
            CANCELLED_TASKS.discard(task_id)
            ACTIVE_PROGRESS.pop(task_id, None)
            shutil.rmtree(temp_dir, ignore_errors=True)
        return


    elif action in ("trim_fast", "trim_accurate"):
        start_t, end_t = parse_time_range(message.text)
        if not start_t or not end_t:
            await menu_msg.edit_text(
                text=(
                    "⚠️ **Invalid Timestamp Format!**\n\n"
                    f"You typed: `{message.text}`\n\n"
                    "Please provide valid start and end timestamps:\n"
                    "• Format: `00:15 - 01:45` or `01:30 to 03:00` or `15 - 90`\n\n"
                    "*(Try typing again in chat or press back)*"
                ),
                reply_markup=get_back_to_trimmer_keyboard(),
            )
            return

        USER_STATES.pop(user_id, None)
        is_accurate = (action == "trim_accurate")
        mode_label = "Frame Accuracy" if is_accurate else "Fast Copy"

        temp_dir = os.path.join("downloads", f"{user_id}_trim_{int(time.time())}")
        os.makedirs(temp_dir, exist_ok=True)

        try:
            tracker_down = ProgressTracker(
                client=client,
                message=menu_msg,
                task_id=task_id,
                action_name=f"📥 **Downloading Audio for Trimming ({mode_label})...**",
                interval=8.0,
                is_upload=False,
            )

            await menu_msg.edit_text(
                f"📥 **Downloading Audio for Trimming ({mode_label})...**\n\nStarting download...",
                reply_markup=get_cancel_process_keyboard(task_id),
            )

            downloaded = await download_media_with_retry(
                client=client,
                message=target,
                file_name=os.path.join(temp_dir, orig_name),
                progress=tracker_down,
            )

            if task_id in CANCELLED_TASKS:
                return

            if not downloaded or not os.path.exists(downloaded):
                await menu_msg.edit_text(
                    "❌ **Failed to download the audio file!**",
                    reply_markup=get_back_to_audio_keyboard(),
                )
                return

            await menu_msg.edit_text(
                f"✂️ **Trimming Audio ({mode_label})...**\n\n"
                f"Cutting from `{start_t}` to `{end_t}` with FFmpeg...\n"
                "Please wait...",
                reply_markup=get_cancel_process_keyboard(task_id),
            )

            base_name, _ = os.path.splitext(orig_name)
            trimmed_name = f"{base_name}_trimmed{orig_ext}"
            trimmed_path = os.path.join(temp_dir, trimmed_name)

            success = await trim_audio_file_with_progress(
                input_path=downloaded,
                output_path=trimmed_path,
                start_time=start_t,
                end_time=end_t,
                accurate=is_accurate,
                message=menu_msg,
                task_id=task_id,
            )

            if not success or not os.path.exists(trimmed_path):
                await menu_msg.edit_text(
                    "❌ **FFmpeg trimming failed!** Please verify your timestamps.",
                    reply_markup=get_back_to_audio_keyboard(),
                )
                return

            if task_id in CANCELLED_TASKS:
                return

            out_duration = get_media_duration(trimmed_path)

            tracker_up = ProgressTracker(
                client=client,
                message=menu_msg,
                task_id=task_id,
                action_name=f"📤 **Uploading Trimmed Audio ({mode_label})...**",
                interval=8.0,
                is_upload=True,
            )

            caption = (
                f"✂️ **Trimmed Audio ({mode_label})**\n\n"
                f"• **Range:** `{start_t}` ➔ `{end_t}`\n"
                f"• **File:** `{trimmed_name}`"
            )
            orig_performer = info.get("performer") if info.get("performer") != "Unknown Artist" else None

            user_thumb = get_user_thumbnail(user_id)

            user_settings = get_user_settings(user_id)
            if user_settings.get("upload_audio") == "file":
                await client.send_document(
                    chat_id=chat_id,
                    document=trimmed_path,
                    caption=caption,
                    file_name=trimmed_name,
                    thumb=user_thumb,
                    force_document=True,
                    progress=tracker_up,
                )
            else:
                await client.send_audio(
                    chat_id=chat_id,
                    audio=trimmed_path,
                    caption=caption,
                    file_name=trimmed_name,
                    performer=orig_performer,
                    duration=out_duration,
                    thumb=user_thumb,
                    progress=tracker_up,
                )

            # Delete the menu message
            if task_id not in CANCELLED_TASKS:
                try:
                    await menu_msg.delete()
                except Exception:
                    pass

        except StopTransmission:
            logger.info(f"Trim task {task_id} cancelled.")
            try:
                await menu_msg.edit_text(
                    "🚫 **Process Cancelled!**",
                    reply_markup=get_back_to_audio_keyboard(),
                )
            except Exception:
                pass
        except Exception as e:
            logger.error(f"Error during audio trim: {e}", exc_info=True)
            await menu_msg.edit_text(
                f"❌ **Error during trim:** `{e}`",
                reply_markup=get_back_to_audio_keyboard(),
            )
        finally:
            CANCELLED_TASKS.discard(task_id)
            ACTIVE_PROGRESS.pop(task_id, None)
            shutil.rmtree(temp_dir, ignore_errors=True)
        return


    elif action == "audio_ffmpeg":
        user_cmd = message.text.strip()
        USER_STATES.pop(user_id, None)

        temp_dir = os.path.join("downloads", f"{user_id}_ffmpeg_{int(time.time())}")
        os.makedirs(temp_dir, exist_ok=True)

        try:
            tracker_down = ProgressTracker(
                client=client,
                message=menu_msg,
                task_id=task_id,
                action_name="📥 **Downloading Audio for FFmpeg Processing...**",
                interval=8.0,
                is_upload=False,
            )

            await menu_msg.edit_text(
                "📥 **Downloading Audio for FFmpeg Processing...**\n\nStarting download...",
                reply_markup=get_cancel_process_keyboard(task_id),
            )

            downloaded = await download_media_with_retry(
                client=client,
                message=target,
                file_name=os.path.join(temp_dir, orig_name),
                progress=tracker_down,
            )

            if task_id in CANCELLED_TASKS:
                return

            if not downloaded or not os.path.exists(downloaded):
                await menu_msg.edit_text(
                    "❌ **Failed to download the audio file!**",
                    reply_markup=get_back_to_audio_keyboard(),
                )
                return

            base_name, _ = os.path.splitext(orig_name)
            output_name = f"{base_name}_ffmpeg{orig_ext}"
            output_path = os.path.join(temp_dir, output_name)

            # Calculate input duration and detect target duration for progress tracking
            input_duration = get_media_duration(downloaded) or float(info.get("duration", 0))
            cmd_tokens = shlex.split(user_cmd)
            target_duration = detect_expected_duration(cmd_tokens, input_duration)

            # Build and execute the custom FFmpeg command with real-time live progress
            cmd = build_custom_ffmpeg_command(user_cmd, downloaded, output_path)
            success, err_msg = await execute_ffmpeg_with_progress(
                cmd=cmd,
                total_duration=target_duration,
                message=menu_msg,
                task_id=task_id,
                action_name="⚙️ **Processing Audio with FFmpeg...**",
            )

            if not success or not os.path.exists(output_path) or os.path.getsize(output_path) == 0:
                short_err = err_msg if len(err_msg) < 400 else err_msg[-400:]
                await menu_msg.edit_text(
                    f"❌ **FFmpeg Execution Error!**\n\n"
                    f"```text\n{short_err}\n```\n"
                    "Please check your FFmpeg arguments and try again.",
                    reply_markup=get_back_to_audio_keyboard(),
                )
                return

            if task_id in CANCELLED_TASKS:
                return

            out_duration = get_media_duration(output_path) or int(target_duration)

            tracker_up = ProgressTracker(
                client=client,
                message=menu_msg,
                task_id=task_id,
                action_name="📤 **Uploading Processed Audio...**",
                interval=8.0,
                is_upload=True,
            )

            caption = (
                f"💻 **Processed with Custom FFmpeg**\n\n"
                f"• **Command:** `{user_cmd}`\n"
                f"• **File:** `{output_name}`"
            )
            orig_performer = info.get("performer") if info.get("performer") != "Unknown Artist" else None

            user_thumb = get_user_thumbnail(user_id)

            user_settings = get_user_settings(user_id)
            if user_settings.get("upload_audio") == "file":
                await client.send_document(
                    chat_id=chat_id,
                    document=output_path,
                    caption=caption,
                    file_name=output_name,
                    thumb=user_thumb,
                    force_document=True,
                    progress=tracker_up,
                )
            else:
                await client.send_audio(
                    chat_id=chat_id,
                    audio=output_path,
                    caption=caption,
                    file_name=output_name,
                    performer=orig_performer,
                    duration=out_duration,
                    thumb=user_thumb,
                    progress=tracker_up,
                )

            # Delete the menu message if completed normally
            if task_id not in CANCELLED_TASKS:
                try:
                    await menu_msg.delete()
                except Exception:
                    pass

        except StopTransmission:
            logger.info(f"FFmpeg task {task_id} cancelled.")
            try:
                await menu_msg.edit_text(
                    "🚫 **Process Cancelled!**",
                    reply_markup=get_back_to_audio_keyboard(),
                )
            except Exception:
                pass
        except Exception as e:
            logger.error(f"Error during FFmpeg command execution: {e}", exc_info=True)
            await menu_msg.edit_text(
                f"❌ **Error during FFmpeg processing:** `{e}`",
                reply_markup=get_back_to_audio_keyboard(),
            )
        finally:
            CANCELLED_TASKS.discard(task_id)
            ACTIVE_PROGRESS.pop(task_id, None)
            shutil.rmtree(temp_dir, ignore_errors=True)
        return


    elif action == "video_rename":
        USER_STATES.pop(user_id, None)
        raw_name = message.text.strip()
        # Add extension if omitted
        if not os.path.splitext(raw_name)[1]:
            new_file_name = f"{raw_name}{orig_ext}"
        else:
            new_file_name = raw_name

        temp_dir = os.path.join("downloads", f"{user_id}_vrename_{int(time.time())}")
        os.makedirs(temp_dir, exist_ok=True)

        try:
            tracker_down = ProgressTracker(
                client=client,
                message=menu_msg,
                task_id=task_id,
                action_name="📥 **Downloading Video for Rename...**",
                interval=8.0,
                is_upload=False,
            )

            await menu_msg.edit_text(
                "📥 **Downloading Video...**\n\nStarting download for rename...",
                reply_markup=get_cancel_process_keyboard(task_id),
            )

            downloaded = await download_media_with_retry(
                client=client,
                message=target,
                file_name=os.path.join(temp_dir, orig_name),
                progress=tracker_down,
            )

            if task_id in CANCELLED_TASKS:
                return

            if not downloaded or not os.path.exists(downloaded):
                await menu_msg.edit_text(
                    "❌ **Failed to download the video file!**",
                    reply_markup=get_back_to_video_keyboard(),
                )
                return

            # Rename file locally
            renamed_path = os.path.join(temp_dir, new_file_name)
            os.rename(downloaded, renamed_path)

            out_size = os.path.getsize(renamed_path)
            if out_size > MAX_BOT_UPLOAD_SIZE:
                ACTIVE_PROGRESS.pop(task_id, None)
                await menu_msg.edit_text(
                    text=build_file_too_large_text(out_size),
                    reply_markup=get_back_to_video_keyboard(),
                )
                return

            tracker_up = ProgressTracker(
                client=client,
                message=menu_msg,
                task_id=task_id,
                action_name="📤 **Uploading Renamed Video...**",
                interval=8.0,
                is_upload=True,
            )

            caption = f"✏️ **Renamed to:** `{new_file_name}`"
            user_thumb = get_user_thumbnail(user_id)
            vid_w, vid_h = get_video_dimensions(renamed_path)
            if not vid_w:
                vid_w = info.get("width") or 0
                vid_h = info.get("height") or 0

            user_settings = get_user_settings(user_id)
            if user_settings.get("upload_video") != "file":
                out_duration = get_media_duration(renamed_path) or info.get("duration", 0)
                await client.send_video(
                    chat_id=chat_id,
                    video=renamed_path,
                    caption=caption,
                    file_name=new_file_name,
                    duration=out_duration,
                    width=vid_w or 0,
                    height=vid_h or 0,
                    thumb=user_thumb,
                    supports_streaming=True,
                    progress=tracker_up,
                )
            else:
                await client.send_document(
                    chat_id=chat_id,
                    document=renamed_path,
                    caption=caption,
                    file_name=new_file_name,
                    thumb=user_thumb,
                    force_document=True,
                    progress=tracker_up,
                )

            # Delete the menu message
            if task_id not in CANCELLED_TASKS:
                try:
                    await menu_msg.delete()
                except Exception:
                    pass

        except StopTransmission:
            logger.info(f"Video rename task {task_id} cancelled.")
            try:
                await menu_msg.edit_text(
                    "🚫 **Process Cancelled!**",
                    reply_markup=get_back_to_video_keyboard(),
                )
            except Exception:
                pass
        except Exception as e:
            logger.error(f"Error during video rename: {e}", exc_info=True)
            err_msg_text = build_file_too_large_text(out_size if 'out_size' in locals() else 0) if ("2000 MiB" in str(e) or "bigger than" in str(e)) else f"❌ **Error during rename:** `{e}`"
            await menu_msg.edit_text(
                err_msg_text,
                reply_markup=get_back_to_video_keyboard(),
            )
        finally:
            CANCELLED_TASKS.discard(task_id)
            ACTIVE_PROGRESS.pop(task_id, None)
            shutil.rmtree(temp_dir, ignore_errors=True)
        return


    elif action == "video_metadata_edit_title":
        new_title = message.text.strip()
        pending_metadata = state.setdefault("pending_metadata", {"global_title": None, "streams": {}})
        pending_metadata["global_title"] = new_title
        state["action"] = "video_metadata"

        probe_data = state.get("probe_data", {})
        streams = state.get("streams", {"audio": [], "subtitle": []})
        orig_name = state.get("file_name", "video.mp4")

        metadata_text = format_video_metadata_text(
            probe_data,
            fallback_name=orig_name,
            pending_metadata=pending_metadata,
        )
        if len(metadata_text) > 4000:
            metadata_text = metadata_text[:3990] + "\n\n*... (truncated)*"

        has_changes = bool(
            pending_metadata.get("global_title") is not None
            or pending_metadata.get("streams")
        )

        await menu_msg.edit_text(
            text=metadata_text,
            reply_markup=get_video_metadata_keyboard(
                streams["audio"],
                streams["subtitle"],
                has_changes=has_changes,
                pending_metadata=pending_metadata,
            ),
        )
        return

    # 6. VIDEO METADATA: EDIT STREAM (In-Memory Draft)
    elif action == "video_metadata_edit_stream":
        user_input = message.text.strip()
        parts = user_input.split("|", 1)
        if len(parts) != 2 or not parts[0].strip() or not parts[1].strip():
            await menu_msg.edit_text(
                text=(
                    "⚠️ **Invalid Format!**\n\n"
                    f"You typed: `{user_input}`\n\n"
                    "Please use the format: `Title|Language`\n"
                    "💡 **Example:** `AsilMedia|uzb`\n\n"
                    "*(Try typing again or press back)*"
                ),
                reply_markup=get_back_to_metadata_keyboard(),
            )
            return

        new_title = parts[0].strip()
        new_lang = parts[1].strip()

        stream_type = state.get("stream_type", "a")
        stream_idx = state.get("stream_idx", 0)
        stream_key = f"{stream_type}:{stream_idx}"

        pending_metadata = state.setdefault("pending_metadata", {"global_title": None, "streams": {}})
        pending_metadata.setdefault("streams", {})[stream_key] = {
            "title": new_title,
            "language": new_lang,
        }
        state["action"] = "video_metadata"

        probe_data = state.get("probe_data", {})
        streams = state.get("streams", {"audio": [], "subtitle": []})
        orig_name = state.get("file_name", "video.mp4")

        metadata_text = format_video_metadata_text(
            probe_data,
            fallback_name=orig_name,
            pending_metadata=pending_metadata,
        )
        if len(metadata_text) > 4000:
            metadata_text = metadata_text[:3990] + "\n\n*... (truncated)*"

        has_changes = bool(
            pending_metadata.get("global_title") is not None
            or pending_metadata.get("streams")
        )

        # Return to metadata overview with live draft changes and Apply button
        await menu_msg.edit_text(
            text=metadata_text,
            reply_markup=get_video_metadata_keyboard(
                streams["audio"],
                streams["subtitle"],
                has_changes=has_changes,
                pending_metadata=pending_metadata,
            ),
        )
        return

    # 7. VIDEO TRIMMER HANDLING (Fast Copy & Frame Accuracy)
    elif action in ("video_trim_fast", "video_trim_accurate"):
        start_t, end_t = parse_time_range(message.text)
        if not start_t or not end_t:
            await menu_msg.edit_text(
                text=(
                    "⚠️ **Invalid Timestamp Format!**\n\n"
                    f"You typed: `{message.text}`\n\n"
                    "Please provide valid start and end timestamps:\n"
                    "• Format: `00:15 - 01:45` or `01:30 to 03:00` or `15 - 90`\n\n"
                    "*(Try typing again in chat or press back)*"
                ),
                reply_markup=get_back_to_video_trimmer_keyboard(),
            )
            return

        USER_STATES.pop(user_id, None)
        is_accurate = (action == "video_trim_accurate")
        mode_label = "Frame Accuracy" if is_accurate else "Fast Copy"

        temp_dir = os.path.join("downloads", f"{user_id}_vtrim_{int(time.time())}")
        os.makedirs(temp_dir, exist_ok=True)

        try:
            tracker_down = ProgressTracker(
                client=client,
                message=menu_msg,
                task_id=task_id,
                action_name=f"📥 **Downloading Video for Trimming ({mode_label})...**",
                interval=8.0,
                is_upload=False,
            )

            await menu_msg.edit_text(
                f"📥 **Downloading Video for Trimming ({mode_label})...**\n\nStarting download...",
                reply_markup=get_cancel_process_keyboard(task_id),
            )

            downloaded = await download_media_with_retry(
                client=client,
                message=target,
                file_name=os.path.join(temp_dir, orig_name),
                progress=tracker_down,
            )

            if task_id in CANCELLED_TASKS:
                return

            if not downloaded or not os.path.exists(downloaded):
                await menu_msg.edit_text(
                    "❌ **Failed to download the video file!**",
                    reply_markup=get_back_to_video_keyboard(),
                )
                return

            await menu_msg.edit_text(
                f"✂️ **Trimming Video ({mode_label})...**\n\n"
                f"Cutting from `{start_t}` to `{end_t}` with FFmpeg...\n"
                "Please wait...",
                reply_markup=get_cancel_process_keyboard(task_id),
            )

            base_name, _ = os.path.splitext(orig_name)
            trimmed_name = f"{base_name}_trimmed{orig_ext}"
            trimmed_path = os.path.join(temp_dir, trimmed_name)

            success = await trim_video_file_with_progress(
                input_path=downloaded,
                output_path=trimmed_path,
                start_time=start_t,
                end_time=end_t,
                accurate=is_accurate,
                message=menu_msg,
                task_id=task_id,
            )

            if not success or not os.path.exists(trimmed_path):
                await menu_msg.edit_text(
                    "❌ **FFmpeg video trimming failed!** Please verify your timestamps.",
                    reply_markup=get_back_to_video_keyboard(),
                )
                return

            if task_id in CANCELLED_TASKS:
                return

            out_size = os.path.getsize(trimmed_path)
            if out_size > MAX_BOT_UPLOAD_SIZE:
                ACTIVE_PROGRESS.pop(task_id, None)
                await menu_msg.edit_text(
                    text=build_file_too_large_text(out_size),
                    reply_markup=get_back_to_video_keyboard(),
                )
                return

            out_duration = get_media_duration(trimmed_path)
            vid_w, vid_h = get_video_dimensions(trimmed_path)

            tracker_up = ProgressTracker(
                client=client,
                message=menu_msg,
                task_id=task_id,
                action_name=f"📤 **Uploading Trimmed Video ({mode_label})...**",
                interval=8.0,
                is_upload=True,
            )

            caption = (
                f"✂️ **Trimmed Video ({mode_label})**\n\n"
                f"• **Range:** `{start_t}` ➔ `{end_t}`\n"
                f"• **File:** `{trimmed_name}`"
            )

            user_thumb = get_user_thumbnail(user_id)

            user_settings = get_user_settings(user_id)
            if user_settings.get("upload_video") != "file":
                vid_info = target.video if target and target.video else None
                if not vid_w and vid_info:
                    vid_w = vid_info.width or 0
                    vid_h = vid_info.height or 0
                await client.send_video(
                    chat_id=chat_id,
                    video=trimmed_path,
                    caption=caption,
                    file_name=trimmed_name,
                    duration=out_duration or (vid_info.duration if vid_info else 0),
                    width=vid_w or 0,
                    height=vid_h or 0,
                    thumb=user_thumb,
                    supports_streaming=True,
                    progress=tracker_up,
                )
            else:
                await client.send_document(
                    chat_id=chat_id,
                    document=trimmed_path,
                    caption=caption,
                    file_name=trimmed_name,
                    thumb=user_thumb,
                    force_document=True,
                    progress=tracker_up,
                )

            # Delete the menu message
            if task_id not in CANCELLED_TASKS:
                try:
                    await menu_msg.delete()
                except Exception:
                    pass

        except StopTransmission:
            logger.info(f"Video trim task {task_id} cancelled.")
            try:
                await menu_msg.edit_text(
                    "🚫 **Process Cancelled!**",
                    reply_markup=get_back_to_video_keyboard(),
                )
            except Exception:
                pass
        except Exception as e:
            logger.error(f"Error during video trim: {e}", exc_info=True)
            err_msg_text = build_file_too_large_text(out_size if 'out_size' in locals() else 0) if ("2000 MiB" in str(e) or "bigger than" in str(e)) else f"❌ **Error during video trim:** `{e}`"
            await menu_msg.edit_text(
                err_msg_text,
                reply_markup=get_back_to_video_keyboard(),
            )
        finally:
            CANCELLED_TASKS.discard(task_id)
            ACTIVE_PROGRESS.pop(task_id, None)
            shutil.rmtree(temp_dir, ignore_errors=True)
        return

    # 8. VIDEO FFMPEG COMMAND HANDLING
    elif action == "video_ffmpeg":
        user_cmd = message.text.strip()
        USER_STATES.pop(user_id, None)

        temp_dir = os.path.join("downloads", f"{user_id}_vffmpeg_{int(time.time())}")
        os.makedirs(temp_dir, exist_ok=True)

        try:
            tracker_down = ProgressTracker(
                client=client,
                message=menu_msg,
                task_id=task_id,
                action_name="📥 **Downloading Video for FFmpeg Processing...**",
                interval=8.0,
                is_upload=False,
            )

            await menu_msg.edit_text(
                "📥 **Downloading Video for FFmpeg Processing...**\n\nStarting download...",
                reply_markup=get_cancel_process_keyboard(task_id),
            )

            downloaded = await download_media_with_retry(
                client=client,
                message=target,
                file_name=os.path.join(temp_dir, orig_name),
                progress=tracker_down,
            )

            if task_id in CANCELLED_TASKS:
                return

            if not downloaded or not os.path.exists(downloaded):
                await menu_msg.edit_text(
                    "❌ **Failed to download the video file!**",
                    reply_markup=get_back_to_video_keyboard(),
                )
                return

            base_name, _ = os.path.splitext(orig_name)
            output_name = f"{base_name}_ffmpeg{orig_ext}"
            output_path = os.path.join(temp_dir, output_name)

            input_duration = get_media_duration(downloaded) or float(info.get("duration", 0))
            cmd_tokens = shlex.split(user_cmd)
            target_duration = detect_expected_duration(cmd_tokens, input_duration)

            cmd = build_custom_ffmpeg_command(user_cmd, downloaded, output_path)
            success, err_msg = await execute_ffmpeg_with_progress(
                cmd=cmd,
                total_duration=target_duration,
                message=menu_msg,
                task_id=task_id,
                action_name="⚙️ **Processing Video with FFmpeg...**",
            )

            if not success or not os.path.exists(output_path) or os.path.getsize(output_path) == 0:
                short_err = err_msg if len(err_msg) < 400 else err_msg[-400:]
                await menu_msg.edit_text(
                    f"❌ **FFmpeg Execution Error!**\n\n"
                    f"```text\n{short_err}\n```\n"
                    "Please check your FFmpeg arguments and try again.",
                    reply_markup=get_back_to_video_keyboard(),
                )
                return

            if task_id in CANCELLED_TASKS:
                return

            out_size = os.path.getsize(output_path)
            if out_size > MAX_BOT_UPLOAD_SIZE:
                ACTIVE_PROGRESS.pop(task_id, None)
                await menu_msg.edit_text(
                    text=build_file_too_large_text(out_size),
                    reply_markup=get_back_to_video_keyboard(),
                )
                return

            out_duration = get_media_duration(output_path) or int(target_duration)
            vid_w, vid_h = get_video_dimensions(output_path)
            user_thumb = get_user_thumbnail(user_id)

            tracker_up = ProgressTracker(
                client=client,
                message=menu_msg,
                task_id=task_id,
                action_name="📤 **Uploading Processed Video...**",
                interval=8.0,
                is_upload=True,
            )

            caption = (
                f"💻 **Processed with Custom Video FFmpeg**\n\n"
                f"• **Command:** `{user_cmd}`\n"
                f"• **File:** `{output_name}`"
            )

            user_settings = get_user_settings(user_id)
            if user_settings.get("upload_video") != "file":
                vid_info = target.video if target and target.video else None
                if not vid_w and vid_info:
                    vid_w = vid_info.width or 0
                    vid_h = vid_info.height or 0
                await client.send_video(
                    chat_id=chat_id,
                    video=output_path,
                    caption=caption,
                    file_name=output_name,
                    duration=out_duration,
                    width=vid_w or 0,
                    height=vid_h or 0,
                    thumb=user_thumb,
                    supports_streaming=True,
                    progress=tracker_up,
                )
            else:
                await client.send_document(
                    chat_id=chat_id,
                    document=output_path,
                    caption=caption,
                    file_name=output_name,
                    thumb=user_thumb,
                    force_document=True,
                    progress=tracker_up,
                )

            if task_id not in CANCELLED_TASKS:
                try:
                    await menu_msg.delete()
                except Exception:
                    pass

        except StopTransmission:
            logger.info(f"FFmpeg task {task_id} cancelled.")
            try:
                await menu_msg.edit_text(
                    "🚫 **Process Cancelled!**",
                    reply_markup=get_back_to_video_keyboard(),
                )
            except Exception:
                pass
        except Exception as e:
            logger.error(f"Error during video FFmpeg processing: {e}", exc_info=True)
            err_msg_text = build_file_too_large_text(out_size if 'out_size' in locals() else 0) if ("2000 MiB" in str(e) or "bigger than" in str(e)) else f"❌ **Error during FFmpeg processing:** `{e}`"
            await menu_msg.edit_text(
                err_msg_text,
                reply_markup=get_back_to_video_keyboard(),
            )
        finally:
            CANCELLED_TASKS.discard(task_id)
            ACTIVE_PROGRESS.pop(task_id, None)
            shutil.rmtree(temp_dir, ignore_errors=True)
        return


async def run_bot():
    await app.start()
    logger.info("✅ FF Media Bot is active and listening for messages! (Press Ctrl+C to stop)")
    try:
        # Sleep in 1-second chunks so Windows console can trigger Ctrl+C immediately
        while True:
            await asyncio.sleep(1)
    except (asyncio.CancelledError, KeyboardInterrupt):
        pass
    finally:
        logger.info("Stopping bot session...")
        try:
            await app.stop()
        except Exception:
            pass


if __name__ == "__main__":
    try:
        app.run(run_bot())
    except (KeyboardInterrupt, SystemExit):
        print("\nBot stopped cleanly.")
        os._exit(0)
    except Exception as e:
        logger.error(f"Error running bot: {e}")
