import re, html, hashlib, unicodedata
from datetime import datetime, timezone

def now():
    return datetime.now(timezone.utc).isoformat()

def digest(value):
    return hashlib.sha256((value or "").encode("utf-8")).hexdigest()

def clean_text(value):
    text = html.unescape(str(value or ""))
    text = re.sub(r"<[^>]+>", " ", text)
    text = unicodedata.normalize("NFKC", text)
    text = re.sub(r"https?://\S+|www\.\S+", "[URL]", text, flags=re.I)
    text = re.sub(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", "[EMAIL]", text, flags=re.I)
    text = re.sub(r"\s+", " ", text).strip()
    return text
