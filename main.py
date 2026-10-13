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


def is_post_live_on_serey(title):
    try:
        url = f"https://global-api.serey.io/api/v2/serey-web/list-by-author?author={SEREY_USER}&limit=5&offset=0"
        r = requests.get(url, headers=BASE_HEADERS, timeout=12)
        if r.status_code == 200:
            posts = r.json().get("posts", [])
            for p in posts:
                p_title = p.get("title", "")
                if title.strip().lower() in p_title.strip().lower() or p_title.strip().lower() in title.strip().lower():
                    return True
    except Exception:
        pass
    return False


def dismiss_welcome_modal(page):
    """Welcome to Serey ব্যানার ও কুকি ওভারলে বন্ধ করা"""
    try:
        close_btn = page.locator("button:has-text('Close'), .no-cookie-notice-overlay button:has-text('Close')").first
        if close_btn.count() > 0 and close_btn.is_visible():
            print("🍪 'Welcome to Serey' ব্যানার বন্ধ করা হচ্ছে...", flush=True)
            close_btn.click(force=True)
            time.sleep(1)
    except Exception:
        pass

    page.evaluate(
        """() => {
            document.querySelectorAll('.no-cookie-notice-overlay, [class*="cookie-notice"]').forEach(el => el.remove());
            document.body.style.overflow = 'auto';
            localStorage.setItem('serey_no_cookie_notice_seen', 'true');
        }"""
    )
    time.sleep(1)


def perform_browser_login(page):
    """হোমপেজে নিশ্চিতভাবে আসল লগইন সম্পন্ন করা"""
    print("🔑 সেরি সাইটে আসল ব্রাউজার লগইন পরীক্ষা করা হচ্ছে...", flush=True)

    # ১. যদি অলরেডি লগইন থাকে
    if page.locator(f"text='{SEREY_USER}'").count() > 0:
        print("✅ অলরেডি লগইন অবস্থায় রয়েছে!", flush=True)
        return True

    # ২. 'Sign up / Log in' বাটন দৃশ্যমান হওয়া পর্যন্ত স্পষ্ট অপেক্ষা
    try:
        print("⏳ 'Sign up / Log in' বাটন আসার অপেক্ষা করা হচ্ছে...", flush=True)
        login_btn = page.wait_for_selector(
            "text='Sign up / Log in', button:has-text('Sign up / Log in'), a:has-text('Sign up / Log in')",
            state="visible",
            timeout=15000,
        )
        if login_btn:
            print("🔑 'Sign up / Log in' বাটনে ক্লিক করা হচ্ছে...", flush=True)
            login_btn.click()
            time.sleep(2)
    except Exception as e:
        print(f"লগইন বাটন নোটিশ: {e}", flush=True)

    # ৩. লগইন মোডাল আসার অপেক্ষা ও তথ্য পূরণ
    try:
        print("⏳ লগইন মোডাল আসার অপেক্ষা করা হচ্ছে...", flush=True)
        user_field = page.wait_for_selector("input[placeholder='Username'], input[name='username']", state="visible", timeout=12000)
        pass_field = page.wait_for_selector("input[placeholder='Private Key or Password'], input[type='password']", state="visible", timeout=12000)

        if user_field and pass_field:
            print("✍️ ইউজারনেম ও পাসওয়ার্ড টাইপ করা হচ্ছে...", flush=True)
            user_field.click()
            user_field.press_sequentially(SEREY_USER, delay=35)
            time.sleep(0.5)

            pass_field.click()
            pass_field.press_sequentially(SEREY_PASSWORD, delay=35)
            time.sleep(0.5)

            # নীল Log In বাটনে ক্লিক
            print("🚀 নীল 'Log In' বাটনে ক্লিক করা হচ্ছে...", flush=True)
            submit_btn = page.locator("div[role='dialog'] button:has-text('Log In'), .ant-modal button:has-text('Log In'), button:has-text('Log In')").first
            submit_btn.click(force=True)

            # প্রোফাইল লোড হওয়া পর্যন্ত নিশ্চিত অপেক্ষা
            print("⏳ প্রোফাইল লোড হওয়ার অপেক্ষা...", flush=True)
            page.wait_for_selector(f"text='{SEREY_USER}'", state="visible", timeout=18000)
            print("✅ ব্রাউজারে সফলভাবে লগইন কনফার্ম হয়েছে!", flush=True)
            return True
    except Exception as err:
        print(f"লগইন সম্পন্ন করার নোটিশ: {err}", flush=True)

    return False


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
            # ধাপ ১: সেরি হোমপেজে গিয়ে লগইন নিশ্চিত করা
            print("🔗 সেরি হোমপেজে যাওয়া হচ্ছে...", flush=True)
            page.goto("https://bengali.serey.io", timeout=45000, wait_until="domcontentloaded")
            time.sleep(3)
            dismiss_welcome_modal(page)

            # হোমপেজেই আসল সাইন-ইন সম্পন্ন ও নিশ্চিত করা
            perform_browser_login(page)
            dismiss_welcome_modal(page)

            # ধাপ ২: নিশ্চিত লগইন অবস্থায় লেখার পেজে যাওয়া
            print("✍️ পোস্ট লেখার পেজে যাওয়া হচ্ছে (/write/new)...", flush=True)
            page.goto("https://bengali.serey.io/write/new", timeout=45000, wait_until="domcontentloaded")
            time.sleep(3)
            dismiss_welcome_modal(page)

            # এডিটর লোড হওয়া পর্যন্ত অপেক্ষা
            print("⏳ এডিটর এবং ফর্ম লোড হওয়ার অপেক্ষা করা হচ্ছে...", flush=True)
            page.wait_for_selector(".ql-editor, div[contenteditable='true']", state="visible", timeout=30000)
            page.wait_for_selector("textarea[name='title'], input[name='title'], textarea[placeholder*='itle' i], input[placeholder*='itle' i]", state="visible", timeout=30000)
            time.sleep(1)

            # টাইটেল বসানো
            print("✍️ টাইটেল বসানো হচ্ছে...", flush=True)
            title_input = page.locator("textarea[name='title'], input[name='title'], textarea[placeholder*='itle' i], input[placeholder*='itle' i]").first
            title_input.scroll_into_view_if_needed()
            title_input.click(force=True)
            title_input.fill(title, force=True)
            time.sleep(1)

            # এডিটরে বডি বসানো
            print("✍️ ব্লগের কন্টেন্ট বসানো হচ্ছে...", flush=True)
            editor = page.locator(".ql-editor, div[contenteditable='true']").first
            editor.scroll_into_view_if_needed()
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

            # ধাপ ৩: নিচে স্ক্রোল করে প্রথম Publish বাটনে ক্লিক
            print("🚀 প্রথম Publish বাটনে ক্লিক করা হচ্ছে...", flush=True)
            page.evaluate(
                """() => {
                    window.scrollTo(0, document.body.scrollHeight);
                    const btns = Array.from(document.querySelectorAll('button'));
                    const pubBtn = btns.find(b => b.textContent.trim() === 'Publish');
                    if (pubBtn) pubBtn.click();
                }"""
            )
            time.sleep(3)

            # ধাপ ৪: মোডাল পপ-আপের ফাইনাল নীল Publish বাটনে ক্লিক
            print("🎯 মোডাল পপ-আপে ফাইনাল Publish বাটনে ক্লিক করা হচ্ছে...", flush=True)
            page.wait_for_selector(".modal-publish-category, div[role='dialog'], .ant-modal", state="visible", timeout=15000)
            time.sleep(1)

            page.evaluate(
                """() => {
                    const modal = document.querySelector('.modal-publish-category, div[role="dialog"], .ant-modal');
                    if (modal) {
                        const btns = Array.from(modal.querySelectorAll('button'));
                        const finalBtn = btns.find(b => b.textContent.trim() === 'Publish');
                        if (finalBtn) {
                            finalBtn.click();
                        } else if (btns.length > 0) {
                            btns[btns.length - 1].click();
                        }
                    }
                }"""
            )

            # সাবমিটের পর অপেক্ষা ও স্ক্রিনশট
            print("⏳ পোস্ট লাইভ হওয়ার অপেক্ষা করা হচ্ছে...", flush=True)
            time.sleep(6)
            page.screenshot(path="serey_post_result.png")

            # ধাপ ৫: সরাসরি প্রোফাইল ডাটাবেজ চেক করে শতভাগ নিশ্চিত হওয়া
            print("🔍 সেরি প্রোফাইল ডাটাবেজে পোস্ট লাইভ হয়েছে কিনা চেক করা হচ্ছে...", flush=True)
            for wait_round in range(1, 6):
                time.sleep(4)
                if is_post_live_on_serey(title):
                    print(f"🎉🎉 পোস্টটি ১০০% নিশ্চিতভাবে সেরি প্রোফাইলে লাইভ পাওয়া গেছে: {title}", flush=True)
                    browser.close()
                    return True
                print(f"অপেক্ষা করা হচ্ছে ({wait_round}/5)...", flush=True)

            if f"/authors/{SEREY_USER.lower()}" in page.url.lower() and "write" not in page.url.lower():
                print(f"🎉🎉 ব্রাউজার সফলভাবে পোস্ট পেজে রিডাইরেক্ট হয়েছে: {title}", flush=True)
                browser.close()
                return True

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

    print(f"\nপ্রসেস করা হচ্ছে: {title}")
    success = post_with_browser(title, body)

    if success:
        data.setdefault("posted", []).append(permlink_to_post)
        data.setdefault("timestamps", []).append(current_time)
        print("ডাটা সেভ করা হয়েছে।")
    else:
        data["queue"].append(permlink_to_post)

    save_data(data)
    print("\nপ্রক্রিয়া সম্পূর্ণ হয়েছে।")


if __name__ == "__main__":
    main()
