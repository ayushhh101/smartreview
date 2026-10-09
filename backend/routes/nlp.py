from fastapi import APIRouter, Query
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from backend.database.mongo import require_db
from ml import registry
from nlp.analysis import explain_text
from nlp.corpus import nearest

router = APIRouter(prefix="/nlp")
NOT_COMPUTED = {"error": "not_computed", "message": "Corpus NLP statistics have not been computed yet.",
                "hint": "Run: python -m scripts.compute_nlp_stats"}


class Text(BaseModel):
    text: str = Field(min_length=2, max_length=2000)


@router.post("/analyze")
def analyze_text(body: Text):
    """Every NLP step on one text, plus the trained classifier's verdict when a model exists."""
    pipe = registry.load("best_model")
    tfidf = pipe.named_steps["tfidf"] if pipe is not None else None
    out = explain_text(body.text, tfidf)
    out["model"] = None
    text = out["model_input"]["text"]
    if pipe is not None and text.strip():
        label = pipe.predict([text])[0]
        mf = registry.manifest() or {}
        out["model"] = {"name": mf.get("best"), "label": label,
                        "agrees_with_lexicon": label == out["sentiment"]["overall"]["label"]}
    return out


@router.get("/corpus")
def corpus():
    doc = require_db().analytics.find_one({"key": "nlp_corpus"})
    if doc is None:
        return JSONResponse(status_code=404, content=NOT_COMPUTED)
    return {**doc["data"], "computed_at": doc["computed_at"].isoformat() if hasattr(doc["computed_at"], "isoformat") else doc["computed_at"]}


@router.get("/similar-words")
def similar_words(word: str = Query(min_length=2, max_length=30), k: int = Query(8, ge=1, le=20)):
    model = registry.load("lsa_words")
    if model is None:
        return JSONResponse(status_code=404, content=NOT_COMPUTED)
    w = word.strip().lower()
    res = nearest(model, w, k)
    if res is None:
        return JSONResponse(status_code=404, content={"error": "word_not_found",
                            "message": f"'{w}' is not in the {len(model['vocab']):,}-word vocabulary (min 15 reviews)."})
    return {"word": w, "method": f"LSA (TruncatedSVD, {model['dim']} dimensions), cosine similarity", "neighbors": res}
