#!/usr/bin/env python3
import os
import random
import uuid
from pathlib import Path
from moviepy.video.VideoClip import TextClip
from moviepy.video.compositing import concatenate
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
FADE_DURATION = 0.8  # seconds
QUOTES_FILE = "quotes.txt"

# ===============================
# UTILITY FUNCTIONS
# ===============================
def load_quotes(file_path):
    if not os.path.exists(file_path):
        print(f"[!] Quotes file '{file_path}' not found.")
        return []
    with open(file_path, "r", encoding="utf-8") as f:
        quotes = [line.strip() for line in f if line.strip()]
    return quotes

def save_quotes(file_path, quotes):
    with open(file_path, "w", encoding="utf-8") as f:
        f.write("\n".join(quotes))

def pick_random_quote(quotes):
    quote = random.choice(quotes)
    quotes.remove(quote)
    return quote

# ===============================
# VIDEO FUNCTIONS
# ===============================
def create_text_clip(text, duration=SCENE_DURATION):
    clip = TextClip(
        text,
        fontsize=80,
        color="white",
        font="Arial-Bold",
        size=(VIDEO_WIDTH, VIDEO_HEIGHT),
        method="caption",
        align="center"
    ).set_duration(duration)

    clip = fadein(clip, FADE_DURATION)
    clip = fadeout(clip, FADE_DURATION)
    return clip

def create_video(quotes, num_scenes=5):
    if len(quotes) < num_scenes:
        num_scenes = len(quotes)
    
    clips = []
    for _ in range(num_scenes):
        quote = pick_random_quote(quotes)
        clip = create_text_clip(quote)
        clips.append(clip)
    
    final_video = concatenate.concatenate_videoclips(clips)
    filename = OUTPUT_DIR / f"sigma_short_{uuid.uuid4().hex[:8]}.mp4"
    final_video.write_videofile(str(filename), fps=FPS)
    print(f"[+] Video saved to {filename}")
    return filename

# ===============================
# MAIN
# ===============================
def main():
    quotes = load_quotes(QUOTES_FILE)
    if not quotes:
        print("[!] No quotes available to generate video.")
        return

    NUM_SCENES = 5
    print(f"[*] Generating video with {NUM_SCENES} quotes...")
    create_video(quotes, NUM_SCENES)
    save_quotes(QUOTES_FILE, quotes)
    print("[*] Remaining quotes saved.")

if __name__ == "__main__":
    main()
