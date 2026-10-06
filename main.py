from datetime import datetime, timedelta
import json
import os
import re
import time
import requests

BLURT_USER = "aburihan1"
SEREY_USER = os.environ.get("SEREY_USERNAME", "raihan123")
SEREY_PASSWORD = os.environ.get("SEREY_POSTING_KEY")

BLURT_NODES = [
    "https://blurt-rpc.saboin.com",
    "https://rpc.blurt.one",
    "https://blurt.world",
]

DATA_FILE = "automation_data.json"
MAX_DAILY_POSTS = 2
DAY_IN_SECONDS = 86400

BASE_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Linux; Android 10; K) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Mobile Safari/537.36",
    "Accept": "application/json, text/plain, */*",
    "Content-Type": "application/json",
    "Referer": "https://bangladesh.serey.io/blog/new",
    "Origin": "https://bangladesh.serey.io",
}


def blurt_call(method, params):
    payload = {"jsonrpc": "2.0", "method": method, "params": params, "id": 1}
    for node in BLURT_NODES:
        try:
            res = requests.post(node, json=payload, timeout=10).json()
            if "result" in res:
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


def fetch_one_year_old_posts():
    one_year_ago = datetime.utcnow() - timedelta(days=365)
    before_date = one_year_ago.strftime("%Y-%m-%dT%H:%M:%S")

    posts = blurt_call(
        "condenser_api.get_discussions_by_author_before_date",
        [BLURT_USER, "", before_date, 30],
    )
    if posts:
        return [p["permlink"] for p in reversed(posts)]
    return []


def get_post_details(permlink):
    return blurt_call("condenser_api.get_content", [BLURT_USER, permlink])


def get_serey_auth_token():
    """global-api.serey.io থেকে লগইন করে টোকেন সংগ্রহ"""
    login_url = "https://global-api.serey.io/api/v2/auth/login"
    payload = {"username": SEREY_USER, "password": SEREY_PASSWORD}

    try:
        r = requests.post(
            login_url, json=payload, headers=BASE_HEADERS, timeout=15
        )
        if r.status_code in [200, 201]:
            data = r.json()
            token = (
                data.get("token")
                or data.get("accessToken")
                or (
                    data.get("data", {}).get("token")
                    if isinstance(data.get("data"), dict)
                    else None
                )
            )
            return token
    except Exception as e:
        print(f"লগইন কানেকশন এরর: {e}")
    return None


def get_serey_categories(token):
    """Serey-র অফিশিয়াল ক্যাটাগরি তালিকা ড্রপডাউন থেকে রিড করা"""
    cat_urls = [
        "https://global-api.serey.io/api/v2/categories",
        "https://bangladesh.serey.io/api/categories",
        "https://global-api.serey.io/api/v1/categories",
    ]
    headers = dict(BASE_HEADERS)
    headers["Authorization"] = f"Bearer {token}"

    for url in cat_urls:
        try:
            r = requests.get(url, headers=headers, timeout=10)
            if r.status_code == 200:
                data = r.json()
                cats = (
                    data.get("data")
                    if isinstance(data, dict) and "data" in data
                    else data
                )
                if isinstance(cats, list) and len(cats) > 0:
                    return cats
        except Exception:
            continue
    return []


def select_best_category(title, content, categories):
    """পোস্টের ধরন অনুযায়ী ক্যাটাগরি এবং সাব-ক্যাটাগরি স্বয়ংক্রিয়ভাবে নির্ধারণ"""
    text_lower = (title + " " + content).lower()

    # সাধারণ ক্যাটাগরি কি-ওয়ার্ড ম্যাপিং
    keywords = {
        "photography": ["photo", "camera", "picture", "nature", "flower", "shot"],
        "gaming": ["game", "splinterlands", "battle", "card", "play", "pack"],
        "lifestyle": ["life", "day", "routine", "my", "family", "personal"],
        "technology": ["tech", "software", "code", "ai", "computer", "phone"],
        "crypto": ["bitcoin", "crypto", "blockchain", "blurt", "serey", "token"],
        "entertainment": ["movie", "song", "music", "fun", "drama"],
    }

    if not categories:
        return None

    # ১. পোস্টের বিষয়বস্তুর সাথে সবচেয়ে বেশি মেলার ক্যাটাগরি খোঁজা
    for cat in categories:
        cat_name = (
            cat.get("name", "") if isinstance(cat, dict) else str(cat)
        ).lower()
        for group, words in keywords.items():
            if any(w in text_lower for w in words):
                if group in cat_name or cat_name in group:
                    return cat

    # ২. মিল না পেলে ড্রপডাউনের ১ম/সাধারণ ক্যাটাগরি নেওয়া
    return categories[0]


def submit_to_bangladesh_serey(title, body, created_date):
    print(f"bangladesh.serey.io তে পোস্ট প্রস্তুত হচ্ছে: {title}")

    token = get_serey_auth_token()
    if not token:
        print("লগইন টোকেন পাওয়া যায়নি।")
        return False

    print("লগইন সফল! Serey ক্যাটাগরি ড্রপডাউন লোড করা হচ্ছে...")
    categories = get_serey_categories(token)

    # ক্যাটাগরি ও সাব-ক্যাটাগরি অবজেক্ট তৈরি
    chosen_cat = select_best_category(title, body, categories)

    cat_id = None
    sub_cat_id = None

    if isinstance(chosen_cat, dict):
        cat_id = chosen_cat.get("id") or chosen_cat.get("_id")
        sub_cats = chosen_cat.get("subCategories", [])
        if sub_cats and isinstance(sub_cats[0], dict):
            sub_cat_id = sub_cats[0].get("id") or sub_cats[0].get("_id")
        elif sub_cats:
            sub_cat_id = sub_cats[0]
        print(f"নির্বাচিত Serey ক্যাটাগরি: {chosen_cat.get('name')}")
    else:
        print("ক্যাটাগরি লোড করা হয়েছে।")

    # সোর্স ক্রেডিট
    date_str = created_date.split("T")[0] if created_date else "1 year ago"
    footer = f"\n\n---\n*Originally written and published on Blurt by @{BLURT_USER} on {date_str}*"
    full_body = body + footer

    headers = dict(BASE_HEADERS)
    headers["Authorization"] = f"Bearer {token}"

    post_url = "https://global-api.serey.io/api/v2/posts"

    # ব্রাউজারের মতো সম্পূর্ণ ফর্ম ডাটা পে-লোড
    post_payload = {
        "title": title,
        "content": full_body,
        "description": full_body[:150],
        "community": "bangladesh",
        "platform": "bangladesh",
        "categories": [cat_id] if cat_id else [],
        "category": cat_id,
        "subCategory": sub_cat_id,
        "author": SEREY_USER,
    }

    try:
        res = requests.post(
            post_url, json=post_payload, headers=headers, timeout=15
        )
        print(f"পোস্ট রেসপন্স স্ট্যাটাস: {res.status_code}")
        print(f"সার্ভার মেসেজ: {res.text}")

        if res.status_code in [200, 201]:
            print(
                "অভিনন্দন! সফলভাবে bangladesh.serey.io তে ক্যাটাগরি সহ পোস্ট লাইভ পাবলিশ হয়েছে!"
            )
            return True
    except Exception as e:
        print(f"পোস্ট সাবমিট এরর: {e}")

    return False


def run():
    data = load_data()
    now = time.time()

    valid_timestamps = [t for t in data["timestamps"] if (now - t) < DAY_IN_SECONDS]
    data["timestamps"] = valid_timestamps

    if len(valid_timestamps) >= MAX_DAILY_POSTS:
        print(
            f"আজকের ২৪ ঘণ্টার কোটা পূর্ণ! ({len(valid_timestamps)}/{MAX_DAILY_POSTS})"
        )
        save_data(data)
        return

    if not data["queue"]:
        print("Blurt থেকে ১ বছর পুরনো পোস্ট সংগ্রহ করা হচ্ছে...")
        fetched = fetch_one_year_old_posts()
        new_items = [p for p in fetched if p not in data["posted"]]
        data["queue"].extend(new_items)
        save_data(data)

    if not data["queue"]:
        print("পোস্ট করার মতো কোনো পুরনো পোস্ট পাওয়া যায়নি।")
        return

    next_permlink = data["queue"].pop(0)
    post_info = get_post_details(next_permlink)

    if post_info and post_info.get("title"):
        title = post_info["title"]
        body = post_info["body"]
        created = post_info.get("created", "")

        success = submit_to_bangladesh_serey(title, body, created)

        if success:
            data["posted"].append(next_permlink)
            data["timestamps"].append(now)
            save_data(data)
            print(
                f"পোস্ট সম্পন্ন! (আজকের পোস্ট সংখ্যা: {len(data['timestamps'])}/{MAX_DAILY_POSTS})"
            )
        else:
            data["queue"].insert(0, next_permlink)
            save_data(data)
    else:
        print("পোস্টের তথ্য রিড করা যায়নি।")
        save_data(data)


if __name__ == "__main__":
    run()
