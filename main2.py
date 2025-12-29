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
FONT_SIZE = 60

THUMB_DIR = Path("thumbnails")
BG_DIR = Path("backgroundim")
OUTTRO_DIR = Path("outtro")
SCRIPT_CSV = Path("Script/script.csv")
OUTPUT_DIR = Path("outputs")
OUTPUT_DIR.mkdir(exist_ok=True)

# ============== YOUTUBE AUTH ==============

CLIENT_ID = os.environ["YT_CLIENT_ID"]
CLIENT_SECRET = os.environ["YT_CLIENT_SECRET"]
REFRESH_TOKEN = os.environ["YT_REFRESH_TOKEN"]

# ================= OCR ====================

def extract_text_from_image(img_path):
    img = Image.open(img_path)
    return pytesseract.image_to_string(img).strip()

# ================= TTS ====================

def generate_voice(text, out_path):
    tts = gTTS(text=text, lang="en")
    tts.save(out_path)

# ============== VIDEO HELPERS =============

def resize(img):
    return img.resize((VIDEO_WIDTH, VIDEO_HEIGHT), Image.LANCZOS)

def draw_caption(img, text):
    draw = ImageDraw.Draw(img)
    font = ImageFont.truetype(FONT_PATH, FONT_SIZE)

    words = text.split()
    lines, line = [], ""

    for w in words:
        test = f"{line} {w}".strip()
        if draw.textlength(test, font) < VIDEO_WIDTH * 0.8:
            line = test
        else:
            lines.append(line)
            line = w
    lines.append(line)

    total_h = sum(font.getbbox(l)[3] for l in lines) + 10 * len(lines)
    y = (VIDEO_HEIGHT - total_h) // 2

    for l in lines:
        w = draw.textlength(l, font)
        x = (VIDEO_WIDTH - w) // 2
        draw.text((x+3, y+3), l, font=font, fill="black")
        draw.text((x, y), l, font=font, fill="white")
        y += font.getbbox(l)[3] + 10

# ================= VIDEO ==================

def create_video(thumb, bg, outtro, voice_text):
    video_path = OUTPUT_DIR / f"{uuid.uuid4().hex}.mp4"
    voice_path = OUTPUT_DIR / "voice.mp3"

    generate_voice(voice_text, voice_path)
    duration = int(subprocess.check_output(
        ["ffprobe", "-v", "error", "-show_entries",
         "format=duration", "-of", "default=noprint_wrappers=1:nokey=1", voice_path]
    ).decode().strip().split(".")[0])

    writer = cv2.VideoWriter(
        str(video_path),
        cv2.VideoWriter_fourcc(*"mp4v"),
        FPS,
        (VIDEO_WIDTH, VIDEO_HEIGHT)
    )

    # Thumbnail
    thumb_img = resize(Image.open(thumb))
    for _ in range(THUMB_DURATION * FPS):
        writer.write(cv2.cvtColor(np.array(thumb_img), cv2.COLOR_RGB2BGR))

    # Main scene
    bg_img = resize(Image.open(bg))
    for _ in range(duration * FPS):
        frame = bg_img.copy()
        draw_caption(frame, voice_text)
        writer.write(cv2.cvtColor(np.array(frame), cv2.COLOR_RGB2BGR))

    # Outtro
    outtro_img = resize(Image.open(outtro))
    for _ in range(OUTTRO_DURATION * FPS):
        writer.write(cv2.cvtColor(np.array(outtro_img), cv2.COLOR_RGB2BGR))

    writer.release()

    final_path = video_path.with_name(video_path.stem + "_final.mp4")

    subprocess.run([
        "ffmpeg", "-y",
        "-i", str(video_path),
        "-i", str(voice_path),
        "-c:v", "copy",
        "-c:a", "aac",
        str(final_path)
    ], check=True)

    return final_path

# ================= UPLOAD =================

def upload(video, title, description):
    creds = Credentials(
        None,
        refresh_token=REFRESH_TOKEN,
        token_uri="https://oauth2.googleapis.com/token",
        client_id=CLIENT_ID,
        client_secret=CLIENT_SECRET,
        scopes=["https://www.googleapis.com/auth/youtube.upload"]
    )

    youtube = build("youtube", "v3", credentials=creds)

    youtube.videos().insert(
        part="snippet,status",
        body={
            "snippet": {
                "title": title,
                "description": description + "\n\n#motivation #success #mindset",
                "categoryId": "22"
            },
            "status": {"privacyStatus": "public"}
        },
        media_body=MediaFileUpload(video, resumable=True)
    ).execute()

# ================= MAIN ===================

def main():
    df = pd.read_csv(SCRIPT_CSV, encoding='latin1')

    for thumb in THUMB_DIR.glob("*"):
        img_text = extract_text_from_image(thumb)

        match = df[df["Title"].str.lower() == img_text.lower()]
        if match.empty:
            continue

        row = match.iloc[0]
        bg = random.choice(list(BG_DIR.glob("*")))
        outtro = random.choice(list(OUTTRO_DIR.glob("*")))

        video = create_video(thumb, bg, outtro, row["Voiceover Text"])
        upload(video, row["Title"], row["Voiceover Text"])

        # Cleanup
        df = df.drop(row.name)
        thumb.unlink()
        df.to_csv(SCRIPT_CSV, index=False)
        break

if __name__ == "__main__":
    main()
