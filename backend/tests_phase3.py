import numpy as np
import mongomock
import pytest
from fastapi.testclient import TestClient

from backend.main import app
from ml import registry
from ml.training import LABELS, evaluate, explain, group_split, make_models, pipeline, run_experiment
from scripts import train_models

POS = ["great sound love it", "excellent quality sturdy", "perfect easy to use", "works great recommend", "amazing tone happy"]
NEG = ["broke after week terrible", "waste of money awful", "not work return refund", "poor quality cheap broken", "bad noise defective"]
NEU = ["okay for the price", "average nothing special", "decent but not great", "fine does the job", "so so mediocre"]


def corpus(n=600, seed=0):
    rng = np.random.default_rng(seed)
    pool = {"positive": POS, "negative": NEG, "neutral": NEU}
    labels = rng.choice(LABELS, size=n, p=[0.2, 0.1, 0.7])
    texts = [pool[l][rng.integers(5)] + f" item{rng.integers(30)}" for l in labels]
    groups = [f"P{rng.integers(40)}" for _ in range(n)]
    return texts, list(labels), groups


def test_group_split_has_no_product_overlap():
    _, y, g = corpus()
    tr, te = group_split(np.array(y), np.array(g))
    assert not ({g[i] for i in tr} & {g[i] for i in te})


def test_experiment_shapes_and_selection_rule():
    t, y, g = corpus()
    models = {k: v for k, v in make_models().items() if k in ("logistic_regression", "linear_svm")}
    res, fitted, info = run_experiment(t, y, g, models, cv_folds=3, log=lambda *_: None)
    assert {r["model_name"] for r in res} == set(models) and sum(r["is_best"] for r in res) == 1
    best = max(res, key=lambda r: r["cv_mean_f1"])
    assert best["is_best"]
    r = res[0]
    assert len(r["cv_scores"]) == 3 and np.array(r["confusion_matrix"]).shape == (3, 3)
    assert np.array(r["confusion_matrix"]).sum() == r["n_test"]
    assert r["metrics"]["macro_f1"] > info["baseline"]["macro_f1"]       # beats the majority baseline
    assert 0 <= r["metrics"]["roc_auc_ovr"]["macro"] <= 1
    assert set(info["class_distribution"]) == set(LABELS)


def test_explain_requires_linear_model_and_returns_terms():
    t, y, g = corpus()
    p = pipeline(make_models()["logistic_regression"]).fit(t, y)
    e = explain(p, "great sound love it")
    assert e["predicted"] == "positive" and e["supporting"]
    rf = pipeline(make_models()["decision_tree"]).fit(t, y)
    with pytest.raises(ValueError):
        explain(rf, "great")


@pytest.fixture
def trained(tmp_path, monkeypatch):
    monkeypatch.setattr(registry, "MODELS_DIR", tmp_path)
    registry._cache.clear()
    db = mongomock.MongoClient().sr
    t, y, g = corpus(400)
    db.reviews.insert_many([{"lemmas": x.split(), "sentiment": s, "product_id": p} for x, s, p in zip(t, y, g)])
    train_models.train(db, folds=3, only=["logistic_regression", "linear_svm"], log=lambda *_: None)
    import backend.routes.ml as r
    monkeypatch.setattr(r, "require_db", lambda: db)
    return db


def test_api_404_when_untrained(tmp_path, monkeypatch):
    monkeypatch.setattr(registry, "MODELS_DIR", tmp_path)
    registry._cache.clear()
    import backend.routes.ml as r
    monkeypatch.setattr(r, "require_db", lambda: mongomock.MongoClient().empty)
    c = TestClient(app)
    for resp in (c.get("/api/ml/model-comparison"), c.post("/api/ml/predict", json={"text": "great sound"}),
                 c.post("/api/ml/explain", json={"text": "great sound"})):
        assert resp.status_code == 404 and resp.json()["error"] == "not_trained"


def test_api_after_training(trained):
    c = TestClient(app)
    cmp = c.get("/api/ml/model-comparison").json()
    assert len(cmp["models"]) == 2 and cmp["baseline"]["accuracy"] > 0 and "label_note" in cmp
    p = c.post("/api/ml/predict", json={"text": "great sound love it"}).json()
    assert p["label"] == "positive" and ("probabilities" in p or "decision_scores" in p)
    e = c.post("/api/ml/explain", json={"text": "terrible broke waste of money"}).json()
    assert e["predicted"] == "negative"
    assert c.post("/api/ml/predict", json={"text": "!!!"}).status_code == 422
