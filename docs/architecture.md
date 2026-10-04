# Architecture

```
            +------------------------------+
            |   React + Vite + Tailwind    |
            |   Dashboard, Labs, Streaming |
            +--------------+---------------+
                           | REST / WebSocket
            +--------------v---------------+
            |        FastAPI backend       |
            |  routes/  ->  services/      |
            +------+-------+-------+-------+
                   |       |       |
          +--------v--+ +--v-----+ +v---------+
          | NLP engine| |ML engine| |BDA engine|
          | nlp/      | | ml/     | | bda/     |
          +--------+--+ +--+------+ +-+--------+
                   |       |          |
                   |  +----v----+     |
                   |  | models/ |     |
                   |  | (joblib)|     |
                   |  +---------+     |
              +----v-----------------v----+
              |         MongoDB           |
              | reviews products users    |
              | analytics model_results   |
              +---------------------------+
```

## Module responsibilities
| Package | Responsibility | Subject |
|---|---|---|
| `nlp/` | cleaning, tokens, lemmas, POS, n-grams, aspects, lexicon sentiment | NLP |
| `ml/` | TF-IDF features, classifiers, evaluation, K-Means, PCA, explainability | ML |
| `bda/` | MapReduce simulation, streaming, Bloom filter, distinct count, recommender | BDA |
| `backend/` | HTTP layer, orchestration, Mongo access | glue |

## Why these choices
- **MongoDB**: reviews are semi-structured (variable aspect lists, nested aspect sentiments), so documents fit better than fixed tables.
- **MapReduce simulation**: a single-process implementation of the map / shuffle / reduce model. It is not Hadoop and is labelled as such everywhere.
- **No LLM**: Ask SmartReview uses intent matching plus MongoDB aggregation so each answer is traceable to data.
