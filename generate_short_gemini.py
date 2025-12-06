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
# FRAME CREATION USING PILLOW
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

    # Calculate text size
    title_w, title_h = draw.textsize(title, font=font_title)
    sub_w, sub_h = draw.textsize(subtitle, font=font_sub)

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

    frames = []
    if not os.path.exists("frames"):
        os.mkdir("frames")

    # Create frames
    for i, scene in enumerate(scenes):
        frame_path = f"frames/frame_{i}.png"
        create_frame(frame_path, scene["title"], scene["subtitle"])
        frames.append(frame_path)

    # Build concat text file for ffmpeg
    concat_file = "frames/concat.txt"
    with open(concat_file, "w") as f:
        for frame in frames:
            # each frame shows 3 seconds
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
