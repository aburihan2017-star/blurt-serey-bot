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
    "User-Agent": "Mozilla/5.0 (Linux; Android 10; K) Chrome/120.0.0.0 Mobile Safari/537.36",
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
    login_url = "https://global-api.serey.io/api/v2/auth/login"
    payload = {"username": SEREY_USER, "password": SEREY_PASSWORD}
    try:
        r = requests.post(
            login_url, json=payload, headers=BASE_HEADERS, timeout=15
        )
        if r.status_code in [200, 201]:
            data = r.json()
            return (
                data.get("token")
                or data.get("accessToken")
                or (
                    data.get("data", {}).get("token")
                    if isinstance(data.get("data"), dict)
                    else None
                )
            )
        else:
            print(f"লগইন রেসপন্স: {r.status_code}")
    except Exception as e:
        print(f"লগইন এরর: {e}")
    return None


def find_community_id(token):
    headers = dict(BASE_HEADERS)
    headers["Authorization"] = f"Bearer {token}"
    urls = [
        "https://bangladesh.serey.io/api/communities",
        "https://global-api.serey.io/api/v2/communities",
        "https://global-api.serey.io/api/v2/community",
    ]
    for u in urls:
        try:
            r = requests.get(u, headers=headers, timeout=8)
            print(f"চেক {u} -> স্ট্যাটাস: {r.status_code}")
            if r.status_code == 200:
                print(f"ডাটা নমুনা: {r.text[:200]}")
                m = re.search(
                    r'"(?:_id|id)"\s*:\s*"([^"]+)"[^}]*?"name"\s*:\s*"Bengali Community"',
                    r.text,
                    re.I,
                )
                if not m:
                    m = re.search(
                        r'"name"\s*:\s*"Bengali Community"[^}]*?"(?:_id|id)"\s*:\s*"([^"]+)"',
                        r.text,
                        re.I,
                    )
                if m:
                    cid = m.group(1)
                    print(f"Bengali Community ID পাওয়া গেছে: {cid}")
                    return cid
        except Exception:
            pass
    return None


def detect_category(title, body):
    t = (title + " " + body).lower()
    if any(
        w in t
        for w in "splinterlands game card battle sports quest pack unit".split()
    ):
        return "Sports"
    if any(w in t for w in "photo photography camera nature flower sky".split()):
        return "Photography"
    if any(w in t for w in "crypto bitcoin blurt hive token".split()):
        return "Crypto"
    if any(w in t for w in "travel tour trip village city".split()):
        return "Travel"
    return "Lifestyle"


def submit_human_post(title, body, created_date):
    print("--------------------------------------------------")
    print(f"[ধাপ ১] ইউজার @{SEREY_USER} হিসেবে লগইন হচ্ছে...")
    token = get_serey_auth_token()
    if not token:
        print("লগইন ব্যর্থ।")
        return False
    print("লগইন সফল!")

    print("[ধাপ ২] Bengali Community আইডি খোঁজা হচ্ছে...")
    comm_id = find_community_id(token)

    print("[ধাপ ৩] কন্টেন্ট ও ক্যাটাগরি তৈরি...")
    cat = detect_category(title, body)
    date_str = created_date.split("T")[0] if created_date else "1 year ago"
    full_body = (
        body
        + f"\n\n---\n*Originally written and published on Blurt by @{BLURT_USER} on {date_str}*"
    )

    headers = dict(BASE_HEADERS)
    headers["Authorization"] = f"Bearer {token}"

    payload = {
        "title": title,
        "content": full_body,
        "body": full_body,
        "description": full_body[:150],
        "categories": cat,
        "category": cat,
        "author": SEREY_USER,
    }
    if comm_id:
        payload["community"] = comm_id
        payload["communityId"] = comm_id
        payload["platform"] = "Bangladesh"

    print(
        f"[ধাপ ৪] bangladesh.serey.io তে সাবমিট করা হচ্ছে (Category: {cat})..."
    )
    try:
        res = requests.post(
            "https://bangladesh.serey.io/api/posts",
            json=payload,
            headers=headers,
            timeout=15,
        )
        print(f"সার্ভার স্ট্যাটাস: {res.status_code}")
        print(f"সার্ভার মেসেজ: {res.text}")

        if res.status_code in [200, 201]:
            print("অভিনন্দন! সফলভাবে পোস্ট পাবলিশ সম্পন্ন হয়েছে!")
            return True
    except Exception as e:
        print(f"পোস্ট এরর: {e}")

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
        print("পোস্ট করার মতো কোনো পুরনো পোস্ট অবশিষ্ট নেই।")
        return

    next_permlink = data["queue"].pop(0)
    post_info = get_post_details(next_permlink)

    if post_info and post_info.get("title"):
        title = post_info["title"]
        body = post_info["body"]
        created = post_info.get("created", "")

        success = submit_human_post(title, body, created)

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
        print("পোস্টের তথ্য পাওয়া যায়নি।")
        save_data(data)


if __name__ == "__main__":
    run()
