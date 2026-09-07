from __future__ import annotations

import argparse
import json
from pathlib import Path

from football1.recency_audit import ALPHA, walk_forward_recency_audit


SHORT_RECENCY_HALF_LIVES = (15.0, 30.0, 60.0, 120.0)


def run_short_recency_audit(
    db_path: Path,
    *,
    min_train_seasons: int = 3,
    alpha: float = ALPHA,
) -> dict[str, object]:
    report = walk_forward_recency_audit(
        db_path,
        min_train_seasons=min_train_seasons,
        alpha=alpha,
        half_lives=SHORT_RECENCY_HALF_LIVES,
    )
    report["experiment"] = "recency_weighted_form_short_half_life_extension_v1"
    report["parameter_policy"] = (
        "15 days is an explicitly requested short-horizon sensitivity probe added after the original 30/60/120-day "
        "history was inspected. It therefore cannot be treated as untouched validation or selected as a winning "
        "half-life from this audit. 30/60/120 remain comparison anchors."
    )
    report["warning"] = (
        "The 15-day result is post-hoc exploratory evidence. Any apparent advantage must be frozen at zero decision "
        "weight and confirmed on future fixtures before product use."
    )
    return report


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Extend Football 1 recency audit with a 15-day half-life probe.")
    parser.add_argument("--database", type=Path, default=Path("data/processed/football1.sqlite"))
    parser.add_argument("--output", type=Path, default=Path("data/processed/recency_short_audit.json"))
    parser.add_argument("--min-train-seasons", type=int, default=3)
    return parser


def main() -> None:
    args = build_parser().parse_args()
    report = run_short_recency_audit(args.database, min_train_seasons=args.min_train_seasons)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({
        "status": report["status"],
        "decision_weight": report["decision_weight"],
        "overall_raw_market": report["overall_raw_market"],
        "overall_variants": report["overall_variants"],
    }, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
