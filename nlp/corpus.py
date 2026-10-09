"""Corpus-level NLP analysis. Pure functions over counters / document lists (no Mongo).

  vocab_stats        vocabulary size, type-token ratio, hapax legomena, effect of stop-word removal + lemmatisation
  zipf_points        rank-frequency data and fitted slope (Zipf's law: slope close to -1)
  log_odds_dirichlet distinctive words per class (Monroe et al. 2008, log-odds with informative Dirichlet prior)
  pmi_collocations   word pairs that occur together more often than chance (pointwise mutual information)
  topic_model        NMF topics on TF-IDF, with each topic's share, average rating and negative share
  lsa_word_vectors   word vectors from TruncatedSVD (Latent Semantic Analysis); nearest() finds similar words
Honesty: LSA is classic distributional semantics, not Word2Vec; topics are unsupervised and need human labels.
"""
import math

import numpy as np
from sklearn.decomposition import NMF, TruncatedSVD
from sklearn.feature_extraction.text import TfidfVectorizer

_TOKEN_PATTERN = r"(?u)\b[a-z][a-z']+\b"


def vocab_stats(raw_counts, lemma_counts, n_reviews):
    raw_total, lem_total = sum(raw_counts.values()), sum(lemma_counts.values())
    v_raw, v_lem = len(raw_counts), len(lemma_counts)
    hapax = sum(1 for c in raw_counts.values() if c == 1)
    return {
        "n_reviews": n_reviews, "tokens_total": raw_total, "vocab_raw": v_raw, "vocab_lemma": v_lem,
        "vocab_reduction_pct": round(100 * (1 - v_lem / v_raw), 1) if v_raw else None,
        "tokens_after_stopwords": lem_total,
        "tokens_removed_pct": round(100 * (1 - lem_total / raw_total), 1) if raw_total else None,
        "type_token_ratio": round(v_raw / raw_total, 4) if raw_total else None,
        "hapax_count": hapax, "hapax_pct_of_vocab": round(100 * hapax / v_raw, 1) if v_raw else None,
        "avg_tokens_per_review": round(raw_total / n_reviews, 1) if n_reviews else None,
    }


def zipf_points(counts, n_points=60, fit_max_rank=2000):
    freqs = sorted(counts.values(), reverse=True)
    if len(freqs) < 20:
        return {"points": [], "slope": None, "r2": None}
    ranks = sorted({int(round(x)) for x in np.logspace(0, math.log10(len(freqs)), n_points)})
    pts = [{"rank": r, "freq": freqs[r - 1]} for r in ranks]
    m = min(fit_max_rank, len(freqs))
    x, y = np.log10(np.arange(1, m + 1)), np.log10(np.array(freqs[:m], dtype=float))
    slope, icpt = np.polyfit(x, y, 1)
    pred = slope * x + icpt
    r2 = 1 - ((y - pred) ** 2).sum() / ((y - y.mean()) ** 2).sum()
    return {"points": pts, "slope": round(float(slope), 3), "r2": round(float(r2), 3)}


def log_odds_dirichlet(c_target, c_other, prior, a0=500.0, min_count=20, top=15):
    n_i, n_j, n_p = sum(c_target.values()), sum(c_other.values()), sum(prior.values())
    rows = []
    for w, pc in prior.items():
        yi, yj = c_target.get(w, 0), c_other.get(w, 0)
        if yi + yj < min_count:
            continue
        aw = a0 * pc / n_p
        delta = math.log((yi + aw) / (n_i + a0 - yi - aw)) - math.log((yj + aw) / (n_j + a0 - yj - aw))
        rows.append((delta / math.sqrt(1 / (yi + aw) + 1 / (yj + aw)), w, yi, yj))
    rows.sort(reverse=True)
    return [{"term": w, "z": round(z, 2), "count": yi, "count_other": yj} for z, w, yi, yj in rows[:top]]


def distinctive_by_class(counts_by_class, top=12, min_count=20):
    total = sum(counts_by_class.values(), type(next(iter(counts_by_class.values())))())
    out = {}
    for cls, c in counts_by_class.items():
        rest = total.copy()
        rest.subtract(c)
        rest = {k: v for k, v in rest.items() if v > 0}
        out[cls] = log_odds_dirichlet(c, rest, total, min_count=min_count, top=top)
    return out


def pmi_collocations(bigram_counts, unigram_counts, min_count=40, top=20):
    n2, n1 = sum(bigram_counts.values()), sum(unigram_counts.values())
    rows = []
    for bg, c in bigram_counts.items():
        if c < min_count:
            continue
        w1, _, w2 = bg.partition(" ")
        u1, u2 = unigram_counts.get(w1, 0), unigram_counts.get(w2, 0)
        if not u1 or not u2 or w1 == w2:
            continue
        rows.append((math.log2((c / n2) / ((u1 / n1) * (u2 / n1))), bg, c))
    rows.sort(reverse=True)
    return [{"bigram": b, "pmi": round(p, 2), "count": c} for p, b, c in rows[:top]]


def topic_model(docs, ratings, sentiments, n_topics=8, top_words=10, seed=42):
    """docs: lemma strings. Returns one dict per topic, largest first."""
    tf = TfidfVectorizer(max_features=5000, min_df=10, max_df=0.4, token_pattern=_TOKEN_PATTERN)
    X = tf.fit_transform(docs)
    nmf = NMF(n_components=n_topics, init="nndsvda", random_state=seed, max_iter=300)
    W = nmf.fit_transform(X)
    names = tf.get_feature_names_out()
    has = W.sum(axis=1) > 0
    dom = W.argmax(axis=1)
    ratings, sentiments = np.asarray(ratings), np.asarray(sentiments)
    out = []
    for k in range(n_topics):
        mask = has & (dom == k)
        n = int(mask.sum())
        out.append({"topic": k + 1, "top_words": [names[i] for i in nmf.components_[k].argsort()[::-1][:top_words]],
                    "n_reviews": n, "share": round(n / max(int(has.sum()), 1), 4),
                    "avg_rating": round(float(ratings[mask].mean()), 2) if n else None,
                    "negative_share": round(float((sentiments[mask] == "negative").mean()), 4) if n else None})
    out.sort(key=lambda t: -t["n_reviews"])
    return out


def lsa_word_vectors(docs, dim=100, max_features=8000, seed=42):
    tf = TfidfVectorizer(max_features=max_features, min_df=15, sublinear_tf=True, token_pattern=_TOKEN_PATTERN)
    X = tf.fit_transform(docs)
    dim = min(dim, X.shape[1] - 1, X.shape[0] - 1)
    svd = TruncatedSVD(n_components=dim, random_state=seed).fit(X)
    vecs = svd.components_.T * svd.singular_values_
    vecs = vecs / np.maximum(np.linalg.norm(vecs, axis=1, keepdims=True), 1e-12)
    return {"vocab": list(tf.get_feature_names_out()), "vectors": vecs.astype(np.float32), "dim": int(dim),
            "explained_variance": round(float(svd.explained_variance_ratio_.sum()), 4)}


def nearest(model, word, k=8):
    """Cosine nearest neighbours. Returns None if the word is not in the vocabulary."""
    idx = {w: i for i, w in enumerate(model["vocab"])}
    if word not in idx:
        return None
    sims = model["vectors"] @ model["vectors"][idx[word]]
    order = np.argsort(-sims)
    return [{"word": model["vocab"][i], "similarity": round(float(sims[i]), 3)} for i in order if i != idx[word]][:k]
