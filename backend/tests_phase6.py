import datetime as dt
import json
import random
from collections import Counter

import mongomock
import pytest
from fastapi.testclient import TestClient

from backend.main import app
from bda.benchmark import run_benchmark
from bda.jobs import JOBS
from bda.mapreduce import partition, run_job
from bda.sketches import BloomFilter, FlajoletMartin
from bda.streaming import Reservoir, SlidingWindow, StreamSimulator


def make_reviews(n=600, seed=3):
    rng = random.Random(seed)
    words = ["tone", "great", "strap", "break", "string", "tune", "price", "easy", "cheap", "sound"]
    out = []
    for i in range(n):
        r = rng.choice([1, 2, 3, 4, 5, 5, 5])
        s = "positive" if r >= 4 else "neutral" if r == 3 else "negative"
        out.append({"review_id": f"r{i}", "product_id": f"P{rng.randint(1, 25)}", "user_id": f"U{rng.randint(1, 400)}", "rating": r, "sentiment": s,
                    "lemmas": [rng.choice(words) for _ in range(rng.randint(2, 9))],
                    "aspect_sentiments": {a: rng.choice(["positive", "negative", "neutral"]) for a in rng.sample(["sound", "price_value", "durability"], rng.randint(0, 2))},
                    "review_date": dt.datetime(2015 + rng.randint(0, 6), rng.randint(1, 12), rng.randint(1, 28)),
                    "title": f"t{i}", "review_text": "some review text " * 5, "helpful_votes": rng.randint(0, 20), "verified_purchase": rng.random() < 0.9})
    return out


# ---------- MapReduce ----------
@pytest.mark.parametrize("name", list(JOBS))
@pytest.mark.parametrize("mappers,reducers", [(1, 1), (4, 3), (7, 5)])
def test_mapreduce_equals_naive_loop_for_every_job_and_config(name, mappers, reducers):
    recs = make_reviews()
    j = JOBS[name]
    result, _ = run_job(recs, j.mapper, j.reducer, j.combiner, j.describe, mappers, reducers)
    assert result == j.naive(recs)


def test_partitioner_is_stable_and_in_range():
    assert partition("tone", 3) == partition("tone", 3) and all(0 <= partition(k, 4) < 4 for k in ("a", 1, "sound|positive"))
    import zlib
    assert partition("tone", 3) == zlib.crc32(b"tone") % 3      # crc32, not Python's per-process hash()


def test_trace_accounting_and_combiner_effect():
    recs = make_reviews()
    j = JOBS["word_count"]
    _, t = run_job(recs, j.mapper, j.reducer, j.combiner, j.describe, 4, 3)
    assert t["map"]["pairs_emitted"] == sum(len(r["lemmas"]) for r in recs)
    assert t["combine"]["pairs_after"] < t["map"]["pairs_emitted"] and t["combine"]["reduction_pct"] > 50
    assert sum(p["pairs"] for p in t["shuffle"]["partitions"]) == t["shuffle"]["pairs_in"] == t["combine"]["pairs_after"]
    assert t["shuffle"]["keys"] == t["reduce"]["keys_out"] == len(set(w for r in recs for w in r["lemmas"]))
    _, t2 = run_job(recs, j.mapper, j.reducer, None, j.describe)            # same job without a combiner
    assert t2["combine"] is None and t2["shuffle"]["pairs_in"] == t2["map"]["pairs_emitted"] == t["map"]["pairs_emitted"]


def test_average_job_needs_pairs_not_means():
    recs = [{"product_id": "A", "rating": 5}, {"product_id": "A", "rating": 1}, {"product_id": "A", "rating": 3}, {"product_id": "B", "rating": 4}]
    j = JOBS["product_avg_rating"]
    for mappers in (1, 2, 3):
        res, _ = run_job(recs, j.mapper, j.reducer, j.combiner, j.describe, mappers, 2)
        assert res == {"A": (3.0, 3), "B": (4.0, 1)}


# ---------- sketches ----------
def test_bloom_has_no_false_negatives_and_sane_fp_rate():
    ids = [f"user{i}" for i in range(6000)]
    bf = BloomFilter(5000, 0.01)
    for u in ids[:5000]:
        bf.add(u)
    assert all(u in bf for u in ids[:5000])
    fp = sum(u in bf for u in ids[5000:]) / 1000
    assert fp < 0.03 and abs(bf.theoretical_fp - 0.01) < 0.003 and 0.3 < bf.fill_ratio < 0.7
    assert len(bf.bits) < 5000 * 20 / 8        # fewer than ~20 bits per item


def test_flajolet_martin_within_30_percent_and_ignores_duplicates():
    ids = [f"u{i}" for i in range(20000)]
    fm = FlajoletMartin()
    fm.add_many(ids * 3)
    assert abs(fm.estimate() - 20000) / 20000 < 0.30


# ---------- streaming ----------
def test_reservoir_is_uniform():
    hits = Counter()
    for seed in range(400):
        r = Reservoir(5, seed)
        for i in range(50):
            r.offer(i)
        hits.update(r.items)
    assert len(r.items) == 5 and r.n == 50
    assert all(0.05 < hits[i] / 400 < 0.18 for i in range(50))      # expected 5/50 = 0.10 each


def test_sliding_window_evicts_old_events():
    w = SlidingWindow(10)
    e = lambda rating, s: {"rating": rating, "sentiment": s, "aspects": {"sound": "negative"} if s == "negative" else {}}
    w.add(1, e(1, "negative")); w.add(5, e(5, "positive")); w.add(9, e(5, "positive"))
    w.evict(10.5)                                    # drops ts=1 (<= 0.5)? keeps 5 and 9
    assert w.n == 3
    w.evict(11.5)
    assert w.n == 2 and w.stats()["negative_share"] == 0 and w.stats()["aspects"] == []
    w.evict(30)
    assert w.n == 0 and w.stats()["avg_rating"] is None


def pool():
    return [{"rating": 5 if i % 5 else 1, "sentiment": "positive" if i % 5 else "negative", "aspects": {"sound": "positive"}, "title": "t", "text": "x" * 300} for i in range(200)]


def test_stream_is_deterministic_and_window_bounded():
    a, b = StreamSimulator(pool(), 20, 10, seed=1), StreamSimulator(pool(), 20, 10, seed=1)
    for _ in range(40):
        sa, sb = a.tick(), b.tick()
    assert sa == sb and sa["window"]["events"] < sa["events_total"] and 100 < sa["window"]["events"] < 320
    assert len(sa["reservoir"]) == 8 and sa["reservoir_seen"] == sa["events_total"] and len(sa["reservoir"][0]["text"]) == 140


def test_burst_raises_negative_share_and_triggers_alert():
    sim = StreamSimulator(pool(), 20, 10, seed=2, burst_at=20, burst_len=10)
    calm = [sim.tick() for _ in range(19)]
    assert all(s["alert"] is None for s in calm)
    spike = [sim.tick() for _ in range(12)]
    assert any(s["alert"] and s["burst_active"] for s in spike)
    assert max(s["window"]["negative_share"] for s in spike) > 0.4 > calm[-1]["window"]["negative_share"]


# ---------- API ----------
@pytest.fixture
def db(monkeypatch):
    database = mongomock.MongoClient().p6
    database.reviews.insert_many(make_reviews())
    import backend.routes.bda as r
    monkeypatch.setattr(r, "require_db", lambda: database)
    return database


def test_api_jobs_and_mapreduce(db):
    c = TestClient(app)
    assert {j["id"] for j in c.get("/api/bda/jobs").json()["jobs"]} == set(JOBS)
    j = c.post("/api/bda/mapreduce/word_count?n=500&mappers=3&reducers=2").json()
    assert j["verified_against_naive"] is True and j["n_records"] == 500 and j["trace"]["config"]["reducers"] == 2 and "Educational" in j["label"]
    assert j["top"][0]["value"] >= j["top"][1]["value"]
    assert c.post("/api/bda/mapreduce/evil").status_code == 404
    assert c.post("/api/bda/mapreduce/word_count?n=5").status_code == 422
    top = c.post("/api/bda/mapreduce/product_avg_rating?n=600").json()
    assert top["verified_against_naive"] and set(top["top"][0]["value"]) == {"avg", "reviews"}


def test_api_bloom_and_distinct(db):
    c = TestClient(app)
    b = c.get("/api/bda/bloom?n=400&error_rate=0.01").json()
    assert b["false_negatives"] == 0 and b["inserted"] + b["probed_unseen"] <= 400 and b["bytes"] < b["approx_python_set_bytes"]
    d = c.get("/api/bda/distinct?field=product_id").json()
    assert d["exact_distinct"] == len({r["product_id"] for r in make_reviews()}) and abs(d["error_pct"]) < 60
    assert c.get("/api/bda/distinct?field=title").status_code == 422


def test_api_queries(db):
    c = TestClient(app)
    ids = [q["id"] for q in c.get("/api/bda/queries").json()["queries"]]
    assert len(ids) == 5
    for qid in ids:
        j = c.get(f"/api/bda/query/{qid}").json()
        assert j["rows"] and j["pipeline"] and j["seconds"] >= 0, qid
    assert c.get("/api/bda/query/drop_database").status_code == 404
    tp = c.get("/api/bda/query/top_products").json()["rows"]
    assert tp[0]["reviews"] >= tp[1]["reviews"]


def test_benchmark_results_match_and_endpoint(db):
    out = run_benchmark(db, [200, 600], repeats=1, log=lambda *_: None)
    assert len(out["rows"]) == 4 and all(r["results_match"] for r in out["rows"])
    c = TestClient(app)
    assert c.get("/api/bda/benchmark").json()["error"] == "not_computed"
    db.analytics.insert_one({"key": "bda_benchmark", "scope": "global", "computed_at": dt.datetime.now(dt.timezone.utc), "data": out})
    assert len(c.get("/api/bda/benchmark").json()["rows"]) == 4


def test_api_stream_sse(db):
    c = TestClient(app)
    with c.stream("GET", "/api/bda/stream?rate=30&window=10&seconds=3&interval=0.05&burst_at=2") as r:
        assert r.headers["content-type"].startswith("text/event-stream")
        events = [json.loads(line[6:]) for line in r.iter_lines() if line.startswith("data: ")]
    assert [e["t"] for e in events] == [1.0, 2.0, 3.0] and events[-1]["events_total"] > 30 and "window" in events[0]
