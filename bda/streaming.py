"""Simulated review stream with sliding-window counters, reservoir sampling and a spike alert.

Educational: it replays REAL stored reviews as if they arrived live, on a virtual clock (one tick = dt seconds),
so the logic is deterministic and testable without sleeping. Nothing here is a real message queue.
"""
import random
from collections import Counter, deque

import numpy as np


class Reservoir:
    """Algorithm R: a uniform random sample of k items from a stream of unknown length, in O(k) memory."""

    def __init__(self, k: int, seed: int = 1):
        self.k, self.n, self.items, self.rng = k, 0, [], random.Random(seed)

    def offer(self, item):
        self.n += 1
        if len(self.items) < self.k:
            self.items.append(item)
        else:
            j = self.rng.randint(0, self.n - 1)
            if j < self.k:
                self.items[j] = item


class SlidingWindow:
    """Counters over the last `seconds` of virtual time, updated incrementally (O(1) per event)."""

    def __init__(self, seconds: int):
        self.seconds, self.q = seconds, deque()
        self.n, self.rating_sum = 0, 0
        self.sent, self.aspects, self.aspects_neg = Counter(), Counter(), Counter()

    def add(self, ts, e):
        self.q.append((ts, e))
        self.n += 1; self.rating_sum += e["rating"]; self.sent[e["sentiment"]] += 1
        for a, label in e["aspects"].items():
            self.aspects[a] += 1
            if label == "negative":
                self.aspects_neg[a] += 1

    def evict(self, now):
        while self.q and self.q[0][0] <= now - self.seconds:
            _, e = self.q.popleft()
            self.n -= 1; self.rating_sum -= e["rating"]; self.sent[e["sentiment"]] -= 1
            for a, label in e["aspects"].items():
                self.aspects[a] -= 1
                if label == "negative":
                    self.aspects_neg[a] -= 1

    def stats(self):
        top = [{"aspect": a, "mentions": c, "negative": self.aspects_neg[a]} for a, c in self.aspects.most_common(6) if c > 0]
        return {"events": self.n, "avg_rating": round(self.rating_sum / self.n, 2) if self.n else None,
                "negative_share": round(self.sent["negative"] / self.n, 4) if self.n else 0.0,
                "sentiment": {k: self.sent[k] for k in ("negative", "neutral", "positive")}, "aspects": top}


class StreamSimulator:
    def __init__(self, pool, rate=20, window=30, seed=7, burst_at=None, burst_len=10, reservoir_k=8):
        if not pool:
            raise ValueError("empty pool")
        self.pool, self.neg = pool, [e for e in pool if e["sentiment"] == "negative"] or pool
        self.rate, self.rng, self.nprng = rate, random.Random(seed), np.random.default_rng(seed)
        self.burst_at, self.burst_len = burst_at, burst_len
        self.win, self.res = SlidingWindow(window), Reservoir(reservoir_k, seed)
        self.now, self.total = 0.0, 0
        self.baseline = sum(e["sentiment"] == "negative" for e in pool) / len(pool)

    def _burst_active(self):
        return self.burst_at is not None and self.burst_at <= self.now < self.burst_at + self.burst_len

    def tick(self, dt=1.0):
        self.now += dt
        burst = self._burst_active()
        n_new = int(self.nprng.poisson(self.rate * dt))
        for _ in range(n_new):
            e = self.rng.choice(self.neg) if (burst and self.rng.random() < 0.7) else self.rng.choice(self.pool)
            self.win.add(self.now, e)
            self.res.offer({"rating": e["rating"], "sentiment": e["sentiment"], "title": e.get("title", ""), "text": e.get("text", "")[:140]})
            self.total += 1
        self.win.evict(self.now)
        w = self.win.stats()
        alert = w["events"] >= 50 and w["negative_share"] >= max(0.25, 2 * self.baseline)
        return {"t": round(self.now, 1), "new_events": n_new, "events_total": self.total, "window_seconds": self.win.seconds,
                "window": w, "baseline_negative_share": round(self.baseline, 4), "burst_active": burst,
                "alert": "Negative spike: share of negative reviews is well above normal" if alert else None,
                "reservoir": list(self.res.items), "reservoir_seen": self.res.n}
