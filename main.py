import json
import os
import re
import time
from datetime import datetime, timedelta
import requests

from beem import Steem
from beem.instance import set_shared_steem_instance

# কনফিগারেশন
BLURT_USER = "aburihan1"
SEREY_USER = os.environ.get("SEREY_USERNAME", "raihan123")
SEREY_POSTING_KEY = os.environ.get("SEREY_POSTING_KEY")

# সেরি ব্লকচেইন কনফিগারেশন (স্ক্রিনশট থেকে সরাসরি প্রাপ্ত)
SEREY_NODE = "https://api.serey.io"
SEREY_CHAIN_ID = "5205c25d3e87cb3e8e527e6fbbf324b7b2b9fe7a7192c604ce5b174d08987324"
SEREY_PREFIX = "SRY"

CUSTOM_CHAINS = {
    "SEREY": {
        "chain_assets": [
            {"asset": "@@000000021", "id": 0, "precision": 3, "symbol": "SRY"},
            {"asset": "@@000000013", "id": 1, "precision": 3, "symbol": "VESTS"},
        ],
        "chain_id": SEREY_CHAIN_ID,
        "min_version": "0.0.0",
        "prefix": SEREY_PREFIX,
    }
}

BLURT_NODES = [
    "https://blurt-rpc.saboin.com",
    "https://rpc.blurt.one",
    "https://blurt.world",
]

DATA_FILE = "automation_data.json"
MAX_DAILY_POSTS = 2
DAY_IN_SECONDS = 86400


def blurt_call(method, params):
    payload = {"jsonrpc": "2.0", "method": method, "params": params, "id": 1}
    for node in BLURT_NODES:
        try:
            res = requests.post(node, json=payload, timeout=15).json()
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


def get_serey_client():
    """সেরি ব্লকচেইনের সাথে সরাসরি কানেকশন স্থাপন"""
    try:
        client = Steem(
            node=[SEREY_NODE],
            keys=[SEREY_POSTING_KEY],
            custom_chains=CUSTOM_CHAINS,
            nobroadcast=False,
            num_retries=3,
            timeout=25,
        )
        set_shared_steem_instance(client)
        return client
    except Exception as e:
        print(f"সেরি ক্লায়েন্ট সংযোগ এরর: {e}")
        return None


def post_directly_to_blockchain(client, title, body, permlink=None, tags=None):
    """সরাসরি ব্লকচেইনে পোস্ট ব্রডকাস্ট করা"""
    if not tags:
        tags = ["news", "bengali-community", "others"]
    else:
        clean_tags = ["news", "bengali-community"]
        for t in tags:
            ct = re.sub(r'[^a-z0-9\-]', '', str(t).lower().strip())
            if ct and ct not in clean_tags:
                clean_tags.append(ct)
        tags = clean_tags

    # ইউনিক পারমালিঙ্ক তৈরি
    if not permlink:
        clean_title = re.sub(r'[^a-z0-9]+', '-', title.lower()).strip('-')
        permlink = f"{clean_title[:45]}-{int(time.time())}"

    # সেরি বাংলা কমিউনিটির ক্যাটাগরি
    community_category = "bengali-community"

    try:
        print(f"🚀 সরাসরি ব্লকচেইনে পোস্ট ব্রডকাস্ট করা হচ্ছে: {title}")
        tx = client.post(
            title=title,
            body=body,
            author=SEREY_USER,
            permlink=permlink,
            tags=tags,
            category=community_category,
        )
        print("✅ ব্লকচেইনে সফলভাবে পোস্ট রেকর্ড হয়েছে!")
        return True
    except Exception as e:
        print(f"❌ ব্লকচেইনে পোস্ট এরর: {e}")
        return False


def main():
    print("বট চালু হচ্ছে...")
    if not SEREY_POSTING_KEY:
        print("ত্রুটি: SEREY_POSTING_KEY পাওয়া যায়নি!")
        return

    client = get_serey_client()
    if not client:
        print("সেরি ব্লকচেইনে সংযোগ স্থাপন করা যায়নি।")
        return

    print("✅ সেরি ব্লকচেইন ক্লায়েন্ট প্রস্তুত!")

    data = load_data()

    # দৈনিক সীমা চেক (সর্বোচ্চ ২টি পোস্ট)
    current_time = time.time()
    data["timestamps"] = [t for t in data.get("timestamps", []) if current_time - t < DAY_IN_SECONDS]

    if len(data["timestamps"]) >= MAX_DAILY_POSTS:
        print(f"আজকের দৈনিক সীমা ({MAX_DAILY_POSTS} টি পোস্ট) পূর্ণ হয়েছে।")
        return

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

    while data["queue"]:
        permlink_to_post = data["queue"].pop(0)
        post_info = get_post_details(permlink_to_post)

        if not post_info or "title" not in post_info:
            print(f"পোস্ট ডিটেইলস মেলেনি, স্কিপ: {permlink_to_post}")
            data.setdefault("posted", []).append(permlink_to_post)
            continue

        title = post_info.get("title", "")
        body = post_info.get("body", "")

        tags = []
        try:
            json_meta = json.loads(post_info.get("json_metadata", "{}"))
            if "tags" in json_meta and isinstance(json_meta["tags"], list):
                tags = json_meta["tags"]
        except Exception:
            pass

        # সরাসরি ব্লকচেইনে পোস্ট ব্রডকাস্ট
        success = post_directly_to_blockchain(client, title, body, tags=tags)

        if success:
            data.setdefault("posted", []).append(permlink_to_post)
            data.setdefault("timestamps", []).append(current_time)
            print("ডাটা সেভ করা হয়েছে।")
            break
        else:
            # যদি পারমালিঙ্ক ডুপ্লিকেট থাকে তবে স্কিপ করে পরের পোস্ট নিবে
            print(f"⏩ স্কিপ করে পরবর্তী পোস্ট দেখা হচ্ছে: {title}")
            data.setdefault("posted", []).append(permlink_to_post)
            save_data(data)
            time.sleep(3)
            continue

    save_data(data)
    print("\nপ্রক্রিয়া সম্পূর্ণ হয়েছে।")


if __name__ == "__main__":
    main()
