"""Validate -> NLP -> MongoDB.

  python -m scripts.seed_database data/reviews_100000.jsonl --meta data/meta_Musical_Instruments.jsonl
  python -m scripts.seed_database --derived-only --meta data/meta_Musical_Instruments.jsonl
      (rebuild products + users from reviews already in MongoDB; skips the slow NLP pass)

Idempotent: re-running never duplicates rows. The raw dump contains ~1% duplicate review ids,
so rows are de-duplicated inside each batch (last one wins) before writing.
Without --meta, products exist but have name=None.
"""
import argparse
import os
import sys
import time
from collections import Counter

from pymongo import ASCENDING

from backend.database.mongo import require_db
from ingestion.amazon import iter_jsonl, to_product, to_review
from nlp.pipeline import analyze

BATCH = 2000


def load_meta(path, wanted: set) -> dict:
    found = {}
    for _, row in iter_jsonl(path):
        pid = row.get("parent_asin") if isinstance(row, dict) else None
        if pid in wanted:
            found[pid] = to_product(row)
            if len(found) == len(wanted):
                break
    return found


def upsert_many(coll, key, docs):
    """Idempotent bulk write: de-dupe on key, delete existing keys, one unordered insert_many."""
    docs = list({d[key]: d for d in docs}.values())
    if docs:
        coll.delete_many({key: {"$in": [d[key] for d in docs]}})
        coll.insert_many(docs, ordered=False)


def ensure_indexes(db):
    db.reviews.create_index([("review_id", ASCENDING)], unique=True)
    db.reviews.create_index([("product_id", ASCENDING), ("review_date", ASCENDING)])
    db.reviews.create_index([("sentiment", ASCENDING)])
    db.reviews.create_index([("aspects", ASCENDING)])
    db.products.create_index([("product_id", ASCENDING)], unique=True)
    db.users.create_index([("user_id", ASCENDING)], unique=True)
    db.analytics.create_index([("key", ASCENDING), ("scope", ASCENDING)], unique=True)


def load_reviews(db, path, log):
    rejects, batch, n_ok, t0 = Counter(), [], 0, time.time()

    def flush():
        upsert_many(db.reviews, "review_id", batch)
        batch.clear()

    for _, raw in iter_jsonl(path):
        doc, why = to_review(raw)
        if doc is None:
            rejects[why or "bad_json"] += 1
            continue
        doc.update(analyze(doc["full_text"], doc["rating"]))
        doc.pop("label_sentiment")          # same value as analyze()'s `sentiment`
        batch.append(doc)
        n_ok += 1
        if len(batch) >= BATCH:
            flush()
            log(f"  {n_ok:,} reviews  ({n_ok / (time.time() - t0):,.0f}/s)")
    flush()
    return n_ok, dict(rejects), round(time.time() - t0, 1)


def build_derived(db, meta_path, log):
    """products (+ names back onto reviews) and users, all computed from reviews in MongoDB."""
    product_ids = set(db.reviews.distinct("product_id"))
    meta = load_meta(meta_path, product_ids) if meta_path else {}
    docs = [dict(meta.get(pid, {"product_id": pid, "name": None, "category": "Musical Instruments"}))
            for pid in product_ids]
    for i in range(0, len(docs), BATCH):
        upsert_many(db.products, "product_id", docs[i:i + BATCH])
    for pid, p in meta.items():
        if p.get("name"):
            db.reviews.update_many({"product_id": pid}, {"$set": {"product_name": p["name"]}})
    # users: derived from the loaded subset only (not lifetime Amazon stats)
    users = [{"user_id": r["_id"], "review_count": r["n"], "avg_rating": round(r["avg"], 3)}
             for r in db.reviews.aggregate([{"$group": {"_id": "$user_id", "n": {"$sum": 1},
                                                       "avg": {"$avg": "$rating"}}}])]
    for i in range(0, len(users), BATCH):
        upsert_many(db.users, "user_id", users[i:i + BATCH])
    log(f"  products: {len(product_ids):,} ({len(meta):,} with metadata)   users: {len(users):,}")
    return len(product_ids), len(meta), len(users)


def seed(path=None, meta_path=None, db=None, log=print, derived_only=False):
    if meta_path and not os.path.exists(meta_path):       # fail in 1 second, not after a 6-minute run
        raise FileNotFoundError(f"Metadata file not found: {meta_path}  (omit --meta to load without product names)")
    db = db if db is not None else require_db()
    ensure_indexes(db)
    n_ok, rejected, secs = 0, {}, 0
    if not derived_only:
        n_ok, rejected, secs = load_reviews(db, path, log)
    n_prod, n_meta, n_users = build_derived(db, meta_path, log)
    summary = {"reviews_loaded": n_ok, "rejected": rejected, "products": n_prod,
               "products_with_metadata": n_meta, "users": n_users, "seconds": secs}
    log(f"done: {summary}")
    return summary


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("path", nargs="?")
    ap.add_argument("--meta", default=None)
    ap.add_argument("--derived-only", action="store_true")
    a = ap.parse_args()
    if not a.derived_only and not a.path:
        ap.error("path is required unless --derived-only")
    try:
        seed(a.path, a.meta, derived_only=a.derived_only)
    except FileNotFoundError as e:
        sys.exit(str(e))
