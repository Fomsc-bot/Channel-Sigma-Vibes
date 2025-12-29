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
        try:
            font = ImageFont.truetype(font_path, size)
        except:
            # Fallback to default font
            font = ImageFont.load_default()
            return font, size, [text[:50]]  # Truncate if font fails
        
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
                try:
                    bbox = font.getbbox(test_line)
                except:
                    # Fallback for font measurement
                    bbox = (0, 0, len(test_line) * size // 2, size)
                
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
                try:
                    bbox = font.getbbox(line)
                    line_height = bbox[3] - bbox[1] + LINE_SPACING
                except:
                    line_height = size + LINE_SPACING
                
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
    try:
        font = ImageFont.truetype(font_path, MIN_FONT_SIZE)
    except:
        font = ImageFont.load_default()
    
    # Show only first few words
    words = text.split()[:5]
    return font, MIN_FONT_SIZE, [' '.join(words) + '...']

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
        return img.convert('RGB') if img.mode != 'RGB' else img
    
    # Calculate total text block dimensions
    line_heights = []
    line_widths = []
    for line in wrapped_lines:
        try:
            bbox = font.getbbox(line)
            line_heights.append(bbox[3] - bbox[1])
            line_widths.append(bbox[2] - bbox[0])
        except:
            line_heights.append(font_size)
            line_widths.append(len(line) * font_size // 2)
    
    total_height = sum(line_heights) + (len(wrapped_lines) - 1) * LINE_SPACING
    max_line_width = max(line_widths) if line_widths else 0
    
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
    try:
        blurred_bg = text_bg.filter(ImageFilter.GaussianBlur(BACKGROUND_BLUR_RADIUS))
        img = Image.alpha_composite(img, blurred_bg)
    except:
        # Fallback if blur fails
        img = Image.alpha_composite(img, text_bg)
    
    draw = ImageDraw.Draw(img)
    
    # Draw each line with shadow effect
    current_y = start_y
    for i, line in enumerate(wrapped_lines):
        try:
            bbox = font.getbbox(line)
            line_width = bbox[2] - bbox[0]
        except:
            line_width = len(line) * font_size // 2
        
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

def run_ffmpeg_command(cmd, error_message="FFmpeg error"):
    """Run FFmpeg command with error handling"""
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            check=True
        )
        return True, result.stdout
    except subprocess.CalledProcessError as e:
        print(f"❌ {error_message}")
        print(f"Command: {' '.join(cmd)}")
        print(f"Error: {e.stderr}")
        print(f"Return code: {e.returncode}")
        return False, e.stderr
    except Exception as e:
        print(f"❌ {error_message}: {e}")
        return False, str(e)

# ================= VIDEO CREATION =================

def create_video(row):
    try:
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
            print(f"⚠ No thumbnail found for {row['Title']}, using random")
            thumbnails = list(THUMB_DIR.glob("*"))
            if thumbnails:
                thumb_file = random.choice(thumbnails)
            else:
                print("❌ No thumbnails available")
                return None

        bg_files = list(BG_DIR.glob("*"))
        outtro_files = list(OUTTRO_DIR.glob("*"))
        
        if not bg_files:
            print("❌ No background images available")
            return None
        
        bg_file = random.choice(bg_files)
        outtro_file = random.choice(outtro_files) if outtro_files else bg_file

        # --- Split sentences and generate TTS ---
        full_text = row['Voiceover Text']
        sentences = [s.strip() for s in full_text.replace("?", ".").replace("!", ".").split(".") if s.strip()]
        
        if not sentences:
            print("❌ No sentences found in voiceover text")
            return None
            
        tts_files = []
        sentence_durations = []
        for i, s in enumerate(sentences):
            tts_path = OUTPUT_DIR / f"{uuid.uuid4().hex}_tts_{i}.mp3"
            try:
                generate_voice(s, tts_path)
                # get duration
                success, output = run_ffmpeg_command([
                    "ffprobe", "-v", "error", "-show_entries",
                    "format=duration", "-of",
                    "default=noprint_wrappers=1:nokey=1", str(tts_path)
                ], "Failed to get audio duration")
                
                if success:
                    dur = float(output.strip())
                else:
                    dur = max(len(s.split()) / 2.5, 1)  # Fallback duration
            except Exception as e:
                print(f"⚠ TTS generation error: {e}")
                dur = max(len(s.split()) / 2.5, 1)
                # Create a dummy audio file if needed
                if not tts_path.exists():
                    # Create silent audio as fallback
                    run_ffmpeg_command([
                        "ffmpeg", "-y", "-f", "lavfi", "-i", "anullsrc=channel_layout=stereo:sample_rate=44100",
                        "-t", str(dur), str(tts_path)
                    ], "Failed to create fallback audio")
            
            tts_files.append(tts_path)
            sentence_durations.append(dur)

        # --- Merge TTS audio for final video ---
        merged_audio = OUTPUT_DIR / f"{uuid.uuid4().hex}_merged.mp3"
        tts_list_file = OUTPUT_DIR / "tts_list.txt"
        
        # Create concat file
        with open(tts_list_file, "w") as f:
            for t in tts_files:
                if t.exists():
                    f.write(f"file '{t.resolve()}'\n")
        
        # Merge audio files
        success, _ = run_ffmpeg_command([
            "ffmpeg", "-y", "-f", "concat", "-safe", "0",
            "-i", str(tts_list_file),
            "-c", "copy", str(merged_audio)
        ], "Failed to merge audio files")
        
        if not success or not merged_audio.exists():
            print("⚠ Audio merging failed, creating silent audio")
            total_duration = sum(sentence_durations)
            run_ffmpeg_command([
                "ffmpeg", "-y", "-f", "lavfi", "-i", f"anullsrc=channel_layout=stereo:sample_rate=44100",
                "-t", str(total_duration), str(merged_audio)
            ], "Failed to create silent audio")

        total_duration = sum(sentence_durations)
        total_frames = int(total_duration * FPS)
        writer_path = OUTPUT_DIR / f"{uuid.uuid4().hex}_temp.mp4"
        
        # Create video writer
        writer = cv2.VideoWriter(
            str(writer_path),
            cv2.VideoWriter_fourcc(*"mp4v"),
            FPS,
            (VIDEO_WIDTH, VIDEO_HEIGHT)
        )
        
        if not writer.isOpened():
            print("❌ Failed to open video writer")
            return None

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
        
        # Simplified FFmpeg command without complex filter
        success, _ = run_ffmpeg_command([
            "ffmpeg", "-y",
            "-i", str(writer_path),
            "-i", str(merged_audio),
            "-c:v", "libx264",
            "-preset", "medium",
            "-crf", "23",
            "-c:a", "aac",
            "-b:a", "192k",
            "-shortest",
            "-movflags", "+faststart",
            str(final_path)
        ], "Failed to merge video and audio")
        
        if not success:
            # Try simpler approach
            print("⚠ Trying alternative merge method...")
            success, _ = run_ffmpeg_command([
                "ffmpeg", "-y",
                "-i", str(writer_path),
                "-i", str(merged_audio),
                "-c:v", "copy",
                "-c:a", "aac",
                str(final_path)
            ], "Alternative merge also failed")
        
        if not success or not final_path.exists():
            print("❌ Video creation failed completely")
            return None

        # --- Cleanup ---
        try:
            if writer_path.exists():
                writer_path.unlink()
            if merged_audio.exists():
                merged_audio.unlink()
            if tts_list_file.exists():
                tts_list_file.unlink()
            for t in tts_files:
                if t.exists():
                    t.unlink()
            # Don't delete thumb_file as it might be used by other videos
        except Exception as e:
            print(f"⚠ Cleanup error: {e}")

        print(f"✅ Video created successfully: {final_path}")
        return final_path
        
    except Exception as e:
        print(f"❌ Video creation failed: {e}")
        import traceback
        traceback.print_exc()
        return None

# ================= UPLOAD =================

def upload(video_file, row):
    if not video_file or not video_file.exists():
        print("❌ Video file doesn't exist for upload")
        return None
        
    creds = Credentials(None, refresh_token=REFRESH_TOKEN, token_uri="https://oauth2.googleapis.com/token",
                        client_id=CLIENT_ID, client_secret=CLIENT_SECRET,
                        scopes=["https://www.googleapis.com/auth/youtube.upload"])
    youtube = build("youtube", "v3", credentials=creds)
    try:
        response = youtube.videos().insert(
            part="snippet,status",
            body={
                "snippet": {
                    "title": f" {row['Title']} ",
                    "description": row['Voiceover Text'] + "\n\n" + 
                                  "💬 COMMENT your thoughts below!\n\n" +
                                  "🔔 SUBSCRIBE for daily motivation!\n\n" +
                                  "#motivation #success #mindset #inspiration #lifelessons #personaldevelopment",
                    "tags": ["motivation", "success", "mindset", "inspiration", "personal development"],
                    "categoryId": "22"
                },
                "status": {
                    "privacyStatus": "public",
                    "selfDeclaredMadeForKids": False
                }
            },
            media_body=MediaFileUpload(str(video_file), resumable=True)
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
        print(f"📊 Loaded {len(df)} rows from CSV")
    except Exception as e:
        print("❌ Failed to read CSV:", e)
        return

    if df.empty:
        print("⚠ CSV empty, nothing to upload.")
        return

    # Add tracking columns if they don't exist
    if 'Uploaded' not in df.columns:
        df['Uploaded'] = False
    if 'Video_ID' not in df.columns:
        df['Video_ID'] = ''
    if 'Upload_Date' not in df.columns:
        df['Upload_Date'] = ''

    # Get unprocessed rows
    unprocessed = df[~df['Uploaded']].head(3)
    
    if unprocessed.empty:
        print("✨ All videos have been processed!")
        return
    
    print(f"🎬 Processing {len(unprocessed)} videos...")
    
    for idx, row in unprocessed.iterrows():
        print(f"\n{'='*50}")
        print(f"🎬 Creating video: {row['Title']}")
        print(f"{'='*50}")
        
        video_file = create_video(row)
        if video_file:
            video_id = upload(video_file, row)
            if video_id:
                # Update CSV to mark as processed
                df.at[idx, 'Uploaded'] = True
                df.at[idx, 'Video_ID'] = video_id
                df.at[idx, 'Upload_Date'] = pd.Timestamp.now().strftime('%Y-%m-%d %H:%M:%S')
                
                # Save progress after each successful upload
                try:
                    df.to_csv(SCRIPT_CSV, index=False)
                    print("💾 Progress saved to CSV")
                except Exception as e:
                    print(f"⚠ Failed to save CSV: {e}")
            else:
                print(f"⚠ Upload failed for: {row['Title']}")
        else:
            print(f"⚠ Video creation failed for: {row['Title']}")
        
        # Add delay to avoid rate limiting
        import time
        time.sleep(2)
    
    print(f"\n{'='*50}")
    print("✨ Batch processing complete!")
    print(f"Total processed: {len(df[df['Uploaded']])}/{len(df)}")
    print(f"{'='*50}")

if __name__ == "__main__":
    main()
