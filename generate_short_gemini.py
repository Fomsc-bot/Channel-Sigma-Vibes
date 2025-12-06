import os
import subprocess
from PIL import Image, ImageDraw, ImageFont
from transformers import AutoTokenizer, AutoModelForCausalLM

os.makedirs("frames", exist_ok=True)
os.makedirs("outputs", exist_ok=True)

# ------------------------------
# Load free HuggingFace model
# ------------------------------
print("[*] Loading text model...")
tokenizer = AutoTokenizer.from_pretrained("gpt2")
model = AutoModelForCausalLM.from_pretrained("gpt2")

def generate_script():
    print("[*] Generating script...")
    prompt = """Create a short motivational sigma-style script with 3 scenes.
Each scene should have a title and subtitle. Format:
Scene 1:
Title: ...
Subtitle: ...

Scene 2:
Title: ...
Subtitle: ...

Scene 3:
Title: ...
Subtitle: ...
"""
    inputs = tokenizer(prompt, return_tensors="pt")
    output = model.generate(**inputs, max_new_tokens=200)
    text = tokenizer.decode(output[0], skip_special_tokens=True)

    scenes = []
    for block in text.split("Scene"):
        if "Title:" in block and "Subtitle:" in block:
            try:
                title = block.split("Title:")[1].split("\n")[0].strip()
                subtitle = block.split("Subtitle:")[1].split("\n")[0].strip()
                scenes.append({"title": title, "subtitle": subtitle})
            except:
                pass

    return scenes[:3]

# ---------------------------------------
# Create PNG frames for each scene
# ---------------------------------------
def create_frame(img_path, title, subtitle):
    W, H = 1080, 1920
    img = Image.new("RGB", (W, H), color=(20, 20, 20))
    draw = ImageDraw.Draw(img)

    try:
        font_title = ImageFont.truetype("arial.ttf", 70)
        font_sub = ImageFont.truetype("arial.ttf", 50)
    except:
        font_title = ImageFont.load_default()
        font_sub = ImageFont.load_default()

    draw.text((50, 600), title, fill="white", font=font_title)
    draw.text((50, 750), subtitle, fill="white", font=font_sub)

    img.save(img_path)

# ---------------------------------------
# Generate 3-second video per scene
# ---------------------------------------
def make_video_from_frames():
    print("[*] Creating MP4 from frames...")
    output_file = "outputs/sigma_short.mp4"

    cmd = [
        "ffmpeg",
        "-y",
        "-framerate", "1",
        "-i", "frames/frame_%d.png",
        "-vf", "fps=30",
        "-pix_fmt", "yuv420p",
        output_file
    ]

    subprocess.run(cmd, check=True)
    print(f"[✔] Video saved to {output_file}")

# ---------------------------------------
# Main
# ---------------------------------------
def main():
    scenes = generate_script()

    print("[*] Creating image frames...")
    for i, s in enumerate(scenes):
        create_frame(f"frames/frame_{i}.png", s["title"], s["subtitle"])

    make_video_from_frames()

if __name__ == "__main__":
    main()
