import json
import os
import re
import time
from datetime import datetime, timedelta
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
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
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
                or (
                    data.get("data", {}).get("token")
                    if isinstance(data.get("data"), dict)
                    else None
                )
            )
            # লগইন রেসপন্স থেকেই কোনো Community ObjectId পাওয়া যায় কি না দেখা
            comm_from_login = None
            m = re.search(r'"(?:community|_community|communityId)"\s*:\s*"([a-f0-9]{24})"', r.text)
            if m:
                comm_from_login = m.group(1)
            return token, comm_from_login
        else:
            print(f"লগইন রেসপন্স: {r.status_code}")
    except Exception as e:
        print(f"লগইন এরর: {e}")
    return None, None


def find_community_id(token, fallback_id=None):
    if fallback_id:
        print(f"লগইন ডাটা থেকে কমিউনিটি আইডি পাওয়া গেছে: {fallback_id}")
        return fallback_id

    session = requests.Session()
    session.headers.update({
        "User-Agent": BASE_HEADERS["User-Agent"],
        "Authorization": f"Bearer {token}",
    })

    # ১. blog/new পেজ স্ক্র্যাপ করে আইডি খোঁজা (এই পেজটিতে সব কমিউনিটির আইডি লোড থাকে)
    web_pages = [
        "https://bangladesh.serey.io/blog/new",
        "https://bangladesh.serey.io",
    ]
    for page in web_pages:
        try:
            r = session.get(page, timeout=10)
            print(f"চেক পেজ {page} -> স্ট্যাটাস: {r.status_code}")
            if r.status_code == 200:
                text = r.text
                # Bengali Community এর ObjectId খোঁজা
                m = re.search(r'"(?:_id|id)"\s*:\s*"([a-f0-9]{24})"[^}]*?"(?:name|title)"\s*:\s*"[^"]*Bengali[^"]*"', text, re.I)
                if not m:
                    m = re.search(r'"(?:name|title)"\s*:\s*"[^"]*Bengali[^"]*"[^}]*?"(?:_id|id)"\s*:\s*"([a-f0-9]{24})"', text, re.I)
                if not m:
                    # যে কোনো ভ্যালিড ২৪ অক্ষরের ObjectId খুঁজে নেওয়া
                    m = re.search(r'"community(?:Id)?"\s*:\s*"([a-f0-9]{24})"', text)
                if not m:
                    # __NEXT_DATA__ ট্যাগ থেকে আইডি বের করা
                    m_next = re.search(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', text)
                    if m_next:
                        ids = re.findall(r'"_id"\s*:\s*"([a-f0-9]{24})"', m_next.group(1))
                        if ids:
                            print(f"NEXT_DATA থেকে কমিউনিটি আইডি পাওয়া গেছে: {ids[0]}")
                            return ids[0]

                if m:
                    cid = m.group(1)
                    print(f"ওয়েবপেজ থেকে Bengali Community ID পাওয়া গেছে: {cid}")
                    return cid
        except Exception as e:
            print(f"পেজ ফেচ এরর: {e}")

    # ২. সাম্প্রতিক পোস্ট ও ক্যাটাগরি এন্ডপয়েন্ট থেকে আইডি খোঁজা
    api_urls = [
        "https://bangladesh.serey.io/api/categories",
        "https://bangladesh.serey.io/api/posts?limit=5",
        "https://global-api.serey.io/api/v2/categories",
        "https://global-api.serey.io/api/v2/posts?limit=5",
    ]
    for api in api_urls:
        try:
            r = session.get(api, timeout=8)
            print(f"চেক API {api} -> স্ট্যাটাস: {r.status_code}")
            if r.status_code == 200:
                ids = re.findall(r'"(?:_id|community|communityId)"\s*:\s*"([a-f0-9]{24})"', r.text)
                if ids:
                    pr
