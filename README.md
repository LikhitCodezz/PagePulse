# PagePulse

### A website change radar by Likhit

Web pages are lively. They also change the clock, shuffle a banner, and occasionally decide you are a robot. **PagePulse tries to tell the plot from the confetti.**

PagePulse watches public pages, saves meaningful versions, and keeps the evidence close: a timestamp, a text diff, and a screenshot. It is a local Streamlit project built for a competition demo and curious people who would rather not refresh the same page all day.

## What it does

- Renders a public page with Playwright and extracts readable text.
- Scans automatically on a per-page interval from **5 minutes to 7 days** while the app is running.
- Saves a new version and screenshot when a change survives its noise filters.
- Ignores changes below the configured word threshold and waits for larger changes to repeat on two consecutive scans.
- Labels common CAPTCHA, blocked, HTTP error, empty-page, and outage cases separately from content changes.
- Prevents duplicate watch entries for the same URL and applies a short per-host request cooldown.
- Supports CSS selectors for focusing on a region or ignoring a noisy region.
- Offers keyword alerts, number-history charts, and a downloadable RSS feed for each watched page.
- Adds optional AI change briefs with importance, category, summary, reason, confidence, and a notification recommendation.

## Quick start on Windows

Install Python 3.10 or newer, then open PowerShell in the project folder:

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
python -m playwright install chromium
streamlit run app.py
```

If PowerShell does not allow virtual-environment activation, run the tools by their full path:

```powershell
py -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m playwright install chromium
.\.venv\Scripts\python.exe -m streamlit run app.py
```

Streamlit opens the dashboard in your browser. Add a page, choose its automatic scan interval, and leave the app running. The first scan is scheduled shortly after a page is added; **Scan now** is available for an immediate check.

## Optional AI briefs

AI is off unless you configure a key and enable it in the sidebar. For the standard OpenAI API, set the key in PowerShell before starting PagePulse:

```powershell
$env:OPENAI_API_KEY = "your-api-key"
streamlit run app.py
```

For another OpenAI-compatible provider, you can also set:

```powershell
$env:OPENAI_BASE_URL = "https://your-provider.example/v1"
$env:OPENAI_MODEL = "your-model-name"
```

See [`.env.example`](.env.example) for the supported variable names. The app does not load that file automatically; it is a reference template. Keep real API keys private. When AI is enabled, changed page text is sent to the configured provider for analysis. Page text is treated as untrusted input in the analysis prompt, and provider errors do not stop the website check.

## How the radar works

1. **Render:** Playwright opens the URL and captures its readable page text.
2. **Tidy:** scripts and other non-content elements are removed; optional CSS selectors can narrow the watched area.
3. **Compare:** a SHA-256 fingerprint spots identical snapshots, and a word diff measures what changed.
4. **Confirm:** tiny edits can be filtered by the sensitivity setting. A larger change must appear on two scans in a row before it is saved.
5. **Keep receipts:** confirmed versions, optional AI assessments, extracted numbers, and screenshot paths are stored in SQLite under `data/`.

CAPTCHA and outage detection uses recognizable page text and HTTP status codes. It is a practical safeguard for a demo, not a perfect classifier.

## Project files

| File | Purpose |
| --- | --- |
| `app.py` | Streamlit interface, SQLite storage, and background scheduler |
| `detector.py` | Public URL checks, browser capture, content cleanup, and page-state detection |
| `ai_analyzer.py` | Optional OpenAI-compatible JSON change analysis |
| `requirements.txt` | Python dependencies |
| `.env.example` | Names of optional environment variables; contains no credentials |

## Notes before deploying

- The scheduler runs inside the Streamlit process. Scheduled scans pause when the app closes and resume when it starts again.
- This is a local, single-user app with a local SQLite database. It is not a hosted multi-user service. A shared deployment would need a central worker and shared subscriptions so one page fetch can serve many users.
- Keyword alerts are shown in the dashboard; email, SMS, and chat delivery are not included.
- The URL check rejects local/private destinations, but it is not a hardened SSRF boundary. Do not expose this demo as a public service without stronger network isolation, authentication, and request controls.
- Only monitor pages you are permitted to access. Some sites may block automated browsers or require interaction.

## A small promise

PagePulse does not try to understand the whole internet. It keeps the receipts, ignores the confetti, and taps you on the shoulder when the plot changes.
