"""Step-by-step text analysis for the NLP Explorer page. Pure functions (no Mongo, no FastAPI).

Shows every classic NLP step on one piece of text:
  sentence splitting -> tokenisation -> POS tagging -> stop words -> stemming (3 stemmers) -> lemmatisation
  -> noun-phrase chunking -> opinion pairs -> named entities (gazetteer) -> n-grams -> aspects -> sentiment.

Honesty note: the Explorer tags the ORIGINAL-case text (better for proper nouns). The classifier's own
pipeline (nlp/pipeline.py) lower-cases first. `model_input` is exactly what the classifier receives.
"""
import re

from nltk import RegexpParser, sent_tokenize
from nltk.stem import LancasterStemmer, PorterStemmer, SnowballStemmer

from nlp.cleaning import _wn_pos, lemma, pos_tag, stop_words, tokenize
from nlp.lexicons import BRANDS, GEAR, INSTRUMENTS
from nlp.pipeline import _CLAUSE, _aspect_of, _vader, analyze, label_from_score

_porter, _snow, _lanc = PorterStemmer(), SnowballStemmer("english"), LancasterStemmer()
_TOKEN = re.compile(r"[A-Za-z]+(?:['’][A-Za-z]+)?|\d+(?:\.\d+)?|[^\sA-Za-z\d]")
_GRAMMAR = RegexpParser(r"NP: {<DT|PRP\$>?<JJ.*|VBN|VBG>*<NN.*>+}")
_BE = {"is", "are", "was", "were", "be", "been", "seems", "seemed", "feels", "felt", "looks", "sounds", "'s", "’s"}
POS_MEANING = {
    "NN": "noun", "NNS": "noun, plural", "NNP": "proper noun", "NNPS": "proper noun, plural", "JJ": "adjective",
    "JJR": "adjective, comparative", "JJS": "adjective, superlative", "RB": "adverb", "RBR": "adverb, comparative",
    "RBS": "adverb, superlative", "VB": "verb, base", "VBD": "verb, past", "VBG": "verb, -ing", "VBN": "verb, past participle",
    "VBP": "verb, present", "VBZ": "verb, 3rd person", "DT": "determiner", "IN": "preposition", "CC": "conjunction",
    "PRP": "pronoun", "PRP$": "possessive pronoun", "MD": "modal verb", "CD": "number", "TO": "to", "UH": "interjection",
    "WRB": "wh-adverb", "WDT": "wh-determiner", "WP": "wh-pronoun", "EX": "existential there", "RP": "particle", "POS": "possessive",
}


def _is_punct(t):
    return not any(c.isalnum() for c in t)


def analyze_tokens(text):
    """Tokens with POS, stop-word flag, three stems and the lemma. Also returns tagged sentences."""
    stops = stop_words()
    sentences, tokens, tagged_sents = sent_tokenize(text), [], []
    for si, sent in enumerate(sentences):
        raw = _TOKEN.findall(sent)
        tagged = pos_tag(raw) if raw else []
        tagged_sents.append(tagged)
        for word, tag in tagged:
            low = word.lower().replace("’", "'")
            punct = _is_punct(word)
            alpha = low.replace("'", "").isalpha()
            tokens.append({
                "text": word, "lower": low, "sentence": si, "pos": tag, "pos_meaning": POS_MEANING.get(tag, ""),
                "is_punct": punct, "is_stop": (low in stops) if not punct else False,
                "porter": _porter.stem(low) if alpha else low, "snowball": _snow.stem(low) if alpha else low,
                "lancaster": _lanc.stem(low) if alpha else low,
                "lemma": lemma(low, _wn_pos(tag)) if alpha else low})
    return sentences, tokens, tagged_sents


def noun_phrases(tagged_sents):
    """Chunking with a regular-expression grammar over POS tags."""
    phrases, pairs = [], []
    for tagged in tagged_sents:
        tree = _GRAMMAR.parse(tagged)
        for st in tree.subtrees(lambda t: t.label() == "NP"):
            leaves = st.leaves()
            phrases.append(" ".join(w for w, _ in leaves).lower())
            nouns = [w.lower() for w, t in leaves if t.startswith("NN")]
            for w, t in leaves:
                if t.startswith("JJ") and nouns:
                    pairs.append({"adjective": w.lower(), "noun": nouns[-1], "pattern": "adjective + noun"})
        for i, (w, t) in enumerate(tagged):                       # copular pattern: "the tone is really great"
            if t.startswith("NN"):
                window = tagged[i + 1:i + 5]
                if window and window[0][0].lower() in _BE:
                    for w2, t2 in window[1:]:
                        if t2.startswith("JJ"):
                            pairs.append({"adjective": w2.lower(), "noun": w.lower(), "pattern": "noun + be + adjective"})
                            break
    seen, uniq = set(), []
    for p in pairs:
        k = (p["adjective"], p["noun"], p["pattern"])
        if k not in seen:
            seen.add(k)
            uniq.append(p)
    return list(dict.fromkeys(phrases)), uniq


def find_entities(tokens):
    """Dictionary NER (brands, instruments, gear) plus a proper-noun heuristic."""
    ents, i, n = [], 0, len(tokens)
    lows = [t["lower"] for t in tokens]
    while i < n:
        if tokens[i]["is_punct"]:
            i += 1
            continue
        hit = None
        for L in (3, 2, 1):
            phrase = " ".join(lows[i:i + L])
            if len(lows[i:i + L]) < L:
                continue
            cands = (phrase, tokens[i]["lemma"]) if L == 1 else (phrase,)
            for typ, gaz in (("BRAND", BRANDS), ("INSTRUMENT", INSTRUMENTS), ("GEAR", GEAR)):
                if any(c in gaz for c in cands):
                    hit = (typ, L)
                    break
            if hit:
                break
        if hit:
            ents.append({"text": " ".join(t["text"] for t in tokens[i:i + hit[1]]), "type": hit[0]})
            i += hit[1]
            continue
        t = tokens[i]
        first_in_sentence = i == 0 or tokens[i - 1]["sentence"] != t["sentence"]
        if t["pos"] in ("NNP", "NNPS") and t["text"][:1].isupper() and not first_in_sentence and not t["is_stop"]:
            ents.append({"text": t["text"], "type": "PROPER_NOUN"})
        i += 1
    return ents


def aspect_details(text):
    """Per-clause aspect evidence. Same rules as nlp.pipeline.aspect_sentiments, plus the clause and trigger words."""
    rows = []
    for clause in _CLAUSE.split(text):
        clause = (clause or "").strip()
        if not clause:
            continue
        hits = {}
        for tok in tokenize(clause):
            a = _aspect_of(tok)
            if a:
                hits.setdefault(a, []).append(tok)
        if hits:
            comp = _vader.polarity_scores(clause)["compound"]
            for a, trig in hits.items():
                rows.append((a, clause, sorted(set(trig)), comp))
    by = {}
    for a, _, _, comp in rows:
        by.setdefault(a, []).append(comp)
    summary = {a: label_from_score(sum(v) / len(v)) for a, v in by.items()}
    details = [{"aspect": a, "clause": c, "triggers": t, "score": round(s, 3), "label": label_from_score(s)} for a, c, t, s in rows]
    return details, summary


def sentiment_view(text, sentences):
    o = _vader.polarity_scores(text)
    return {"overall": {"compound": round(o["compound"], 4), "label": label_from_score(o["compound"]),
                        "positive": o["pos"], "neutral": o["neu"], "negative": o["neg"]},
            "sentences": [{"sentence": s, "compound": round(_vader.polarity_scores(s)["compound"], 3),
                           "label": label_from_score(_vader.polarity_scores(s)["compound"])} for s in sentences]}


def tfidf_top(tfidf, model_text, k=8):
    """Highest-weighted TF-IDF terms of this text under a fitted TfidfVectorizer."""
    X = tfidf.transform([model_text]).tocoo()
    names = tfidf.get_feature_names_out()
    rows = sorted(((names[j], float(v)) for j, v in zip(X.col, X.data)), key=lambda r: -r[1])[:k]
    return [{"term": t, "weight": round(w, 4)} for t, w in rows]


def explain_text(text, tfidf=None):
    text = text.strip()
    sentences, tokens, tagged = analyze_tokens(text)
    phrases, pairs = noun_phrases(tagged)
    details, summary = aspect_details(text)
    core = analyze(text)
    model_text = " ".join(core["lemmas"])
    out = {
        "text": text, "n_chars": len(text), "n_sentences": len(sentences), "sentences": sentences,
        "n_words": sum(not t["is_punct"] for t in tokens), "tokens": tokens,
        "stop_word_count": sum(t["is_stop"] for t in tokens),
        "model_input": {"lemmas": core["lemmas"], "bigrams": core["bigrams"], "trigrams": core["trigrams"], "text": model_text},
        "noun_phrases": phrases, "opinion_pairs": pairs, "entities": find_entities(tokens),
        "aspects": {"details": details, "summary": summary},
        "sentiment": sentiment_view(text, sentences), "tfidf_top": None,
    }
    if tfidf is not None and model_text.strip():
        out["tfidf_top"] = tfidf_top(tfidf, model_text)
    return out
