import datetime as dt
import pytest
import mongomock
from fastapi.testclient import TestClient

from analytics.health import (aspect_summary, choose_granularity, health_score, period_key, product_stats,
                              trend_analysis, two_prop_z)
from backend.main import app
from scripts.compute_analytics import compute

D = dt.datetime


def rv(date, rating, sent=None, asp=None):
    sent = sent or ("positive" if rating >= 4 else "neutral" if rating == 3 else "negative")
    return {"review_date": date, "rating": rating, "sentiment": sent, "aspect_sentiments": asp or {}}


def test_period_keys_and_granularity():
    assert period_key(D(2021, 5, 3), "month") == "2021-05" and period_key(D(2021, 5, 3), "quarter") == "2021-Q2"
    assert choose_granularity(D(2021, 1, 1), D(2022, 6, 1)) == "month"
    assert choose_granularity(D(2015, 1, 1), D(2022, 6, 1)) == "quarter"


def test_aspect_summary_counts():
    s = aspect_summary([rv(D(2020, 1, 1), 5, asp={"sound": "positive"}), rv(D(2020, 1, 2), 1, asp={"sound": "negative", "tuning": "negative"}),
                        rv(D(2020, 1, 3), 3, asp={"sound": "neutral"})])
    assert s["sound"] == {"mentions": 3, "positive": 1, "neutral": 1, "negative": 1, "positive_ratio": 0.3333}
    assert s["tuning"]["positive_ratio"] == 0


def test_health_formula_exact_value():
    aspects = {"sound": {"mentions": 10, "positive_ratio": 0.8}, "price_value": {"mentions": 5, "positive_ratio": 0.4},
               "tuning": {"mentions": 2, "positive_ratio": 0.0}}          # tuning ignored: only 2 mentions
    h = health_score(4.0, 0.7, aspects, {"status": "stable", "drop": 0.0})
    # A = mean(0.8, 0.4) = 0.6; R = 0.75 -> 100 * (0.4*0.6 + 0.3*0.7 + 0.3*0.75) = 67.5
    assert h["score"] == 67.5 and h["components"]["aspects_used"] == 2 and h["penalty"] == 0


def test_health_without_aspects_renormalises_and_penalty_is_capped():
    h = health_score(5.0, 1.0, {}, {"status": "stable", "drop": 0})
    assert h["score"] == 100.0 and h["components"]["aspect_mean_positive_ratio"] is None
    h2 = health_score(5.0, 1.0, {}, {"status": "emerging_negative", "drop": 0.9})
    assert h2["penalty"] == 10.0 and h2["score"] == 90.0
    assert health_score(1.0, 0.0, {}, {"status": "emerging_negative", "drop": 0.9})["score"] == 0.0     # clamped


def _two_windows(prior_pos, recent_pos, n=40):
    last = D(2022, 12, 31)
    out = []
    for i in range(n):
        out.append(rv(last - dt.timedelta(days=400 + i), 5 if i < prior_pos else 1))
        out.append(rv(last - dt.timedelta(days=10 + i), 5 if i < recent_pos else 1))
    return out, last


def test_trend_statuses():
    revs, last = _two_windows(36, 20)                    # 90% -> 50%: big, significant drop
    t = trend_analysis(revs, last)
    assert t["status"] == "emerging_negative" and t["drop"] == 0.4 and t["z"] > 1.645
    revs, last = _two_windows(20, 36)
    assert trend_analysis(revs, last)["status"] == "improving"
    revs, last = _two_windows(30, 29)
    assert trend_analysis(revs, last)["status"] == "stable"


def test_small_windows_never_trigger_a_trend():
    revs, last = _two_windows(10, 0, n=10)               # looks dramatic but only 10 per window
    assert trend_analysis(revs, last)["status"] == "insufficient_data"


def test_z_is_zero_when_no_variance():
    assert two_prop_z(1.0, 20, 1.0, 20) == 0.0


def test_product_stats_shape_and_penalty_applied():
    revs, last = _two_windows(36, 20)
    for r in revs:
        r["aspect_sentiments"] = {"sound": r["sentiment"]}
    s = product_stats(revs, "P1", "Test Guitar")
    assert s["n_reviews"] == 80 and s["name"] == "Test Guitar" and s["weakest_aspect"]["aspect"] == "sound"
    assert s["health"]["penalty"] == 10.0 and s["trend"]["granularity"] == "month" and s["trend"]["series"]
    assert sum(s["rating_histogram"].values()) == 80


# ---- API over mongomock -----------------------------------------------------
@pytest.fixture
def db(monkeypatch):
    database = mongomock.MongoClient().p4
    revs, last = _two_windows(36, 20)
    docs = []
    for i, r in enumerate(revs):
        docs.append({**r, "product_id": "GUITAR1", "review_id": f"a{i}", "aspect_sentiments": {"sound": r["sentiment"]},
                     "review_text": "x" * 500, "title": "t", "helpful_votes": i})
    for i in range(6):
        docs.append({"product_id": "TINY", "review_id": f"b{i}", "review_date": D(2020, 1, 1 + i), "rating": 5,
                     "sentiment": "positive", "aspect_sentiments": {}, "review_text": "ok", "title": "", "helpful_votes": 0})
    docs.append({"product_id": "ONE", "review_id": "c0", "review_date": D(2020, 1, 1), "rating": 5, "sentiment": "positive",
                 "aspect_sentiments": {}, "review_text": "ok", "title": "", "helpful_votes": 0})
    database.reviews.insert_many(docs)
    database.products.insert_one({"product_id": "GUITAR1", "name": "Acme Dreadnought Guitar"})
    import backend.routes.products as pr
    monkeypatch.setattr(pr, "require_db", lambda: database)
    return database


def test_compute_stores_only_products_with_enough_reviews(db):
    s = compute(db, log=lambda *_: None)
    assert s["products_stored"] == 2 and s["reviews_scanned"] == 87
    assert db.analytics.count_documents({"key": "product_health"}) == 2
    assert db.analytics.find_one({"key": "global_summary"})["data"]["aspects"][0]["aspect"] == "sound"
    compute(db, log=lambda *_: None)                                            # idempotent
    assert db.analytics.count_documents({"key": "product_health"}) == 2


def test_api_404s_before_compute(db):
    c = TestClient(app)
    for url in ("/api/products", "/api/products/GUITAR1", "/api/analytics/summary"):
        r = c.get(url)
        assert r.status_code == 404 and r.json()["error"] == "not_computed"


def test_api_list_filter_sort_search(db):
    compute(db, log=lambda *_: None)
    c = TestClient(app)
    j = c.get("/api/products?min_reviews=5").json()
    assert j["total"] == 2 and j["items"][0]["product_id"] == "TINY"            # TINY: all 5-star -> higher health
    assert c.get("/api/products").json()["total"] == 1                          # default min 20 hides TINY
    g = c.get("/api/products?q=dreadnought").json()
    assert g["total"] == 1 and g["items"][0]["name"] == "Acme Dreadnought Guitar" and g["items"][0]["trend_status"] == "emerging_negative"
    assert c.get("/api/products?q=.*").json()["total"] == 0                      # regex chars are escaped
    assert c.get("/api/products?sort=evil").status_code == 422
    assert c.get("/api/products?limit=1&offset=1&min_reviews=5").json()["items"][0]["product_id"] == "GUITAR1"


def test_api_detail_and_evidence(db):
    compute(db, log=lambda *_: None)
    c = TestClient(app)
    d = c.get("/api/products/GUITAR1").json()
    assert d["health"]["penalty"] == 10.0 and "note" in d and isinstance(d["last_review"], str)
    assert c.get("/api/products/NOPE").json()["error"] == "product_not_found"
    ev = c.get("/api/products/GUITAR1/evidence?aspect=sound&sentiment=negative&limit=3").json()
    assert len(ev["reviews"]) == 3 and ev["reviews"][0]["helpful_votes"] >= ev["reviews"][1]["helpful_votes"]
    assert ev["reviews"][0]["text"].endswith("…")
    assert c.get("/api/products/GUITAR1/evidence?aspect=$where").status_code == 422
    assert c.get("/api/products/GUITAR1/evidence?aspect=sound&sentiment=x").status_code == 422


def test_summary_endpoint(db):
    compute(db, log=lambda *_: None)
    j = TestClient(app).get("/api/analytics/summary").json()
    assert j["total_reviews"] == 87 and j["aspects"] and j["trend"] and "computed_at" in j
