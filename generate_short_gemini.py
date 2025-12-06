#!/usr/bin/env python3
import os
import uuid
from pathlib import Path
from random import choice
from moviepy.video.VideoClip import TextClip
from moviepy.video.compositing.concatenate import concatenate_videoclips
from moviepy.video.fx.all import fadein, fadeout

# ===============================
# CONFIG
# ===============================
OUTPUT_DIR = Path("outputs")
OUTPUT_DIR.mkdir(exist_ok=True)
VIDEO_WIDTH = 1080
VIDEO_HEIGHT = 1920
FPS = 30
SCENE_DURATION = 5  # seconds per quote
FADE_DURATION = 1   # seconds
QUOTES_FILE = Path("quotes.txt")  # file containing one quote per line
MAX_QUOTES = 10  # max number of quotes per video

# ===============================
# Load quotes
# ===============================
def load_quotes():
    if not QUOTES_FILE.exists():
        print(f"[!] Quotes file {QUOTES_FILE} not found.")
        return []
    with open(QUOTES_FILE, "r", encoding="utf-8") as f:
        quotes = [line.strip() for line in f if line.strip()]
    return quotes

# ===============================
# Save remaining quotes
# ===============================
def save_remaining_quotes(quotes):
    with open(QUOTES_FILE, "w", encoding="utf-8") as f:
        f.write("\n".join(quotes))

# ===============================
# Create video clip for a quote
# ===============================
def create_scene_clip(quote):
    clip = TextClip(
        quote,
        fontsize=80,
        color="white",
        size=(VIDEO_WIDTH, VIDEO_HEIGHT),
        method="caption",
        align="center",
        font="Arial-Bold"
    ).set_duration(SCENE_DURATION)

    # Apply fade in/out
    clip = fadein(clip, FADE_DURATION).fadeout(FADE_DURATION)
    return clip

# ===============================
# Compose full video
# ===============================
def compose_video(selected_quotes):
    clips = [create_scene_clip(q) for q in selected_quotes]
    final_video = concatenate_videoclips(clips, method="compose")
    return final_video

# ===============================
# Main
# ===============================
def main():
    quotes = load_quotes()
    if not quotes:
        print("[!] No quotes available.")
        return

    num_quotes = min(MAX_QUOTES, len(quotes))
    selected_quotes = []
    for _ in range(num_quotes):
        q = choice(quotes)
        selected_quotes.append(q)
        quotes.remove(q)  # remove used quote

    save_remaining_quotes(quotes)  # save remaining quotes

    print(f"[*] Creating video with {len(selected_quotes)} quotes...")
    video = compose_video(selected_quotes)
    filename = OUTPUT_DIR / f"sigma_short_{uuid.uuid4().hex[:8]}.mp4"
    video.write_videofile(str(filename), fps=FPS)
    print(f"[+] Video saved to {filename}")

if __name__ == "__main__":
    main()
