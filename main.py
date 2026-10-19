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
        r = requests.get(url, headers=BASE_HEADERS, timeout=10)
        if r.status_code == 200:
            posts = r.json().get("posts", [])
            for p in posts:
                p_title = p.get("title", "")
                if title.strip().lower() in p_title.strip().lower() or p_title.strip().lower() in title.strip().lower():
                    return True
    except Exception:
        pass
    return False


def extract_first_image_url(body, json_metadata_str):
    try:
        meta = json.loads(json_metadata_str or "{}")
        images = meta.get("image") or meta.get("images")
        if images and isinstance(images, list) and len(images) > 0:
            if isinstance(images[0], str) and images[0].startswith("http"):
                return images[0].strip()
    except Exception:
        pass

    md_match = re.search(r'!\[.*?\]\((https?://[^\s\)]+)\)', body)
    if md_match:
        return md_match.group(1).split('"')[0].split("'")[0].strip()

    html_match = re.search(r'<img[^>]+src=["\'](https?://[^"\'>\s]+)["\']', body, re.IGNORECASE)
    if html_match:
        return html_match.group(1).strip()

    raw_match = re.search(r'https?://[^\s"\'\)]+\.(?:jpg|jpeg|png|webp)', body, re.IGNORECASE)
    if raw_match:
        return raw_match.group(0).strip()

    return None


def download_thumbnail_file(page, img_url):
    if not img_url:
        return None
    try:
        print(f"📥 থাম্বনেইল ছবি ডাউনলোড করা হচ্ছে: {img_url}", flush=True)
        resp = page.request.get(img_url, timeout=15000)
        if resp.status == 200:
            body_bytes = resp.body()
            if len(body_bytes) > 500:
                ext = ".png" if ".png" in img_url.lower() else ".jpg"
                file_path = os.path.abspath(f"serey_thumb{ext}")
                with open(file_path, "wb") as f:
                    f.write(body_bytes)
                print(f"✅ থাম্বনেইল ছবি প্রস্তুত ({len(body_bytes)} bytes)!", flush=True)
                return file_path
    except Exception as e:
        print(f"ছবি ডাউনলোড নোটিশ: {e}", flush=True)
    return None


def dismiss_welcome_banner(page):
    try:
        page.evaluate(
            """() => {
                const closeBtn = Array.from(document.querySelectorAll('button')).find(b => b.textContent.trim() === 'Close');
                if (closeBtn) closeBtn.click();
                document.querySelectorAll('.no-cookie-notice-overlay, [class*="cookie"]').forEach(el => el.remove());
                document.body.style.overflow = 'auto';
                localStorage.setItem('serey_no_cookie_notice_seen', 'true');
            }"""
        )
        time.sleep(1)
    except Exception:
        pass


def perform_login(page):
    """হোমপেজে নিশ্চিত লগইন সম্পন্ন করা"""
    if page.locator(f"text='{SEREY_USER}'").count() > 0:
        return True

    dismiss_welcome_banner(page)

    try:
        login_btn = page.locator("text='Sign up / Log in', button:has-text('Sign up / Log in')").first
        if login_btn.count() > 0 and login_btn.is_visible():
            login_btn.click(force=True)
            time.sleep(2)

        user_field = page.locator("input[placeholder='Username'], input[name='username']").first
        pass_field = page.locator("input[placeholder='Private Key or Password'], input[type='password']").first

        if user_field.count() > 0 and user_field.is_visible():
            user_field.fill(SEREY_USER, force=True)
            time.sleep(0.5)
            pass_field.fill(SEREY_PASSWORD, force=True)
            time.sleep(0.5)

            submit_btn = page.locator("div[role='dialog'] button:has-text('Log In'), .ant-modal button:has-text('Log In')").first
            submit_btn.click(force=True)
            time.sleep(4)
    except Exception:
        pass
    return False


def post_with_browser(title, body, img_url):
    print("🌐 ভার্চুয়াল ক্রোম ব্রাউজার চালু করা হচ্ছে...", flush=True)

    formatted_body = body
    if not ("<p>" in formatted_body or "<div>" in formatted_body):
        formatted_body = f"<p>{body.replace(chr(10) + chr(10), '</p><p>').replace(chr(10), '<br/>')}</p>"

    thumb_file = None

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
            viewport={"width": 1366, "height": 950},
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
        )

        context.add_init_script("""
            try {
                localStorage.setItem('serey_no_cookie_notice_seen', 'true');
            } catch(e) {}
        """)

        page = context.new_page()

        try:
            # ছবি ডাউনলোড
            if img_url:
                thumb_file = download_thumbnail_file(page, img_url)

            # ধাপ ১: সেরি হোমপেজে গিয়ে লগইন নিশ্চিত করা
            print("🔗 সেরি হোমপেজে লগইন নিশ্চিত করা হচ্ছে...", flush=True)
            page.goto("https://bengali.serey.io", timeout=35000, wait_until="domcontentloaded")
            time.sleep(2)
            dismiss_welcome_banner(page)
            perform_login(page)

            # ধাপ ২: পোস্ট লেখার পেজে যাওয়া
            print("✍️ পোস্ট লেখার পেজে যাওয়া হচ্ছে (/write/new)...", flush=True)
            page.goto("https://bengali.serey.io/write/new", timeout=35000, wait_until="domcontentloaded")
            time.sleep(2)
            dismiss_welcome_banner(page)

            # এডিটর লোড হওয়া
            print("⏳ এডিটর লোড হওয়ার অপেক্ষা...", flush=True)
            page.wait_for_selector(".ql-editor", state="visible", timeout=25000)
            page.wait_for_selector("textarea[name='title'], input[name='title']", state="visible", timeout=25000)
            time.sleep(1)

            # টাইটেল বসানো
            print("✍️ টাইটেল বসানো হচ্ছে...", flush=True)
            title_input = page.locator("textarea[name='title'], input[name='title']").first
            title_input.scroll_into_view_if_needed()
            title_input.click(force=True)
            title_input.fill(title, force=True)
            time.sleep(1)

            # থাম্বনেইল ছবি আপলোড
            if thumb_file and os.path.exists(thumb_file):
                print("🖼️ থাম্বনেইল বক্সে ছবি আপলোড করা হচ্ছে...", flush=True)
                try:
                    file_input = page.locator("input[type='file']").first
                    if file_input.count() > 0:
                        file_input.set_input_files(thumb_file)
                        print("✅ থাম্বনেইল সফলভাবে সেট হয়েছে!", flush=True)
                        time.sleep(3)
                except Exception as t_err:
                    print(f"থাম্বনেইল নোটিশ: {t_err}", flush=True)

            # এডিটরে বডি বসানো
            print("✍️ ব্লগের কন্টেন্ট বসানো হচ্ছে...", flush=True)
            editor = page.locator(".ql-editor").first
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

            # ধাপ ৩: Publish বাটনে স্ক্রোল করে একক নিশ্চিত ক্লিক (Single Click Fix)
            print("🚀 প্রথম Publish বাটনে নিশ্চিত ক্লিক করা হচ্ছে...", flush=True)
            pub_btn = page.locator("button:has-text('Publish'):not([role='dialog'] button):not(.ant-modal button)").last
            pub_btn.scroll_into_view_if_needed()
            time.sleep(1)
            pub_btn.click(force=True)
            time.sleep(2)

            # ধাপ ৪: ক্যাটাগরি মোডাল আসা পর্যন্ত অপেক্ষা ও ক্লিক
            print("⏳ ক্যাটাগরি মোডাল আসার অপেক্ষা...", flush=True)
            modal = page.locator("div[role='dialog'], .ant-modal, .modal-publish-category").first
            
            # যদি মোডাল না আসে তবে ১ বার রিট্রাই ক্লিক
            if modal.count() == 0 or not modal.is_visible():
                print("মোডাল আসতে সময় নিচ্ছে, পুনরায় ক্লিক করা হচ্ছে...", flush=True)
                pub_btn.click(force=True)
                time.sleep(2)

            page.wait_for_selector("div[role='dialog'], .ant-modal", state="visible", timeout=12000)
            time.sleep(1)

            print("🎯 মোডালের ফাইনাল নীল Publish বাটনে ক্লিক করা হচ্ছে...", flush=True)
            modal_publish_btn = page.locator("div[role='dialog'] button:has-text('Publish'), .ant-modal button:has-text('Publish')").last
            modal_publish_btn.click(force=True)

            # স্ক্রিনশট ও সাবমিট ভেরিফিকেশন
            print("⏳ পোস্ট লাইভ হওয়ার অপেক্ষা করা হচ্ছে...", flush=True)
            time.sleep(6)
            page.screenshot(path="serey_post_result.png")

            # সরাসরি প্রোফাইল ডাটাবেজ চেক
            print("🔍 সেরি প্রোফাইল ডাটাবেজে পোস্ট চেক করা হচ্ছে...", flush=True)
            for wait_round in range(1, 5):
                time.sleep(3)
                if is_post_live_on_serey(title):
                    print(f"🎉🎉 পোস্টটি ১০০% নিশ্চিতভাবে সেরি প্রোফাইলে লাইভ পাওয়া গেছে: {title}", flush=True)
                    browser.close()
                    return True

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
            if thumb_file and os.path.exists(thumb_file):
                try:
                    os.remove(thumb_file)
                except Exception:
                    pass

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
    json_meta = post_info.get("json_metadata", "{}")

    img_url = extract_first_image_url(body, json_meta)

    print(f"\nপ্রসেস করা হচ্ছে: {title}")
    success = post_with_browser(title, body, img_url)

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
