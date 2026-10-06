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
    "User-Agent": "Mozilla/5.0 (Linux; Android 10; K) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Mobile Safari/537.36",
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
    """লগইন করে সেশন টোকেন নেওয়া"""
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
    except Exception as e:
        print(f"লগইন এরর: {e}")
    return None


def get_categories(token):
    """bangladesh.serey.io এর ড্রপডাউন ক্যাটাগরিগুলো ফেচ করা"""
    cat_urls = [
        "https://bangladesh.serey.io/api/categories",
        "https://bangladesh.serey.io/api/category",
        "https://global-api.serey.io/api/v2/categories",
    ]
    headers = dict(BASE_HEADERS)
    headers["Authorization"] = f"Bearer {token}"

    for url in cat_urls:
        try:
            r = requests.get(url, headers=headers, timeout=10)
            if r.status_code == 200:
                res_data = r.json()
                cats = (
                    res_data.get("data")
                    if isinstance(res_data, dict) and "data" in res_data
                    else res_data
                )
                if isinstance(cats, list) and len(cats) > 0:
                    print(
                        f"ক্যাটাগরি তালিকা পাওয়া গেছে ({len(cats)}টি ক্যাটাগরি)"
                    )
                    return cats
        except Exception:
            continue
    return []


def submit_to_bangladesh_serey(title, body, created_date):
    print(f"bangladesh.serey.io তে পোস্ট প্রস্তুত হচ্ছে: {title}")

    token = get_serey_auth_token()
    if not token:
        print("লগইন টোকেন পাওয়া যায়নি।")
        return False

    print("লগইন সফল! ড্রপডাউন ডাটা প্রসেস করা হচ্ছে...")
    categories_list = get_categories(token)

    # সোর্স ক্রেডিট
    date_str = created_date.split("T")[0] if created_date else "1 year ago"
    footer = f"\n\n---\n*Originally written and published on Blurt by @{BLURT_USER} on {date_str}*"
    full_body = body + footer

    # ক্যাটাগরি নির্বাচন
    cat_val = None
    sub_cat_val = None

    if categories_list and isinstance(categories_list[0], dict):
        first_cat = categories_list[0]
        cat_val = first_cat.get("id") or first_cat.get("_id")
        sub_list = first_cat.get("subCategories", [])
        if sub_list and isinstance(sub_list[0], dict):
            sub_cat_val = sub_list[0].get("id") or sub_list[0].get("_id")
        elif sub_list:
            sub_cat_val = sub_list[0]

    headers = dict(BASE_HEADERS)
    headers["Authorization"] = f"Bearer {token}"

    # আসল পোস্টিং এন্ডপয়েন্ট (bangladesh.serey.io)
    post_urls = [
        "https://bangladesh.serey.io/api/posts",
        "https://bengali.serey.io/api/posts",
    ]

    # সার্ভারের চাওয়া 'categories' ফিল্ড সহ পে-লোড
    post_payload = {
        "title": title,
        "content": full_body,
        "description": full_body[:120],
        "community": "bangladesh",
        "categories": [cat_val] if cat_val else ["general"],
        "category": cat_val or "general",
        "subCategory": sub_cat_val,
        "author": SEREY_USER,
    }

    for url in post_urls:
        try:
            res = requests.post(
                url, json=post_payload, headers=headers, timeout=15
            )
            print(f"পোস্ট চেষ্টা ({url}) -> কোড: {res.status_code}")
            print(f"সার্ভার মেসেজ: {res.text}")

            if res.status_code in [200, 201]:
                print(
                    "অভিনন্দন! সফলভাবে bangladesh.serey.io তে পোস্ট লাইভ পাবলিশ হয়েছে!"
                )
                return True
        except Exception as e:
            print(f"পোস্ট সাবমিট এরর ({url}): {e}")

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

        success = submit_to_bangladesh_serey(title, body, created)

        if success:
            data["posted"].append(next_permlink)
            data["timestamps"].append(now)
            save_data(data)
            print(
                f"পোস্ট সফল! (আজকের পোস্ট সংখ্যা: {len(data['timestamps'])}/{MAX_DAILY_POSTS})"
            )
        else:
            data["queue"].insert(0, next_permlink)
            save_data(data)
    else:
        print("পোস্টের তথ্য রিড করা যায়নি।")
        save_data(data)


if __name__ == "__main__":
    run()
