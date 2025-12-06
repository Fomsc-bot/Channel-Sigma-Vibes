#!/usr/bin/env python3
import os
import json
import uuid
import requests
from pathlib import Path
from moviepy.editor import TextClip, concatenate_videoclips

# =============================
# CONFIG
# =============================
OUTPUT_DIR = Path("outputs")
OUTPUT_DIR.mkdir(exist_ok=True)

VIDEO_WIDTH = 1080
VIDEO_HEIGHT = 1920
FPS = 30
SCENE_DURATION = 5

HF_MODEL = "Qwen/Qwen2.5-0.5B-Instruct"
HF_API_URL = "https://router.huggingface.co/text-generation"  # NEW API

HF_TOKEN = os.getenv("HF_TOKEN")  # optional
HEADERS = {"Authorization": f"Bearer {HF_TOKEN}"} if HF_TOKEN else {}

PROMPT = """
Generate exactly 3 motivational Sigma mindset rules for a YouTube Short.
Return only valid JSON in this structure:

{
  "scenes": [
    {"title": "Scene 1 title", "subtitle": "Scene 1 subtitle"},
    {"title": "Scene 2 title", "subtitle": "Scene 2 subtitle"},
    {"title": "Scene 3 title", "subtitle": "Scene 3 subtitle"}
  ]
}
"""

# =============================
# Hugging Face API
# =============================
def generate_text():
    print("[*] Contacting HF Router API...")

    payload = {
        "model": HF_MODEL,
        "inputs": PROMPT,
        "parameters": {
            "max_new_tokens": 200,
            "temperature": 0.7
        }
    }

    response = requests.post(HF_API_URL, headers=HEADERS, json=payload)

    if response.status_code != 200:
        print("[!] HF API Error:", response.text)
        return ""

    try:
        return response.json()["generated_text"]
    except Exception:
        print("[!] Unexpected format from HF:", response.text)
        return ""

# =============================
# Parse JSON scenes
# =============================
def generate_script():
    text = generate_text()
    if not text:
        return []

    try:
        data = json.loads(text)
        return data.get("scenes", [])
    except:
        print("[!] Could not parse returned text as JSON:")
        print(text)
        return []

# =============================
# Video builder
# =============================
def create_scene_clip(title, subtitle, duration=SCENE_DURATION):
    txt = f"{title}\n{subtitle}"
    return (
        TextClip(
            txt,
            fontsize=80,
            color="white",
            size=(VIDEO_WIDTH, VIDEO_HEIGHT),
            method="caption",
            align="center",
            font="Arial-Bold"
        ).set_duration(duration)
    )

def compose_video(scenes):
    clips = [create_scene_clip(s["title"], s["subtitle"]) for s in scenes]
    return concatenate_videoclips(clips)

# =============================
# Main
# =============================
def main():
    scenes = generate_script()

    if not scenes:
        print("[!] No scenes generated.")
        return

    print(f"[*] Creating video with {len(scenes)} scenes...")

    video = compose_video(scenes)
    file = OUTPUT_DIR / f"sigma_short_{uuid.uuid4().hex[:8]}.mp4"

    video.write_videofile(str(file), fps=FPS)
    print("[+] Saved:", file)


if __name__ == "__main__":
    main()
