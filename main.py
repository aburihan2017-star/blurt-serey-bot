from datetime import datetime, timedelta
import json
import os
import re
import time
import requests

BLURT_USER = "aburihan1"
SEREY_USER = os.environ.get("SEREY_USERNAME", "raihan123")
# আপনার GitHub Secret-এ থাকা পাসওয়ার্ড/কি
SEREY_PASS = os.environ.get("SEREY_POSTING_KEY")

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
    "Referer": "https://bengali.serey.io/login",
    "Origin": "https://bengali.serey.io",
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
    """bengali.serey.io থেকে লগইন করে টোকেন সংগ্রহ করা"""
    login_urls = [
        "https://bengali.serey.io/api/auth/login",
        "https://bengali.serey.io/api/login",
        "https://bengali.serey.io/api/users/login",
        "https://global-api.serey.io/api/v2/auth/login",
    ]

    payloads = [
        {"username": SEREY_USER, "password": SEREY_PASS},
        {"user": SEREY_USER, "password": SEREY_PASS},
        {"account": SEREY_USER, "key": SEREY_PASS},
    ]

    for url in login_urls:
        for p in payloads:
            try:
                r = requests.post(
                    url, json=p, headers=BASE_HEADERS, timeout=10
                )
                print(f"লগইন টেস্ট ({url}) -> কোড: {r.status_code}")
                if r.status_code == 200:
                    data = r.json()
                    # টোকেন খোঁজা
                    token = (
                        data.get("token")
                        or data.get("accessToken")
                        or data.get("access_token")
                        or (
                            data.get("data", {}).get("token")
                            if isinstance(data.get("data"), dict)
                            else None
                        )
                    )
                    if token:
                        print("লগইন সফল! টোকেন পাওয়া গেছে।")
                        return token
            except Exception:
                continue
    return None


def submit_to_bengali_serey(title, body, category, tags, created_date):
    print(f"bengali.serey.io তে পাঠানো হচ্ছে: {title}")
    print(f"কমিউনিটি: Bengali Community | ক্যাটাগরি: {category}")

    date_str = created_date.split("T")[0] if created_date else "1 year ago"
    footer = f"\n\n---\n*Originally written and published on Blurt by @{BLURT_USER} on {date_str}*"
    full_body = body + footer

    # টোকেন নেওয়া
    token = get_serey_auth_token()

    headers = dict(BASE_HEADERS)
    if token:
        headers["Authorization"] = f"Bearer {token}"

    post_url = "https://bengali.serey.io/api/posts"
    post_data = {
        "title": title,
        "body": full_body,
        "content": full_body,
        "category": category,
        "community": "bengali-community",
        "tags": ["bengali-community", "bangladesh", category] + tags[:3],
        "author": SEREY_USER,
    }

    try:
        res = requests.post(
            post_url, json=post_data, headers=headers, timeout=15
        )
        print(f"পোস্ট রিকোয়েস্ট রেসপন্স: {res.status_code} | {res.text[:200]}")
        if res.status_code in [200, 201]:
            print("অভিনন্দন! সফলভাবে bengali.serey.io তে পোস্ট সম্পন্ন হয়েছে!")
            return True
    except Exception as e:
        print(f"পোস্ট রিকোয়েস্টে এরর: {e}")

    return True


def run():
    data = load_data()
    now = time.time()

    valid_timestamps = [t for t in data["timestamps"] if (now - t) < DAY_IN_SECONDS]
    data["timestamps"] = valid_timestamps

    if len(valid_timestamps) >= MAX_DAILY_POSTS:
        print(f"আজকের ২৪ ঘণ্টার কোটা পূর্ণ! ({len(valid_timestamps)}/2)")
        save_data(data)
        return

    if not data["queue"]:
        print("Blurt থেকে ১ বছর পুরনো পোস্ট সংগ্রহ করা হচ্ছে...")
        fetched = fetch_one_year_old_posts()
        new_items = [p for p in fetched if p not in data["posted"]]
        data["queue"].extend(new_items)
        save_data(data)

    if not data["queue"]:
        print("পোস্ট করার মতো কোনো পুরনো পোস্ট অবশিষ্ট নেই।")
        return

    next_permlink = data["queue"].pop(0)
    post_info = get_post_details(next_permlink)

    if post_info and post_info.get("title"):
        title = post_info["title"]
        body = post_info["body"]
        meta = json.loads(post_info.get("json_metadata", "{}"))
        tags = meta.get("tags", [])
        created = post_info.get("created", "")

        category = tags[0] if len(tags) > 0 else "general"

        success = submit_to_bengali_serey(
            title, body, category, tags, created
        )

        if success:
            data["posted"].append(next_permlink)
            data["timestamps"].append(now)
            save_data(data)
            print("পোস্ট সম্পন্ন হয়েছে!")
    else:
        print("পোস্টের তথ্য রিড করা যায়নি।")
        save_data(data)


if __name__ == "__main__":
    run()
