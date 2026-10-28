"""Job definitions for the MapReduce simulator, each with a plain-loop equivalent used to verify the result."""
from collections import Counter, defaultdict
from dataclasses import dataclass
from typing import Callable


def _sum(_k, vs):
    return sum(vs)


def _sum_pairs(_k, vs):
    return (sum(v[0] for v in vs), sum(v[1] for v in vs))


def _avg(_k, vs):
    total, n = _sum_pairs(_k, vs)
    return (round(total / n, 4), n)


@dataclass
class Job:
    title: str
    description: str
    fields: dict
    mapper: Callable
    reducer: Callable
    combiner: Callable | None
    describe: Callable
    rank: Callable          # value -> sortable (largest first)
    show: Callable          # value -> JSON-friendly
    naive: Callable         # records -> {key: value}, plain loops


def _naive_count(extract):
    def f(records):
        c = Counter()
        for r in records:
            for k in extract(r):
                c[k] += 1
        return dict(c)
    return f


def _naive_avg(records):
    acc = defaultdict(lambda: [0, 0])
    for r in records:
        a = acc[r["product_id"]]
        a[0] += r["rating"]; a[1] += 1
    return {k: (round(t / n, 4), n) for k, (t, n) in acc.items()}


_aspect_keys = lambda r: [f"{a}|{l}" for a, l in (r.get("aspect_sentiments") or {}).items()]

JOBS = {
    "rating_distribution": Job(
        "Rating distribution", "How many reviews per star rating. map: (rating, 1)  reduce: sum.",
        {"rating": 1}, lambda r: [(r["rating"], 1)], _sum, _sum, lambda r: f"rating = {r['rating']}",
        lambda v: v, lambda v: v, _naive_count(lambda r: [r["rating"]])),
    "word_count": Job(
        "Word count (lemmas)", "The classic: how often each lemma appears. map: (lemma, 1)  combine + reduce: sum.",
        {"lemmas": 1}, lambda r: [(w, 1) for w in r["lemmas"]], _sum, _sum, lambda r: " ".join(r["lemmas"][:8]) + " ...",
        lambda v: v, lambda v: v, _naive_count(lambda r: r["lemmas"])),
    "aspect_sentiment": Job(
        "Aspect sentiment counts", "Mentions per (aspect, sentiment). map: ('sound|positive', 1)  reduce: sum.",
        {"aspect_sentiments": 1}, lambda r: [(k, 1) for k in _aspect_keys(r)], _sum, _sum,
        lambda r: str(r.get("aspect_sentiments") or {}), lambda v: v, lambda v: v, _naive_count(_aspect_keys)),
    "reviews_per_year": Job(
        "Reviews per year", "Review volume by calendar year. map: (year, 1)  reduce: sum.",
        {"review_date": 1}, lambda r: [(r["review_date"].year, 1)], _sum, _sum, lambda r: f"date = {r['review_date'].date()}",
        lambda v: v, lambda v: v, _naive_count(lambda r: [r["review_date"].year])),
    "product_avg_rating": Job(
        "Average rating per product", "Mean needs (sum, count) pairs because an average is not associative. map: (product, (rating, 1))  combine: add pairs  reduce: sum / count.",
        {"product_id": 1, "rating": 1}, lambda r: [(r["product_id"], (r["rating"], 1))], _avg, _sum_pairs,
        lambda r: f"{r['product_id']} rated {r['rating']}", lambda v: v[1], lambda v: {"avg": v[0], "reviews": v[1]}, _naive_avg),
}
