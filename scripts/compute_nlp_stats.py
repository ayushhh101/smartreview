"""Corpus-level NLP statistics -> `analytics` (key=nlp_corpus) + models/lsa_words.joblib.

  python -m scripts.compute_nlp_stats                 (needs reviews seeded; ~1-2 minutes for 100k reviews)

Streams the reviews once. Topic modelling and word vectors use a seeded random sample (--sample, default 30000)
to keep it fast; the counters (vocabulary, Zipf, distinctive words, collocations) use every review.
"""
import argparse
import datetime as dt
import random
from collections import Counter

from backend.database.mongo import require_db
from ml import registry
from nlp import corpus as C

FIELDS = {"tokens": 1, "lemmas": 1, "bigrams": 1, "keywords": 1, "sentiment": 1, "rating": 1, "_id": 0}
CLASSES = ("negative", "neutral", "positive")


def compute(db=None, sample=30_000, log=print):
    db = db if db is not None else require_db()
    raw, lem, big = Counter(), Counter(), Counter()
    lem_c = {c: Counter() for c in CLASSES}
    big_c = {c: Counter() for c in CLASSES}
    kw = Counter()
    kw_c = {c: Counter() for c in CLASSES}
    pool, rng, n = [], random.Random(42), 0
    for d in db.reviews.find({"lemmas": {"$exists": True}}, FIELDS):
        n += 1
        raw.update(d["tokens"])
        lem.update(d["lemmas"])
        big.update(d["bigrams"])
        s = d.get("sentiment")
        if s in CLASSES:
            lem_c[s].update(d["lemmas"])
            big_c[s].update(d["bigrams"])
            kw_c[s].update(d.get("keywords", []))
        kw.update(d.get("keywords", []))
        item = (" ".join(d["lemmas"]), d["rating"], s)
        if len(pool) < sample:
            pool.append(item)
        elif (j := rng.randint(0, n - 1)) < sample:
            pool[j] = item
        if n % 25_000 == 0:
            log(f"  ...{n:,} reviews")
    if n < 500:
        raise SystemExit(f"Only {n} NLP-processed reviews found - run scripts.seed_database first.")
    pool = [p for p in pool if p[0].strip()]
    log(f"counters done ({n:,} reviews); fitting topics and word vectors on {len(pool):,} reviews...")
    docs, ratings, sents = zip(*pool)
    model = C.lsa_word_vectors(docs)
    registry.save("lsa_words", model)
    topn = lambda c, k=25: [{"term": t, "count": v} for t, v in c.most_common(k)]
    data = {
        **C.vocab_stats(raw, lem, n), "zipf": C.zipf_points(raw),
        "distinctive_unigrams": C.distinctive_by_class(lem_c), "distinctive_bigrams": C.distinctive_by_class(big_c, min_count=15),
        "collocations": C.pmi_collocations(big, lem), "top_keywords": topn(kw),
        "top_keywords_by_class": {c: topn(kw_c[c], 15) for c in CLASSES},
        "topics": C.topic_model(docs, ratings, sents), "topic_sample_size": len(pool),
        "lsa": {"dim": model["dim"], "vocab": len(model["vocab"]), "explained_variance": model["explained_variance"]},
    }
    db.analytics.delete_many({"key": "nlp_corpus"})
    db.analytics.insert_one({"key": "nlp_corpus", "scope": "global", "job": "compute_nlp_stats",
                             "computed_at": dt.datetime.now(dt.timezone.utc), "data": data})
    log(f"done: vocab {data['vocab_raw']:,} -> {data['vocab_lemma']:,} ({data['vocab_reduction_pct']}% smaller), "
        f"Zipf slope {data['zipf']['slope']}, {len(data['topics'])} topics")
    return data


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--sample", type=int, default=30_000)
    compute(None, ap.parse_args().sample)
