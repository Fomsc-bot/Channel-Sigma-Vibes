#!/usr/bin/env python3
import os
import json
import uuid
from pathlib import Path
from moviepy.editor import TextClip, concatenate_videoclips

# Hugging Face imports
from transformers import AutoModelForCausalLM, AutoTokenizer, pipeline
import torch

# =============================
# CONFIG
# =============================
OUTPUT_DIR = Path("outputs")
OUTPUT_DIR.mkdir(exist_ok=True)

VIDEO_WIDTH = 1080
VIDEO_HEIGHT = 1920
FPS = 30
SCENE_DURATION = 5

# Small free model for CPU
MODEL_NAME = "gpt2"  # tiny, fully free
DEVICE = "cpu"       # use "cuda" if GPU is available

PROMPT = """
Generate 3 motivational Sigma mindset rules for a YouTube Short.
Output JSON exactly like this:
{
  "scenes": [
    {"title": "Scene 1 title", "subtitle": "Scene 1 subtitle"},
    {"title": "Scene 2 title", "subtitle": "Scene 2 subtitle"},
    {"title": "Scene 3 title", "subtitle": "Scene 3 subtitle"}
  ]
}
"""

# =============================
# Generate text with local model
# =============================
def generate_script():
    print("[*] Loading local model...")
    tokenizer = AutoTokenizer.from_pretrained(MODEL_NAME)
    model = AutoModelForCausalLM.from_pretrained(MODEL_NAME)
    model.to(DEVICE)

    generator = pipeline(
        "text-generation",
        model=model,
        tokenizer=tokenizer,
        device=-1 if DEVICE == "cpu" else 0
    )

    print("[*] Generating script...")
    output = generator(PROMPT, max_length=250, do_sample=True, temperature=0.7)
    text = output[0]["generated_text"]

    # Try to extract JSON
    try:
        start = text.find("{")
        end = text.rfind("}") + 1
        json_text = text[start:end]
        data = json.loads(json_text)
        return data.get("scenes", [])
    except Exception:
        print("[!] Failed to parse JSON from model output:")
        print(text)
        return []

# =============================
# Video
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

    print(f"[*] Composing video with {len(scenes)} scenes...")
    video = compose_video(scenes)

    filepath = OUTPUT_DIR / f"sigma_short_{uuid.uuid4().hex[:8]}.mp4"
    video.write_videofile(str(filepath), fps=FPS)
    print("[+] Saved video:", filepath)

if __name__ == "__main__":
    main()
