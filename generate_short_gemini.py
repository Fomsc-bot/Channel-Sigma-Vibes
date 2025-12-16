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

CLIENT_ID = "CLIENT_ID"
CLIENT_SECRET = "CLIENT_SECRET"
REFRESH_TOKEN = "REFRESH_TOKEN"

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

    title = f"{quote[:80]} #shorts"
    description = f"{quote}\n\n#shorts #motivation #sigma #mindset"
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
# TEXT
# ===============================

def draw_typewriter_text(img, text, frame_idx):
    draw = ImageDraw.Draw(img)
    font = ImageFont.truetype(FONT_PATH, FONT_SIZE)

    visible = text[:frame_idx * TYPE_SPEED]
    bbox = draw.textbbox((0,0), visible, font=font)

    x = (VIDEO_WIDTH - (bbox[2]-bbox[0])) // 2
    y = VIDEO_HEIGHT // 2

    draw.text((x+3, y+3), visible, font=font, fill=(0,0,0))
    draw.text((x, y), visible, font=font, fill=(255,255,255))

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
