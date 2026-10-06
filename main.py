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
    except Exception as e:
        print(f"লগইন এরর: {e}")
    return None


def find_community_id(token):
    """bangladesh.serey.io পেজ থেকে সরাসরি আসল Bengali Community ID রিড করা"""
    headers = dict(BASE_HEADERS)
    headers["Authorization"] = f"Bearer {token}"

    # ১. পেজ সোর্স থেকে খোঁজা
    try:
        page = requests.get(
            "https://bangladesh.serey.io/blog/new", headers=headers, timeout=10
        ).text
        matches = re.findall(
            r'\{[^{}]*?"name"\s*:\s*"Bengali Community"[^{}]*?\}', page
        )
        for m in matches:
            id_match = re.search(r'"(?:_id|id)"\s*:\s*"([^"]+)"', m)
            if id_match:
                cid = id_match.group(1)
                print(f"পেজ থেকে Bengali Community ID শনাক্ত হয়েছে: {cid}")
                return cid
    except Exception:
        pass

    # ২. সিস্টেম এপিআই এন্ডপয়েন্টগুলো স্ক্যান করা
    api_urls = [
        "https://global-api.serey.io/api/v2/communities",
        "https://global-api.serey.io/api/v2/platforms",
        "https://bangladesh.serey.io/api/communities",
        "https://global-api.serey.io/api/v2/community",
        "https://global-api.serey.io/api/v2/channels",
    ]

    for url in api_urls:
        try:
            r = requests.get(url, headers=headers, timeout=8)
            print(f"সিস্টেম চেক ({url}) -> স্ট্যাটাস: {r.status_code}")
            if r.status_code == 200:
                text = r.text
                print(f"সার্ভার ডাটা নমুনা: {text[:200]}")
                # Bengali Community খোঁজা
                m = re.search(
                    r'"(?:_id|id)"\s*:\s*"([a-f0-9]{24}|[0-9]+)"[^}]*?"name"\s*:\s*"Bengali Community"',
                    text,
                    re.I,
                )
                if not m:
                    m = re.search(
                        r'"name"\s*:\s*"Bengali Community"[^}]*?"(?:_id|id)"\s*:\s*"([a-f0-9]{24}|[0-9]+)"',
                        text,
                        re.I,
                    )
                if m:
                    cid = m.group(1)
                    print(
                        f"ডাটাবেজ থেকে আসল Bengali Community ID পাওয়া গেছে: {cid}"
                    )
                    return cid
        except Exception:
            continue

    return None


def detect_category(title, body):
    text = (title + " " + body).lower()
    if any(
        w in text
        for w in [
            "splinterlands",
            "game",
