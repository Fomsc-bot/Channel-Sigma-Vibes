#!/usr/bin/env python3
import os
import uuid
from pathlib import Path
from random import choice
from moviepy.editor import TextClip, CompositeVideoClip, ColorClip, concatenate_videoclips

# ===============================
# CONFIG
# ===============================
OUTPUT_DIR = Path("outputs")
OUTPUT_DIR.mkdir(exist_ok=True)
QUOTES_FILE = Path("quotes.txt")   # Must exist
VIDEO_WIDTH = 1080
VIDEO_HEIGHT = 1920
FPS = 30
SCENE_DURATION = 5  # seconds per quote
FADE_DURATION = 0.5  # seconds for fade in/out

# ===============================
# FUNCTIONS
# ===============================
def get_random_quote():
    """Pick a random quote from quotes.txt and remove it from file."""
    if not QUOTES_FILE.exists():
        print("[!] Quotes file not found.")
        return None
    with open(QUOTES_FILE, "r", encoding="utf-8") as f:
        quotes = [q.strip() for q in f if q.strip()]
    if not quotes:
        print("[!] No more quotes left.")
        return None
    quote = choice(quotes)
    # Remove used quote
    quotes.remove(quote)
    with open(QUOTES_FILE, "w", encoding="utf-8") as f:
        f.write("\n".join(quotes))
    return quote

def create_scene_clip(quote):
    """Create a single scene with text on a gradient background and fade-in/out."""
    # Gradient background (dark at top -> lighter at bottom)
    bg = ColorClip(size=(VIDEO_WIDTH, VIDEO_HEIGHT), color=(30, 30, 30), duration=SCENE_DURATION)

    # Create text clip
    txt_clip = TextClip(
        txt=quote,
        fontsize=70,
        color="white",
        font="Arial-Bold",
        method="caption",
        size=(VIDEO_WIDTH - 100, VIDEO_HEIGHT - 200),
        align="center"
    ).set_duration(SCENE_DURATION)

    # Add fade-in/out
    txt_clip = txt_clip.fadein(FADE_DURATION).fadeout(FADE_DURATION)
    scene = CompositeVideoClip([bg, txt_clip.set_position("center")])
    return scene

def create_video(num_scenes=3):
    """Generate the final video from quotes."""
    scenes = []
    for _ in range(num_scenes):
        quote = get_random_quote()
        if not quote:
            break
        clip = create_scene_clip(quote)
        scenes.append(clip)
    if not scenes:
        print("[!] No scenes generated.")
        return

    final_video = concatenate_videoclips(scenes)
    filename = OUTPUT_DIR / f"sigma_short_{uuid.uuid4().hex[:8]}.mp4"
    final_video.write_videofile(str(filename), fps=FPS)
    print(f"[+] Video saved to {filename}")

# ===============================
# MAIN
# ===============================
if __name__ == "__main__":
    create_video(num_scenes=3)  # Change the number of quotes/scenes per short if needed
