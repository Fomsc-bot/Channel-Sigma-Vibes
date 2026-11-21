#!/usr/bin/env python3
"""Create a Playwright storage state for the Content Rewards workflow."""
from pathlib import Path
from playwright.sync_api import sync_playwright

STATE_FILE = Path(__file__).resolve().parent / ".content_rewards_storage_state.json"
START_URL = "https://contentrewards.com/c/campaigns"


def main() -> None:
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=False)
        context = browser.new_context()
        page = context.new_page()
        page.goto(START_URL, wait_until="domcontentloaded", timeout=60_000)
        input(
            "Sign in to Content Rewards in the opened browser, open your Campaigns page, "
            "then return here and press Enter to save this session: "
        )
        context.storage_state(path=str(STATE_FILE))
        browser.close()
    print(f"Saved authenticated browser state to {STATE_FILE}")
    print("Treat this file like a password. Do not commit or share it.")


if __name__ == "__main__":
    main()
