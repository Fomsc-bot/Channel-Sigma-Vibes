#!/usr/bin/env python3
"""Render one inline-CSS HTML scene and publish it as a YouTube Short."""
from __future__ import annotations
import json, os, random, re, subprocess, sys, time, urllib.error, urllib.parse, urllib.request
from collections import Counter
from html.parser import HTMLParser
from pathlib import Path
from google.oauth2.credentials import Credentials
from groq import Groq
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
    return ("Create YouTube Shorts metadata for this exact video. Return JSON only with keys caption "
      "and hashtags, where hashtags is a JSON array of exactly three strings. Caption: maximum four "
      "words, relevant, accurate, and no emoji. Hashtags: relevant topic hashtags, each starting with # "
      "and containing no spaces. Do not include #Shorts because "
      "it is added automatically. Do not promise views or make claims unsupported by the video."
      "\n\nVideo text: " + scene_text)

def parse_metadata(raw, provider):
    result = json.loads(raw)
    if not isinstance(result, dict):
        raise ValueError(f"{provider} returned metadata that is not a JSON object")
    caption = " ".join(str(result.get("caption", "")).split())
    caption = re.sub(r"[#\W]+$", "", caption).strip()
    if not caption or len(caption.split()) > 4:
        raise ValueError(f"{provider} caption must be one to four words")
    raw_tags = result.get("hashtags", [])
    if isinstance(raw_tags, str):
        raw_tags = re.findall(r"#?[A-Za-z0-9_]+", raw_tags)
    elif not isinstance(raw_tags, list):
        raise ValueError(f"{provider} hashtags must be a JSON array or a string")
    topic_tags = []
    for item in raw_tags:
        tag = "#" + re.sub(r"[^A-Za-z0-9_]", "", str(item).lstrip("#"))[:28]
        if tag != "#" and tag.lower() != "#shorts" and tag.lower() not in {t.lower() for t in topic_tags}:
            topic_tags.append(tag)
        if len(topic_tags) == 3:
            break
    tags = ["#shorts"]
    for tag in topic_tags + ["#Motivation", "#Mindset", "#Sigma"]:
        if tag.lower() not in {t.lower() for t in tags}:
            tags.append(tag)
        if len(tags) == 4:
            break
    return caption, tags

def related_emoji(scene_text, caption):
    text = (scene_text + " " + caption).casefold()
    choices = [
        (("self-love", "self love", "love", "kindness", "compassion", "heart"), "\U0001F49B"),
        (("courage", "fear", "brave", "bold", "fearless"), "\U0001F981"),
        (("mindset", "wisdom", "think", "thought", "philosophy", "mind"), "\U0001F9E0"),
        (("discipline", "success", "focus", "goal", "action", "habit", "motivation"), "\U000026A1"),
        (("growth", "healing", "heal", "change", "begin", "start"), "\U0001F331"),
    ]
    for keywords, emoji in choices:
        if any(keyword in text for keyword in keywords):
            return emoji
    return "\U00002728"

def build_title(caption, emoji, tags):
    selected_tags = list(tags)
    title = f"{caption} {emoji} {' '.join(selected_tags)}"
    while len(title) > 100 and len(selected_tags) > 1:
        selected_tags.pop()
        title = f"{caption} {emoji} {' '.join(selected_tags)}"
    if len(title) > 100:
        suffix = f" {emoji} {' '.join(selected_tags)}"
        caption = caption[:max(1, 100 - len(suffix))].rstrip()
        title = caption + suffix
    return title

def generate_with_gemini(api_key, prompt):
    model_name = os.environ.get("GEMINI_MODEL", "gemini-3.8-flash")
    endpoint = f"https://generativelanguage.googleapis.com/v1beta/models/{model_name}:generateContent"
    payload = json.dumps({"contents":[{"parts":[{"text":prompt}]}],
                          "generationConfig":{"responseMimeType":"application/json"}}).encode()
    request = urllib.request.Request(endpoint, data=payload, headers={
        "Content-Type": "application/json",
        "x-goog-api-key": api_key,
    })
    for attempt in range(3):
        try:
            with urllib.request.urlopen(request, timeout=90) as response:
                data = json.load(response)
            break
        except urllib.error.HTTPError as error:
            details = error.read().decode("utf-8", errors="replace")
            retryable = error.code == 429 or error.code >= 500
            if not retryable or attempt == 2:
                raise RuntimeError(f"Gemini API returned HTTP {error.code} for {model_name}: {details}") from error
            time.sleep(3 * (2 ** attempt))
        except (TimeoutError, urllib.error.URLError) as error:
            if attempt == 2:
                raise RuntimeError(f"Gemini timed out after three attempts for {model_name}: {error}") from error
            time.sleep(3 * (2 ** attempt))
    raw = data["candidates"][0]["content"]["parts"][0]["text"]
    return parse_metadata(raw, "Gemini")

def generate_with_groq(api_key, prompt):
    model_name = os.environ.get("GROQ_MODEL", "openai/gpt-oss-20b")
    try:
        client = Groq(api_key=api_key, timeout=90.0, max_retries=2)
        response = client.chat.completions.create(
            model=model_name,
            messages=[{"role": "user", "content": prompt}],
            response_format={"type": "json_object"},
        )
    except Exception as error:
        details = str(error)
        if "1010" in details:
            raise RuntimeError(
                "Groq returned Cloudflare error 1010, which blocks this client signature. "
                "The official Groq client is configured; contact Groq support if it persists. "
                + details
            ) from error
        raise RuntimeError(f"Groq API request failed for {model_name}: {details}") from error
    return parse_metadata(response.choices[0].message.content, "Groq")

def generate_metadata(gemini_key, groq_key, scene_text):
    prompt = metadata_prompt(scene_text)
    failures = []
    if gemini_key:
        try:
            return generate_with_gemini(gemini_key, prompt)
        except Exception as error:
            failures.append(f"Gemini: {error}")
            print(f"Gemini metadata request failed; trying Groq fallback. {error}", file=sys.stderr)
    if groq_key:
        try:
            return generate_with_groq(groq_key, prompt)
        except Exception as error:
            failures.append(f"Groq: {error}")
    if not failures:
        raise RuntimeError("Set GEMINI_API_KEY or GROQ_API_KEY for caption and hashtag generation")
    raise RuntimeError("No metadata provider succeeded. " + " | ".join(failures))

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

def upload_youtube(video, caption, emoji, tags):
    credentials = Credentials(None, refresh_token=os.environ["YT_REFRESH_TOKEN"],
      token_uri="https://oauth2.googleapis.com/token", client_id=os.environ["YT_CLIENT_ID"],
      client_secret=os.environ["YT_CLIENT_SECRET"], scopes=["https://www.googleapis.com/auth/youtube.upload"])
    youtube = build("youtube","v3",credentials=credentials)
    result = youtube.videos().insert(part="snippet,status",body={
      "snippet":{"title":build_title(caption, emoji, tags),"description":caption+"\n\n"+" ".join(tags),
                 "tags":[t[1:] for t in tags],"categoryId":"22"},
      "status":{"privacyStatus":"public","selfDeclaredMadeForKids":False}},
      media_body=MediaFileUpload(str(video),mimetype="video/mp4",resumable=True)).execute()
    return result["id"]

def upload_facebook_reel(video, caption, emoji, tags):
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

    facebook_tags = []
    for tag in tags:
        if tag.casefold() not in {"#sigma", "#sigmamale"} and tag.casefold() not in {
            existing.casefold() for existing in facebook_tags
        }:
            facebook_tags.append(tag)
    facebook_tags.extend(["#sigma", "#Sigmamale"])

    finished = post_form(f"{api_root}/{page_id}/video_reels", {
        "upload_phase": "finish",
        "video_id": video_id,
        "video_state": "PUBLISHED",
        "title": build_title(caption, emoji, tags),
        "description": caption + "\n\n" + " ".join(facebook_tags),
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
    if not (os.environ.get("GEMINI_API_KEY") or os.environ.get("GROQ_API_KEY")):
        raise RuntimeError("Set GEMINI_API_KEY or GROQ_API_KEY for metadata generation")
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
    caption, tags = generate_metadata(os.environ.get("GEMINI_API_KEY"), os.environ.get("GROQ_API_KEY"), scene_text)
    emoji = related_emoji(scene_text, caption)
    OUTPUT_DIR.mkdir(parents=True,exist_ok=True)
    silent = OUTPUT_DIR / (source.stem+"-silent.mp4")
    final = OUTPUT_DIR / (source.stem+".mp4")
    render_html(source,duration,silent)
    add_music(silent,select_music(),final,duration)
    silent.unlink(missing_ok=True)
    if not delivery.get("youtube_video_id"):
        delivery["youtube_video_id"] = upload_youtube(final, caption, emoji, tags)
        save_publish_state(state)
    if not delivery.get("facebook_reel_id"):
        delivery["facebook_reel_id"] = upload_facebook_reel(final, caption, emoji, tags)
        save_publish_state(state)
    source.unlink()
    youtube_id, facebook_id = delivery["youtube_video_id"], delivery["facebook_reel_id"]
    state.pop(source.name, None)
    save_publish_state(state)
    print(f"Published {source.name} to YouTube ({youtube_id}) and Facebook ({facebook_id}); removed source HTML.")
    print(f"Title: {build_title(caption, emoji, tags)}")

if __name__ == "__main__":
    try: main()
    except Exception as error:
        print(f"Pipeline failed: {error}",file=sys.stderr)
        raise
