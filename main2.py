#!/usr/bin/env python3

import cv2
import numpy as np
import pandas as pd
import pytesseract
import random
import subprocess
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont, ImageOps, ImageFilter
from gtts import gTTS
import uuid
import os
import sys
import textwrap
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
from google.oauth2.credentials import Credentials
from fuzzywuzzy import process

# ================= ENHANCED CONFIG =================

VIDEO_WIDTH = 1920
VIDEO_HEIGHT = 1080
FPS = 30

THUMB_DURATION = 1        # seconds
OUTTRO_DURATION = 2       # seconds
FONT_PATH = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
MIN_FONT_SIZE = 40
MAX_FONT_SIZE = 70
LINE_SPACING = 15
MAX_LINE_WIDTH = 1600     # Prevent text from reaching edges
TEXT_PADDING = 100        # Padding from screen edges

# Visual enhancements
BACKGROUND_BLUR_RADIUS = 15
TEXT_BACKGROUND_OPACITY = 0.7
SHADOW_OFFSET = (4, 4)
SHADOW_BLUR = 6
ANIMATION_DURATION = 0.5  # seconds for fade in/out

THUMB_DIR = Path("thumbnails")
BG_DIR = Path("backgroundim")
OUTTRO_DIR = Path("outtro")
SCRIPT_CSV = Path("Script/script.csv")
OUTPUT_DIR = Path("outputs")
OUTPUT_DIR.mkdir(exist_ok=True)

# ================= YOUTUBE AUTH =================

CLIENT_ID = os.environ.get("YT_CLIENT_ID")
CLIENT_SECRET = os.environ.get("YT_CLIENT_SECRET")
REFRESH_TOKEN = os.environ.get("YT_REFRESH_TOKEN")

if not CLIENT_ID or not CLIENT_SECRET or not REFRESH_TOKEN:
    print("❌ Missing YouTube credentials. Set YT_CLIENT_ID, YT_CLIENT_SECRET, YT_REFRESH_TOKEN.")
    sys.exit(1)

# ================= ENHANCED UTILITIES =================

def extract_text_from_image(img_path):
    img = Image.open(img_path)
    text = pytesseract.image_to_string(img, lang="eng")
    text = " ".join(text.split())
    return text if text else "Double Meaning Quote"

def generate_voice(text, out_path):
    text = text.replace("’", "'").replace("‘", "'")
    tts = gTTS(text=text, lang="en")
    tts.save(out_path)

def resize(img):
    return img.resize((VIDEO_WIDTH, VIDEO_HEIGHT), Image.LANCZOS)

def ease_in_out(t):
    return 0.5 - 0.5 * np.cos(np.pi * t)

def prepare_ken_burns(img):
    zoom_end = random.uniform(1.05, 1.15)
    pan_x = random.choice([0, 0.5, 1])
    pan_y = random.choice([0, 0.5, 1])
    return zoom_end, pan_x, pan_y

def ken_burns_frame(img, idx, total, zoom_end, pan_x, pan_y):
    t = ease_in_out(idx / total)
    zoom = 1 + (zoom_end - 1) * t
    w, h = img.size
    cw, ch = int(w / zoom), int(h / zoom)
    x = int((w - cw) * pan_x * t)
    y = int((h - ch) * pan_y * t)
    crop = img.crop((x, y, x + cw, y + ch))
    return crop.resize((VIDEO_WIDTH, VIDEO_HEIGHT), Image.LANCZOS)

def get_optimal_font_size(text, max_width, max_height, font_path):
    """Dynamically adjust font size to fit text within bounds"""
    font_size = MAX_FONT_SIZE
    
    # Split into sentences first
    sentences = [s.strip() for s in text.replace("?", ".").replace("!", ".").split(".") if s.strip()]
    if not sentences:
        return FONT_PATH, FONT_SIZE, []
    
    # Adjust font size until text fits
    for size in range(MAX_FONT_SIZE, MIN_FONT_SIZE - 1, -2):
        font = ImageFont.truetype(font_path, size)
        wrapped_lines = []
        total_height = 0
        fits = True
        
        for sentence in sentences:
            # Wrap each sentence
            words = sentence.split()
            lines = []
            current_line = []
            
            for word in words:
                test_line = ' '.join(current_line + [word])
                bbox = font.getbbox(test_line)
                if bbox[2] - bbox[0] <= max_width:
                    current_line.append(word)
                else:
                    if current_line:
                        lines.append(' '.join(current_line))
                    current_line = [word]
            
            if current_line:
                lines.append(' '.join(current_line))
            
            # Check if lines fit vertically
            for line in lines:
                bbox = font.getbbox(line)
                line_height = bbox[3] - bbox[1] + LINE_SPACING
                total_height += line_height
                if total_height > max_height:
                    fits = False
                    break
            
            if not fits:
                break
            wrapped_lines.extend(lines)
        
        if fits:
            return font, size, wrapped_lines
    
    # If even minimum doesn't fit, truncate
    font = ImageFont.truetype(font_path, MIN_FONT_SIZE)
    return font, MIN_FONT_SIZE, ["Text too long to display..."]

def create_text_background(size, text_bbox, padding=20, opacity=0.7):
    """Create a blurred background behind text for better readability"""
    # Create a blank image with alpha channel
    bg = Image.new('RGBA', size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(bg)
    
    # Draw rounded rectangle behind text
    x0 = text_bbox[0] - padding
    y0 = text_bbox[1] - padding
    x1 = text_bbox[2] + padding
    y1 = text_bbox[3] + padding
    
    # Create rounded rectangle
    radius = 20
    draw.rectangle([x0, y0 + radius, x1, y1 - radius], fill=(0, 0, 0, int(255 * opacity)))
    draw.rectangle([x0 + radius, y0, x1 - radius, y1], fill=(0, 0, 0, int(255 * opacity)))
    draw.pieslice([x0, y0, x0 + radius * 2, y0 + radius * 2], 180, 270, fill=(0, 0, 0, int(255 * opacity)))
    draw.pieslice([x1 - radius * 2, y0, x1, y0 + radius * 2], 270, 360, fill=(0, 0, 0, int(255 * opacity)))
    draw.pieslice([x0, y1 - radius * 2, x0 + radius * 2, y1], 90, 180, fill=(0, 0, 0, int(255 * opacity)))
    draw.pieslice([x1 - radius * 2, y1 - radius * 2, x1, y1], 0, 90, fill=(0, 0, 0, int(255 * opacity)))
    
    return bg

def draw_caption(img, text, alpha=1.0, animation_progress=1.0):
    """Enhanced caption drawing with proper wrapping and visual effects"""
    # Convert to RGBA for transparency support
    if img.mode != 'RGBA':
        img = img.convert('RGBA')
    
    # Create a copy for drawing
    draw_img = img.copy()
    draw = ImageDraw.Draw(draw_img)
    
    # Calculate available space
    max_width = VIDEO_WIDTH - (2 * TEXT_PADDING)
    max_height = VIDEO_HEIGHT - (2 * TEXT_PADDING)
    
    # Get optimal font and wrapped lines
    font, font_size, wrapped_lines = get_optimal_font_size(
        text, max_width, max_height, FONT_PATH
    )
    
    if not wrapped_lines:
        return img
    
    # Calculate total text block dimensions
    line_heights = []
    line_widths = []
    for line in wrapped_lines:
        bbox = font.getbbox(line)
        line_heights.append(bbox[3] - bbox[1])
        line_widths.append(bbox[2] - bbox[0])
    
    total_height = sum(line_heights) + (len(wrapped_lines) - 1) * LINE_SPACING
    max_line_width = max(line_widths)
    
    # Center the text block
    start_y = (VIDEO_HEIGHT - total_height) // 2
    text_bbox = [
        (VIDEO_WIDTH - max_line_width) // 2,  # left
        start_y,  # top
        (VIDEO_WIDTH + max_line_width) // 2,  # right
        start_y + total_height  # bottom
    ]
    
    # Apply animation (fade in/out)
    animated_alpha = alpha * animation_progress
    
    # Create and apply text background
    text_bg = create_text_background(
        (VIDEO_WIDTH, VIDEO_HEIGHT),
        text_bbox,
        padding=30,
        opacity=TEXT_BACKGROUND_OPACITY * animated_alpha
    )
    
    # Apply Gaussian blur to background for depth
    blurred_bg = text_bg.filter(ImageFilter.GaussianBlur(BACKGROUND_BLUR_RADIUS))
    img = Image.alpha_composite(img, blurred_bg)
    draw = ImageDraw.Draw(img)
    
    # Draw each line with shadow effect
    current_y = start_y
    for i, line in enumerate(wrapped_lines):
        bbox = font.getbbox(line)
        line_width = bbox[2] - bbox[0]
        x = (VIDEO_WIDTH - line_width) // 2
        
        # Draw shadow with gradient opacity
        shadow_alpha = int(100 * animated_alpha)
        for offset_x in range(SHADOW_OFFSET[0] + 1):
            for offset_y in range(SHADOW_OFFSET[1] + 1):
                if offset_x == 0 and offset_y == 0:
                    continue
                draw.text(
                    (x + offset_x, current_y + offset_y),
                    line,
                    font=font,
                    fill=(0, 0, 0, shadow_alpha)
                )
        
        # Draw main text
        text_alpha = int(255 * animated_alpha)
        # Add subtle gradient to text (darker at bottom for 3D effect)
        draw.text(
            (x, current_y),
            line,
            font=font,
            fill=(255, 255, 255, text_alpha)
        )
        
        # Draw highlight on top of text for embossed effect
        highlight_alpha = int(100 * animated_alpha)
        draw.text(
            (x, current_y - 1),
            line,
            font=font,
            fill=(255, 255, 255, highlight_alpha)
        )
        
        current_y += line_heights[i] + LINE_SPACING
    
    return img.convert('RGB')

# ================= VIDEO CREATION =================

def create_video(row):
    # --- Thumbnail selection ---
    thumb_file = None
    thumbnails = list(THUMB_DIR.glob("*"))
    if thumbnails:
        thumb_texts = [extract_text_from_image(f) for f in thumbnails]
        best_match, score = process.extractOne(row['Title'], thumb_texts)
        if score >= 80:
            idx = thumb_texts.index(best_match)
            thumb_file = thumbnails[idx]
    if not thumb_file:
        print(f"⚠ No thumbnail found for {row['Title']}")
        return None

    bg_file = random.choice(list(BG_DIR.glob("*")))
    outtro_file = random.choice(list(OUTTRO_DIR.glob("*")))

    # --- Split sentences and generate TTS ---
    full_text = row['Voiceover Text']
    sentences = [s.strip() for s in full_text.replace("?", ".").replace("!", ".").split(".") if s.strip()]
    tts_files = []
    sentence_durations = []
    for i, s in enumerate(sentences):
        tts_path = OUTPUT_DIR / f"{uuid.uuid4().hex}_tts_{i}.mp3"
        generate_voice(s, tts_path)
        # get duration
        try:
            dur = float(subprocess.check_output([
                "ffprobe","-v","error","-show_entries",
                "format=duration","-of",
                "default=noprint_wrappers=1:nokey=1", str(tts_path)
            ]).decode().strip())
        except:
            dur = max(len(s.split())/2, 1)
        tts_files.append(tts_path)
        sentence_durations.append(dur)

    # --- Merge TTS audio for final video ---
    merged_audio = OUTPUT_DIR / f"{uuid.uuid4().hex}_merged.mp3"
    with open(OUTPUT_DIR / "tts_list.txt", "w") as f:
        for t in tts_files:
            f.write(f"file '{t.resolve()}'\n")
    subprocess.run([
        "ffmpeg","-y","-f","concat","-safe","0",
        "-i", str(OUTPUT_DIR / "tts_list.txt"),
        "-c","copy", str(merged_audio)
    ], check=True)

    total_duration = sum(sentence_durations)
    total_frames = int(total_duration * FPS)
    writer_path = OUTPUT_DIR / f"{uuid.uuid4().hex}_temp.mp4"
    writer = cv2.VideoWriter(str(writer_path), cv2.VideoWriter_fourcc(*"mp4v"), FPS, (VIDEO_WIDTH, VIDEO_HEIGHT))

    # --- Thumbnail with animation ---
    thumb_img = resize(Image.open(thumb_file))
    for i in range(THUMB_DURATION * FPS):
        # Fade in effect
        alpha = min(1.0, i / (FPS * 0.5))  # Fade in over 0.5 seconds
        frame_img = thumb_img.copy()
        frame = draw_caption(frame_img, row['Title'], alpha=alpha)
        writer.write(cv2.cvtColor(np.array(frame), cv2.COLOR_RGB2BGR))

    # --- Main Scene ---
    bg_img = resize(Image.open(bg_file))
    zoom_end, pan_x, pan_y = prepare_ken_burns(bg_img)

    # Track sentence timing
    frame_cursor = 0
    for s, dur in zip(sentences, sentence_durations):
        frames = int(dur * FPS)
        # Calculate animation frames for this sentence
        fade_frames = int(min(frames * 0.2, FPS * ANIMATION_DURATION))
        
        for i in range(frames):
            frame = ken_burns_frame(bg_img, frame_cursor + i, total_frames, zoom_end, pan_x, pan_y)
            
            # Calculate animation progress (fade in at start, fade out at end)
            animation_progress = 1.0
            if i < fade_frames:
                # Fade in
                animation_progress = i / fade_frames
            elif i > frames - fade_frames:
                # Fade out
                animation_progress = (frames - i) / fade_frames
            
            # Draw caption with animation
            frame = draw_caption(frame, s, animation_progress=animation_progress)
            writer.write(cv2.cvtColor(np.array(frame), cv2.COLOR_RGB2BGR))
        frame_cursor += frames

    # --- Outro ---
    outtro_img = resize(Image.open(outtro_file))
    outro_frames = OUTTRO_DURATION * FPS
    zoom_end_out, pan_x_out, pan_y_out = prepare_ken_burns(outtro_img)
    for i in range(outro_frames):
        # Fade out effect for outro
        alpha = max(0.0, 1.0 - (i / (outro_frames * 0.5)))
        frame = ken_burns_frame(outtro_img, i, outro_frames, zoom_end_out, pan_x_out, pan_y_out)
        # Add call to action text
        cta_text = "Like & Subscribe!"
        if i > outro_frames * 0.3:  # Show CTA after 30% of outro
            frame = draw_caption(frame, cta_text, alpha=alpha)
        writer.write(cv2.cvtColor(np.array(frame), cv2.COLOR_RGB2BGR))

    writer.release()

    # --- Merge video with merged audio ---
    final_path = OUTPUT_DIR / f"{uuid.uuid4().hex}_final.mp4"
    # Add background music for better engagement (optional)
    # bg_music_path = "path/to/background_music.mp3"
    
    subprocess.run([
        "ffmpeg","-y",
        "-i", str(writer_path),
        "-i", str(merged_audio),
        # "-i", bg_music_path,  # Uncomment to add background music
        "-filter_complex", "[1:a]volume=1.0[a1];[a1]aresample=async=1:first_pts=0[aout]",  # Audio normalization
        "-c:v", "libx264",
        "-preset", "medium",
        "-crf", "23",
        "-c:a", "aac",
        "-b:a", "192k",
        "-shortest",
        str(final_path)
    ], check=True)

    # --- Cleanup ---
    writer_path.unlink()
    merged_audio.unlink()
    (OUTPUT_DIR / "tts_list.txt").unlink()
    for t in tts_files:
        t.unlink()
    thumb_file.unlink()

    return final_path

# ================= UPLOAD =================

def upload(video_file, row):
    creds = Credentials(None, refresh_token=REFRESH_TOKEN, token_uri="https://oauth2.googleapis.com/token",
                        client_id=CLIENT_ID, client_secret=CLIENT_SECRET,
                        scopes=["https://www.googleapis.com/auth/youtube.upload"])
    youtube = build("youtube", "v3", credentials=creds)
    try:
        response = youtube.videos().insert(
            part="snippet,status",
            body={
                "snippet": {
                    "title": f"🔥 {row['Title']} 🔥",  # Add emojis for clickability
                    "description": row['Voiceover Text'] + "\n\n" + 
                                  "👇 WATCH NEXT: [Your Playlist Link]\n\n" +
                                  "💬 COMMENT your thoughts below!\n\n" +
                                  "🔔 SUBSCRIBE for daily motivation!\n\n" +
                                  "📱 FOLLOW on social media: [Your Links]\n\n" +
                                  "#motivation #success #mindset #inspiration #lifelessons #personaldevelopment #growthmindset #positivevibes #entrepreneur #goals",
                    "tags": ["motivation", "success", "mindset", "inspiration", "personal development", 
                            "life lessons", "positive thinking", "self improvement", "mindfulness"],
                    "categoryId": "22"
                },
                "status": {
                    "privacyStatus": "public",
                    "selfDeclaredMadeForKids": False,
                    "embeddable": True
                }
            },
            media_body=MediaFileUpload(video_file, resumable=True)
        ).execute()
        print("✅ Uploaded Video ID:", response.get("id"))
        return response.get("id")
    except Exception as e:
        print("❌ Upload failed:", e)
        return None

# ================= ENHANCED MAIN =================

def main():
    try:
        df = pd.read_csv(SCRIPT_CSV, encoding='latin1')
    except Exception as e:
        print("❌ Failed to read CSV:", e)
        return

    if df.empty:
        print("⚠ CSV empty, nothing to upload.")
        return

    # Process up to 3 videos in one run
    for idx, row in df.head(3).iterrows():
        print(f"🎬 Creating video {idx + 1}/3: {row['Title']}")
        video_file = create_video(row)
        if video_file:
            video_id = upload(video_file, row)
            if video_id:
                # Update CSV to mark as processed
                df.at[idx, 'Uploaded'] = True
                df.at[idx, 'Video_ID'] = video_id
                df.at[idx, 'Upload_Date'] = pd.Timestamp.now().strftime('%Y-%m-%d %H:%M:%S')
            else:
                print(f"⚠ Upload failed for: {row['Title']}")
        else:
            print(f"⚠ Video creation failed for: {row['Title']}")
        
        # Save progress after each video
        df.to_csv(SCRIPT_CSV, index=False)
        print("💾 Progress saved to CSV")
    
    print("✨ Batch processing complete!")

if __name__ == "__main__":
    main()
