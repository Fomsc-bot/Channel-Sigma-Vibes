#!/usr/bin/env python3

import cv2
import numpy as np
import pandas as pd
import pytesseract
import random
import subprocess
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont
from gtts import gTTS
import uuid
import os
import sys
import math
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
from google.oauth2.credentials import Credentials
from fuzzywuzzy import process

# ================= CONFIG =================

VIDEO_WIDTH = 1920
VIDEO_HEIGHT = 1080
FPS = 30

THUMB_DURATION = 1        # seconds
OUTTRO_DURATION = 2       # seconds
FONT_PATH = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
FONT_SIZE = 60

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
    print("❌ Missing YouTube credentials. Set YT_CLIENT_ID, YT_CLIENT_SECRET, YT_REFRESH_TOKEN.")
    sys.exit(1)

# ================= UTILITIES =================

def extract_text_from_image(img_path):
    """Robust OCR to get text from thumbnail"""
    img = Image.open(img_path)
    text = pytesseract.image_to_string(img, lang="eng")
    text = " ".join(text.split())
    return text if text else "Double Meaning Quote"

def generate_voice(text, out_path):
    tts = gTTS(text=text, lang="en")
    tts.save(out_path)

def resize(img):
    return img.resize((VIDEO_WIDTH, VIDEO_HEIGHT), Image.LANCZOS)

def ease_in_out(t):
    return 0.5 - 0.5 * np.cos(np.pi * t)

def prepare_ken_burns(img):
    zoom_end = random.uniform(1.05, 1.15)
    pan_x = random.choice([0, 0.5, 1])
    pan_y = random.choice([0, 0.5, 1])
    return zoom_end, pan_x, pan_y

def ken_burns_frame(img, idx, total, zoom_end, pan_x, pan_y):
    t = ease_in_out(idx / total)
    zoom = 1 + (zoom_end - 1) * t
    w, h = img.size
    cw, ch = int(w / zoom), int(h / zoom)
    x = int((w - cw) * pan_x * t)
    y = int((h - ch) * pan_y * t)
    crop = img.crop((x, y, x + cw, y + ch))
    return crop.resize((VIDEO_WIDTH, VIDEO_HEIGHT), Image.LANCZOS)

def wrap_text(draw, text, font, max_width):
    words = text.split()
    lines = []
    while words:
        line = ""
        while words and draw.textlength(line + words[0] + " ", font=font) < max_width:
            line += words.pop(0) + " "
        lines.append(line.strip())
    return lines

def draw_typewriter_text(img, text, frame_idx, total_frames):
    draw = ImageDraw.Draw(img)
    font = ImageFont.truetype(FONT_PATH, FONT_SIZE)
    num_chars = int(len(text) * frame_idx / total_frames)
    visible_text = text[:num_chars]
    lines = wrap_text(draw, visible_text, font, VIDEO_WIDTH * 0.8)
    total_h = sum(font.getbbox(l)[3] for l in lines) + 10 * len(lines)
    y = (VIDEO_HEIGHT - total_h) // 2
    for l in lines:
        w = draw.textlength(l, font)
        x = (VIDEO_WIDTH - w) // 2
        draw.text((x+3, y+3), l, font=font, fill="black")
        draw.text((x, y), l, font=font, fill="white")
        y += font.getbbox(l)[3] + 10

# ================= VIDEO CREATION =================

def create_video(row):
    # --- Thumbnail selection: fuzzy OCR matching
    thumb_file = None
    thumbnails = list(THUMB_DIR.glob("*"))
    best_match = None
    if thumbnails:
        thumb_texts = [extract_text_from_image(f) for f in thumbnails]
        best_match, score = process.extractOne(row['Title'], thumb_texts)
        if score >= 80:
            idx = thumb_texts.index(best_match)
            thumb_file = thumbnails[idx]
    if not thumb_file:
        print(f"⚠ No thumbnail found for {row['Title']}")
        return None

    bg_file = random.choice(list(BG_DIR.glob("*")))
    outtro_file = random.choice(list(OUTTRO_DIR.glob("*")))
    voice_file = OUTPUT_DIR / f"{uuid.uuid4().hex}_voice.mp3"

    generate_voice(row['Voiceover Text'], voice_file)

    # get duration of voice
    try:
        duration = float(subprocess.check_output([
            "ffprobe","-v","error","-show_entries",
            "format=duration","-of",
            "default=noprint_wrappers=1:nokey=1", str(voice_file)
        ]).decode().strip())
    except:
        duration = max(len(row['Voiceover Text'].split())/2, 5)

    total_frames = int(duration * FPS)
    writer_path = OUTPUT_DIR / f"{uuid.uuid4().hex}_temp.mp4"
    writer = cv2.VideoWriter(str(writer_path), cv2.VideoWriter_fourcc(*"mp4v"), FPS, (VIDEO_WIDTH, VIDEO_HEIGHT))

    # --- Thumbnail scene
    thumb_img = resize(Image.open(thumb_file))
    for _ in range(THUMB_DURATION * FPS):
        writer.write(cv2.cvtColor(np.array(thumb_img), cv2.COLOR_RGB2BGR))

    # --- Main scene with Ken Burns + typewriter
    bg_img = resize(Image.open(bg_file))
    zoom_end, pan_x, pan_y = prepare_ken_burns(bg_img)
    for i in range(total_frames):
        frame = ken_burns_frame(bg_img, i, total_frames, zoom_end, pan_x, pan_y)
        draw_typewriter_text(frame, row['Voiceover Text'], i, total_frames)
        writer.write(cv2.cvtColor(np.array(frame), cv2.COLOR_RGB2BGR))

    # --- Outtro
    outtro_img = resize(Image.open(outtro_file))
    for _ in range(OUTTRO_DURATION * FPS):
        writer.write(cv2.cvtColor(np.array(outtro_img), cv2.COLOR_RGB2BGR))

    writer.release()

    # --- Merge voice
    final_path = OUTPUT_DIR / f"{uuid.uuid4().hex}_final.mp4"
    subprocess.run([
        "ffmpeg","-y","-i", str(writer_path), "-i", str(voice_file),
        "-c:v","copy","-c:a","aac", str(final_path)
    ], check=True)

    # cleanup temp files
    writer_path.unlink()
    voice_file.unlink()
    thumb_file.unlink()

    return final_path

# ================= UPLOAD =================

def upload(video_file, row):
    creds = Credentials(None, refresh_token=REFRESH_TOKEN, token_uri="https://oauth2.googleapis.com/token",
                        client_id=CLIENT_ID, client_secret=CLIENT_SECRET, scopes=["https://www.googleapis.com/auth/youtube.upload"])
    youtube = build("youtube", "v3", credentials=creds)
    try:
        response = youtube.videos().insert(
            part="snippet,status",
            body={
                "snippet": {
                    "title": row['Title'],
                    "description": row['Voiceover Text'] + "\n\n#motivation #success #mindset",
                    "categoryId": "22"
                },
                "status":{"privacyStatus":"public"}
            },
            media_body=MediaFileUpload(video_file, resumable=True)
        ).execute()
        print("✅ Uploaded Video ID:", response.get("id"))
    except Exception as e:
        print("❌ Upload failed:", e)

# ================= MAIN =================

def main():
    try:
        df = pd.read_csv(SCRIPT_CSV, encoding='latin1')
    except Exception as e:
        print("❌ Failed to read CSV:", e)
        return

    if df.empty:
        print("⚠ CSV empty, nothing to upload.")
        return

    row = df.iloc[0]  # take first row
    video_file = create_video(row)
    if video_file:
        upload(video_file, row)
        # remove row from CSV
        df = df.drop(row.name)
        df.to_csv(SCRIPT_CSV, index=False)
    else:
        print("⚠ Video creation failed.")

if __name__ == "__main__":
    main()
