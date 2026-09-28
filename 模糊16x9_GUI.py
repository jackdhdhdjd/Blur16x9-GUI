import os
import cv2
import json
import subprocess
import threading
import tkinter as tk
from tkinter import filedialog, messagebox
from PIL import Image, ImageTk


# =========================================================
# 基本設定
# =========================================================

OUTPUT_W = 1920
OUTPUT_H = 1080

# 縮小預覽，避免下面按鈕被吃掉
PREVIEW_W = 640
PREVIEW_H = 360

LINE_WIDTH = 4
MIN_CROP_WIDTH = 20

# 16:9 模糊輸出碼率保護
MIN_16_9_BITRATE = 2_500_000
MAX_16_9_BITRATE = 20_000_000


# =========================================================
# 全域影片資料
# =========================================================

video_path = None
cap = None

video_width = 0
video_height = 0
frame_count = 0
fps = 30.0
duration = 0.0

source_codec = "unknown"
source_bitrate = 0
source_audio_codec = "unknown"
source_audio_bitrate = 0

display_x = 0
display_y = 0
display_w = 0
display_h = 0

left_crop_x = 0
right_crop_x = 0

dragging_line = None
preview_photo = None


# =========================================================
# FFprobe
# =========================================================

def probe_video(path):

    command = [
        "ffprobe",
        "-v", "error",
        "-print_format", "json",
        "-show_streams",
        "-show_format",
        path
    ]

    try:

        result = subprocess.run(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
            creationflags=subprocess.CREATE_NO_WINDOW
        )

        if result.returncode != 0:
            return None

        data = json.loads(result.stdout)

        video_stream = None
        audio_stream = None

        for stream in data.get("streams", []):

            if (
                stream.get("codec_type") == "video"
                and video_stream is None
            ):
                video_stream = stream

            elif (
                stream.get("codec_type") == "audio"
                and audio_stream is None
            ):
                audio_stream = stream

        if video_stream is None:
            return None

        codec = video_stream.get(
            "codec_name",
            "unknown"
        )

        # -----------------------------------------
        # Video bitrate
        # -----------------------------------------

        bitrate = 0

        try:
            bitrate = int(
                video_stream.get(
                    "bit_rate",
                    0
                )
            )
        except:
            bitrate = 0

        # -----------------------------------------
        # Audio
        # -----------------------------------------

        audio_codec = "none"
        audio_bitrate = 0

        if audio_stream:

            audio_codec = audio_stream.get(
                "codec_name",
                "unknown"
            )

            try:
                audio_bitrate = int(
                    audio_stream.get(
                        "bit_rate",
                        0
                    )
                )
            except:
                audio_bitrate = 0

        # -----------------------------------------
        # stream 沒 bitrate → 用 format bitrate
        # -----------------------------------------

        if bitrate <= 0:

            try:
                total_bitrate = int(
                    data.get(
                        "format",
                        {}
                    ).get(
                        "bit_rate",
                        0
                    )
                )
            except:
                total_bitrate = 0

            if total_bitrate > 0:

                bitrate = max(
                    100000,
                    total_bitrate - audio_bitrate
                )

        return {
            "codec": codec,
            "bitrate": bitrate,
            "audio_codec": audio_codec,
            "audio_bitrate": audio_bitrate
        }

    except Exception:
        return None


# =========================================================
# 顯示 bitrate
# =========================================================

def format_bitrate(bitrate):

    if bitrate <= 0:
        return "未知"

    return f"{bitrate / 1_000_000:.2f} Mbps"


# =========================================================
# Codec 名稱
# =========================================================

def codec_display_name(codec):

    codec = codec.lower()

    if codec == "h264":
        return "H.264 / AVC"

    if codec in (
        "hevc",
        "h265"
    ):
        return "H.265 / HEVC"

    if codec == "av1":
        return "AV1"

    if codec == "vp9":
        return "VP9"

    if codec == "mpeg4":
        return "MPEG-4"

    return codec.upper()


# =========================================================
# NVIDIA encoder
# =========================================================

def get_nvenc_encoder():

    codec = source_codec.lower()

    if codec in (
        "hevc",
        "h265"
    ):
        return "hevc_nvenc"

    return "h264_nvenc"


# =========================================================
# 時間格式
# =========================================================

def format_time(seconds):

    if seconds < 0:
        seconds = 0

    minutes = int(
        seconds // 60
    )

    sec = seconds % 60

    return (
        f"{minutes:02d}:"
        f"{sec:05.2f}"
    )


# =========================================================
# 選影片
# =========================================================

def choose_file():

    global video_path
    global cap

    global video_width
    global video_height
    global frame_count
    global fps
    global duration

    global source_codec
    global source_bitrate
    global source_audio_codec
    global source_audio_bitrate

    global left_crop_x
    global right_crop_x

    path = filedialog.askopenfilename(
        title="選擇影片",
        filetypes=[
            (
                "影片檔案",
                "*.mp4 *.mov *.mkv *.avi *.webm *.m4v"
            ),
            (
                "所有檔案",
                "*.*"
            )
        ]
    )

    if not path:
        return

    if cap is not None:
        cap.release()

    cap = cv2.VideoCapture(
        path
    )

    if not cap.isOpened():

        messagebox.showerror(
            "錯誤",
            "影片無法開啟"
        )

        return

    video_path = path

    input_var.set(
        path
    )

    video_width = int(
        cap.get(
            cv2.CAP_PROP_FRAME_WIDTH
        )
    )

    video_height = int(
        cap.get(
            cv2.CAP_PROP_FRAME_HEIGHT
        )
    )

    frame_count = int(
        cap.get(
            cv2.CAP_PROP_FRAME_COUNT
        )
    )

    fps = cap.get(
        cv2.CAP_PROP_FPS
    )

    if fps <= 0:
        fps = 30.0

    if frame_count > 0:
        duration = frame_count / fps
    else:
        duration = 0.0

    probe = probe_video(
        path
    )

    if probe:

        source_codec = probe[
            "codec"
        ]

        source_bitrate = probe[
            "bitrate"
        ]

        source_audio_codec = probe[
            "audio_codec"
        ]

        source_audio_bitrate = probe[
            "audio_bitrate"
        ]

    else:

        source_codec = "unknown"
        source_bitrate = 0
        source_audio_codec = "unknown"
        source_audio_bitrate = 0

    # -----------------------------------------
    # 直式 / 窄影片：
    # 預設直接全寬
    #
    # 16:9：
    # 預設左右各留 10%
    # -----------------------------------------

    if video_width < video_height:

        left_crop_x = 0
        right_crop_x = video_width

    else:

        left_crop_x = int(
            video_width * 0.10
        )

        right_crop_x = int(
            video_width * 0.90
        )

    timeline.config(
        from_=0,
        to=max(
            duration,
            0.1
        )
    )

    timeline.set(
        0
    )

    update_video_info()

    show_frame(
        0
    )


# =========================================================
# 更新資訊
# =========================================================

def update_video_info():

    crop_w = (
        right_crop_x
        - left_crop_x
    )

    encoder = (
        get_nvenc_encoder()
    )

    info_label.config(
        text=(
            f"原始影片："
            f"{video_width} × {video_height}"
            f"　｜　"
            f"{format_time(duration)}"
            f"　｜　"
            f"{fps:.2f} FPS"
        )
    )

    codec_info_label.config(
        text=(
            f"原片編碼："
            f"{codec_display_name(source_codec)}"
            f"　｜　"
            f"Video Bitrate："
            f"{format_bitrate(source_bitrate)}"
            f"　｜　"
            f"輸出：{encoder}"
        )
    )

    crop_info_label.config(
        text=(
            f"左：{left_crop_x}px"
            f"　右：{right_crop_x}px"
            f"　保留：{crop_w}px"
            f"　尺寸："
            f"{crop_w}×{video_height}"
        )
    )


# =========================================================
# 預覽
# =========================================================

def show_frame(seconds):

    global preview_photo

    global display_x
    global display_y
    global display_w
    global display_h

    if cap is None:
        return

    cap.set(
        cv2.CAP_PROP_POS_MSEC,
        seconds * 1000
    )

    ok, frame = cap.read()

    if not ok:
        return

    frame = cv2.cvtColor(
        frame,
        cv2.COLOR_BGR2RGB
    )

    h, w = frame.shape[:2]

    scale = min(
        PREVIEW_W / w,
        PREVIEW_H / h
    )

    new_w = max(
        1,
        int(w * scale)
    )

    new_h = max(
        1,
        int(h * scale)
    )

    frame = cv2.resize(
        frame,
        (
            new_w,
            new_h
        ),
        interpolation=cv2.INTER_AREA
    )

    image = Image.fromarray(
        frame
    )

    preview_photo = ImageTk.PhotoImage(
        image=image
    )

    preview_canvas.delete(
        "all"
    )

    display_w = new_w
    display_h = new_h

    display_x = (
        PREVIEW_W - new_w
    ) // 2

    display_y = (
        PREVIEW_H - new_h
    ) // 2

    preview_canvas.create_image(
        display_x,
        display_y,
        anchor="nw",
        image=preview_photo
    )

    draw_crop_lines()

    current_time_label.config(
        text=(
            f"{format_time(seconds)}"
            f" / "
            f"{format_time(duration)}"
        )
    )


# =========================================================
# 座標
# =========================================================

def source_to_canvas_x(source_x):

    if video_width <= 0:
        return 0

    return (
        display_x
        + source_x
        / video_width
        * display_w
    )


def canvas_to_source_x(canvas_x):

    if display_w <= 0:
        return 0

    relative_x = (
        canvas_x
        - display_x
    )

    relative_x = max(
        0,
        min(
            display_w,
            relative_x
        )
    )

    source_x = int(
        relative_x
        / display_w
        * video_width
    )

    return max(
        0,
        min(
            video_width,
            source_x
        )
    )


# =========================================================
# 畫紅線
# =========================================================

def draw_crop_lines():

    if video_width <= 0:
        return

    lx = source_to_canvas_x(
        left_crop_x
    )

    rx = source_to_canvas_x(
        right_crop_x
    )

    top = display_y
    bottom = display_y + display_h

    preview_canvas.create_rectangle(
        display_x,
        top,
        lx,
        bottom,
        fill="black",
        stipple="gray50",
        outline=""
    )

    preview_canvas.create_rectangle(
        rx,
        top,
        display_x + display_w,
        bottom,
        fill="black",
        stipple="gray50",
        outline=""
    )

    preview_canvas.create_line(
        lx,
        top,
        lx,
        bottom,
        fill="red",
        width=LINE_WIDTH
    )

    preview_canvas.create_line(
        rx,
        top,
        rx,
        bottom,
        fill="red",
        width=LINE_WIDTH
    )

    preview_canvas.create_text(
        lx + 8,
        top + 18,
        text=f"{left_crop_x}px",
        fill="red",
        anchor="w",
        font=(
            "Microsoft JhengHei",
            10,
            "bold"
        )
    )

    preview_canvas.create_text(
        rx - 8,
        top + 18,
        text=f"{right_crop_x}px",
        fill="red",
        anchor="e",
        font=(
            "Microsoft JhengHei",
            10,
            "bold"
        )
    )


# =========================================================
# 拖紅線
# =========================================================

def preview_mouse_down(event):

    global dragging_line

    if video_width <= 0:
        return

    lx = source_to_canvas_x(
        left_crop_x
    )

    rx = source_to_canvas_x(
        right_crop_x
    )

    ld = abs(
        event.x - lx
    )

    rd = abs(
        event.x - rx
    )

    tolerance = 18

    if (
        ld <= tolerance
        and ld <= rd
    ):
        dragging_line = "left"

    elif rd <= tolerance:
        dragging_line = "right"

    else:
        dragging_line = None


def preview_mouse_drag(event):

    global left_crop_x
    global right_crop_x

    if dragging_line is None:
        return

    source_x = canvas_to_source_x(
        event.x
    )

    if dragging_line == "left":

        source_x = min(
            source_x,
            right_crop_x
            - MIN_CROP_WIDTH
        )

        left_crop_x = max(
            0,
            source_x
        )

    else:

        source_x = max(
            source_x,
            left_crop_x
            + MIN_CROP_WIDTH
        )

        right_crop_x = min(
            video_width,
            source_x
        )

    refresh_current_preview()


def preview_mouse_up(event):

    global dragging_line

    dragging_line = None


def refresh_current_preview():

    show_frame(
        timeline.get()
    )

    update_video_info()


# =========================================================
# 時間軸
# =========================================================

def timeline_changed(value):

    if cap is None:
        return

    try:
        seconds = float(
            value
        )
    except:
        return

    show_frame(
        seconds
    )


def jump_percent(percent):

    if duration <= 0:
        return

    seconds = (
        duration
        * percent
    )

    timeline.set(
        seconds
    )

    show_frame(
        seconds
    )


# =========================================================
# 快捷紅線
# =========================================================

def reset_lines():

    global left_crop_x
    global right_crop_x

    if video_width <= 0:
        return

    left_crop_x = int(
        video_width * 0.10
    )

    right_crop_x = int(
        video_width * 0.90
    )

    refresh_current_preview()


def full_width():

    global left_crop_x
    global right_crop_x

    if video_width <= 0:
        return

    left_crop_x = 0
    right_crop_x = video_width

    refresh_current_preview()


def set_9_16():

    global left_crop_x
    global right_crop_x

    if video_width <= 0:
        return

    wanted_width = int(
        video_height
        * 9
        / 16
    )

    wanted_width = min(
        wanted_width,
        video_width
    )

    wanted_width = (
        wanted_width
        // 2
        * 2
    )

    center = (
        video_width
        // 2
    )

    left_crop_x = (
        center
        - wanted_width
        // 2
    )

    right_crop_x = (
        left_crop_x
        + wanted_width
    )

    refresh_current_preview()


def set_764_ratio():

    global left_crop_x
    global right_crop_x

    if video_width <= 0:
        return

    wanted_width = int(
        video_height
        * 764
        / 1080
    )

    wanted_width = min(
        wanted_width,
        video_width
    )

    wanted_width = (
        wanted_width
        // 2
        * 2
    )

    center = (
        video_width
        // 2
    )

    left_crop_x = (
        center
        - wanted_width
        // 2
    )

    right_crop_x = (
        left_crop_x
        + wanted_width
    )

    refresh_current_preview()


# =========================================================
# 安全裁切數值
# =========================================================

def get_crop_values():

    crop_w = (
        right_crop_x
        - left_crop_x
    )

    if crop_w < MIN_CROP_WIDTH:
        return None

    crop_x = (
        left_crop_x
        // 2
        * 2
    )

    crop_w = (
        crop_w
        // 2
        * 2
    )

    if (
        crop_x
        + crop_w
        > video_width
    ):

        crop_w = (
            video_width
            - crop_x
        )

        crop_w = (
            crop_w
            // 2
            * 2
        )

    return (
        crop_x,
        crop_w
    )


# =========================================================
# 只裁切時：
# 依像素比例降低 bitrate
# =========================================================

def calculate_crop_bitrate(crop_w):

    if source_bitrate <= 0:
        return 5_000_000

    original_pixels = (
        video_width
        * video_height
    )

    cropped_pixels = (
        crop_w
        * video_height
    )

    if original_pixels <= 0:
        return source_bitrate

    ratio = (
        cropped_pixels
        / original_pixels
    )

    bitrate = int(
        source_bitrate
        * ratio
    )

    return max(
        bitrate,
        500_000
    )


# =========================================================
# ★ 新版：
# 製作 1920x1080 模糊背景時
# 按輸出像素數補償 bitrate
# =========================================================

def calculate_16_9_bitrate(
    source_w,
    source_h
):

    if (
        source_bitrate <= 0
        or source_w <= 0
        or source_h <= 0
    ):
        return 5_000_000

    source_pixels = (
        source_w
        * source_h
    )

    output_pixels = (
        OUTPUT_W
        * OUTPUT_H
    )

    pixel_ratio = (
        output_pixels
        / source_pixels
    )

    # -----------------------------------------
    # 如果輸出像素變多
    # bitrate 跟著增加
    #
    # 如果輸出像素反而變少
    # 不需要高於原片
    # -----------------------------------------

    if pixel_ratio > 1:

        target = int(
            source_bitrate
            * pixel_ratio
        )

    else:

        target = source_bitrate

    # -----------------------------------------
    # 最低 / 最高保護
    # -----------------------------------------

    target = max(
        target,
        MIN_16_9_BITRATE
    )

    target = min(
        target,
        MAX_16_9_BITRATE
    )

    return target


# =========================================================
# bitrate 字串
# =========================================================

def bitrate_string(bitrate):

    return (
        f"{int(bitrate / 1000)}k"
    )


# =========================================================
# 估算輸出大小
# =========================================================

def estimate_size_mb(
    video_bitrate
):

    if duration <= 0:
        return 0

    audio = (
        source_audio_bitrate
        if source_audio_bitrate > 0
        else 128_000
    )

    total = (
        video_bitrate
        + audio
    )

    size_bytes = (
        total
        * duration
        / 8
    )

    return (
        size_bytes
        / 1024
        / 1024
    )


# =========================================================
# 按鈕 1：
# 只擷取紅線
# =========================================================

def start_crop_only():

    if not video_path:

        messagebox.showwarning(
            "提示",
            "請先選擇影片"
        )

        return

    values = get_crop_values()

    if values is None:
        return

    crop_x, crop_w = values

    target_bitrate = (
        calculate_crop_bitrate(
            crop_w
        )
    )

    encoder = (
        get_nvenc_encoder()
    )

    base, ext = os.path.splitext(
        video_path
    )

    output_file = (
        base
        + f"_擷取中央_{crop_w}x{video_height}.mp4"
    )

    log.delete(
        "1.0",
        tk.END
    )

    log.insert(
        tk.END,
        "===== 只擷取紅線中間 =====\n"
        f"原片碼率：{format_bitrate(source_bitrate)}\n"
        f"輸出碼率：{format_bitrate(target_bitrate)}\n"
        f"估計大小：約 {estimate_size_mb(target_bitrate):.1f} MB\n\n"
    )

    set_buttons(
        False
    )

    threading.Thread(
        target=run_crop_only,
        args=(
            video_path,
            output_file,
            crop_x,
            crop_w,
            encoder,
            target_bitrate
        ),
        daemon=True
    ).start()


def run_crop_only(
    input_file,
    output_file,
    crop_x,
    crop_w,
    encoder,
    target_bitrate
):

    bitrate = bitrate_string(
        target_bitrate
    )

    maxrate = bitrate_string(
        int(
            target_bitrate
            * 1.25
        )
    )

    bufsize = bitrate_string(
        int(
            target_bitrate
            * 2
        )
    )

    command = [
        "ffmpeg",
        "-y",

        "-i",
        input_file,

        "-vf",
        (
            f"crop="
            f"{crop_w}:"
            f"ih:"
            f"{crop_x}:0"
        ),

        "-c:v",
        encoder,

        "-preset",
        "p5",

        "-b:v",
        bitrate,

        "-maxrate",
        maxrate,

        "-bufsize",
        bufsize,

        "-c:a",
        "copy",

        "-movflags",
        "+faststart",

        output_file
    ]

    run_process(
        command,
        output_file
    )


# =========================================================
# 按鈕 2：
# 紅線擷取 → 16:9 模糊
# =========================================================

def start_crop_blur():

    if not video_path:

        messagebox.showwarning(
            "提示",
            "請先選擇影片"
        )

        return

    values = get_crop_values()

    if values is None:
        return

    crop_x, crop_w = values

    blur_value = int(
        blur_var.get()
    )

    bg_position = int(
        position_var.get()
    )

    encoder = (
        get_nvenc_encoder()
    )

    # -----------------------------------------
    # 注意：
    # 這裡使用「裁出來的清晰影片」
    # 作為來源解析度
    # -----------------------------------------

    target_bitrate = (
        calculate_16_9_bitrate(
            crop_w,
            video_height
        )
    )

    base, ext = os.path.splitext(
        video_path
    )

    output_file = (
        base
        + "_紅線擷取_左右模糊16x9.mp4"
    )

    log.delete(
        "1.0",
        tk.END
    )

    log.insert(
        tk.END,
        "===== 紅線擷取 → 左右模糊16:9 =====\n"
        f"清晰區：{crop_w}x{video_height}\n"
        f"輸出：1920x1080\n"
        f"原片碼率：{format_bitrate(source_bitrate)}\n"
        f"補償後碼率：{format_bitrate(target_bitrate)}\n"
        f"估計大小：約 {estimate_size_mb(target_bitrate):.1f} MB\n"
        f"模糊：{blur_value}\n"
        f"背景上下：{bg_position}%\n\n"
    )

    set_buttons(
        False
    )

    threading.Thread(
        target=run_crop_blur,
        args=(
            video_path,
            output_file,
            crop_x,
            crop_w,
            blur_value,
            bg_position,
            encoder,
            target_bitrate
        ),
        daemon=True
    ).start()


def run_crop_blur(
    input_file,
    output_file,
    crop_x,
    crop_w,
    blur_value,
    bg_position,
    encoder,
    target_bitrate
):

    y_ratio = (
        bg_position
        / 100.0
    )

    bitrate = bitrate_string(
        target_bitrate
    )

    maxrate = bitrate_string(
        int(
            target_bitrate
            * 1.25
        )
    )

    bufsize = bitrate_string(
        int(
            target_bitrate
            * 2
        )
    )

    filter_complex = (
        "[0:v]"
        f"crop={crop_w}:ih:{crop_x}:0"
        "[center];"

        "[center]"
        "split=2"
        "[bg][fg];"

        "[bg]"
        "scale=1920:1080:"
        "force_original_aspect_ratio=increase,"
        "crop=1920:1080:"
        "(iw-1920)/2:"
        f"(ih-1080)*{y_ratio},"
        f"boxblur={blur_value}:2"
        "[bgblur];"

        "[fg]"
        "scale=1920:1080:"
        "force_original_aspect_ratio=decrease"
        "[fgclear];"

        "[bgblur][fgclear]"
        "overlay="
        "(W-w)/2:"
        "(H-h)/2"
        "[outv]"
    )

    command = [
        "ffmpeg",
        "-y",

        "-i",
        input_file,

        "-filter_complex",
        filter_complex,

        "-map",
        "[outv]",

        "-map",
        "0:a?",

        "-c:v",
        encoder,

        "-preset",
        "p5",

        "-b:v",
        bitrate,

        "-maxrate",
        maxrate,

        "-bufsize",
        bufsize,

        "-c:a",
        "copy",

        "-movflags",
        "+faststart",

        output_file
    ]

    run_process(
        command,
        output_file
    )


# =========================================================
# 按鈕 3：
# 完整原片 → 16:9 模糊
# 完全不理紅線
# =========================================================

def start_original_blur():

    if not video_path:

        messagebox.showwarning(
            "提示",
            "請先選擇影片"
        )

        return

    blur_value = int(
        blur_var.get()
    )

    bg_position = int(
        position_var.get()
    )

    encoder = (
        get_nvenc_encoder()
    )

    target_bitrate = (
        calculate_16_9_bitrate(
            video_width,
            video_height
        )
    )

    base, ext = os.path.splitext(
        video_path
    )

    output_file = (
        base
        + "_原影片_左右模糊16x9.mp4"
    )

    log.delete(
        "1.0",
        tk.END
    )

    log.insert(
        tk.END,
        "===== 完整原影片 → 左右模糊16:9 =====\n"
        "※ 此模式完全不使用紅線\n"
        f"原片：{video_width}x{video_height}\n"
        f"輸出：1920x1080\n"
        f"原片碼率：{format_bitrate(source_bitrate)}\n"
        f"補償後碼率：{format_bitrate(target_bitrate)}\n"
        f"估計大小：約 {estimate_size_mb(target_bitrate):.1f} MB\n"
        f"模糊：{blur_value}\n"
        f"背景上下：{bg_position}%\n\n"
    )

    set_buttons(
        False
    )

    threading.Thread(
        target=run_original_blur,
        args=(
            video_path,
            output_file,
            blur_value,
            bg_position,
            encoder,
            target_bitrate
        ),
        daemon=True
    ).start()


def run_original_blur(
    input_file,
    output_file,
    blur_value,
    bg_position,
    encoder,
    target_bitrate
):

    y_ratio = (
        bg_position
        / 100.0
    )

    bitrate = bitrate_string(
        target_bitrate
    )

    maxrate = bitrate_string(
        int(
            target_bitrate
            * 1.25
        )
    )

    bufsize = bitrate_string(
        int(
            target_bitrate
            * 2
        )
    )

    filter_complex = (
        "[0:v]"
        "split=2"
        "[bg][fg];"

        "[bg]"
        "scale=1920:1080:"
        "force_original_aspect_ratio=increase,"
        "crop=1920:1080:"
        "(iw-1920)/2:"
        f"(ih-1080)*{y_ratio},"
        f"boxblur={blur_value}:2"
        "[bgblur];"

        "[fg]"
        "scale=1920:1080:"
        "force_original_aspect_ratio=decrease"
        "[fgclear];"

        "[bgblur][fgclear]"
        "overlay="
        "(W-w)/2:"
        "(H-h)/2"
        "[outv]"
    )

    command = [
        "ffmpeg",
        "-y",

        "-i",
        input_file,

        "-filter_complex",
        filter_complex,

        "-map",
        "[outv]",

        "-map",
        "0:a?",

        "-c:v",
        encoder,

        "-preset",
        "p5",

        "-b:v",
        bitrate,

        "-maxrate",
        maxrate,

        "-bufsize",
        bufsize,

        "-c:a",
        "copy",

        "-movflags",
        "+faststart",

        output_file
    ]

    run_process(
        command,
        output_file
    )


# =========================================================
# FFmpeg 共用
# =========================================================

def run_process(
    command,
    output_file
):

    try:

        process = subprocess.Popen(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
            creationflags=subprocess.CREATE_NO_WINDOW
        )

        for line in process.stdout:

            root.after(
                0,
                append_log,
                line
            )

        process.wait()

        if process.returncode == 0:

            root.after(
                0,
                conversion_done,
                output_file
            )

        else:

            root.after(
                0,
                conversion_failed
            )

    except Exception as e:

        error_text = str(e)

        root.after(
            0,
            lambda: messagebox.showerror(
                "錯誤",
                error_text
            )
        )

        root.after(
            0,
            set_buttons,
            True
        )


def append_log(text):

    log.insert(
        tk.END,
        text
    )

    log.see(
        tk.END
    )


def conversion_done(
    output_file
):

    set_buttons(
        True
    )

    messagebox.showinfo(
        "完成",
        "處理完成！\n\n"
        + output_file
    )


def conversion_failed():

    set_buttons(
        True
    )

    messagebox.showerror(
        "失敗",
        "FFmpeg 處理失敗。\n"
        "請查看下方紀錄。"
    )


# =========================================================
# 按鈕鎖定
# =========================================================

def set_buttons(enabled):

    state = (
        "normal"
        if enabled
        else "disabled"
    )

    select_button.config(
        state=state
    )

    crop_only_button.config(
        state=state
    )

    crop_blur_button.config(
        state=state
    )

    original_blur_button.config(
        state=state
    )


# =========================================================
# Slider
# =========================================================

def update_blur_label(value):

    blur_value_label.config(
        text=str(
            int(
                float(value)
            )
        )
    )


def update_position_label(value):

    value = int(
        float(value)
    )

    position_value_label.config(
        text=f"{value}%"
    )


# =========================================================
# 關閉
# =========================================================

def on_close():

    if cap is not None:
        cap.release()

    root.destroy()


# =========================================================
# GUI
# =========================================================

root = tk.Tk()

root.title(
    "影片紅線裁切 / 原碼率偵測 / 左右模糊16:9"
)

# 不再做 930 高
# 1080p 螢幕比較容易全部看到
root.geometry(
    "820x850"
)

root.minsize(
    780,
    800
)

root.protocol(
    "WM_DELETE_WINDOW",
    on_close
)


# =========================================================
# 變數
# =========================================================

input_var = tk.StringVar()

blur_var = tk.IntVar(
    value=12
)

position_var = tk.IntVar(
    value=25
)


# =========================================================
# 標題
# =========================================================

tk.Label(
    root,
    text="影片手動紅線裁切",
    font=(
        "Microsoft JhengHei",
        17,
        "bold"
    )
).pack(
    pady=(
        5,
        0
    )
)


tk.Label(
    root,
    text=(
        "自動偵測 Codec / Bitrate "
        "＋ 1920×1080 碼率補償"
    )
).pack(
    pady=(
        0,
        3
    )
)


# =========================================================
# 檔案
# =========================================================

file_frame = tk.Frame(
    root
)

file_frame.pack(
    fill="x",
    padx=15
)


tk.Entry(
    file_frame,
    textvariable=input_var
).pack(
    side="left",
    fill="x",
    expand=True
)


select_button = tk.Button(
    file_frame,
    text="選擇影片",
    command=choose_file,
    width=10
)

select_button.pack(
    side="left",
    padx=5
)


# =========================================================
# 資訊
# =========================================================

info_label = tk.Label(
    root,
    text="尚未選擇影片"
)

info_label.pack(
    pady=(
        3,
        0
    )
)


codec_info_label = tk.Label(
    root,
    text="等待偵測",
    font=(
        "Microsoft JhengHei",
        9,
        "bold"
    )
)

codec_info_label.pack(
    pady=(
        0,
        2
    )
)


# =========================================================
# 預覽
# =========================================================

preview_canvas = tk.Canvas(
    root,
    width=PREVIEW_W,
    height=PREVIEW_H,
    bg="#202020",
    highlightthickness=1
)

preview_canvas.pack(
    pady=2
)


preview_canvas.bind(
    "<Button-1>",
    preview_mouse_down
)

preview_canvas.bind(
    "<B1-Motion>",
    preview_mouse_drag
)

preview_canvas.bind(
    "<ButtonRelease-1>",
    preview_mouse_up
)


# =========================================================
# 裁切資訊
# =========================================================

crop_info_label = tk.Label(
    root,
    text="紅線中間 = 保留區域",
    font=(
        "Microsoft JhengHei",
        10,
        "bold"
    )
)

crop_info_label.pack(
    pady=1
)


# =========================================================
# 快捷裁切
# =========================================================

quick_frame = tk.Frame(
    root
)

quick_frame.pack(
    pady=1
)


tk.Button(
    quick_frame,
    text="左右10%",
    command=reset_lines
).pack(
    side="left",
    padx=2
)


tk.Button(
    quick_frame,
    text="完整",
    command=full_width
).pack(
    side="left",
    padx=2
)


tk.Button(
    quick_frame,
    text="中央 9:16",
    command=set_9_16
).pack(
    side="left",
    padx=2
)


tk.Button(
    quick_frame,
    text="中央 764:1080",
    command=set_764_ratio
).pack(
    side="left",
    padx=2
)


# =========================================================
# 時間軸
# =========================================================

timeline_frame = tk.Frame(
    root
)

timeline_frame.pack(
    fill="x",
    padx=15
)


timeline = tk.Scale(
    timeline_frame,
    from_=0,
    to=1,
    resolution=0.1,
    orient="horizontal",
    showvalue=False,
    command=timeline_changed
)

timeline.pack(
    side="left",
    fill="x",
    expand=True
)


current_time_label = tk.Label(
    timeline_frame,
    text="00:00 / 00:00",
    width=17
)

current_time_label.pack(
    side="left"
)


# =========================================================
# 時間快捷
# =========================================================

jump_frame = tk.Frame(
    root
)

jump_frame.pack(
    pady=0
)


for text_, value_ in [
    ("開頭", 0.02),
    ("25%", 0.25),
    ("50%", 0.50),
    ("75%", 0.75),
    ("結尾", 0.98)
]:

    tk.Button(
        jump_frame,
        text=text_,
        width=7,
        command=(
            lambda p=value_:
            jump_percent(p)
        )
    ).pack(
        side="left",
        padx=2
    )


# =========================================================
# 模糊設定
# =========================================================

settings_frame = tk.Frame(
    root
)

settings_frame.pack(
    pady=0
)


tk.Label(
    settings_frame,
    text="模糊"
).grid(
    row=0,
    column=0
)


tk.Scale(
    settings_frame,
    from_=1,
    to=20,
    resolution=1,
    variable=blur_var,
    orient="horizontal",
    showvalue=False,
    length=200,
    command=update_blur_label
).grid(
    row=0,
    column=1
)


blur_value_label = tk.Label(
    settings_frame,
    text="12",
    width=5
)

blur_value_label.grid(
    row=0,
    column=2
)


tk.Label(
    settings_frame,
    text="背景上下"
).grid(
    row=1,
    column=0
)


tk.Scale(
    settings_frame,
    from_=0,
    to=100,
    resolution=5,
    variable=position_var,
    orient="horizontal",
    showvalue=False,
    length=200,
    command=update_position_label
).grid(
    row=1,
    column=1
)


position_value_label = tk.Label(
    settings_frame,
    text="25%",
    width=5
)

position_value_label.grid(
    row=1,
    column=2
)


# =========================================================
# ★ 三顆功能按鈕
# =========================================================

button_frame = tk.Frame(
    root
)

button_frame.pack(
    pady=4
)


crop_only_button = tk.Button(
    button_frame,
    text="① 只擷取紅線中間",
    command=start_crop_only,
    width=22,
    height=2,
    font=(
        "Microsoft JhengHei",
        10,
        "bold"
    )
)

crop_only_button.grid(
    row=0,
    column=0,
    padx=4,
    pady=2
)


crop_blur_button = tk.Button(
    button_frame,
    text="② 紅線擷取＋左右模糊16:9",
    command=start_crop_blur,
    width=25,
    height=2,
    font=(
        "Microsoft JhengHei",
        10,
        "bold"
    )
)

crop_blur_button.grid(
    row=0,
    column=1,
    padx=4,
    pady=2
)


original_blur_button = tk.Button(
    button_frame,
    text="③ 完整原影片＋左右模糊16:9",
    command=start_original_blur,
    width=49,
    height=2,
    font=(
        "Microsoft JhengHei",
        10,
        "bold"
    )
)

original_blur_button.grid(
    row=1,
    column=0,
    columnspan=2,
    padx=4,
    pady=2
)


# =========================================================
# 提示
# =========================================================

tk.Label(
    root,
    text=(
        "① 只裁切　"
        "② 先用紅線取中間再補模糊　"
        "③ 真正直式影片直接補模糊"
    ),
    font=(
        "Microsoft JhengHei",
        8
    )
).pack()


# =========================================================
# LOG
# =========================================================

log = tk.Text(
    root,
    height=3,
    font=(
        "Consolas",
        8
    )
)

log.pack(
    fill="both",
    expand=True,
    padx=15,
    pady=(
        2,
        5
    )
)


# =========================================================
# 啟動
# =========================================================

root.mainloop()