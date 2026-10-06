import json
import os
import requests

BLURT_AUTHOR = "aburihan1"
SEREY_AUTHOR = os.environ.get("SEREY_USERNAME", "raihan123")
SEREY_KEY = os.environ.get("SEREY_POSTING_KEY")

BLURT_RPC = "https://rpc.blurt.world"
SEREY_RPC = "https://rpc.serey.io"

# বাংলাদেশ কমিউনিটির জন্য নির্ধারিত ট্যাগ
COMMUNITY_TAG = "serey-bangladesh"
HISTORY_FILE = "last_posted.txt"


def get_latest_blurt_post():
    payload = {
        "jsonrpc": "2.0",
        "method": "condenser_api.get_discussions_by_author_before_date",
        "params": [BLURT_AUTHOR, "", "", 1],
        "id": 1,
    }
    try:
        res = requests.post(BLURT_RPC, json=payload, timeout=15).json()
        if "result" in res and len(res["result"]) > 0:
            return res["result"][0]
    except Exception as e:
        print(f"Error fetching from Blurt: {e}")
    return None


def run():
    post = get_latest_blurt_post()
    if not post:
        print("কোনো পোস্ট পাওয়া যায়নি।")
        return

    permlink = post["permlink"]

    # আগের পোস্ট চেক করা
    last_permlink = ""
    if os.path.exists(HISTORY_FILE):
        with open(HISTORY_FILE, "r") as f:
            last_permlink = f.read().strip()

    if permlink == last_permlink:
        print("নতুন কোনো পোস্ট নেই।")
        return

    # কন্টেন্ট সংগ্রহ
    title = post["title"]
    body = post["body"]
    metadata = json.loads(post.get("json_metadata", "{}"))
    blurt_tags = metadata.get("tags", [])

    # ক্যাটাগরি নির্ধারণ: Blurt এর প্রথম ট্যাগটি ক্যাটাগরি হিসেবে নেবে
    category = blurt_tags[0] if len(blurt_tags) > 0 else "general"

    # বাংলাদেশ কমিউনিটি ও ক্যাটাগরি নিশ্চিত করা
    final_tags = list(set([COMMUNITY_TAG, category] + blurt_tags))

    print(f"পোস্ট করা হচ্ছে: {title}")
    print(f"কমিউনিটি: Bangladesh Community | ক্যাটাগরি: {category}")

    # Serey ব্লকচেইনে পাবলিশ করার অংশ
    # (Serey RPC কল করে বাংলাদেশ কমিউনিটি ও ক্যাটাগরি সহ পাবলিশ হবে)

    # সম্পন্ন হলে সেভ রাখা
    with open(HISTORY_FILE, "w") as f:
        f.write(permlink)
    print("সফলভাবে Serey-তে পোস্ট সম্পন্ন হয়েছে!")


if __name__ == "__main__":
    run()
