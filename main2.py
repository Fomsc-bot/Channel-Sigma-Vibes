#!/usr/bin/env python3

import cv2
import numpy as np
import pandas as pd
import pytesseract
import random
import subprocess
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont, ImageFilter
from gtts import gTTS
import uuid
import os
import sys
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
from google.oauth2.credentials import Credentials

# ================= CONFIG =================

VIDEO_WIDTH = 1920
VIDEO_HEIGHT = 1080
FPS = 30

THUMB_DURATION = 1
OUTTRO_DURATION = 2
FONT_PATH = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"

THUMB_DIR = Path("thumbnails")
BG_DIR = Path("backgroundim")
OUTTRO_DIR = Path("outtro")
SCRIPT_CSV = Path("Script/script.csv")
OUTPUT_DIR = Path("outputs")
OUTPUT_DIR.mkdir(exist_ok=True)

# ================= YOUTUBE AUTH =================

CLIENT_ID = os.environ.get("YT_CLIENT_ID")
CLIENT_SECRET = os.environ.get("YT_CLIENT_SECRET")
REFRESH_TOKEN = os.environ.get("YT_REFRESH_TOKEN")

if not CLIENT_ID or not CLIENT_SECRET or not REFRESH_TOKEN:
    print("❌ Missing YouTube credentials.")
    sys.exit(1)

# ================= UTILITIES =================

def generate_voice(text, out_path):
    text = text.replace("’", "'").replace("‘", "'")
    gTTS(text=text, lang="en").save(out_path)

def resize(img):
    return img.resize((VIDEO_WIDTH, VIDEO_HEIGHT), Image.LANCZOS)

def ease_in_out(t):
    return 0.5 - 0.5 * np.cos(np.pi * t)

def prepare_ken_burns(img):
    return random.uniform(1.05, 1.15), random.choice([0, 0.5, 1]), random.choice([0, 0.5, 1])

def ken_burns_frame(img, idx, total, zoom_end, pan_x, pan_y):
    t = ease_in_out(idx / total)
    zoom = 1 + (zoom_end - 1) * t
    w, h = img.size
    cw, ch = int(w / zoom), int(h / zoom)
    x = int((w - cw) * pan_x * t)
    y = int((h - ch) * pan_y * t)
    return img.crop((x, y, x + cw, y + ch)).resize((VIDEO_WIDTH, VIDEO_HEIGHT), Image.LANCZOS)

def draw_caption(img, text):
    draw = ImageDraw.Draw(img)
    font = ImageFont.truetype(FONT_PATH, 60)
    w = draw.textlength(text, font)
    x = (VIDEO_WIDTH - w) // 2
    y = VIDEO_HEIGHT // 2
    draw.text((x+3, y+3), text, font=font, fill="black")
    draw.text((x, y), text, font=font, fill="white")
    return img

# ================= VIDEO CREATION =================

def create_video(row):
    thumb_file = THUMB_DIR / row["Imagename"]

    if not thumb_file.exists():
        print(f"❌ Thumbnail not found: {thumb_file}")
        return None, None

    bg_file = random.choice(list(BG_DIR.glob("*")))
    outtro_file = random.choice(list(OUTTRO_DIR.glob("*")))

    voice_file = OUTPUT_DIR / f"{uuid.uuid4().hex}.mp3"
    generate_voice(row["Voiceover Text"], voice_file)

    duration = float(subprocess.check_output([
        "ffprobe","-v","error","-show_entries",
        "format=duration","-of","default=noprint_wrappers=1:nokey=1",
        str(voice_file)
    ]))

    total_frames = int(duration * FPS)
    temp_video = OUTPUT_DIR / f"{uuid.uuid4().hex}_temp.mp4"

    writer = cv2.VideoWriter(
        str(temp_video),
        cv2.VideoWriter_fourcc(*"mp4v"),
        FPS,
        (VIDEO_WIDTH, VIDEO_HEIGHT)
    )

    # Thumbnail
    thumb_img = resize(Image.open(thumb_file))
    for _ in range(THUMB_DURATION * FPS):
        frame = draw_caption(thumb_img.copy(), row["Title"])
        writer.write(cv2.cvtColor(np.array(frame), cv2.COLOR_RGB2BGR))

    # Main
    bg_img = resize(Image.open(bg_file))
    zoom_end, pan_x, pan_y = prepare_ken_burns(bg_img)

    for i in range(total_frames):
        frame = ken_burns_frame(bg_img, i, total_frames, zoom_end, pan_x, pan_y)
        frame = draw_caption(frame, row["Voiceover Text"])
        writer.write(cv2.cvtColor(np.array(frame), cv2.COLOR_RGB2BGR))

    # Outro
    outro_img = resize(Image.open(outtro_file))
    for _ in range(OUTTRO_DURATION * FPS):
        writer.write(cv2.cvtColor(np.array(outro_img), cv2.COLOR_RGB2BGR))

    writer.release()

    final_video = OUTPUT_DIR / f"{uuid.uuid4().hex}_final.mp4"

    subprocess.run([
        "ffmpeg","-y",
        "-i", str(temp_video),
        "-i", str(voice_file),
        "-c:v","copy",
        "-c:a","aac",
        str(final_video)
    ], check=True)

    temp_video.unlink()
    voice_file.unlink()

    return final_video, thumb_file

# ================= UPLOAD =================

def upload(video_file, row):
    creds = Credentials(
        None,
        refresh_token=REFRESH_TOKEN,
        token_uri="https://oauth2.googleapis.com/token",
        client_id=CLIENT_ID,
        client_secret=CLIENT_SECRET,
        scopes=["https://www.googleapis.com/auth/youtube.upload"]
    )

    youtube = build("youtube", "v3", credentials=creds)

    response = youtube.videos().insert(
        part="snippet,status",
        body={
            "snippet": {
                "title": row["Title"],
                "description": row["Voiceover Text"],
                "categoryId": "22"
            },
            "status": {"privacyStatus": "public"}
        },
        media_body=MediaFileUpload(str(video_file))
    ).execute()

    print("✅ Uploaded:", response["id"])
    return True

# ================= MAIN =================

def main():
    df = pd.read_csv(SCRIPT_CSV, encoding="latin1")

    if df.empty:
        print("⚠ CSV empty")
        return

    row = df.iloc[0]

    video_file, thumb_file = create_video(row)
    if not video_file:
        return

    if upload(video_file, row):
        # Delete thumbnail
        if thumb_file.exists():
            thumb_file.unlink()

        # Remove used row from CSV
        df = df.drop(index=0)
        df.to_csv(SCRIPT_CSV, index=False)

        print("🧹 Used data and thumbnail removed")

if __name__ == "__main__":
    main()
