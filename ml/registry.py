"""Model registry: joblib files under /models plus a small JSON manifest. Cached by file mtime."""
import json
import os
from pathlib import Path

import joblib

MODELS_DIR = Path(os.getenv("MODELS_DIR", Path(__file__).resolve().parent.parent / "models"))
_cache = {}


def save(name: str, pipe, meta: dict | None = None):
    MODELS_DIR.mkdir(parents=True, exist_ok=True)
    joblib.dump(pipe, MODELS_DIR / f"{name}.joblib", compress=3)
    if meta is not None:
        (MODELS_DIR / "manifest.json").write_text(json.dumps(meta, indent=2))


def manifest():
    p = MODELS_DIR / "manifest.json"
    return json.loads(p.read_text()) if p.exists() else None


def load(name: str):
    """Returns the fitted pipeline, or None if that model was never saved."""
    p = MODELS_DIR / f"{name}.joblib"
    if not p.exists():
        return None
    key = (str(p), p.stat().st_mtime_ns)
    if key not in _cache:
        _cache.clear()
        _cache[key] = joblib.load(p)
    return _cache[key]
