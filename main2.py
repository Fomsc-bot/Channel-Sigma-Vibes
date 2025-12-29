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
    img = Image.open(img_path)
    text = pytesseract.image_to_string(img, lang="eng")
    text = " ".join(text.split())
    return text if text else "Double Meaning Quote"

def generate_voice(text, out_path):
    text = text.replace("’", "'").replace("‘", "'")
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

def draw_caption(img, text, alpha=1.0):
    """Draw caption in middle with optional fade effect."""
    draw = ImageDraw.Draw(img)
    font = ImageFont.truetype(FONT_PATH, FONT_SIZE)
    lines = text.split(". ")
    total_h = sum(font.getbbox(l)[3] for l in lines) + 10 * len(lines)
    y = (VIDEO_HEIGHT - total_h) // 2
    for l in lines:
        l = l.strip()
        if not l:
            continue
        w = draw.textlength(l, font)
        x = (VIDEO_WIDTH - w) // 2
        draw.text((x+3, y+3), l, font=font, fill=(0,0,0,int(255*alpha)))  # shadow
        draw.text((x, y), l, font=font, fill=(255,255,255,int(255*alpha)))  # main text
        y += font.getbbox(l)[3] + 10

# ================= VIDEO CREATION =================

def create_video(row):
    # --- Thumbnail selection ---
    thumb_file = None
    thumbnails = list(THUMB_DIR.glob("*"))
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

    # --- Split sentences and generate TTS ---
    full_text = row['Voiceover Text']
    sentences = [s.strip() for s in full_text.replace("?", ".").replace("!", ".").split(".") if s.strip()]
    tts_files = []
    sentence_durations = []
    for i, s in enumerate(sentences):
        tts_path = OUTPUT_DIR / f"{uuid.uuid4().hex}_tts_{i}.mp3"
        generate_voice(s, tts_path)
        # get duration
        try:
            dur = float(subprocess.check_output([
                "ffprobe","-v","error","-show_entries",
                "format=duration","-of",
                "default=noprint_wrappers=1:nokey=1", str(tts_path)
            ]).decode().strip())
        except:
            dur = max(len(s.split())/2, 1)
        tts_files.append(tts_path)
        sentence_durations.append(dur)

    # --- Merge TTS audio for final video ---
    merged_audio = OUTPUT_DIR / f"{uuid.uuid4().hex}_merged.mp3"
    with open(OUTPUT_DIR / "tts_list.txt", "w") as f:
        for t in tts_files:
            f.write(f"file '{t.resolve()}'\n")
    subprocess.run([
        "ffmpeg","-y","-f","concat","-safe","0",
        "-i", str(OUTPUT_DIR / "tts_list.txt"),
        "-c","copy", str(merged_audio)
    ], check=True)

    total_duration = sum(sentence_durations)
    total_frames = int(total_duration * FPS)
    writer_path = OUTPUT_DIR / f"{uuid.uuid4().hex}_temp.mp4"
    writer = cv2.VideoWriter(str(writer_path), cv2.VideoWriter_fourcc(*"mp4v"), FPS, (VIDEO_WIDTH, VIDEO_HEIGHT))

    # --- Thumbnail ---
    thumb_img = resize(Image.open(thumb_file))
    for _ in range(THUMB_DURATION * FPS):
        writer.write(cv2.cvtColor(np.array(thumb_img), cv2.COLOR_RGB2BGR))

    # --- Main Scene ---
    bg_img = resize(Image.open(bg_file))
    zoom_end, pan_x, pan_y = prepare_ken_burns(bg_img)

    # Track sentence timing
    frame_cursor = 0
    for s, dur in zip(sentences, sentence_durations):
        frames = int(dur * FPS)
        for i in range(frames):
            frame = ken_burns_frame(bg_img, frame_cursor + i, total_frames, zoom_end, pan_x, pan_y)
            # optional fade
            alpha = 1.0
            draw_caption(frame, s, alpha)
            writer.write(cv2.cvtColor(np.array(frame), cv2.COLOR_RGB2BGR))
        frame_cursor += frames

    # --- Outro ---
    outtro_img = resize(Image.open(outtro_file))
    outro_frames = OUTTRO_DURATION * FPS
    zoom_end_out, pan_x_out, pan_y_out = prepare_ken_burns(outtro_img)
    for i in range(outro_frames):
        frame = ken_burns_frame(outtro_img, i, outro_frames, zoom_end_out, pan_x_out, pan_y_out)
        writer.write(cv2.cvtColor(np.array(frame), cv2.COLOR_RGB2BGR))

    writer.release()

    # --- Merge video with merged audio ---
    final_path = OUTPUT_DIR / f"{uuid.uuid4().hex}_final.mp4"
    subprocess.run([
        "ffmpeg","-y",
        "-i", str(writer_path),
        "-i", str(merged_audio),
        "-c:v","copy",
        "-c:a","aac",
        str(final_path)
    ], check=True)

    # --- Cleanup ---
    writer_path.unlink()
    merged_audio.unlink()
    (OUTPUT_DIR / "tts_list.txt").unlink()
    for t in tts_files:
        t.unlink()
    thumb_file.unlink()

    return final_path

# ================= UPLOAD =================

def upload(video_file, row):
    creds = Credentials(None, refresh_token=REFRESH_TOKEN, token_uri="https://oauth2.googleapis.com/token",
                        client_id=CLIENT_ID, client_secret=CLIENT_SECRET,
                        scopes=["https://www.googleapis.com/auth/youtube.upload"])
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
