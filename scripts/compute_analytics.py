"""Compute per-product health/aspect/trend analytics and portfolio totals into the `analytics` collection.

  python -m scripts.compute_analytics            (run again after seeding or after loading product names)

One streaming pass over `reviews` (sorted by product_id via the index), so memory stays small.
Products with fewer than --min-store reviews are skipped: a handful of reviews cannot support a score.
"""
import argparse
import datetime as dt
from itertools import groupby
from operator import itemgetter

from analytics.health import GlobalAccumulator, product_stats
from backend.database.mongo import require_db
from scripts.seed_database import ensure_indexes

FIELDS = {"product_id": 1, "rating": 1, "sentiment": 1, "aspect_sentiments": 1, "review_date": 1, "_id": 0}


def compute(db=None, min_store=5, log=print):
    db = db if db is not None else require_db()
    ensure_indexes(db)
    names = {p["product_id"]: p.get("name") for p in db.products.find({}, {"product_id": 1, "name": 1, "_id": 0})}
    now, acc, docs, stored, total = dt.datetime.now(dt.timezone.utc), GlobalAccumulator(), [], 0, 0
    db.analytics.delete_many({"key": "product_health"})

    def flush():
        if docs:
            db.analytics.insert_many(docs, ordered=False)
            docs.clear()

    cur = db.reviews.find({"sentiment": {"$exists": True}, "review_date": {"$exists": True}}, FIELDS).sort("product_id", 1)
    for pid, grp in groupby(cur, key=itemgetter("product_id")):
        revs = list(grp)
        total += len(revs)
        for r in revs:
            acc.add(r)
        if len(revs) >= min_store:
            docs.append({"key": "product_health", "scope": pid, "job": "compute_analytics", "computed_at": now,
                         "data": product_stats(revs, pid, names.get(pid))})
            stored += 1
            if len(docs) >= 1000:
                flush()
    flush()
    db.analytics.delete_many({"key": "global_summary"})
    db.analytics.insert_one({"key": "global_summary", "scope": "global", "job": "compute_analytics",
                             "computed_at": now, "data": {**acc.result(), "total_reviews": total}})
    scores = sorted(d["data"]["health"]["score"] for d in db.analytics.find({"key": "product_health", "data.n_reviews": {"$gte": 20}}))
    summary = {"reviews_scanned": total, "products_stored": stored,
               "products_with_20plus_reviews": len(scores),
               "health_min_median_max": [scores[0], scores[len(scores) // 2], scores[-1]] if scores else None}
    log(f"done: {summary}")
    return summary


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--min-store", type=int, default=5)
    compute(None, ap.parse_args().min_store)
