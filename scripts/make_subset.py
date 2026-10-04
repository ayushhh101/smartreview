"""Draw a reproducible random sample of N valid reviews (raw JSONL, same format as the source).

python -m scripts.make_subset data/Musical_Instruments.jsonl --n 100000 --out data/reviews_100000.jsonl

Reservoir sampling: one pass, constant memory, uniform over valid rows, seeded.
Natural rating distribution is kept by default (Amazon is heavily 5-star skewed; Phase 3 handles
imbalance with class weights + macro-F1). --min-chars drops one-word reviews that carry no signal.
"""
import argparse
import json
import random

from ingestion.amazon import iter_jsonl, to_review


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("path")
    ap.add_argument("--n", type=int, default=100_000)
    ap.add_argument("--out", default=None)
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--min-chars", type=int, default=20)
    a = ap.parse_args()
    out = a.out or f"data/reviews_{a.n}.jsonl"

    rng = random.Random(a.seed)
    pool, seen, valid = [], set(), 0
    for _, raw in iter_jsonl(a.path):
        doc, _why = to_review(raw, min_chars=a.min_chars)
        if doc is None or doc["review_id"] in seen:
            continue
        valid += 1
        if len(pool) < a.n:
            pool.append(raw)
            seen.add(doc["review_id"])
        else:
            j = rng.randint(0, valid - 1)
            if j < a.n:
                pool[j] = raw            # duplicate ids can slip back in at most by chance; seeding upserts anyway
        if valid % 250_000 == 0:
            print(f"  ...{valid:,} valid rows scanned")

    rng.shuffle(pool)
    with open(out, "w", encoding="utf-8") as fh:
        for raw in pool:
            fh.write(json.dumps(raw, ensure_ascii=False) + "\n")
    print(f"scanned {valid:,} valid rows -> wrote {len(pool):,} to {out} (seed={a.seed})")


if __name__ == "__main__":
    main()
