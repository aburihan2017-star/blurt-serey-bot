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


def clear_stuck_drafts(headers):
    list_url = "https://global-api.serey.io/api/v2/draft-post/list-by-current-user"
    try:
        lr = requests.get(list_url, headers=headers, timeout=20)
        if lr.status_code == 200:
            draft_list = lr.json().get("draft_posts", [])
            if draft_list:
                for d in draft_list:
                    d_id = d.get("id") or d.get("_id")
                    if d_id:
                        del_url = f"https://global-api.serey.io/api/v2/draft-post/delete-by-id/{d_id}"
                        requests.delete(del_url, headers=headers, timeout=15)
                time.sleep(2)
    except Exception:
        pass


def post_to_serey_verified(token, title, body, tags=None):
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


def clear_stuck_drafts(headers):
    list_url = "https://global-api.serey.io/api/v2/draft-post/list-by-current-user"
    try:
        lr = requests.get(list_url, headers=headers, timeout=20)
        if lr.status_code == 200:
            draft_list = lr.json().get("draft_posts", [])
            if draft_list:
                for d in draft_list:
                    d_id = d.get("id") or d.get("_id")
                    if d_id:
                        del_url = f"https://global-api.serey.io/api/v2/draft-post/delete-by-id/{d_id}"
                        requests.delete(del_url, headers=headers, timeout=15)
                time.sleep(2)
    except Exception:
        pass


def post_to_serey_verified(token, title, body, tags=None):
    headers = dict(BASE_HEADERS)
    headers["Authorization"] = f"Bearer {token}"

    final_tags = ["news", "bengali-community", "others"]
    if tags:
        for t in tags:
            clean_t = re.sub(r'[^a-z0-9\-]', '', str(t).lower().strip())
            if clean_t and clean_t not in final_tags:
                final_tags.append(clean_t)

    clear_stuck_drafts(headers)

    # HTML ফরম্যাটিং
    formatted_body = body
    if not ("<p>" in formatted_body or "<div>" in formatted_body):
        formatted_body = f"<p>{body.replace(chr(10) + chr(10), '</p><p>').replace(chr(10), '<br/>')}</p>"

    # রান #৪৩ এর সফল ফরম্যাট অনুযায়ী ড্রাফট তৈরি
    draft_url = "https://global-api.serey.io/api/v2/draft-post/create-or-update"
    draft_payload = {
        "title": title,
        "community": COMMUNITY_NAME,
        "community_id": COMMUNITY_ID,
        "tags": final_tags,
        "posts": [
            {
                "title": title,
                "body": formatted_body,
                "posts": formatted_body,
                "tags": final_tags,
                "categories": "news",
                "community": COMMUNITY_NAME,
                "community_id": COMMUNITY_ID,
            }
        ],
    }

    try:
        print("ধাপ ১: নতুন ড্রাফট তৈরি করা হচ্ছে...")
        r = requests.post(draft_url, json=draft_payload, headers=headers, timeout=35)
        print(f"ড্রাফট রেসপন্স ({r.status_code}): {r.text}")

        if r.status_code in [200, 201]:
            print("✅ ড্রাফট সফলভাবে তৈরি হয়েছে!")
            time.sleep(3)

            # আইডি সংগ্রহ
            list_url = "https://global-api.serey.io/api/v2/draft-post/list-by-current-user"
            lr = requests.get(list_url, headers=headers, timeout=25)
            
            draft_id = None
            if lr.status_code == 200:
                draft_list = lr.json().get("draft_posts") or []
                if draft_list:
                    sorted_drafts = sorted(draft_list, key=lambda x: int(x.get("id", 0)), reverse=True)
                    draft_id = str(sorted_drafts[0].get("id"))

            if not draft_id:
                print("❌ ড্রাফট আইডি পাওয়া যায়নি।")
                return False, False

            print(f"ধাপ ২: ড্রাফট আইডি {draft_id} দিয়ে লাইভ পাবলিশ করা হচ্ছে...")
            publish_url = f"https://global-api.serey.io/api/v2/draft-post/publish-by-id/{draft_id}"
            
            # রান #৪৩ এর প্রমাণিত কল
            pr = requests.post(publish_url, json={}, headers=headers, timeout=35)
            print(f"পাবলিশ রেসপন্স ({pr.status_code}): {pr.text}")

            if pr.status_code in [200, 201]:
                print(f"🎉🎉 পোস্ট সফলভাবে বাংলা কমিউনিটিতে লাইভ পাবলিশ হয়েছে: {title}")
                return True, False

            err_msg = pr.text.lower()
            if "inprogress" in err_msg or "in progress" in err_msg:
                print("⚠️ পোস্টটি অতীতে সেরিতে থাকায় ডুপ্লিকেট কনফ্লিক্ট হয়েছে। স্কিপ করা হচ্ছে...")
                return False, True
        else:
            print(f"ড্রাফট তৈরিতে ব্যর্থ: {r.text}")
    except Exception as e:
        print(f"পোস্ট এরর: {e}")

    return False, False


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

    # দৈনিক সীমা চেক
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

        print(f"\nপ্রসেস করা হচ্ছে: {title}")
        success, should_skip = post_to_serey_verified(token, title, body, tags)

        if success:
            data.setdefault("posted", []).append(permlink_to_post)
            data.setdefault("timestamps", []).append(current_time)
            print("ডাটা সেভ করা হয়েছে।")
            break
        elif should_skip:
            # অতীতে থাকা ডুপ্লিকেট পোস্ট স্বয়ংক্রিয়ভাবে স্কিপ করে পরের পোস্ট প্রসেস করবে
            print(f"⏩ ডুপ্লিকেট পোস্ট স্কিপ করে পরের পোস্ট দেখা হচ্ছে...")
            data.setdefault("posted", []).append(permlink_to_post)
            save_data(data)
            time.sleep(2)
            continue
        else:
            data["queue"].append(permlink_to_post)
            break

    save_data(data)
    print("\nপ্রক্রিয়া সম্পূর্ণ হয়েছে।")


if __name__ == "__main__":
    main() json_meta =
