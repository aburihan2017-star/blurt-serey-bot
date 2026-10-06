from datetime import datetime, timedelta
import json
import os
import re
import time
from beem import Steem
from beem.exceptions import AccountDoesNotExistsException
import requests

BLURT_USER = "aburihan1"
SEREY_USER = os.environ.get("SEREY_USERNAME", "raihan123")
SEREY_KEY = os.environ.get("SEREY_POSTING_KEY")

BLURT_NODES = [
    "https://blurt-rpc.saboin.com",
    "https://rpc.blurt.one",
    "https://blurt.world",
]
SEREY_NODES = ["https://serey.io", "wss://serey.io"]

DATA_FILE = "automation_data.json"
MAX_DAILY_POSTS = 2
DAY_IN_SECONDS = 86400


def get_serey_client():
    """Serey নেটওয়ার্কে কানেক্ট হওয়া"""
    return Steem(node=SEREY_NODES, keys=[SEREY_KEY])


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


def clean_permlink(title):
    permlink = re.sub(r"[^a-z0-9\-]+", "", title.lower().replace(" ", "-"))
    return f"{permlink[:40]}-{int(time.time())}"


def post_to_serey(title, body, category, tags, created_date):
    """বাংলাদেশ কমিউনিটিতে লাইভ পোস্ট ব্রডকাস্ট করা"""
    print(f"Serey-তে লাইভ পাবলিশ করা হচ্ছে: {title}")
    print(f"কমিউনিটি: Bengali Community (Bangladesh) | ক্যাটাগরি: {category}")

    date_str = created_date.split("T")[0] if created_date else "1 year ago"
    footer = f"\n\n---\n*Originally written and published on Blurt by @{BLURT_USER} on {date_str}*"
    full_body = body + footer

    post_permlink = clean_permlink(title)
    final_tags = list(
        dict.fromkeys(["bengali-community", "bangladesh", category] + tags[:3])
    )

    try:
        serey = get_serey_client()
        # Serey ব্লকচেইনে বাংলাদেশ কমিউনিটিতে কমেন্ট/পোস্ট অপারেশন
        serey.post(
            title=title,
            body=full_body,
            author=SEREY_USER,
            permlink=post_permlink,
            reply_identifier="bengali-community",
            tags=final_tags,
            self_vote=True,
        )
        print("Serey ব্লকচেইনে সফলভাবে পোস্ট সাবমিট হয়েছে!")
        return True
    except Exception as e:
        print(f"Serey-তে সাবমিট করার সময় সমস্যা: {e}")
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
        meta = json.loads(post_info.get("json_metadata", "{}"))
        tags = meta.get("tags", [])
        created = post_info.get("created", "")

        category = tags[0] if len(tags) > 0 else "photography"

        success = post_to_serey(title, body, category, tags, created)

        if success:
            data["posted"].append(next_permlink)
            data["timestamps"].append(now)
            save_data(data)
            print(
                f"পোস্ট সফল! (আজকের পোস্ট সংখ্যা: {len(data['timestamps'])}/{MAX_DAILY_POSTS})"
            )
        else:
            # ব্যর্থ হলে আবার কিউ-তে সামনে রেখে দেওয়া যাতে পরে চেষ্টা করতে পারে
            data["queue"].insert(0, next_permlink)
            save_data(data)
    else:
        print("পোস্টের তথ্য রিড করা যায়নি, পরবর্তী চেষ্টা করা হবে।")
        save_data(data)


if __name__ == "__main__":
    run()
