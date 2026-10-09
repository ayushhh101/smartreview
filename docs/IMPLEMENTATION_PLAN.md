# SmartReview — Implementation Plan

SmartReview is a review-intelligence platform built to demonstrate BDA, NLP and ML in one product.
Priority order: correctness > simplicity > academic value > UI polish > extras.

## 1. Architecture
See `architecture.md`. React (Vite) -> FastAPI -> {NLP engine, ML engine, BDA engine} -> MongoDB + model registry (`/models`, joblib files).
Every module is a plain Python package importable without the web server, so each can be demoed from a script or notebook.

## 2. Data flow
1. **Real data, not synthetic** (changed in Phase 2): Amazon Reviews 2023, Musical Instruments category (McAuley Lab, UCSD). `scripts/profile_dataset.py` profiles the raw file; `scripts/make_subset.py` draws a seeded random sample (`data/reviews_<N>.jsonl`).
2. `scripts/seed_database.py` validates (`ingestion/amazon.py`), runs the NLP pipeline, and idempotently writes `reviews`, `products` (from `meta_*.jsonl`), `users` to MongoDB.
3. `train_models.py` fits TF-IDF + 4 classifiers with stratified K-fold, stores metrics in `model_results` and the best model in `/models`.
4. BDA engine runs MapReduce-style jobs over `reviews` and caches aggregates in `analytics`.
5. API serves dashboards from `analytics` and live queries from `reviews`. Nothing in the UI is hardcoded.

## 3. Database schema (MongoDB)
Full field list in `database_schema.md`. Collections: `reviews`, `products`, `users`, `analytics`, `model_results`.
Indexes: `reviews.review_id` (unique), `(product_id, review_date)`, `sentiment`, `aspects`.

## 4. NLP pipeline
clean -> tokenize -> lowercase -> stopword removal -> stem / lemmatize -> POS tag -> n-grams -> TF-IDF -> aspect extraction -> sentiment.
Aspect extraction: aspect lexicon (seed terms per aspect) matched on lemmas, then sentiment is scored on the clause window around each aspect term.
Sentiment labels for training: derived from star rating (<=2 negative, 3 neutral, >=4 positive). Limitation documented: labels are rating-derived, not human-annotated.

## 5. ML pipeline
TF-IDF (unigram+bigram) -> LogReg / Decision Tree / Random Forest / Linear SVM.
Stratified 5-fold CV, hold-out test set, accuracy / macro precision / recall / F1, confusion matrix, one-vs-rest ROC-AUC.
K-Means on TF-IDF (user-chosen k, top terms per cluster computed from centroids). PCA via TruncatedSVD-free `PCA` on a sampled dense matrix, explained variance shown.
Explainability: LogReg coefficients x TF-IDF values per review.

## 6. BDA pipeline
- MapReduce simulation (`bda/mapreduce.py`): explicit map, shuffle/group, reduce phases, trace exposed to the UI. Labelled "Educational MapReduce Simulation".
- Streaming (`bda/streaming.py`): simulated generator + WebSocket, sliding-window counters, reservoir sampling.
- Bloom filter and Flajolet-Martin demos: educational, labelled as such.
- Recommendations: content-based cosine similarity over product feature vectors.
- Benchmark: naive loop vs MapReduce-style, real timings at 10k / 50k / 100k.

## 7. API surface (prefix `/api`)
| Area | Endpoints |
|---|---|
| Core | `GET /health`, `GET /stats/overview` |
| Products | `GET /products`, `GET /products/{id}` (health, aspects, trend) |
| Reviews | `GET /reviews`, `GET /reviews/search?q=` |
| NLP | `POST /nlp/analyze` |
| ML | `GET /ml/model-comparison`, `POST /ml/predict`, `POST /ml/explain`, `GET /ml/clusters?k=`, `GET /ml/pca` |
| BDA | `POST /bda/mapreduce/{job}`, `GET /bda/bloom`, `GET /bda/distinct`, `GET /bda/benchmark`, `WS /bda/stream` |
| Other | `GET /recommendations/{product_id}`, `POST /ask`, `POST /ingest/csv` |

## 8. Frontend pages
Dashboard, Products (+ detail), Reviews, NLP Explorer, ML Lab, BDA Lab, Streaming, Recommendations, Ask SmartReview, Academic Mapping, About, plus Demo Mode overlay.
Every page has loading, empty and error states.

## 9. Phases
1. Setup, backend skeleton, MongoDB connection, dashboard shell  (done)
2. Real-data ingestion (Amazon 2023), profiling, NLP pipeline  (done)
3. ML training, evaluation, model comparison  (done)
4. Aspect sentiment, health score, trends  (done)
5. BDA: MapReduce, NoSQL queries, streaming, Bloom, distinct count, benchmark
6. Clustering, PCA, recommendations, search
7. Academic mapping, report, viva, demo mode

## 9b. NLP Lab pack (added after Phase 4)
NLP Explorer page: step-by-step analysis of any text (`nlp/analysis.py`) and corpus insights (`nlp/corpus.py`,
`scripts/compute_nlp_stats.py`): vocabulary reduction, Zipf's law, log-odds distinctive words, PMI collocations,
NMF topics, LSA word vectors. Dictionary NER for brands, instruments and gear. Honest limits: lexicon-based aspects,
LSA is not Word2Vec, topics are unlabeled.

## 10. Testing strategy
- pytest for each pure module (tokenizer, aspect extractor, mapreduce vs naive equality, bloom no-false-negative).
- API tests with FastAPI TestClient against a test database.
- Metrics are only ever read from `model_results`; a test asserts the endpoint returns 404-style "not trained" when empty.
- Frontend: `npm run build` must pass at the end of each phase.

## 11. Health score formula (fixed now, implemented in Phase 4)
`Health = 100 * (0.40*aspect_mean_positive_ratio + 0.30*overall_positive_ratio + 0.30*(avg_rating-1)/4)`
minus a capped penalty of up to 10 points for an emerging negative trend.
Implementation details (Phase 4): aspects with <3 mentions are ignored; if none qualify the aspect term is dropped and the other weights renormalised. "Emerging negative" = positive share in the latest 12 months is >=10 points below the previous 12 months, both windows have >=15 reviews, and a one-sided two-proportion z-test passes at 95%; penalty = min(10, 50 x drop). Windows are measured back from each product's own last review. Labelled "SmartReview Composite Health Score"; a heuristic, not a validated metric.
