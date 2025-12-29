#!/usr/bin/env python3

import os
import random
import subprocess
import uuid
from pathlib import Path
from io import BytesIO

import requests
from gtts import gTTS
from PIL import Image, ImageDraw, ImageFont
from moviepy.editor import (
    ImageClip, AudioFileClip, CompositeVideoClip, concatenate_audioclips,
    concatenate_videoclips, vfx, VideoFileClip
)
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
import html
import re

# ---------------- CONFIG ----------------
VIDEO_W, VIDEO_H = 1920, 1080
FPS = 30
ZOOM_RATE = 0.015
BASE_FONT_SIZE = 60
CAPTION_HEIGHT = int(VIDEO_H * 0.25)
MAX_CAPTION_CHARS = 250

WORKDIR = Path("work")
WORKDIR.mkdir(exist_ok=True)

OUTTRO_DIR = Path("Outtro")

YT_CLIENT_ID = os.getenv("YT_CLIENT_ID")
YT_CLIENT_SECRET = os.getenv("YT_CLIENT_SECRET")
YT_REFRESH_TOKEN = os.getenv("YT_REFRESH_TOKEN")

# ---------------- UTILITIES ----------------
def sanitize_text(s: str) -> str:
    if not s:
        return ""
    s = html.unescape(s)
    s = re.sub(r"[\x00-\x1f\x7f-\x9f]", "", s)
    s = re.sub(r"\s+", " ", s)
    return s.strip()

def fetch_and_prepare_bg(image_url, fallback_query="entertainment"):
    try:
        if image_url:
            r = requests.get(image_url, timeout=15)
            img = Image.open(BytesIO(r.content)).convert("RGB")
        else:
            unsplash_url = f"https://source.unsplash.com/{VIDEO_W}x{VIDEO_H}/?{fallback_query}"
            r = requests.get(unsplash_url, timeout=15)
            img = Image.open(BytesIO(r.content)).convert("RGB")
        w, h = img.size
        scale = max(VIDEO_W / w, VIDEO_H / h)
        img = img.resize((int(w * scale), int(h * scale)))
        left = (img.size[0] - VIDEO_W) // 2
        top = (img.size[1] - VIDEO_H) // 2
        img = img.crop((left, top, left + VIDEO_W, top + VIDEO_H))
        out = WORKDIR / "bg.jpg"
        img.save(out)
        return str(out)
    except:
        raise RuntimeError("Failed to fetch or prepare background image")

def generate_tts_per_line(lines):
    tts_paths = []
    durations = []
    for i, line in enumerate(lines):
        line = line.replace("’", "'").replace("‘", "'")
        tts_file = WORKDIR / f"tts_{i}.mp3"
        tts = gTTS(text=line, lang="en")
        tts.save(str(tts_file))
        audio = AudioFileClip(str(tts_file))
        durations.append(max(audio.duration, 1))
        audio.close()
        tts_paths.append(str(tts_file))
    return tts_paths, durations

def prepare_ken_burns(img: Image.Image):
    zoom_end = random.uniform(1.05, 1.15)
    pan_x = random.choice([0, 0.5, 1])
    pan_y = random.choice([0, 0.5, 1])
    return zoom_end, pan_x, pan_y

def ken_burns_frame(img: Image.Image, idx: int, total: int, zoom_end, pan_x, pan_y):
    t = 0.5 - 0.5 * (1 - (idx/total) * 2 if idx/total < 0.5 else 1)  # simple ease-in/out
    zoom = 1 + (zoom_end - 1) * t
    w, h = img.size
    cw, ch = int(w / zoom), int(h / zoom)
    x = int((w - cw) * pan_x * t)
    y = int((h - ch) * pan_y * t)
    crop = img.crop((x, y, x + cw, y + ch))
    return crop.resize((VIDEO_W, VIDEO_H), Image.LANCZOS)

def render_center_caption(text, index, max_width=VIDEO_W*0.9, max_height=CAPTION_HEIGHT, base_font_size=BASE_FONT_SIZE):
    text = sanitize_text(text)[:MAX_CAPTION_CHARS]
    try:
        font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", base_font_size)
    except:
        font = ImageFont.load_default()

    tmp_img = Image.new("RGBA", (VIDEO_W, VIDEO_H), (0, 0, 0, 0))
    draw = ImageDraw.Draw(tmp_img)

    # wrap text
    words = text.split()
    lines = []
    while words:
        line = ""
        while words and draw.textlength(line + words[0] + " ", font=font) < max_width:
            line += words.pop(0) + " "
        lines.append(line.strip())

    img = Image.new("RGBA", (VIDEO_W, int(max_height)), (0, 0, 0, 180))
    draw = ImageDraw.Draw(img)
    total_h = sum(font.getbbox(l)[3] for l in lines) + 10 * len(lines)
    y = (max_height - total_h) // 2
    for l in lines:
        w = draw.textlength(l, font)
        x = (VIDEO_W - w) // 2
        draw.text((x, y), l, font=font, fill="white")
        y += font.getbbox(l)[3] + 10
    out = WORKDIR / f"center_cap_{index}.png"
    img.save(out)
    return str(out)

def load_outtro_clip(target_w=VIDEO_W, target_h=VIDEO_H):
    if not OUTTRO_DIR.exists():
        return None
    videos = list(OUTTRO_DIR.glob("*.mp4"))
    if not videos:
        return None
    outro_path = random.choice(videos)
    outro = VideoFileClip(str(outro_path)).resize(newsize=(target_w, target_h))
    return outro

def build_final_video(bg_path, lines, tts_paths, durations, out_file):
    total = sum(durations) + 2
    bg = ImageClip(bg_path).set_duration(total)
    bg = bg.fx(vfx.resize, lambda t: 1 + ZOOM_RATE * t)

    caps = []
    cursor = 0
    for i, (line, dur) in enumerate(zip(lines, durations)):
        cap_img = render_center_caption(line, i)
        cap = ImageClip(cap_img).set_duration(dur).set_start(cursor)
        cap = cap.set_position(("center", "center"))
        caps.append(cap)
        cursor += dur

    audio = concatenate_audioclips([AudioFileClip(p) for p in tts_paths])
    main_video = CompositeVideoClip([bg] + caps, size=(VIDEO_W, VIDEO_H))
    main_video = main_video.set_audio(audio)

    outro_clip = load_outtro_clip()
    if outro_clip:
        final_video = concatenate_videoclips([main_video, outro_clip], method="compose")
    else:
        final_video = main_video

    final_video.write_videofile(str(out_file), fps=FPS, codec="libx264", audio_codec="aac")
    return str(out_file)

def get_youtube_service():
    creds = Credentials(
        token=None,
        refresh_token=YT_REFRESH_TOKEN,
        client_id=YT_CLIENT_ID,
        client_secret=YT_CLIENT_SECRET,
        token_uri="https://oauth2.googleapis.com/token",
        scopes=["https://www.googleapis.com/auth/youtube.upload"]
    )
    creds.refresh(Request())
    return build("youtube", "v3", credentials=creds, cache_discovery=False)

def upload_public(video_file, title, description):
    yt = get_youtube_service()
    body = {
        "snippet": {"title": title, "description": description, "tags": ["news","updates"]},
        "status": {"privacyStatus": "public"}
    }
    media = MediaFileUpload(video_file, resumable=True)
    req = yt.videos().insert(part="snippet,status", body=body, media_body=media)
    resp = None
    while resp is None:
        status, resp = req.next_chunk()
        if status:
            print("Upload:", int(status.progress() * 100), "%")
    return resp["id"]

# ---------------- MAIN ----------------
def main():
    # Example placeholders (replace with your real news/data fetching)
    lines = [
        "Breaking news: Major event happening now.",
        "Stay tuned for the latest updates on this story."
    ]
    image_url = None  # replace with fetched article image url

    bg = fetch_and_prepare_bg(image_url)
    tts_paths, durations = generate_tts_per_line(lines)
    out_video = WORKDIR / "final.mp4"
    build_final_video(bg, lines, tts_paths, durations, out_video)

    upload_public(str(out_video), "Breaking News Update", "Stay informed with latest news.")
    print("✅ Video completed and uploaded.")

if __name__ == "__main__":
    main()
