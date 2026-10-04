"""Stream a reviews file once and print/save a data-quality profile.

python -m scripts.profile_dataset data/Musical_Instruments.jsonl[.gz] [--out data/profile.json]
Memory stays flat except two sets of hashed ids (users, products).
"""
import argparse
import json
import random
from collections import Counter

from ingestion.amazon import iter_jsonl, to_review


def pct(sorted_vals, p):
    return sorted_vals[min(len(sorted_vals) - 1, int(p / 100 * len(sorted_vals)))] if sorted_vals else None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("path")
    ap.add_argument("--out", default="data/profile.json")
    ap.add_argument("--limit", type=int, default=0, help="stop after N lines (quick look)")
    a = ap.parse_args()

    rows = bad = 0
    reasons, ratings, years = Counter(), Counter(), Counter()
    verified = voted = with_img = 0
    users, prods = set(), set()
    lens, rng = [], random.Random(7)          # reservoir of 50k lengths for percentiles
    seen_ids = set()
    dupes = 0

    for n, raw in iter_jsonl(a.path):
        rows += 1
        if a.limit and rows > a.limit:
            rows -= 1
            break
        doc, why = to_review(raw)
        if doc is None:
            bad += 1
            reasons[why or "bad_json"] += 1
            continue
        h = hash(doc["review_id"])
        if h in seen_ids:
            dupes += 1
        else:
            seen_ids.add(h)
        ratings[doc["rating"]] += 1
        years[doc["review_date"].year] += 1
        verified += doc["verified_purchase"]
        voted += doc["helpful_votes"] > 0
        with_img += doc["image_count"] > 0
        users.add(hash(doc["user_id"]))
        prods.add(hash(doc["product_id"]))
        if len(lens) < 50_000:
            lens.append(doc["n_chars"])
        elif (j := rng.randint(0, rows)) < 50_000:
            lens[j] = doc["n_chars"]
        if rows % 250_000 == 0:
            print(f"  ...{rows:,} lines")

    ok = rows - bad
    lens.sort()
    prof = {
        "file": a.path, "lines": rows, "valid": ok, "rejected": bad, "reject_reasons": dict(reasons),
        "duplicate_review_ids": dupes, "users": len(users), "products": len(prods),
        "rating_counts": {str(k): ratings[k] for k in sorted(ratings)},
        "rating_pct": {str(k): round(100 * ratings[k] / ok, 2) for k in sorted(ratings)} if ok else {},
        "verified_pct": round(100 * verified / ok, 2) if ok else None,
        "with_helpful_vote_pct": round(100 * voted / ok, 2) if ok else None,
        "with_images_pct": round(100 * with_img / ok, 2) if ok else None,
        "text_chars": {f"p{p}": pct(lens, p) for p in (5, 25, 50, 75, 95, 99)},
        "reviews_per_year": {str(k): years[k] for k in sorted(years)},
    }
    with open(a.out, "w") as fh:
        json.dump(prof, fh, indent=2)
    print(json.dumps(prof, indent=2))
    print(f"\nsaved -> {a.out}")


if __name__ == "__main__":
    main()
