"""Exhaustively verify the finite calibration case without contacting a model.

This is an external experiment answer-key check, not a production truth predicate
or scheduling objective. Every allowed bias tuple is considered. Connectedness
and the anchored pressure make each corrected graph have at most one pressure
assignment; checking all eight original equations rejects inconsistent tuples.
"""

from itertools import combinations, product
import json


EDGES = (
    ("A", "E", "M", 0),
    ("A", "D", "M", -1),
    ("C", "D", "N", -2),
    ("B", "E", "N", -3),
    ("A", "B", "P", 6),
    ("A", "C", "P", 4),
    ("C", "E", "Q", -1),
    ("B", "D", "Q", -4),
)


def feasible_worlds():
    """Enumerate the entire allowed fault domain, propagating exact pressures."""
    worlds = []
    for values in product(range(-3, 4), repeat=4):
        if sum(v != 0 for v in values) > 2:
            continue
        bias = dict(zip("MNPQ", values))
        pressure = {"A": 10}
        for _ in range(5):
            for start, end, meter, reading in EDGES:
                difference = reading - bias[meter]
                if start in pressure and end not in pressure:
                    pressure[end] = pressure[start] + difference
                elif end in pressure and start not in pressure:
                    pressure[start] = pressure[end] - difference
        if len(pressure) != 5:
            raise AssertionError("The designated graph must be connected")
        if not all(7 <= x <= 23 for x in pressure.values()):
            continue
        if not all(
            pressure[end] - pressure[start] + bias[meter] == reading
            for start, end, meter, reading in EDGES
        ):
            continue
        worlds.append({"pressure": {k: pressure[k] for k in "ABCDE"}, "bias": bias})
    return worlds


def verify():
    worlds = feasible_worlds()
    compact = [(tuple(w["pressure"].values()), tuple(w["bias"].values())) for w in worlds]
    assert compact == [
        ((10, 16, 14, 12, 13), (-3, 0, 0, 0)),
        ((10, 15, 13, 11, 12), (-2, 0, 1, 0)),
        ((10, 14, 12, 10, 11), (-1, 0, 2, 0)),
        ((10, 13, 11, 9, 10), (0, 0, 3, 0)),
        ((10, 16, 14, 9, 10), (0, 3, 0, 3)),
    ]
    assert not any(all(v == 0 for v in w["bias"].values()) for w in worlds)
    assert [sum(v != 0 for v in w["bias"].values()) for w in worlds] == [1, 2, 2, 1, 2]
    single_checks = {
        meter: len({w["bias"][meter] for w in worlds}) == len(worlds)
        for meter in "MNPQ"
    }
    assert not any(single_checks.values())
    pairs = [
        "".join(pair)
        for pair in combinations("MNPQ", 2)
        if len({tuple(w["bias"][m] for m in pair) for w in worlds}) == len(worlds)
    ]
    assert pairs == ["MN", "MP", "MQ", "NP", "PQ"]
    after_m_zero = [w for w in worlds if w["bias"]["M"] == 0]
    assert len(after_m_zero) == 2
    after_n_zero = [w for w in after_m_zero if w["bias"]["N"] == 0]
    assert len(after_n_zero) == 1
    assert after_n_zero[0]["bias"] == dict(zip("MNPQ", (0, 0, 3, 0)))
    # An ideal-meter cycle would require 4 + (-2) - (-1) = 0.
    assert 4 - 2 + 1 == 3
    # Adaptive first M, then N only if M == 0, identifies every initial world.
    leaves = [(w["bias"]["M"], w["bias"]["N"] if w["bias"]["M"] == 0 else None) for w in worlds]
    assert len(set(leaves)) == len(worlds)
    return {
        "world_count": len(worlds),
        "worlds": worlds,
        "any_single_meter_always_identifies": single_checks,
        "identifying_fixed_pairs": pairs,
        "after_M_zero": after_m_zero,
        "after_M_zero_N_zero": after_n_zero,
        "minimum_guaranteed_worst_case_checks": 2,
        "enumeration_scope": "All 7^4 bias tuples, filtered to at most two nonzero; exact connected-graph propagation; all eight equations and pressure bounds checked",
    }


if __name__ == "__main__":
    print(json.dumps(verify(), indent=2))
