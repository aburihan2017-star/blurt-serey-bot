# Bengali Community-এর পরিচিত আইডি (যদি আপনার কাছে নির্দিষ্ট MongoDB ObjectId থাকে তবে সেটি দিন)
# সাধারণ ক্ষেত্রে Serey Bangladesh-এ এটি "Bangladesh" অথবা "Bengali Community" বা প্ল্যাটফর্ম আইডি হয়
DEFAULT_COMMUNITY_ID = "Bangladesh" 

def find_community_id(token):
    # GET রিকোয়েস্টের জন্য ক্লিন হেডার (Content-Type ছাড়া) ব্যবহার করুন
    headers = {
        "User-Agent": BASE_HEADERS["User-Agent"],
        "Authorization": f"Bearer {token}",
        "Accept": "application/json"
    }
    
    urls = [
        "https://bangladesh.serey.io/api/communities",
        "https://global-api.serey.io/api/v2/communities",
        "https://bangladesh.serey.io/api/community"
    ]
    
    for u in urls:
        try:
            r = requests.get(u, headers=headers, timeout=8)
            print(f"চেক {u} -> স্ট্যাটাস: {r.status_code}")
            if r.status_code == 200:
                m = re.search(r'"(?:_id|id)"\s*:\s*"([^"]+)"[^}]*?"name"\s*:\s*"Bengali Community"', r.text, re.I)
                if not m:
                    m = re.search(r'"name"\s*:\s*"Bengali Community"[^}]*?"(?:_id|id)"\s*:\s*"([^"]+)"', r.text, re.I)
                if m:
                    cid = m.group(1)
                    print(f"Bengali Community ID পাওয়া গেছে: {cid}")
                    return cid
        except Exception:
            pass
            
    # যদি API কাজ না করে, তবে ফলব্যাক আইডি ব্যবহার করবে
    print(f"API থেকে আইডি পাওয়া যায়নি। ডিফল্ট হিসেবে '{DEFAULT_COMMUNITY_ID}' ব্যবহার করা হচ্ছে।")
    return DEFAULT_COMMUNITY_ID# comm_id না পাওয়া গেলে ডিফল্ট ভ্যালু দিন
    if not comm_id:
        comm_id = "Bangladesh"

    payload = {
        "title": title,
        "content": full_body,
        "body": full_body,
        "description": full_body[:150],
        "categories": cat,
        "category": cat,
        "author": SEREY_USER,
        "community": comm_id,
        "communityId": comm_id,
        "platform": "Bangladesh"
    }
