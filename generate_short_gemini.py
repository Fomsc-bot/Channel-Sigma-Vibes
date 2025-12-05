#!/usr/bin/env python3
import os
import json
from datetime import datetime
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont
from moviepy.editor import ImageClip, concatenate_videoclips

import google.generativeai as genai


# ---------------------------------------------------------
#  CONFIG
# ---------------------------------------------------------
WIDTH = 1080
HEIGHT = 1920
BG_COLOR = (0, 0, 0)
TEXT_COLOR = (255, 255, 255)

TITLE_FONT_SIZE = 90
BODY_FONT_SIZE = 70

OUT_DIR = Path("outputs")
OUT_DIR.mkdir(exist_ok=True)


# ---------------------------------------------------------
#  GEMINI CLIENT
# ---------------------------------------------------------
def get_gemini_client():
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        raise RuntimeError("Missing GEMINI_API_KEY in environment variables.")
    genai.configure(api_key=api_key)
    return genai.GenerativeModel("gemini-1.5-flash")


# ---------------------------------------------------------
#  REQUEST SCRIPT FROM GEMINI
# ---------------------------------------------------------
PROMPT = """
You generate a YouTube short script following this structure:

- 4 scenes
- Each scene must include:
    { "text": "text on screen", "duration": <seconds> }
- Total duration 15–30 seconds
- Tone: Sigma mindset, intense, punchy lines, short powerful quotes.
- Keep each scene VERY short and impactful.
- No narration instructions, no camera directions, text only.

Return strictly valid JSON: { "scenes": [ ... ] }
"""

def generate_script(model):
    response = model.generate_content(PROMPT)
    cleaned = response.text.strip().strip("```json").strip("```")
    data = json.loads(cleaned)
    return data["scenes"]


# ---------------------------------------------------------
#  MAKE TEXT FRAME (PIL)
# ---------------------------------------------------------
def make_image_frame(text: str):
    img = Image.new("RGB", (WIDTH, HEIGHT), BG_COLOR)
    draw = ImageDraw.Draw(img)

    # Load fonts
    try:
        title_font = ImageFont.truetype("DejaVuSans-Bold.ttf", TITLE_FONT_SIZE)
        body_font = ImageFont.truetype("DejaVuSans.ttf", BODY_FONT_SIZE)
    except:
        title_font = ImageFont.load_default()
        body_font = ImageFont.load_default()

    # Split into lines nicely
    lines = []
    for line in text.split("\n"):
        lines.append(line.strip())

    # Calculate text block height
    total_height = 0
    for line in lines:
        w, h = draw.textbbox((0, 0), line, font=body_font)[2:]
        total_height += h + 10

    y = (HEIGHT - total_height) // 2

    for line in lines:
        w, h = draw.textbbox((0, 0), line, font=body_font)[2:]
        x = (WIDTH - w) // 2
        draw.text((x, y), line, fill=TEXT_COLOR, font=body_font)
        y += h + 10

    return img


# ---------------------------------------------------------
#  COMPOSE VIDEO
# ---------------------------------------------------------
def compose_video(scenes, output_path: Path):
    clips = []

    for scene in scenes:
        text = scene["text"]
        dur = float(scene["duration"])

        frame = make_image_frame(text)
        frame_path = OUT_DIR / f"frame_tmp.png"
        frame.save(frame_path)

        clip = ImageClip(str(frame_path)).set_duration(dur)

        # ★ IMPORTANT FIX: remove zoom animation (no resize = no ANTIALIAS bug)
        clip = clip

        clips.append(clip)

    final_video = concatenate_videoclips(clips, method="compose")
    final_video.write_videofile(
        str(output_path),
        fps=30,
        codec="libx264",
        audio=False,
        threads=4
    )

    print(f"[+] Saved video -> {output_path}")


# ---------------------------------------------------------
#  MAIN
# ---------------------------------------------------------
def main():
    print("[*] Creating Gemini model...")
    model = get_gemini_client()

    print("[*] Generating script...")
    scenes = generate_script(model)

    ts = datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")
    out_file = OUT_DIR / f"sigma_short_{ts}.mp4"

    print("[*] Composing video...")
    compose_video(scenes, out_file)

    print("[✔] Done!")


if __name__ == "__main__":
    main()


