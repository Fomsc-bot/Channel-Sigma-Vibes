#!/usr/bin/env python3
import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont
from pathlib import Path
import random
import uuid
import time
import os

# ===============================
# CONFIG
# ===============================
OUTPUT_DIR = Path("outputs")
OUTPUT_DIR.mkdir(exist_ok=True)
VIDEO_WIDTH = 1080
VIDEO_HEIGHT = 1920
FPS = 30
VIDEO_DURATION = 10  # seconds per video
QUOTE_FILE = "quotes.txt"  # txt file with one quote per line
FONT_PATH = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
FONT_SIZE = 80
FADE_FRAMES = 20  # fade in/out frames
MUSIC_FILE = "music.mp3"  # Creative Commons background music

# ===============================
# FUNCTIONS
# ===============================

def load_quote():
    """Load a single random quote and remove it from the file."""
    if not Path(QUOTE_FILE).exists():
        raise FileNotFoundError(f"{QUOTE_FILE} not found.")
    
    with open(QUOTE_FILE, "r") as f:
        quotes = [line.strip() for line in f if line.strip()]
    
    if not quotes:
        raise ValueError("No quotes left in the file.")
    
    quote = random.choice(quotes)
    quotes.remove(quote)
    
    with open(QUOTE_FILE, "w") as f:
        for q in quotes:
            f.write(q + "\n")
    
    return quote

def create_animated_background(frame_num, total_frames):
    """Generate animated gradient + moving shapes background."""
    img = np.zeros((VIDEO_HEIGHT, VIDEO_WIDTH, 3), dtype=np.uint8)
    
    # Gradient background
    gradient = np.linspace(50, 200, VIDEO_HEIGHT).astype(np.uint8)
    img[:, :, 0] = gradient  # Blue channel
    img[:, :, 1] = np.flip(gradient)  # Green channel
    img[:, :, 2] = 150  # Fixed Red
    
    # Moving circles animation
    num_circles = 5
    for i in range(num_circles):
        radius = 50 + (i * 20)
        center_x = int((VIDEO_WIDTH / num_circles) * i + (frame_num * 5) % VIDEO_WIDTH)
        center_y = int((VIDEO_HEIGHT / num_circles) * i + (frame_num * 3) % VIDEO_HEIGHT)
        color = (np.random.randint(100,255), np.random.randint(100,255), np.random.randint(100,255))
        cv2.circle(img, (center_x, center_y), radius, color, -1)
    
    return img

def draw_text(frame, text, frame_num, total_frames):
    """Draw text with slide-in / typewriter effect."""
    pil_img = Image.fromarray(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB))
    draw = ImageDraw.Draw(pil_img)
    font = ImageFont.truetype(FONT_PATH, FONT_SIZE)

    # Wrap text
    lines = []
    words = text.split()
    while words:
        line = ""
        while words and draw.textbbox((0,0), line + words[0], font=font)[2] < VIDEO_WIDTH*0.9:
            line += (words.pop(0) + " ")
        lines.append(line.strip())

    total_height = sum([draw.textbbox((0,0), line, font=font)[3] for line in lines])
    y = (VIDEO_HEIGHT - total_height) // 2

    # Typewriter effect: show characters progressively
    char_count = int(len(text) * frame_num / total_frames)
    text_to_show = text[:char_count]

    # Re-wrap text based on typewriter progress
    lines2 = []
    words = text_to_show.split()
    while words:
        line = ""
        while words and draw.textbbox((0,0), line + words[0], font=font)[2] < VIDEO_WIDTH*0.9:
            line += (words.pop(0) + " ")
        lines2.append(line.strip())
    
    # Draw each line
    y = (VIDEO_HEIGHT - sum([draw.textbbox((0,0), l, font=font)[3] for l in lines2])) // 2
    for line in lines2:
        bbox = draw.textbbox((0,0), line, font=font)
        w = bbox[2] - bbox[0]
        h = bbox[3] - bbox[1]
        x = (VIDEO_WIDTH - w) // 2
        draw.text((x, y), line, font=font, fill=(255, 255, 255))
        y += h

    return cv2.cvtColor(np.array(pil_img), cv2.COLOR_RGB2BGR)

def add_fade_in_out(frames, fade_frames=FADE_FRAMES):
    """Apply fade-in and fade-out effect to frames."""
    total = len(frames)
    for i in range(total):
        alpha = 1.0
        if i < fade_frames:
            alpha = i / fade_frames
        elif i > total - fade_frames:
            alpha = (total - i) / fade_frames
        overlay = np.zeros_like(frames[i])
        cv2.addWeighted(frames[i], alpha, overlay, 1-alpha, 0, frames[i])
    return frames

def create_video():
    """Generate a short video with one quote."""
    quote = load_quote()
    total_frames = VIDEO_DURATION * FPS
    frames = []

    for i in range(total_frames):
        bg = create_animated_background(i, total_frames)
        frame = draw_text(bg, quote, i, total_frames)
        frames.append(frame)

    frames = add_fade_in_out(frames)

    filename = OUTPUT_DIR / f"sigma_short_{uuid.uuid4().hex[:8]}.mp4"
    fourcc = cv2.VideoWriter_fourcc(*"mp4v")
    out = cv2.VideoWriter(str(filename), fourcc, FPS, (VIDEO_WIDTH, VIDEO_HEIGHT))

    for frame in frames:
        out.write(frame)
    out.release()
    
    # Optional: Add background music using ffmpeg if MUSIC_FILE exists
    if os.path.exists(MUSIC_FILE):
        temp_file = filename.with_suffix(".tmp.mp4")
        cmd = f'ffmpeg -y -i "{filename}" -i "{MUSIC_FILE}" -c copy -map 0:v:0 -map 1:a:0 -shortest "{temp_file}"'
        os.system(cmd)
        os.rename(temp_file, filename)
    
    print(f"[+] Video saved to {filename}")

# ===============================
# MAIN
# ===============================
if __name__ == "__main__":
    create_video()
