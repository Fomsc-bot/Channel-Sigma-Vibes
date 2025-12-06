import os
import random
from moviepy.editor import *
from PIL import Image, ImageDraw, ImageFont

# -------------------------
# CONFIGURATION
# -------------------------
WIDTH = 1080
HEIGHT = 1920
BG_COLOR = (10, 10, 10)
TEXT_COLOR = "white"
FONT_TITLE = "DejaVuSans-Bold.ttf"      # GitHub Actions safe font
FONT_SIZE_TITLE = 80
DURATION = 6                             # seconds
FADE_DURATION = 1.2                      # text fade-in

QUOTES_FILE = "quotes.txt"
OUTPUT_DIR = "outputs"


# -------------------------
# Read a quote + delete it so it won't repeat
# -------------------------
def get_unique_quote():
    if not os.path.exists(QUOTES_FILE):
        raise FileNotFoundError("quotes.txt not found! Add it to the repo.")

    with open(QUOTES_FILE, "r", encoding="utf-8") as f:
        quotes = [q.strip() for q in f.readlines() if q.strip()]

    if not quotes:
        raise ValueError("No quotes left in quotes.txt")

    quote = random.choice(quotes)
    quotes.remove(quote)

    # Write back remaining quotes
    with open(QUOTES_FILE, "w", encoding="utf-8") as f:
        for q in quotes:
            f.write(q + "\n")

    return quote


# -------------------------
# Create ONE frame with text
# -------------------------
def generate_frame(quote, frame_path):
    img = Image.new("RGB", (WIDTH, HEIGHT), BG_COLOR)
    draw = ImageDraw.Draw(img)

    # Load font
    try:
        font = ImageFont.truetype(FONT_TITLE, FONT_SIZE_TITLE)
    except:
        font = ImageFont.load_default()

    # Text box wrap
    max_width = WIDTH - 200
    words = quote.split()
    lines = []
    line = ""

    for word in words:
        test_line = line + word + " "
        w, _ = draw.textbbox((0, 0), test_line, font=font)[2:]
        if w <= max_width:
            line = test_line
        else:
            lines.append(line)
            line = word + " "
    lines.append(line)

    # Center vertically
    total_h = len(lines) * (FONT_SIZE_TITLE + 20)
    y = (HEIGHT - total_h) // 2

    # Draw each line
    for line in lines:
        w, h = draw.textbbox((0, 0), line, font=font)[2:]
        x = (WIDTH - w) // 2
        draw.text((x, y), line, fill=TEXT_COLOR, font=font)
        y += FONT_SIZE_TITLE + 20

    img.save(frame_path)


# -------------------------
# Create final video
# -------------------------
def create_video():
    if not os.path.exists(OUTPUT_DIR):
        os.makedirs(OUTPUT_DIR)

    quote = get_unique_quote()
    frame_path = "frame.png"

    print("Using quote:", quote)

    # Create still image
    generate_frame(quote, frame_path)

    # Load image into video
    clip = ImageClip(frame_path).set_duration(DURATION)

    # Add fade-in
    clip = clip.fadein(FADE_DURATION)

    # Slight zoom animation (for engagement)
    clip = clip.resize(lambda t: 1 + 0.02 * t)

    # Output file
    output_path = os.path.join(OUTPUT_DIR, "sigma_short.mp4")
    clip.write_videofile(
        output_path,
        fps=30,
        codec="libx264",
        audio=False,
        threads=4
    )

    print("Generated:", output_path)


# -------------------------
# Run generator
# -------------------------
if __name__ == "__main__":
    create_video()
