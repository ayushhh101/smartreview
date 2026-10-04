from fastapi import APIRouter
from backend.database.mongo import ping, DB_NAME
from backend.services.overview import overview

router = APIRouter()


@router.get("/health")
def health():
    ok, err = ping()
    return {"api": "ok", "mongodb": "up" if ok else "down", "database": DB_NAME, "error": err}


@router.get("/stats/overview")
def stats_overview():
    return overview()
