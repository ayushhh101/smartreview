"""NLP pipeline: clean -> tokens -> lemmas/POS -> n-grams -> aspects -> sentiment.

Two sentiment signals are kept apart on purpose:
  sentiment        label derived from STAR RATING (training target in Phase 3)
  sentiment_score  VADER compound score of the TEXT (-1..1), a rule-based signal
Where they disagree (5 stars, negative text) is itself interesting data for the report.
Aspect sentiment = VADER on the clause containing the aspect term.
"""
import re
from collections import defaultdict

from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer

from ingestion.amazon import rating_to_sentiment
from nlp.cleaning import lemma, lemmas_with_pos, ngrams, tokenize
from nlp.lexicons import TERM_TO_ASPECT

POS_T, NEG_T = 0.05, -0.05        # standard VADER thresholds
_CLAUSE = re.compile(r"[.!?;\n]+|,|\s+but\s+|\s+however\s+|\s+although\s+|\s+though\s+", re.I)
_vader = SentimentIntensityAnalyzer()


def label_from_score(score: float) -> str:
    return "positive" if score >= POS_T else "negative" if score <= NEG_T else "neutral"


def _aspect_of(token: str):
    """Aspect for a raw token, trying noun and verb lemmas (clauses have no POS context)."""
    for cand in (token, lemma(token, "n"), lemma(token, "v")):
        if cand in TERM_TO_ASPECT:
            return TERM_TO_ASPECT[cand]
    return None


def aspect_sentiments(text: str) -> dict:
    """{aspect: label}. Multiple clauses for one aspect are averaged."""
    scores = defaultdict(list)
    for clause in _CLAUSE.split(text):
        clause = (clause or "").strip()
        if not clause:
            continue
        hit = {a for a in map(_aspect_of, tokenize(clause)) if a}
        if not hit:
            continue
        comp = _vader.polarity_scores(clause)["compound"]
        for a in hit:
            scores[a].append(comp)
    return {a: label_from_score(sum(v) / len(v)) for a, v in scores.items()}


def analyze(text: str, rating: int | None = None) -> dict:
    """Full analysis of one review text. Pure function, no database."""
    tokens = tokenize(text)
    lemmas, keywords = lemmas_with_pos(tokens)
    asp = aspect_sentiments(text)
    out = {
        "tokens": tokens,
        "lemmas": lemmas,
        "bigrams": ngrams(lemmas, 2),
        "trigrams": ngrams(lemmas, 3),
        "keywords": sorted(set(keywords)),
        "aspects": sorted(asp),
        "aspect_sentiments": asp,
        "sentiment_score": round(_vader.polarity_scores(text)["compound"], 4),
    }
    if rating is not None:
        out["sentiment"] = rating_to_sentiment(rating)
    return out
