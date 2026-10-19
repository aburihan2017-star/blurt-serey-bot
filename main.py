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


def dismiss_welcome_banner(page):
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
            document.querySelectorAll('.no-cookie-notice-overlay, [class*="cookie"]').forEach(el => el.remove());
            document.body.style.overflow = 'auto';
            localStorage.setItem('serey_no_cookie_notice_seen', 'true');
        }"""
    )
    time.sleep(1)


def handle_login_modal(page):
    try:
        user_input = page.get_by_placeholder("Username")
        pass_input = page.get_by_placeholder("Private Key or Password")

        if user_input.count() > 0 and user_input.is_visible():
            print("🔑 সেরি Log In মোডাল সামনে এসেছে! ইউজারনেম ও পাসওয়ার্ড পূরণ করা হচ্ছে...", flush=True)
            user_input.click(force=True)
            user_input.fill(SEREY_USER)
            time.sleep(0.5)

            pass_input.click(force=True)
            pass_input.fill(SEREY_PASSWORD)
            time.sleep(0.5)

            print("🚀 নীল 'Log In' বাটনে ক্লিক করা হচ্ছে...", flush=True)
            login_btn = page.get_by_role("button", name="Log In", exact=True)
            if login_btn.count() > 0 and login_btn.is_visible():
                login_btn.click(force=True)
            else:
                pass_input.press("Enter")

            print("⏳ লগইন সম্পন্ন ও মোডাল বন্ধ হওয়ার অপেক্ষা...", flush=True)
            try:
                page.wait_for_selector("input[placeholder='Username']", state="hidden", timeout=15000)
                print("✅ লগইন মোডাল সফলভাবে বন্ধ হয়েছে!", flush=True)
            except Exception:
                pass
            time.sleep(3)
            return True
    except Exception as e:
        print(f"লগইন মোডাল নোটিশ: {e}", flush=True)
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

        context.add_init_script("""
            try {
                localStorage.setItem('serey_no_cookie_notice_seen', 'true');
            } catch(e) {}
        """)

        page = context.new_page()

        try:
            # ধাপ ১: সরাসরি পোস্ট লেখার পেজে যাওয়া
            print("✍️ পোস্ট লেখার পেজে যাওয়া হচ্ছে (/write/new)...", flush=True)
            page.goto("https://bengali.serey.io/write/new", timeout=45000, wait_until="domcontentloaded")
            time.sleep(4)

            dismiss_welcome_banner(page)

            # যদি পেজের উপরে 'Sign up / Log in' থাকে
            try:
                header_login = page.get_by_text("Sign up / Log in", exact=True)
                if header_login.count() > 0 and header_login.is_visible():
                    header_login.click(force=True)
                    time.sleep(2)
                    handle_login_modal(page)
            except Exception:
                pass

            # ধাপ ২: এডিটর ও ফর্ম লোড হওয়া পর্যন্ত অপেক্ষা
            print("⏳ এডিটর এবং ফর্ম লোড হওয়ার অপেক্ষা করা হচ্ছে...", flush=True)
            page.wait_for_selector(".ql-editor, div[contenteditable='true']", state="visible", timeout=30000)
            title_input = page.locator("textarea[name='title'], input[name='title'], textarea[placeholder*='itle' i], input[placeholder*='itle' i]").first
            title_input.wait_for(state="visible", timeout=30000)
            time.sleep(1)

            # টাইটেল বসানো (ক্লিক করে সরাসরি টাইপ করানো, যাতে React ভ্যালিডেশন সক্রিয় হয়)
            print("✍️ টাইটেল বসানো হচ্ছে...", flush=True)
            title_input.scroll_into_view_if_needed()
            title_input.click()
            title_input.fill(title)
            page.keyboard.press("Space")
            page.keyboard.press("Backspace")
            time.sleep(1)

            # এডিটরে বডি বসানো (Quill Editor API ও Clipboard ইভেন্ট নিশ্চিত করা)
            print("✍️ ব্লগের কন্টেন্ট বসানো হচ্ছে...", flush=True)
            editor = page.locator(".ql-editor, div[contenteditable='true']").first
            editor.scroll_into_view_if_needed()
            editor.click()

            # Quill বা ContentEditable এ সঠিকভাবে HTML ইনজেক্ট করা
            page.evaluate(
                """([html]) => {
                    const editor = document.querySelector('.ql-editor');
                    if (editor) {
                        editor.focus();
                        editor.innerHTML = html;
                        // React ও Quill এর ইভেন্ট ফায়ার করা
                        editor.dispatchEvent(new Event('input', { bubbles: true }));
                        editor.dispatchEvent(new Event('change', { bubbles: true }));
                    }
                }""",
                [formatted_body]
            )
            time.sleep(1)
            # এডিটরে একটি কার্সার হিট দিয়ে React স্টেট ট্রিগার করা
            editor.click()
            page.keyboard.press("End")
            page.keyboard.type(" ")
            time.sleep(2)

            # ধাপ ৩: স্ক্রোল করে প্রথম Publish বাটনে ক্লিক
            print("🚀 প্রথম Publish বাটন খোঁজা হচ্ছে...", flush=True)
            page.evaluate("window.scrollTo(0, document.body.scrollHeight);")
            time.sleep(1)

            # মূল পেজের নিচের Publish বাটন লোকেট করা
            pub_btn = page.locator("button:has-text('Publish'):not([disabled])").last
            if pub_btn.count() > 0:
                pub_btn.scroll_into_view_if_needed()
                time.sleep(1)
                pub_btn.click(force=True)
                print("✅ প্রথম Publish বাটনে ক্লিক সম্পন্ন!", flush=True)
            else:
                print("সতর্কতা: Playwright বাটন পায়নি, JS দিয়ে চেষ্টা করা হচ্ছে...", flush=True)
                page.evaluate("""() => {
                    const btns = Array.from(document.querySelectorAll('button'));
                    const b = btns.find(x => x.innerText.includes('Publish'));
                    if (b) b.click();
                }""")
            time.sleep(3)

            # যদি লগইন চায়
            logged_in_now = handle_login_modal(page)
            if logged_in_now:
                time.sleep(2)
                pub_btn = page.locator("button:has-text('Publish'):not([disabled])").last
                if pub_btn.count() > 0:
                    pub_btn.click(force=True)
                time.sleep(3)

            # ধাপ ৪: Preparing to publish বা ইমেজ প্রসেসিং চেক
            try:
                if page.locator("text='Preparing to publish'").count() > 0:
                    print("⏳ 'Preparing to publish' ইমেজ আপলোড শেষ হওয়ার অপেক্ষা করা হচ্ছে...", flush=True)
                    page.wait_for_selector("text='Preparing to publish'", state="detached", timeout=35000)
            except Exception:
                pass
            time.sleep(2)

            # ধাপ ৫: পপ-আপ মোডালের ভেতর ফাইনাল Publish বাটনে ক্লিক
            print("🎯 কনফার্মেশন/ক্যাটাগরি মোডালের ফাইনাল Publish বাটনে ক্লিক করার চেষ্টা...", flush=True)
            final_clicked = False
            modal_btn = page.locator(".ant-modal button:has-text('Publish'), [role='dialog'] button:has-text('Publish')").last
            if modal_btn.count() > 0 and modal_btn.is_visible():
                modal_btn.click(force=True)
                final_clicked = True
                print("✅ মোডালের ফাইনাল Publish বাটনে ক্লিক হয়েছে!", flush=True)
            
            if not final_clicked:
                # পেজের অন্য কোনো এক্টিভ Publish বাটন থাকলে ক্লিক
                page.evaluate("""() => {
                    const activeBtns = Array.from(document.querySelectorAll('.ant-modal button, [role="dialog"] button, button.ant-btn-primary'));
                    const target = activeBtns.find(b => b.innerText.includes('Publish'));
                    if (target) target.click();
                }""")

            # সাবমিটের পর পেজ আপডেট ও স্ক্রিনশট
            print("⏳ পোস্ট লাইভ হওয়া ও রিডাইরেক্টের অপেক্ষা করা হচ্ছে...", flush=True)
            for wait_round in range(1, 10):
                time.sleep(3)
                current_url = page.url.lower()

                # রিডাইরেক্ট হওয়া চেক
                if f"/authors/{SEREY_USER.lower()}" in current_url and "write" not in current_url:
                    print(f"🎉🎉 ব্রাউজার সফলভাবে পোস্ট পেজে রিডাইরেক্ট হয়েছে: {title}", flush=True)
                    page.screenshot(path="serey_post_result.png")
                    browser.close()
                    return True

                # সরাসরি API দিয়ে চেক
                if is_post_live_on_serey(title):
                    print(f"🎉🎉 পোস্টটি সেরি প্রোফাইলে লাইভ পাওয়া গেছে: {title}", flush=True)
                    page.screenshot(path="serey_post_result.png")
                    browser.close()
                    return True

                print(f"অপেক্ষা করা হচ্ছে ({wait_round}/9)...", flush=True)

            page.screenshot(path="serey_post_result.png")
            print("⚠️ সতর্কতা: পোস্টটি লাইভ হতে দেরি হচ্ছে, স্ক্রিনশট সংরক্ষণ করা হয়েছে।", flush=True)
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
