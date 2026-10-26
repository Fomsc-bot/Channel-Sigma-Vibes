#!/usr/bin/env python3
"""Render one inline-CSS HTML scene and publish it as a YouTube Short."""
from __future__ import annotations
import json, os, random, re, subprocess, sys, urllib.parse, urllib.request
from collections import Counter
from html.parser import HTMLParser
from pathlib import Path
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parent
INPUT_DIR = ROOT / "HTML Files That Needed To Convert To Video"
MUSIC_DIR = ROOT / "Background_Music"
OUTPUT_DIR = ROOT / "outputs"
ROTATION_FILE = ROOT / "content" / "music_rotation.json"
WIDTH, HEIGHT, FPS = 1080, 1920, 30

class TextExtractor(HTMLParser):
    def __init__(self):
        super().__init__()
        self.parts, self.skip = [], 0
    def handle_starttag(self, tag, attrs):
        if tag in {"style", "script"}: self.skip += 1
    def handle_endtag(self, tag):
        if tag in {"style", "script"} and self.skip: self.skip -= 1
    def handle_data(self, data):
        if not self.skip and data.strip(): self.parts.append(data.strip())

def run(command):
    subprocess.run(command, check=True, cwd=ROOT)

def parse_duration(source):
    match = re.search(r"DURATION\s*:\s*(\d+(?:\.\d+)?)\s*s?\b", source, re.I)
    if not match: raise ValueError("HTML header must specify a duration, for example DURATION: 8s")
    duration = float(match.group(1))
    if not 1 <= duration <= 180: raise ValueError(f"Unsupported duration: {duration}s")
    return duration

def visible_text(source):
    parser = TextExtractor()
    parser.feed(source)
    return " ".join(parser.parts)[:5000]

def generate_metadata(api_key, scene_text):
    prompt = ("Create YouTube Shorts metadata for this exact video. Return JSON only with keys caption "
      "and hashtags. Caption: maximum four words, relevant, accurate, and no emoji. Hashtags: exactly "
      "four relevant hashtags, each starting with #, no spaces. Do not promise views or make claims "
      "unsupported by the video.\n\nVideo text: " + scene_text)
    endpoint = "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key=" + urllib.parse.quote(api_key)
    payload = json.dumps({"contents":[{"parts":[{"text":prompt}]}],
                          "generationConfig":{"responseMimeType":"application/json"}}).encode()
    request = urllib.request.Request(endpoint, data=payload, headers={"Content-Type":"application/json"})
    with urllib.request.urlopen(request, timeout=60) as response: data = json.load(response)
    result = json.loads(data["candidates"][0]["content"]["parts"][0]["text"])
    caption = " ".join(str(result.get("caption", "")).split())
    caption = re.sub(r"[#\W]+$", "", caption).strip()
    if not caption or len(caption.split()) > 4: raise ValueError("Gemini caption must be one to four words")
    tags = []
    for item in result.get("hashtags", []):
        tag = "#" + re.sub(r"[^A-Za-z0-9_]", "", str(item).lstrip("#"))
        if tag != "#" and tag.lower() not in {t.lower() for t in tags}: tags.append(tag)
        if len(tags) == 4: break
    if len(tags) < 3: raise ValueError("Gemini must return at least three relevant hashtags")
    return caption, tags

def render_html(source_file, duration, target):
    frame_count = round(duration * FPS)
    frame_dir = OUTPUT_DIR / "frames"
    frame_dir.mkdir(parents=True, exist_ok=True)
    for old in frame_dir.glob("frame-*.png"): old.unlink()
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={"width":WIDTH,"height":HEIGHT}, device_scale_factor=1)
        page.goto(source_file.resolve().as_uri(), wait_until="load")
        page.evaluate("document.fonts.ready")
        page.evaluate("() => document.getAnimations().forEach(a => a.pause())")
        for i in range(frame_count):
            page.evaluate("t => document.getAnimations().forEach(a => { a.currentTime = t; })", i*1000/FPS)
            page.screenshot(path=str(frame_dir/f"frame-{i:06d}.png"), type="png", animations="allow")
        browser.close()
    run(["ffmpeg","-hide_banner","-loglevel","error","-y","-framerate",str(FPS),"-i",
         str(frame_dir/"frame-%06d.png"),"-an","-c:v","libx264","-preset","veryfast",
         "-pix_fmt","yuv420p","-r",str(FPS),"-t",str(duration),str(target)])
    for frame in frame_dir.glob("frame-*.png"): frame.unlink()
    frame_dir.rmdir()

def select_music():
    tracks = sorted(p for p in MUSIC_DIR.iterdir() if p.is_file() and p.suffix.lower() in {".mp3",".m4a",".wav",".aac"})
    if not tracks: raise FileNotFoundError(f"No music tracks in {MUSIC_DIR}")
    history = json.loads(ROTATION_FILE.read_text(encoding="utf-8-sig")) if ROTATION_FILE.exists() else {}
    counts = Counter(history)
    least = min(counts.get(track.name,0) for track in tracks)
    selected = random.choice([t for t in tracks if counts.get(t.name,0) == least])
    history[selected.name] = counts.get(selected.name,0)+1
    ROTATION_FILE.parent.mkdir(parents=True,exist_ok=True)
    ROTATION_FILE.write_text(json.dumps(history,indent=2)+"\n",encoding="utf-8")
    return selected

def add_music(silent, music, final, duration):
    run(["ffmpeg","-hide_banner","-loglevel","error","-y","-i",str(silent),"-stream_loop","-1","-i",str(music),
         "-map","0:v:0","-map","1:a:0","-vf",f"fps={FPS},scale={WIDTH}:{HEIGHT}:force_original_aspect_ratio=decrease,pad={WIDTH}:{HEIGHT}:(ow-iw)/2:(oh-ih)/2",
         "-t",str(duration),"-r",str(FPS),"-c:v","libx264","-preset","veryfast","-pix_fmt","yuv420p",
         "-c:a","aac","-b:a","128k","-af","volume=0.18","-movflags","+faststart",str(final)])

def upload(video, caption, tags):
    credentials = Credentials(None, refresh_token=os.environ["YT_REFRESH_TOKEN"],
      token_uri="https://oauth2.googleapis.com/token", client_id=os.environ["YT_CLIENT_ID"],
      client_secret=os.environ["YT_CLIENT_SECRET"], scopes=["https://www.googleapis.com/auth/youtube.upload"])
    youtube = build("youtube","v3",credentials=credentials)
    result = youtube.videos().insert(part="snippet,status",body={
      "snippet":{"title":caption,"description":caption+"\n\n"+" ".join(tags),
                 "tags":[t[1:] for t in tags],"categoryId":"22"},
      "status":{"privacyStatus":"public","selfDeclaredMadeForKids":False}},
      media_body=MediaFileUpload(str(video),mimetype="video/mp4",resumable=True)).execute()
    return result["id"]

def main():
    if not os.environ.get("GEMINI_API_KEY") or any(not os.environ.get(k) for k in ("YT_CLIENT_ID","YT_CLIENT_SECRET","YT_REFRESH_TOKEN")):
        raise RuntimeError("Set GEMINI_API_KEY and the YT_CLIENT_ID, YT_CLIENT_SECRET, YT_REFRESH_TOKEN secrets")
    candidates = sorted(INPUT_DIR.glob("*.html"))
    if not candidates:
        print("No HTML scenes remain.")
        return
    source = candidates[0]
    markup = source.read_text(encoding="utf-8")
    duration = parse_duration(markup)
    caption, tags = generate_metadata(os.environ["GEMINI_API_KEY"], visible_text(markup))
    OUTPUT_DIR.mkdir(parents=True,exist_ok=True)
    silent = OUTPUT_DIR / (source.stem+"-silent.mp4")
    final = OUTPUT_DIR / (source.stem+".mp4")
    render_html(source,duration,silent)
    add_music(silent,select_music(),final,duration)
    silent.unlink(missing_ok=True)
    video_id = upload(final,caption,tags)
    source.unlink()
    print(f"Uploaded {source.name} as {video_id}; removed source HTML after successful upload.")
    print(f"Caption: {caption}; hashtags: {' '.join(tags)}")

if __name__ == "__main__":
    try: main()
    except Exception as error:
        print(f"Pipeline failed: {error}",file=sys.stderr)
        raise
