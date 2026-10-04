"""One-time download of the NLTK data the pipeline needs.  python -m scripts.setup_nltk"""
import nltk

for pkg in ("wordnet", "omw-1.4", "averaged_perceptron_tagger_eng", "stopwords", "punkt_tab"):
    print(f"{pkg:34s}", "ok" if nltk.download(pkg, quiet=True) else "FAILED")
