"""Real timings: plain Python loop vs the MapReduce simulation vs MongoDB's aggregation framework."""
import time

from bda.jobs import JOBS
from bda.mapreduce import run_job

MONGO = {
    "rating_distribution": [{"$group": {"_id": "$rating", "c": {"$sum": 1}}}],
    "word_count": [{"$unwind": "$lemmas"}, {"$group": {"_id": "$lemmas", "c": {"$sum": 1}}}],
}


def _best(fn, repeats):
    best, out = float("inf"), None
    for _ in range(repeats):
        t = time.perf_counter()
        out = fn()
        best = min(best, time.perf_counter() - t)
    return best, out


def run_benchmark(db, sizes, jobs=("rating_distribution", "word_count"), repeats=2, log=print):
    total = db.reviews.count_documents({})
    sizes = sorted({min(s, total) for s in sizes if total})
    rows = []
    for n in sizes:
        for name in jobs:
            job = JOBS[name]
            t = time.perf_counter()
            recs = list(db.reviews.find({}, job.fields).limit(n))
            fetch = time.perf_counter() - t
            t_naive, naive = _best(lambda: job.naive(recs), repeats)
            t_mr, (mr, _trace) = _best(lambda: run_job(recs, job.mapper, job.reducer, job.combiner, job.describe), repeats)
            pipe = [{"$limit": n}] + MONGO[name]
            t_mongo, mg = _best(lambda: {d["_id"]: d["c"] for d in db.reviews.aggregate(pipe)}, repeats)
            row = {"n": len(recs), "job": name, "fetch_seconds": round(fetch, 3), "naive_seconds": round(t_naive, 3),
                   "mapreduce_seconds": round(t_mr, 3), "mongo_seconds": round(t_mongo, 3),
                   "results_match": naive == mr == mg}
            rows.append(row)
            log(f"  n={row['n']:>7,} {name:20s} naive {row['naive_seconds']}s  mapreduce {row['mapreduce_seconds']}s  mongo {row['mongo_seconds']}s  match={row['results_match']}")
    return {"rows": rows, "repeats": repeats, "note": "Best of %d runs. Naive and MapReduce times exclude the fetch from MongoDB (reported separately); the MongoDB time includes its own scan." % repeats}
