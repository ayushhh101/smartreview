"""Educational MapReduce simulation: explicit map -> combine -> shuffle -> reduce phases with a trace.

Runs in ONE Python process (no cluster, no HDFS). What it keeps from real MapReduce:
- input is cut into splits, each handled by one 'mapper'
- mappers emit (key, value) pairs; an optional combiner merges pairs locally before they cross the 'network'
- the shuffle partitions pairs to reducers by hash(key) and groups values per key
- each reducer sees all values of a key and emits one result
Partitioning uses crc32 (stable across runs; Python's built-in hash() of strings changes per process).
"""
import time
import zlib
from collections import defaultdict

LABEL = "Educational MapReduce Simulation: single Python process, no cluster"


def partition(key, n_reducers: int) -> int:
    return zlib.crc32(str(key).encode()) % n_reducers


def run_job(records, mapper, reducer, combiner=None, describe=None, n_mappers=4, n_reducers=3, sample=3):
    """Returns (result dict key -> value, trace dict). `records` is a list so it can be split."""
    describe = describe or (lambda r: str(r)[:100])
    splits = [records[i::n_mappers] for i in range(n_mappers)]
    emitted, map_samples, mapped = 0, [], []
    t_map = t_comb = 0.0
    for si, split in enumerate(splits):
        t0 = time.perf_counter()
        local = defaultdict(list)
        for rec in split:
            pairs = list(mapper(rec))
            emitted += len(pairs)
            if si == 0 and len(map_samples) < sample and pairs:
                map_samples.append({"record": describe(rec), "pairs": [[str(k), _show(v)] for k, v in pairs[:6]]})
            for k, v in pairs:
                local[k].append(v)
        t_map += time.perf_counter() - t0
        if combiner:
            t0 = time.perf_counter()
            local = {k: [combiner(k, vs)] for k, vs in local.items()}
            t_comb += time.perf_counter() - t0
        mapped.append(local)
    after_combine = sum(len(vs) for local in mapped for vs in local.values())

    t0 = time.perf_counter()
    parts = [defaultdict(list) for _ in range(n_reducers)]
    for local in mapped:
        for k, vs in local.items():
            parts[partition(k, n_reducers)][k].extend(vs)
    t_shuffle = time.perf_counter() - t0
    biggest = sorted(((k, vs) for p in parts for k, vs in p.items()), key=lambda kv: -len(kv[1]))[:sample]
    shuffle_sample = [{"key": str(k), "n_values": len(vs), "values": [_show(v) for v in vs[:5]]} for k, vs in biggest]

    t0 = time.perf_counter()
    result = {}
    for p in parts:
        for k, vs in p.items():
            result[k] = reducer(k, vs)
    t_reduce = time.perf_counter() - t0

    trace = {
        "config": {"records": len(records), "mappers": n_mappers, "reducers": n_reducers, "combiner": combiner is not None},
        "map": {"records_in": len(records), "pairs_emitted": emitted, "seconds": round(t_map, 4), "sample": map_samples},
        "combine": {"pairs_after": after_combine, "reduction_pct": round(100 * (1 - after_combine / emitted), 1) if emitted else 0.0,
                    "seconds": round(t_comb, 4)} if combiner else None,
        "shuffle": {"pairs_in": after_combine, "keys": sum(len(p) for p in parts), "seconds": round(t_shuffle, 4),
                    "partitions": [{"reducer": i, "keys": len(p), "pairs": sum(len(v) for v in p.values())} for i, p in enumerate(parts)],
                    "sample": shuffle_sample},
        "reduce": {"keys_out": len(result), "seconds": round(t_reduce, 4),
                   "sample": [{"key": str(k), "value": _show(result[k])} for k, _ in biggest]},
    }
    return result, trace


def _show(v):
    return list(v) if isinstance(v, tuple) else v
