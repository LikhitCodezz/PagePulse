import difflib
import json
import logging
import os
import re
import sqlite3
import threading
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta
from email.utils import format_datetime
from pathlib import Path
from urllib.parse import urlparse

import pandas as pd
import streamlit as st
from streamlit_autorefresh import st_autorefresh

from ai_analyzer import analyze_change
from detector import PageCheckError, check_page, safe_public_url

APP_DIR = Path(__file__).parent
DATA_DIR = APP_DIR / "data"
SNAP_DIR = DATA_DIR / "screenshots"
DB_PATH = DATA_DIR / "detector.db"
HOST_COOLDOWN_SECONDS = 10
SCHEDULER_POLL_SECONDS = 15
DATA_DIR.mkdir(exist_ok=True)
SNAP_DIR.mkdir(exist_ok=True)

st.set_page_config(page_title="PagePulse | Web change radar", page_icon="🔭", layout="wide")

st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=DM+Mono:wght@400;500&family=Manrope:wght@400;500;600;700;800&display=swap');
:root { --ink:#eaf3ff; --muted:#8da5bd; --mint:#55e6c1; --blue:#78aaff; --panel:#101d31; }
.stApp { background: radial-gradient(ellipse at 12% -10%, #20385a 0, #0a1322 42%, #08111e 100%); color:var(--ink); font-family:'Manrope',sans-serif; }
section[data-testid="stSidebar"] { background:linear-gradient(180deg,#111f34,#0b1423); border-right:1px solid #273a54; }
h1,h2,h3 { letter-spacing:-.04em; }
div[data-testid="stMetric"] { background:linear-gradient(145deg,#14253a,#101c2d); border:1px solid #2b4058; padding:18px 20px; border-radius:18px; }
div[data-testid="stMetricValue"] { color:#f3f8ff; }
div[data-testid="stVerticalBlockBorderWrapper"] { border-color:#263a52!important; background:rgba(16,29,49,.8); border-radius:18px; }
.pulse-kicker { color:var(--mint); font:500 12px 'DM Mono',monospace; letter-spacing:.18em; text-transform:uppercase; }
.hero-kicker { text-align:center; }
.hero-kicker.intro-animate { animation:kicker-arrive .8s ease-out both; }
.pulse-title { font-size:clamp(66px,9vw,92px); line-height:1.02; font-weight:800; letter-spacing:-.07em; margin:8px 0 0; text-align:center; }
.brand-wordmark { display:inline-block; background:linear-gradient(105deg,#f3f8ff 0%,#f3f8ff 35%,#55e6c1 48%,#78aaff 58%,#f3f8ff 72%); background-size:220% 100%; background-position:100% 0; color:transparent; -webkit-background-clip:text; background-clip:text; animation:brand-breathe 6s ease-in-out infinite; }
.pulse-title.intro-animate .brand-wordmark { animation:brand-shimmer 1.7s cubic-bezier(.2,.75,.2,1) .45s both, brand-breathe 6s ease-in-out 2.2s infinite; }
.pulse-title > span:not(.brand-wordmark) { display:inline-block; position:relative; color:var(--mint); transform-origin:center; animation:radar-pulse 5s ease-in-out infinite; }
.pulse-title.intro-animate { animation:title-arrive 1.05s cubic-bezier(.16,1,.3,1) .12s both; }
.pulse-title.intro-animate > span:not(.brand-wordmark) { animation:radar-intro 1.5s cubic-bezier(.16,1,.3,1) .35s both, radar-pulse 5s ease-in-out 1.9s infinite; }
.pulse-title.intro-animate > span:not(.brand-wordmark)::after { content:''; position:absolute; inset:-.12em; border:1px solid #55e6c1aa; border-right-color:transparent; border-radius:50%; opacity:0; animation:ring-arrive 1.8s ease-out .55s both; }
.pulse-byline { display:block; width:max-content; margin:10px auto 20px; color:#a4bad0; font:500 18px 'DM Mono',monospace; letter-spacing:.18em; overflow:hidden; white-space:nowrap; text-align:center; }
.pulse-byline.intro-animate { width:0; border-right:1px solid var(--mint); animation:byline-reveal 1.35s steps(9,end) .95s forwards, caret-blink .8s step-end 2.3s infinite; }
.pulse-title::after { content:''; display:block; width:min(440px,78vw); height:1px; margin:15px auto 0; background:linear-gradient(90deg,transparent,#55e6c1aa,#78aaff55,transparent); background-size:200% 100%; animation:quiet-current 9s linear infinite; }
.pulse-subtitle { text-align:center; color:var(--muted); font-size:16px; margin:2px 0 26px; }
.pulse-subtitle.intro-animate { animation:subtitle-arrive .8s ease-out .7s both; }
@keyframes kicker-arrive { from { opacity:0; transform:translateY(8px); letter-spacing:.34em; } to { opacity:1; transform:translateY(0); letter-spacing:.18em; } }
@keyframes title-arrive { from { opacity:0; transform:translateY(20px) scale(.97); filter:blur(9px); } to { opacity:1; transform:translateY(0) scale(1); filter:blur(0); } }
@keyframes subtitle-arrive { from { opacity:0; transform:translateY(7px); } to { opacity:1; transform:translateY(0); } }
@keyframes brand-shimmer { 0% { background-position:120% 0; filter:brightness(.75); } 100% { background-position:0 0; filter:brightness(1.12); } }
@keyframes brand-breathe { 0%,100% { filter:drop-shadow(0 0 0 #55e6c100); } 50% { filter:drop-shadow(0 0 9px #55e6c155); } }
@keyframes radar-intro { 0% { transform:scale(.35) rotate(-80deg); opacity:0; } 70% { transform:scale(1.25) rotate(12deg); opacity:1; } 100% { transform:scale(1) rotate(0); opacity:1; } }
@keyframes ring-arrive { 0% { transform:scale(.55) rotate(-90deg); opacity:0; } 35% { opacity:.8; } 100% { transform:scale(1.45) rotate(240deg); opacity:0; } }
@keyframes radar-pulse { 0%,100% { transform:scale(1); text-shadow:0 0 5px #55e6c144; } 50% { transform:scale(1.07); text-shadow:0 0 11px #55e6c177; } }
@keyframes byline-reveal { to { width:11ch; } }
@keyframes caret-blink { 50% { border-color:transparent; } }
@keyframes quiet-current { to { background-position:-200% 0; } }
.pulse-subtitle { color:var(--muted); font-size:15px; margin:0 0 18px; }
.stButton>button[kind="primary"] { background:linear-gradient(100deg,#41dcb7,#71afff); color:#071521; border:0; font-weight:800; }
div[data-testid="stExpander"] { border-color:#263a52; border-radius:14px; }
code, .stCode { font-family:'DM Mono',monospace!important; }
@media (max-width:640px) { .pulse-title { font-size:56px; } .pulse-byline { font-size:16px; } .pulse-subtitle { font-size:14px; } }
@media (prefers-reduced-motion:reduce) { *,*::before,*::after { animation-duration:.01ms!important; animation-iteration-count:1!important; scroll-behavior:auto!important; } }
</style>
""", unsafe_allow_html=True)


def db():
    conn = sqlite3.connect(DB_PATH, check_same_thread=False, timeout=15)
    conn.row_factory = sqlite3.Row
    conn.execute("""CREATE TABLE IF NOT EXISTS pages (
        id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL, url TEXT NOT NULL UNIQUE,
        interval_minutes INTEGER NOT NULL DEFAULT 60, include_selector TEXT DEFAULT '',
        ignore_selector TEXT DEFAULT '', sensitivity INTEGER DEFAULT 3,
        keywords TEXT DEFAULT '', pending_hash TEXT, pending_text TEXT,
        pending_count INTEGER DEFAULT 0,
        next_check_at TEXT,
        last_checked TEXT, last_status TEXT DEFAULT 'Not checked', last_error TEXT DEFAULT ''
    )""")
    conn.execute("""CREATE TABLE IF NOT EXISTS versions (
        id INTEGER PRIMARY KEY AUTOINCREMENT, page_id INTEGER NOT NULL,
        checked_at TEXT NOT NULL, content_hash TEXT NOT NULL, text_content TEXT NOT NULL,
        screenshot_path TEXT, note TEXT DEFAULT 'Initial snapshot',
        ai_status TEXT DEFAULT 'not_run', ai_importance TEXT, ai_category TEXT,
        ai_summary TEXT, ai_reason TEXT, ai_confidence REAL, ai_notify INTEGER,
        numbers_json TEXT DEFAULT '{}', matched_keywords TEXT DEFAULT '[]',
        FOREIGN KEY(page_id) REFERENCES pages(id)
    )""")
    conn.execute("CREATE TABLE IF NOT EXISTS request_log (host TEXT PRIMARY KEY, last_requested TEXT NOT NULL)")
    conn.execute("CREATE TABLE IF NOT EXISTS app_settings (setting_key TEXT PRIMARY KEY, setting_value TEXT NOT NULL)")
    migrations = {
        "pages": {
            "keywords": "TEXT DEFAULT ''", "pending_hash": "TEXT", "pending_text": "TEXT",
            "pending_count": "INTEGER DEFAULT 0", "next_check_at": "TEXT",
        },
        "versions": {
            "ai_status": "TEXT DEFAULT 'not_run'", "ai_importance": "TEXT", "ai_category": "TEXT",
            "ai_summary": "TEXT", "ai_reason": "TEXT", "ai_confidence": "REAL", "ai_notify": "INTEGER",
            "numbers_json": "TEXT DEFAULT '{}'", "matched_keywords": "TEXT DEFAULT '[]'",
        },
    }
    for table, columns in migrations.items():
        existing = {row["name"] for row in conn.execute(f"PRAGMA table_info({table})")}
        for column, definition in columns.items():
            if column not in existing:
                conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")
    conn.commit()
    return conn


def get_pages(conn):
    return conn.execute("SELECT * FROM pages ORDER BY id DESC").fetchall()


def page_versions(conn, page_id):
    return conn.execute("SELECT * FROM versions WHERE page_id=? ORDER BY id DESC", (page_id,)).fetchall()


def setting(conn, key, default=""):
    row = conn.execute("SELECT setting_value FROM app_settings WHERE setting_key=?", (key,)).fetchone()
    return row["setting_value"] if row else default


def save_setting(conn, key, value):
    conn.execute("INSERT INTO app_settings(setting_key,setting_value) VALUES(?,?) ON CONFLICT(setting_key) DO UPDATE SET setting_value=excluded.setting_value",
                 (key, str(value)))
    conn.commit()


def schedule_next_check(conn, page_id, interval_minutes):
    due = datetime.now() + timedelta(minutes=int(interval_minutes))
    conn.execute("UPDATE pages SET next_check_at=? WHERE id=?", (due.isoformat(timespec="seconds"), page_id))
    conn.commit()


def scheduler_loop(stop_event):
    """Poll due rows in a daemon worker; no browser fetch runs on UI reruns."""
    while not stop_event.is_set():
        worker_conn = None
        try:
            worker_conn = db()
            now = datetime.now().isoformat(timespec="seconds")
            due_pages = worker_conn.execute(
                "SELECT * FROM pages WHERE next_check_at IS NULL OR next_check_at<=? ORDER BY next_check_at",
                (now,),
            ).fetchall()
            run_ai = setting(worker_conn, "ai_enabled", "false") == "true" and bool(os.getenv("OPENAI_API_KEY", "").strip())
            for due_page in due_pages:
                if stop_event.is_set():
                    break
                outcome, _, _ = do_check(worker_conn, due_page, ai_enabled=run_ai)
                if outcome != "cooldown":
                    schedule_next_check(worker_conn, due_page["id"], due_page["interval_minutes"])
        except Exception:
            logging.exception("PagePulse background scheduler error")
        finally:
            if worker_conn is not None:
                worker_conn.close()
        stop_event.wait(SCHEDULER_POLL_SECONDS)


@st.cache_resource
def start_scheduler():
    stop_event = threading.Event()
    worker = threading.Thread(target=scheduler_loop, args=(stop_event,), name="pagepulse-scheduler", daemon=True)
    worker.start()
    return stop_event, worker


def reserve_host_request(conn, host):
    """Atomically enforce a small per-host cooldown across monitored URLs."""
    conn.execute("BEGIN IMMEDIATE")
    prior = conn.execute("SELECT last_requested FROM request_log WHERE host=?", (host,)).fetchone()
    now = datetime.now()
    if prior:
        elapsed = (now - datetime.fromisoformat(prior["last_requested"])).total_seconds()
        if elapsed < HOST_COOLDOWN_SECONDS:
            conn.rollback()
            return max(1, int(HOST_COOLDOWN_SECONDS - elapsed + .99))
    conn.execute("INSERT INTO request_log(host,last_requested) VALUES(?,?) ON CONFLICT(host) DO UPDATE SET last_requested=excluded.last_requested",
                 (host, now.isoformat(timespec="seconds")))
    conn.commit()
    return 0


def changed_word_count(old_text, new_text):
    old_words, new_words = old_text.split(), new_text.split()
    matcher = difflib.SequenceMatcher(a=old_words, b=new_words, autojunk=False)
    return sum(max(i2 - i1, j2 - j1) for tag, i1, i2, j1, j2 in matcher.get_opcodes() if tag != "equal")


def changed_text(old_text, new_text):
    old_words, new_words = old_text.split(), new_text.split()
    matcher = difflib.SequenceMatcher(a=old_words, b=new_words, autojunk=False)
    return " ".join(" ".join(new_words[j1:j2]) for tag, _, _, j1, j2 in matcher.get_opcodes() if tag != "equal")


def numeric_values(text):
    """Track number-like values with a short nearby text label."""
    found = {}
    pattern = re.compile(r"(?P<label>[A-Za-z][A-Za-z0-9 _/%$€£#.,:-]{0,44}?)\s+(?P<value>-?\d[\d,]*(?:\.\d+)?%?)")
    for match in pattern.finditer(text):
        label = " ".join(match.group("label").split()[-5:]).strip(" .,:-_")
        if not label:
            continue
        raw = match.group("value").replace(",", "").rstrip("%")
        try:
            found[label[:60]] = float(raw)
        except ValueError:
            continue
    return found


def rss_for_page(page, versions):
    root = ET.Element("rss", version="2.0")
    channel = ET.SubElement(root, "channel")
    ET.SubElement(channel, "title").text = f"PagePulse — {page['name']}"
    ET.SubElement(channel, "link").text = page["url"]
    ET.SubElement(channel, "description").text = f"Saved website changes for {page['name']}"
    for version in versions:
        item = ET.SubElement(channel, "item")
        ET.SubElement(item, "title").text = version["ai_summary"] or version["note"] or "Website content updated"
        ET.SubElement(item, "link").text = page["url"]
        ET.SubElement(item, "guid", isPermaLink="false").text = f"pagepulse-version-{version['id']}"
        try:
            pub_date = format_datetime(datetime.fromisoformat(version["checked_at"]).astimezone())
        except (TypeError, ValueError):
            pub_date = version["checked_at"]
        ET.SubElement(item, "pubDate").text = pub_date
        ET.SubElement(item, "description").text = (version["ai_summary"] or version["text_content"][:500])
    return ET.tostring(root, encoding="utf-8", xml_declaration=True)


def do_check(conn, page, ai_enabled=False):
    temp_screenshot = SNAP_DIR / f"page_{page['id']}_check_temp.png"
    try:
        host = urlparse(page["url"]).hostname or ""
        wait_seconds = reserve_host_request(conn, host)
        if wait_seconds:
            return "cooldown", {"error": f"This host was just checked. Try again in about {wait_seconds} seconds."}, None

        result = check_page(
            page["url"], screenshot_path=str(temp_screenshot),
            include_selector=page["include_selector"] or "",
            ignore_selector=page["ignore_selector"] or "",
            sensitivity=int(page["sensitivity"] or 3),
        )
        old = conn.execute("SELECT * FROM versions WHERE page_id=? ORDER BY id DESC LIMIT 1", (page["id"],)).fetchone()
        now = datetime.now().isoformat(timespec="seconds")
        if old is not None and old["content_hash"] == result["content_hash"]:
            conn.execute("UPDATE pages SET pending_hash=NULL,pending_text=NULL,pending_count=0,last_checked=?,last_status='OK · Stable',last_error='' WHERE id=?", (now, page["id"]))
            conn.commit()
            if temp_screenshot.exists():
                temp_screenshot.unlink()
            return "same", result, old

        if old is not None and changed_word_count(old["text_content"], result["text"]) < int(page["sensitivity"] or 3):
            conn.execute("UPDATE pages SET pending_hash=NULL,pending_text=NULL,pending_count=0,last_checked=?,last_status='NOISE · Ignored',last_error='' WHERE id=?", (now, page["id"]))
            conn.commit()
            if temp_screenshot.exists():
                temp_screenshot.unlink()
            return "noise", result, old

        # A changed page must produce the same meaningful text twice in a row.
        # Per-load dates, counters and rotating banners therefore do not flood history.
        if old is not None and page["pending_hash"] != result["content_hash"]:
            conn.execute("UPDATE pages SET pending_hash=?,pending_text=?,pending_count=1,last_checked=?,last_status='CANDIDATE · Confirming',last_error='' WHERE id=?",
                         (result["content_hash"], result["text"], now, page["id"]))
            conn.commit()
            if temp_screenshot.exists():
                temp_screenshot.unlink()
            return "candidate", result, old

        keywords = [word.strip() for word in (page["keywords"] or "").split(",") if word.strip()]
        delta_text = changed_text(old["text_content"], result["text"]) if old else result["text"]
        matched = [word for word in keywords if word.casefold() in delta_text.casefold()]
        analysis = {"status": "baseline" if old is None else "not_run"}
        if ai_enabled and old is not None:
            analysis = analyze_change(old["text_content"], result["text"])
        screenshot = SNAP_DIR / f"page_{page['id']}_version_{datetime.now().strftime('%Y%m%d_%H%M%S_%f')}.png"
        os.replace(temp_screenshot, screenshot)
        note = "Initial snapshot" if old is None else "Confirmed content change"
        conn.execute("""INSERT INTO versions(
            page_id,checked_at,content_hash,text_content,screenshot_path,note,
            ai_status,ai_importance,ai_category,ai_summary,ai_reason,ai_confidence,ai_notify,
            numbers_json,matched_keywords
        ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                     (page["id"], now, result["content_hash"], result["text"], str(screenshot), note,
                      analysis.get("status", "not_run"), analysis.get("importance"), analysis.get("category"),
                      analysis.get("summary"), analysis.get("reason") or analysis.get("error"),
                      analysis.get("confidence"), int(analysis["notify"]) if analysis.get("notify") is not None else None,
                      json.dumps(numeric_values(result["text"]), ensure_ascii=False), json.dumps(matched)))
        conn.execute("UPDATE pages SET pending_hash=NULL,pending_text=NULL,pending_count=0,last_checked=?,last_status=?,last_error='' WHERE id=?",
                     (now, "OK · Baseline saved" if old is None else ("ALERT · Keyword matched" if matched else "CHANGED · Confirmed"), page["id"]))
        conn.commit()
        return ("initial" if old is None else "changed"), {**result, "matched_keywords": matched}, old
    except Exception as exc:
        if temp_screenshot.exists():
            temp_screenshot.unlink()
        now = datetime.now().isoformat(timespec="seconds")
        category = exc.category if isinstance(exc, PageCheckError) else "CHECK ERROR"
        conn.execute("UPDATE pages SET last_checked=?,last_status=?,last_error=?,pending_hash=NULL,pending_text=NULL,pending_count=0 WHERE id=?",
                     (now, category, str(exc)[:500], page["id"]))
        conn.commit()
        return "error", {"error": str(exc), "category": category}, None


def render_ai_assessment(version):
    if version["ai_status"] == "ok":
        st.markdown("**AI change brief**")
        importance = (version["ai_importance"] or "unknown").title()
        st.write(f"**{importance}** · {version['ai_category'] or 'Other'}")
        st.write(version["ai_summary"] or "No summary returned.")
        st.caption(version["ai_reason"] or "No reason returned.")
        confidence = version["ai_confidence"]
        st.caption(f"Confidence {confidence:.0%}" if confidence is not None else "Confidence unavailable")
        st.caption("Keyword alert matched" if version["matched_keywords"] not in (None, "[]") else ("AI recommends a notification" if version["ai_notify"] else "No notification recommended"))
    elif version["ai_status"] in ("error", "unavailable"):
        st.caption(f"AI analysis unavailable: {version['ai_reason'] or 'Check API configuration.'}")
    elif version["ai_status"] == "baseline":
        st.caption("Baseline saved. Analysis begins when a later change is confirmed.")
    else:
        st.caption("AI analysis was not enabled for this version.")


conn = db()
intro_class = "intro-animate" if not st.session_state.get("intro_animation_seen_v2", False) else ""
st.session_state["intro_animation_seen_v2"] = True
st.markdown(f'<div class="pulse-kicker hero-kicker {intro_class}">WEBSITE CHANGE RADAR · COMPETITION EDITION</div>', unsafe_allow_html=True)
st.markdown(f'<div class="pulse-title {intro_class}"><span class="brand-wordmark">PagePulse</span> <span>◉</span></div>', unsafe_allow_html=True)
st.markdown(f'<div class="pulse-byline {intro_class}">by Likhit</div>', unsafe_allow_html=True)
st.markdown(f'<div class="pulse-subtitle {intro_class}">Catch the changes that matter. Let the noise pass.</div>', unsafe_allow_html=True)

with st.sidebar:
    st.markdown("### + Add a watch")
    with st.form("add_page", clear_on_submit=True):
        name = st.text_input("Watch name", placeholder="Admissions announcements")
        url = st.text_input("Public website URL", placeholder="https://example.com/news")
        interval = st.number_input(
            "Automatic scan interval (minutes)",
            min_value=5,
            max_value=10080,
            value=60,
            step=5,
            help="Choose from 5 minutes up to 7 days (10,080 minutes). PagePulse scans automatically while this app is running.",
        )
        include_selector = st.text_input("Watch only this CSS area (optional)", placeholder="main")
        ignore_selector = st.text_input("Ignore CSS areas (optional)", placeholder=".timestamp, .ad")
        sensitivity = st.slider("Noise filter · minimum changed words", 1, 20, 3)
        keywords = st.text_input("Alert only when these words change (optional)", placeholder="deadline, scholarship, postponed")
        submitted = st.form_submit_button("Add to radar", use_container_width=True, type="primary")
        if submitted:
            try:
                safe_public_url(url)
                if not name.strip():
                    st.error("Add a name for this watch.")
                else:
                    first_scan = datetime.now().isoformat(timespec="seconds")
                    conn.execute("INSERT INTO pages(name,url,interval_minutes,include_selector,ignore_selector,sensitivity,keywords,next_check_at) VALUES(?,?,?,?,?,?,?,?)",
                                 (name.strip(), url.strip(), interval, include_selector.strip(), ignore_selector.strip(), sensitivity, keywords.strip(), first_scan))
                    conn.commit()
                    st.success("Added to your radar.")
                    st.rerun()
            except sqlite3.IntegrityError:
                st.error("This URL is already watched. One monitor is shared per unique URL.")
            except Exception as exc:
                st.error(f"Could not add URL: {exc}")
    st.divider()
    st.caption("One saved monitor per unique URL, a 10-second per-host request cooldown, and a two-check confirmation filter help prevent duplicate fetches and noisy history.")
    ai_key_configured = bool(os.getenv("OPENAI_API_KEY", "").strip())
    ai_enabled = st.checkbox("AI one-line change briefs", value=(setting(conn, "ai_enabled", "false") == "true") if ai_key_configured else False,
                             disabled=not ai_key_configured,
                             help="Sends changed page text to your configured OpenAI-compatible provider.")
    save_setting(conn, "ai_enabled", ai_enabled)
    if not ai_key_configured:
        st.caption("AI is optional. Set OPENAI_API_KEY to enable it.")

start_scheduler()
st_autorefresh(interval=SCHEDULER_POLL_SECONDS * 1000, key="pagepulse-dashboard-refresh")
pages = get_pages(conn)
changed_count = sum("CHANGED" in (page["last_status"] or "") or "ALERT" in (page["last_status"] or "") for page in pages)
attention_count = sum(any(word in (page["last_status"] or "") for word in ("CAPTCHA", "OUTAGE", "BLOCKED", "ERROR")) for page in pages)
m1, m2, m3 = st.columns(3)
m1.metric("Pages on radar", len(pages))
m2.metric("Confirmed changes", changed_count)
m3.metric("Needs attention", attention_count)

if not pages:
    st.info("Your radar is clear. Add a public page from the sidebar to save its first baseline.")
else:
    st.markdown("### Live watches")
    for page in pages:
        versions = page_versions(conn, page["id"])
        with st.container(border=True):
            left, mid, right = st.columns([5, 2, 2])
            with left:
                st.markdown(f"#### {page['name']}")
                st.caption(page["url"])
                st.caption(f"Last check: {page['last_checked'] or 'Not checked'}  ·  Auto scan: every {page['interval_minutes']} min  ·  Next: {page['next_check_at'] or 'Due shortly'}")
                if page["keywords"]:
                    st.caption(f"Keyword watch: {page['keywords']}")
                if page["last_error"]:
                    st.warning(page["last_error"])
            with mid:
                st.caption("RADAR STATUS")
                st.write(page["last_status"] or "Not checked")
            with right:
                if st.button("Scan now", key=f"check_{page['id']}", use_container_width=True, type="primary"):
                    with st.spinner("Checking the page and filtering noise…"):
                        outcome, result, old = do_check(conn, page, ai_enabled=ai_enabled)
                    if outcome != "cooldown":
                        schedule_next_check(conn, page["id"], page["interval_minutes"])
                    if outcome == "initial":
                        st.success("Baseline captured.")
                    elif outcome == "changed":
                        st.success("Confirmed change saved.")
                        if result.get("matched_keywords"):
                            st.toast("Keyword alert: " + ", ".join(result["matched_keywords"]), icon="🔔")
                    elif outcome == "candidate":
                        st.info("Change candidate found. It will be saved if it appears again on the next scan.")
                    elif outcome == "noise":
                        st.info("Small change filtered as likely noise.")
                    elif outcome == "same":
                        st.success("Stable. No new version stored.")
                    elif outcome == "cooldown":
                        st.warning(result["error"])
                    else:
                        st.error(f"{result.get('category', 'Check failed')}: {result['error']}")
                    st.rerun()
                if st.button("Remove", key=f"delete_{page['id']}", use_container_width=True):
                    conn.execute("DELETE FROM versions WHERE page_id=?", (page["id"],))
                    conn.execute("DELETE FROM pages WHERE id=?", (page["id"],))
                    conn.commit()
                    st.rerun()

            x1, x2 = st.columns([3, 7])
            with x1:
                st.download_button("↓ Page RSS feed", data=rss_for_page(page, versions), file_name=f"pagepulse-{page['id']}.xml",
                                   mime="application/rss+xml", key=f"rss_{page['id']}", use_container_width=True)
            with x2:
                if versions:
                    st.caption(f"{len(versions)} saved version(s) · one fetch serves this unique URL in this app")

            with st.expander(f"Change lab · {len(versions)} version(s)", expanded=False):
                if not versions:
                    st.write("No baseline yet. Scan this page to start tracking it.")
                    continue
                ids = [v["id"] for v in versions]
                labels = {v["id"]: f"v{v['id']} · {v['checked_at']} · {v['note']}" for v in versions}
                chosen = st.selectbox("Version", ids, format_func=lambda value: labels[value], key=f"ver_{page['id']}")
                selected = next(v for v in versions if v["id"] == chosen)
                render_ai_assessment(selected)
                if selected["matched_keywords"] not in (None, "[]"):
                    st.warning("Keyword alert: " + ", ".join(json.loads(selected["matched_keywords"])))

                series = []
                for version in reversed(versions):
                    values = json.loads(version["numbers_json"] or "{}")
                    if values:
                        series.append({"checked_at": version["checked_at"], **values})
                if len(series) >= 2:
                    st.markdown("**Number watch · values found near text labels**")
                    frame = pd.DataFrame(series).set_index("checked_at")
                    st.line_chart(frame, height=230)
                st.text_area("Captured page text", selected["text_content"], height=150, key=f"text_{page['id']}_{chosen}")
                if selected["screenshot_path"] and Path(selected["screenshot_path"]).exists():
                    st.image(selected["screenshot_path"], caption="Saved with this version", use_container_width=True)
                if len(versions) >= 2:
                    older, newer = versions[1], versions[0]
                    diff = difflib.unified_diff(older["text_content"].splitlines(), newer["text_content"].splitlines(),
                                                fromfile=f"v{older['id']}", tofile=f"v{newer['id']}", lineterm="")
                    st.markdown("**Latest confirmed text diff**")
                    st.code("\n".join(diff) or "No textual differences.", language="diff")

st.markdown("""
<div style="margin-top:26px;padding:18px 22px;border:1px solid #263a52;border-radius:16px;background:rgba(16,29,49,.65)">
<span class="pulse-kicker">HOW THE RADAR STAYS POLITE</span><br>
<span style="color:#dce9f7">Unique URL deduplication · 10-second host cooldown · low-change word threshold · two matching scans before saving · CAPTCHA/outage states never become content versions.</span>
</div>
""", unsafe_allow_html=True)
st.caption("PagePulse scans automatically while this app is running. Keep the Streamlit window/process open for scheduled checks. This local SQLite app is single-user and does not provide a shared multi-user polling service.")

st.divider()
st.markdown('<div class="pulse-kicker">FIELD NOTES · UNDER THE HOOD</div>', unsafe_allow_html=True)
st.markdown("## So, how does PagePulse work?")
st.markdown("""
Websites are lively places. They also change the clock, shuffle a banner, and occasionally decide you are a robot. PagePulse tries to tell the plot from the confetti.

Each watch opens the public page in a browser, tidies the readable text, and compares it with the last saved version. A fingerprint catches exact repeats; a word-diff spots what moved. The interesting bits get a timestamp and screenshot in the local SQLite history, so every alert comes with receipts.
""")

guide_left, guide_mid, guide_right = st.columns(3)
with guide_left:
    with st.container(border=True):
        st.markdown("### 01 · Give it a watch")
        st.write("Choose a page and a scan interval from **5 minutes to 7 days**. The background radar checks on schedule while PagePulse is running. Add CSS selectors to zoom in on the useful part or ignore the noisy bits.")
with guide_mid:
    with st.container(border=True):
        st.markdown("### 02 · Let the noise settle")
        st.write("Tiny edits can be ignored with the word threshold. Bigger changes need to show up on **two scans in a row** before they join the version history. Repeated scans to one host get a cooldown, and one URL gets one monitor record.")
with guide_right:
    with st.container(border=True):
        st.markdown("### 03 · Keep the useful receipts")
        st.write("CAPTCHAs, blocks, and outages get their own status instead of pretending to be content. Keyword matches can flag a change; nearby numbers can become a chart; every watch can export an RSS feed. Optional AI adds a short change brief when configured.")

st.markdown("""
<div style="margin-top:12px;padding:20px 24px;border:1px solid #2c4861;border-radius:18px;background:linear-gradient(110deg,rgba(35,58,82,.58),rgba(16,29,49,.72));box-shadow:0 12px 40px #02081133">
<span class="pulse-kicker">A NOTE FROM THE RADAR ROOM</span><br>
<span style="display:block;margin-top:8px;color:#dce9f7;font-size:17px;line-height:1.7"><em>“PagePulse doesn’t try to understand the whole internet. It keeps the receipts, ignores the confetti, and taps you on the shoulder when the plot changes.”</em></span>
<span style="display:block;margin-top:12px;color:#8da5bd;font-size:13px">A practical little watcher, with a healthy suspicion of blinking timestamps.</span>
</div>
""", unsafe_allow_html=True)
