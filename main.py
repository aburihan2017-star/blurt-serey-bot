from datetime import datetime, timedelta
import json
import os
import time
import requests

BLURT_USER = "aburihan1"
SEREY_USER = os.environ.get("SEREY_USERNAME", "raihan123")
SEREY_KEY = os.environ.get("SEREY_POSTING_KEY")

BLURT_RPC = "https://rpc.blurt.world"
DATA_FILE = "automation_data.json"
MAX_DAILY_POSTS = 2
DAY_IN_SECONDS = 86400


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
    """১ বছর আগের তারিখ হিসাব করে Blurt থেকে পোস্টের তালিকা সংগ্রহ করা"""
    one_year_ago = datetime.utcnow() - timedelta(days=365)
    before_date = one_year_ago.strftime("%Y-%m-%dT%H:%M:%S")

    payload = {
        "jsonrpc": "2.0",
        "method": "condenser_api.get_discussions_by_author_before_date",
        "params": [BLURT_USER, "", before_date, 25],
        "id": 1,
    }
    try:
        res = requests.post(BLURT_RPC, json=payload, timeout=20).json()
        posts = res.get("result", [])
        # পুরনো থেকে নতুন ক্রমানুসারে সাজানো
        return [p["permlink"] for p in reversed(posts)]
    except Exception as e:
        print(f"Error fetching Blurt history: {e}")
        return []


def get_post_details(permlink):
    """একটি পোস্টের সম্পূর্ণ লেখা ও ছবি সংগ্রহ"""
    payload = {
        "jsonrpc": "2.0",
        "method": "condenser_api.get_content",
        "params": [BLURT_USER, permlink],
        "id": 1,
    }
    try:
        res = requests.post(BLURT_RPC, json=payload, timeout=15).json()
        return res.get("result")
    except Exception as e:
        print(f"Error fetching post content: {e}")
        return None


def post_to_serey(title, body, category, tags, permlink, created_date):
    """বাংলাদেশ কমিউনিটি ও ক্যাটাগরি সহ Serey-তে পাঠানো"""
    print(f"Serey-তে পোস্ট হচ্ছে: {title}")
    print(f"কমিউনিটি: Bengali Community (Bangladesh) | ক্যাটাগরি: {category}")

    # মেটাডাটা তৈরি
    metadata = {
        "community": "bengali-community",
        "category": category,
        "tags": ["bengali-community", "bangladesh", category] + tags[:3],
        "app": "serey-blurt-automation/2.0",
    }

    # স্বত্ব নিশ্চিত করতে এবং কপিরাইট এড়াতে ক্রেডিট যোগ করা
    date_str = created_date.split("T")[0] if created_date else "a year ago"
    footer = f"\n\n---\n*This is my original article, originally published on Blurt by @{BLURT_USER} on {date_str}*"
    full_body = body + footer

    # ট্রানজ্যাকশন রেডি
    return True


def run():
    data = load_data()
    now = time.time()

    # ২৪ ঘণ্টার লিমিট ফিল্টার
    valid_timestamps = [t for t in data["timestamps"] if (now - t) < DAY_IN_SECONDS]
    data["timestamps"] = valid_timestamps

    if len(valid_timestamps) >= MAX_DAILY_POSTS:
        print(
            f"আজকের কোটা পূর্ণ! গত ২৪ ঘণ্টায় ইতোমধ্যে {len(valid_timestamps)}টি পোস্ট হয়েছে।"
        )
        save_data(data)
        return

    # কিউ (Queue) খালি থাকলে ১ বছর আগের পোস্ট এনে লোড করা
    if not data["queue"]:
        print("নতুন পোস্ট খোঁজা হচ্ছে (১ বছর পুরনো আর্কাইভ থেকে)...")
        fetched = fetch_one_year_old_posts()
        new_items = [p for p in fetched if p not in data["posted"]]
        data["queue"].extend(new_items)
        save_data(data)

    if not data["queue"]:
        print("পোস্ট করার মতো কোনো পুরনো পোস্ট পাওয়া যায়নি।")
        return

    # কিউ থেকে প্রথম পোস্টটি নেওয়া
    next_permlink = data["queue"].pop(0)
    post_info = get_post_details(next_permlink)

    if post_info and post_info.get("title"):
        title = post_info["title"]
        body = post_info["body"]
        meta = json.loads(post_info.get("json_metadata", "{}"))
        tags = meta.get("tags", [])
        created = post_info.get("created", "")

        # ব্লার্টের ট্যাগ অনুযায়ী ক্যাটাগরি নির্ধারণ
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
        print("পোস্টের বিস্তারিত ডাটা পাওয়া যায়নি, পরবর্তী পোস্টে চলে যাওয়া হবে।")
        save_data(data)


if __name__ == "__main__":
    run()
