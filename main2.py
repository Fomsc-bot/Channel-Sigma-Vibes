#!/usr/bin/env python3

import cv2
import numpy as np
import pandas as pd
import pytesseract
import random
import subprocess
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont, ImageOps, ImageFilter
from gtts import gTTS
import uuid
import os
import sys
import textwrap
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
from google.oauth2.credentials import Credentials
from fuzzywuzzy import process

# ================= CONFIG =================

VIDEO_WIDTH = 1920
VIDEO_HEIGHT = 1080
FPS = 30

THUMB_DURATION = 1
OUTTRO_DURATION = 2

FONT_PATH = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
MIN_FONT_SIZE = 40
MAX_FONT_SIZE = 70
LINE_SPACING = 15
TEXT_PADDING = 100

BACKGROUND_BLUR_RADIUS = 15
TEXT_BACKGROUND_OPACITY = 0.7
SHADOW_OFFSET = (4, 4)
ANIMATION_DURATION = 0.5

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
    print("❌ Missing YouTube credentials")
    sys.exit(1)

# ================= UTILITIES =================

def generate_voice(text, out_path):
    gTTS(text=text, lang="en").save(out_path)

def resize(img):
    return img.resize((VIDEO_WIDTH, VIDEO_HEIGHT), Image.LANCZOS)

def ease(t):
    return 0.5 - 0.5 * np.cos(np.pi * t)

def prepare_ken_burns(img):
    return random.uniform(1.05, 1.15), random.random(), random.random()

def ken_burns_frame(img, idx, total, zoom_end, px, py):
    t = ease(idx / total)
    zoom = 1 + (zoom_end - 1) * t
    w, h = img.size
    cw, ch = int(w / zoom), int(h / zoom)
    x = int((w - cw) * px * t)
    y = int((h - ch) * py * t)
    return img.crop((x, y, x + cw, y + ch)).resize((VIDEO_WIDTH, VIDEO_HEIGHT))

def draw_caption(img, text, alpha=1.0):
    img = img.convert("RGBA")
    draw = ImageDraw.Draw(img)
    font = ImageFont.truetype(FONT_PATH, MAX_FONT_SIZE)

    bbox = draw.textbbox((0, 0), text, font=font)
    w = bbox[2] - bbox[0]
    h = bbox[3] - bbox[1]

    x = (VIDEO_WIDTH - w) // 2
    y = (VIDEO_HEIGHT - h) // 2

    bg = Image.new("RGBA", img.size, (0, 0, 0, 0))
    bg_draw = ImageDraw.Draw(bg)
    bg_draw.rectangle(
        [x - 40, y - 30, x + w + 40, y + h + 30],
        fill=(0, 0, 0, int(255 * TEXT_BACKGROUND_OPACITY * alpha))
    )
    bg = bg.filter(ImageFilter.GaussianBlur(BACKGROUND_BLUR_RADIUS))
    img = Image.alpha_composite(img, bg)

    draw = ImageDraw.Draw(img)
    draw.text((x, y), text, font=font, fill=(255, 255, 255, int(255 * alpha)))
    return img.convert("RGB")

def run(cmd):
    subprocess.run(cmd, check=True)

# ================= VIDEO CREATION =================

def create_video(row):

    sentences = [s.strip() for s in row["Voiceover Text"].split(".") if s.strip()]
    tts_files, durations = [], []

    for i, s in enumerate(sentences):
        p = OUTPUT_DIR / f"{uuid.uuid4().hex}_{i}.mp3"
        generate_voice(s, p)
        tts_files.append(p)
        d = float(subprocess.check_output([
            "ffprobe", "-v", "error", "-show_entries",
            "format=duration", "-of",
            "default=nokey=1:noprint_wrappers=1", str(p)
        ]))
        durations.append(d)

    # -------- AUDIO FIX (THUMB SILENCE) --------

    concat_file = OUTPUT_DIR / "tts.txt"
    with open(concat_file, "w") as f:
        for t in tts_files:
            f.write(f"file '{t.resolve()}'\n")

    voice_audio = OUTPUT_DIR / f"{uuid.uuid4().hex}_voice.mp3"
    run(["ffmpeg", "-y", "-f", "concat", "-safe", "0",
         "-i", concat_file, "-c", "copy", voice_audio])

    merged_audio = OUTPUT_DIR / f"{uuid.uuid4().hex}_merged.mp3"
    run([
        "ffmpeg", "-y",
        "-f", "lavfi", "-i",
        f"anullsrc=channel_layout=stereo:sample_rate=44100",
        "-t", str(THUMB_DURATION),
        "-i", voice_audio,
        "-filter_complex", "[0:a][1:a]concat=n=2:v=0:a=1[a]",
        "-map", "[a]", merged_audio
    ])

    # -------- VIDEO --------

    writer = cv2.VideoWriter(
        str(OUTPUT_DIR / "temp.mp4"),
        cv2.VideoWriter_fourcc(*"mp4v"),
        FPS,
        (VIDEO_WIDTH, VIDEO_HEIGHT)
    )

    thumb = resize(Image.open(random.choice(list(THUMB_DIR.glob("*")))))
    for i in range(int(THUMB_DURATION * FPS)):
        writer.write(cv2.cvtColor(np.array(draw_caption(thumb, row["Title"])), cv2.COLOR_RGB2BGR))

    bg = resize(Image.open(random.choice(list(BG_DIR.glob("*")))))
    zoom, px, py = prepare_ken_burns(bg)

    frame_cursor = 0
    for s, d in zip(sentences, durations):
        frames = int(d * FPS)
        for i in range(frames):
            frame = ken_burns_frame(bg, frame_cursor + i, sum(durations)*FPS, zoom, px, py)
            frame = draw_caption(frame, s)
            writer.write(cv2.cvtColor(np.array(frame), cv2.COLOR_RGB2BGR))
        frame_cursor += frames

    writer.release()

    final = OUTPUT_DIR / f"{uuid.uuid4().hex}_final.mp4"
    run(["ffmpeg", "-y", "-i", OUTPUT_DIR / "temp.mp4",
         "-i", merged_audio, "-shortest",
         "-c:v", "libx264", "-c:a", "aac", final])

    return final

# ================= MAIN =================

def main():
    df = pd.read_csv(SCRIPT_CSV, encoding="latin1")
    for _, row in df.iterrows():
        create_video(row)

if __name__ == "__main__":
    main()
