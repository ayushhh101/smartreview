"""Overview statistics, computed directly from MongoDB (no hardcoded numbers)."""
from backend.database.mongo import require_db


def overview() -> dict:
    db = require_db()
    total = db.reviews.count_documents({})
    products = db.products.count_documents({})
    if total == 0:
        return {"seeded": False, "total_reviews": 0, "products": products,
                "sentiment": {}, "top_complaint": None}

    sentiment = {r["_id"]: r["n"] for r in db.reviews.aggregate(
        [{"$group": {"_id": "$sentiment", "n": {"$sum": 1}}}]) if r["_id"]}
    scored = sum(sentiment.values()) or 1

    top = list(db.reviews.aggregate([
        {"$match": {"aspect_sentiments": {"$exists": True}}},
        {"$project": {"a": {"$objectToArray": "$aspect_sentiments"}}},
        {"$unwind": "$a"}, {"$match": {"a.v": "negative"}},
        {"$group": {"_id": "$a.k", "n": {"$sum": 1}}},
        {"$sort": {"n": -1}}, {"$limit": 1}]))
    return {
        "seeded": True,
        "total_reviews": total,
        "products": products,
        "sentiment": sentiment,
        "positive_pct": round(100 * sentiment.get("positive", 0) / scored, 1) if sentiment else None,
        "negative_pct": round(100 * sentiment.get("negative", 0) / scored, 1) if sentiment else None,
        "top_complaint": top[0]["_id"] if top else None,
        "nlp_processed": bool(sentiment),
    }
