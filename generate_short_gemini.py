#!/usr/bin/env python3
import os
import json
import uuid
from pathlib import Path
from moviepy.editor import TextClip, concatenate_videoclips
from transformers import AutoModelForCausalLM, AutoTokenizer, pipeline

# ===============================
# CONFIG
# ===============================
OUTPUT_DIR = Path("outputs")
OUTPUT_DIR.mkdir(exist_ok=True)
VIDEO_WIDTH = 1080
VIDEO_HEIGHT = 1920
FPS = 30
SCENE_DURATION = 5  # seconds per scene
MODEL_NAME = "TheBloke/wizardLM-7B-HF"  # free HF model (CPU compatible)

# ===============================
# Load Hugging Face model
# ===============================
print("[*] Loading local model...")
tokenizer = AutoTokenizer.from_pretrained(MODEL_NAME)
model = AutoModelForCausalLM.from_pretrained(MODEL_NAME)

generator = pipeline(
    "text-generation",
    model=model,
    tokenizer=tokenizer,
    device=-1  # CPU
)

# ===============================
# Generate script/scenes
# ===============================
PROMPT = """
Generate 3 motivational Sigma mindset rules for a YouTube Short.
Output JSON like this:
{
  "scenes": [
    {"title": "Scene 1 title", "subtitle": "Scene 1 subtitle"},
    {"title": "Scene 2 title", "subtitle": "Scene 2 subtitle"},
    {"title": "Scene 3 title", "subtitle": "Scene 3 subtitle"}
  ]
}
"""

def generate_script():
    print("[*] Generating script...")
    try:
        output = generator(PROMPT, max_new_tokens=256, do_sample=True, temperature=0.7)
        text = output[0]["generated_text"]
        data = json.loads(text)
        scenes = data.get("scenes", [])
        return scenes
    except Exception as e:
        print("[!] Failed to generate or parse JSON:")
        print(text if 'text' in locals() else "")
        raise e

# ===============================
# Compose video
# ===============================
def create_scene_clip(title, subtitle, duration=SCENE_DURATION):
    txt = f"{title}\n{subtitle}"
    clip = TextClip(
        txt,
        fontsize=80,
        color="white",
        size=(VIDEO_WIDTH, VIDEO_HEIGHT),
        method="caption",  # Pillow-based text rendering
        align="center",
        font="DejaVu-Sans"  # preinstalled on Linux runners
    )
    clip = clip.set_duration(duration)
    return clip

def compose_video(scenes):
    clips = [create_scene_clip(s["title"], s["subtitle"]) for s in scenes]
    final_video = concatenate_videoclips(clips)
    return final_video

# ===============================
# Main
# ===============================
def main():
    scenes = generate_script()
    if not scenes:
        print("[!] No scenes generated.")
        return

    print(f"[*] Composing video with {len(scenes)} scenes...")
    video = compose_video(scenes)
    filename = OUTPUT_DIR / f"sigma_short_{uuid.uuid4().hex[:8]}.mp4"
    video.write_videofile(str(filename), fps=FPS)
    print(f"[+] Video saved to {filename}")

if __name__ == "__main__":
    main()
