"""Sentiment-classifier training and evaluation. Pure functions: no Mongo, no FastAPI.

Target     3 classes from star rating (<=2 negative, 3 neutral, >=4 positive). Weak labels.
Features   TF-IDF (1-2 grams) over the NLP pipeline's lemmas, fitted INSIDE each CV fold.
Split      GROUP split by product_id, so test products are never seen in training (a review of a
           product the model has already seen would flatter it). Cross-validation is grouped too.
Imbalance  ~67% of reviews are 5-star. All models use class_weight="balanced" and the primary
           metric is macro-F1. A majority-class baseline is reported next to every model.
Selection  best model = highest mean CV macro-F1 on the TRAIN split. Test set is only reported.
"""
import time

import numpy as np
from sklearn.dummy import DummyClassifier
from sklearn.ensemble import RandomForestClassifier
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import (accuracy_score, confusion_matrix, precision_recall_fscore_support,
                             roc_auc_score)
from sklearn.model_selection import GroupShuffleSplit, StratifiedGroupKFold, cross_val_score
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import label_binarize
from sklearn.svm import LinearSVC
from sklearn.tree import DecisionTreeClassifier

LABELS = ["negative", "neutral", "positive"]
SEED = 42


def make_tfidf(max_features=30_000):
    return TfidfVectorizer(ngram_range=(1, 2), min_df=3, max_df=0.9, max_features=max_features,
                           sublinear_tf=True, token_pattern=r"(?u)\b[\w']+\b")


def make_models():
    cw = "balanced"
    return {
        "logistic_regression": LogisticRegression(C=2.0, class_weight=cw, max_iter=1000),
        "linear_svm": LinearSVC(C=0.3, class_weight=cw),
        "decision_tree": DecisionTreeClassifier(max_depth=40, min_samples_leaf=5, class_weight=cw,
                                                random_state=SEED),
        "random_forest": RandomForestClassifier(n_estimators=150, min_samples_leaf=2, class_weight=cw,
                                                n_jobs=-1, random_state=SEED),
    }


def pipeline(clf, max_features=30_000):
    return Pipeline([("tfidf", make_tfidf(max_features)), ("clf", clf)])


def group_split(y, groups, test_size=0.2, seed=SEED):
    """Indices (train, test) with no product in both."""
    gss = GroupShuffleSplit(n_splits=1, test_size=test_size, random_state=seed)
    return next(gss.split(np.zeros(len(y)), y, groups))


def _scores(model, X):
    """Per-class scores for AUC: probabilities if available, else decision_function."""
    return model.predict_proba(X) if hasattr(model, "predict_proba") else model.decision_function(X)


def evaluate(model, X_test, y_test):
    """All test-set metrics for a fitted pipeline."""
    pred = model.predict(X_test)
    p, r, f, s = precision_recall_fscore_support(y_test, pred, labels=LABELS, zero_division=0)
    macro = precision_recall_fscore_support(y_test, pred, labels=LABELS, average="macro", zero_division=0)
    scores = _scores(model, X_test)
    order = [list(model.classes_).index(l) for l in LABELS]
    scores = scores[:, order]
    Y = label_binarize(y_test, classes=LABELS)
    auc = {}
    for i, l in enumerate(LABELS):                 # one-vs-rest; skipped if a class is absent from test
        if Y[:, i].min() != Y[:, i].max():
            auc[l] = round(float(roc_auc_score(Y[:, i], scores[:, i])), 4)
    return {
        "accuracy": round(float(accuracy_score(y_test, pred)), 4),
        "macro_precision": round(float(macro[0]), 4),
        "macro_recall": round(float(macro[1]), 4),
        "macro_f1": round(float(macro[2]), 4),
        "per_class": {l: {"precision": round(float(p[i]), 4), "recall": round(float(r[i]), 4),
                          "f1": round(float(f[i]), 4), "support": int(s[i])} for i, l in enumerate(LABELS)},
        "roc_auc_ovr": {**auc, "macro": round(float(np.mean(list(auc.values()))), 4) if auc else None},
    }, confusion_matrix(y_test, pred, labels=LABELS).tolist()


def run_experiment(texts, labels, groups, models=None, cv_folds=5, test_size=0.2, max_features=30_000,
                   log=print):
    """Train + evaluate every model. Returns (results_list, fitted_pipelines_by_name, info)."""
    texts, y, groups = np.asarray(texts, dtype=object), np.asarray(labels), np.asarray(groups)
    tr, te = group_split(y, groups, test_size)
    Xtr, Xte, ytr, yte, gtr = texts[tr], texts[te], y[tr], y[te], groups[tr]
    info = {"dataset_size": int(len(y)), "n_train": int(len(tr)), "n_test": int(len(te)),
            "n_train_products": int(len(set(gtr))), "n_test_products": int(len(set(groups[te]))),
            "class_distribution": {l: int((y == l).sum()) for l in LABELS},
            "cv_folds": cv_folds, "tfidf_max_features": max_features}
    models = models or make_models()

    # majority-class baseline: what "predicting positive for everything" scores
    base = pipeline(DummyClassifier(strategy="most_frequent"), 1000).fit(Xtr, ytr)
    base_m, _ = evaluate_dummy(base, Xte, yte)
    info["baseline"] = base_m

    cv = StratifiedGroupKFold(n_splits=cv_folds, shuffle=True, random_state=SEED)
    results, fitted = [], {}
    for name, clf in models.items():
        t0 = time.time()
        pipe = pipeline(clf, max_features)
        log(f"[{name}] cross-validating ({cv_folds} folds)...")
        cvs = cross_val_score(pipe, Xtr, ytr, groups=gtr, cv=cv, scoring="f1_macro")
        log(f"[{name}] fitting on full train split...")
        pipe.fit(Xtr, ytr)
        t_fit = time.time() - t0
        metrics, cm = evaluate(pipe, Xte, yte)
        results.append({"model_name": name, "metrics": metrics, "confusion_matrix": cm,
                        "labels": LABELS, "cv_scores": [round(float(s), 4) for s in cvs],
                        "cv_mean_f1": round(float(cvs.mean()), 4), "cv_std_f1": round(float(cvs.std()), 4),
                        "train_seconds": round(t_fit, 1), **{k: info[k] for k in
                        ("n_train", "n_test", "dataset_size")}})
        fitted[name] = pipe
        log(f"[{name}] cv macro-F1 {cvs.mean():.3f}  test macro-F1 {metrics['macro_f1']:.3f}  ({t_fit:.0f}s)")
    best = max(results, key=lambda r: r["cv_mean_f1"])["model_name"]
    for r in results:
        r["is_best"] = r["model_name"] == best
    return results, fitted, info


def evaluate_dummy(model, X_test, y_test):
    pred = model.predict(X_test)
    m = precision_recall_fscore_support(y_test, pred, labels=LABELS, average="macro", zero_division=0)
    return {"strategy": "always predict the most common class", "accuracy": round(float(accuracy_score(y_test, pred)), 4),
            "macro_f1": round(float(m[2]), 4)}, None


def explain(pipe, text, top_n=8):
    """Linear-model explanation: which terms pushed the prediction toward its class.
    contribution = tfidf value x class coefficient. Only valid for linear models."""
    clf = pipe.named_steps["clf"]
    if not hasattr(clf, "coef_"):
        raise ValueError("Explanation needs a linear model (logistic regression or linear SVM).")
    X = pipe.named_steps["tfidf"].transform([text])
    pred = pipe.predict([text])[0]
    ci = list(clf.classes_).index(pred)
    names = pipe.named_steps["tfidf"].get_feature_names_out()
    row = X.tocoo()
    contrib = [(names[j], float(v * clf.coef_[ci][j])) for j, v in zip(row.col, row.data)]
    contrib.sort(key=lambda t: t[1])
    return {"predicted": pred,
            "supporting": [{"term": t, "weight": round(w, 4)} for t, w in contrib[::-1][:top_n] if w > 0],
            "opposing": [{"term": t, "weight": round(w, 4)} for t, w in contrib[:top_n] if w < 0]}
