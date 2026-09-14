from dataclasses import dataclass

import pandas as pd

from astana_access.config import ROOT

GOLD = ROOT / "data" / "labels" / "linkage_gold.csv"


@dataclass(frozen=True)
class Metrics:
    evaluated: int
    true_positive: int
    false_positive: int
    false_negative: int
    precision: float
    recall: float
    f1: float


def load_gold() -> pd.DataFrame:
    gold = pd.read_csv(GOLD, dtype={"gold_osm_idx": str}, keep_default_na=False)
    return gold


def evaluate(
    matches: pd.DataFrame, gold: pd.DataFrame, confidence: str | None = None
) -> tuple[Metrics, pd.DataFrame]:
    frame = gold[gold["gold_osm_idx"] != "AMBIGUOUS"].copy()
    if confidence is not None:
        frame = frame[frame["confidence"] == confidence]
    predicted = dict(
        zip(matches["reg_idx"].astype(int), matches["osm_idx"].astype(int), strict=True)
    )
    rows = []
    tp = fp = fn = 0
    for _, row in frame.iterrows():
        truth = int(row["gold_osm_idx"]) if row["gold_osm_idx"] else None
        guess = predicted.get(int(row["reg_idx"]))
        if guess is not None and truth is not None and guess == truth:
            outcome = "tp"
            tp += 1
        else:
            outcome = []
            if guess is not None:
                fp += 1
                outcome.append("fp")
            if truth is not None:
                fn += 1
                outcome.append("fn")
            outcome = "+".join(outcome) or "tn"
        rows.append(
            {
                "reg_idx": int(row["reg_idx"]),
                "truth": truth,
                "guess": guess,
                "outcome": outcome,
                "note": row["note"],
            }
        )
    precision = tp / (tp + fp) if tp + fp else 0.0
    recall = tp / (tp + fn) if tp + fn else 0.0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    metrics = Metrics(len(frame), tp, fp, fn, precision, recall, f1)
    return metrics, pd.DataFrame(rows)
