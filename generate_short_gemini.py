#!/usr/bin/env python3
import os
import json
from datetime import datetime
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont
from moviepy.editor import ImageClip, concatenate_videoclips

import google.generativeai as genai

# ---------------------------------------------------------
# CONFIG
# ---------------------------------------------------------
WIDTH = 1080
HEIGHT = 1920
BG_COLOR = (0, 0, 0)
TEXT_COLOR = (255, 255, 255)

BODY_FONT_SIZE = 70

OUT_DIR = Path("outputs")
OUT_DIR.mkdir(exist_ok=True)

PROMPT = """
Generate a YouTube Shorts script with 4 scenes:
- Each scene must include: { "text": "text on screen", "duration": <seconds> }
- Tone: Sigma mindset, short & punchy
- Total duration: 15–30 seconds
- Return strictly valid JSON
"""

# ---------------------------------------------------------
# Gemini 2.0 Flash client
# ---------------------------------------------------------
def get_gemini_client():
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        raise RuntimeError("Missing GEMINI_API_KEY in environment variables.")
    genai.configure(api_key=api_key)
    return "gemini-2.0-flash"

# ---------------------------------------------------------
# Generate script from Gemini
# ---------------------------------------------------------
def generate_script():
    model_name = get_gemini_client()
    response = genai.generate_text(
        model=model_name,
        prompt=PROMPT,
        temperature=0.7,
        max_output_tokens=500
    )

    raw_text = response.result[0].content[0].text.strip()

    # Clean code fences if any
    if raw_text.startswith("```json"):
        raw_text = raw_text[7:]
    if raw_text.endswith("```"):
        raw_text = raw_text[:-3]

    data = json.loads(raw_text)
    return data["scenes"]

# ---------------------------------------------------------
# Make PIL image frame for text
# ---------------------------------------------------------
def make_image_frame(text: str):
    img = Image.new("RGB", (WIDTH, HEIGHT), BG_COLOR)
    draw = ImageDraw.Draw(img)

    try:
        font = ImageFont.truetype("DejaVuSans-Bold.ttf", BODY_FONT_SIZE)
    except:
        font = ImageFont.load_default()

    lines = [line.strip() for line in text.split("\n") if line.strip()]

    total_height = 0
    line_sizes = []
    for line in lines:
        bbox = draw.textbbox((0, 0), line, font=font)
        w, h = bbox[2], bbox[3]
        line_sizes.append((w, h))
        total_height += h + 10

    y = (HEIGHT - total_height) // 2
    for i, line in enumerate(lines):
        w, h = line_sizes[i]
        x = (WIDTH - w) // 2
        draw.text((x, y), line, fill=TEXT_COLOR, font=font)
        y += h + 10

    return img

# ---------------------------------------------------------
# Compose video from scenes
# ---------------------------------------------------------
def compose_video(scenes, output_path: Path):
    clips = []

    for idx, scene in enumerate(scenes):
        text = scene["text"]
        dur = float(scene["duration"])

        frame = make_image_frame(text)
        tmp_frame_path = OUT_DIR / f"frame_{idx}.png"
        frame.save(tmp_frame_path)

        clip = ImageClip(str(tmp_frame_path)).set_duration(dur)
        clips.append(clip)

    final_video = concatenate_videoclips(clips, method="compose")
    final_video.write_videofile(
        str(output_path),
        fps=30,
        codec="libx264",
        audio=False,
        threads=4
    )
    print(f"[+] Video saved to {output_path}")

# ---------------------------------------------------------
# MAIN
# ---------------------------------------------------------
def main():
    print("[*] Generating script from Gemini 2.0 Flash...")
    scenes = generate_script()
    print(f"[+] Received {len(scenes)} scenes.")

    timestamp = datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")
    out_file = OUT_DIR / f"sigma_short_{timestamp}.mp4"

    print("[*] Composing video...")
    compose_video(scenes, out_file)
    print("[✔] Done!")

if __name__ == "__main__":
    main()
