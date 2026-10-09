# MongoDB schema

```
reviews                         products                    users
-------                         --------                    -----
review_id (unique)              product_id (unique)         user_id (unique)
product_id  ---------------->   name                        review_count
product_name                    category                     avg_rating
category                        launch_date
user_id ---------------------------------------------->
rating (1-5)                    analytics                   model_results
review_text                     ---------                   -------------
review_date (ISODate)           main_category
                                amazon_avg_rating,
                                amazon_rating_number
key  (e.g. "aspect_counts")  model_name
verified_purchase               scope (global | product_id) metrics {accuracy,...}
helpful_votes                   data  {...}                 confusion_matrix
-- added by NLP --              computed_at                 cv_scores[]
sentiment                       job   (mapreduce/manual)    trained_at
sentiment_score                                              n_train / n_test
tokens[] lemmas[]                                            dataset_size
bigrams[] trigrams[] keywords[]
aspects[]
aspect_sentiments { aspect: label }
```

## Indexes
```js
db.reviews.createIndex({ review_id: 1 }, { unique: true })
db.reviews.createIndex({ product_id: 1, review_date: 1 })
db.reviews.createIndex({ sentiment: 1 })
db.reviews.createIndex({ aspects: 1 })
db.analytics.createIndex({ key: 1, scope: 1 }, { unique: true })
```

## Sample queries
```js
// negative reviews for a product mentioning battery
db.reviews.find({ product_id: "P001", "aspect_sentiments.battery": "negative" })

// sentiment counts per product
db.reviews.aggregate([{ $group: { _id: { p: "$product_id", s: "$sentiment" }, n: { $sum: 1 } } }])

// monthly negative battery share
db.reviews.aggregate([
  { $match: { aspects: "battery" } },
  { $group: { _id: { $dateToString: { format: "%Y-%m", date: "$review_date" } },
              neg: { $sum: { $cond: [{ $eq: ["$aspect_sentiments.battery", "negative"] }, 1, 0] } },
              total: { $sum: 1 } } },
  { $sort: { _id: 1 } }
])
```

## Amazon 2023 field mapping (Phase 2)
| Raw field | SmartReview field | Note |
|---|---|---|
| `parent_asin` | `product_id` | `asin` (colour/size variant) kept as `asin`; metadata is keyed by parent |
| `text`, `title` | `review_text`, `title`, `full_text` | `full_text` = title + text, what NLP reads; HTML stripped |
| `timestamp` (epoch ms) | `review_date` | UTC; rows outside 1996-2023 rejected |
| `helpful_vote` | `helpful_votes` | |
| `images[]` | `image_count` | image URLs not stored |
| (none) | `review_id` | sha1(user_id\|product_id\|timestamp)[:20] |
| `rating` | `rating`, `sentiment` | label from stars: <=2 neg, 3 neu, >=4 pos (weak label) |
| NLP | `sentiment_score` | VADER compound on text, -1..1; independent of the star label |
`users.review_count / avg_rating` describe the loaded subset, not lifetime Amazon activity.

## analytics documents (Phase 4, written by `scripts/compute_analytics.py`)
| key | scope | data |
|---|---|---|
| `product_health` | product_id | n_reviews, avg_rating, positive_ratio, rating_histogram, aspects{mentions, positive/neutral/negative, positive_ratio}, weakest_aspect, trend{status, recent, prior, drop, z, series[]}, health{score, penalty, components}. Only products with >=5 reviews. |
| `global_summary` | global | aspects[] (portfolio counts), trend[] (quarterly), total_reviews |
| `nlp_corpus` | global | vocab stats, zipf{points, slope, r2}, distinctive_unigrams/bigrams per class, collocations, top_keywords, topics[], lsa info (written by `scripts/compute_nlp_stats.py`; word vectors saved to `models/lsa_words.joblib`) |
