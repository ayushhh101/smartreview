"""Amazon Reviews 2023 (McAuley Lab, UCSD) -> SmartReview review documents.

Pure functions, no I/O side effects, so every rule is unit-testable.

Raw review fields: rating, title, text, images, asin, parent_asin, user_id,
timestamp (epoch MILLISECONDS), helpful_vote, verified_purchase.
Raw metadata fields (meta_*.jsonl): parent_asin, title, main_category, store,
average_rating, rating_number, price, categories, ...

Design decisions
- product_id = parent_asin. `asin` is a colour/size variant; metadata is keyed by parent_asin.
- review_id = sha1(user_id|parent_asin|timestamp). The dataset has no review id.
- Sentiment label is derived from the star rating (<=2 neg, 3 neu, >=4 pos). This is
  a weak label, not human annotation (documented limitation).
"""
import gzip
import hashlib
import html
import json
import re
import unicodedata
from datetime import datetime, timezone

CATEGORY = "Musical Instruments"
MIN_YEAR, MAX_YEAR = 1996, 2023          # dataset spans May 1996 - Sep 2023

_TAGS = re.compile(r"<[^>]+>")
_WS = re.compile(r"\s+")


def open_text(path):
    """Open .jsonl or .jsonl.gz transparently."""
    p = str(path)
    return gzip.open(p, "rt", encoding="utf-8") if p.endswith(".gz") else open(p, encoding="utf-8")


def iter_jsonl(path):
    """Yield (line_no, obj_or_None). Bad JSON yields None instead of crashing a 500 MB run."""
    with open_text(path) as fh:
        for n, line in enumerate(fh, 1):
            line = line.strip()
            if not line:
                continue
            try:
                yield n, json.loads(line)
            except json.JSONDecodeError:
                yield n, None


def clean_text(s) -> str:
    """Decode entities, drop HTML tags (<br />), normalise unicode and whitespace."""
    if not isinstance(s, str):
        return ""
    s = html.unescape(s)
    s = _TAGS.sub(" ", s)
    s = unicodedata.normalize("NFKC", s)
    return _WS.sub(" ", s).strip()


def parse_timestamp(ts):
    """Epoch ms -> aware UTC datetime. Tolerates seconds. Returns None if implausible."""
    if isinstance(ts, bool) or not isinstance(ts, (int, float)):
        return None
    if ts < 1e11:          # looks like seconds
        ts *= 1000
    try:
        d = datetime.fromtimestamp(ts / 1000, tz=timezone.utc)
    except (OverflowError, OSError, ValueError):
        return None
    return d if MIN_YEAR <= d.year <= MAX_YEAR else None


def make_review_id(user_id, product_id, timestamp) -> str:
    return hashlib.sha1(f"{user_id}|{product_id}|{timestamp}".encode()).hexdigest()[:20]


def rating_to_sentiment(rating: int) -> str:
    return "negative" if rating <= 2 else "neutral" if rating == 3 else "positive"


def to_review(raw, category=CATEGORY, min_chars=1):
    """Return (document, None) or (None, reject_reason)."""
    if raw is None:
        return None, "bad_json"            # iter_jsonl yields None for unparseable lines
    if not isinstance(raw, dict):
        return None, "not_an_object"
    product_id = raw.get("parent_asin") or raw.get("asin")
    user_id = raw.get("user_id")
    if not product_id or not user_id:
        return None, "missing_ids"
    try:
        rating = float(raw.get("rating"))
    except (TypeError, ValueError):
        return None, "bad_rating"
    if rating not in (1.0, 2.0, 3.0, 4.0, 5.0):
        return None, "bad_rating"
    when = parse_timestamp(raw.get("timestamp"))
    if when is None:
        return None, "bad_timestamp"
    title, text = clean_text(raw.get("title")), clean_text(raw.get("text"))
    body = f"{title}. {text}" if title and text else (text or title)
    if len(text) < min_chars:
        return None, "text_too_short"
    return {
        "review_id": make_review_id(user_id, product_id, raw.get("timestamp")),
        "product_id": product_id,
        "asin": raw.get("asin"),
        "user_id": user_id,
        "category": category,
        "rating": int(rating),
        "title": title,
        "review_text": text,
        "full_text": body,                      # title + text: what the NLP pipeline reads
        "review_date": when,
        "verified_purchase": bool(raw.get("verified_purchase")),
        "helpful_votes": int(raw.get("helpful_vote") or 0),
        "image_count": len(raw.get("images") or []),
        "n_chars": len(text),
        "label_sentiment": rating_to_sentiment(int(rating)),
    }, None


def to_product(meta):
    """Subset of a meta_*.jsonl row that SmartReview uses."""
    price = meta.get("price")
    return {
        "product_id": meta.get("parent_asin"),
        "name": clean_text(meta.get("title")) or None,
        "category": CATEGORY,
        "main_category": meta.get("main_category"),
        "store": meta.get("store"),
        "price": price if isinstance(price, (int, float)) else None,
        "amazon_avg_rating": meta.get("average_rating"),
        "amazon_rating_number": meta.get("rating_number"),
    }
