from hydrogram.types import InlineKeyboardMarkup, InlineKeyboardButton


def get_start_keyboard() -> InlineKeyboardMarkup:
    """Returns the main welcome inline keyboard."""
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("ℹ️ Help", callback_data="help"),
                InlineKeyboardButton("🤖 About", callback_data="about"),
            ],
            [
                InlineKeyboardButton("⚡ Server Status", callback_data="status"),
            ],
        ]
    )


def get_back_keyboard() -> InlineKeyboardMarkup:
    """Returns a back button keyboard to Home."""
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("⬅️ Back to Home", callback_data="home")]
        ]
    )


def get_audio_keyboard() -> InlineKeyboardMarkup:
    """
    Returns the Audio Management Menu keyboard.
    - Audio rename
    - Audio merger
    - Audio trimmer
    - Remove Metadata Title
    - FFmpeg command
    - FFprobe info
    - Close Menu
    """
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("✏️ Audio Rename", callback_data="audio_rename"),
                InlineKeyboardButton("🔀 Audio Merger", callback_data="audio_merger"),
            ],
            [
                InlineKeyboardButton("✂️ Audio Trimmer", callback_data="audio_trimmer"),
                InlineKeyboardButton("🏷️ Remove Metadata Title", callback_data="audio_rm_title"),
            ],
            [
                InlineKeyboardButton("💻 FFmpeg Command", callback_data="audio_ffmpeg"),
                InlineKeyboardButton("🔍 FFprobe Info", callback_data="audio_ffprobe"),
            ],
            [
                InlineKeyboardButton("❌ Close Menu", callback_data="close_menu"),
            ],
        ]
    )


def get_audio_trimmer_keyboard() -> InlineKeyboardMarkup:
    """
    Returns the Audio Trimmer Mode Selection keyboard.
    Options:
    - Fast copy
    - Frame accuracy
    - Back to Audio Menu
    """
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("⚡ Fast Copy", callback_data="trim_mode_fast"),
            ],
            [
                InlineKeyboardButton("🎯 Frame Accuracy", callback_data="trim_mode_accurate"),
            ],
            [
                InlineKeyboardButton("⬅️ Back to Audio Menu", callback_data="audio_menu_back"),
            ],
        ]
    )


def get_back_to_audio_keyboard() -> InlineKeyboardMarkup:
    """Returns a single Back to Audio Menu button."""
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("⬅️ Back to Audio Menu", callback_data="audio_menu_back")]
        ]
    )


def get_audio_merger_keyboard(track_count: int) -> InlineKeyboardMarkup:
    """
    Returns the Audio Merger Queue keyboard.
    - When track_count >= 2: displays [ 🔀 Merge Now ({track_count} Tracks) ] button along with Reset and Back.
    - When track_count < 2: displays [ ⬅️ Cancel & Back ] button.
    """
    if track_count >= 2:
        return InlineKeyboardMarkup(
            [
                [
                    InlineKeyboardButton(
                        f"🔀 Merge Now ({track_count} Tracks)",
                        callback_data="start_audio_merge",
                    ),
                ],
                [
                    InlineKeyboardButton("🗑️ Reset Queue", callback_data="reset_audio_merger"),
                    InlineKeyboardButton("⬅️ Cancel & Back", callback_data="audio_menu_back"),
                ],
            ]
        )
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("⬅️ Cancel & Back", callback_data="audio_menu_back"),
            ]
        ]
    )


def get_back_to_trimmer_keyboard() -> InlineKeyboardMarkup:
    """Returns Back to Trimmer Options and Back to Audio Menu buttons."""
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("⬅️ Back to Trimmer Options", callback_data="audio_trimmer")],
            [InlineKeyboardButton("🏠 Back to Audio Menu", callback_data="audio_menu_back")],
        ]
    )


def get_video_trimmer_keyboard() -> InlineKeyboardMarkup:
    """
    Returns the Video Trimmer Mode Selection keyboard.
    Options:
    - Fast copy
    - Frame accuracy
    - Back to Video Menu
    """
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("⚡ Fast Copy", callback_data="video_trim_mode_fast"),
            ],
            [
                InlineKeyboardButton("🎯 Frame Accuracy", callback_data="video_trim_mode_accurate"),
            ],
            [
                InlineKeyboardButton("⬅️ Back to Video Menu", callback_data="video_menu_back"),
            ],
        ]
    )


def get_back_to_video_trimmer_keyboard() -> InlineKeyboardMarkup:
    """Returns Back to Video Trimmer Options and Back to Video Menu buttons."""
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("⬅️ Back to Trimmer Options", callback_data="video_trimmer")],
            [InlineKeyboardButton("🏠 Back to Video Menu", callback_data="video_menu_back")],
        ]
    )


def get_video_keyboard() -> InlineKeyboardMarkup:
    """
    Returns the Video Management Menu keyboard.
    - Video Rename
    - Metadata Editor
    - Stream Remover
    - Stream Extractor
    - Merge Audio
    - Video Trimmer
    - Video Merger
    - FFmpeg Command
    - FFprobe Info
    - Close Menu
    """
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("✏️ Video Rename", callback_data="video_rename"),
                InlineKeyboardButton("🏷️ Metadata Editor", callback_data="video_metadata"),
            ],
            [
                InlineKeyboardButton("🗑️ Stream Remover", callback_data="video_stream_remover"),
                InlineKeyboardButton("📤 Stream Extractor", callback_data="video_stream_extractor"),
            ],
            [
                InlineKeyboardButton("🎵 Merge Audio", callback_data="video_merge_audio"),
                InlineKeyboardButton("✂️ Video Trimmer", callback_data="video_trimmer"),
            ],
            [
                InlineKeyboardButton("🔀 Video Merger", callback_data="video_merger"),
                InlineKeyboardButton("💬 Subtitle Merger", callback_data="video_merge_subtitle"),
            ],
            [
                InlineKeyboardButton("💻 FFmpeg Command", callback_data="video_ffmpeg"),
                InlineKeyboardButton("🔍 FFprobe Info", callback_data="video_ffprobe"),
            ],
            [
                InlineKeyboardButton("❌ Close Menu", callback_data="close_menu"),
            ],
        ]
    )


def get_back_to_video_keyboard() -> InlineKeyboardMarkup:
    """Returns Back to Video Menu button."""
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("⬅️ Back to Video Menu", callback_data="video_menu_back")]
        ]
    )


def get_video_merge_audio_keyboard(track_count: int) -> InlineKeyboardMarkup:
    """
    Returns the Video Audio Muxer Queue keyboard.
    - When track_count >= 1: displays [ 🔀 Merge Audio Now ({track_count} Tracks) ], Reset, and Back.
    - When track_count == 0: displays [ ⬅️ Cancel & Back ].
    """
    if track_count >= 1:
        track_str = f"{track_count} Track" if track_count == 1 else f"{track_count} Tracks"
        return InlineKeyboardMarkup(
            [
                [
                    InlineKeyboardButton(
                        f"🔀 Merge Audio Now ({track_str})",
                        callback_data="start_video_audio_merge",
                    ),
                ],
                [
                    InlineKeyboardButton("🗑️ Reset Queue", callback_data="reset_video_audio_merge"),
                    InlineKeyboardButton("⬅️ Cancel & Back", callback_data="video_menu_back"),
                ],
            ]
        )
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("⬅️ Cancel & Back", callback_data="video_menu_back"),
            ]
        ]
    )


def get_video_merger_keyboard(video_count: int) -> InlineKeyboardMarkup:
    """
    Returns the Video Merger Queue keyboard (Fast Copy).
    - When video_count >= 2: displays [ 🔀 Merge Now ({video_count} Videos) ], Reset, and Back.
    - When video_count < 2: displays [ ⬅️ Cancel & Back ].
    """
    if video_count >= 2:
        return InlineKeyboardMarkup(
            [
                [
                    InlineKeyboardButton(
                        f"🔀 Merge Now ({video_count} Videos)",
                        callback_data="start_video_merge",
                    ),
                ],
                [
                    InlineKeyboardButton("🗑️ Reset Queue", callback_data="reset_video_merger"),
                    InlineKeyboardButton("⬅️ Cancel & Back", callback_data="video_menu_back"),
                ],
            ]
        )
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("⬅️ Cancel & Back", callback_data="video_menu_back"),
            ]
        ]
    )


def get_video_merge_subtitle_keyboard(track_count: int) -> InlineKeyboardMarkup:
    """
    Returns the Video Subtitle Muxer Queue keyboard.
    - When track_count >= 1: displays [ 🔀 Merge Subtitles Now ({track_count} Tracks) ], Reset, and Back.
    - When track_count == 0: displays [ ⬅️ Cancel & Back ].
    """
    if track_count >= 1:
        track_str = f"{track_count} Track" if track_count == 1 else f"{track_count} Tracks"
        return InlineKeyboardMarkup(
            [
                [
                    InlineKeyboardButton(
                        f"🔀 Merge Subtitles Now ({track_str})",
                        callback_data="start_video_subtitle_merge",
                    ),
                ],
                [
                    InlineKeyboardButton("🗑️ Reset Queue", callback_data="reset_video_subtitle_merge"),
                    InlineKeyboardButton("⬅️ Cancel & Back", callback_data="video_menu_back"),
                ],
            ]
        )
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("⬅️ Cancel & Back", callback_data="video_menu_back"),
            ]
        ]
    )


def get_video_metadata_keyboard(
    audio_streams: list,
    subtitle_streams: list,
    has_changes: bool = False,
    pending_metadata: dict = None,
) -> InlineKeyboardMarkup:
    """
    Compact keyboard for Metadata Editor with edit buttons for:
    - Global Video Title
    - Audio Streams (Title & Lang)
    - Subtitle Streams (Title & Lang)
    - Apply button
    """
    buttons = []
    pending = pending_metadata or {}
    modified_streams = pending.get("streams", {})

    # 1. Video Title Button
    vid_title_label = "🎬 Edit Video Title"
    if pending.get("global_title") is not None:
        short_t = pending['global_title'][:18]
        vid_title_label = f"🎬 Title: {short_t} ✏️"
    buttons.append([InlineKeyboardButton(vid_title_label, callback_data="vmeta_v")])

    # 2. Audio Streams
    for i, stream in enumerate(audio_streams):
        s_idx = stream.get("index", i)
        codec = stream.get("codec_name", "?").upper()
        stream_key = f"a:{i}"
        is_mod = stream_key in modified_streams

        if is_mod:
            cur_lang = modified_streams[stream_key].get("language", "")
            cur_title = modified_streams[stream_key].get("title", "")
            tag = cur_lang if cur_lang else codec
            label = f"🎵 #{s_idx} Audio ({tag}) ✏️"
            if cur_title:
                label = f"🎵 #{s_idx} Audio: {cur_title[:15]} ✏️"
        else:
            lang = stream.get("language", "und")
            tag = lang if lang and lang != "und" else codec
            label = f"🎵 #{s_idx} Audio ({tag})"
            if stream.get("title"):
                label = f"🎵 #{s_idx} Audio: {stream['title'][:15]}"

        buttons.append([InlineKeyboardButton(label, callback_data=f"vmeta_a{i}")])

    # 3. Subtitle Streams
    for i, stream in enumerate(subtitle_streams):
        s_idx = stream.get("index", i)
        codec = stream.get("codec_name", "?").upper()
        stream_key = f"s:{i}"
        is_mod = stream_key in modified_streams

        if is_mod:
            cur_lang = modified_streams[stream_key].get("language", "")
            cur_title = modified_streams[stream_key].get("title", "")
            tag = cur_lang if cur_lang else codec
            label = f"💬 #{s_idx} Sub ({tag}) ✏️"
            if cur_title:
                label = f"💬 #{s_idx} Sub: {cur_title[:15]} ✏️"
        else:
            lang = stream.get("language", "und")
            tag = lang if lang and lang != "und" else codec
            label = f"💬 #{s_idx} Sub ({tag})"
            if stream.get("title"):
                label = f"💬 #{s_idx} Sub: {stream['title'][:15]}"

        buttons.append([InlineKeyboardButton(label, callback_data=f"vmeta_s{i}")])

    # 4. Apply Changes button
    if has_changes:
        buttons.append([
            InlineKeyboardButton("💾 Apply & Save Changes", callback_data="video_metadata_apply")
        ])

    buttons.append([InlineKeyboardButton("⬅️ Back to Video Menu", callback_data="video_menu_back")])
    return InlineKeyboardMarkup(buttons)


def get_back_to_metadata_keyboard() -> InlineKeyboardMarkup:
    """Returns Back to Metadata view and Back to Video Menu buttons."""
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("⬅️ Back to Metadata", callback_data="video_metadata_back")],
            [InlineKeyboardButton("🏠 Back to Video Menu", callback_data="video_menu_back")],
        ]
    )


def get_stream_remover_keyboard(streams: list, selected_indices: set) -> InlineKeyboardMarkup:
    """
    Compact multi-select keyboard for Stream Remover.
    """
    buttons = []
    for st in streams:
        idx = st["index"]
        ctype = st["type"]
        type_icon = "🎬" if ctype == "video" else ("🎵" if ctype == "audio" else ("💬" if ctype == "subtitle" else "📦"))
        type_short = "Video" if ctype == "video" else ("Audio" if ctype == "audio" else ("Sub" if ctype == "subtitle" else ctype))
        codec = st.get("codec_name", "?")
        lang = st.get("language", "und")

        is_selected = idx in selected_indices
        check = "🗑️" if is_selected else "▫️"

        tag = lang if lang and lang != "und" else codec
        label = f"{check} #{idx} {type_icon} {type_short} ({tag})"
        if st.get("title"):
            label = f"{check} #{idx} {type_icon} {st['title'][:18]}"

        buttons.append([InlineKeyboardButton(label, callback_data=f"vrem_toggle_{idx}")])

    if len(selected_indices) > 0:
        buttons.append([
            InlineKeyboardButton(
                f"🗑️ Confirm & Remove ({len(selected_indices)})",
                callback_data="vrem_apply",
            )
        ])

    buttons.append([InlineKeyboardButton("⬅️ Back to Video Menu", callback_data="video_menu_back")])
    return InlineKeyboardMarkup(buttons)


def get_stream_extractor_keyboard(streams: list, selected_indices: set) -> InlineKeyboardMarkup:
    """
    Compact multi-select keyboard for Stream Extractor.
    """
    buttons = []
    for st in streams:
        idx = st["index"]
        ctype = st["type"]
        type_icon = "🎬" if ctype == "video" else ("🎵" if ctype == "audio" else ("💬" if ctype == "subtitle" else "📦"))
        type_short = "Video" if ctype == "video" else ("Audio" if ctype == "audio" else ("Sub" if ctype == "subtitle" else ctype))
        codec = st.get("codec_name", "?")
        lang = st.get("language", "und")

        is_selected = idx in selected_indices
        check = "📥" if is_selected else "▫️"

        tag = lang if lang and lang != "und" else codec
        label = f"{check} #{idx} {type_icon} {type_short} ({tag})"
        if st.get("title"):
            label = f"{check} #{idx} {type_icon} {st['title'][:18]}"

        buttons.append([InlineKeyboardButton(label, callback_data=f"vext_toggle_{idx}")])

    if len(selected_indices) > 0:
        buttons.append([
            InlineKeyboardButton(
                f"📤 Extract Selected ({len(selected_indices)})",
                callback_data="vext_apply",
            )
        ])

    buttons.append([InlineKeyboardButton("⬅️ Back to Video Menu", callback_data="video_menu_back")])
    return InlineKeyboardMarkup(buttons)


def get_file_keyboard() -> InlineKeyboardMarkup:
    """Returns the File/Document Management Menu keyboard."""
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("✏️ File Rename", callback_data="file_rename"),
            ],
            [
                InlineKeyboardButton("🎬 Treat as Video", callback_data="file_as_video"),
                InlineKeyboardButton("🎵 Treat as Audio", callback_data="file_as_audio"),
            ],
            [
                InlineKeyboardButton("❌ Close Menu", callback_data="close_menu"),
            ],
        ]
    )


def get_back_to_file_keyboard() -> InlineKeyboardMarkup:
    """Returns Back to File Menu button."""
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("⬅️ Back to File Menu", callback_data="file_menu_back")]
        ]
    )


def get_cancel_process_keyboard(task_id: str) -> InlineKeyboardMarkup:
    """Returns an inline keyboard with Refresh and Cancel Process buttons."""
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("🔄 Refresh", callback_data=f"refresh_{task_id}"),
                InlineKeyboardButton("🚫 Cancel Process", callback_data=f"cancel_{task_id}"),
            ]
        ]
    )


def get_settings_keyboard(upload_audio: str = "audio", upload_video: str = "video") -> InlineKeyboardMarkup:
    """
    Returns the settings keyboard with toggles for audio and video upload formats.
    - If upload_audio == 'audio' -> 'Upload as Audio'
    - If upload_audio == 'file'  -> 'Upload as File'
    - If upload_video == 'video' -> 'Upload as Video'
    - If upload_video == 'file'  -> 'Upload as File'
    """
    audio_label = "Upload as File" if upload_audio == "file" else "Upload as Audio"
    video_label = "Upload as File" if upload_video == "file" else "Upload as Video"

    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton(audio_label, callback_data="toggle_setting_audio")],
            [InlineKeyboardButton(video_label, callback_data="toggle_setting_video")],
            [InlineKeyboardButton("❌ Cancel", callback_data="close_settings")],
        ]
    )


