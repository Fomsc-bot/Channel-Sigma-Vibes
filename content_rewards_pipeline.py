#!/usr/bin/env python3
"""Campaign-driven Content Rewards video creation and submission."""
from __future__ import annotations

import base64
import html
import json
import os
import re
import subprocess
import sys
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

from google import genai
from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
from playwright.sync_api import sync_playwright
import imageio_ffmpeg

import html_short_pipeline as youtube_uploader

ROOT = Path(__file__).resolve().parent
STATE_FILE = ROOT / "content" / "content_rewards_delivery.json"
MEDIA_DIR = ROOT / "outputs" / "content_rewards"
FFMPEG = imageio_ffmpeg.get_ffmpeg_exe()
CAMPAIGNS_URL = os.environ.get("CR_CAMPAIGNS_URL") or "https://contentrewards.com/c/campaigns"
DRAFTS_URL = os.environ.get("CR_DRAFTS_URL") or "https://contentrewards.com/c/drafts"


def save_state(state: dict) -> None:
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    STATE_FILE.write_text(json.dumps(state, indent=2) + "\n", encoding="utf-8")


def read_state() -> dict:
    if not STATE_FILE.exists():
        return {}
    return json.loads(STATE_FILE.read_text(encoding="utf-8-sig"))


def session_file() -> str:
    encoded = os.environ.get("CR_STORAGE_STATE_B64", "").strip()
    if not encoded:
        raise RuntimeError("Set GitHub secret CR_STORAGE_STATE_B64 to your Content Rewards Playwright session")
    try:
        raw = base64.b64decode(encoded, validate=True)
        state = json.loads(raw)
    except Exception as exc:
        raise RuntimeError("CR_STORAGE_STATE_B64 must be base64-encoded Playwright storage-state JSON") from exc
    if not isinstance(state, dict) or not isinstance(state.get("cookies"), list):
        raise RuntimeError("The saved Content Rewards session has no cookies array")
    handle = tempfile.NamedTemporaryFile(prefix="cr-session-", suffix=".json", delete=False)
    handle.write(raw)
    handle.close()
    return handle.name


def campaign_candidates(page) -> list[dict]:
    page.goto(CAMPAIGNS_URL, wait_until="domcontentloaded", timeout=60_000)
    page.wait_for_timeout(1500)
    if any(term in page.url.lower() for term in ("login", "sign-in", "auth")):
        raise RuntimeError("Content Rewards session expired; refresh CR_STORAGE_STATE_B64")

    links = page.locator("a[href]")
    urls: list[str] = []
    for index in range(min(links.count(), 600)):
        href = links.nth(index).get_attribute("href") or ""
        if re.search(r"/c/campaigns?/[^/?#]+", href):
            full = page.evaluate("u => new URL(u, location.href).href", href)
            if full not in urls:
                urls.append(full)
    if not urls:
        raise RuntimeError("No campaign detail links found; check CR_CAMPAIGNS_URL and your session")

    candidates = []
    for url in urls[:40]:
        page.goto(url, wait_until="domcontentloaded", timeout=60_000)
        page.wait_for_timeout(500)
        body = page.locator("body")
        try:
            body.locator(":scope").wait_for(state="visible", timeout=5_000)
        except PlaywrightTimeoutError:
            continue
        text = body.inner_text(timeout=10_000)
        labels = body.evaluate(
            "n => [...n.querySelectorAll('[aria-label],[title],img[alt]')]"
            ".map(e=>e.getAttribute('aria-label')||e.getAttribute('title')||e.getAttribute('alt'))"
            ".filter(Boolean).join(' ')"
        )
        text += "\n" + labels
        if not re.search(r"youtube", text, re.I):
            continue

        submit = page.get_by_role("button", name=re.compile(r"^submit clip$", re.I))
        if submit.count() == 0:
            submit = page.get_by_role("link", name=re.compile(r"^submit clip$", re.I))
        join = page.get_by_role("button", name=re.compile(r"^join campaign$", re.I))
        if join.count() == 0:
            join = page.get_by_role("link", name=re.compile(r"^join campaign$", re.I))
        action = "submit" if submit.count() else "join" if join.count() else ""
        if not action:
            # Application-only campaigns need creator-specific answers and brand approval.
            continue

        sources = page.locator("a[href]").evaluate_all(
            "els=>els.map(a=>({url:a.href,label:(a.innerText||a.title||'').trim()}))"
        )
        sources += page.locator("iframe[src],video[src]").evaluate_all(
            "els=>els.map(e=>({url:e.src,label:e.title||'embedded media'}))"
        )
        media_links = []
        for item in sources:
            href = str(item.get("url", ""))
            if re.search(r"youtube\.com|youtu\.be|\.(mp4|mov|webm)(?:\?|$)", href, re.I):
                media_links.append({"url": href, "label": str(item.get("label", ""))[:200]})
        title = page.locator("h1").first.inner_text() if page.locator("h1").count() else text.splitlines()[0][:150]
        candidates.append({
            "url": page.url,
            "title": title.strip(),
            "brief": text[:10_000],
            "action": action,
            "sources": media_links[:25],
        })
    return candidates


def plan_campaign(campaigns: list[dict]) -> dict:
    if not campaigns:
        raise RuntimeError("No eligible YouTube campaign found. Join or receive approval for a campaign first.")
    key = os.environ.get("GEMINI_API_KEY")
    if not key:
        raise RuntimeError("Set GEMINI_API_KEY for campaign selection and creative generation")
    prompt = """Act as a careful short-form producer. Choose the best-fit campaign from the supplied campaign pages, then create a campaign-specific production plan. Read the full brief and distinguish required source clipping from original creative. Use source_clip only when the rules require clipping supplied source content, and only choose an exact public YouTube or direct video URL listed for that campaign. Use original_ai for original promotional/UGC-style concepts only when the brief allows it or does not restrict footage origin. Never fabricate product facts, personal experience, endorsements, discounts, or results. Reject briefs needing a real person's testimonial, physical product handling, unavailable brand assets, or an unsupported duration. The output must satisfy every requirement listed in `requirements`; if none of the campaigns can be fulfilled, return fit=false and explain why.

Return one JSON object only with: fit (boolean), campaign_url (exact candidate URL), reason, creation_mode (original_ai or source_clip), source_url (empty for original_ai), duration_seconds (3-15 whole seconds, within campaign requirements), video_prompt (specific vertical video prompt with hook, sequence, camera, setting, sound, and no gibberish text), on_screen_text (array of exact text to composite, empty if none), youtube_title (max 100 chars), youtube_description (truthful, campaign compliant), youtube_keywords (5-8 plain phrases), youtube_hashtags (2-4 tags with #), requirements (array of mandatory rules the plan satisfies). For source_clip, describe a genuine excerpt, don't add invented narration, and choose the provided source URL. Avoid claims not supported by the campaign brief.

Campaigns:\n""" + json.dumps(campaigns[:40], ensure_ascii=False)
    model = os.environ.get("GEMINI_MODEL", "gemini-3.8-flash")
    fallback = os.environ.get("GEMINI_FALLBACK_MODEL") or "gemini-3.6-flash"
    response, _ = youtube_uploader.generate_content_with_fallback(
        key, model, fallback, prompt, {"response_mime_type": "application/json"}
    )
    plan = json.loads(response.text or "{}")
    if plan.get("fit") is not True:
        raise RuntimeError("No compliant campaign can be fulfilled: " + str(plan.get("reason", "no safe fit")))
    campaign = next((c for c in campaigns if c["url"] == plan.get("campaign_url")), None)
    if not campaign:
        raise RuntimeError("Campaign planner returned a URL outside the discovered campaigns")
    if plan.get("creation_mode") not in {"original_ai", "source_clip"}:
        raise RuntimeError("Campaign planner returned an unsupported creation mode")
    if plan["creation_mode"] == "source_clip" and not any(
        x["url"] == plan.get("source_url") for x in campaign["sources"]
    ):
        raise RuntimeError("The selected source is not linked from the selected campaign")
    if plan["creation_mode"] == "source_clip" and not re.search(
        r"(?:youtube\.com/(?:watch|shorts)|youtu\.be/)", plan.get("source_url", ""), re.I
    ):
        raise RuntimeError("Automatic source clipping currently requires a public YouTube video URL")
    try:
        duration = int(plan["duration_seconds"])
    except (KeyError, ValueError, TypeError) as exc:
        raise RuntimeError("Campaign plan has no valid video duration") from exc
    if not 3 <= duration <= 15:
        raise RuntimeError("This automated generator supports 3-15 second campaign videos")
    title = " ".join(str(plan.get("youtube_title", "")).split())
    desc = str(plan.get("youtube_description", "")).strip()
    keywords = plan.get("youtube_keywords")
    hashtags = plan.get("youtube_hashtags")
    if not title or len(title) > 100 or not desc or not isinstance(keywords, list) or not 5 <= len(keywords) <= 8:
        raise RuntimeError("Campaign plan returned invalid YouTube title, description, or keywords")
    if not isinstance(hashtags, list) or not 2 <= len(hashtags) <= 4:
        raise RuntimeError("Campaign plan must return two to four campaign-relevant hashtags")
    plan["youtube_title"] = title
    plan["youtube_description"] = desc + "\n\n" + " ".join(hashtags)
    plan["youtube_keywords"] = [str(x).replace("#", "").strip()[:100] for x in keywords]
    plan["youtube_hashtags"] = hashtags
    plan["campaign"] = campaign
    print(f"Selected: {campaign['title']} | {plan['creation_mode']} | {plan['reason']}")
    return plan


def generate_original_video(plan: dict, target: Path) -> None:
    client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])
    prompt = plan["video_prompt"] + "\nCreate a vertical 9:16 short for this campaign. Follow these exact requirements: " + json.dumps(plan.get("requirements", []), ensure_ascii=False)
    interaction = client.interactions.create(
        model=os.environ.get("GEMINI_VIDEO_MODEL", "gemini-omni-1.2-flash"),
        input=prompt,
        response_format={"type": "video", "aspect_ratio": "9:16", "duration": f"{plan['duration_seconds']}s", "resolution": "720p"},
    )
    encoded = getattr(getattr(interaction, "output_video", None), "data", None)
    if not encoded:
        raise RuntimeError("Gemini video generation returned no MP4 data")
    target.write_bytes(base64.b64decode(encoded))


def choose_source_moment(plan: dict) -> tuple[float, float]:
    client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])
    interaction = client.interactions.create(
        model=os.environ.get("GEMINI_VIDEO_ANALYSIS_MODEL", "gemini-4-hydrogen"),
        input=[
            {"type": "text", "text": f"Find the single strongest {plan['duration_seconds']}-second excerpt of this supplied video that follows this campaign brief: {plan['campaign']['brief'][:5000]}. Return JSON only with start_seconds and end_seconds as decimals. Choose a complete moment with context, no fabricated content."},
            {"type": "video", "uri": plan["source_url"]},
        ],
    )
    result = json.loads(interaction.output_text or "{}")
    start, end = float(result["start_seconds"]), float(result["end_seconds"])
    if start < 0 or end <= start or end - start < 3 or end - start > 15:
        raise RuntimeError("Video analysis returned invalid clip timestamps")
    return start, end


def generate_source_clip(plan: dict, target: Path) -> None:
    start, end = choose_source_moment(plan)
    raw = target.with_name(target.stem + "-source.mp4")
    command = [sys.executable, "-m", "yt_dlp", "--no-warnings", "--force-keyframes-at-cuts",
               "--download-sections", f"*{start:.3f}-{end:.3f}", "-f", "bv*+ba/b",
               "--merge-output-format", "mp4", "-o", str(raw), plan["source_url"]]
    subprocess.run(command, check=True, cwd=ROOT)
    subprocess.run([FFMPEG, "-hide_banner", "-loglevel", "error", "-y", "-i", str(raw),
                    "-vf", "scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,setsar=1",
                    "-t", str(plan["duration_seconds"]), "-c:v", "libx264", "-preset", "veryfast",
                    "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "128k", "-movflags", "+faststart", str(target)],
                   check=True, cwd=ROOT)
    raw.unlink(missing_ok=True)


def overlay_campaign_text(source: Path, plan: dict) -> None:
    lines = [str(x).strip() for x in plan.get("on_screen_text", []) if str(x).strip()]
    if not lines:
        return
    overlay = source.with_name(source.stem + "-overlay.png")
    output = source.with_name(source.stem + "-final.mp4")
    content = "".join(f"<div>{html.escape(line)}</div>" for line in lines[:5])
    markup = f"""<!doctype html><html><head><style>
      *{{box-sizing:border-box}} html,body{{margin:0;width:1080px;height:1920px;background:transparent;color:#fff;font:700 62px Arial,sans-serif}}
      main{{position:absolute;left:70px;right:70px;bottom:230px;text-align:center;text-shadow:0 3px 10px #000,0 1px 2px #000}}
      div{{margin:12px 0;padding:4px 10px;line-height:1.12}}
      </style></head><body><main>{content}</main></body></html>"""
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": 1080, "height": 1920}, device_scale_factor=1)
        page.set_content(markup)
        page.screenshot(path=str(overlay), omit_background=True)
        browser.close()
    subprocess.run([FFMPEG, "-hide_banner", "-loglevel", "error", "-y", "-i", str(source), "-i", str(overlay),
                    "-filter_complex", "[0:v][1:v]overlay=0:0:format=auto[v]", "-map", "[v]", "-map", "0:a?",
                    "-c:v", "libx264", "-preset", "veryfast", "-pix_fmt", "yuv420p", "-c:a", "aac",
                    "-movflags", "+faststart", str(output)], check=True, cwd=ROOT)
    overlay.unlink(missing_ok=True)
    source.unlink(missing_ok=True)
    output.replace(source)


def campaign_page_action(page, campaign: dict) -> None:
    page.goto(campaign["url"], wait_until="domcontentloaded", timeout=60_000)
    if campaign["action"] != "join":
        return
    join = page.get_by_role("button", name=re.compile(r"^join campaign$", re.I))
    if join.count() == 0:
        join = page.get_by_role("link", name=re.compile(r"^join campaign$", re.I))
    if join.count() != 1:
        raise RuntimeError("Could not uniquely identify the selected campaign's Join Campaign action")
    join.click()
    page.wait_for_timeout(1200)
    if page.get_by_role("button", name=re.compile(r"^apply$", re.I)).count():
        raise RuntimeError("The selected campaign requires an application; automatic application is not supported")


def submit_campaign_clip(page, campaign_url: str, video_path: Path | None = None, post_url: str | None = None) -> str:
    page.goto(campaign_url, wait_until="domcontentloaded", timeout=60_000)
    button = page.get_by_role("button", name=re.compile(r"^submit clip$", re.I))
    if button.count() == 0:
        button = page.get_by_role("link", name=re.compile(r"^submit clip$", re.I))
    if button.count() != 1:
        raise RuntimeError("Could not locate a unique Submit clip action")
    button.click()
    dialog = page.get_by_role("dialog")
    if dialog.count() != 1:
        raise RuntimeError("Content Rewards did not open the expected submission dialog")

    file_inputs = dialog.locator('input[type="file"]')
    if file_inputs.count():
        if video_path is None:
            raise RuntimeError("This campaign requires a draft file")
        file_inputs.first.set_input_files(str(video_path))
        # Select the connected YouTube account if a chooser is present.
        selects = dialog.locator("select")
        if selects.count():
            options = selects.first.locator("option").all_text_contents()
            usable = [x.strip() for x in options if x.strip() and "select" not in x.lower()]
            if len(usable) != 1:
                raise RuntimeError("Choose a single connected YouTube account in Content Rewards")
            selects.first.select_option(label=usable[0])
        submission_type = "draft"
    else:
        if not post_url:
            raise RuntimeError("This campaign requires a live post link")
        link = dialog.get_by_label(re.compile(r"submit video link", re.I))
        if link.count() == 0:
            link = dialog.get_by_placeholder(re.compile(r"paste.*link|video link", re.I))
        if link.count() != 1:
            raise RuntimeError("Could not find the campaign's video-link field")
        link.fill(post_url)
        submission_type = "post"

    acceptance = dialog.get_by_label(re.compile(r"i've read the requirements", re.I))
    if acceptance.count() == 1:
        acceptance.check()
    final = dialog.get_by_role("button", name=re.compile(r"^submit clip$", re.I))
    if final.count() != 1:
        raise RuntimeError("Could not locate the final Submit clip button")
    final.click()
    dialog.wait_for(state="hidden", timeout=30_000)
    return submission_type


def draft_status(page, record: dict) -> str:
    page.goto(DRAFTS_URL, wait_until="domcontentloaded", timeout=60_000)
    page.wait_for_timeout(800)
    text = page.locator("body").inner_text(timeout=10_000)
    marker = record["youtube_title"]
    index = text.casefold().find(marker.casefold())
    if index < 0:
        marker = record["campaign_title"]
        index = text.casefold().find(marker.casefold())
    if index < 0:
        raise RuntimeError("Could not find the saved campaign draft on Content Rewards Drafts")
    context = text[max(0, index - 300):index + 1800].casefold()
    if "approved" in context:
        return "approved"
    if "needs changes" in context or "rejected" in context:
        return "changes_requested"
    if "pending" in context:
        return "pending"
    return "unknown"


def metadata_for_upload(plan: dict) -> dict:
    return {
        "youtube_title": plan["youtube_title"],
        "youtube_description": plan["youtube_description"],
        "youtube_keywords": plan["youtube_keywords"],
    }


def main() -> None:
    auth_path = session_file()
    try:
        MEDIA_DIR.mkdir(parents=True, exist_ok=True)
        state = read_state()
        pending = next((row for row in state.values() if row.get("status") == "draft_pending"), None)
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            context = browser.new_context(storage_state=auth_path)
            page = context.new_page()

            posted = next((row for row in state.values() if row.get("status") == "youtube_uploaded"), None)
            if posted:
                age = (datetime.now(timezone.utc) - datetime.fromisoformat(posted["uploaded_at"])).total_seconds()
                if age > 25 * 60:
                    raise RuntimeError(f"{posted['youtube_url']} is outside Content Rewards' 30-minute submission window")
                submit_campaign_clip(page, posted["campaign_url"], post_url=posted["youtube_url"])
                state.pop(posted["key"], None)
                save_state(state)
                print(f"Resumed Content Rewards submission: {posted['youtube_url']}")
                browser.close()
                return

            if pending:
                status = draft_status(page, pending)
                if status == "pending":
                    print(f"Draft is still awaiting approval: {pending['campaign_title']}")
                    browser.close()
                    return
                if status == "changes_requested":
                    raise RuntimeError("Campaign requested draft changes; inspect Content Rewards and revise before posting")
                if status != "approved":
                    raise RuntimeError("Draft status could not be confirmed; no YouTube upload was made")
                draft_file = MEDIA_DIR / pending["video_file"]
                if not draft_file.exists():
                    raise RuntimeError("Approved draft video artifact is missing")
                video_id = youtube_uploader.upload_youtube(draft_file, pending["metadata"])
                post_url = f"https://www.youtube.com/shorts/{video_id}"
                submit_campaign_clip(page, pending["campaign_url"], post_url=post_url)
                state.pop(pending["key"], None)
                save_state(state)
                print(f"Approved draft published and submitted: {post_url}")
                browser.close()
                return

            campaigns = campaign_candidates(page)
            plan = plan_campaign(campaigns)
            campaign = plan["campaign"]
            campaign_page_action(page, campaign)
            slug = re.sub(r"[^a-z0-9]+", "-", campaign["title"].lower()).strip("-")[:50] or "campaign"
            final = MEDIA_DIR / f"{slug}-{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}.mp4"
            if plan["creation_mode"] == "original_ai":
                generate_original_video(plan, final)
            else:
                generate_source_clip(plan, final)
            overlay_campaign_text(final, plan)
            if not final.exists() or final.stat().st_size < 100_000:
                raise RuntimeError("Campaign video output is missing or unexpectedly small")

            # Detect the campaign-specific submission flow from its brief and dialog.
            is_preapproval = bool(re.search(r"pre.?approval|before posting|draft approval", campaign["brief"], re.I))
            if is_preapproval:
                kind = submit_campaign_clip(page, campaign["url"], video_path=final)
                if kind != "draft":
                    raise RuntimeError("Brief requires pre-approval but Content Rewards opened a link submission form")
                run_id = os.environ.get("GITHUB_RUN_ID", "local")
                record = {
                    "key": final.name,
                    "status": "draft_pending",
                    "artifact_run_id": run_id,
                    "video_file": final.name,
                    "campaign_url": campaign["url"],
                    "campaign_title": campaign["title"],
                    "youtube_title": plan["youtube_title"],
                    "metadata": metadata_for_upload(plan),
                    "created_at": datetime.now(timezone.utc).isoformat(),
                }
                state[final.name] = record
                save_state(state)
                print("Pre-approval draft submitted. The scheduled workflow will check for the brand decision before posting.")
            else:
                video_id = youtube_uploader.upload_youtube(final, metadata_for_upload(plan))
                post_url = f"https://www.youtube.com/shorts/{video_id}"
                record = {
                    "key": final.name,
                    "status": "youtube_uploaded",
                    "youtube_url": post_url,
                    "uploaded_at": datetime.now(timezone.utc).isoformat(),
                    "campaign_url": campaign["url"],
                }
                state[final.name] = record
                save_state(state)
                # Content Rewards requires a fresh public post, so submit immediately.
                submit_campaign_clip(page, campaign["url"], post_url=post_url)
                state.pop(final.name, None)
                save_state(state)
                final.unlink(missing_ok=True)
                print(f"Campaign video published and submitted: {post_url}")
            browser.close()
    finally:
        Path(auth_path).unlink(missing_ok=True)


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        print(f"Content Rewards pipeline failed: {error}", file=sys.stderr)
        raise
