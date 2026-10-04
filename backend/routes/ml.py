from fastapi import APIRouter
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from backend.database.mongo import require_db
from ml import registry
from ml.training import LABELS, explain
from nlp.pipeline import analyze

router = APIRouter(prefix="/ml")

NOT_TRAINED = {"error": "not_trained", "message": "No trained models yet.",
               "hint": "Run: python -m scripts.train_models --max-docs 20000 --folds 3"}


class Text(BaseModel):
    text: str = Field(min_length=3, max_length=5000)


def _prep(text: str) -> str:
    """Same preprocessing as training: NLP pipeline lemmas joined by spaces."""
    return " ".join(analyze(text)["lemmas"])


@router.get("/model-comparison")
def model_comparison():
    docs = list(require_db().model_results.find({}, {"_id": 0}))
    if not docs:
        return JSONResponse(status_code=404, content=NOT_TRAINED)
    docs.sort(key=lambda d: -d["cv_mean_f1"])
    for d in docs:
        d["trained_at"] = d["trained_at"].isoformat() if hasattr(d.get("trained_at"), "isoformat") else d.get("trained_at")
    return {"models": docs, "baseline": docs[0].get("baseline"), "class_distribution": docs[0].get("class_distribution"),
            "selection_rule": "best = highest mean cross-validated macro-F1 on the training split; test metrics are held out",
            "label_note": "Labels come from star ratings (<=2 negative, 3 neutral, >=4 positive), not human annotation."}


@router.post("/predict")
def predict(body: Text):
    pipe = registry.load("best_model")
    if pipe is None:
        return JSONResponse(status_code=404, content=NOT_TRAINED)
    x = _prep(body.text)
    if not x.strip():
        return JSONResponse(status_code=422, content={"error": "no_content", "message": "No usable words in the text."})
    label = pipe.predict([x])[0]
    out = {"label": label, "model": registry.manifest().get("best") if registry.manifest() else None}
    clf = pipe.named_steps["clf"]
    if hasattr(clf, "predict_proba"):
        out["probabilities"] = {c: round(float(p), 4) for c, p in zip(clf.classes_, pipe.predict_proba([x])[0])}
    else:                                   # LinearSVC has no probabilities; do not invent them
        out["decision_scores"] = {c: round(float(s), 4) for c, s in zip(clf.classes_, pipe.decision_function([x])[0])}
    return out


@router.post("/explain")
def explain_route(body: Text):
    pipe = registry.load("logistic_regression")
    if pipe is None:
        return JSONResponse(status_code=404, content=NOT_TRAINED)
    x = _prep(body.text)
    if not x.strip():
        return JSONResponse(status_code=422, content={"error": "no_content", "message": "No usable words in the text."})
    return {"model": "logistic_regression", **explain(pipe, x)}
