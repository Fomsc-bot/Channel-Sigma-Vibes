#!/usr/bin/env python3
"""Render and publish one motivational quote image to the configured Facebook Page."""
from __future__ import annotations

import json
import os
import re
import secrets
import sys
import tempfile
import urllib.error
import urllib.parse
import urllib.request
from html.parser import HTMLParser
from pathlib import Path

from google import genai
from google.genai import errors as genai_errors
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parent
INPUT_DIR = ROOT / "HTML Files That Needed To Convert To picures and upload to fb"
WIDTH, HEIGHT, DEVICE_SCALE = 1080, 1920, 2


class TextExtractor(HTMLParser):
    def __init__(self):
        super().__init__()
        self.parts, self.skip = [], 0

    def handle_starttag(self, tag, attrs):
        if tag in {"style", "script"}:
            self.skip += 1

    def handle_endtag(self, tag):
        if tag in {"style", "script"} and self.skip:
            self.skip -= 1

    def handle_data(self, data):
        if not self.skip and data.strip():
            self.parts.append(data.strip())


def visible_text(source):
    parser = TextExtractor()
    parser.feed(source)
    return " ".join(parser.parts)[:5000]


def metadata_prompt(image_text):
    return (
        "Create accurate Facebook Page photo-post metadata for this motivational quote image. "
        "Return JSON only with exactly these keys: title, caption, keywords, hashtags, alt_text. "
        "Use the quote and author shown in the image; do not invent or misattribute a quote. "
        "Title: a concise, emotionally resonant hook that accurately reflects the quote, with no "
        "hashtags. Caption: 10 to 30 words in one or two natural sentences, positive and relatable; "
        "include the primary topic keyword naturally and end with a genuine question or gentle "
        "invitation to share. Avoid begging for reactions, engagement bait, clickbait, and promises "
        "of reach. Keywords: an array of 3 to 5 short, relevant search phrases. Hashtags: exactly "
        "two relevant topic hashtags, each beginning with # and containing no spaces; the publisher "
        "adds #Motivation and the reusable #SigmaVibes brand tag. Avoid #viral, #trending, and "
        "#foryou. Alt_text: a concise, factual description of the image including its quote and "
        "visible attribution. Keep the caption keywords natural rather than stuffing a keyword list.\n\n"
        "Visible image text:\n" + image_text
    )


def parse_metadata(raw):
    result = json.loads(raw)
    if not isinstance(result, dict):
        raise ValueError("Gemini returned metadata that is not a JSON object")

    title = " ".join(str(result.get("title", "")).split())
    if not title or len(title) > 100 or "#" in title:
        raise ValueError("Gemini Facebook post title must be 1 to 100 characters without hashtags")

    caption = " ".join(str(result.get("caption", "")).split())
    if not 10 <= len(caption.split()) <= 30:
        raise ValueError("Gemini Facebook caption must be between 10 and 30 words")

    raw_keywords = result.get("keywords")
    if not isinstance(raw_keywords, list):
        raise ValueError("Gemini Facebook keywords must be a JSON array")
    keywords = []
    for item in raw_keywords:
        keyword = " ".join(str(item).replace("#", "").split()).strip(" ,")
        if keyword and keyword.casefold() not in {existing.casefold() for existing in keywords}:
            keywords.append(keyword[:80])
        if len(keywords) == 5:
            break
    if not 3 <= len(keywords) <= 5:
        raise ValueError("Gemini must return three to five unique Facebook keywords")
    if keywords[0].casefold() not in caption.casefold():
        raise ValueError("Facebook caption must naturally include its primary keyword")

    raw_hashtags = result.get("hashtags")
    if not isinstance(raw_hashtags, list):
        raise ValueError("Gemini Facebook hashtags must be a JSON array")
    hashtags = []
    for item in raw_hashtags:
        tag = "#" + re.sub(r"[^A-Za-z0-9_]", "", str(item).lstrip("#"))[:28]
        if (tag != "#" and tag.casefold() not in {
            "#viral", "#trending", "#foryou", "#motivation", "#sigmavibes",
        } and tag.casefold() not in {existing.casefold() for existing in hashtags}):
            hashtags.append(tag)
        if len(hashtags) == 2:
            break
    if len(hashtags) != 2:
        raise ValueError("Gemini must return exactly two relevant Facebook topic hashtags")

    alt_text = " ".join(str(result.get("alt_text", "")).split())
    if not alt_text or len(alt_text) > 1000:
        raise ValueError("Gemini Facebook alt text must be between 1 and 1000 characters")

    return {
        "title": title,
        "caption": caption,
        "keywords": keywords,
        "hashtags": ["#Motivation"] + hashtags + ["#SigmaVibes"],
        "alt_text": alt_text,
    }


def generate_metadata(api_key, image_text):
    if not api_key:
        raise RuntimeError("Set GEMINI_API_KEY for Facebook post metadata generation")

    model_name = os.environ.get("GEMINI_MODEL", "gemini-3.8-flash")
    fallback_model = os.environ.get("GEMINI_FALLBACK_MODEL") or "gemini-3.6-flash"
    client = genai.Client(api_key=api_key)

    def request(model):
        response = client.models.generate_content(
            model=model,
            contents=metadata_prompt(image_text),
            config={"response_mime_type": "application/json"},
        )
        if not response.text:
            raise RuntimeError(f"Gemini returned no metadata for {model}")
        return parse_metadata(response.text)

    active_model = model_name
    try:
        try:
            return request(model_name)
        except genai_errors.APIError as error:
            if error.code != 503 or fallback_model == model_name:
                raise
            print(f"Gemini {model_name} is unavailable; trying {fallback_model}.", file=sys.stderr)
            active_model = fallback_model
            return request(active_model)
    except Exception as error:
        raise RuntimeError(f"Gemini metadata request failed for {active_model}: {error}") from error


def render_image(source_file, target):
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        try:
            page = browser.new_page(
                viewport={"width": WIDTH, "height": HEIGHT},
                device_scale_factor=DEVICE_SCALE,
            )
            page.goto(source_file.resolve().as_uri(), wait_until="load")
            page.evaluate("document.fonts.ready")
            page.screenshot(path=str(target), type="png", full_page=False)
        finally:
            browser.close()


def facebook_multipart_fields(fields, image):
    boundary = "----SigmaVibesFacebookImageUpload" + secrets.token_hex(16)
    body = bytearray()
    for name, value in fields.items():
        body.extend(f"--{boundary}\r\n".encode())
        body.extend(f'Content-Disposition: form-data; name="{name}"\r\n\r\n'.encode())
        body.extend(str(value).encode("utf-8"))
        body.extend(b"\r\n")
    body.extend(f"--{boundary}\r\n".encode())
    body.extend(
        'Content-Disposition: form-data; name="source"; filename="quote.png"\r\n'.encode()
    )
    body.extend(b"Content-Type: image/png\r\n\r\n")
    body.extend(image.read_bytes())
    body.extend(f"\r\n--{boundary}--\r\n".encode())
    return boundary, bytes(body)


def upload_facebook_photo(image, metadata):
    page_id = os.environ["FB_PAGE_ID"]
    token = os.environ["FB_PAGE_ACCESS_TOKEN"]
    version = os.environ.get("FB_GRAPH_API_VERSION", "v26.0")
    caption = (
        metadata["title"] + "\n\n" + metadata["caption"] + "\n\n"
        + " ".join(metadata["hashtags"])
    )
    fields = {
        "published": "true",
        "caption": caption,
        "alt_text_custom": metadata["alt_text"],
        "access_token": token,
    }
    boundary, body = facebook_multipart_fields(fields, image)
    request = urllib.request.Request(
        f"https://graph.facebook.com/{version}/{page_id}/photos",
        data=body,
        headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
    )
    try:
        with urllib.request.urlopen(request, timeout=300) as response:
            result = json.load(response)
    except urllib.error.HTTPError as error:
        details = error.read().decode("utf-8", errors="replace").replace(token, "[REDACTED]")
        raise RuntimeError(f"Facebook photo upload returned HTTP {error.code}: {details}") from error
    except urllib.error.URLError as error:
        raise RuntimeError(f"Facebook photo upload failed: {error.reason}") from error

    photo_id = result.get("id")
    if not photo_id:
        raise RuntimeError(f"Facebook photo upload returned an incomplete response: {result}")
    return result.get("post_id") or photo_id


def main():
    required = ("GEMINI_API_KEY", "FB_PAGE_ID", "FB_PAGE_ACCESS_TOKEN")
    missing = [key for key in required if not os.environ.get(key)]
    if missing:
        raise RuntimeError("Set these GitHub secrets before running: " + ", ".join(missing))

    candidates = sorted(INPUT_DIR.glob("*.html"))
    if not candidates:
        print("No Facebook quote HTML files remain.")
        return

    source = candidates[0]
    source_text = source.read_text(encoding="utf-8")
    metadata = generate_metadata(os.environ["GEMINI_API_KEY"], visible_text(source_text))
    with tempfile.TemporaryDirectory(prefix="sigma-fb-quote-") as temp_dir:
        image = Path(temp_dir) / f"{source.stem}.png"
        render_image(source, image)
        post_id = upload_facebook_photo(image, metadata)

    source.unlink()
    print(f"Published {source.name} to Facebook ({post_id}); removed source HTML.")
    print(f"Facebook post hook: {metadata['title']}")


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        print(f"Facebook quote image pipeline failed: {error}", file=sys.stderr)
        raise
