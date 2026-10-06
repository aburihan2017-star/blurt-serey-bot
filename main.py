from datetime import datetime, timedelta
import json
import os
import time
import requests

BLURT_USER = "aburihan1"
SEREY_USER = os.environ.get("SEREY_USERNAME", "raihan123")
SEREY_KEY = os.environ.get("SEREY_POSTING_KEY")

# সচল Blurt RPC নোডগুলো
BLURT_NODES = [
    "https://blurt-rpc.saboin.com",
    "https://rpc.blurt.one",
    "https://blurt.world",
]

DATA_FILE = "automation_data.json"
MAX_DAILY_POSTS = 2
DAY_IN_SECONDS = 86400


def blurt_call(method, params):
    """নোড ডাউন থাকলে অটোমেটিক অন্য নোড চেষ্টা করবে"""
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
        [BLURT_USER, "", before_date, 25],
    )
    if posts:
        return [p["permlink"] for p in reversed(posts)]
    return []


def get_post_details(permlink):
    return blurt_call("condenser_api.get_content", [BLURT_USER, permlink])


def post_to_serey(title, body, category, tags, permlink, created_date):
    print(f"Serey-তে পোস্ট হচ্ছে: {title}")
    print(f"কমিউনিটি: Bengali Community (Bangladesh) | ক্যাটাগরি: {category}")
    return True


def run():
    data = load_data()
    now = time.time()

    valid_timestamps = [t for t in data["timestamps"] if (now - t) < DAY_IN_SECONDS]
    data["timestamps"] = valid_timestamps

    if len(valid_timestamps) >= MAX_DAILY_POSTS:
        print(f"আজকের কোটা পূর্ণ! ({len(valid_timestamps)}/{MAX_DAILY_POSTS})")
        save_data(data)
        return

    if not data["queue"]:
        print("Blurt থেকে ১ বছর পুরনো পোস্ট খোঁজা হচ্ছে...")
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
        meta = json.loads(post_info.get("json_metadata", "{}"))
        tags = meta.get("tags", [])
        created = post_info.get("created", "")

        category = tags[0] if len(tags) > 0 else "general"

        success = post_to_serey(title, body, category, tags, next_permlink, created)

        if success:
            data["posted"].append(next_permlink)
            data["timestamps"].append(now)
            save_data(data)
            print(
                f"সফলভাবে পোস্ট সম্পন্ন হয়েছে! (আজকের পোস্ট: {len(data['timestamps'])}/{MAX_DAILY_POSTS})"
            )
    else:
        print("পোস্টের তথ্য পাওয়া যায়নি, পরবর্তী চেষ্টা করা হবে।")
        save_data(data)


if __name__ == "__main__":
    run()
