import json
import os
import re
import time
from datetime import datetime, timedelta
import requests
from playwright.sync_api import sync_playwright

# কনফিগারেশন
BLURT_USER = "aburihan1"
SEREY_USER = os.environ.get("SEREY_USERNAME", "raihan123")
SEREY_PASSWORD = os.environ.get("SEREY_POSTING_KEY")

BLURT_NODES = [
    "https://rpc.blurt.blog",
    "https://rpc.beblurt.com",
    "https://blurtrpc.dagobert.uk",
]

DATA_FILE = "automation_data.json"
MAX_DAILY_POSTS = 2
DAY_IN_SECONDS = 72000

BASE_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Accept": "application/json, text/plain, */*",
}


def blurt_call(method, params):
    payload = {"jsonrpc": "2.0", "method": method, "params": params, "id": 1}
    for node in BLURT_NODES:
        try:
            res = requests.post(node, json=payload, timeout=8).json()
            if "result" in res and res["result"]:
                return res["result"]
        except Exception:
            continue
    return None


def load_data():
    if os.path.exists(DATA_FILE):
        try:
            with open(DATA_FILE, "r") as f:
                return json.load(f)
        except Exception:
            pass
    return {"queue": [], "posted": [], "timestamps": []}


def save_data(data):
    with open(DATA_FILE, "w") as f:
        json.dump(data, f, indent=2)


def fetch_blurt_posts(posted_set):
    """ব্লার্ট লাইভ নোড থেকে aburihan1 এর ১ বছর আগের পোস্ট সংগ্রহ"""
    print("📡 ব্লার্ট লাইভ নোড থেকে পোস্ট খোঁজা হচ্ছে...")
    one_year_ago = datetime.utcnow() - timedelta(days=365)
    before_date = one_year_ago.strftime("%Y-%m-%dT%H:%M:%S")

    posts = blurt_call(
        "condenser_api.get_discussions_by_author_before_date",
        [BLURT_USER, "", before_date, 100],
    )

    if not posts:
        posts = blurt_call(
            "condenser_api.get_discussions_by_blog",
            [{"tag": BLURT_USER, "limit": 100}],
        )

    if posts:
        new_permlinks = []
        for p in reversed(posts):
            plink = p.get("permlink")
            if plink and plink not in posted_set and plink not in new_permlinks:
                new_permlinks.append(plink)
        print(f"✅ ব্লার্ট থেকে {len(new_permlinks)}টি পোস্ট পাওয়া গেছে!")
        return new_permlinks
    return []


def get_post_details(permlink):
    return blurt_call("condenser_api.get_content", [BLURT_USER, permlink])


def get_serey_auth_token():
    """সেরি এপিআই থেকে টোকেন সংগ্রহ"""
    login_url = "https://global-api.serey.io/api/v2/auth/login"
    payload = {"username": SEREY_USER, "password": SEREY_PASSWORD}
    try:
        r = requests.post(login_url, json=payload, headers=BASE_HEADERS, timeout=25)
        if r.status_code in [200, 201]:
            d = r.json()
            return d.get("token") or d.get("accessToken") or (d.get("data", {}).get("token") if isinstance(d.get("data"), dict) else None)
    except Exception:
        pass
    return None


def post_with_browser(title, body, token):
    """ভার্চুয়াল ব্রাউজারের মাধ্যমে সরাসরি সেরি পেজে পোস্ট করা"""
    print("🌐 ভার্চুয়াল ক্রোম ব্রাউজার চালু করা হচ্ছে...")

    # HTML ফরম্যাটিং
    formatted_body = body
    if not ("<p>" in formatted_body or "<div>" in formatted_body):
        formatted_body = f"<p>{body.replace(chr(10) + chr(10), '</p><p>').replace(chr(10), '<br/>')}</p>"

    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=True,
            args=[
                "--no-sandbox",
                "--disable-setuid-sandbox",
                "--disable-dev-shm-usage",
                "--disable-blink-features=AutomationControlled",
            ],
        )

        context = browser.new_context(
            viewport={"width": 1280, "height": 800},
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
        )

        page = context.new_page()

        try:
            print("🔗 সেরি রাইট পেজে যাওয়া হচ্ছে...")
            page.goto("https://bengali.serey.io/write/new", timeout=45000, wait_until="domcontentloaded")
            time.sleep(3)

            # লগইন টোকেন ব্রাউজার স্টোরেজ ও কুকিতে ইনজেক্ট করা
            if token:
                page.evaluate(
                    f"""() => {{
                        localStorage.setItem('token', '{token}');
                        localStorage.setItem('accessToken', '{token}');
                    }}"""
                )
                context.add_cookies([
                    {"name": "token", "value": token, "domain": ".serey.io", "path": "/"},
                    {"name": "accessToken", "value": token, "domain": ".serey.io", "path": "/"},
                ])

            # পেজ রিলোড নিশ্চিত করতে
            page.goto("https://bengali.serey.io/write/new", timeout=45000, wait_until="networkidle")
            time.sleep(4)

            # যদি লগইন পেজে রিডাইরেক্ট করে থাকে, তবে ব্রাউজারে লগইন করা
            if "login" in page.url or page.locator("input[type='password']").count() > 0:
                print("🔑 ব্রাউজারে লগইন সম্পন্ন করা হচ্ছে...")
                user_input = page.locator("input[type='text'], input[name='username'], input[placeholder*='sername' i]").first
                pass_input = page.locator("input[type='password']").first
                if user_input.count() > 0 and pass_input.count() > 0:
                    user_input.fill(SEREY_USER)
                    pass_input.fill(SEREY_PASSWORD)
                    time.sleep(1)
                    page.locator("button[type='submit'], button:has-text('Login'), button:has-text('Sign In')").first.click()
                    page.wait_for_load_state("networkidle", timeout=20000)
                    time.sleep(3)
                    page.goto("https://bengali.serey.io/write/new", timeout=45000, wait_until="networkidle")
                    time.sleep(3)

            print("✍️ টাইটেল ও পোস্টের বিষয়বস্তু পেস্ট করা হচ্ছে...")

            # ১. টাইটেল ইনপুট
            title_input = page.locator("input[placeholder*='itle' i], input[name='title'], textarea[placeholder*='itle' i]").first
            if title_input.count() > 0:
                title_input.click()
                title_input.fill(title)
            else:
                # ফলব্যাক হিসেবে প্রথম টেক্সট ইনপুট
                page.locator("input[type='text']").first.fill(title)

            time.sleep(1)

            # ২. Quill এডিটরে বডি বসানো
            editor = page.locator(".ql-editor, div[contenteditable='true']").first
            if editor.count() > 0:
                editor.click()
                # কন্টেন্ট সরাসরি এডিটরে ইনজেক্ট
                page.evaluate(
                    """([selector, html]) => {
                        const el = document.querySelector(selector);
                        if (el) { el.innerHTML = html; el.dispatchEvent(new Event('input', { bubbles: true })); }
                    }""",
                    [".ql-editor", formatted_body]
                )
            time.sleep(2)

            # ৩. নিচে থাকা প্রথম "Publish" বাটনে ক্লিক (যা ক্যাটাগরি মোডাল খোলে)
            print("🚀 প্রথম Publish বাটনে ক্লিক করা হচ্ছে...")
            publish_btn = page.locator("button:has-text('Publish')").last
            publish_btn.scroll_into_view_if_needed()
            publish_btn.click()
            time.sleep(3)

            # ৪. মোডাল পপ-আপের নীল "Publish" বাটনে ক্লিক
            print("🎯 মোডাল কনফার্ম করে ফাইনাল Publish বাটনে ক্লিক করা হচ্ছে...")
            # মোডালের ভেতরের নীল বাটন
            modal_publish_btn = page.locator("div[role='dialog'] button:has-text('Publish'), .ant-modal button:has-text('Publish'), button:has-text('Publish')").last
            modal_publish_btn.click()

            # ৫. সফলতার নোটিফিকেশন চেক (Success toast / redirect)
            print("⏳ পোস্ট সফল হওয়ার নোটিফিকেশনের অপেক্ষা করা হচ্ছে...")
            for _ in range(15):
                time.sleep(2)
                page_text = page.content().lower()
                if (
                    "successfully" in page_text
                    or "success" in page_text
                    or "/authors/" in page.url
                    or "article" in page_text
                ):
                    print(f"🎉🎉 ব্রাউজার অটোমেশন দিয়ে পোস্টটি ১০০% সফলভাবে লাইভ হয়েছে: {title}")
                    browser.close()
                    return True

            # পেজ ইউআরএল পরিবর্তিত হয়ে লেখকের প্রোফাইলে গেলে সফল
            if SEREY_USER in page.url and "write" not in page.url:
                print(f"🎉🎉 পোস্ট সফলভাবে লাইভ হয়ে প্রোফাইল পেজে চলে গেছে: {title}")
                browser.close()
                return True

            print("সতর্কতা: পাবলিশ বাটন চাপার পর কনফার্মেশন পাওয়া যায়নি।")
        except Exception as e:
            print(f"❌ ব্রাউজার অটোমেশন এরর: {e}")
        finally:
            browser.close()

    return False


def main():
    print("বট চালু হচ্ছে...")
    if not SEREY_PASSWORD:
        print("ত্রুটি: SEREY_POSTING_KEY পাওয়া যায়নি!")
        return

    data = load_data()

    # দৈনিক সীমা চেক
    current_time = time.time()
    data["timestamps"] = [t for t in data.get("timestamps", []) if current_time - t < DAY_IN_SECONDS]

    if len(data["timestamps"]) >= MAX_DAILY_POSTS:
        print(f"আজকের দৈনিক সীমা ({MAX_DAILY_POSTS} টি পোস্ট) পূর্ণ হয়েছে।")
        return

    posted_set = set(data.get("posted", []))

    if not data.get("queue"):
        fetched_permlinks = fetch_blurt_posts(posted_set)
        data["queue"] = fetched_permlinks
        save_data(data)

    if not data["queue"]:
        print("পোস্ট করার মতো কোনো নতুন পোস্ট পাওয়া যায়নি।")
        return

    permlink_to_post = data["queue"].pop(0)
    post_info = get_post_details(permlink_to_post)

    if not post_info or "title" not in post_info:
        data.setdefault("posted", []).append(permlink_to_post)
        save_d
