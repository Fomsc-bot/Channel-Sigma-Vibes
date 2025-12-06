#!/usr/bin/env python3
import os
import json
import uuid
from pathlib import Path
from moviepy.editor import TextClip, concatenate_videoclips

from transformers import AutoTokenizer, AutoModelForSeq2SeqLM, pipeline

# ===============================
# CONFIG
# ===============================
OUTPUT_DIR = Path("outputs")
OUTPUT_DIR.mkdir(exist_ok=True)

VIDEO_WIDTH = 1080
VIDEO_HEIGHT = 1920
FPS = 30
SCENE_DURATION = 5

MODEL_NAME = "google/flan-t5-small"   # small + free

PROMPT = """
Generate 3 motivational Sigma mindset rules for a YouTube Short.
Return JSON ONLY like this:
{
  "scenes": [
    {"title": "Scene 1 title", "subtitle": "Scene 1 subtitle"},
    {"title": "Scene 2 title", "subtitle": "Scene 2 subtitle"},
    {"title": "Scene 3 title", "subtitle": "Scene 3 subtitle"}
  ]
}
"""

# ===============================
# Load Model
# ===============================
print("[*] Loading Hugging Face model...")

generator = pipeline(
    "text2text-generation",
    model=MODEL_NAME,
    tokenizer=MODEL_NAME
)

# ===============================
# Generate script
# ===============================

def generate_script():
    print("[*] Generating script...")

    output = generator(
        PROMPT,
        max_length=300
    )[0]["generated_text"]

    try:
        data = json.loads(output)
        return data.get("scenes", [])
    except Exception:
        print("[!] Model returned invalid JSON:")
        print(output)
        return []

# ===============================
# Create video clips
# ===============================
def create_scene_clip(title, subtitle, duration=SCENE_DURATION):
    txt = f"{title}\n{subtitle}"
    clip = TextClip(
        txt,
        fontsize=80,
        color="white",
        size=(VIDEO_WIDTH, VIDEO_HEIGHT),
        method="caption",
        align="center",
        font="Arial-Bold"
    ).set_duration(duration)
    return clip

def compose_video(scenes):
    clips = [create_scene_clip(s["title"], s["subtitle"]) for s in scenes]
    return concatenate_videoclips(clips)

# ===============================
# Main
# ===============================

def main():
    scenes = generate_script()
    if not scenes:
        print("[!] No scenes generated.")
        return

    print(f"[*] Creating video with {len(scenes)} scenes...")

    video = compose_video(scenes)
    filename = OUTPUT_DIR / f"sigma_short_{uuid.uuid4().hex[:8]}.mp4"

    video.write_videofile(str(filename), fps=FPS)
    print(f"[+] Saved to {filename}")

if __name__ == "__main__":
    main()
