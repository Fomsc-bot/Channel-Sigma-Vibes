from PIL import Image, ImageDraw, ImageFont
import os

OUTPUT_DIR = "outputs"
os.makedirs(OUTPUT_DIR, exist_ok=True)

# Your short text
text = """Stay focused.
Stay disciplined.
Stay unstoppable."""

# Video settings
W, H = 1080, 1920
FPS = 30
DURATION = 5  # seconds
FRAMES = FPS * DURATION

# Load a font
try:
    FONT = ImageFont.truetype("arial.ttf", 80)
except:
    FONT = ImageFont.load_default()

frames = []

for i in range(FRAMES):
    img = Image.new("RGB", (W, H), color=(0, 0, 0))
    draw = ImageDraw.Draw(img)

    # Multi-line centered text
    lines = text.split("\n")
    total_height = sum([draw.textbbox((0, 0), line, font=FONT)[3] for line in lines])
    y = (H - total_height) // 2

    for line in lines:
        bbox = draw.textbbox((0, 0), line, font=FONT)
        text_w = bbox[2]
        text_h = bbox[3]

        draw.text(((W - text_w) // 2, y), line, fill="white", font=FONT)
        y += text_h + 10

    frames.append(img)

# Save as MP4 using pillow-av (built into GitHub Actions)
output_path = os.path.join(OUTPUT_DIR, "short.mp4")
frames[0].save(
    output_path,
    save_all=True,
    append_images=frames[1:],
    duration=int(1000 / FPS),
    loop=0,
    codec="libx264",
)

print("Video saved to:", output_path)
