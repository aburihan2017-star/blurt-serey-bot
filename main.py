import json
import os
import time
from datetime import datetime, timedelta
import requests

# কনফিগারেশন
BLURT_USER = "aburihan1"
SEREY_USER = os.environ.get("SEREY_USERNAME", "raihan123")
SEREY_PASSWORD = os.environ.get("SEREY_POSTING_KEY")

# সরাসরি বাংলাদেশ কমিউনিটি নির্ধারণ করা হলো
COMMUNITY_NAME = "bangladesh"

BLURT_NODES = [
    "https://blurt-rpc.saboin.com",
    "https://rpc.blurt.one",
    "https://blurt.world",
]

DATA_FILE = "automation_data.json"
MAX_DAILY_POSTS = 2
DAY_IN_SECONDS = 86400

BASE_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Accept": "application/json, text/plain, */*",
    "Content-Type": "application/json",
    "Referer": "https://bangladesh.serey.io/",
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


def get_serey_auth():
    login_url = "https://global-api.serey.io/api/v2/auth/login"
    payload = {"username": SEREY_USER, "password": SEREY_PASSWORD}
    try:
        r = requests.post(login_url, json=payload, headers=BASE_HEADERS, timeout=15)
        if r.status_code in [200, 201]:
            data = r.json()
            token = (
                data.get("token")
                or data.get("accessToken")
                or (data.get("data", {}).get("token") if isinstance(data.get("data"), dict) else None)
            )
            if token:
                print("সেরিতে সফলভাবে লগইন হয়েছে!")
                return token
            print("লগইন হয়েছে কিন্তু টোকেন পাওয়া যায়নি:", data)
        else:
            print(f"লগইন রেসপন্স এরর: {r.status_code} - {r.text}")
    except Exception as e:
        print(f"লগইন এরর: {e}")
    return None


def post_to_serey(token, title, body, tags=None):
    post_url = "https://global-api.serey.io/api/v2/posts"
    headers = dict(BASE_HEADERS)
    headers["Authorization"] = f"Bearer {token}"

    # বাংলাদেশ কমিউনিটির ট্যাগ নিশ্চিত করা
    final_tags = ["bangladesh", "serey-io", "bengali"]
    if tags:
        for t in tags:
            clean_t = str(t).strip().lower()
            if clean_t and clean_t not in final_tags:
                final_tags.append(clean_t)

    payload = {
        "title": title,
        "body": body,
        "community": COMMUNITY_NAME,
        "category": COMMUNITY_NAME,
        "tags": final_tags,
    }

    try:
        r = requests.post(post_url, json=payload, headers=headers, timeout=25)
        if r.status_code in [200, 201]:
            print(f"✅ পোস্ট সফল হয়েছে: {title}")
            return True
        else:
            print(f"❌ পোস্ট ব্যর্থ হয়েছে ({r.status_code}): {r.text}")
    except Exception as e:
        print(f"পোস্ট রিকোয়েস্ট এরর: {e}")

    return False


def main():
    print("বট চালু হচ্ছে...")
    if not SEREY_PASSWORD:
        print("ত্রুটি: SEREY_POSTING_KEY (বা পাসওয়ার্ড) পাওয়া যায়নি!")
        return

    token = get_serey_auth()
    if not token:
        print("সেরিতে লগইন ব্যর্থ হয়েছে। ইউজারনেম ও পাসওয়ার্ড চেক করুন।")
        return

    print(f"নির্বাচিত কমিউনিটি: {COMMUNITY_NAME}")

    data = load_data()

    # দৈনিক সীমা চেক (সর্বোচ্চ ২টি পোস্ট)
    current_time = time.time()
    data["timestamps"] = [t for t in data.get("timestamps", []) if current_time - t < DAY_IN_SECONDS]

    if len(data["timestamps"]) >= MAX_DAILY_POSTS:
        print(f"আজকের দৈনিক সীমা ({MAX_DAILY_POSTS} টি পোস্ট) পূর্ণ হয়েছে।")
        return

    # কিউ খালি থাকলে ১ বছর আগের পোস্ট আনা
    if not data.get("queue"):
        print("ব্লার্ট থেকে ১ বছর আগের পোস্ট আনা হচ্ছে...")
        fetched_permlinks = fetch_one_year_old_posts()
        posted_set = set(data.get("posted", []))
        new_queue = [p for p in fetched_permlinks if p not in posted_set]
        data["queue"] = new_queue
        save_data(data)

    if not data["queue"]:
        print("পোস্ট করার মতো কোনো নতুন পোস্ট পাওয়া যায়নি।")
        return

    permlink_to_post = data["queue"].pop(0)
    post_info = get_post_details(permlink_to_post)

    if not post_info or "title" not in post_info:
        print(f"পোস্ট ডিটেইলস পাওয়া যায়নি: {permlink_to_post}")
        save_data(data)
        return

    title = post_info.get("title", "")
    body = post_info.get("body", "")

    tags = []
    try:
        json_meta = json.loads(post_info.get("json_metadata", "{}"))
        if "tags" in json_meta and isinstance(json_meta["tags"], list):
            tags = json_meta["tags"]
    except Exception:
        pass

    success = post_to_serey(token, title, body, tags)
    if success:
        data.setdefault("posted", []).append(permlink_to_post)
        data.setdefault("timestamps", []).append(current_time)
        print("ডাটা সেভ করা হয়েছে।")
    else:
        # ব্যর্থ হলে পুনরায় কিউতে ফেরত রাখা
        data["queue"].insert(0, permlink_to_post)

    save_data(data)
    print("প্রক্রিয়া সম্পন্ন হয়েছে।")


if __name__ == "__main__":
    main()
