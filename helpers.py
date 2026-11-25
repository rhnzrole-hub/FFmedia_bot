import asyncio
import json
import os
import re
import shlex
import time
import subprocess
import logging
import sqlite3
from typing import Tuple, Optional
import mutagen
from hydrogram.types import Message
from hydrogram import StopTransmission
from keyboards import get_cancel_process_keyboard

logger = logging.getLogger(__name__)

# Set of task_ids that have been requested to cancel
CANCELLED_TASKS = set()

# Dictionary to hold the latest live progress metrics for each active task
# Used by the 'Refresh' button to immediately update without waiting for the 8s timer
ACTIVE_PROGRESS = {}

AUDIO_EXTENSIONS = (
    ".mp3", ".m4a", ".wav", ".aac", ".flac", ".ogg",
    ".opus", ".wma", ".mka", ".alac", ".aiff", ".amr",
    ".ape", ".ra", ".mid", ".midi"
)

VIDEO_EXTENSIONS = (
    ".mp4", ".mkv", ".avi", ".mov", ".flv", ".webm",
    ".wmv", ".3gp", ".ts", ".m4v", ".mpg", ".mpeg",
    ".vob", ".ogv"
)


def humanbytes(size: Optional[int]) -> str:
    """Converts bytes to human readable format (KB, MB, GB)."""
    if not size:
        return "0 B"
    for unit in ["B", "KB", "MB", "GB", "TB"]:
        if size < 1024:
            return f"{size:.2f} {unit}"
        size /= 1024
    return f"{size:.2f} PB"


def format_duration(seconds: Optional[int]) -> str:
    """Formats duration in seconds to HH:MM:SS or MM:SS."""
    if not seconds:
        return "00:00"
    m, s = divmod(int(seconds), 60)
    h, m = divmod(m, 60)
    if h > 0:
        return f"{h:02d}:{m:02d}:{s:02d}"
    return f"{m:02d}:{s:02d}"


def detect_media(message: Message) -> Tuple[str, dict]:
    """
    Detects if the message is an Audio, Video, or File.
    Returns:
        type_str: 'audio' | 'video' | 'file'
        info: dict with file_name, file_size, duration, mime_type, file_id
    """
    # 1. Native Audio or Voice
    if message.audio:
        audio = message.audio
        return "audio", {
            "file_id": audio.file_id,
            "file_name": audio.file_name or f"{audio.title or 'audio'}.mp3",
            "file_size": audio.file_size,
            "duration": audio.duration,
            "mime_type": audio.mime_type or "audio/mpeg",
            "performer": audio.performer or "Unknown Artist",
            "title": audio.title or "Unknown Title",
        }

    if message.voice:
        voice = message.voice
        return "audio", {
            "file_id": voice.file_id,
            "file_name": f"voice_note_{voice.file_unique_id}.ogg",
            "file_size": voice.file_size,
            "duration": voice.duration,
            "mime_type": voice.mime_type or "audio/ogg",
            "performer": "Voice Note",
            "title": "Voice Message",
        }

    # 2. Native Video or Animation or Video Note
    if message.video:
        video = message.video
        return "video", {
            "file_id": video.file_id,
            "file_name": video.file_name or f"video_{video.file_unique_id}.mp4",
            "file_size": video.file_size,
            "duration": video.duration,
            "mime_type": video.mime_type or "video/mp4",
            "width": video.width,
            "height": video.height,
        }

    if message.animation:
        anim = message.animation
        return "video", {
            "file_id": anim.file_id,
            "file_name": anim.file_name or f"animation_{anim.file_unique_id}.mp4",
            "file_size": anim.file_size,
            "duration": anim.duration,
            "mime_type": anim.mime_type or "video/mp4",
        }

    if message.video_note:
        vnote = message.video_note
        return "video", {
            "file_id": vnote.file_id,
            "file_name": f"video_note_{vnote.file_unique_id}.mp4",
            "file_size": vnote.file_size,
            "duration": vnote.duration,
            "mime_type": "video/mp4",
        }

    # 3. Document (Can be Audio, Video, or generic File)
    if message.document:
        doc = message.document
        file_name = doc.file_name or f"file_{doc.file_unique_id}"
        mime_type = (doc.mime_type or "").lower()
        ext = os.path.splitext(file_name)[1].lower()

        # Check if document is actually Audio
        if mime_type.startswith("audio/") or ext in AUDIO_EXTENSIONS:
            return "audio", {
                "file_id": doc.file_id,
                "file_name": file_name,
                "file_size": doc.file_size,
                "duration": 0,
                "mime_type": mime_type or "audio/mpeg",
                "performer": "Document Audio",
                "title": file_name,
            }

        # Check if document is actually Video
        if mime_type.startswith("video/") or ext in VIDEO_EXTENSIONS:
            return "video", {
                "file_id": doc.file_id,
                "file_name": file_name,
                "file_size": doc.file_size,
                "duration": 0,
                "mime_type": mime_type or "video/mp4",
            }

        # Otherwise it's a generic document/file
        return "file", {
            "file_id": doc.file_id,
            "file_name": file_name,
            "file_size": doc.file_size,
            "mime_type": mime_type or "application/octet-stream",
        }

    return "unknown", {}


def remove_audio_metadata_title(file_path: str) -> str:
    """
    Removes the metadata 'title' tag from the audio file using Mutagen and FFmpeg stream copy.
    Returns the path of the cleaned file.
    """
    ext = os.path.splitext(file_path)[1].lower()
    base_dir, file_name = os.path.split(file_path)
    output_path = os.path.join(base_dir, f"notitle_{file_name}")

    # 1. Try with FFmpeg stream copy (fast, loss-less, reliable across containers)
    try:
        cmd = [
            "ffmpeg", "-y", "-i", file_path,
            "-metadata", "title=",
            "-codec", "copy",
            output_path
        ]
        res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        if res.returncode == 0 and os.path.exists(output_path) and os.path.getsize(output_path) > 0:
            target_file = output_path
        else:
            target_file = file_path
    except Exception as e:
        logger.warning(f"FFmpeg strip title failed: {e}")
        target_file = file_path

    # 2. Also strip tags via Mutagen for absolute certainty
    try:
        if ext == ".mp3":
            from mutagen.id3 import ID3
            try:
                id3 = ID3(target_file)
                id3.delall("TIT2")
                id3.delall("TIT1")
                id3.delall("TIT3")
                id3.save()
            except Exception:
                pass
        elif ext in [".m4a", ".mp4"]:
            from mutagen.mp4 import MP4
            try:
                mp4 = MP4(target_file)
                if mp4.tags:
                    if "\xa9nam" in mp4.tags:
                        del mp4.tags["\xa9nam"]
                    mp4.save()
            except Exception:
                pass
        else:
            try:
                audio = mutagen.File(target_file, easy=True)
                if audio is not None and "title" in audio:
                    del audio["title"]
                    audio.save()
            except Exception:
                pass
    except Exception as e:
        logger.warning(f"Mutagen strip title error: {e}")

    return target_file


def format_progress_text(
    action_name: str,
    label: str,
    current: int,
    total: int,
    speed: float,
    eta: float,
    elapsed: float,
    percent: float,
    bar: str,
) -> str:
    """Formats the standardized progress message text."""
    return (
        f"{action_name}\n\n"
        f"`[{bar}]` **{percent:.1f}%**\n"
        f"• **{label}:** `{humanbytes(current)} / {humanbytes(total)}`\n"
        f"• **Speed:** `{humanbytes(int(speed))}/s`\n"
        f"• **ETA:** `{format_duration(int(eta))}`\n"
        f"• **Elapsed:** `{format_duration(int(elapsed))}`"
    )


def format_ffmpeg_progress_text(
    action_name: str,
    current_sec: float,
    total_sec: float,
    speed_str: str,
    eta: float,
    elapsed: float,
    percent: float,
    bar: str,
) -> str:
    """Formats the standardized FFmpeg execution progress message."""
    curr_fmt = format_duration(int(current_sec))
    total_fmt = format_duration(int(total_sec)) if total_sec > 0 else "--:--"
    eta_fmt = format_duration(int(eta)) if eta >= 0 and total_sec > 0 else "--:--"
    elapsed_fmt = format_duration(int(elapsed))
    return (
        f"{action_name}\n\n"
        f"`[{bar}]` **{percent:.1f}%**\n"
        f"• **Processed:** `{curr_fmt} / {total_fmt}`\n"
        f"• **Speed:** `{speed_str}`\n"
        f"• **ETA:** `{eta_fmt}`\n"
        f"• **Elapsed:** `{elapsed_fmt}`"
    )


def create_progress_tracker(
    client,
    message: Message,
    task_id: str,
    action_name: str = "📥 **Downloading Media...**",
    interval: float = 8.0,
    is_upload: Optional[bool] = None,
):
    """
    Creates an async coroutine callback function for Hydrogram file progress.
    Properly passes inspect.iscoroutinefunction check so Hydrogram awaits it directly!
    Displays 'Downloaded' for downloads and 'Uploaded' for uploads.
    Supports on-demand 'Refresh' and 'Cancel Process' buttons.
    """
    start_time = time.time()
    last_update_time = 0.0
    first_call = True

    # Auto-detect upload vs download if not explicitly provided
    if is_upload is None:
        upload_mode = "upload" in action_name.lower()
    else:
        upload_mode = is_upload

    label = "Uploaded" if upload_mode else "Downloaded"

    async def progress_callback(current: int, total: int):
        nonlocal last_update_time, first_call

        # 1. Check if user requested cancellation
        if task_id and task_id in CANCELLED_TASKS:
            ACTIVE_PROGRESS.pop(task_id, None)
            if client:
                client.stop_transmission()
            raise StopTransmission

        now = time.time()
        if not total or total == 0:
            return

        elapsed = now - start_time
        speed = current / elapsed if elapsed > 0 else 0
        eta = (total - current) / speed if speed > 0 else 0
        percent = (current / total) * 100

        # Progress bar (10 blocks)
        completed_blocks = min(10, max(0, int(percent / 10)))
        remaining_blocks = 10 - completed_blocks
        bar = "▰" * completed_blocks + "▱" * remaining_blocks

        # Always update ACTIVE_PROGRESS so Refresh button can fetch the latest state
        ACTIVE_PROGRESS[task_id] = {
            "action_name": action_name,
            "label": label,
            "current": current,
            "total": total,
            "speed": speed,
            "eta": eta,
            "elapsed": elapsed,
            "percent": percent,
            "bar": bar,
        }

        # Update message on first chunk, or strictly every 8 seconds, or when 100% complete
        if not first_call and current != total and (now - last_update_time) < interval:
            return

        first_call = False
        last_update_time = now

        text = format_progress_text(
            action_name=action_name,
            label=label,
            current=current,
            total=total,
            speed=speed,
            eta=eta,
            elapsed=elapsed,
            percent=percent,
            bar=bar,
        )

        try:
            keyboard = get_cancel_process_keyboard(task_id) if task_id else None
            await message.edit_text(text, reply_markup=keyboard)
        except StopTransmission:
            raise
        except Exception:
            pass

    return progress_callback


async def download_media_with_retry(
    client,
    message,
    file_name: str,
    progress=None,
    max_attempts: int = 3,
) -> Optional[str]:
    """
    Downloads media from Telegram with retry logic and exponential backoff.
    Prevents failed downloads due to transient DC network congestion or socket drops.
    """
    for attempt in range(1, max_attempts + 1):
        try:
            downloaded = await client.download_media(
                message=message,
                file_name=file_name,
                progress=progress,
            )
            if downloaded and os.path.exists(downloaded) and os.path.getsize(downloaded) > 0:
                return str(downloaded)
        except StopTransmission:
            raise
        except Exception as e:
            logger.warning(f"Download attempt {attempt}/{max_attempts} failed: {e}")
        if attempt < max_attempts:
            await asyncio.sleep(2 * attempt)
    return None


# Backward compatibility alias
ProgressTracker = create_progress_tracker


async def refresh_progress_display(query, task_id: str):
    """
    Immediately updates the progress display message when the user clicks 'Refresh',
    bypassing the 8-second interval timer.
    """
    state = ACTIVE_PROGRESS.get(task_id)
    if not state:
        await query.answer("Progress is already up to date or completed.", show_alert=False)
        return

    if state.get("is_ffmpeg"):
        text = format_ffmpeg_progress_text(
            action_name=state["action_name"],
            current_sec=state["current_sec"],
            total_sec=state["total_sec"],
            speed_str=state["speed_str"],
            eta=state["eta"],
            elapsed=state["elapsed"],
            percent=state["percent"],
            bar=state["bar"],
        )
    else:
        text = format_progress_text(
            action_name=state["action_name"],
            label=state["label"],
            current=state["current"],
            total=state["total"],
            speed=state["speed"],
            eta=state["eta"],
            elapsed=state["elapsed"],
            percent=state["percent"],
            bar=state["bar"],
        )

    try:
        await query.message.edit_text(
            text=text,
            reply_markup=get_cancel_process_keyboard(task_id),
        )
        await query.answer("🔄 Refreshed!", show_alert=False)
    except Exception:
        await query.answer("⚡ Already showing the latest metrics.", show_alert=False)



def parse_time_input(time_str: str) -> Optional[str]:
    """Parses a single timestamp string (seconds, MM:SS, HH:MM:SS) into a valid format."""
    clean = time_str.strip()
    if not clean:
        return None
    # If purely digits: seconds e.g. "90" -> "00:01:30"
    if clean.isdigit():
        return format_duration(int(clean))
    # If formatted e.g. 01:25 or 00:01:25 or 01:25.500
    parts = clean.split(":")
    if len(parts) in (2, 3):
        return clean
    return None


def parse_time_range(text: str) -> Tuple[Optional[str], Optional[str]]:
    """
    Parses start and end timestamps from user text.
    Supports formats:
      - '00:15 - 01:45'
      - '0:15 to 1:45'
      - '15 - 90'
      - '00:15.500 - 01:45.250'
    """
    clean_text = text.strip()
    if "-" in clean_text:
        parts = clean_text.split("-", 1)
    elif "to" in clean_text.lower():
        parts = re.split(r'\bto\b', clean_text, flags=re.IGNORECASE)
    else:
        parts = clean_text.split()

    if len(parts) != 2:
        return None, None

    start = parse_time_input(parts[0])
    end = parse_time_input(parts[1])
    return start, end


def get_media_duration(file_path: str) -> int:
    """Returns the media file duration in seconds (int) using ffprobe or mutagen."""
    if not file_path or not os.path.exists(file_path):
        return 0
    try:
        cmd = [
            "ffprobe",
            "-v", "error",
            "-show_entries", "format=duration",
            "-of", "default=noprint_wrappers=1:nokey=1",
            file_path,
        ]
        res = subprocess.run(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=10,
        )
        if res.returncode == 0 and res.stdout.strip():
            return int(float(res.stdout.strip()))
    except Exception as e:
        logger.debug(f"ffprobe duration probe error: {e}")

    try:
        from mutagen import File
        audio = File(file_path)
        if audio and audio.info and getattr(audio.info, "length", None):
            return int(audio.info.length)
    except Exception:
        pass

    return 0


MAX_BOT_UPLOAD_SIZE = 2097152000  # 2000 MiB (Telegram Bot MTProto hard limit)


def get_video_dimensions(file_path: str) -> tuple[int, int]:
    """Returns the video dimensions (width, height) using ffprobe.
    Returns (0, 0) if extraction fails or not a video.
    """
    if not file_path or not os.path.exists(file_path):
        return 0, 0
    try:
        cmd = [
            "ffprobe",
            "-v", "error",
            "-select_streams", "v:0",
            "-show_entries", "stream=width,height",
            "-of", "csv=s=x:p=0",
            str(file_path),
        ]
        res = subprocess.run(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=10,
        )
        if res.returncode == 0 and "x" in res.stdout:
            parts = res.stdout.strip().split("x")
            return int(parts[0]), int(parts[1])
    except Exception:
        pass
    return 0, 0


def build_file_too_large_text(file_size: int) -> str:
    """Returns user-facing explanation when file exceeds Telegram Bot upload limit."""
    return (
        f"❌ **Upload Failed: File Exceeds 2 GB Limit!**\n\n"
        f"• **File Size:** `{humanbytes(file_size)}`\n"
        f"• **Telegram Bot Limit:** `2.00 GB (2000 MiB)`\n\n"
        f"⚠️ **Telegram server cheklovi:**\n"
        f"Telegram Bot API va bot hisoblari orqali **2 GB (2000 MiB) dan katta** fayllarni yuklash imkonsiz. "
        f"Bu Telegram platformasining server darajasidagi qat'iy cheklovidir (faqat Premium user akkauntlar 4 GB gacha yuklay oladi).\n\n"
        f"💡 **Yechim:** Faylni qismlarga bo'ling (Trim) yoki video hajmini siqing (Compress)."
    )


def get_audio_ffprobe_info(file_path: str) -> Optional[dict]:
    """
    Runs ffprobe on the given audio file and parses complete stream and container JSON.
    """
    if not file_path or not os.path.exists(file_path):
        return None
    try:
        cmd = [
            "ffprobe",
            "-v", "quiet",
            "-print_format", "json",
            "-show_format",
            "-show_streams",
            file_path,
        ]
        res = subprocess.run(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=15,
        )
        if res.returncode == 0 and res.stdout.strip():
            return json.loads(res.stdout)
    except Exception as e:
        logger.error(f"FFprobe extraction failed: {e}")
    return None


def format_ffprobe_audio_info(probe_data: dict, fallback_name: str = "audio.mp3") -> str:
    """
    Formats ffprobe JSON output into an attractive, structured Markdown presentation.
    """
    format_info = probe_data.get("format", {})
    streams = probe_data.get("streams", [])

    # Find the primary audio stream
    audio_stream = None
    for st in streams:
        if st.get("codec_type") == "audio":
            audio_stream = st
            break
    if not audio_stream and streams:
        audio_stream = streams[0]

    # Container details
    format_name = format_info.get("format_name", "Unknown")
    format_long_name = format_info.get("format_long_name", format_name)
    try:
        file_size = int(format_info.get("size", 0))
    except (ValueError, TypeError):
        file_size = 0

    try:
        duration_sec = float(format_info.get("duration", 0))
    except (ValueError, TypeError):
        duration_sec = 0.0

    # Overall Bitrate
    try:
        overall_bitrate = int(format_info.get("bit_rate", 0))
        bitrate_str = f"{overall_bitrate // 1000} kbps" if overall_bitrate > 0 else "Unknown"
    except (ValueError, TypeError):
        bitrate_str = "Unknown"

    # Audio Stream Details
    codec_name = "Unknown"
    codec_long = "Unknown"
    sample_rate_str = "Unknown"
    channels_str = "Unknown"
    sample_fmt = "Unknown"

    if audio_stream:
        codec_name = audio_stream.get("codec_name", "Unknown").upper()
        codec_long = audio_stream.get("codec_long_name", codec_name)

        sr = audio_stream.get("sample_rate")
        if sr:
            try:
                sr_int = int(sr)
                sample_rate_str = f"{sr_int:,} Hz ({sr_int / 1000:.1f} kHz)"
            except Exception:
                sample_rate_str = f"{sr} Hz"

        channels = audio_stream.get("channels")
        layout = audio_stream.get("channel_layout")
        if channels:
            channels_str = f"{channels} Channel{'s' if channels > 1 else ''}"
            if layout:
                channels_str += f" ({layout})"
        elif layout:
            channels_str = layout

        sample_fmt = audio_stream.get("sample_fmt", "Unknown")

        # Stream bitrate if overall was unknown
        if bitrate_str == "Unknown" and audio_stream.get("bit_rate"):
            try:
                s_br = int(audio_stream.get("bit_rate", 0))
                if s_br > 0:
                    bitrate_str = f"{s_br // 1000} kbps"
            except Exception:
                pass

    # Metadata tags
    tags = dict(format_info.get("tags", {}))
    if audio_stream and "tags" in audio_stream:
        for k, v in audio_stream["tags"].items():
            if k.lower() not in [tk.lower() for tk in tags.keys()]:
                tags[k] = v

    def get_tag(*candidates):
        for c in candidates:
            for k, v in tags.items():
                if k.lower() == c.lower() and str(v).strip():
                    return str(v).strip()
        return None

    title = get_tag("title", "track")
    artist = get_tag("artist", "performer", "album_artist")
    album = get_tag("album")
    genre = get_tag("genre")
    date = get_tag("date", "year", "creation_time")
    if date and len(date) > 10:
        date = date[:10]
    track_num = get_tag("track", "tracknumber")
    encoder = get_tag("encoder", "encoded_by", "tool")

    lines = [
        "🔍 **FFprobe Audio Analysis**\n",
        "📁 **File Details:**",
        f"• **File Name:** `{fallback_name}`",
        f"• **File Size:** `{humanbytes(file_size)}`",
        f"• **Duration:** `{format_duration(int(duration_sec))}` (`{duration_sec:.2f}s`)",
        f"• **Container:** `{format_long_name}`",
        "",
        "🎵 **Audio Stream:**",
        f"• **Codec:** `{codec_long}` (`{codec_name}`)",
        f"• **Bitrate:** `{bitrate_str}`",
        f"• **Sample Rate:** `{sample_rate_str}`",
        f"• **Channels:** `{channels_str}`",
        f"• **Sample Format:** `{sample_fmt}`",
    ]

    tag_lines = []
    if title:
        tag_lines.append(f"• **Title:** `{title}`")
    if artist:
        tag_lines.append(f"• **Artist:** `{artist}`")
    if album:
        tag_lines.append(f"• **Album:** `{album}`")
    if genre:
        tag_lines.append(f"• **Genre:** `{genre}`")
    if date:
        tag_lines.append(f"• **Date / Year:** `{date}`")
    if track_num:
        tag_lines.append(f"• **Track #:** `{track_num}`")
    if encoder:
        tag_lines.append(f"• **Encoder:** `{encoder}`")

    if tag_lines:
        lines.append("")
        lines.append("🏷️ **Metadata Tags:**")
        lines.extend(tag_lines)

    return "\n".join(lines)


def format_ffprobe_video_info(probe_data: dict, fallback_name: str = "video.mp4") -> str:
    """
    Formats ffprobe JSON output for a video file into an attractive, structured Markdown presentation.
    Includes container details, video stream(s), audio stream(s), subtitle stream(s), and metadata tags.
    """
    format_info = probe_data.get("format", {})
    streams = probe_data.get("streams", [])

    # Container details
    format_name = format_info.get("format_name", "Unknown")
    format_long_name = format_info.get("format_long_name", format_name)
    try:
        file_size = int(format_info.get("size", 0))
    except (ValueError, TypeError):
        file_size = 0

    try:
        duration_sec = float(format_info.get("duration", 0))
    except (ValueError, TypeError):
        duration_sec = 0.0

    try:
        overall_bitrate = int(format_info.get("bit_rate", 0))
        bitrate_str = f"{overall_bitrate // 1000} kbps" if overall_bitrate > 0 else "Unknown"
    except (ValueError, TypeError):
        bitrate_str = "Unknown"

    lines = [
        "🔍 **FFprobe Video Analysis**\n",
        "📁 **File Details:**",
        f"• **File Name:** `{fallback_name}`",
        f"• **File Size:** `{humanbytes(file_size)}`",
        f"• **Duration:** `{format_duration(int(duration_sec))}` (`{duration_sec:.2f}s`)",
        f"• **Overall Bitrate:** `{bitrate_str}`",
        f"• **Container:** `{format_long_name}`",
    ]

    video_streams = [s for s in streams if s.get("codec_type") == "video"]
    audio_streams = [s for s in streams if s.get("codec_type") == "audio"]
    subtitle_streams = [s for s in streams if s.get("codec_type") == "subtitle"]

    # 1. Video Streams
    for i, vs in enumerate(video_streams):
        v_idx = vs.get("index", i)
        v_codec = vs.get("codec_name", "unknown").upper()
        v_codec_long = vs.get("codec_long_name", v_codec)
        w = vs.get("width", 0)
        h = vs.get("height", 0)
        res_str = f"{w}x{h}" if w and h else "Unknown"
        dar = vs.get("display_aspect_ratio")
        if dar:
            res_str += f" ({dar})"

        fps = vs.get("r_frame_rate", "")
        fps_str = "Unknown"
        if fps and "/" in fps:
            try:
                num, den = fps.split("/")
                if float(den) > 0:
                    fps_str = f"{round(float(num) / float(den), 2)} fps"
            except Exception:
                pass

        pix_fmt = vs.get("pix_fmt", "Unknown")
        profile = vs.get("profile", "")
        v_br = vs.get("bit_rate")
        v_br_str = f"{int(v_br) // 1000} kbps" if v_br else "Unknown"

        lines.append(f"\n🎬 **Video Stream #{v_idx}:**")
        lines.append(f"• **Codec:** `{v_codec_long}` (`{v_codec}`)")
        if profile:
            lines.append(f"• **Profile:** `{profile}`")
        lines.append(f"• **Resolution:** `{res_str}`")
        lines.append(f"• **Frame Rate:** `{fps_str}`")
        lines.append(f"• **Pixel Format:** `{pix_fmt}`")
        if v_br_str != "Unknown":
            lines.append(f"• **Bitrate:** `{v_br_str}`")

    # 2. Audio Streams
    for i, ast in enumerate(audio_streams):
        a_idx = ast.get("index", i)
        a_codec = ast.get("codec_name", "unknown").upper()
        a_codec_long = ast.get("codec_long_name", a_codec)
        channels = ast.get("channels")
        layout = ast.get("channel_layout")
        ch_str = f"{channels} ch" if channels else "Unknown"
        if layout:
            ch_str += f" ({layout})"
        sr = ast.get("sample_rate")
        sr_str = f"{int(sr)//1000} kHz" if sr else "Unknown"
        a_br = ast.get("bit_rate")
        a_br_str = f"{int(a_br) // 1000} kbps" if a_br else "Unknown"
        tags = ast.get("tags", {})
        lang = tags.get("language", tags.get("LANGUAGE", "und"))
        title = tags.get("title", tags.get("TITLE", ""))

        lines.append(f"\n🎵 **Audio Stream #{a_idx}:**")
        lines.append(f"• **Codec:** `{a_codec_long}` (`{a_codec}`)")
        lines.append(f"• **Channels & Rate:** `{ch_str}`, `{sr_str}`")
        if a_br_str != "Unknown":
            lines.append(f"• **Bitrate:** `{a_br_str}`")
        if lang and lang != "und":
            lines.append(f"• **Language:** `{lang}`")
        if title:
            lines.append(f"• **Title:** `{title}`")

    # 3. Subtitle Streams
    for i, sst in enumerate(subtitle_streams):
        s_idx = sst.get("index", i)
        s_codec = sst.get("codec_name", "unknown").upper()
        tags = sst.get("tags", {})
        lang = tags.get("language", tags.get("LANGUAGE", "und"))
        title = tags.get("title", tags.get("TITLE", ""))
        lines.append(f"\n💬 **Subtitle Stream #{s_idx}:**")
        lines.append(f"• **Codec:** `{s_codec}`")
        if lang and lang != "und":
            lines.append(f"• **Language:** `{lang}`")
        if title:
            lines.append(f"• **Title:** `{title}`")

    # 4. Metadata Tags
    tags = format_info.get("tags", {})
    tag_lines = []
    for k, v in tags.items():
        if k.lower() in ("title", "encoder", "creation_time", "comment", "copyright", "artist"):
            val = str(v).strip()
            if len(val) > 100:
                val = val[:97] + "..."
            tag_lines.append(f"• **{k.capitalize()}:** `{val}`")

    if tag_lines:
        lines.append("\n🏷️ **Metadata Tags:**")
        lines.extend(tag_lines)

    return "\n".join(lines)


def extract_video_streams(probe_data: dict) -> dict:
    """
    Extracts categorized stream info from ffprobe JSON data.
    Returns dict with 'video', 'audio', 'subtitle' lists.
    Each entry has: index, codec_name, codec_long_name, title, language, and type-specific fields.
    """
    streams = probe_data.get("streams", [])
    result = {"video": [], "audio": [], "subtitle": []}

    for stream in streams:
        codec_type = stream.get("codec_type", "unknown")
        tags = stream.get("tags", {})
        info = {
            "index": stream.get("index", 0),
            "codec_name": stream.get("codec_name", "unknown"),
            "codec_long_name": stream.get("codec_long_name", "unknown"),
            "title": tags.get("title", tags.get("TITLE", "")),
            "language": tags.get("language", tags.get("LANGUAGE", "und")),
        }

        if codec_type == "video":
            info["width"] = stream.get("width", 0)
            info["height"] = stream.get("height", 0)
            info["r_frame_rate"] = stream.get("r_frame_rate", "")
            info["pix_fmt"] = stream.get("pix_fmt", "")
            br = stream.get("bit_rate")
            info["bit_rate"] = int(br) if br else 0
            result["video"].append(info)
        elif codec_type == "audio":
            info["channels"] = stream.get("channels", 0)
            info["channel_layout"] = stream.get("channel_layout", "")
            info["sample_rate"] = stream.get("sample_rate", "")
            br = stream.get("bit_rate")
            info["bit_rate"] = int(br) if br else 0
            result["audio"].append(info)
        elif codec_type == "subtitle":
            result["subtitle"].append(info)

    return result


def format_video_metadata_text(
    probe_data: dict,
    fallback_name: str = "video.mp4",
    pending_metadata: Optional[dict] = None,
) -> str:
    """
    Formats ffprobe data into a clean, compact video metadata display text.
    Reflects any pending user changes (modified stream titles or languages) with a marker.
    """
    format_info = probe_data.get("format", {})
    format_tags = format_info.get("tags", {})
    streams_info = extract_video_streams(probe_data)

    pending = pending_metadata or {}
    modified_global_title = pending.get("global_title")
    modified_streams = pending.get("streams", {})

    try:
        file_size = int(format_info.get("size", 0))
    except (ValueError, TypeError):
        file_size = 0
    try:
        duration = float(format_info.get("duration", 0))
    except (ValueError, TypeError):
        duration = 0.0

    orig_global_title = format_tags.get("title", format_tags.get("TITLE", ""))
    active_global_title = modified_global_title if modified_global_title is not None else orig_global_title

    lines = [
        "🏷️ **Video Metadata Editor**\n",
        f"📁 **File:** `{fallback_name}` ({humanbytes(file_size)}, {format_duration(int(duration))})",
    ]

    if active_global_title:
        title_tag = f"• **Video Title:** `{active_global_title}`"
        if modified_global_title is not None and modified_global_title != orig_global_title:
            title_tag += " ✏️"
        lines.append(title_tag)
    else:
        lines.append("• **Video Title:** *(Not set)*")

    lines.append("\n**Streams:**")

    # Video streams
    for i, vs in enumerate(streams_info["video"]):
        s_idx = vs.get("index", i)
        codec = vs.get("codec_name", "?").upper()
        w, h = vs.get("width", 0), vs.get("height", 0)
        res = f"{w}x{h}" if w and h else ""
        fps = vs.get("r_frame_rate", "")
        fps_str = ""
        if "/" in fps:
            try:
                n, d = fps.split("/")
                if float(d) > 0:
                    fps_str = f"{round(float(n)/float(d), 1)}fps"
            except Exception:
                pass
        parts = filter(None, [codec, res, fps_str])
        lines.append(f"• 🎬 **#{s_idx} Video:** `{', '.join(parts)}`")

    # Audio streams
    for i, ast in enumerate(streams_info["audio"]):
        s_idx = ast.get("index", i)
        codec = ast.get("codec_name", "?").upper()
        ch = ast.get("channels", 0)
        ch_str = f"{ch}ch" if ch else ""
        stream_key = f"a:{i}"
        mod_info = modified_streams.get(stream_key, {})
        cur_title = mod_info.get("title", ast.get("title", ""))
        cur_lang = mod_info.get("language", ast.get("language", "und"))
        is_mod = stream_key in modified_streams

        parts = [codec]
        if cur_lang and cur_lang != "und":
            parts.append(cur_lang)
        if ch_str:
            parts.append(ch_str)

        mod_mark = " ✏️" if is_mod else ""
        line = f"• 🎵 **#{s_idx} Audio:** `{', '.join(parts)}`{mod_mark}"
        if cur_title:
            line += f" — *{cur_title}*"
        lines.append(line)

    # Subtitle streams
    for i, sst in enumerate(streams_info["subtitle"]):
        s_idx = sst.get("index", i)
        codec = sst.get("codec_name", "?").upper()
        stream_key = f"s:{i}"
        mod_info = modified_streams.get(stream_key, {})
        cur_title = mod_info.get("title", sst.get("title", ""))
        cur_lang = mod_info.get("language", sst.get("language", "und"))
        is_mod = stream_key in modified_streams

        parts = [codec]
        if cur_lang and cur_lang != "und":
            parts.append(cur_lang)

        mod_mark = " ✏️" if is_mod else ""
        line = f"• 💬 **#{s_idx} Sub:** `{', '.join(parts)}`{mod_mark}"
        if cur_title:
            line += f" — *{cur_title}*"
        lines.append(line)

    lines.append("")
    has_changes = bool(modified_global_title is not None or modified_streams)
    if has_changes:
        lines.append("⚡ **Unsaved changes pending!** Press Apply below when ready.")
    else:
        lines.append("👇 **Select a stream or Video Title below to edit:**")

    return "\n".join(lines)


def apply_all_video_metadata(
    input_path: str,
    output_path: str,
    pending_metadata: dict,
) -> tuple:
    """
    Applies all pending metadata changes (global title + stream title/languages)
    in a single FFmpeg stream-copy pass.
    Returns (success: bool, error_message: str).
    """
    cmd = [
        "ffmpeg", "-y", "-i", input_path,
        "-map", "0",
        "-c", "copy",
    ]

    # Global title
    global_title = pending_metadata.get("global_title")
    if global_title is not None:
        cmd.extend(["-metadata", f"title={global_title}"])

    # Stream-specific metadata
    streams = pending_metadata.get("streams", {})
    for stream_key, meta in streams.items():
        # stream_key format: 'a:0', 's:1', 'v:0'
        title = meta.get("title")
        lang = meta.get("language")
        if title is not None:
            cmd.extend([f"-metadata:s:{stream_key}", f"title={title}"])
        if lang is not None:
            cmd.extend([f"-metadata:s:{stream_key}", f"language={lang}"])

    cmd.append(output_path)

    try:
        res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=300)
        if res.returncode == 0 and os.path.exists(output_path) and os.path.getsize(output_path) > 0:
            return True, ""
        stderr = res.stderr.decode(errors="replace")
        return False, stderr[-400:] if len(stderr) > 400 else stderr
    except subprocess.TimeoutExpired:
        return False, "FFmpeg process timed out (5 minutes)."
    except Exception as e:
        return False, str(e)


def apply_video_stream_metadata(
    input_path: str,
    output_path: str,
    stream_type: str,
    stream_idx: int,
    title: str,
    language: str,
) -> tuple:
    """Backward compatibility wrapper."""
    pending = {
        "streams": {
            f"{stream_type}:{stream_idx}": {"title": title, "language": language}
        }
    }
    return apply_all_video_metadata(input_path, output_path, pending)


def get_all_streams_flat(probe_data: dict) -> list:
    """
    Returns a unified flat list of all streams in the file with their absolute indices.
    Each item:
      - index: int
      - type: 'video' | 'audio' | 'subtitle' | 'other'
      - codec_name: str
      - title: str
      - language: str
      - details: str
    """
    raw_streams = probe_data.get("streams", [])
    flat = []
    v_count = 0
    a_count = 0
    s_count = 0

    for stream in raw_streams:
        idx = stream.get("index", len(flat))
        ctype = stream.get("codec_type", "other")
        codec = stream.get("codec_name", "?").upper()
        tags = stream.get("tags", {})
        title = tags.get("title", tags.get("TITLE", ""))
        lang = tags.get("language", tags.get("LANGUAGE", "und"))

        details_parts = []
        if ctype == "video":
            v_count += 1
            type_num = v_count
            w = stream.get("width")
            h = stream.get("height")
            if w and h:
                details_parts.append(f"{w}x{h}")
            fps = stream.get("r_frame_rate")
            if fps and "/" in fps:
                try:
                    num, den = fps.split("/")
                    if float(den) > 0:
                        fps_val = round(float(num) / float(den), 1)
                        details_parts.append(f"{fps_val} fps")
                except Exception:
                    pass
        elif ctype == "audio":
            a_count += 1
            type_num = a_count
            ch = stream.get("channels")
            if ch:
                details_parts.append(f"{ch} ch")
            sr = stream.get("sample_rate")
            if sr:
                try:
                    details_parts.append(f"{int(sr)//1000} kHz")
                except Exception:
                    pass
        elif ctype == "subtitle":
            s_count += 1
            type_num = s_count
        else:
            type_num = 1

        flat.append({
            "index": idx,
            "type": ctype,
            "type_num": type_num,
            "codec_name": codec,
            "title": title,
            "language": lang,
            "details": ", ".join(details_parts),
        })

    return flat


def format_stream_remover_text(
    probe_data: dict,
    selected_indices: set,
    fallback_name: str = "video.mp4",
) -> str:
    """
    Formats stream remover selection overview in a clean, compact view.
    Displays all streams with concise one-line markers: [REMOVE] or [KEEP].
    """
    streams = get_all_streams_flat(probe_data)
    format_info = probe_data.get("format", {})
    try:
        file_size = int(format_info.get("size", 0))
    except (ValueError, TypeError):
        file_size = 0
    try:
        duration = float(format_info.get("duration", 0))
    except (ValueError, TypeError):
        duration = 0.0

    lines = [
        "🗑️ **Stream Remover**\n",
        f"📁 **File:** `{fallback_name}` ({humanbytes(file_size)}, {format_duration(int(duration))})",
        f"• **Streams Count:** `{len(streams)}`\n",
        "**Streams:**",
    ]

    for st in streams:
        idx = st["index"]
        ctype = st["type"]
        type_icon = "🎬" if ctype == "video" else ("🎵" if ctype == "audio" else ("💬" if ctype == "subtitle" else "📦"))
        type_short = "Video" if ctype == "video" else ("Audio" if ctype == "audio" else ("Sub" if ctype == "subtitle" else ctype))

        status_mark = "❌ `[REMOVE]`" if idx in selected_indices else "✅ `[KEEP]`"

        parts = [st["codec_name"]]
        if st["language"] and st["language"] != "und":
            parts.append(st["language"])
        if st["details"]:
            parts.append(st["details"])

        line = f"• {status_mark} **#{idx}** {type_icon} **{type_short}:** `{', '.join(parts)}`"
        if st["title"]:
            line += f" — *{st['title']}*"
        lines.append(line)

    lines.append("")
    selected_count = len(selected_indices)
    if selected_count > 0:
        lines.append(f"⚠️ **{selected_count} stream(s) marked for removal.**")
        lines.append("Press **Confirm & Remove** below to execute (lossless stream copy).")
    else:
        lines.append("👇 **Click on stream buttons below to toggle for removal:**")

    return "\n".join(lines)


def remove_streams_from_video(
    input_path: str,
    output_path: str,
    remove_indices: list,
) -> tuple:
    """
    Removes specified streams from video using FFmpeg negative mapping (-map -0:{idx}).
    Executes lossless stream copy (-c copy).
    Returns (success: bool, error_message: str).
    """
    cmd = [
        "ffmpeg", "-y", "-i", input_path,
        "-map", "0",
    ]
    for idx in remove_indices:
        cmd.extend(["-map", f"-0:{idx}"])

    cmd.extend(["-c", "copy", output_path])

    try:
        res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=300)
        if res.returncode == 0 and os.path.exists(output_path) and os.path.getsize(output_path) > 0:
            return True, ""
        stderr = res.stderr.decode(errors="replace")
        return False, stderr[-400:] if len(stderr) > 400 else stderr
    except subprocess.TimeoutExpired:
        return False, "FFmpeg process timed out (5 minutes)."
    except Exception as e:
        return False, str(e)


def get_stream_extension(codec_type: str, codec_name: str, orig_ext: str = ".mp4") -> str:
    """Returns the most appropriate file extension for the given stream codec."""
    cname = codec_name.lower()
    if codec_type == "audio":
        if "aac" in cname:
            return ".m4a"
        elif "mp3" in cname:
            return ".mp3"
        elif "opus" in cname:
            return ".opus"
        elif "flac" in cname:
            return ".flac"
        elif "ac3" in cname or "eac3" in cname:
            return ".ac3"
        elif "vorbis" in cname or "ogg" in cname:
            return ".ogg"
        elif "wav" in cname or "pcm" in cname:
            return ".wav"
        elif "alac" in cname:
            return ".m4a"
        return ".m4a"

    elif codec_type == "subtitle":
        if "ass" in cname or "ssa" in cname:
            return ".ass"
        elif "vtt" in cname:
            return ".vtt"
        return ".srt"

    elif codec_type == "video":
        return orig_ext if orig_ext else ".mp4"

    return ".bin"


def format_stream_extractor_text(
    probe_data: dict,
    selected_indices: set,
    fallback_name: str = "video.mp4",
) -> str:
    """
    Formats stream extractor selection overview in a clean, compact view.
    Displays all streams with concise one-line markers: [EXTRACT] or [SKIP].
    """
    streams = get_all_streams_flat(probe_data)
    format_info = probe_data.get("format", {})
    try:
        file_size = int(format_info.get("size", 0))
    except (ValueError, TypeError):
        file_size = 0
    try:
        duration = float(format_info.get("duration", 0))
    except (ValueError, TypeError):
        duration = 0.0

    lines = [
        "📤 **Stream Extractor**\n",
        f"📁 **Source:** `{fallback_name}` ({humanbytes(file_size)}, {format_duration(int(duration))})",
        f"• **Streams Count:** `{len(streams)}`\n",
        "**Available Streams:**",
    ]

    for st in streams:
        idx = st["index"]
        ctype = st["type"]
        type_icon = "🎬" if ctype == "video" else ("🎵" if ctype == "audio" else ("💬" if ctype == "subtitle" else "📦"))
        type_short = "Video" if ctype == "video" else ("Audio" if ctype == "audio" else ("Sub" if ctype == "subtitle" else ctype))

        status_mark = "📥 `[EXTRACT]`" if idx in selected_indices else "▫️ `[SKIP]`"

        parts = [st["codec_name"]]
        if st["language"] and st["language"] != "und":
            parts.append(st["language"])
        if st["details"]:
            parts.append(st["details"])

        line = f"• {status_mark} **#{idx}** {type_icon} **{type_short}:** `{', '.join(parts)}`"
        if st["title"]:
            line += f" — *{st['title']}*"
        lines.append(line)

    lines.append("")
    selected_count = len(selected_indices)
    if selected_count > 0:
        lines.append(f"⚡ **{selected_count} stream(s) marked for extraction.**")
        lines.append("Press **Extract Selected** below to receive the files directly.")
    else:
        lines.append("👇 **Click on stream buttons below to toggle for extraction:**")

    return "\n".join(lines)


def extract_single_stream(
    input_path: str,
    output_path: str,
    stream_index: int,
    codec_type: str,
    codec_name: str,
) -> tuple:
    """
    Extracts a single stream from video using FFmpeg stream copy or conversion.
    - Audio: lossless stream copy (-c copy)
    - Subtitle: converts mov_text/subrip to clean .srt, or direct .ass stream copy
    - Video: lossless video extraction (-an -sn -c copy)
    Returns (success: bool, error_message: str).
    """
    cname = codec_name.lower()
    if codec_type == "subtitle":
        # mov_text or subrip converted cleanly to SRT text
        if "mov_text" in cname or "subrip" in cname or "srt" in cname or output_path.endswith(".srt"):
            cmd = [
                "ffmpeg", "-y", "-i", input_path,
                "-map", f"0:{stream_index}",
                output_path,
            ]
        else:
            cmd = [
                "ffmpeg", "-y", "-i", input_path,
                "-map", f"0:{stream_index}",
                "-c", "copy",
                output_path,
            ]
    elif codec_type == "audio":
        cmd = [
            "ffmpeg", "-y", "-i", input_path,
            "-map", f"0:{stream_index}",
            "-vn", "-sn",
            "-c", "copy",
            output_path,
        ]
    elif codec_type == "video":
        cmd = [
            "ffmpeg", "-y", "-i", input_path,
            "-map", f"0:{stream_index}",
            "-an", "-sn",
            "-c", "copy",
            output_path,
        ]
    else:
        cmd = [
            "ffmpeg", "-y", "-i", input_path,
            "-map", f"0:{stream_index}",
            "-c", "copy",
            output_path,
        ]

    try:
        res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=300)
        if res.returncode == 0 and os.path.exists(output_path) and os.path.getsize(output_path) > 0:
            return True, ""

        # If audio stream-copy failed due to container mismatch, fallback to high-quality re-encode
        if codec_type == "audio":
            fallback_cmd = [
                "ffmpeg", "-y", "-i", input_path,
                "-map", f"0:{stream_index}",
                "-vn", "-sn",
                output_path,
            ]
            res_fb = subprocess.run(fallback_cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=300)
            if res_fb.returncode == 0 and os.path.exists(output_path) and os.path.getsize(output_path) > 0:
                return True, ""

        stderr = res.stderr.decode(errors="replace")
        return False, stderr[-400:] if len(stderr) > 400 else stderr
    except subprocess.TimeoutExpired:
        return False, "FFmpeg process timed out (5 minutes)."
    except Exception as e:
        return False, str(e)


def parse_time_str(s: str) -> float:
    """Parses timestamp string like '00:09:09', '09:09', or '549' to seconds."""
    try:
        parts = s.split(":")
        if len(parts) == 3:
            return float(parts[0]) * 3600 + float(parts[1]) * 60 + float(parts[2])
        elif len(parts) == 2:
            return float(parts[0]) * 60 + float(parts[1])
        else:
            return float(s)
    except Exception:
        return 0.0


def detect_expected_duration(cmd_tokens: list[str], input_duration: float) -> float:
    """Detects expected output duration from command flags (-t, -to, -ss) or input file."""
    ss_val = 0.0
    to_val = 0.0
    t_val = 0.0
    for i, tok in enumerate(cmd_tokens):
        if tok == "-ss" and i + 1 < len(cmd_tokens):
            ss_val = parse_time_str(cmd_tokens[i + 1])
        elif tok == "-to" and i + 1 < len(cmd_tokens):
            to_val = parse_time_str(cmd_tokens[i + 1])
        elif tok == "-t" and i + 1 < len(cmd_tokens):
            t_val = parse_time_str(cmd_tokens[i + 1])

    if t_val > 0:
        return t_val
    if to_val > 0 and to_val > ss_val:
        return to_val - ss_val
    if input_duration > 0 and ss_val > 0 and input_duration > ss_val:
        return input_duration - ss_val
    return input_duration if input_duration > 0 else 0.0


def trim_audio_file(
    input_path: str,
    output_path: str,
    start_time: str,
    end_time: str,
    accurate: bool = False,
) -> bool:
    """
    Trims audio from start_time to end_time.
    If accurate is False, uses Fast Copy (-c copy).
    If accurate is True (or if Fast Copy fails), re-encodes boundary frames.
    """
    if not accurate:
        # Fast copy mode (stream copy)
        cmd = [
            "ffmpeg", "-y",
            "-ss", start_time,
            "-to", end_time,
            "-i", input_path,
            "-codec", "copy",
            output_path,
        ]
        res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        if res.returncode == 0 and os.path.exists(output_path) and os.path.getsize(output_path) > 0:
            return True
        logger.info("Fast copy trim failed or unsupported for this codec, falling back to frame-accurate mode.")

    # Frame accuracy mode (re-encodes audio)
    cmd = [
        "ffmpeg", "-y",
        "-ss", start_time,
        "-to", end_time,
        "-i", input_path,
        output_path,
    ]
    res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    return res.returncode == 0 and os.path.exists(output_path) and os.path.getsize(output_path) > 0


async def trim_audio_file_with_progress(
    input_path: str,
    output_path: str,
    start_time: str,
    end_time: str,
    accurate: bool,
    message: Message,
    task_id: str,
) -> bool:
    """
    Trims audio with live progress reporting, ETA, Elapsed, Speed, Refresh, and Cancel support.
    """
    start_sec = parse_time_str(start_time)
    end_sec = parse_time_str(end_time)
    duration = end_sec - start_sec if end_sec > start_sec else 0.0

    if not accurate:
        # Try ultra-fast stream copy first
        cmd = [
            "ffmpeg", "-y",
            "-ss", start_time,
            "-to", end_time,
            "-i", input_path,
            "-codec", "copy",
            output_path,
        ]
        res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        if res.returncode == 0 and os.path.exists(output_path) and os.path.getsize(output_path) > 0:
            return True
        logger.info("Fast copy trim fallback to frame-accurate mode.")

    # Frame accuracy mode with live progress
    cmd = [
        "ffmpeg", "-y",
        "-ss", start_time,
        "-to", end_time,
        "-i", input_path,
        output_path,
    ]
    success, _ = await execute_ffmpeg_with_progress(
        cmd=cmd,
        total_duration=duration,
        message=message,
        task_id=task_id,
        action_name="✂️ **Trimming Audio (Frame Accuracy)...**",
    )
    return success and os.path.exists(output_path) and os.path.getsize(output_path) > 0


def trim_video_file(
    input_path: str,
    output_path: str,
    start_time: str,
    end_time: str,
    accurate: bool = False,
) -> bool:
    """
    Trims video from start_time to end_time.
    If accurate is False, uses Fast Copy (-c copy).
    If accurate is True (or if Fast Copy fails), re-encodes frames.
    """
    if not accurate:
        # Fast copy mode (stream copy)
        cmd = [
            "ffmpeg", "-y",
            "-ss", start_time,
            "-to", end_time,
            "-i", input_path,
            "-codec", "copy",
            "-avoid_negative_ts", "make_zero",
            output_path,
        ]
        res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        if res.returncode == 0 and os.path.exists(output_path) and os.path.getsize(output_path) > 0:
            return True
        logger.info("Fast copy video trim failed, falling back to frame-accurate mode.")

    # Frame accuracy mode (re-encodes video)
    cmd = [
        "ffmpeg", "-y",
        "-ss", start_time,
        "-to", end_time,
        "-i", input_path,
        output_path,
    ]
    res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    return res.returncode == 0 and os.path.exists(output_path) and os.path.getsize(output_path) > 0


async def trim_video_file_with_progress(
    input_path: str,
    output_path: str,
    start_time: str,
    end_time: str,
    accurate: bool,
    message: Message,
    task_id: str,
) -> bool:
    """
    Trims video with live progress reporting, ETA, Elapsed, Speed, Refresh, and Cancel support.
    """
    start_sec = parse_time_str(start_time)
    end_sec = parse_time_str(end_time)
    duration = end_sec - start_sec if end_sec > start_sec else 0.0

    if not accurate:
        cmd = [
            "ffmpeg", "-y",
            "-ss", start_time,
            "-to", end_time,
            "-i", input_path,
            "-codec", "copy",
            "-avoid_negative_ts", "make_zero",
            output_path,
        ]
        res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        if res.returncode == 0 and os.path.exists(output_path) and os.path.getsize(output_path) > 0:
            return True
        logger.info("Fast copy video trim fallback to frame-accurate mode.")

    cmd = [
        "ffmpeg", "-y",
        "-ss", start_time,
        "-to", end_time,
        "-i", input_path,
        output_path,
    ]
    success, _ = await execute_ffmpeg_with_progress(
        cmd=cmd,
        total_duration=duration,
        message=message,
        task_id=task_id,
        action_name="✂️ **Trimming Video (Frame Accuracy)...**",
    )
    return success and os.path.exists(output_path) and os.path.getsize(output_path) > 0


def build_audio_merger_text(tracks: list[dict]) -> str:
    """Builds the Audio Merger queue status message."""
    lines = [
        "🔀 **Audio Merger Queue**\n",
        f"**Queued Tracks ({len(tracks)}):**",
    ]
    total_size = 0
    total_duration = 0
    for idx, tr in enumerate(tracks, start=1):
        dur = format_duration(tr.get("duration", 0))
        sz = humanbytes(tr.get("file_size", 0))
        name = tr.get("file_name", f"Track {idx}")
        total_size += tr.get("file_size", 0)
        total_duration += tr.get("duration", 0)
        lines.append(f"{idx}️⃣ `{name}` [{dur}] ({sz})")

    lines.append(
        f"\n📊 **Total Duration:** `{format_duration(total_duration)}` | **Total Size:** `{humanbytes(total_size)}`"
    )
    if len(tracks) < 2:
        lines.append(
            "\n📥 **Please send the next audio file(s) to add to the merge queue.**\n"
            "*(Send another audio file, or click Cancel & Back)*"
        )
    else:
        lines.append(
            "\n📥 Send another audio to add more, or click **🔀 Merge Now** below to start!"
        )
    return "\n".join(lines)


def build_video_merge_audio_text(video_name: str, tracks: list[dict]) -> str:
    """Builds the Video Audio Muxer queue status message in a clean, compact view."""
    lines = [
        "🎵 **Merge Audio Tracks to Video**\n",
        f"📁 **Target Video:** `{video_name}`",
    ]

    if not tracks:
        lines.append("\nℹ️ **No audio tracks queued yet.**")
        lines.append("\nPlease send the audio file you want to add to this video.")
        lines.append("*(1st audio sent becomes Track #1, 2nd becomes Track #2, etc.)*")
    else:
        lines.append(f"\n**Queued New Audio Tracks ({len(tracks)}):**")
        total_size = 0
        for idx, tr in enumerate(tracks, start=1):
            dur = format_duration(tr.get("duration", 0))
            sz = humanbytes(tr.get("file_size", 0))
            name = tr.get("file_name", f"Audio Track {idx}")
            total_size += tr.get("file_size", 0)
            lines.append(f"• {idx}️⃣ **Track #{idx}:** `{name}` ({dur}, {sz})")

        lines.append("\n📌 **Track Order:**")
        lines.append("• New audios are placed as primary tracks (`#1`, `#2`...).")
        lines.append("• Original video audio (if any) is placed as the **LAST** track.")
        lines.append("\n👇 Send another audio to add more, or press **Merge Audio Now** below:")

    return "\n".join(lines)


def merge_audio_into_video(
    video_path: str,
    audio_paths: list,
    output_path: str,
    has_orig_audio: bool = True,
) -> tuple:
    """
    Merges one or more external audio tracks into a video file as discrete streams.
    Stream order:
      1. Video stream(s): -map 0:v:0?
      2. New audio tracks in the order they were sent: -map 1:a:0?, -map 2:a:0?, ...
      3. Original video audio tracks (if any): -map 0:a? (as last track)
      4. Subtitle streams (if any): -map 0:s?
    Lossless stream-copy (-c copy) is used for ultra-fast execution.
    Returns (success: bool, error_message: str).
    """
    video_path = str(video_path)
    output_path = str(output_path)
    audio_paths = [str(ap) for ap in audio_paths]

    cmd = ["ffmpeg", "-y", "-i", video_path]
    for ap in audio_paths:
        cmd.extend(["-i", ap])

    # 1. Map video stream
    cmd.extend(["-map", "0:v:0?"])

    # 2. Map new audio streams in exact order
    for i in range(1, len(audio_paths) + 1):
        cmd.extend(["-map", f"{i}:a:0?"])

    # 3. Map original audio streams as the last audio track(s)
    if has_orig_audio:
        cmd.extend(["-map", "0:a?"])

    # 4. Map existing subtitles if any
    cmd.extend(["-map", "0:s?"])

    # 5. Set 1st audio track as default and clear default from others
    cmd.extend(["-disposition:a", "0", "-disposition:a:0", "default"])

    # 6. Assign track titles from file names
    for idx, ap in enumerate(audio_paths):
        audio_title = os.path.splitext(os.path.basename(ap))[0]
        if audio_title.startswith("audio_"):
            parts = audio_title.split("_", 2)
            if len(parts) >= 3:
                audio_title = parts[2]
        cmd.extend([f"-metadata:s:a:{idx}", f"title={audio_title}"])

    cmd.extend(["-c", "copy", output_path])

    try:
        res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=600)
        if res.returncode == 0 and os.path.exists(output_path) and os.path.getsize(output_path) > 0:
            return True, ""

        # Fallback if stream-copy fails due to container incompatibility:
        # Re-encode only the audio streams to AAC while copying video stream
        fallback_cmd = ["ffmpeg", "-y", "-i", video_path]
        for ap in audio_paths:
            fallback_cmd.extend(["-i", ap])

        fallback_cmd.extend(["-map", "0:v:0?"])
        for i in range(1, len(audio_paths) + 1):
            fallback_cmd.extend(["-map", f"{i}:a:0?"])
        if has_orig_audio:
            fallback_cmd.extend(["-map", "0:a?"])
        fallback_cmd.extend(["-map", "0:s?"])

        fallback_cmd.extend(["-disposition:a", "0", "-disposition:a:0", "default"])

        for idx, ap in enumerate(audio_paths):
            audio_title = os.path.splitext(os.path.basename(ap))[0]
            if audio_title.startswith("audio_"):
                parts = audio_title.split("_", 2)
                if len(parts) >= 3:
                    audio_title = parts[2]
            fallback_cmd.extend([f"-metadata:s:a:{idx}", f"title={audio_title}"])

        fallback_cmd.extend(["-c:v", "copy", "-c:a", "aac", "-b:a", "192k", "-c:s", "copy", output_path])
        res_fb = subprocess.run(fallback_cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=600)
        if res_fb.returncode == 0 and os.path.exists(output_path) and os.path.getsize(output_path) > 0:
            return True, ""

        stderr = res.stderr.decode(errors="replace")
        return False, stderr[-400:] if len(stderr) > 400 else stderr
    except subprocess.TimeoutExpired:
        return False, "FFmpeg process timed out (10 minutes)."
    except Exception as e:
        return False, str(e)


def build_video_merge_subtitle_text(video_name: str, tracks: list[dict]) -> str:
    """Builds the Video Subtitle Muxer queue status message in a clean, compact view."""
    lines = [
        "💬 **Merge Subtitles to Video**\n",
        f"📁 **Target Video:** `{video_name}`",
    ]

    if not tracks:
        lines.append("\nℹ️ **No subtitle files queued yet.**")
        lines.append("\nPlease send the subtitle file(s) (`.srt`, `.ass`, `.vtt`, `.sub`, etc.) you want to add to this video.")
        lines.append("*(1st subtitle sent becomes Subtitle Track #1, 2nd becomes Track #2, etc.)*")
    else:
        lines.append(f"\n**Queued New Subtitle Tracks ({len(tracks)}):**")
        total_size = 0
        for idx, tr in enumerate(tracks, start=1):
            sz = humanbytes(tr.get("file_size", 0))
            name = tr.get("file_name", f"Subtitle Track {idx}.srt")
            total_size += tr.get("file_size", 0)
            lines.append(f"• {idx}️⃣ **Track #{idx}:** `{name}` ({sz})")

        lines.append("\n📌 **Track Order:**")
        lines.append("• New subtitles are placed as primary subtitle tracks (`#1`, `#2`...).")
        lines.append("• Original video subtitles (if any) are kept after.")
        lines.append("\n👇 Send another subtitle to add more, or press **Merge Subtitles Now** below:")

    return "\n".join(lines)


def merge_subtitles_into_video(
    video_path: str,
    subtitle_paths: list,
    output_path: str,
    has_orig_sub: bool = True,
) -> tuple:
    """
    Merges one or more external subtitle files (.srt, .ass, .vtt, etc.) into a video file as discrete streams.
    Stream order:
      1. Video stream(s): -map 0:v?
      2. Audio stream(s): -map 0:a?
      3. New subtitle tracks in the exact order they were sent: -map 1:0, -map 2:0, ...
      4. Original video subtitle tracks (if any): -map 0:s?
    Uses stream-copy for zero quality loss and instant processing.
    If target is MP4 and subtitles contain ASS/SSA or fail with mov_text, switches to MKV container.
    Returns (success: bool, final_output_path: str, error_message: str).
    """
    video_path = str(video_path)
    output_path = str(output_path)
    subtitle_paths = [str(sp) for sp in subtitle_paths]

    has_ass = any(
        sp.lower().endswith((".ass", ".ssa"))
        for sp in subtitle_paths
    )

    base, ext = os.path.splitext(output_path)
    target_out = output_path
    if ext.lower() == ".mp4" and has_ass:
        target_out = f"{base}.mkv"

    def build_cmd(out_file, sub_codec=None):
        cmd = ["ffmpeg", "-y", "-i", video_path]
        for sp in subtitle_paths:
            cmd.extend(["-i", sp])

        cmd.extend(["-map", "0:v?"])
        cmd.extend(["-map", "0:a?"])

        for i in range(1, len(subtitle_paths) + 1):
            cmd.extend(["-map", f"{i}:0"])

        if has_orig_sub:
            cmd.extend(["-map", "0:s?"])

        for idx, sp in enumerate(subtitle_paths):
            sub_title = os.path.splitext(os.path.basename(sp))[0]
            if "_" in sub_title and sub_title.startswith("sub_"):
                parts = sub_title.split("_", 2)
                if len(parts) >= 3:
                    sub_title = parts[2]
            cmd.extend([f"-metadata:s:s:{idx}", f"title={sub_title}"])

        if out_file.lower().endswith(".mkv"):
            cmd.extend(["-c", "copy", out_file])
        elif sub_codec:
            cmd.extend(["-c:v", "copy", "-c:a", "copy", "-c:s", sub_codec, out_file])
        else:
            cmd.extend(["-c", "copy", out_file])
        return cmd

    try:
        if target_out.lower().endswith(".mp4"):
            cmd = build_cmd(target_out, sub_codec="mov_text")
        else:
            cmd = build_cmd(target_out)

        res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=600)
        if res.returncode == 0 and os.path.exists(target_out) and os.path.getsize(target_out) > 0:
            return True, target_out, ""

        # Fallback to MKV if MP4 container refused the subtitle format
        if target_out.lower().endswith(".mp4"):
            mkv_out = f"{base}.mkv"
            cmd_mkv = build_cmd(mkv_out)
            res_mkv = subprocess.run(cmd_mkv, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=600)
            if res_mkv.returncode == 0 and os.path.exists(mkv_out) and os.path.getsize(mkv_out) > 0:
                return True, mkv_out, ""

        stderr = res.stderr.decode(errors="replace")
        return False, target_out, stderr[-400:] if len(stderr) > 400 else stderr
    except subprocess.TimeoutExpired:
        return False, target_out, "FFmpeg process timed out (10 minutes)."
    except Exception as e:
        return False, target_out, str(e)


def build_video_merger_text(videos: list[dict]) -> str:
    """Builds the Video Merger queue status message in a clean, compact view."""
    lines = [
        "🔀 **Video Merger Queue (Fast Copy)**\n",
        f"**Queued Videos ({len(videos)}):**",
    ]
    total_size = 0
    total_duration = 0
    for idx, v in enumerate(videos, start=1):
        dur = format_duration(v.get("duration", 0))
        sz = humanbytes(v.get("file_size", 0))
        name = v.get("file_name", f"Video {idx}.mp4")
        total_size += v.get("file_size", 0)
        total_duration += v.get("duration", 0)
        lines.append(f"{idx}️⃣ `{name}` [{dur}] ({sz})")

    lines.append("")
    lines.append(f"• **Total Duration:** `{format_duration(total_duration)}`")
    lines.append(f"• **Combined Size:** `~{humanbytes(total_size)}`")
    lines.append("• **Method:** ⚡ Fast Copy (Zero quality loss, concat demuxer)")
    if len(videos) < 2:
        lines.append("\n📥 Please send the next video file(s) to add to the merge queue.")
    else:
        lines.append("\n📥 Send another video to add more, or press **🔀 Merge Videos Now** below:")
    return "\n".join(lines)


def fast_merge_video_files(input_paths: list[str], output_path: str) -> tuple:
    """
    Merges multiple video files sequentially using FFmpeg Concat Demuxer with Fast Copy (-c copy).
    Ultra-fast execution with 100% original quality preserved.
    Returns (success: bool, error_message: str).
    """
    if not input_paths:
        return False, "No input videos provided."

    input_paths = [str(p) for p in input_paths]
    output_path = str(output_path)

    base_dir = os.path.dirname(output_path)
    concat_list_file = os.path.join(base_dir, "concat_videos_list.txt")

    try:
        with open(concat_list_file, "w", encoding="utf-8") as f:
            for p in input_paths:
                safe_path = os.path.abspath(p).replace("\\", "/")
                f.write(f"file '{safe_path}'\n")

        cmd = [
            "ffmpeg", "-y",
            "-f", "concat",
            "-safe", "0",
            "-i", concat_list_file,
            "-c", "copy",
            "-avoid_negative_ts", "make_zero",
            "-fflags", "+genpts",
            output_path,
        ]

        res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=900)
        if res.returncode == 0 and os.path.exists(output_path) and os.path.getsize(output_path) > 0:
            return True, ""

        stderr = res.stderr.decode(errors="replace")
        return False, stderr[-400:] if len(stderr) > 400 else stderr
    except subprocess.TimeoutExpired:
        return False, "FFmpeg concat process timed out (15 minutes)."
    except Exception as e:
        return False, str(e)
    finally:
        if os.path.exists(concat_list_file):
            try:
                os.remove(concat_list_file)
            except Exception:
                pass


async def merge_audio_files_with_progress(
    input_paths: list[str],
    output_path: str,
    total_duration: float,
    message: Message,
    task_id: str,
) -> bool:
    """
    Merges multiple audio files into a single unified audio file using FFmpeg filter_complex concat.
    Normalizes audio sample rates and channels to prevent format mismatch errors.
    Displays live progress with speed, ETA, elapsed, Refresh, and Cancel.
    """
    if not input_paths:
        return False

    input_paths = [str(p) for p in input_paths]
    output_path = str(output_path)

    cmd = ["ffmpeg", "-y"]
    for path in input_paths:
        cmd.extend(["-i", path])

    filter_parts = [
        f"[{i}:a]aformat=sample_rates=44100:channel_layouts=stereo[a{i}]"
        for i in range(len(input_paths))
    ]
    concat_inputs = "".join(f"[a{i}]" for i in range(len(input_paths)))
    filter_parts.append(f"{concat_inputs}concat=n={len(input_paths)}:v=0:a=1[out]")
    filter_expr = ";".join(filter_parts)

    _, ext = os.path.splitext(output_path)
    ext = ext.lower()
    if ext in (".m4a", ".mp4", ".aac"):
        codec_args = ["-c:a", "aac", "-b:a", "192k"]
    elif ext == ".flac":
        codec_args = ["-c:a", "flac"]
    elif ext in (".ogg", ".opus"):
        codec_args = ["-c:a", "libopus", "-b:a", "128k"]
    else:
        codec_args = ["-c:a", "libmp3lame", "-b:a", "192k"]

    cmd.extend(["-filter_complex", filter_expr, "-map", "[out]"] + codec_args + [output_path])

    success, _ = await execute_ffmpeg_with_progress(
        cmd=cmd,
        total_duration=total_duration,
        message=message,
        task_id=task_id,
        action_name=f"🔀 **Merging {len(input_paths)} Audio Tracks...**",
    )
    return success and os.path.exists(output_path) and os.path.getsize(output_path) > 0


def build_custom_ffmpeg_command(user_input: str, input_path: str, output_path: str) -> list[str]:
    """
    Safely parses user-supplied FFmpeg arguments/command and injects proper input/output paths.
    Supports:
      - '-af "volume=1.5"'
      - '-b:a 320k'
      - 'ffmpeg -i song.mp3 -af "atempo=1.2" out.mp3'
    """
    tokens = shlex.split(user_input.strip())
    if tokens and tokens[0].lower() == "ffmpeg":
        tokens = tokens[1:]

    filtered = []
    skip_next = False
    for token in tokens:
        if skip_next:
            skip_next = False
            continue
        if token == "-i":
            skip_next = True
            continue
        if token == "-y":
            continue
        filtered.append(token)

    # If user provided a dummy output filename at the end, drop it
    if filtered and not filtered[-1].startswith("-"):
        last = filtered[-1].lower()
        if any(last.endswith(ext) for ext in AUDIO_EXTENSIONS):
            filtered.pop()

    return ["ffmpeg", "-y", "-i", input_path] + filtered + [output_path]


async def execute_ffmpeg_with_progress(
    cmd: list[str],
    total_duration: float,
    message: Message,
    task_id: str,
    action_name: str = "⚙️ **Processing Audio with FFmpeg...**",
    interval: float = 8.0,
) -> Tuple[bool, str]:
    """
    Executes an FFmpeg command asynchronously with real-time live progress updates,
    ETA, Elapsed, Speed, [ 🔄 Refresh ], and instant [ 🚫 Cancel Process ] support.
    """
    # Inject -progress pipe:1 -nostats right after "ffmpeg -y"
    progress_cmd = []
    inserted = False
    for tok in cmd:
        progress_cmd.append(tok)
        if not inserted and tok in ("ffmpeg", "-y"):
            progress_cmd.extend(["-progress", "pipe:1", "-nostats"])
            inserted = True
    if not inserted:
        progress_cmd = ["ffmpeg", "-y", "-progress", "pipe:1", "-nostats"] + cmd[1:]

    start_time = time.time()
    last_update_time = 0.0
    first_call = True

    try:
        proc = await asyncio.create_subprocess_exec(
            *progress_cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
    except Exception as e:
        return False, f"Failed to start FFmpeg process: {e}"

    stderr_lines = []

    async def drain_stderr():
        while True:
            line = await proc.stderr.readline()
            if not line:
                break
            stderr_lines.append(line.decode(errors="ignore"))

    drain_task = asyncio.create_task(drain_stderr())

    curr_sec = 0.0
    speed_str = "0.00x"
    percent = 0.0
    bar = "▱" * 10
    eta = 0.0
    elapsed = 0.0

    try:
        while True:
            if task_id in CANCELLED_TASKS:
                try:
                    proc.kill()
                except Exception:
                    pass
                await drain_task
                raise StopTransmission

            line = await proc.stdout.readline()
            if not line:
                break

            text = line.decode(errors="ignore").strip()
            if not text:
                continue

            if text.startswith("out_time_us="):
                val = text.split("=", 1)[1].strip()
                if val.isdigit():
                    curr_sec = int(val) / 1_000_000.0
            elif text.startswith("speed="):
                raw_speed = text.split("=", 1)[1].strip()
                if raw_speed and raw_speed != "N/A":
                    speed_str = raw_speed
            elif text == "progress=end":
                if total_duration > 0:
                    curr_sec = total_duration
                percent = 100.0

            now = time.time()
            elapsed = now - start_time
            if total_duration > 0:
                percent = min(100.0, max(0.0, (curr_sec / total_duration) * 100.0))
                speed_num = 0.0
                try:
                    speed_num = float(speed_str.rstrip("xX"))
                except Exception:
                    speed_num = (curr_sec / elapsed) if elapsed > 0 else 0.0
                if speed_num > 0 and curr_sec < total_duration:
                    eta = max(0.0, (total_duration - curr_sec) / speed_num)
                else:
                    eta = 0.0
            else:
                percent = 0.0
                eta = 0.0

            completed_blocks = min(10, max(0, int(percent / 10)))
            remaining_blocks = 10 - completed_blocks
            bar = "▰" * completed_blocks + "▱" * remaining_blocks

            # Update ACTIVE_PROGRESS for instant [ 🔄 Refresh ]
            ACTIVE_PROGRESS[task_id] = {
                "is_ffmpeg": True,
                "action_name": action_name,
                "current_sec": curr_sec,
                "total_sec": total_duration,
                "speed_str": speed_str,
                "eta": eta,
                "elapsed": elapsed,
                "percent": percent,
                "bar": bar,
            }

            # Periodic update to Telegram message (every 8s or first call)
            if first_call or (now - last_update_time) >= interval:
                first_call = False
                last_update_time = now
                msg_text = format_ffmpeg_progress_text(
                    action_name=action_name,
                    current_sec=curr_sec,
                    total_sec=total_duration,
                    speed_str=speed_str,
                    eta=eta,
                    elapsed=elapsed,
                    percent=percent,
                    bar=bar,
                )
                try:
                    await message.edit_text(
                        text=msg_text,
                        reply_markup=get_cancel_process_keyboard(task_id),
                    )
                except StopTransmission:
                    raise
                except Exception:
                    pass

        returncode = await proc.wait()
        await drain_task

        if returncode == 0:
            return True, ""

        err_full = "".join(stderr_lines).strip()
        last_error = "\n".join(err_full.splitlines()[-10:]) if err_full else "Unknown FFmpeg error"
        return False, last_error

    except StopTransmission:
        try:
            proc.kill()
        except Exception:
            pass
        await drain_task
        raise


def execute_ffmpeg_command(cmd: list[str], timeout: int = 300) -> Tuple[bool, str]:
    """
    Executes an FFmpeg command list synchronously (fallback).
    Returns:
      (success: bool, error_message: str)
    """
    try:
        proc = subprocess.run(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=timeout,
        )
        if proc.returncode == 0:
            return True, ""
        err_lines = proc.stderr.strip().splitlines()
        last_error = "\n".join(err_lines[-10:]) if err_lines else "Unknown FFmpeg error"
        return False, last_error
    except subprocess.TimeoutExpired:
        return False, "FFmpeg command timed out (maximum 5 minutes allowed)."
    except Exception as e:
        return False, str(e)


# ==============================================================================
# CUSTOM THUMBNAIL MANAGEMENT
# ==============================================================================

THUMBNAIL_DIR = "thumbnails"


def get_user_thumbnail(user_id: int) -> Optional[str]:
    """
    Returns the file path to the user's custom thumbnail if it exists, otherwise None.
    """
    thumb_path = os.path.join(THUMBNAIL_DIR, f"{user_id}.jpg")
    if os.path.exists(thumb_path) and os.path.getsize(thumb_path) > 0:
        return thumb_path
    return None


def save_user_thumbnail(user_id: int, input_photo_path: str) -> Optional[str]:
    """
    Resizes/converts the uploaded photo into a valid Telegram thumbnail (JPEG, <= 320x320, < 200KB)
    using FFmpeg and saves it to thumbnails/{user_id}.jpg.
    Returns the saved thumbnail path or None if failed.
    """
    os.makedirs(THUMBNAIL_DIR, exist_ok=True)
    target_path = os.path.join(THUMBNAIL_DIR, f"{user_id}.jpg")

    cmd = [
        "ffmpeg", "-y",
        "-i", input_photo_path,
        "-vf", "scale=320:320:force_original_aspect_ratio=decrease",
        "-q:v", "2",
        target_path,
    ]
    try:
        res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=15)
        if res.returncode == 0 and os.path.exists(target_path) and os.path.getsize(target_path) > 0:
            return target_path
    except Exception as e:
        logger.error(f"Failed to process thumbnail for user {user_id}: {e}")

    # Fallback: copy file directly
    try:
        import shutil
        shutil.copy2(input_photo_path, target_path)
        return target_path
    except Exception:
        return None


def delete_user_thumbnail(user_id: int) -> bool:
    """
    Deletes the user's custom thumbnail if it exists. Returns True if deleted, False otherwise.
    """
    thumb_path = os.path.join(THUMBNAIL_DIR, f"{user_id}.jpg")
    if os.path.exists(thumb_path):
        try:
            os.remove(thumb_path)
            return True
        except Exception as e:
            logger.error(f"Failed to delete thumbnail {thumb_path}: {e}")
    return False


SETTINGS_DB_PATH = "user_settings.db"


def init_settings_db():
    """Initializes the SQLite database for storing user settings."""
    try:
        with sqlite3.connect(SETTINGS_DB_PATH) as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS user_settings (
                    user_id INTEGER PRIMARY KEY,
                    upload_audio TEXT DEFAULT 'audio',
                    upload_video TEXT DEFAULT 'video'
                )
                """
            )
            conn.commit()
    except Exception as e:
        logger.error(f"Error initializing user settings db: {e}")


# Initialize settings table on module import
init_settings_db()


def get_user_settings(user_id: int) -> dict:
    """
    Returns user settings dict:
    {'upload_audio': 'audio' | 'file', 'upload_video': 'video' | 'file'}
    Default is 'audio' and 'video'.
    """
    default_settings = {"upload_audio": "audio", "upload_video": "video"}
    if not user_id:
        return default_settings
    try:
        with sqlite3.connect(SETTINGS_DB_PATH) as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT upload_audio, upload_video FROM user_settings WHERE user_id = ?",
                (user_id,),
            )
            row = cursor.fetchone()
            if row:
                return {
                    "upload_audio": row[0] or "audio",
                    "upload_video": row[1] or "video",
                }
    except Exception as e:
        logger.error(f"Error reading user settings for {user_id}: {e}")
    return default_settings


def toggle_user_upload_mode(user_id: int, media_type: str) -> str:
    """
    media_type: 'audio' or 'video'
    Toggles between 'audio'/'video' and 'file'.
    Returns the new mode string ('audio', 'video', or 'file').
    """
    current = get_user_settings(user_id)
    if media_type == "audio":
        new_mode = "file" if current.get("upload_audio") == "audio" else "audio"
        upload_audio = new_mode
        upload_video = current.get("upload_video", "video")
    else:
        new_mode = "file" if current.get("upload_video") == "video" else "video"
        upload_audio = current.get("upload_audio", "audio")
        upload_video = new_mode

    try:
        with sqlite3.connect(SETTINGS_DB_PATH) as conn:
            conn.execute(
                """
                INSERT INTO user_settings (user_id, upload_audio, upload_video)
                VALUES (?, ?, ?)
                ON CONFLICT(user_id) DO UPDATE SET
                    upload_audio = excluded.upload_audio,
                    upload_video = excluded.upload_video
                """,
                (user_id, upload_audio, upload_video),
            )
            conn.commit()
    except Exception as e:
        logger.error(f"Error saving user settings for {user_id}: {e}")
    return new_mode


def get_settings_text(settings: dict) -> str:
    """
    Builds the Settings menu text showing current upload formats.
    """
    audio_mode = settings.get("upload_audio", "audio")
    video_mode = settings.get("upload_video", "video")

    audio_status = "Upload as File (Document)" if audio_mode == "file" else "Upload as Audio"
    video_status = "Upload as File (Document)" if video_mode == "file" else "Upload as Video"

    return (
        "⚙️ **Upload Settings**\n\n"
        "Configure how processed media files are sent to you:\n\n"
        f"• **Audio Upload:** `{audio_status}`\n"
        f"• **Video Upload:** `{video_status}`\n\n"
        "Tap a button below to toggle between standard media and file format:"
    )






