#!/usr/bin/env python3
import os
import uuid
import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont
from pathlib import Path
from random import choice

# ===============================
# CONFIG
# ===============================
OUTPUT_DIR = Path("outputs")
OUTPUT_DIR.mkdir(exist_ok=True)
QUOTES_FILE = Path("quotes.txt")
VIDEO_WIDTH = 1080
VIDEO_HEIGHT = 1920
FPS = 30
SCENE_DURATION = 5  # seconds per quote
FADE_DURATION = 1.0  # seconds for fade in/out
FONT_PATH = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"  # default Linux font

# ===============================
# FUNCTIONS
# ===============================
def get_random_quote():
    if not QUOTES_FILE.exists():
        print("[!] Quotes file not found.")
        return None
    with open(QUOTES_FILE, "r", encoding="utf-8") as f:
        quotes = [q.strip() for q in f if q.strip()]
    if not quotes:
        print("[!] No more quotes left.")
        return None
    quote = choice(quotes)
    quotes.remove(quote)
    with open(QUOTES_FILE, "w", encoding="utf-8") as f:
        f.write("\n".join(quotes))
    return quote

def create_frame(text):
    """Create a single PIL image with centered text and gradient background."""
    img = Image.new("RGB", (VIDEO_WIDTH, VIDEO_HEIGHT))
    draw = ImageDraw.Draw(img)

    # Gradient background
    for y in range(VIDEO_HEIGHT):
        r = int(20 + (y / VIDEO_HEIGHT) * 40)
        g = int(20 + (y / VIDEO_HEIGHT) * 40)
        b = int(20 + (y / VIDEO_HEIGHT) * 40)
        draw.line([(0, y), (VIDEO_WIDTH, y)], fill=(r, g, b))

    # Load font
    font_size = 80
    font = ImageFont.truetype(FONT_PATH, font_size)

    # Wrap text
    lines = []
    words = text.split()
    line = ""
    for word in words:
        test_line = f"{line} {word}".strip()
        w, h = draw.textsize(test_line, font=font)
        if w > VIDEO_WIDTH - 100:
            lines.append(line)
            line = word
        else:
            line = test_line
    lines.append(line)

    # Draw text
    total_h = len(lines) * font_size + (len(lines)-1)*10
    y_text = (VIDEO_HEIGHT - total_h) // 2
    for line in lines:
        w, h = draw.textsize(line, font=font)
        x_text = (VIDEO_WIDTH - w) // 2
        draw.text((x_text, y_text), line, font=font, fill=(255, 255, 255))
        y_text += font_size + 10

    return np.array(img)

def create_video(num_scenes=3):
    scenes = []
    for _ in range(num_scenes):
        quote = get_random_quote()
        if not quote:
            break
        scenes.append(quote)

    if not scenes:
        print("[!] No quotes to generate video.")
        return

    filename = OUTPUT_DIR / f"sigma_short_{uuid.uuid4().hex[:8]}.mp4"
    fourcc = cv2.VideoWriter_fourcc(*"mp4v")
    out = cv2.VideoWriter(str(filename), fourcc, FPS, (VIDEO_WIDTH, VIDEO_HEIGHT))

    for quote in scenes:
        frame = create_frame(quote)
        fade_frames = int(FADE_DURATION * FPS)
        scene_frames = int(SCENE_DURATION * FPS)

        # Fade-in
        for i in range(fade_frames):
            alpha = i / fade_frames
            out_frame = (frame * alpha).astype(np.uint8)
            out.write(out_frame)

        # Full scene
        for _ in range(scene_frames - 2*fade_frames):
            out.write(frame)

        # Fade-out
        for i in range(fade_frames):
            alpha = 1 - (i / fade_frames)
            out_frame = (frame * alpha).astype(np.uint8)
            out.write(out_frame)

    out.release()
    print(f"[+] Video saved to {filename}")

# ===============================
# MAIN
# ===============================
if __name__ == "__main__":
    create_video(num_scenes=3)
