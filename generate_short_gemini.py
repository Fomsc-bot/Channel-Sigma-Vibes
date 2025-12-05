#!/usr/bin/env python3
"""
generate_short_gemini.py
Generates a vertical (9:16) YouTube Short using Gemini for script + TTS, and MoviePy for video composition.

Requires:
  - GEMINI_API_KEY environment variable (create one in Google AI Studio).
  - pip install -r requirements.txt

Run:
  python generate_short_gemini.py
"""

import os
import json
import time
from datetime import datetime
from pathlib import Path
import base64
import wave

# Gemini SDK + types
from google import genai
from google.genai import types

# Movie/graphics/audio
from moviepy.editor import ImageClip, concatenate_videoclips, AudioFileClip
from PIL import Image, ImageDraw, ImageFont
import numpy as np

# Config
W, H = 1080, 1920
OUTPUT_DIR = Path("outputs")
PROMPT_FILE = Path("content/prompt_templates.json")

# Make sure output dir exists
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

# --- Helper: load prompts ---
def load_prompt_templates(path=PROMPT_FILE):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)

# --- Gems: Gemini client setup ---
def make_genai_client():
    # The SDK automatically picks GEMINI_API_KEY if present.
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        raise RuntimeError("Set GEMINI_API_KEY environment variable (get it from Google AI Studio).")
    client = genai.Client(api_key=api_key)
    return client

# --- 1) Ask Gemini to produce a script in JSON ---
def request_script_json(client, prompt_templates):
    system = (
        "You are a short-form YouTube writer for 'Sigma Vibes'. Follow instructions strictly. "
        "Return ONLY valid JSON (no preface/explanations)."
    )
    # Compose prompt:
    contents = (
        prompt_templates.get("short_goal", "") + "\n\n"
        + prompt_templates.get("instructions_for_model", "") + "\n\n"
        + "Respond with JSON structure like: {\"scenes\": [ {\"title\":\"...\",\"subtitle\":\"...\",\"voice_text\":\"...\",\"duration_seconds\":3 }, ...], \"total_duration\":20 }"
    )

    # Use a Gemini text model for content creation
    resp = client.models.generate_content(
        model="gemini-2.5-flash",
        contents=contents
    )

    # The SDK exposes .text for convenience
    text = resp.text if hasattr(resp, "text") else None
    if not text:
        # Fallback: try candidate text
        try:
            text = resp.candidates[0].content[0].text
        except Exception:
            raise RuntimeError("Could not get text from Gemini response.")
    # Parse JSON (model should return JSON)
    try:
        # Model sometimes returns trailing whitespace/newlines
        payload = json.loads(text.strip())
    except Exception as e:
        # try to recover by extracting first {...} block
        import re
        m = re.search(r"\{.*\}", text, re.DOTALL)
        if not m:
            raise RuntimeError("Model response was not valid JSON. Raw response:\n" + text)
        payload = json.loads(m.group(0))
    return payload

# --- 2) TTS each scene using Gemini native TTS model ---
def synthesize_scene_audio(client, scene_text, out_wav_path, voice_name="Kore"):
    # Use TTS preview model (as in docs)
    model_name = "gemini-2.5-flash-preview-tts"
    # Call the SDK
    resp = client.models.generate_content(
        model=model_name,
        contents=scene_text,
        config=types.GenerateContentConfig(
            response_modalities=["AUDIO"],
            speech_config=types.SpeechConfig(
                voice_config=types.VoiceConfig(
                    prebuilt_voice_config=types.PrebuiltVoiceConfig(
                        voice_name=voice_name
                    )
                )
            )
        )
    )
    # Extract base64 or bytes
    candidate = resp.candidates[0]
    # Path in the SDK response: candidate.content.parts[0].inline_data.data
    data = None
    try:
        data = candidate.content.parts[0].inline_data.data
    except Exception:
        # fallback: string field
        data = candidate["content"][0]["parts"][0]["inline_data"]["data"]

    # data might already be bytes or a base64 string
    if isinstance(data, (bytes, bytearray)):
        pcm = data
    else:
        pcm = base64.b64decode(data)

    # The docs indicate PCM16LE s16le at 24000 Hz mono (sample_width=2, rate=24000)
    rate = 24000
    channels = 1
    sample_width = 2

    # Write to a WAV file
    with wave.open(str(out_wav_path), "wb") as wf:
        wf.setnchannels(channels)
        wf.setsampwidth(sample_width)
        wf.setframerate(rate)
        wf.writeframes(pcm)

    return str(out_wav_path)

# --- 3) Make an image frame for a scene (title + subtitle) ---
def make_image_frame(title, subtitle=None, bgcolor=(12,12,12), fontsize=100, subtitle_size=48):
    img = Image.new("RGB", (W, H), color=bgcolor)
    draw = ImageDraw.Draw(img)

    # try to use provided font first
    font_paths = [
        "assets/fonts/DejaVuSans-Bold.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
    ]
    try:
        font_path = next(p for p in font_paths if Path(p).exists())
        title_font = ImageFont.truetype(font_path, fontsize)
        sub_font = ImageFont.truetype(font_path, subtitle_size)
    except StopIteration:
        title_font = ImageFont.load_default()
        sub_font = ImageFont.load_default()

    # Title can have newlines
    lines = title.split("\n")
    y = int(H * 0.18)
    for line in lines:
        w, h = draw.textsize(line, font=title_font)
        draw.text(((W-w)/2, y), line, font=title_font, fill=(255,255,255))
        y += h + 8

    if subtitle:
        w2, h2 = draw.textsize(subtitle, font=sub_font)
        draw.text(((W-w2)/2, int(H*0.6)), subtitle, font=sub_font, fill=(220,220,220))

    return np.array(img)

# --- 4) Compose video with moviepy using generated audio and images ---
def compose_video_from_scenes(scenes, audio_paths, out_video_path, fps=30):
    # Create image clips
    clips = []
    for i, scene in enumerate(scenes):
        dur = int(scene.get("duration_seconds", 5))
        title = scene.get("title", "")
        subtitle = scene.get("subtitle", "")
        img_arr = make_image_frame(title, subtitle=subtitle)
        clip = ImageClip(img_arr).set_duration(dur)
        # small zoom-in
        clip = clip.fx(lambda c: c.resize(lambda t: 1 + 0.015 * t))
        clips.append(clip)

    video = concatenate_videoclips(clips, method="compose")
    # Build concatenated audio
    audio_clips = [AudioFileClip(p) for p in audio_paths]
    # concatenate AudioFileClip objects
    combined_audio = None
    if audio_clips:
        combined_audio = audio_clips[0]
        for a in audio_clips[1:]:
            combined_audio = concatenate_audioclips([combined_audio, a])
    if combined_audio:
        combined_audio = combined_audio.set_duration(video.duration)
        video = video.set_audio(combined_audio)

    video = video.set_fps(fps)
    video.write_videofile(str(out_video_path), codec="libx264", audio_codec="aac", threads=4, bitrate="3500k")
    return str(out_video_path)

# Helper required by compose (moviepy concat of audio)
from moviepy.editor import concatenate_audioclips

# --- Main flow ---
def main():
    print("[*] Loading prompt templates...")
    prompts = load_prompt_templates()

    print("[*] Creating Gemini client...")
    client = make_genai_client()

    print("[*] Requesting script JSON from Gemini...")
    payload = request_script_json(client, prompts)
    scenes = payload.get("scenes", [])
    if not scenes:
        raise RuntimeError("No scenes generated by Gemini.")

    # Ensure durations and sanity checks
    total_duration = sum(int(s.get("duration_seconds", 5)) for s in scenes)
    print(f"[+] Received {len(scenes)} scenes, total {total_duration}s.")

    # Create audio files for scenes
    audio_paths = []
    for idx, scene in enumerate(scenes):
        voice_text = scene.get("voice_text") or scene.get("title")
        out_wav = OUTPUT_DIR / f"scene_{idx+1}.wav"
        print(f"[*] Synthesizing TTS for scene {idx+1} (duration {scene.get('duration_seconds')}s)...")
        synth_path = synthesize_scene_audio(client, voice_text, out_wav)
        audio_paths.append(synth_path)

    # Compose video
    timestamp = datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")
    out_mp4 = OUTPUT_DIR / f"sigma_short_{timestamp}.mp4"
    print("[*] Composing final video with moviepy...")
    compose_video_from_scenes(scenes, audio_paths, out_mp4)
    print("[+] Video written to:", out_mp4)

if __name__ == "__main__":
    main()
