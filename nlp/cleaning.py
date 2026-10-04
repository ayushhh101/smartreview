"""Tokenisation, stop words, lemmas, POS, n-grams.

NLTK's default stop list contains negations (not, no, nor, don't...). Dropping them
flips the meaning of "not good", so they are explicitly kept.
"""
import re
from functools import lru_cache

import nltk
from nltk.corpus import stopwords, wordnet
from nltk.stem import WordNetLemmatizer

NEGATIONS = {"no", "nor", "not", "never", "none", "cannot", "without"}
_TOKEN = re.compile(r"[a-z]+(?:'[a-z]+)?")
_lem = WordNetLemmatizer()


class NLTKDataMissing(RuntimeError):
    pass


@lru_cache(maxsize=1)
def stop_words():
    try:
        base = set(stopwords.words("english"))
    except LookupError as exc:
        raise NLTKDataMissing("Run: python -m scripts.setup_nltk") from exc
    # drop contractions of negation too ("didn't", "isn't") by stripping to the stem check below
    keep = NEGATIONS | {w for w in base if w.endswith("n't")}
    return frozenset(base - keep)


def tokenize(text: str):
    """Lowercase word tokens; apostrophes inside words are kept (didn't)."""
    return _TOKEN.findall(text.lower().replace("’", "'"))


def _wn_pos(tag: str):
    return {"J": wordnet.ADJ, "V": wordnet.VERB, "N": wordnet.NOUN, "R": wordnet.ADV}.get(tag[:1], wordnet.NOUN)


@lru_cache(maxsize=200_000)
def lemma(word: str, pos: str = wordnet.NOUN) -> str:
    try:
        return _lem.lemmatize(word, pos)
    except LookupError as exc:
        raise NLTKDataMissing("Run: python -m scripts.setup_nltk") from exc


def pos_tag(tokens):
    try:
        return nltk.pos_tag(tokens)
    except LookupError as exc:
        raise NLTKDataMissing("Run: python -m scripts.setup_nltk") from exc


def lemmas_with_pos(tokens):
    """POS-aware lemmas for content tokens. Returns (lemmas, noun_adj_lemmas)."""
    stops = stop_words()
    tagged = pos_tag(tokens)
    out, keywords = [], []
    for word, tag in tagged:
        if word in stops or len(word) < 2:
            continue
        lm = lemma(word, _wn_pos(tag))
        out.append(lm)
        if tag[:1] in ("N", "J") and word not in NEGATIONS:
            keywords.append(lm)
    return out, keywords


def ngrams(items, n):
    return [" ".join(items[i:i + n]) for i in range(len(items) - n + 1)]
