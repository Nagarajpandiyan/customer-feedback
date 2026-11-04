"""No-key public adapters: Hacker News Algolia API and Stack Exchange API."""
import os, time, requests
from .common import now, digest

TIMEOUT = 20
YOUTUBE_URL = "https://www.googleapis.com/youtube/v3"
REDDIT_URL = "https://oauth.reddit.com"
HN_URL = "https://hn.algolia.com/api/v1"
STACKEXCHANGE_URL = "https://api.stackexchange.com/2.3"

def _verified_record(source, source_id, product_query, text, url, created_at,
                     engagement=0, author=None):
    # API response + canonical platform permalink verify platform provenance,
    # not whether the author's opinion is truthful.
    has_id = bool(source_id)
    has_url = bool(url and url.startswith(("https://www.youtube.com/", "https://www.reddit.com/", "https://news.ycombinator.com/", "https://stackoverflow.com/")))
    has_author = bool(author)
    has_time = bool(created_at)
    score = 30 + (20 if has_url else 0) + (15 if has_author else 0) + (10 if has_time else 0) + 15 + 10
    return {
        "source": source, "source_id": str(source_id), "product_query": product_query,
        "text": text, "url": url, "created_at": created_at, "engagement": int(engagement or 0),
        "author_hash": digest(author) if author else None, "collected_at": now(),
        "verification_status": "verified_api" if has_id and has_url else "partially_verified",
        "trust_score": min(score, 100),
        "verification_details": {
            "retrieval": "public_platform_api", "source_id_present": has_id,
            "canonical_url_present": has_url, "author_id_present": has_author,
            "timestamp_present": has_time,
            "scope": "Public API provenance only; does not prove opinion accuracy or author identity."
        }
    }

def fetch_youtube(keyword, limit):
    key = os.getenv("YOUTUBE_API_KEY", "").strip()
    if not key:
        raise RuntimeError("YOUTUBE_API_KEY is not configured")
    out=[]
    search = requests.get(f"{YOUTUBE_URL}/search", params={
        "key": key, "part": "id", "type": "video", "q": keyword,
        "maxResults": min(max(1, limit // 10 or 1), 10), "order": "relevance"
    }, timeout=TIMEOUT)
    search.raise_for_status()
    for video in search.json().get("items", []):
        video_id = video.get("id", {}).get("videoId")
        if not video_id: continue
        comments = requests.get(f"{YOUTUBE_URL}/commentThreads", params={
            "key": key, "part": "snippet", "videoId": video_id,
            "maxResults": min(max(limit, 1), 100), "textFormat": "plainText",
            "order": "relevance"
        }, timeout=TIMEOUT)
        if comments.status_code in (403, 404):
            # Comments may be disabled or inaccessible; continue with other videos.
            continue
        comments.raise_for_status()
        for item in comments.json().get("items", []):
            top = item.get("snippet", {}).get("topLevelComment", {})
            sn = top.get("snippet", {})
            cid = top.get("id") or item.get("id")
            text = sn.get("textDisplay", "")
            if not cid or not text: continue
            out.append(_verified_record(
                "youtube", cid, keyword, text,
                f"https://www.youtube.com/watch?v={video_id}&lc={cid}",
                sn.get("publishedAt"), sn.get("likeCount", 0),
                sn.get("authorChannelId", {}).get("value")
            ))
            if len(out) >= limit: return out
    return out

def _reddit_token():
    client_id=os.getenv("REDDIT_CLIENT_ID","").strip()
    client_secret=os.getenv("REDDIT_CLIENT_SECRET","").strip()
    user_agent=os.getenv("REDDIT_USER_AGENT","GNPFeedbackCollector/1.0 (academic project)").strip()
    if not client_id or not client_secret:
        raise RuntimeError("REDDIT_CLIENT_ID and REDDIT_CLIENT_SECRET are not configured")
    response=requests.post("https://www.reddit.com/api/v1/access_token",
        auth=(client_id,client_secret),
        data={"grant_type":"client_credentials"},
        headers={"User-Agent":user_agent}, timeout=TIMEOUT)
    response.raise_for_status()
    return response.json()["access_token"], user_agent

def fetch_reddit(keyword, limit):
    token, user_agent = _reddit_token()
    response=requests.get(f"{REDDIT_URL}/search.json",
        params={"q":keyword,"sort":"new","limit":min(max(limit,1),100),"type":"comment"},
        headers={"Authorization":f"Bearer {token}","User-Agent":user_agent},
        timeout=TIMEOUT)
    response.raise_for_status()
    out=[]
    for child in response.json().get("data",{}).get("children",[]):
        d=child.get("data",{})
        cid=d.get("id")
        body=d.get("body","")
        if not cid or not body or body in ("[deleted]","[removed]"): continue
        permalink=d.get("permalink","")
        url=("https://www.reddit.com"+permalink) if permalink.startswith("/") else None
        out.append(_verified_record("reddit",cid,keyword,body,url,
            time.strftime("%Y-%m-%dT%H:%M:%SZ",time.gmtime(d["created_utc"])) if d.get("created_utc") else None,
            d.get("score",0),d.get("author")))
    return out


def fetch_hackernews(keyword, limit):
    """Search public Hacker News comments through Algolia's public API."""
    response=requests.get(f"{HN_URL}/search_by_date",
        params={"query":keyword,"tags":"comment","hitsPerPage":min(max(limit,1),100)},
        timeout=TIMEOUT)
    response.raise_for_status()
    out=[]
    for hit in response.json().get("hits",[]):
        cid=hit.get("objectID")
        body=hit.get("comment_text") or ""
        if not cid or not body: continue
        story_id=hit.get("story_id")
        url=f"https://news.ycombinator.com/item?id={cid}"
        author=hit.get("author")
        created=hit.get("created_at")
        out.append(_verified_record("hackernews",cid,keyword,body,url,created,
                                    hit.get("points",0),author))
        if len(out)>=limit: break
    return out

def fetch_stackexchange(keyword, limit):
    """Search public Stack Overflow answers/questions through Stack Exchange API."""
    response=requests.get(f"{STACKEXCHANGE_URL}/search/advanced",
        params={"site":"stackoverflow","q":keyword,"order":"desc","sort":"relevance",
                "pagesize":min(max(limit,1),100),"filter":"withbody"},
        headers={"User-Agent":"GNPFeedbackCollector/1.0 (academic demo)"},
        timeout=TIMEOUT)
    response.raise_for_status()
    payload=response.json()
    out=[]
    for item in payload.get("items",[]):
        item_id=item.get("question_id") or item.get("answer_id") or item.get("post_id")
        body=item.get("body") or item.get("title") or ""
        if not item_id or not body: continue
        owner=item.get("owner") or {}
        created=time.strftime("%Y-%m-%dT%H:%M:%SZ",time.gmtime(item["creation_date"])) if item.get("creation_date") else None
        out.append(_verified_record("stackoverflow",item_id,keyword,body,item.get("link"),created,
                                    item.get("score",0),owner.get("user_id") or owner.get("display_name")))
        if len(out)>=limit: break
    return out

def collect_live(task):
    records=[]
    limit=max(1, min(int(task["batch_size"]), 100))
    for keyword in task["keywords"]:
        for source in task["sources"]:
            if source == "youtube":
                records.extend(fetch_youtube(keyword, limit-len(records)))
            elif source == "reddit":
                records.extend(fetch_reddit(keyword, limit-len(records)))
            elif source == "hackernews":
                records.extend(fetch_hackernews(keyword, limit-len(records)))
            elif source == "stackoverflow":
                records.extend(fetch_stackexchange(keyword, limit-len(records)))
            if len(records) >= limit: return records[:limit]
            time.sleep(1.0)  # polite spacing between API requests
    return records[:limit]
