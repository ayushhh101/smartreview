import asyncio
import json
import time

from fastapi import APIRouter, Query, Request
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import JSONResponse, StreamingResponse

from backend.database.mongo import require_db
from bda.jobs import JOBS
from bda.mapreduce import LABEL, run_job
from bda.sketches import BloomFilter, FlajoletMartin
from bda.streaming import StreamSimulator

router = APIRouter(prefix="/bda")
NO_REVIEWS = {"error": "no_reviews", "message": "No reviews in MongoDB yet.", "hint": "Run: python -m scripts.seed_database data/reviews_100000.jsonl"}
BENCH_MISSING = {"error": "not_computed", "message": "Benchmark has not been run yet.", "hint": "Run: python -m scripts.run_benchmark"}

# Fixed, server-side aggregation pipelines (no user input reaches MongoDB).
QUERIES = {
    "top_products": ("Top products by review volume", "Group by product, count, average the rating, sort, limit.",
                     [{"$group": {"_id": "$product_id", "reviews": {"$sum": 1}, "avg_rating": {"$avg": "$rating"}}}, {"$sort": {"reviews": -1}}, {"$limit": 10}]),
    "reviews_per_year": ("Reviews per year", "$year operator on the review date.",
                         [{"$group": {"_id": {"$year": "$review_date"}, "reviews": {"$sum": 1}}}, {"$sort": {"_id": 1}}]),
    "verified_vs_not": ("Verified vs unverified purchases", "Average rating and sentiment-positive share by purchase type.",
                        [{"$group": {"_id": "$verified_purchase", "reviews": {"$sum": 1}, "avg_rating": {"$avg": "$rating"}}}, {"$sort": {"reviews": -1}}]),
    "helpful_leaders": ("Most helpful reviews", "Filter on helpful_votes, sort descending, project a few fields.",
                        [{"$match": {"helpful_votes": {"$gte": 10}}}, {"$sort": {"helpful_votes": -1}}, {"$limit": 5},
                         {"$project": {"_id": 0, "product_id": 1, "rating": 1, "title": 1, "helpful_votes": 1}}]),
    "sentiment_by_rating": ("Rating x sentiment cross-tab", "Two-key $group: how star ratings map to the derived sentiment label.",
                            [{"$group": {"_id": {"rating": "$rating", "sentiment": "$sentiment"}, "reviews": {"$sum": 1}}}, {"$sort": {"_id.rating": 1}}]),
}


def _records(db, job, n):
    return list(db.reviews.find({}, {**job.fields, "_id": 0}).limit(n))


@router.get("/jobs")
def jobs():
    return {"label": LABEL, "jobs": [{"id": k, "title": j.title, "description": j.description} for k, j in JOBS.items()]}


@router.post("/mapreduce/{job_id}")
def mapreduce(job_id: str, n: int = Query(10_000, ge=100, le=100_000), mappers: int = Query(4, ge=1, le=8), reducers: int = Query(3, ge=1, le=6)):
    job = JOBS.get(job_id)
    if job is None:
        return JSONResponse(status_code=404, content={"error": "unknown_job", "message": f"job must be one of {sorted(JOBS)}"})
    recs = _records(require_db(), job, n)
    if not recs:
        return JSONResponse(status_code=404, content=NO_REVIEWS)
    t0 = time.perf_counter()
    result, trace = run_job(recs, job.mapper, job.reducer, job.combiner, job.describe, mappers, reducers)
    mr_seconds = time.perf_counter() - t0
    t0 = time.perf_counter()
    naive = job.naive(recs)
    naive_seconds = time.perf_counter() - t0
    top = sorted(result.items(), key=lambda kv: job.rank(kv[1]), reverse=True)[:15]
    return {"job": job_id, "title": job.title, "description": job.description, "label": LABEL, "n_records": len(recs),
            "trace": trace, "n_keys": len(result), "top": [{"key": str(k), "value": job.show(v)} for k, v in top],
            "verified_against_naive": naive == result, "mapreduce_seconds": round(mr_seconds, 3), "naive_seconds": round(naive_seconds, 3)}


def _ids(db, field, limit):
    seen, out = set(), []
    for d in db.reviews.find({}, {field: 1, "_id": 0}):
        v = d.get(field)
        if v and v not in seen:
            seen.add(v); out.append(v)
            if len(out) >= limit:
                break
    return out


@router.get("/bloom")
def bloom(n: int = Query(50_000, ge=100, le=200_000), error_rate: float = Query(0.01, ge=0.0001, le=0.2)):
    """Bloom filter over reviewer ids: insert 80% of distinct users, then probe with the inserted ones and the unseen 20%."""
    ids = _ids(require_db(), "user_id", n)
    if len(ids) < 50:
        return JSONResponse(status_code=404, content=NO_REVIEWS)
    cut = int(len(ids) * 0.8)
    known, unseen = ids[:cut], ids[cut:]
    bf = BloomFilter(len(known), error_rate)
    for u in known:
        bf.add(u)
    false_neg = sum(u not in bf for u in known)
    false_pos = sum(u in bf for u in unseen)
    set_bytes = sum(len(u) + 49 for u in known) + 8 * len(known) * 4          # rough CPython str + hash-table cost
    return {"label": "Educational Bloom filter demo", "inserted": len(known), "probed_unseen": len(unseen), "target_error_rate": error_rate,
            "bits": bf.m, "bytes": len(bf.bits), "hash_functions": bf.k, "fill_ratio": round(bf.fill_ratio, 4),
            "false_negatives": false_neg, "false_positives": false_pos,
            "measured_fp_rate": round(false_pos / len(unseen), 5), "theoretical_fp_rate": round(bf.theoretical_fp, 5),
            "approx_python_set_bytes": set_bytes}


@router.get("/distinct")
def distinct(field: str = Query("user_id", pattern="^(user_id|product_id)$")):
    db = require_db()
    values = [d[field] for d in db.reviews.find({}, {field: 1, "_id": 0}) if d.get(field)]
    if not values:
        return JSONResponse(status_code=404, content=NO_REVIEWS)
    fm = FlajoletMartin()
    fm.add_many(values)
    exact, est = len(set(values)), fm.estimate()
    return {"label": "Educational Flajolet-Martin demo", "field": field, "stream_length": len(values), "exact_distinct": exact,
            "estimated_distinct": est, "error_pct": round(100 * (est - exact) / exact, 1), "hash_functions": 64,
            "sketch_bytes": int(fm.seen.size)}


@router.get("/benchmark")
def benchmark():
    doc = require_db().analytics.find_one({"key": "bda_benchmark"})
    if doc is None:
        return JSONResponse(status_code=404, content=BENCH_MISSING)
    ts = doc["computed_at"]
    return {**doc["data"], "computed_at": ts.isoformat() if hasattr(ts, "isoformat") else ts}


@router.get("/queries")
def queries():
    return {"queries": [{"id": k, "title": t, "description": d} for k, (t, d, _) in QUERIES.items()]}


@router.get("/query/{qid}")
def run_query(qid: str):
    q = QUERIES.get(qid)
    if q is None:
        return JSONResponse(status_code=404, content={"error": "unknown_query", "message": f"query must be one of {sorted(QUERIES)}"})
    title, desc, pipe = q
    db = require_db()
    t0 = time.perf_counter()
    rows = list(db.reviews.aggregate(pipe))
    secs = time.perf_counter() - t0
    plan = None
    try:                                                      # which access path did MongoDB choose?
        txt = json.dumps(db.command({"explain": {"aggregate": "reviews", "pipeline": pipe, "cursor": {}}, "verbosity": "queryPlanner"}), default=str)
        plan = "IXSCAN (index used)" if "IXSCAN" in txt else "COLLSCAN (full collection scan)" if "COLLSCAN" in txt else None
    except Exception:
        plan = None
    return {"id": qid, "title": title, "description": desc, "pipeline": pipe, "seconds": round(secs, 4), "plan": plan,
            "rows": json.loads(json.dumps(rows, default=str))}


def _load_pool(size=5000):
    db = require_db()
    proj = {"_id": 0, "rating": 1, "sentiment": 1, "aspect_sentiments": 1, "title": 1, "review_text": 1}
    try:
        docs = list(db.reviews.aggregate([{"$sample": {"size": size}}, {"$project": proj}]))
    except Exception:
        docs = list(db.reviews.find({}, proj).limit(size))
    return [{"rating": d["rating"], "sentiment": d["sentiment"], "aspects": d.get("aspect_sentiments") or {},
             "title": d.get("title", ""), "text": d.get("review_text", "")} for d in docs if "sentiment" in d]


@router.get("/stream")
async def stream(request: Request, rate: int = Query(20, ge=1, le=200), window: int = Query(30, ge=5, le=300),
                 burst_at: int | None = Query(None, ge=1, le=3600), burst_len: int = Query(10, ge=1, le=60),
                 seconds: int = Query(300, ge=1, le=3600), interval: float = Query(1.0, ge=0.05, le=5.0)):
    """Server-Sent Events: one JSON snapshot per `interval` real seconds; each advances the simulated clock by 1 s."""
    pool = await run_in_threadpool(_load_pool)
    if not pool:
        return JSONResponse(status_code=404, content=NO_REVIEWS)
    sim = StreamSimulator(pool, rate, window, burst_at=burst_at, burst_len=burst_len)

    async def gen():
        for _ in range(seconds):
            if await request.is_disconnected():
                break
            yield f"data: {json.dumps(sim.tick(1.0))}\n\n"
            await asyncio.sleep(interval)

    return StreamingResponse(gen(), media_type="text/event-stream", headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})
