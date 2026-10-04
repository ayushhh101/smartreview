# SmartReview — AI Product Review Intelligence Platform

BDA + NLP + ML mini-project. Status: **Phase 3 of 7 complete** (real-data ingestion, NLP pipeline, ML training + ML Lab page). Dataset: Amazon Reviews 2023 - Musical Instruments (McAuley Lab, UCSD).
Plan: `docs/IMPLEMENTATION_PLAN.md` · Architecture: `docs/architecture.md` · Schema: `docs/database_schema.md`

## Run (without Docker)
```bash
# 1. MongoDB (pick one)
docker run -d -p 27017:27017 --name smartreview-mongo mongo:7
# or install MongoDB Community locally and start mongod

# 2. Backend (from project root)
python -m venv .venv && source .venv/bin/activate      # Windows: .venv\Scripts\activate
pip install -r requirements.txt
uvicorn backend.main:app --reload --port 8000

# 3. Frontend (new terminal)
cd frontend && npm install && npm run dev               # http://localhost:5173
```

## Run (Docker)
```bash
docker compose up --build
```

## Phase 2: load the real data
Download `Musical_Instruments.jsonl(.gz)` (reviews) and `meta_Musical_Instruments.jsonl(.gz)` (product names) into `data/`.
```bash
python -m scripts.setup_nltk                                    # once
python -m scripts.profile_dataset data/Musical_Instruments.jsonl   # data-quality report -> data/profile.json
python -m scripts.make_subset data/Musical_Instruments.jsonl --n 100000
python -m scripts.seed_database data/reviews_100000.jsonl --meta data/meta_Musical_Instruments.jsonl
```
Start with `--n 10000` to check everything works (~20 s), then go bigger. Re-running seed never duplicates rows.

## Phase 3: train the models
```bash
python -m scripts.train_models --max-docs 20000 --folds 3    # quick run first
python -m scripts.train_models                               # all loaded reviews, 5-fold CV
```
Outputs: `models/` (best model + logistic regression), `model_results` collection, ML Lab page at `/ml`.
If products/users are empty after a seed that crashed on `--meta`, run
`python -m scripts.seed_database --derived-only --meta data/meta_Musical_Instruments.jsonl`.

## Tests
```bash
python -m pytest backend/tests_phase1.py backend/tests_phase2.py backend/tests_phase3.py -q
```

## Phase 1 status
Working: `GET /api/health`, `GET /api/stats/overview`, dashboard with loading / error / empty states.
Phase 2 adds: `ingestion/`, `nlp/` (tokens, lemmas, POS, n-grams, aspects, VADER), and the `scripts/`. Not built yet: phases 3-7. Pages for those features are labelled placeholders, and the dashboard shows no numbers until real data is loaded.
