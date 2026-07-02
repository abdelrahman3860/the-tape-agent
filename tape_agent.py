#!/usr/bin/env python3
"""
THE TAPE — Autonomous Content Agent
Runs free on GitHub Actions. Pulls live market data, writes a sharp brand-voice
post with a free LLM (Groq, NVIDIA fallback), and publishes to Telegram (+ X when enabled).
No servers, no OpenClaw, no per-run model cost.
"""
import os, json, random, urllib.request, urllib.error, datetime

# ---------- config from environment (set these as GitHub Secrets) ----------
GROQ_API_KEY     = os.getenv("GROQ_API_KEY", "").strip()
NVIDIA_API_KEY   = os.getenv("NVIDIA_API_KEY", "").strip()   # optional free fallback brain
FINNHUB_API_KEY  = os.getenv("FINNHUB_API_KEY", "").strip()  # optional free news
TELEGRAM_TOKEN   = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
TELEGRAM_CHAT    = os.getenv("TELEGRAM_CHAT_ID", "").strip()

GROQ_MODEL   = "llama-3.3-70b-versatile"
NVIDIA_MODEL = "meta/llama-3.1-70b-instruct"

def http_json(url, data=None, headers=None, timeout=25):
    headers = headers or {}
    body = json.dumps(data).encode() if data is not None else None
    if body is not None:
        headers.setdefault("Content-Type", "application/json")
    req = urllib.request.Request(url, data=body, headers=headers, method="POST" if body else "GET")
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode())

# ---------- 1. gather live data (all free) ----------
def get_crypto():
    try:
        d = http_json("https://api.coingecko.com/api/v3/simple/price?ids=bitcoin,ethereum&vs_currencies=usd&include_24hr_change=true")
        btc, eth = d.get("bitcoin", {}), d.get("ethereum", {})
        def fmt(v): return f"${v:,.0f}" if isinstance(v, (int, float)) else "n/a"
        def pct(v): return (f"{v:+.1f}%") if isinstance(v, (int, float)) else ""
        return (f"BTC {fmt(btc.get('usd'))} (24h {pct(btc.get('usd_24h_change'))}) | "
                f"ETH {fmt(eth.get('usd'))} (24h {pct(eth.get('usd_24h_change'))})")
    except Exception as e:
        print("crypto fetch failed:", e); return ""

def get_news():
    if not FINNHUB_API_KEY:
        return ""
    try:
        d = http_json(f"https://finnhub.io/api/v1/news?category=general&token={FINNHUB_API_KEY}")
        heads = [x.get("headline", "") for x in d[:6] if x.get("headline")]
        return "\n".join(f"- {h}" for h in heads)
    except Exception as e:
        print("news fetch failed:", e); return ""

# ---------- 2. write the post (free LLM, Groq primary / NVIDIA fallback) ----------
SYSTEM = (
    "You are The Tape, a faceless markets X account in the style of The Kobeissi Letter mixed with "
    "the punch of a sharp macro trader. Using ONLY the live data and headlines provided, write ONE post "
    "under 270 characters. Lead with a real number or a real headline. Dry, opinionated, authoritative; "
    "one idea; numbers and concepts over adjectives. Do NOT invent any number that is not in the data. "
    "Add '(not advice)' if it reads like a call. No emojis, no hashtags, no links, no surrounding quotes. "
    "Occasionally instead write a punchy one-line market/trading-psychology truth (no data needed). "
    "Output ONLY the post text."
)

def llm(messages):
    # try Groq first
    if GROQ_API_KEY:
        try:
            out = http_json("https://api.groq.com/openai/v1/chat/completions",
                            {"model": GROQ_MODEL, "temperature": 0.85, "messages": messages},
                            {"Authorization": f"Bearer {GROQ_API_KEY}"})
            return out["choices"][0]["message"]["content"].strip()
        except Exception as e:
            print("Groq failed, trying NVIDIA:", e)
    # fallback: NVIDIA NIM (free, OpenAI-compatible)
    if NVIDIA_API_KEY:
        try:
            out = http_json("https://integrate.api.nvidia.com/v1/chat/completions",
                            {"model": NVIDIA_MODEL, "temperature": 0.85, "messages": messages},
                            {"Authorization": f"Bearer {NVIDIA_API_KEY}"})
            return out["choices"][0]["message"]["content"].strip()
        except Exception as e:
            print("NVIDIA failed:", e)
    return ""

def clean(txt):
    txt = txt.strip()
    if len(txt) > 1 and txt[0] in "\"'" and txt[-1] in "\"'":
        txt = txt[1:-1].strip()
    return txt[:275]

# ---------- 3. publish ----------
def post_telegram(text):
    if not (TELEGRAM_TOKEN and TELEGRAM_CHAT):
        print("Telegram not configured, skipping"); return False
    try:
        http_json(f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage",
                  {"chat_id": TELEGRAM_CHAT, "text": text, "disable_web_page_preview": True})
        print("posted to Telegram"); return True
    except Exception as e:
        print("Telegram post failed:", e); return False

# X posting: enabled later. When X access is available, drop the logic here
# (API tweepy call, or a Playwright browser step). For now the agent runs Telegram-first, zero ban risk.
def post_x(text):
    print("X posting not enabled yet (waiting on API access / browser module). Post was:\n", text)
    return False

def main():
    crypto = get_crypto()
    news = get_news()
    data = "LIVE DATA (use only these real numbers, invent nothing):\n"
    data += (crypto + "\n") if crypto else ""
    data += ("TOP HEADLINES:\n" + news) if news else ""
    if not crypto and not news:
        data = "No fresh data this run. Write a punchy one-line market/trading-psychology truth instead."

    post = clean(llm([{"role": "system", "content": SYSTEM}, {"role": "user", "content": data}]))
    if not post:
        print("no post generated (no working LLM key?)"); return

    stamp = datetime.datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC")
    print(f"[{stamp}] POST:\n{post}\n")
    post_telegram(post)
    post_x(post)

    # append to a local log (committed back by the workflow, optional)
    try:
        with open("posts_log.md", "a") as f:
            f.write(f"\n**{stamp}**\n{post}\n")
    except Exception:
        pass

if __name__ == "__main__":
    main()
