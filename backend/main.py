from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from backend.database.mongo import DatabaseUnavailable
from backend.routes import core, ml, nlp, products

app = FastAPI(title="SmartReview API", version="0.1.0",
              description="AI Product Review Intelligence Platform (BDA + NLP + ML mini-project)")

app.add_middleware(CORSMiddleware, allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
                   allow_methods=["*"], allow_headers=["*"])


@app.exception_handler(DatabaseUnavailable)
async def db_down(_: Request, exc: DatabaseUnavailable):
    return JSONResponse(status_code=503, content={"error": "database_unavailable", "message": str(exc),
                        "hint": "Start MongoDB (docker compose up mongo) and retry."})


@app.exception_handler(Exception)
async def unhandled(_: Request, exc: Exception):
    return JSONResponse(status_code=500, content={"error": "internal_error", "message": str(exc)})


app.include_router(core.router, prefix="/api")
app.include_router(ml.router, prefix="/api")
app.include_router(products.router, prefix="/api")
app.include_router(nlp.router, prefix="/api")
