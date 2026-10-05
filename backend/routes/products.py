import re

from fastapi import APIRouter, Query
from fastapi.responses import JSONResponse

from backend.database.mongo import require_db
from nlp.lexicons import ASPECTS

router = APIRouter()
NOT_COMPUTED = {"error": "not_computed", "message": "Product analytics have not been computed yet.",
                "hint": "Run: python -m scripts.compute_analytics"}
SORTS = {"health_desc": ("data.health.score", -1), "health_asc": ("data.health.score", 1),
         "reviews_desc": ("data.n_reviews", -1), "rating_desc": ("data.avg_rating", -1),
         "rating_asc": ("data.avg_rating", 1)}
NOTE = ("Scores come from the loaded review sample, not all of Amazon. Health is a heuristic composite "
        "(see formula), and sentiment labels are derived from star ratings.")


def _summary(doc):
    d = doc["data"]
    return {"product_id": doc["scope"], "name": d.get("name"), "n_reviews": d["n_reviews"],
            "avg_rating": d["avg_rating"], "positive_ratio": d["positive_ratio"],
            "health_score": d["health"]["score"], "trend_status": d["trend"]["status"],
            "weakest_aspect": d.get("weakest_aspect"), "last_review": d["last_review"].isoformat()}


@router.get("/products")
def list_products(q: str = Query("", max_length=100), sort: str = "health_desc",
                  min_reviews: int = Query(20, ge=5, le=100000), limit: int = Query(25, ge=1, le=100),
                  offset: int = Query(0, ge=0)):
    db = require_db()
    if db.analytics.count_documents({"key": "product_health"}) == 0:
        return JSONResponse(status_code=404, content=NOT_COMPUTED)
    if sort not in SORTS:
        return JSONResponse(status_code=422, content={"error": "bad_sort", "message": f"sort must be one of {sorted(SORTS)}"})
    flt = {"key": "product_health", "data.n_reviews": {"$gte": min_reviews}}
    if q.strip():
        pat = {"$regex": re.escape(q.strip()), "$options": "i"}
        flt["$or"] = [{"data.name": pat}, {"scope": pat}]
    field, direction = SORTS[sort]
    total = db.analytics.count_documents(flt)
    rows = db.analytics.find(flt).sort([(field, direction), ("scope", 1)]).skip(offset).limit(limit)
    return {"total": total, "limit": limit, "offset": offset, "min_reviews": min_reviews, "note": NOTE,
            "items": [_summary(d) for d in rows]}


@router.get("/products/{product_id}")
def product_detail(product_id: str):
    db = require_db()
    doc = db.analytics.find_one({"key": "product_health", "scope": product_id})
    if doc is None:
        if db.analytics.count_documents({"key": "product_health"}) == 0:
            return JSONResponse(status_code=404, content=NOT_COMPUTED)
        return JSONResponse(status_code=404, content={"error": "product_not_found",
                            "message": "No analytics for this product (it may have too few reviews)."})
    d = doc["data"]
    for k in ("first_review", "last_review"):
        d[k] = d[k].isoformat()
    return {**d, "note": NOTE}


@router.get("/products/{product_id}/evidence")
def evidence(product_id: str, aspect: str, sentiment: str = "negative", limit: int = Query(5, ge=1, le=20)):
    """Real reviews behind an aspect score, most helpful first."""
    if aspect not in ASPECTS:
        return JSONResponse(status_code=422, content={"error": "bad_aspect", "message": f"aspect must be one of {sorted(ASPECTS)}"})
    if sentiment not in ("positive", "neutral", "negative"):
        return JSONResponse(status_code=422, content={"error": "bad_sentiment", "message": "sentiment must be positive, neutral or negative"})
    rows = require_db().reviews.find({"product_id": product_id, f"aspect_sentiments.{aspect}": sentiment},
                                    {"_id": 0, "rating": 1, "title": 1, "review_text": 1, "helpful_votes": 1, "review_date": 1}
                                    ).sort([("helpful_votes", -1), ("review_date", -1)]).limit(limit)
    out = [{"rating": r["rating"], "title": r.get("title", ""), "helpful_votes": r.get("helpful_votes", 0),
            "review_date": r["review_date"].isoformat(),
            "text": r["review_text"][:400] + ("…" if len(r["review_text"]) > 400 else "")} for r in rows]
    return {"aspect": aspect, "sentiment": sentiment, "reviews": out}


@router.get("/analytics/summary")
def analytics_summary():
    doc = require_db().analytics.find_one({"key": "global_summary"})
    if doc is None:
        return JSONResponse(status_code=404, content=NOT_COMPUTED)
    return {**doc["data"], "computed_at": doc["computed_at"].isoformat() if hasattr(doc["computed_at"], "isoformat") else doc["computed_at"]}
