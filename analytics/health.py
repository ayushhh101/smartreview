"""Product analytics: aspect summary, trend detection, composite health score.
Pure functions over plain dicts (no Mongo, no FastAPI), so each rule is unit-testable.

Review dict fields used: rating, sentiment, aspect_sentiments {aspect: label}, review_date.

SmartReview Composite Health Score (a heuristic, NOT a validated metric):
    Health = 100 * (0.40*A + 0.30*P + 0.30*R) - trend_penalty          clamped to 0..100
    A = mean over aspects of (positive mentions / all mentions); only aspects with >= 3 mentions
    P = share of reviews whose star-derived sentiment is positive
    R = (average rating - 1) / 4
    If the product has no aspect with enough mentions, A is dropped and the 0.30/0.30 weights are
    renormalised, so a product is not punished for having few aspect mentions.
    trend_penalty: only when the positive share in the latest 12 months is lower than in the
    previous 12 months by >= 10 points AND the drop is significant (one-sided two-proportion
    z-test, 95%); penalty = min(10, 50 * drop).
"""
import math
from collections import Counter, defaultdict
from datetime import timedelta

W_ASPECT, W_OVERALL, W_RATING = 0.40, 0.30, 0.30
ASPECT_MIN_MENTIONS = 3
TREND_WINDOW_DAYS = 365
TREND_MIN_PER_WINDOW = 15
TREND_MIN_DROP = 0.10
TREND_Z = 1.645
PENALTY_PER_UNIT, PENALTY_CAP = 50, 10


def _naive(d):
    return d.replace(tzinfo=None) if getattr(d, "tzinfo", None) else d


def period_key(d, granularity):
    d = _naive(d)
    return f"{d.year}-{d.month:02d}" if granularity == "month" else f"{d.year}-Q{(d.month - 1) // 3 + 1}"


def choose_granularity(first, last):
    first, last = _naive(first), _naive(last)
    months = (last.year - first.year) * 12 + last.month - first.month
    return "month" if months <= 24 else "quarter"


def two_prop_z(p_prior, n_prior, p_recent, n_recent):
    """z for 'prior share > recent share' (positive z = the share dropped)."""
    pooled = (p_prior * n_prior + p_recent * n_recent) / (n_prior + n_recent)
    se = math.sqrt(pooled * (1 - pooled) * (1 / n_prior + 1 / n_recent))
    return (p_prior - p_recent) / se if se > 0 else 0.0


def aspect_summary(reviews):
    """{aspect: {mentions, positive, neutral, negative, positive_ratio}}"""
    counts = defaultdict(Counter)
    for r in reviews:
        for a, label in (r.get("aspect_sentiments") or {}).items():
            counts[a][label] += 1
    out = {}
    for a, c in counts.items():
        n = sum(c.values())
        out[a] = {"mentions": n, "positive": c["positive"], "neutral": c["neutral"],
                  "negative": c["negative"], "positive_ratio": round(c["positive"] / n, 4)}
    return out


def _window(reviews, lo, hi):
    sel = [r for r in reviews if lo < _naive(r["review_date"]) <= hi]
    n = len(sel)
    pos = sum(r["sentiment"] == "positive" for r in sel)
    return {"n": n, "positive_ratio": round(pos / n, 4) if n else None,
            "avg_rating": round(sum(r["rating"] for r in sel) / n, 3) if n else None}


def trend_analysis(reviews, last):
    """Recent 12 months vs the 12 months before, measured back from the product's own last review."""
    last = _naive(last)
    step = timedelta(days=TREND_WINDOW_DAYS)
    recent, prior = _window(reviews, last - step, last), _window(reviews, last - 2 * step, last - step)
    out = {"recent": recent, "prior": prior, "drop": None, "z": None, "status": "insufficient_data"}
    if recent["n"] < TREND_MIN_PER_WINDOW or prior["n"] < TREND_MIN_PER_WINDOW:
        return out
    drop = prior["positive_ratio"] - recent["positive_ratio"]
    z = two_prop_z(prior["positive_ratio"], prior["n"], recent["positive_ratio"], recent["n"])
    out.update(drop=round(drop, 4), z=round(z, 3))
    if drop >= TREND_MIN_DROP and z >= TREND_Z:
        out["status"] = "emerging_negative"
    elif -drop >= TREND_MIN_DROP and -z >= TREND_Z:
        out["status"] = "improving"
    else:
        out["status"] = "stable"
    return out


def health_score(avg_rating, positive_ratio, aspects, trend):
    usable = [v["positive_ratio"] for v in aspects.values() if v["mentions"] >= ASPECT_MIN_MENTIONS]
    a = sum(usable) / len(usable) if usable else None
    r = (avg_rating - 1) / 4
    if a is None:
        base = (W_OVERALL * positive_ratio + W_RATING * r) / (W_OVERALL + W_RATING)
    else:
        base = W_ASPECT * a + W_OVERALL * positive_ratio + W_RATING * r
    penalty = min(PENALTY_CAP, PENALTY_PER_UNIT * trend["drop"]) if trend["status"] == "emerging_negative" else 0.0
    score = max(0.0, min(100.0, 100 * base - penalty))
    return {"score": round(score, 1), "penalty": round(penalty, 1),
            "components": {"aspect_mean_positive_ratio": None if a is None else round(a, 4),
                           "aspects_used": len(usable), "overall_positive_ratio": round(positive_ratio, 4),
                           "rating_component": round(r, 4)},
            "label": "SmartReview Composite Health Score (heuristic, not a validated metric)"}


def time_series(reviews, granularity):
    buckets = defaultdict(list)
    for r in reviews:
        buckets[period_key(r["review_date"], granularity)].append(r)
    return [{"period": k, "n": len(v), "avg_rating": round(sum(x["rating"] for x in v) / len(v), 3),
             "positive_ratio": round(sum(x["sentiment"] == "positive" for x in v) / len(v), 4)}
            for k, v in sorted(buckets.items())]


def product_stats(reviews, product_id, name=None):
    """Full analytics document body for one product (needs at least 1 review)."""
    n = len(reviews)
    dates = [_naive(r["review_date"]) for r in reviews]
    first, last = min(dates), max(dates)
    avg = sum(r["rating"] for r in reviews) / n
    pos = sum(r["sentiment"] == "positive" for r in reviews) / n
    neg = sum(r["sentiment"] == "negative" for r in reviews) / n
    aspects = aspect_summary(reviews)
    usable = {a: v for a, v in aspects.items() if v["mentions"] >= ASPECT_MIN_MENTIONS}
    weakest = min(usable.items(), key=lambda kv: kv[1]["positive_ratio"]) if usable else None
    trend = trend_analysis(reviews, last)
    gran = choose_granularity(first, last)
    trend.update(granularity=gran, series=time_series(reviews, gran))
    return {
        "product_id": product_id, "name": name, "n_reviews": n, "avg_rating": round(avg, 3),
        "positive_ratio": round(pos, 4), "negative_ratio": round(neg, 4),
        "rating_histogram": {str(k): sum(r["rating"] == k for r in reviews) for k in range(1, 6)},
        "first_review": first, "last_review": last,
        "aspects": aspects,
        "weakest_aspect": {"aspect": weakest[0], "positive_ratio": weakest[1]["positive_ratio"],
                           "mentions": weakest[1]["mentions"]} if weakest else None,
        "trend": trend, "health": health_score(avg, pos, aspects, trend),
    }


class GlobalAccumulator:
    """One-pass portfolio totals: aspect sentiment counts and a quarterly series."""

    def __init__(self):
        self.aspects = defaultdict(Counter)
        self.q = defaultdict(lambda: [0, 0, 0])      # period -> [n, rating_sum, positives]

    def add(self, r):
        for a, label in (r.get("aspect_sentiments") or {}).items():
            self.aspects[a][label] += 1
        row = self.q[period_key(r["review_date"], "quarter")]
        row[0] += 1; row[1] += r["rating"]; row[2] += r["sentiment"] == "positive"

    def result(self):
        aspects = []
        for a, c in self.aspects.items():
            n = sum(c.values())
            aspects.append({"aspect": a, "mentions": n, "positive": c["positive"], "neutral": c["neutral"],
                            "negative": c["negative"], "positive_ratio": round(c["positive"] / n, 4),
                            "negative_ratio": round(c["negative"] / n, 4)})
        aspects.sort(key=lambda x: -x["mentions"])
        trend = [{"period": k, "n": v[0], "avg_rating": round(v[1] / v[0], 3), "positive_ratio": round(v[2] / v[0], 4)}
                 for k, v in sorted(self.q.items())]
        return {"aspects": aspects, "trend": trend, "granularity": "quarter"}
