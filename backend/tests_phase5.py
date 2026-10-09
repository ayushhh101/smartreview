import math
import random
from collections import Counter

import mongomock
import numpy as np
import pytest
from fastapi.testclient import TestClient
from sklearn.feature_extraction.text import TfidfVectorizer

from backend.main import app
from ml import registry
from nlp import corpus as C
from nlp.analysis import aspect_details, explain_text, find_entities, analyze_tokens, noun_phrases
from nlp.pipeline import aspect_sentiments
from scripts.compute_nlp_stats import compute


# ---------- step-by-step analysis ----------
def toks(text):
    return {t["text"]: t for t in analyze_tokens(text)[1]}


def test_pos_stop_stem_lemma():
    t = toks("The tone is great but the strap broke after two weeks.")
    assert t["tone"]["pos"] == "NN" and t["great"]["pos"] == "JJ" and t["The"]["is_stop"] and not t["tone"]["is_stop"]
    assert t["is"]["lemma"] == "be" and t["broke"]["lemma"] == "break" and t["weeks"]["lemma"] == "week" and t["weeks"]["porter"] == "week"
    assert t["."]["is_punct"] and t["."]["porter"] == "."


def test_negations_are_not_stop_words_in_explorer():
    t = toks("It did not work and I wouldn't buy it")
    assert not t["not"]["is_stop"]


def test_stemmers_differ_but_lemma_is_a_word():
    t = toks("The company was really easily fooled")
    assert t["easily"]["porter"] == "easili" and t["easily"]["lemma"] == "easily"


def test_noun_phrases_and_opinion_pairs():
    _, tokens, tagged = analyze_tokens("The tone is great. I love the great sustain pedal.")
    phrases, pairs = noun_phrases(tagged)
    assert any("tone" in p for p in phrases) and any("pedal" in p for p in phrases)
    got = {(p["adjective"], p["noun"], p["pattern"]) for p in pairs}
    assert ("great", "tone", "noun + be + adjective") in got and ("great", "pedal", "adjective + noun") in got


def test_entities_gazetteer_multiword_and_proper_nouns():
    _, tokens, _ = analyze_tokens("I bought a Fender guitar and Ernie Ball strings from Amazon.")
    e = {(x["text"], x["type"]) for x in find_entities(tokens)}
    assert ("Fender", "BRAND") in e and ("guitar", "INSTRUMENT") in e and ("Ernie Ball", "BRAND") in e and ("strings", "GEAR") in e
    assert ("Amazon", "PROPER_NOUN") in e


def test_aspect_details_agree_with_the_classifier_pipeline():
    for text in ["The tone is great but the strap broke after two weeks.", "Terrible sound, cheap build, but easy setup and fair price!",
                 "I like the piano.. but the sustain pedal failed after less than 1 year. I expected better support.", "works great with my tablet"]:
        details, summary = aspect_details(text)
        assert summary == aspect_sentiments(text), text
        assert all(d["triggers"] and d["clause"] for d in details)


def test_explain_text_shape_and_tfidf_top():
    docs = ["great sound easy setup", "terrible broke waste money", "okay for price", "love tone great", "bad noise return"] * 5
    tf = TfidfVectorizer(ngram_range=(1, 2)).fit(docs)
    r = explain_text("Great tone and easy to set up, love it!", tf)
    assert r["n_sentences"] == 1 and r["n_words"] == 9 and r["model_input"]["lemmas"] and r["sentiment"]["overall"]["label"] == "positive"
    assert r["tfidf_top"] and r["tfidf_top"][0]["weight"] >= r["tfidf_top"][-1]["weight"]
    assert explain_text("!!!")["model_input"]["text"] == ""


# ---------- corpus functions ----------
def test_vocab_stats_and_reduction():
    s = C.vocab_stats(Counter({"a": 1, "b": 1, "c": 8}), Counter({"x": 5}), 2)
    assert s["vocab_raw"] == 3 and s["hapax_count"] == 2 and s["vocab_reduction_pct"] == 66.7 and s["tokens_removed_pct"] == 50.0


def test_zipf_slope_for_a_zipfian_corpus():
    counts = Counter({f"w{r}": int(100000 / r) for r in range(1, 3001)})
    z = C.zipf_points(counts)
    assert -1.1 < z["slope"] < -0.9 and z["r2"] > 0.99 and z["points"][0] == {"rank": 1, "freq": 100000}


def test_log_odds_finds_class_specific_terms():
    pos = Counter({"great": 300, "love": 200, "the": 1000, "item": 100}); neg = Counter({"broke": 300, "waste": 200, "the": 1000, "item": 100})
    out = C.distinctive_by_class({"positive": pos, "negative": neg}, top=2)
    assert [r["term"] for r in out["positive"]] == ["great", "love"] and [r["term"] for r in out["negative"]] == ["broke", "waste"]
    assert all(r["z"] > 0 for r in out["positive"]) and "the" not in [r["term"] for r in out["positive"]]


def test_pmi_prefers_sticky_pairs():
    bg = Counter({"sustain pedal": 100, "good product": 100, "pedal product": 5}); un = Counter({"sustain": 120, "pedal": 400, "good": 2000, "product": 4000})
    r = C.pmi_collocations(bg, un, min_count=40)
    assert r[0]["bigram"] == "sustain pedal" and r[0]["pmi"] > r[1]["pmi"] and len(r) == 2


def synth(n=1200, seed=1):
    rng = random.Random(seed)
    clusters = [["guitar", "string", "pick", "fret", "neck", "tune", "chord", "strum", "capo", "tone"],
                ["battery", "charger", "cable", "power", "usb", "plug", "adapter", "cord", "volt", "charge"],
                ["sound", "volume", "speaker", "bass", "treble", "loud", "clear", "mic", "noise", "audio"],
                ["broke", "return", "refund", "defect", "waste", "cheap", "flimsy", "snap", "crack", "fail"]]
    rows = []
    for i in range(n):
        k = i % 4
        words = [rng.choice(clusters[k]) for _ in range(7)]
        s = "negative" if k == 3 else "positive"
        rows.append({"tokens": words, "lemmas": words, "bigrams": [f"{a} {b}" for a, b in zip(words, words[1:])],
                     "keywords": sorted(set(words)), "sentiment": s, "rating": 1 if k == 3 else 5})
    return rows


def test_topics_recover_planted_clusters():
    rows = synth()
    topics = C.topic_model([" ".join(r["lemmas"]) for r in rows], [r["rating"] for r in rows], [r["sentiment"] for r in rows], n_topics=4)
    assert len(topics) == 4 and abs(sum(t["share"] for t in topics) - 1) < 1e-6
    bad = [t for t in topics if "broke" in t["top_words"] or "refund" in t["top_words"]]
    assert bad and bad[0]["negative_share"] > 0.95 and bad[0]["avg_rating"] == 1.0


def test_lsa_nearest_words_come_from_the_same_cluster():
    rows = synth()
    m = C.lsa_word_vectors([" ".join(r["lemmas"]) for r in rows], dim=10)
    near = [r["word"] for r in C.nearest(m, "guitar", 3)]
    assert set(near) <= {"string", "pick", "fret", "neck", "tune", "chord", "strum", "capo", "tone"}
    assert C.nearest(m, "zzzz") is None


# ---------- script + API ----------
@pytest.fixture
def env(tmp_path, monkeypatch):
    monkeypatch.setattr(registry, "MODELS_DIR", tmp_path); registry._cache.clear()
    db = mongomock.MongoClient().p5
    db.reviews.insert_many(synth())
    import backend.routes.nlp as r
    monkeypatch.setattr(r, "require_db", lambda: db)
    return db


def test_api_404_before_compute(env):
    c = TestClient(app)
    assert c.get("/api/nlp/corpus").json()["error"] == "not_computed"
    assert c.get("/api/nlp/similar-words?word=guitar").json()["error"] == "not_computed"


def test_analyze_works_without_a_trained_model(env):
    j = TestClient(app).post("/api/nlp/analyze", json={"text": "The tone is great but the strap broke."}).json()
    assert j["model"] is None and j["aspects"]["summary"] == {"sound": "positive", "durability": "negative"} and j["tokens"]
    assert TestClient(app).post("/api/nlp/analyze", json={"text": "x"}).status_code == 422


def test_compute_and_endpoints(env):
    d = compute(env, sample=800, log=lambda *_: None)
    assert d["vocab_raw"] == 40 and d["zipf"]["points"] and set(d["distinctive_unigrams"]) == {"negative", "neutral", "positive"}
    c = TestClient(app)
    j = c.get("/api/nlp/corpus").json()
    assert j["n_reviews"] == 1200 and len(j["topics"]) == 8 and "computed_at" in j
    assert j["distinctive_unigrams"]["negative"][0]["term"] in {"broke", "return", "refund", "defect", "waste", "cheap", "flimsy", "snap", "crack", "fail"}
    s = c.get("/api/nlp/similar-words?word=guitar&k=3").json()
    assert len(s["neighbors"]) == 3 and "LSA" in s["method"]
    assert c.get("/api/nlp/similar-words?word=qwertyu").json()["error"] == "word_not_found"
    compute(env, sample=800, log=lambda *_: None)
    assert env.analytics.count_documents({"key": "nlp_corpus"}) == 1


def test_analyze_with_trained_model(env):
    from ml.training import make_models, pipeline
    texts = [" ".join(r["lemmas"]) for r in synth()]
    labels = [r["sentiment"] for r in synth()]
    registry.save("best_model", pipeline(make_models()["logistic_regression"]).fit(texts, labels), {"best": "logistic_regression"})
    j = TestClient(app).post("/api/nlp/analyze", json={"text": "broke waste refund"}).json()
    assert j["model"]["label"] == "negative" and isinstance(j["model"]["agrees_with_lexicon"], bool) and j["tfidf_top"]
