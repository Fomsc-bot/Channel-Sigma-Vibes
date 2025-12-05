#!/usr/bin/env python3
"""
generate_short_gemini.py
Generates two vertical YouTube Shorts (text-only) using Gemini for script writing.

Requirements:
  - Set GEMINI_API_KEY environment variable (Google AI Studio / google-genai API key).
  - pip install -r requirements.txt

Run:
  python generate_short_gemini.py
"""

import os
import json
import time
from datetime import datetime
from pathlib import Path
import traceback

# Gemini SDK
try:
    from google import genai
    from google.genai import types
except Exception:
    genai = None

# Movie/graphics
from moviepy.editor import ImageClip, concatenate_videoclips
from PIL import Image, ImageDraw, ImageFont
import numpy as np

# Config
W, H = 1080, 1920  # vertical 9:16
OUTPUT_DIR = Path("outputs")
PROMPT_FILE = Path("content/prompt_templates.json")
ASSET_FONTS = [Path("assets/fonts/DejaVuSans-Bold.ttf"), Path("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf")]
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

# ---------------------------
# Utilities
# ---------------------------
def load_prompt_templates(path=PROMPT_FILE):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)

def make_genai_client():
    api_key = os.environ.get("GEMINI_API_KEY")
    if genai is None:
        raise RuntimeError("google-genai SDK not installed or import failed. pip install google-genai")
    if not api_key:
        raise RuntimeError("Set GEMINI_API_KEY environment variable.")
    client = genai.Client(api_key=api_key)
    return client

def request_script_json(client, base_prompt, variation_note=""):
    """
    Ask Gemini to produce a JSON script. Returns parsed JSON.
    If Gemini response cannot be parsed, raises RuntimeError with response text.
    """
    system = "You are a professional short-form writer for a motivational channel named 'Sigma Vibes'."
    prompt = (
        base_prompt + "\n\n"
        + "Variation note: " + variation_note + "\n\n"
        + "IMPORTANT: Return ONLY valid JSON. Example format:\n"
        + "{\"scenes\": [{\"title\":\"...\",\"subtitle\":\"...\",\"duration_seconds\":3},{...}], \"total_duration\":20}"
    )

    # Use the text model
    resp = client.models.generate_content(
        model="gemini-2.5-flash",
        contents=prompt
    )

    # Extract text safely
    text = None
    try:
        text = resp.text if hasattr(resp, "text") and resp.text else None
    except Exception:
        pass

    if not text:
        # Try candidate path
        try:
            text = resp.candidates[0].content[0].text
        except Exception:
            text = None

    if not text:
        raise RuntimeError("No text returned from Gemini. Response object:\n" + str(resp))

    # Try parse JSON
    try:
        payload = json.loads(text.strip())
        return payload
    except Exception:
        # Try to extract first {...} block
        import re
        m = re.search(r"\{.*\}", text, re.DOTALL)
        if not m:
            raise RuntimeError("Gemini returned non-JSON and no JSON block. Raw:\n" + text)
        payload = json.loads(m.group(0))
        return payload

# ---------------------------
# Image generation (text-only visuals)
# ---------------------------
def pick_font(size):
    for p in ASSET_FONTS:
        if p.exists():
            try:
                return ImageFont.truetype(str(p), size)
            except Exception:
                continue
    return ImageFont.load_default()

def make_image_frame(title, subtitle=None, channel_name="Sigma Vibes", bgcolor=(18,18,18)):
    """
    Creates an RGB numpy image sized W x H with centered title and subtitle using Pillow textbbox.
    """
    img = Image.new("RGB", (W, H), color=bgcolor)
    draw = ImageDraw.Draw(img)

    # Fonts
    title_font = pick_font(110)
    subtitle_font = pick_font(48)
    watermark_font = pick_font(36)

    # Title (allow newlines)
    lines = title.split("\n")
    # start y somewhat upper
    y = int(H * 0.2)
    for line in lines:
        bbox = draw.textbbox((0,0), line, font=title_font)
        w = bbox[2] - bbox[0]
        h = bbox[3] - bbox[1]
        draw.text(((W-w)//2, y), line, font=title_font, fill=(255,255,255))
        y += h + 10

    # Subtitle
    if subtitle:
        bbox = draw.textbbox((0,0), subtitle, font=subtitle_font)
        w = bbox[2] - bbox[0]
        h = bbox[3] - bbox[1]
        draw.text(((W-w)//2, int(H*0.62)), subtitle, font=subtitle_font, fill=(200,200,200))

    # Channel watermark bottom-left
    wm_text = f"@{channel_name.replace(' ', '')}"
    bbox = draw.textbbox((0,0), wm_text, font=watermark_font)
    draw.text((30, H - bbox[3] - 30), wm_text, font=watermark_font, fill=(150,150,150))

    return np.array(img)

# ---------------------------
# Compose video
# ---------------------------
def compose_video_from_scenes(scenes, out_path, channel_name="Sigma Vibes", fps=30):
    clips = []
    for scene in scenes:
        dur = int(scene.get("duration_seconds", 5))
        title = scene.get("title", "")
        subtitle = scene.get("subtitle", "")
        img_arr = make_image_frame(title, subtitle=subtitle, channel_name=channel_name)
        clip = ImageClip(img_arr).set_duration(dur)
        # Slight zoom in effect (using resize lambda)
        clip = clip.fx(lambda c: c.resize(lambda t: 1 + 0.012 * t))
        clips.append(clip)
    video = concatenate_videoclips(clips, method="compose")
    video = video.set_fps(fps)
    # No audio (text-only)
    video.write_videofile(str(out_path), codec="libx264", audio=False, threads=4, bitrate="3500k")
    return str(out_path)

# ---------------------------
# Main
# ---------------------------
def main():
    print("[*] Loading prompt templates...")
    prompts = load_prompt_templates()
    channel_name = prompts.get("channel_name", "Sigma Vibes")
    base_prompt = prompts.get("short_goal", "") + "\n\n" + prompts.get("instructions_for_model", "")

    # Create client if possible; else fallback to template
    client = None
    try:
        client = make_genai_client()
    except Exception as e:
        print("[!] Could not create Gemini client (falling back to local templates). Error:", str(e))

    outputs = []
    timestamp = datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")

    # We'll generate 2 variations per run
    for variant_idx in range(1, 3):
        print(f"[*] Generating script variant {variant_idx}...")
        variation_note = "Produce a slightly different hook & phrasing (variant #%d)." % variant_idx
        try:
            if client:
                payload = request_script_json(client, base_prompt, variation_note)
            else:
                # Fallback: produce a simple template script if no Gemini available
                print("[!] No Gemini client — using local fallback script.")
                payload = {
                    "scenes": [
                        {"title": "Most Sigma men never share this secret...", "subtitle": "Stay silent. Build quietly.", "duration_seconds": 3},
                        {"title": "Rule #1\\nFocus > Approval", "subtitle": "Do the work, ignore noise.", "duration_seconds": 8},
                        {"title": "Follow for daily Sigma rules", "subtitle": "Join the Sigma Vibes squad", "duration_seconds": 4}
                    ],
                    "total_duration": 15
                }
        except Exception as e:
            traceback.print_exc()
            print("[!] Error generating script from Gemini:", e)
            # Try fallback
            payload = {
                "scenes": [
                    {"title": "Most Sigma men never share this...", "subtitle": "Build silently.", "duration_seconds": 3},
                    {"title": "Rule #1\\nProtect Your Time", "subtitle": "Say no to distractions.", "duration_seconds": 7},
                    {"title": "Follow for more", "subtitle": "Daily Sigma rules", "duration_seconds": 4}
                ], "total_duration": 14
            }

        scenes = payload.get("scenes", [])
        if not scenes:
            print("[!] Generated payload contains no scenes — skipping variant.")
            continue

        out_mp4 = OUTPUT_DIR / f"sigma_short_var{variant_idx}_{timestamp}.mp4"
        print(f"[*] Composing video for variant {variant_idx} -> {out_mp4} ...")
        try:
            compose_video_from_scenes(scenes, out_mp4, channel_name=channel_name)
            outputs.append(str(out_mp4))
            print("[+] Wrote:", out_mp4)
        except Exception as e:
            print("[!] Error composing video:", e)
            traceback.print_exc()

    if outputs:
        print("[+] Completed. Generated files:")
        for p in outputs:
            print("   -", p)
    else:
        print("[!] No outputs produced.")

if __name__ == "__main__":
    main()

