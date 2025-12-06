#!/usr/bin/env python3
import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont
from pathlib import Path
import random
import uuid
import time

# ===============================
# CONFIG
# ===============================
OUTPUT_DIR = Path("outputs")
OUTPUT_DIR.mkdir(exist_ok=True)
VIDEO_WIDTH = 1080
VIDEO_HEIGHT = 1920
FPS = 30
SCENE_DURATION = 5  # seconds
QUOTE_FILE = "quotes.txt"  # txt file with one quote per line
FONT_PATH = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
FONT_SIZE = 80
FADE_FRAMES = 15  # frames for fade in/out

# ===============================
# FUNCTIONS
# ===============================

def load_quote():
    """Load a random quote from the txt file and remove it to avoid reuse."""
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
    gradient = np.linspace(50, 200, VIDEO_HEIGHT, dtype=np.uint8)
    gradient_2d = np.tile(gradient[:, np.newaxis], (1, VIDEO_WIDTH))
    img[:, :, 0] = gradient_2d                     # Blue
    img[:, :, 1] = np.flip(gradient_2d, axis=0)   # Green
    img[:, :, 2] = 150                             # Red fixed
    
    # Moving circles
    num_circles = 5
    for i in range(num_circles):
        radius = 50 + (i * 15)
        center_x = int((VIDEO_WIDTH / num_circles) * i + (frame_num * 5) % VIDEO_WIDTH)
        center_y = int((VIDEO_HEIGHT / num_circles) * i + (frame_num * 3) % VIDEO_HEIGHT)
        color = (np.random.randint(100,255), np.random.randint(100,255), np.random.randint(100,255))
        cv2.circle(img, (center_x, center_y), radius, color, -1)
    
    return img

def create_text_frame(text, frame_num, total_frames):
    """Draw text with slide-in effect on background."""
    bg = create_animated_background(frame_num, total_frames)
    img = Image.fromarray(bg)
    draw = ImageDraw.Draw(img)
    font = ImageFont.truetype(FONT_PATH, FONT_SIZE)
    
    # Wrap text
    lines = []
    words = text.split()
    while words:
        line = ""
        while words and draw.textbbox((0,0), line + words[0], font=font)[2] < VIDEO_WIDTH * 0.8:
            line += (words.pop(0) + " ")
        lines.append(line.strip())
    
    # Compute vertical start
    total_height = sum([draw.textbbox((0,0), line, font=font)[3] for line in lines])
    y = (VIDEO_HEIGHT - total_height) // 2
    
    # Slide-in from left effect
    progress = min(1.0, frame_num / FADE_FRAMES)
    x_offset = int((1.0 - progress) * VIDEO_WIDTH // 2)
    
    for line in lines:
        bbox = draw.textbbox((0,0), line, font=font)
        w = bbox[2] - bbox[0]
        h = bbox[3] - bbox[1]
        x = (VIDEO_WIDTH - w) // 2 - x_offset
        draw.text((x, y), line, font=font, fill=(255,255,255))
        y += h
    
    return cv2.cvtColor(np.array(img), cv2.COLOR_RGB2BGR)

def add_fade(frames):
    """Apply fade-in/out effect."""
    total_frames = len(frames)
    faded = []
    for i, frame in enumerate(frames):
        overlay = np.zeros_like(frame)
        # fade-in
        alpha_in = min(1.0, (i+1)/FADE_FRAMES)
        # fade-out
        alpha_out = min(1.0, (total_frames-i)/FADE_FRAMES)
        alpha = min(alpha_in, alpha_out)
        blended = cv2.addWeighted(frame, alpha, overlay, 1-alpha, 0)
        faded.append(blended)
    return faded

def create_video():
    """Create a single-quote video with animated background and dynamic text."""
    quote = load_quote()
    total_frames = SCENE_DURATION * FPS
    frames = []
    for i in range(total_frames):
        frame = create_text_frame(quote, i, total_frames)
        frames.append(frame)
    
    frames = add_fade(frames)
    
    filename = OUTPUT_DIR / f"sigma_short_{uuid.uuid4().hex[:8]}.mp4"
    fourcc = cv2.VideoWriter_fourcc(*"mp4v")
    out = cv2.VideoWriter(str(filename), fourcc, FPS, (VIDEO_WIDTH, VIDEO_HEIGHT))
    
    for frame in frames:
        out.write(frame)
    out.release()
    
    print(f"[+] Video saved to {filename}")
    print(f"[+] Quote used: {quote}")

# ===============================
# MAIN
# ===============================
if __name__ == "__main__":
    create_video()
