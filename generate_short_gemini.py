#!/usr/bin/env python3 
import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont
from pathlib import Path
import random
import uuid
import subprocess

from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
from google.oauth2.credentials import Credentials

# ===============================
# CONFIG
# ===============================

OUTPUT_DIR = Path("outputs")
OUTPUT_DIR.mkdir(exist_ok=True)

BACKGROUND_DIR = Path("Background_images")
MERGE_VIDEO_DIR = Path("out")
MUSIC_DIR = Path("Background_Music")

VIDEO_WIDTH = 1080
VIDEO_HEIGHT = 1920
FPS = 30
SCENE_DURATION = 5

QUOTE_FILE = "quotes.txt"
FONT_PATH = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
FONT_SIZE = 80

FADE_FRAMES = 15
TYPE_SPEED = 2

# ===============================
# YOUTUBE CREDENTIALS
# ===============================

CLIENT_ID = "193654836130-ete2tqnm52un70bnj5ahfp23qlpt4g5u.apps.googleusercontent.com"
CLIENT_SECRET = "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"
REFRESH_TOKEN = "1//0gT9zWzMp_ABrCgYIARAAGBASNwF-L9IrujGKCmb2P2pIpKsH8gf4Av2p90dDCbRWnD3vJZfIX7fvgHViK0yAmQLYZiBOYmfT_r8"

# ===============================
# UTILITIES
# ===============================

def ease_in_out(t):
    return 0.5 - 0.5 * np.cos(np.pi * t)

# ===============================
# YOUTUBE UPLOAD
# ===============================

def upload_to_youtube(video_path, quote):
    creds = Credentials(
        None,
        refresh_token=REFRESH_TOKEN,
        token_uri="https://oauth2.googleapis.com/token",
        client_id=CLIENT_ID,
        client_secret=CLIENT_SECRET,
        scopes=["https://www.googleapis.com/auth/youtube.upload"],
    )

    youtube = build("youtube", "v3", credentials=creds)

    # --- TITLE FIX: 3 words + emojis + hashtags
    words = quote.split()
    title_words = words[:3]
    emojis = ["💪","🔥","🧠","✨","⚡"]
    hashtags = "#shorts #motivation #sigma #mindset"
    title = " ".join(title_words) + " " + random.choice(emojis) + " " + hashtags
    
    description = quote  # now only the quote itself
    tags = ["shorts", "motivation", "sigma", "mindset"]

    request = youtube.videos().insert(
        part="snippet,status",
        body={
            "snippet": {
                "title": title,
                "description": description,
                "tags": tags,
                "categoryId": "22"
            },
            "status": {
                "privacyStatus": "public",
                "selfDeclaredMadeForKids": False
            }
        },
        media_body=MediaFileUpload(
            str(video_path),
            mimetype="video/mp4",
            resumable=True
        )
    )

    response = request.execute()
    print("🚀 Uploaded to YouTube!")
    print("🎬 Video ID:", response["id"])

# ===============================
# QUOTE
# ===============================

def load_quote():
    with open(QUOTE_FILE, "r", encoding="utf-8") as f:
        quotes = [q.strip() for q in f if q.strip()]

    quote = random.choice(quotes)
    quotes.remove(quote)

    with open(QUOTE_FILE, "w", encoding="utf-8") as f:
        for q in quotes:
            f.write(q + "\n")

    return quote

# ===============================
# BACKGROUND IMAGE
# ===============================

def load_background_image():
    img = Image.open(random.choice(list(BACKGROUND_DIR.glob("*.*")))).convert("RGB")

    img_ratio = img.width / img.height
    target_ratio = VIDEO_WIDTH / VIDEO_HEIGHT

    if img_ratio > target_ratio:
        new_w = int(img.height * target_ratio)
        x = (img.width - new_w) // 2
        img = img.crop((x, 0, x + new_w, img.height))
    else:
        new_h = int(img.width / target_ratio)
        y = (img.height - new_h) // 2
        img = img.crop((0, y, img.width, y + new_h))

    return img

# ===============================
# KEN BURNS
# ===============================

def prepare_ken_burns():
    return random.uniform(1.1, 1.2), random.choice([0, 0.5, 1]), random.choice([0, 0.5, 1])

def ken_burns_frame(img, idx, total, zoom_end, pan_x, pan_y):
    t = ease_in_out(idx / total)
    zoom = 1 + (zoom_end - 1) * t

    w, h = img.size
    cw, ch = int(w / zoom), int(h / zoom)

    x = int((w - cw) * pan_x * t)
    y = int((h - ch) * pan_y * t)

    crop = img.crop((x, y, x + cw, y + ch))
    return crop.resize((VIDEO_WIDTH, VIDEO_HEIGHT), Image.LANCZOS)

# ===============================
# TEXT (FIXED)
# ===============================

def wrap_text(draw, text, font, max_width):
    words = text.split()
    lines = []
    while words:
        line = ""
        while words and draw.textbbox((0,0), line + words[0], font=font)[2] < max_width:
            line += words.pop(0) + " "
        lines.append(line.strip())
    return lines

def draw_typewriter_text(img, text, frame_idx):
    draw = ImageDraw.Draw(img)
    font = ImageFont.truetype(FONT_PATH, FONT_SIZE)

    visible = text[:frame_idx * TYPE_SPEED]
    lines = wrap_text(draw, visible, font, VIDEO_WIDTH * 0.8)

    total_h = sum(draw.textbbox((0,0), l, font=font)[3] for l in lines)
    y = (VIDEO_HEIGHT - total_h) // 2

    for line in lines:
        bbox = draw.textbbox((0,0), line, font=font)
        x = (VIDEO_WIDTH - (bbox[2]-bbox[0])) // 2
        draw.text((x+3, y+3), line, font=font, fill=(0,0,0))
        draw.text((x, y), line, font=font, fill=(255,255,255))
        y += (bbox[3]-bbox[1]) + 10

# ===============================
# MUSIC
# ===============================

def add_background_music(video_path):
    music = random.choice(list(MUSIC_DIR.glob("*.*")))
    final_path = video_path.with_name(video_path.stem + "_music.mp4")

    subprocess.run([
        "ffmpeg", "-y",
        "-i", str(video_path),
        "-stream_loop", "-1",
        "-i", str(music),
        "-shortest",
        "-c:v", "copy",
        "-c:a", "aac",
        str(final_path)
    ], check=True)

    video_path.unlink()
    return final_path

# ===============================
# CREATE VIDEO
# ===============================

def create_video():
    quote = load_quote()
    bg = load_background_image()
    zoom_end, pan_x, pan_y = prepare_ken_burns()

    total_frames = SCENE_DURATION * FPS
    temp_video = OUTPUT_DIR / f"temp_{uuid.uuid4().hex}.mp4"

    writer = cv2.VideoWriter(
        str(temp_video),
        cv2.VideoWriter_fourcc(*"mp4v"),
        FPS,
        (VIDEO_WIDTH, VIDEO_HEIGHT)
    )

    for i in range(total_frames):
        img = ken_burns_frame(bg, i, total_frames, zoom_end, pan_x, pan_y)
        draw_typewriter_text(img, quote, i)
        frame = cv2.cvtColor(np.array(img), cv2.COLOR_RGB2BGR)
        writer.write(frame)

    writer.release()

    final_video = add_background_music(temp_video)
    print("🎵 Video ready:", final_video)

    upload_to_youtube(final_video, quote)

# ===============================
# RUN
# ===============================

if __name__ == "__main__":
    create_video()
