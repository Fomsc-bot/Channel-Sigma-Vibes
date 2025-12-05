#!/usr/bin/env python3
import os
import json
import uuid
from pathlib import Path
from moviepy.editor import TextClip, concatenate_videoclips
import google.generativeai as genai

# ===============================
# CONFIG
# ===============================
OUTPUT_DIR = Path("outputs")
OUTPUT_DIR.mkdir(exist_ok=True)
VIDEO_WIDTH = 1080
VIDEO_HEIGHT = 1920
FPS = 30
SCENE_DURATION = 5  # seconds per scene
MODEL_NAME = "models/gemini-2.5-flash"  # choose from your list_models output

# ===============================
# Configure Gemini
# ===============================
genai.configure(api_key=os.getenv("GEMINI_API_KEY"))

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
    print("[*] Generating script from model...")
    response = genai.generate_text(
        model=MODEL_NAME,
        prompt=PROMPT,
        temperature=0.7
    )
    
    # The generated text is in response.output_text
    text = response.output_text
    try:
        data = json.loads(text)
        scenes = data.get("scenes", [])
        return scenes
    except Exception as e:
        print("[!] Failed to parse JSON from Gemini:")
        print(text)
        raise e

# ===============================
# Compose video
# ===============================
def create_scene_clip(title, subtitle, duration=SCENE_DURATION):
    txt = f"{title}\n{subtitle}"
    clip = TextClip(txt, fontsize=80, color="white",
                    size=(VIDEO_WIDTH, VIDEO_HEIGHT),
                    method="caption", align="center", font="Arial-Bold")
    clip = clip.set_duration(duration)
    return clip

def compose_video(scenes):
    clips = []
    for scene in scenes:
        title = scene.get("title", "")
        subtitle = scene.get("subtitle", "")
        clip = create_scene_clip(title, subtitle)
        clips.append(clip)
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
