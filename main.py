import json
import os
import re
import time
from datetime import datetime, timedelta
import requests

# কনফিগারেশন
BLURT_USER = "aburihan1"
SEREY_USER = os.environ.get("SEREY_USERNAME", "raihan123")
SEREY_PASSWORD = os.environ.get("SEREY_POSTING_KEY")

COMMUNITY_NAME = "Bengali Community"
COMMUNITY_ID = 2

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
    "Referer": "https://bengali.serey.io/write/new",
    "Origin": "https://bengali.serey.io",
}


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


def fetch_one_year_old_posts(posted_set):
    one_year_ago = datetime.utcnow() - timedelta(days=365)
    before_date = one_year_ago.strftime("%Y-%m-%dT%H:%M:%S")
    
    posts = blurt_call(
        "condenser_api.get_discussions_by_author_before_date",
        [BLURT_USER, "", before_date, 100],
    )
    if posts:
        new_permlinks = []
        for p in reversed(posts):
            plink = p.get("permlink")
            if plink and plink not in posted_set:
                new_permlinks.append(plink)
        return new_permlinks
    return []


def get_post_details(permlink):
    return blurt_call("condenser_api.get_content", [BLURT_USER, permlink])


def get_serey_auth():
    login_url = "https://global-api.serey.io/api/v2/auth/login"
    payload = {"username": SEREY_USER, "password": SEREY_PASSWORD}

    for attempt in range(1, 4):
        try:
            print(f"সেরিতে লগইন চেষ্টা চলছে (Attempt {attempt}/3)...")
            r = requests.post(login_url, json=payload, headers=BASE_HEADERS, timeout=40)
            if r.status_code in [200, 201]:
                data = r.json()
                token = (
                    data.get("token")
                    or data.get("accessToken")
                    or (data.get("data", {}).get("token") if isinstance(data.get("data"), dict) else None)
                )
                if token:
                    print("✅ সেরিতে সফলভাবে লগইন হয়েছে!")
                    return token
                print("লগইন হয়েছে কিন্তু টোকেন পাওয়া যায়নি:", data)
            else:
                print(f"লগইন রেসপন্স: {r.status_code} - {r.text}")
        except requests.exceptions.Timeout:
            print(f"টাইমআউট হয়েছে (চেষ্টা #{attempt})। ৫ সেকেন্ড পর আবার চেষ্টা...")
            time.sleep(5)
        except Exception as e:
            print(f"লগইন এরর: {e}")
            time.sleep(3)
    return None


def post_to_serey_direct(token, title, body, tags=None):
    """ড্রাফট বাদে সরাসরি আসল পোস্ট API দিয়ে পাবলিশ করা"""
    headers = dict(BASE_HEADERS)
    headers["Authorization"] = f"Bearer {token}"

    final_tags = ["news", "others", "bengali-community"]
    if tags:
        for t in tags:
            clean_t = re.sub(r'[^a-z0-9\-]', '', str(t).lower().strip())
            if clean_t and clean_t not in final_tags:
                final_tags.append(clean_t)

    # HTML ফরম্যাটিং
    formatted_body = body
    if not ("<p>" in formatted_body or "<div>" in formatted_body):
        formatted_body = f"<p>{body.replace(chr(10) + chr(10), '</p><p>').replace(chr(10), '<br/>')}</p>"

    # ইউনিক পারমালিঙ্ক
    slug = re.sub(r'[^a-z0-9]+', '-', title.lower()).strip('-')[:35]
    unique_permlink = f"{slug}-{int(time.time())}"

    # স্ক্রিনশট ৩:২০ থেকে সরাসরি প্রাপ্ত আসল পাবলিশ পেলোড
    direct_payload = {
        "title": title,
        "permlink": unique_permlink,
        "description": formatted_body,
        "body": formatted_body,
        "categories": ["news", "others"],
        "community_id": COMMUNITY_ID,
        "community_title": COMMUNITY_NAME,
        "tags": final_tags,
        "type": 1,
        "post_to_blockchain": True,
    }

    # সেরি ব্যাকএন্ডের মূল পোস্ট এন্ডপয়েন্টগুলো
    candidate_urls = [
        "https://global-api.serey.io/api/v2/posts",
        "https://global-api.serey.io/api/v2/post",
        "https://global-api.serey.io/api/v2/blog/post",
        "https://global-api.serey.io/api/v2/articles",
    ]

    for url in candidate_urls:
        try:
            print(f"🚀 সরাসরি পোস্ট পাঠানো হচ্ছে: {url}")
            r = requests.post(url, json=direct_payload, headers=headers, timeout=30)
            print(f"সার্ভার রেসপন্স ({r.status_code}): {r.text[:300]}")

            if r.status_code in [200, 201]:
                print(f"🎉🎉 পোস্ট সরাসরি সফলভাবে লাইভ পাবলিশ হয়েছে: {title}")
                return True
        except Exception as e:
            print(f"রিকোয়েস্ট এরর ({url}): {e}")

    return False


def main():
    print("বট চালু হচ্ছে...")
    if not SEREY_PASSWORD:
        print("ত্রুটি: SEREY_POSTING_KEY পাওয়া যায়নি!")
        return

    token = get_serey_auth()
    if not token:
        print("সেরিতে লগইন ব্যর্থ হয়েছে।")
        return

    data = load_data()

    # দৈনিক সীমা চেক (সর্বোচ্চ ২টি পোস্ট)
    current_time = time.time()
    data["timestamps"] = [t for t in data.get("timestamps", []) if current_time - t < DAY_IN_SECONDS]

    if len(data["timestamps"]) >= MAX_DAILY_POSTS:
        print(f"আজকের দৈনিক সীমা ({MAX_DAILY_POSTS} টি পোস্ট) পূর্ণ হয়েছে।")
        return

    posted_set = set(data.get("posted", []))

    if not data.get("queue"):
        print("ব্লার্ট থেকে ১ বছর আগের পোস্ট আনা হচ্ছে...")
        fetched_permlinks = fetch_one_year_old_posts(posted_set)
        data["queue"] = fetched_permlinks
        save_data(data)

    if not data["queue"]:
        print("পোস্ট করার মতো কোনো নতুন পোস্ট পাওয়া যায়নি।")
        return

    # প্রতি রানে ১টি করে পোস্ট পাঠানো হবে
    permlink_to_post = data["queue"].pop(0)
    post_info = get_post_details(permlink_to_post)

    if not post_info or "title" not in post_info:
        print(f"পোস্ট ডিটেইলস মেলেনি, স্কিপ: {permlink_to_post}")
        data.setdefault("posted", []).append(permlink_to_post)
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

    print(f"\nপ্রসেস করা হচ্ছে: {title}")
    success = post_to_serey_direct(token, title, body, tags)

    if success:
        data.setdefault("posted", []).append(permlink_to_post)
        data.setdefault("timestamps", []).append(current_time)
        print("ডাটা সেভ করা হয়েছে।")
    else:
        # সফল না হলে কিউয়ের শেষে দিয়ে রাখা হলো
        data["queue"].append(permlink_to_post)

    save_data(data)
    print("\nপ্রক্রিয়া সম্পূর্ণ হয়েছে।")


if __name__ == "__main__":
    main()
