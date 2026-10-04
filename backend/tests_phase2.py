import json
import os
import tempfile

import mongomock

from ingestion.amazon import (clean_text, iter_jsonl, make_review_id, parse_timestamp,
                              rating_to_sentiment, to_review)
from nlp.cleaning import stop_words, tokenize
from nlp.pipeline import analyze, aspect_sentiments
from scripts.seed_database import seed

SAMPLE = os.path.join(os.path.dirname(__file__), "..", "data", "sample_reviews.jsonl")


def raw_rows():
    return [r for _, r in iter_jsonl(SAMPLE)]


# ---- ingestion -------------------------------------------------------------
def test_all_sample_rows_map_cleanly():
    docs = [to_review(r) for r in raw_rows()]
    assert len(docs) == 12 and all(d is not None and why is None for d, why in docs)


def test_field_mapping_uses_parent_asin_and_ms_timestamp():
    d, _ = to_review(raw_rows()[1])               # asin B00723436A, parent B06XP6TDVY
    assert d["product_id"] == "B06XP6TDVY" and d["asin"] == "B00723436A"
    assert (d["review_date"].year, d["review_date"].month) == (2019, 5)
    assert d["helpful_votes"] == 2 and d["rating"] == 3 and d["verified_purchase"] is True


def test_review_id_is_deterministic_and_unique():
    ids = [to_review(r)[0]["review_id"] for r in raw_rows()]
    assert len(set(ids)) == 12
    assert make_review_id("u", "p", 1) == make_review_id("u", "p", 1)


def test_rejects_bad_rows_with_reason():
    good = raw_rows()[0]
    assert to_review({**good, "rating": 9})[1] == "bad_rating"
    assert to_review({**good, "rating": None})[1] == "bad_rating"
    assert to_review({**good, "timestamp": "x"})[1] == "bad_timestamp"
    assert to_review({**good, "timestamp": 5})[1] == "bad_timestamp"
    assert to_review({**good, "user_id": ""})[1] == "missing_ids"
    assert to_review({**good, "text": "  "})[1] == "text_too_short"
    assert to_review("nope")[1] == "not_an_object"


def test_timestamp_seconds_are_tolerated():
    assert parse_timestamp(1452650586).year == 2016


def test_clean_text_strips_html_and_entities():
    assert clean_text("Great<br />sound &amp; build  ") == "Great sound & build"


def test_rating_to_sentiment():
    assert [rating_to_sentiment(r) for r in (1, 2, 3, 4, 5)] == \
        ["negative", "negative", "neutral", "positive", "positive"]


# ---- NLP -------------------------------------------------------------------
def test_negations_survive_stopword_removal():
    sw = stop_words()
    assert "not" not in sw and "no" not in sw and "didn't" not in sw and "the" in sw
    assert "not" in analyze("it is not good")["lemmas"]


def test_tokenizer_keeps_contractions():
    assert tokenize("It didn’t work!") == ["it", "didn't", "work"]


def test_aspect_sentiment_direction():
    a = aspect_sentiments("The sound is amazing, but the battery died after a week")
    assert a["sound"] == "positive" and a["connectivity_power"] == "negative"


def test_negated_praise_is_negative():
    assert aspect_sentiments("The sound is not good")["sound"] == "negative"


def test_last_weekend_is_not_a_durability_complaint():
    assert "durability" not in aspect_sentiments("We had a party last weekend and it was great")


def test_analyze_output_shape():
    a = analyze("Great sturdy stand, easy to set up", 5)
    for k in ("tokens", "lemmas", "bigrams", "trigrams", "keywords", "aspects",
              "aspect_sentiments", "sentiment_score", "sentiment"):
        assert k in a
    assert a["sentiment"] == "positive" and a["sentiment_score"] > 0.05
    assert a["aspects"] == sorted(a["aspect_sentiments"])


def test_rating_label_and_text_score_are_independent():
    d, _ = to_review(raw_rows()[4])               # 5 stars, but text describes a struggle
    a = analyze(d["full_text"], d["rating"])
    assert a["sentiment"] == "positive" and a["sentiment_score"] < 0


# ---- seeding (mongomock: no server needed) ----------------------------------
def test_seed_is_idempotent_and_counts_rejects():
    db = mongomock.MongoClient().smartreview
    with tempfile.NamedTemporaryFile("w", suffix=".jsonl", delete=False) as fh:
        for r in raw_rows():
            fh.write(json.dumps(r) + "\n")
        fh.write(json.dumps({**raw_rows()[0], "rating": 7}) + "\n")
        fh.write("{not json\n")
    s1 = seed(fh.name, db=db, log=lambda *_: None)
    assert s1["reviews_loaded"] == 12 and s1["rejected"] == {"bad_rating": 1, "bad_json": 1}
    seed(fh.name, db=db, log=lambda *_: None)
    assert db.reviews.count_documents({}) == 12
    assert db.products.count_documents({}) == s1["products"]
    r = db.reviews.find_one({"product_id": "B06XP6TDVY"})
    assert r["sentiment"] == "neutral" and "aspect_sentiments" in r and "label_sentiment" not in r
    os.unlink(fh.name)


def test_seed_fails_fast_on_missing_meta_and_dedupes_batches():
    import pytest
    db = mongomock.MongoClient().smartreview2
    with pytest.raises(FileNotFoundError):
        seed(SAMPLE, meta_path="nope.jsonl", db=db, log=lambda *_: None)
    assert db.reviews.count_documents({}) == 0               # failed before doing any work
    with tempfile.NamedTemporaryFile("w", suffix=".jsonl", delete=False) as fh:
        for r in raw_rows() + raw_rows()[:3]:                # same review id twice in one batch
            fh.write(json.dumps(r) + "\n")
    seed(fh.name, db=db, log=lambda *_: None)
    assert db.reviews.count_documents({}) == 12
    os.unlink(fh.name)


def test_derived_only_rebuilds_products_and_users():
    db = mongomock.MongoClient().smartreview3
    with tempfile.NamedTemporaryFile("w", suffix=".jsonl", delete=False) as fh:
        for r in raw_rows():
            fh.write(json.dumps(r) + "\n")
    seed(fh.name, db=db, log=lambda *_: None)
    db.products.delete_many({}); db.users.delete_many({})
    s = seed(None, db=db, log=lambda *_: None, derived_only=True)
    assert s["reviews_loaded"] == 0 and db.products.count_documents({}) == s["products"] > 0
    assert db.users.count_documents({}) == s["users"] > 0
    os.unlink(fh.name)
