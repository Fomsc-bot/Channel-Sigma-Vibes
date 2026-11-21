# Content Rewards publishing workflow

The GitHub Actions workflow `Select Content Rewards Campaign and Publish Short`
runs each day at 6:00 PM Sri Lanka time and can also be started with
**Actions → Run workflow**. It uses Playwright to inspect campaigns already
available to your creator account, chooses a campaign only when an existing
Sigma Vibes HTML scene clearly meets its brief, renders the scene, publishes it
publicly as a YouTube Short, and submits the YouTube link to that campaign.

Content Rewards' creator instructions require a connected and verified social
account, a public post, and submission of the link within 30 minutes. The
workflow checks for a campaign's **Submit clip** action, which means it is
already joined/approved. It does not join campaigns or submit applications. If
the brief asks for source footage, product demos, assets, or claims the current
scene cannot satisfy, the run stops without publishing.

## One-time setup

1. In Content Rewards, connect and verify the same YouTube channel used by the
   YouTube API credentials. Join/apply to campaigns manually and wait until
   **Submit clip** is available.
2. Install the Python dependencies locally (`python -m pip install -r
   requirements.txt`) and install Chromium (`python -m playwright install
   chromium`). Run `python capture_content_rewards_session.py`. Sign in to
   Content Rewards in the opened browser, navigate to your Campaigns page, and
   press Enter in the terminal. This creates
   `.content_rewards_storage_state.json` in the repo root.
3. Add these GitHub repository secrets:

   - `CR_STORAGE_STATE_B64`: base64 encoding of the storage-state file. In
     PowerShell, copy the output of:
     `[Convert]::ToBase64String([IO.File]::ReadAllBytes('.content_rewards_storage_state.json'))`
     and save it as the secret. The state contains login cookies; treat it like
     a password and refresh it when the workflow reports an expired session.
   - `GEMINI_API_KEY`
   - `YT_CLIENT_ID`
   - `YT_CLIENT_SECRET`
   - `YT_REFRESH_TOKEN`

4. Optionally set the repository variable `CR_CAMPAIGNS_URL` to the exact
   campaign list URL shown after signing in. The default is
   `https://contentrewards.com/c/campaigns`.

The YouTube OAuth refresh token must allow video uploads. The video is published
as **public** because Content Rewards requires a public post. A successful
upload is submitted immediately. If the UI submission fails, the run prints the
Short link; resubmit it manually before the 30-minute window closes. The saved
delivery state prevents a retry from uploading the same source twice.

## Current content fit

The source files are short original quote/motivation scenes, not clips from
campaign source footage. The campaign matcher rejects briefs that require other
content. To support those campaigns, add source assets and a renderer designed
for their specific requirements before loosening the matching gate.
