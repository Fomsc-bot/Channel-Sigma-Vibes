#!/usr/bin/env python3
"""Render one inline-CSS HTML scene and publish it as a YouTube Short."""
from __future__ import annotations
import json, os, random, re, subprocess, sys, urllib.error, urllib.parse, urllib.request
from collections import Counter
from html.parser import HTMLParser
from pathlib import Path
from google.oauth2.credentials import Credentials
from google import genai
from google.genai import errors as genai_errors
import imageio_ffmpeg
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parent
INPUT_DIR = ROOT / "HTML Files That Needed To Convert To Video"
MUSIC_DIR = ROOT / "Background_Music"
OUTPUT_DIR = ROOT / "outputs"
ROTATION_FILE = ROOT / "content" / "music_rotation.json"
PUBLISH_STATE_FILE = ROOT / "content" / "publish_state.json"
FFMPEG = imageio_ffmpeg.get_ffmpeg_exe()
WIDTH, HEIGHT, FPS = 1080, 1920, 30
LAYOUT_WIDTH, LAYOUT_HEIGHT, DEVICE_SCALE = 540, 960, 2

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

def metadata_prompt(scene_text):
    return (
        "Create accurate, platform-specific metadata for the exact short video described below. "
        "Return a JSON object with exactly these keys: youtube_title, youtube_description, "
        "youtube_keywords, youtube_hashtags, facebook_caption, facebook_hashtags. "
        "YouTube only: identify one focused search phrase that accurately describes the video. "
        "Put it first in youtube_keywords and begin both the title and first description sentence "
        "with that exact phrase. Keep the title under 60 characters, clear and "
        "compelling, using a fitting question, result, contrast, or direct-instruction format. "
        "Do not put hashtags in the title. Write a natural description of 150 to 500 characters: "
        "put the primary keyword in its first sentence, add useful supporting context and one "
        "relevant, non-begging call to action, and do not include hashtags in the description "
        "field. Return 5 to 8 specific YouTube search keywords as plain phrases without #, and "
        "2 to 4 relevant YouTube hashtags as strings starting with #, including a broad topic "
        "and a niche tag. The publisher adds #Shorts to the end of the description. "
        "Facebook Reels: there is no separate title field, so the first line of facebook_caption "
        "must be an accurate, curiosity-driven hook that matches the video; then add one short "
        "context line using natural subject keywords and one soft, relevant call to action. Keep "
        "the caption under 100 words. Return exactly two relevant niche hashtags in "
        "facebook_hashtags, each starting with # and containing no spaces; the publisher adds "
        "one broad Reels hashtag and the reusable #SigmaVibes brand hashtag. "
        "Avoid generic tags such as #viral, #trending, and #foryou, engagement bait, clickbait, "
        "unsupported claims, and promises of views or virality. Do not invent details not present "
        "in the video.\n\nVideo text:\n" + scene_text
    )

def parse_metadata(raw, provider):
    result = json.loads(raw)
    if not isinstance(result, dict):
        raise ValueError(f"{provider} returned metadata that is not a JSON object")

    youtube_title = " ".join(str(result.get("youtube_title", "")).split())
    if not youtube_title or len(youtube_title) > 60:
        raise ValueError(f"{provider} YouTube title must be between 1 and 60 characters")
    if "#" in youtube_title:
        raise ValueError(f"{provider} YouTube title must not contain hashtags")

    youtube_description = " ".join(str(result.get("youtube_description", "")).split())
    if not youtube_description or len(youtube_description) > 5000:
        raise ValueError(f"{provider} YouTube description must be between 1 and 5000 characters")
    if "#" in youtube_description:
        raise ValueError(f"{provider} YouTube description must not contain hashtags in its base text")

    raw_keywords = result.get("youtube_keywords")
    if not isinstance(raw_keywords, list):
        raise ValueError(f"{provider} YouTube keywords must be a JSON array")
    youtube_keywords = []
    for item in raw_keywords:
        keyword = " ".join(str(item).replace("#", "").split()).strip(" ,")
        if keyword and keyword.casefold() not in {tag.casefold() for tag in youtube_keywords}:
            youtube_keywords.append(keyword[:100])
        if len(youtube_keywords) == 8:
            break
    if not 5 <= len(youtube_keywords) <= 8:
        raise ValueError(f"{provider} must return five to eight unique YouTube keywords")
    primary_keyword = youtube_keywords[0]
    if not youtube_title.casefold().startswith(primary_keyword.casefold()):
        raise ValueError(f"{provider} YouTube title must begin with its primary search keyword")

    raw_youtube_hashtags = result.get("youtube_hashtags")
    if not isinstance(raw_youtube_hashtags, list):
        raise ValueError(f"{provider} YouTube hashtags must be a JSON array")
    youtube_hashtags = []
    for item in raw_youtube_hashtags:
        tag = "#" + re.sub(r"[^A-Za-z0-9_]", "", str(item).lstrip("#"))[:28]
        if (tag != "#" and tag.casefold() != "#shorts"
                and tag.casefold() not in {existing.casefold() for existing in youtube_hashtags}):
            youtube_hashtags.append(tag)
        if len(youtube_hashtags) == 4:
            break
    if not 2 <= len(youtube_hashtags) <= 4:
        raise ValueError(f"{provider} must return two to four unique YouTube topic hashtags")
    youtube_description += "\n\n" + " ".join(youtube_hashtags + ["#Shorts"])
    if not 150 <= len(youtube_description) <= 500:
        raise ValueError(
            f"{provider} YouTube description with hashtags must be between 150 and 500 characters"
        )

    facebook_caption = str(result.get("facebook_caption", "")).strip()
    facebook_caption = "\n".join(
        " ".join(line.split()) for line in facebook_caption.splitlines() if line.strip()
    )
    if not facebook_caption or len(facebook_caption.split()) > 100:
        raise ValueError(f"{provider} Facebook caption must be between 1 and 100 words")

    if not youtube_description.casefold().startswith(primary_keyword.casefold()):
        raise ValueError(f"{provider} YouTube description must begin with its primary search keyword")

    raw_hashtags = result.get("facebook_hashtags")
    if not isinstance(raw_hashtags, list):
        raise ValueError(f"{provider} Facebook hashtags must be a JSON array")
    facebook_hashtags = []
    for item in raw_hashtags:
        tag = "#" + re.sub(r"[^A-Za-z0-9_]", "", str(item).lstrip("#"))[:28]
        if (tag != "#" and tag.casefold() not in {
            "#viral", "#trending", "#foryou", "#shorts", "#fbreels",
            "#facebookreels", "#sigmavibes",
        } and tag.casefold() not in {existing.casefold() for existing in facebook_hashtags}):
            facebook_hashtags.append(tag)
        if len(facebook_hashtags) == 2:
            break
    if len(facebook_hashtags) != 2:
        raise ValueError(f"{provider} must return exactly two relevant Facebook niche hashtags")

    return {
        "youtube_title": youtube_title,
        "youtube_description": youtube_description,
        "youtube_keywords": youtube_keywords,
        "youtube_hashtags": youtube_hashtags + ["#Shorts"],
        "facebook_caption": facebook_caption,
        "facebook_hashtags": facebook_hashtags,
    }

def generate_with_gemini(api_key, prompt):
    model_name = os.environ.get("GEMINI_MODEL", "gemini-3.8-flash")
    fallback_model = os.environ.get("GEMINI_FALLBACK_MODEL") or "gemini-3.6-flash"
    try:
        client = genai.Client(api_key=api_key)
        try:
            response = client.models.generate_content(
                model=model_name,
                contents=prompt,
                config={"response_mime_type": "application/json"},
            )
        except genai_errors.APIError as error:
            if error.code != 503 or fallback_model == model_name:
                raise
            response = client.models.generate_content(
                model=fallback_model,
                contents=prompt,
                config={"response_mime_type": "application/json"},
            )
            model_name = fallback_model
    except Exception as error:
        raise RuntimeError(f"Gemini API request failed for {model_name}: {error}") from error
    if not response.text:
        raise RuntimeError(f"Gemini returned no metadata for {model_name}")
    return parse_metadata(response.text, "Gemini")

def generate_metadata(gemini_key, scene_text):
    if not gemini_key:
        raise RuntimeError("Set GEMINI_API_KEY for metadata generation")
    return generate_with_gemini(gemini_key, metadata_prompt(scene_text))

def render_html(source_file, duration, target):
    frame_count = round(duration * FPS)
    frame_dir = OUTPUT_DIR / "frames"
    frame_dir.mkdir(parents=True, exist_ok=True)
    for old in frame_dir.glob("frame-*.png"): old.unlink()
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(
            viewport={"width": LAYOUT_WIDTH, "height": LAYOUT_HEIGHT},
            device_scale_factor=DEVICE_SCALE,
        )
        page.goto(source_file.resolve().as_uri(), wait_until="load")
        page.evaluate("document.fonts.ready")
        page.evaluate("() => document.getAnimations().forEach(a => a.pause())")
        for i in range(frame_count):
            page.evaluate("t => document.getAnimations().forEach(a => { a.currentTime = t; })", i*1000/FPS)
            page.screenshot(
                path=str(frame_dir/f"frame-{i:06d}.png"),
                type="png",
                scale="device",
                animations="allow",
            )
        browser.close()
    run([FFMPEG,"-hide_banner","-loglevel","error","-y","-framerate",str(FPS),"-i",
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
    run([FFMPEG,"-hide_banner","-loglevel","error","-y","-i",str(silent),"-stream_loop","-1","-i",str(music),
         "-map","0:v:0","-map","1:a:0","-vf",f"fps={FPS},scale={WIDTH}:{HEIGHT}:force_original_aspect_ratio=decrease,pad={WIDTH}:{HEIGHT}:(ow-iw)/2:(oh-ih)/2",
         "-t",str(duration),"-r",str(FPS),"-c:v","libx264","-preset","veryfast","-pix_fmt","yuv420p",
         "-c:a","aac","-b:a","128k","-af","volume=0.18","-movflags","+faststart",str(final)])

def upload_youtube(video, metadata):
    credentials = Credentials(None, refresh_token=os.environ["YT_REFRESH_TOKEN"],
      token_uri="https://oauth2.googleapis.com/token", client_id=os.environ["YT_CLIENT_ID"],
      client_secret=os.environ["YT_CLIENT_SECRET"], scopes=["https://www.googleapis.com/auth/youtube.upload"])
    youtube = build("youtube","v3",credentials=credentials)
    result = youtube.videos().insert(part="snippet,status",body={
      "snippet":{"title":metadata["youtube_title"],
                 "description":metadata["youtube_description"],
                 "tags":metadata["youtube_keywords"],"categoryId":"22"},
      "status":{"privacyStatus":"public","selfDeclaredMadeForKids":False}},
      media_body=MediaFileUpload(str(video),mimetype="video/mp4",resumable=True)).execute()
    return result["id"]

def upload_facebook_reel(video, metadata):
    """Upload and publish a Reel to the configured Facebook Page."""
    page_id = os.environ["FB_PAGE_ID"]
    token = os.environ["FB_PAGE_ACCESS_TOKEN"]
    version = os.environ.get("FB_GRAPH_API_VERSION", "v26.0")
    api_root = f"https://graph.facebook.com/{version}"

    def post_form(url, fields):
        body = urllib.parse.urlencode(fields).encode()
        request = urllib.request.Request(url, data=body, headers={
            "Content-Type": "application/x-www-form-urlencoded",
        })
        try:
            with urllib.request.urlopen(request, timeout=90) as response:
                return json.load(response)
        except urllib.error.HTTPError as error:
            details = error.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"Facebook API returned HTTP {error.code}: {details}") from error

    start = post_form(f"{api_root}/{page_id}/video_reels", {
        "upload_phase": "start", "access_token": token,
    })
    video_id = start.get("video_id")
    upload_url = start.get("upload_url")
    if not video_id or not upload_url:
        raise RuntimeError(f"Facebook Reel upload start returned an incomplete response: {start}")

    file_size = video.stat().st_size
    upload_request = urllib.request.Request(upload_url, data=video.read_bytes(), headers={
        "Authorization": f"OAuth {token}",
        "offset": "0",
        "file_size": str(file_size),
        "Content-Type": "application/octet-stream",
    })
    try:
        with urllib.request.urlopen(upload_request, timeout=300) as response:
            uploaded = json.load(response)
    except urllib.error.HTTPError as error:
        details = error.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"Facebook Reel upload returned HTTP {error.code}: {details}") from error
    if uploaded.get("success") is not True:
        raise RuntimeError(f"Facebook Reel upload was not confirmed: {uploaded}")

    facebook_tags = ["#fbreels"] + metadata["facebook_hashtags"] + ["#SigmaVibes"]
    facebook_caption = metadata["facebook_caption"] + "\n\n" + " ".join(facebook_tags)
    facebook_title = metadata["facebook_caption"].splitlines()[0][:100]

    finished = post_form(f"{api_root}/{page_id}/video_reels", {
        "upload_phase": "finish",
        "video_id": video_id,
        "video_state": "PUBLISHED",
        "title": facebook_title,
        "description": facebook_caption,
        "access_token": token,
    })
    if finished.get("success") is not True:
        raise RuntimeError(f"Facebook did not confirm publishing the Reel: {finished}")
    return video_id

def load_publish_state():
    if not PUBLISH_STATE_FILE.exists():
        return {}
    return json.loads(PUBLISH_STATE_FILE.read_text(encoding="utf-8-sig"))

def save_publish_state(state):
    PUBLISH_STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    PUBLISH_STATE_FILE.write_text(json.dumps(state, indent=2) + "\n", encoding="utf-8")

def main():
    if not os.environ.get("GEMINI_API_KEY"):
        raise RuntimeError("Set GEMINI_API_KEY for metadata generation")
    required = ("YT_CLIENT_ID", "YT_CLIENT_SECRET", "YT_REFRESH_TOKEN", "FB_PAGE_ID", "FB_PAGE_ACCESS_TOKEN")
    missing = [key for key in required if not os.environ.get(key)]
    if missing:
        raise RuntimeError("Set these GitHub secrets before running: " + ", ".join(missing))
    candidates = sorted(INPUT_DIR.glob("*.html"))
    if not candidates:
        print("No HTML scenes remain.")
        return
    source = candidates[0]
    markup = source.read_text(encoding="utf-8")
    duration = parse_duration(markup)
    scene_text = visible_text(markup)
    state = load_publish_state()
    delivery = state.setdefault(source.name, {})
    metadata = generate_metadata(os.environ.get("GEMINI_API_KEY"), scene_text)
    OUTPUT_DIR.mkdir(parents=True,exist_ok=True)
    silent = OUTPUT_DIR / (source.stem+"-silent.mp4")
    final = OUTPUT_DIR / (source.stem+".mp4")
    render_html(source,duration,silent)
    add_music(silent,select_music(),final,duration)
    silent.unlink(missing_ok=True)
    if not delivery.get("youtube_video_id"):
        delivery["youtube_video_id"] = upload_youtube(final, metadata)
        save_publish_state(state)
    if not delivery.get("facebook_reel_id"):
        delivery["facebook_reel_id"] = upload_facebook_reel(final, metadata)
        save_publish_state(state)
    source.unlink()
    youtube_id, facebook_id = delivery["youtube_video_id"], delivery["facebook_reel_id"]
    state.pop(source.name, None)
    save_publish_state(state)
    print(f"Published {source.name} to YouTube ({youtube_id}) and Facebook ({facebook_id}); removed source HTML.")
    print(f"YouTube title: {metadata['youtube_title']}")
    print(f"Facebook hook: {metadata['facebook_caption'].splitlines()[0]}")

if __name__ == "__main__":
    try: main()
    except Exception as error:
        print(f"Pipeline failed: {error}",file=sys.stderr)
        raise
