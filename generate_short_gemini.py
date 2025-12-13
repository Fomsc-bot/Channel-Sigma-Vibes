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

VIDEO_WIDTH = 1080
VIDEO_HEIGHT = 1920
FPS = 30
SCENE_DURATION = 5  # seconds (1 quote per short)

QUOTE_FILE = "quotes.txt"
FONT_PATH = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
FONT_SIZE = 80

FADE_FRAMES = 15
TYPE_SPEED = 2  # characters per frame (typewriter speed)

# ===============================
# QUOTE HANDLING
# ===============================

def load_quote():
    if not Path(QUOTE_FILE).exists():
        raise FileNotFoundError("quotes.txt not found")

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
# BACKGROUND IMAGE + KEN BURNS
# ===============================

def load_background_image():
    images = list(BACKGROUND_DIR.glob("*.*"))
    if not images:
        raise FileNotFoundError("No images in Background_images")

    img = Image.open(random.choice(images)).convert("RGB")

    # Crop to 9:16
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

def ken_burns_frame(img, frame_idx, total_frames):
    zoom_start = 1.0
    zoom_end = random.uniform(1.1, 1.25)
    zoom = zoom_start + (zoom_end - zoom_start) * (frame_idx / total_frames)

    w, h = img.size
    new_w, new_h = int(w / zoom), int(h / zoom)

    max_x = w - new_w
    max_y = h - new_h

    pan_x = int(max_x * frame_idx / total_frames)
    pan_y = int(max_y * frame_idx / total_frames)

    crop = img.crop((pan_x, pan_y, pan_x + new_w, pan_y + new_h))
    crop = crop.resize((VIDEO_WIDTH, VIDEO_HEIGHT), Image.LANCZOS)

    return crop

# ===============================
# TEXT RENDERING
# ===============================

def wrap_text(draw, text, font, max_width):
    words = text.split()
    lines = []
    while words:
        line = ""
        while words and draw.textbbox((0, 0), line + words[0], font=font)[2] < max_width:
            line += words.pop(0) + " "
        lines.append(line.strip())
    return lines

def draw_typewriter_text(img, text, frame_idx):
    draw = ImageDraw.Draw(img)
    font = ImageFont.truetype(FONT_PATH, FONT_SIZE)

    max_chars = frame_idx * TYPE_SPEED
    visible_text = text[:max_chars]

    lines = wrap_text(draw, visible_text, font, VIDEO_WIDTH * 0.8)

    total_height = sum(draw.textbbox((0,0), l, font=font)[3] for l in lines)
    y = (VIDEO_HEIGHT - total_height) // 2

    for line in lines:
        bbox = draw.textbbox((0,0), line, font=font)
        w = bbox[2] - bbox[0]
        h = bbox[3] - bbox[1]
        x = (VIDEO_WIDTH - w) // 2

        draw.text((x+3, y+3), line, font=font, fill=(0,0,0))
        draw.text((x, y), line, font=font, fill=(255,255,255))
        y += h + 10

# ===============================
# FADE EFFECT
# ===============================

def apply_fade(frame, idx, total):
    alpha_in = min(1.0, (idx+1) / FADE_FRAMES)
    alpha_out = min(1.0, (total-idx) / FADE_FRAMES)
    alpha = min(alpha_in, alpha_out)

    black = np.zeros_like(frame)
    return cv2.addWeighted(frame, alpha, black, 1-alpha, 0)

# ===============================
# VIDEO CREATION
# ===============================

def create_video():
    quote = load_quote()
    bg_image = load_background_image()

    total_frames = SCENE_DURATION * FPS

    output_path = OUTPUT_DIR / f"sigma_short_{uuid.uuid4().hex[:8]}.mp4"
    writer = cv2.VideoWriter(
        str(output_path),
        cv2.VideoWriter_fourcc(*"mp4v"),
        FPS,
        (VIDEO_WIDTH, VIDEO_HEIGHT)
    )

    for i in range(total_frames):
        bg = ken_burns_frame(bg_image, i, total_frames)
        draw_typewriter_text(bg, quote, i)

        frame = cv2.cvtColor(np.array(bg), cv2.COLOR_RGB2BGR)
        frame = apply_fade(frame, i, total_frames)

        writer.write(frame)

    writer.release()
    print("✅ Video created:", output_path)
    print("🧠 Quote used:", quote)

# ===============================
# RUN
# ===============================

if __name__ == "__main__":
    create_video()

