import os
import random
from PIL import Image, ImageDraw, ImageFont
import subprocess

# ---------------------------------------------------------
# SIMPLE TEXT GENERATION (free, local)
# ---------------------------------------------------------
PROMPTS = [
    ("THE GRIND NEVER STOPS", "Winners work in silence."),
    ("BE UNSTOPPABLE", "Let your actions talk."),
    ("FOCUS ON YOURSELF", "The world follows those who don’t wait."),
    ("KEEP MOVING", "Small steps create big change."),
    ("NO EXCUSES", "Discipline beats motivation."),
]

def generate_scenes():
    scenes = []
    for _ in range(3):
        title, subtitle = random.choice(PROMPTS)
        scenes.append({"title": title, "subtitle": subtitle})
    return scenes


# ---------------------------------------------------------
# FRAME CREATION USING PILLOW (Pillow 12 compatible)
# ---------------------------------------------------------
def create_frame(path, title, subtitle):
    W, H = 1080, 1920
    img = Image.new("RGB", (W, H), color=(20, 20, 20))
    draw = ImageDraw.Draw(img)

    FONT_PATH = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"

    # Load fonts
    try:
        font_title = ImageFont.truetype(FONT_PATH, 110)
        font_sub = ImageFont.truetype(FONT_PATH, 70)
    except Exception as e:
        print("Font load failed, using default:", e)
        font_title = ImageFont.load_default()
        font_sub = ImageFont.load_default()

    # ---- FIX FOR PILLOW 12 (uses textbbox instead of textsize) ----
    title_bbox = draw.textbbox((0, 0), title, font=font_title)
    sub_bbox = draw.textbbox((0, 0), subtitle, font=font_sub)

    title_w = title_bbox[2] - title_bbox[0]
    title_h = title_bbox[3] - title_bbox[1]

    sub_w = sub_bbox[2] - sub_bbox[0]
    sub_h = sub_bbox[3] - sub_bbox[1]
    # ---------------------------------------------------------------

    # Draw centered title
    draw.text(
        ((W - title_w) / 2, 650),
        title,
        fill="white",
        font=font_title
    )

    # Draw centered subtitle
    draw.text(
        ((W - sub_w) / 2, 850),
        subtitle,
        fill="white",
        font=font_sub
    )

    img.save(path)


# ---------------------------------------------------------
# VIDEO CREATION USING FFMPEG
# ---------------------------------------------------------
def create_video():
    scenes = generate_scenes()

    if not os.path.exists("frames"):
        os.mkdir("frames")

    frames = []

    # Create frames
    for i, scene in enumerate(scenes):
        frame_path = f"frames/frame_{i}.png"
        create_frame(frame_path, scene["title"], scene["subtitle"])
        frames.append(frame_path)

    # Build concat file
    concat_file = "frames/concat.txt"
    with open(concat_file, "w") as f:
        for frame in frames:
            f.write(f"file '{os.getcwd()}/{frame}'\n")
            f.write("duration 3\n")

    output_path = "outputs/sigma_short.mp4"

    # Render video
    subprocess.run([
        "ffmpeg", "-y",
        "-f", "concat",
        "-safe", "0",
        "-i", concat_file,
        "-vf", "fps=30",
        "-pix_fmt", "yuv420p",
        output_path
    ])

    print("[✓] Video generated:", output_path)


# ---------------------------------------------------------
# MAIN
# ---------------------------------------------------------
if __name__ == "__main__":
    if not os.path.exists("outputs"):
        os.mkdir("outputs")
    create_video()
