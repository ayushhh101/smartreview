"""Train + evaluate the four classifiers on reviews in MongoDB.

  python -m scripts.train_models --max-docs 20000 --folds 3     # quick check (a few minutes)
  python -m scripts.train_models                                # everything loaded, 5-fold CV

Saves: models/best_model.joblib, models/logistic_regression.joblib (used by /ml/explain),
models/manifest.json, and one document per model in the `model_results` collection.
"""
import argparse
import datetime as dt
import random

from backend.database.mongo import require_db
from ml import registry
from ml.training import LABELS, make_models, run_experiment


def load_corpus(db, max_docs=0, seed=42):
    cur = db.reviews.find({"lemmas": {"$exists": True}, "sentiment": {"$in": LABELS}},
                          {"lemmas": 1, "sentiment": 1, "product_id": 1, "_id": 0})
    rows = [(" ".join(d["lemmas"]), d["sentiment"], d["product_id"]) for d in cur]
    rows = [r for r in rows if r[0].strip()]                  # reviews whose lemmas came out empty
    if max_docs and len(rows) > max_docs:
        random.Random(seed).shuffle(rows)
        rows = rows[:max_docs]
    return rows


def train(db=None, max_docs=0, folds=5, only=None, max_features=30_000, log=print):
    db = db if db is not None else require_db()
    rows = load_corpus(db, max_docs)
    if len(rows) < 200:
        raise SystemExit(f"Only {len(rows)} NLP-processed reviews in MongoDB - run scripts.seed_database first.")
    log(f"loaded {len(rows):,} reviews")
    texts, labels, groups = zip(*rows)
    models = make_models()
    if only:
        models = {k: v for k, v in models.items() if k in only}
    results, fitted, info = run_experiment(texts, labels, groups, models, folds, max_features=max_features, log=log)

    now = dt.datetime.now(dt.timezone.utc)
    db.model_results.delete_many({})
    db.model_results.insert_many([{**r, "trained_at": now, "baseline": info["baseline"],
                                  "class_distribution": info["class_distribution"]} for r in results])
    best = next(r["model_name"] for r in results if r["is_best"])
    registry.save("best_model", fitted[best], {"best": best, "trained_at": now.isoformat(), **info})
    if "logistic_regression" in fitted:
        registry.save("logistic_regression", fitted["logistic_regression"])
    log(f"best by CV macro-F1: {best}.  baseline test accuracy {info['baseline']['accuracy']}, "
        f"macro-F1 {info['baseline']['macro_f1']}")
    return results, info


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--max-docs", type=int, default=0, help="0 = use everything in MongoDB")
    ap.add_argument("--folds", type=int, default=5)
    ap.add_argument("--only", nargs="*", help="e.g. --only logistic_regression linear_svm")
    ap.add_argument("--max-features", type=int, default=30_000)
    a = ap.parse_args()
    train(None, a.max_docs, a.folds, a.only, a.max_features)
