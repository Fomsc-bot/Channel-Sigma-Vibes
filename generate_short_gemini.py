#!/usr/bin/env python3
import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont
from pathlib import Path
import random
import uuid

# ===============================
# CONFIG
# ===============================
OUTPUT_DIR = Path("outputs")
OUTPUT_DIR.mkdir(exist_ok=True)

BACKGROUND_DIR = Path("Background_images")
MERGE_VIDEO_DIR = Path("out")

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
# UTILITIES
# ===============================

def ease_in_out(t):
    return 0.5 - 0.5 * np.cos(np.pi * t)

# ===============================
# QUOTE
# ===============================

def load_quote():
    with open(QUOTE_FILE, "r", encoding="utf-8") as f:
        quotes = [q.strip() for q in f if q.strip()]

    if not quotes:
        raise ValueError("No quotes left")

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
    images = list(BACKGROUND_DIR.glob("*.*"))
    if not images:
        raise FileNotFoundError("No images in Background_images")

    img = Image.open(random.choice(images)).convert("RGB")

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
# FADE
# ===============================

def apply_fade(frame, idx, total):
    alpha = min((idx+1)/FADE_FRAMES, (total-idx)/FADE_FRAMES, 1)
    return cv2.addWeighted(frame, alpha, np.zeros_like(frame), 1-alpha, 0)

# ===============================
# LOAD MERGE VIDEO
# ===============================

def load_merge_video_frames():
    videos = list(MERGE_VIDEO_DIR.glob("*.mp4"))
    if not videos:
        raise FileNotFoundError("No videos in out/ folder")

    cap = cv2.VideoCapture(str(random.choice(videos)))
    frames = []

    while True:
        ret, frame = cap.read()
        if not ret:
            break
        frame = cv2.resize(frame, (VIDEO_WIDTH, VIDEO_HEIGHT))
        frames.append(frame)

    cap.release()
    return frames

# ===============================
# CREATE FINAL VIDEO
# ===============================

def create_video():
    quote = load_quote()
    bg = load_background_image()
    zoom_end, pan_x, pan_y = prepare_ken_burns()

    quote_frames = SCENE_DURATION * FPS
    merge_frames = load_merge_video_frames()

    output = OUTPUT_DIR / f"sigma_short_{uuid.uuid4().hex[:8]}.mp4"
    writer = cv2.VideoWriter(
        str(output),
        cv2.VideoWriter_fourcc(*"mp4v"),
        FPS,
        (VIDEO_WIDTH, VIDEO_HEIGHT)
    )

    # --- QUOTE VIDEO ---
    for i in range(quote_frames):
        img = ken_burns_frame(bg, i, quote_frames, zoom_end, pan_x, pan_y)
        draw_typewriter_text(img, quote, i)

        frame = cv2.cvtColor(np.array(img), cv2.COLOR_RGB2BGR)
        frame = apply_fade(frame, i, quote_frames)
        writer.write(frame)

    # --- MERGED VIDEO ---
    for frame in merge_frames:
        writer.write(frame)

    writer.release()
    print("✅ Final merged video created:", output)

# ===============================
# RUN
# ===============================

if __name__ == "__main__":
    create_video()
