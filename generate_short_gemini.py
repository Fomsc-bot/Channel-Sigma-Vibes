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
SCENE_DURATION = 5  # seconds per scene
QUOTE_FILE = "quotes.txt"  # txt file with one quote per line
FONT_PATH = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
FONT_SIZE = 80
FADE_FRAMES = 15  # number of frames for fade in/out

# ===============================
# Functions
# ===============================
def load_quote():
    """Load a random quote from the txt file and remove it."""
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

def create_frame(text):
    """Create a single frame with fade-in effect."""
    # Create blank image
    img = Image.new("RGB", (VIDEO_WIDTH, VIDEO_HEIGHT), color=(0, 0, 0))
    draw = ImageDraw.Draw(img)
    font = ImageFont.truetype(FONT_PATH, FONT_SIZE)
    
    # Wrap text manually
    lines = []
    words = text.split()
    while words:
        line = ""
        while words and draw.textbbox((0,0), line + words[0], font=font)[2] < VIDEO_WIDTH * 0.9:
            line += (words.pop(0) + " ")
        lines.append(line.strip())
    
    # Draw multiline text centered
    total_height = sum([draw.textbbox((0,0), line, font=font)[3] for line in lines])
    y = (VIDEO_HEIGHT - total_height) // 2
    for line in lines:
        bbox = draw.textbbox((0,0), line, font=font)
        w = bbox[2] - bbox[0]
        h = bbox[3] - bbox[1]
        x = (VIDEO_WIDTH - w) // 2
        draw.text((x, y), line, font=font, fill=(255, 255, 255))
        y += h

    return cv2.cvtColor(np.array(img), cv2.COLOR_RGB2BGR)

def add_fade(frames, fade_frames=FADE_FRAMES):
    """Apply fade in effect to frames."""
    faded = []
    for i in range(len(frames)):
        frame = frames[i].copy()
        alpha = min(1.0, (i + 1) / fade_frames)
        overlay = np.zeros_like(frame)
        cv2.addWeighted(frame, alpha, overlay, 1 - alpha, 0, frame)
        faded.append(frame)
    return faded

def create_video(num_scenes=3):
    """Generate video with quotes."""
    frames = []
    for _ in range(num_scenes):
        quote = load_quote()
        frame = create_frame(quote)
        # Repeat frame for duration
        for _ in range(FPS * SCENE_DURATION):
            frames.append(frame.copy())
    
    frames = add_fade(frames)
    
    filename = OUTPUT_DIR / f"sigma_short_{uuid.uuid4().hex[:8]}.mp4"
    fourcc = cv2.VideoWriter_fourcc(*"mp4v")
    out = cv2.VideoWriter(str(filename), fourcc, FPS, (VIDEO_WIDTH, VIDEO_HEIGHT))
    
    for frame in frames:
        out.write(frame)
    out.release()
    print(f"[+] Video saved to {filename}")

# ===============================
# Main
# ===============================
if __name__ == "__main__":
    create_video(num_scenes=3)
