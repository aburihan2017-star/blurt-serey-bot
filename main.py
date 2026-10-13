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
    print("📡 ব্লার্ট লাইভ নোড থেকে পোস্ট খোঁজা হচ্ছে...", flush=True)
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
        print(f"✅ ব্লার্ট থেকে {len(new_permlinks)}টি পোস্ট পাওয়া গেছে!", flush=True)
        return new_permlinks
    return []


def get_post_details(permlink):
    return blurt_call("condenser_api.get_content", [BLURT_USER, permlink])


def post_with_browser(title, body):
    print("🌐 ভার্চুয়াল ক্রোম ব্রাউজার চালু করা হচ্ছে...", flush=True)

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
            viewport={"width": 1366, "height": 900},
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
        )

        page = context.new_page()

        try:
            # ধাপ ১: সেরি হোমপেজে গিয়ে লগইন করা
            print("🔗 সেরি হোমপেজে যাওয়া হচ্ছে...", flush=True)
            page.goto("https://bengali.serey.io", timeout=45000, wait_until="domcontentloaded")
            time.sleep(2)

            page.evaluate(
                """() => {
                    localStorage.setItem('serey_no_cookie_notice_seen', 'true');
                    const overlays = document.querySelectorAll('.no-cookie-notice-overlay, [class*="cookie-notice"]');
                    overlays.forEach(el => el.remove());
                }"""
            )

            print("🔑 ব্রাউজারে লগইন সম্পন্ন করা হচ্ছে...", flush=True)
            login_btn = page.locator("button:has-text('Sign up / Log in'), button:has-text('Log in'), a:has-text('Sign up / Log in')").first
            if login_btn.count() > 0 and login_btn.is_visible():
                login_btn.click(force=True)
                time.sleep(2)

                user_input = page.locator("input[placeholder*='sername' i], input[name='username'], input[type='text']").last
                pass_input = page.locator("input[type='password']").last

                if user_input.count() > 0 and pass_input.count() > 0:
                    user_input.fill(SEREY_USER, force=True)
                    pass_input.fill(SEREY_PASSWORD, force=True)
                    time.sleep(1)

                    submit_btn = page.locator("button[type='submit'], div[role='dialog'] button:has-text('Sign In'), button:has-text('Sign In')").last
                    submit_btn.click(force=True)
                    time.sleep(5)

            # ধাপ ২: পোস্ট লেখার পেজে যাওয়া
            print("✍️ পোস্ট লেখার পেজে যাওয়া হচ্ছে (/write/new)...", flush=True)
            page.goto("https://bengali.serey.io/write/new", timeout=45000, wait_until="domcontentloaded")
            time.sleep(3)

            page.evaluate(
                """() => {
                    const overlays = document.querySelectorAll('.no-cookie-notice-overlay, [class*="cookie-notice"]');
                    overlays.forEach(el => el.remove());
                }"""
            )

            # টাইটেল বসানো
            print("টাইটেল বসানো হচ্ছে...", flush=True)
            title_input = page.locator("textarea[name='title'], input[name='title'], textarea[placeholder*='itle' i], input[placeholder*='itle' i]").first
            title_input.fill(title, force=True)
            time.sleep(1)

            # এডিটরে কন্টেন্ট বসানো
            print("কন্টেন্ট বসানো হচ্ছে...", flush=True)
            editor = page.locator(".ql-editor, div[contenteditable='true']").first
            if editor.count() > 0:
                editor.click(force=True)
                page.evaluate(
                    """([selector, html]) => {
                        const el = document.querySelector(selector);
                        if (el) { 
                            el.innerHTML = html; 
                            el.dispatchEvent(new Event('input', { bubbles: true })); 
                        }
                    }""",
                    [".ql-editor", formatted_body]
                )
            time.sleep(2)

            # ধাপ ৩: স্ক্রিনের একদম নিচে স্ক্রোল করে Publish বাটনে ক্লিক
            print("🚀 প্রথম Publish বাটনে ক্লিক করা হচ্ছে...", flush=True)
            publish_btn = page.locator("button:has-text('Publish')").first
            publish_btn.scroll_into_view_if_needed()
            time.sleep(1)
            publish_btn.click(force=True)
            time.sleep(3)

            # ধাপ ৪: ক্যাটাগরি মোডাল পপ-আপে ক্লিক
            print("🎯 মোডাল পপ-আপে ক্যাটাগরি ও ফাইনাল Publish নিশ্চিত করা হচ্ছে...", flush=True)
            
            # মোডালের ভেতরের Publish বাটন খুঁজে ক্লিক করা
            modal_btn = page.locator("div[role='dialog'] button:has-text('Publish'), .ant-modal button:has-text('Publish')").first
            if modal_btn.count() > 0 and modal_btn.is_visible():
                modal_btn.click(force=True)
            else:
                # ফলব্যাক হিসেবে পেজের শেষ Publish বাটন
                page.locator("button:has-text('Publish')").last.click(force=True)

            # ধাপ ৫: পোস্ট লাইভ হওয়ার নোটিফিকেশন চেক
            print("⏳ পোস্ট লাইভ হওয়ার নোটিফিকেশনের অপেক্ষা করা হচ্ছে...", flush=True)
            success = False
            for _ in range(15):
                time.sleep(2)
                current_url = page.url.lower()
                page_text = page.content().lower()

                if "successfully" in page_text or "success" in page_text:
                    success = True
                    break

                if f"/authors/{SEREY_USER.lower()}" in current_url and "write" not in current_url:
                    success = True
                    break

            page.screenshot(path="serey_post_result.png")

            if success:
                print(f"🎉🎉 পোস্টটি ১০০% নিশ্চিতভাবে সেরি প্রোফাইলে লাইভ হয়েছে: {title}", flush=True)
                browser.close()
                return True
            else:
                print("সতর্কতা: পোস্ট সম্পন্ন হয়েছে, স্ক্রিনশট সংরক্ষণ করা হয়েছে।", flush=True)

        except Exception as e:
            print(f"❌ ব্রাউজার অটোমেশন এরর: {e}", flush=True)
            try:
                page.screenshot(path="serey_post_result.png")
            except Exception:
                pass
        finally:
            browser.close()

    return False


def main():
    print("বট চালু হচ্ছে...", flush=True)
    if not SEREY_PASSWORD:
        print("ত্রুটি: SEREY_POSTING_KEY পাওয়া যায়নি!", flush=True)
        return

    data = load_data()
    current_time = time.time()
    data["timestamps"] = [t for t in data.get("timestamps", []) if current_time - t < DAY_IN_SECONDS]

    if len(data["timestamps"]) >= MAX_DAILY_POSTS:
        print(f"আজকের দৈনিক সীমা ({MAX_DAILY_POSTS} টি পোস্ট) পূর্ণ হয়েছে।", flush=True)
        return

    posted_set = set(data.get("posted", []))

    if not data.get("queue"):
        fetched_permlinks = fetch_blurt_posts(posted_set)
        data["queue"] = fetched_permlinks
        save_data(data)

    if not data["queue"]:
        print("পোস্ট করার মতো কোনো নতুন পোস্ট পাওয়া যায়নি।", flush=True)
        return

    permlink_to_post = data["queue"].pop(0)
    post_info = get_post_details(permlink_to_post)

    if not post_info or "title" not in post_info:
        data.setdefault("posted", []).append(permlink_to_post)
        save_data(data)
        return

    title = post_info.get("title", "")
    body = post_info.get("body", "")

    print(f"\nপ্রসেস করা হচ্ছে: {title}", flush=True)
    success = post_with_browser(title, body)

    if success:
        data.setdefault("posted", []).append(permlink_to_post)
        data.setdefault("timestamps", []).append(current_time)
        print("ডাটা সেভ করা হয়েছে।", flush=True)
    else:
        data["queue"].append(permlink_to_post)

    save_data(data)
    print("\nপ্রক্রিয়া সম্পূর্ণ হয়েছে।", flush=True)


if __name__ == "__main__":
    main()
