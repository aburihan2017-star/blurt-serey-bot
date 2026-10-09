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


def is_post_live(title):
    """সেরি ওয়েবসাইটে পোস্টটি সরাসরি লাইভ হয়েছে কিনা নিশ্চিত করা"""
    try:
        url = f"https://global-api.serey.io/api/v2/serey-web/list-by-author?author={SEREY_USER}&limit=5&offset=0"
        r = requests.get(url, headers=BASE_HEADERS, timeout=15)
        if r.status_code == 200:
            posts = r.json().get("posts", [])
            for p in posts:
                p_title = p.get("title", "")
                if title.strip().lower() == p_title.strip().lower():
                    return True
    except Exception:
        pass
    return False


def post_to_serey_native(token, title, body, tags=None):
    """সরাসরি অফিশিয়াল পাবলিশ API কল করা (ড্রাফট এভয়েড করে সরাসরি পোস্ট)"""
    headers = dict(BASE_HEADERS)
    headers["Authorization"] = f"Bearer {token}"

    final_tags = ["news", "bengali-community", "others"]
    if tags:
        for t in tags:
            clean_t = re.sub(r'[^a-z0-9\-]', '', str(t).lower().strip())
            if clean_t and clean_t not in final_tags:
                final_tags.append(clean_t)

    # ইউনিক পারমালিঙ্ক
    clean_title = re.sub(r'[^a-z0-9]+', '-', title.lower()).strip('-')
    unique_permlink = f"{clean_title[:40]}-{int(time.time())}"

    # সরাসরি আর্টিকেল পোস্ট করার এন্ডপয়েন্ট
    post_payload = {
        "title": title,
        "body": body,
        "permlink": unique_permlink,
        "community": COMMUNITY_NAME,
        "community_id": COMMUNITY_ID,
        "categories": "news",
        "tags": final_tags,
        "status": "publish",
        "is_published": True,
        "publish": True,
    }

    # ১. সরাসরি আর্টিকেল তৈরির এন্ডপয়েন্টে চেষ্টা
    endpoints = [
        "https://global-api.serey.io/api/v2/articles",
        "https://global-api.serey.io/api/v2/posts",
        "https://bengali.serey.io/api/post",
    ]

    for ep in endpoints:
        try:
            r = requests.post(ep, json=post_payload, headers=headers, timeout=25)
            if r.status_code in [200, 201]:
                print(f"🎉 পোস্ট সরাসরি এপিআই দিয়ে লাইভ হয়েছে ({ep})!")
                time.sleep(3)
                if is_post_live(title):
                    return True
        except Exception:
            pass

    # ২. ড্রাফট ও পাবলিশ ফ্লো (যাতে ইন-প্রোগ্রেস এড়িয়ে ফ্রেশ পাবলিশ নিশ্চিত হয়)
    draft_url = "https://global-api.serey.io/api/v2/draft-post/create-or-update"
    draft_payload = {
        "title": title,
        "community": COMMUNITY_NAME,
        "community_id": COMMUNITY_ID,
        "tags": final_tags,
        "posts": [
            {
                "title": title,
                "body": body,
                "posts": body,
                "tags": final_tags,
                "categories": "news",
                "community": COMMUNITY_NAME,
                "community_id": COMMUNITY_ID,
            }
        ],
    }

    try:
        print("ধাপ ১: ফ্রেশ ড্রাফট তৈরি করা হচ্ছে...")
        r = requests.post(draft_url, json=draft_payload, headers=headers, timeout=35)
        if r.status_code in [200, 201]:
            time.sleep(3)
            # ড্রাফট আইডি আনা
            list_url = "https://global-api.serey.io/api/v2/draft-post/list-by-current-user"
            lr = requests.get(list_url, headers=headers, timeout=25)
            if lr.status_code == 200:
                draft_list = lr.json().get("draft_posts") or []
                if draft_list:
                    sorted_drafts = sorted(draft_list, key=lambda x: int(x.get("id", 0)), reverse=True)
                    draft_id = str(sorted_drafts[0].get("id"))
                    
                    print(f"ধাপ ২: ড্রাফট আইডি {draft_id} দিয়ে পাবলিশ রিকোয়েস্ট পাঠানো হচ্ছে...")
                    publish_url = f"https://global-api.serey.io/api/v2/draft-post/publish-by-id/{draft_id}"
                    
                    # সম্পূর্ণ মেটাডাটা সহ পাবলিশ কল
                    pr = requests.post(
                        publish_url,
                        json={"id": int(draft_id), "community_id": COMMUNITY_ID, "categories": "news"},
                        headers=headers,
                        timeout=35
                    )
                    print(f"পাবলিশ রেসপন্স ({pr.status_code}): {pr.text}")
                    
                    # ১৫ সেকেন্ড অপেক্ষা করে প্রোফাইল থেকে যাচাই
                    print("🔍 পোস্টটি প্রোফাইলে এসেছে কিনা যাচাই করা হচ্ছে...")
                    for check_round in range(1, 4):
                        time.sleep(5)
                        if is_post_live(title):
                            print(f"🎉🎉 পোস্ট নিশ্চিতভাবে আপনার প্রোফাইলে লাইভ হয়ে গেছে: {title}")
                            return True
    except Exception as e:
        print(f"পোস্ট এরর: {e}")

    # সর্বশেষ প্রোফাইল চেক
    if is_post_live(title):
        print(f"🎉🎉 পোস্টটি লাইভ তালিকায় পাওয়া গেছে: {title}")
        return True

    print("❌ পোস্টটি লাইভ হয়নি।")
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
    success = post_to_serey_native(token, title, body, tags)

    if success:
        data.setdefault("posted", []).append(permlink_to_post)
        data.setdefault("timestamps", []).append(current_time)
        print("ডাটা সেভ করা হয়েছে।")
    else:
        # সফল না হলে টাইমস্ট্যাম্প যোগ হবে না এবং পোস্টটি কিউতে থাকবে
        print("পোস্ট লাইভ না হওয়ায় টাইমস্ট্যাম্পে যোগ করা হয়নি।")
        data["queue"].append(permlink_to_post)

    save_data(data)
    print("\nপ্রক্রিয়া সম্পূর্ণ হয়েছে।")


if __name__ == "__main__":
    main()
