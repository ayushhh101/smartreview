"""Run the BDA benchmark on your reviews and cache it for the BDA Lab page.   python -m scripts.run_benchmark  (about 1-2 minutes)"""
import datetime as dt

from backend.database.mongo import require_db
from bda.benchmark import run_benchmark

if __name__ == "__main__":
    db = require_db()
    res = run_benchmark(db, [10_000, 50_000, 100_000])
    db.analytics.delete_many({"key": "bda_benchmark"})
    db.analytics.insert_one({"key": "bda_benchmark", "scope": "global", "job": "run_benchmark",
                             "computed_at": dt.datetime.now(dt.timezone.utc), "data": res})
    print("saved. Open BDA Lab in the app.")
