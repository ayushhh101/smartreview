"""Probabilistic data structures: Bloom filter (membership) and Flajolet-Martin (distinct count).
Educational implementations; both trade exactness for tiny, fixed memory."""
import hashlib
import math

import numpy as np


class BloomFilter:
    """Set membership with no false negatives and a tunable false-positive rate."""

    def __init__(self, n_expected: int, error_rate: float = 0.01):
        self.n_expected, self.error_rate = n_expected, error_rate
        self.m = max(8, math.ceil(-n_expected * math.log(error_rate) / (math.log(2) ** 2)))
        self.k = max(1, round(self.m / n_expected * math.log(2)))
        self.bits = bytearray((self.m + 7) // 8)
        self.count = 0

    def _indexes(self, item: str):
        d = hashlib.blake2b(item.encode(), digest_size=16).digest()
        h1, h2 = int.from_bytes(d[:8], "little"), int.from_bytes(d[8:], "little") | 1
        return [(h1 + i * h2) % self.m for i in range(self.k)]          # double hashing

    def add(self, item: str):
        for i in self._indexes(item):
            self.bits[i >> 3] |= 1 << (i & 7)
        self.count += 1

    def __contains__(self, item: str) -> bool:
        return all(self.bits[i >> 3] & (1 << (i & 7)) for i in self._indexes(item))

    @property
    def fill_ratio(self) -> float:
        return sum(bin(b).count("1") for b in self.bits) / self.m

    @property
    def theoretical_fp(self) -> float:
        return (1 - math.exp(-self.k * self.count / self.m)) ** self.k


_M = np.uint64(0xFFFFFFFFFFFFFFFF)
_PHI = 0.77351


def _splitmix(x):
    """SplitMix64 finaliser on a uint64 array (wraps modulo 2**64)."""
    z = x + np.uint64(0x9E3779B97F4A7C15)
    z = (z ^ (z >> np.uint64(30))) * np.uint64(0xBF58476D1CE4E5B9)
    z = (z ^ (z >> np.uint64(27))) * np.uint64(0x94D049BB133111EB)
    return z ^ (z >> np.uint64(31))


def _trailing_zeros(x):
    low = x & (~x + np.uint64(1))
    tz = np.log2(np.where(x == 0, np.uint64(1), low).astype(np.float64)).astype(np.int64)
    return np.where(x == 0, 64, tz)


class FlajoletMartin:
    """Flajolet-Martin distinct count. For each hash function keep a bitmap of which trailing-zero counts were
    seen; the lowest bit still unset (R) estimates log2(distinct). Averaging R over many hash functions gives
    estimate = 2^mean(R) / 0.77351 with a typical error of about 10%."""

    def __init__(self, n_hashes: int = 64, seed: int = 1):
        rng = np.random.default_rng(seed)
        self.seeds = rng.integers(1, 2**63, size=n_hashes, dtype=np.uint64)
        self.seen = np.zeros((n_hashes, 65), dtype=bool)

    def add_many(self, items, chunk=20_000):
        items = list(items)
        for i in range(0, len(items), chunk):
            base = np.fromiter((int.from_bytes(hashlib.blake2b(s.encode(), digest_size=8).digest(), "little")
                                for s in items[i:i + chunk]), dtype=np.uint64)
            for j, seed in enumerate(self.seeds):
                self.seen[j, np.unique(_trailing_zeros(_splitmix(base ^ seed)))] = True

    def estimate(self) -> int:
        r = np.array([int(np.argmin(row)) if not row.all() else 65 for row in self.seen])    # lowest unset bit
        return int(round(2 ** float(r.mean()) / _PHI))
