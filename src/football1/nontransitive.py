from __future__ import annotations

import argparse
import itertools
import json
import math
from collections import defaultdict
from pathlib import Path

from football1.davidson import MatchRecord, load_matches


MIN_MEETINGS = 4
PRIOR_MATCHES = 4.0
EDGE_THRESHOLD = 0.04
WINDOWS = (3, 5, 10)


def _score_for_team(match: MatchRecord, team: str) -> tuple[float, float] | None:
    if match.market_probs is None:
        return None
    h, d, a = match.market_probs
    if team == match.home_team:
        observed = 1.0 if match.result == "H" else 0.5 if match.result == "D" else 0.0
        expected = h + 0.5 * d
    elif team == match.away_team:
        observed = 1.0 if match.result == "A" else 0.5 if match.result == "D" else 0.0
        expected = a + 0.5 * d
    else:
        raise ValueError("Team is not in match")
    return observed, expected


def pair_residuals(matches: list[MatchRecord]) -> list[dict[str, object]]:
    grouped: dict[tuple[str, str], list[float]] = defaultdict(list)
    for match in matches:
        if match.market_probs is None:
            continue
        a, b = sorted((match.home_team, match.away_team))
        score = _score_for_team(match, a)
        if score is None:
            continue
        observed, expected = score
        grouped[(a, b)].append(observed - expected)

    rows: list[dict[str, object]] = []
    for (a, b), values in grouped.items():
        n = len(values)
        raw = sum(values) / n
        shrunk = sum(values) / (n + PRIOR_MATCHES)
        if n > 1:
            variance = sum((x - raw) ** 2 for x in values) / (n - 1)
            se = math.sqrt(variance / n)
        else:
            se = None
        rows.append({
            "team_a": a,
            "team_b": b,
            "meetings": n,
            "mean_market_score_residual_a_minus_b": raw,
            "shrunk_residual_a_minus_b": shrunk,
            "standard_error": se,
        })
    return sorted(rows, key=lambda r: (-abs(float(r["shrunk_residual_a_minus_b"])), str(r["team_a"]), str(r["team_b"])))


def _directed_scores(rows: list[dict[str, object]]) -> dict[tuple[str, str], float]:
    scores: dict[tuple[str, str], float] = {}
    for row in rows:
        if int(row["meetings"]) < MIN_MEETINGS:
            continue
        a = str(row["team_a"])
        b = str(row["team_b"])
        value = float(row["shrunk_residual_a_minus_b"])
        if abs(value) < EDGE_THRESHOLD:
            continue
        scores[(a, b)] = value
        scores[(b, a)] = -value
    return scores


def cycle_audit(rows: list[dict[str, object]]) -> dict[str, object]:
    scores = _directed_scores(rows)
    teams = sorted({team for pair in scores for team in pair})
    complete_triangles = 0
    cyclic_triangles = 0
    transitive_triangles = 0
    cycles: list[dict[str, object]] = []

    for a, b, c in itertools.combinations(teams, 3):
        if not all((x, y) in scores for x, y in ((a, b), (b, c), (c, a))):
            continue
        complete_triangles += 1
        ab, bc, ca = scores[(a, b)], scores[(b, c)], scores[(c, a)]
        forward = ab > 0 and bc > 0 and ca > 0
        reverse = ab < 0 and bc < 0 and ca < 0
        if forward or reverse:
            cyclic_triangles += 1
            if reverse:
                a, b, c = a, c, b
                ab = scores[(a, b)]
                bc = scores[(b, c)]
                ca = scores[(c, a)]
            cycles.append({
                "cycle": [a, b, c, a],
                "edges": [ab, bc, ca],
                "cycle_strength": min(abs(ab), abs(bc), abs(ca)),
            })
        else:
            transitive_triangles += 1

    cycles.sort(key=lambda x: -float(x["cycle_strength"]))
    return {
        "significant_directed_edges": len(scores) // 2,
        "complete_significant_triangles": complete_triangles,
        "cyclic_triangles": cyclic_triangles,
        "transitive_triangles": transitive_triangles,
        "cyclic_share": (cyclic_triangles / complete_triangles if complete_triangles else None),
        "strongest_cycles": cycles[:20],
    }


def audit_window(matches: list[MatchRecord], seasons: set[int], label: str) -> dict[str, object]:
    selected = [m for m in matches if m.season_start_year in seasons]
    rows = pair_residuals(selected)
    eligible = [r for r in rows if int(r["meetings"]) >= MIN_MEETINGS]
    return {
        "window": label,
        "seasons": sorted(seasons),
        "matches": len(selected),
        "paired_market_matches": sum(1 for m in selected if m.market_probs is not None),
        "pair_count": len(rows),
        "eligible_pair_count": len(eligible),
        "strongest_pair_residuals": eligible[:20],
        "cycle_audit": cycle_audit(rows),
    }


def nontransitive_audit(db_path: Path) -> dict[str, object]:
    matches = load_matches(db_path)
    seasons = sorted({m.season_start_year for m in matches})
    reports: list[dict[str, object]] = []
    for width in WINDOWS:
        use = set(seasons[-min(width, len(seasons)):])
        reports.append(audit_window(matches, use, f"latest_{width}_seasons"))
    reports.append(audit_window(matches, set(seasons), "all_seasons"))
    return {
        "experiment": "market_residual_nontransitivity_audit_v1",
        "status": "exploratory_context_only",
        "question": "Do repeated pairwise EPL relationships contain cyclic residual structure after the bookmaker market expectation is removed?",
        "residual_definition": "observed match score (win=1, draw=0.5, loss=0) minus de-vigged B365 expected score, from the canonical first team's perspective",
        "shrinkage_policy": f"pair residual sum divided by meetings + {PRIOR_MATCHES:g} prior matches",
        "edge_policy": f"at least {MIN_MEETINGS} meetings and absolute shrunk residual at least {EDGE_THRESHOLD:.3f}",
        "interpretation_warning": "A cycle is a descriptive anomaly in repeated pair relationships, not proof of a stable style effect and not a betting signal.",
        "windows": reports,
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Audit market-residual non-transitive EPL matchup structure.")
    parser.add_argument("--database", type=Path, default=Path("data/processed/football1.sqlite"))
    parser.add_argument("--output", type=Path)
    return parser


def main() -> None:
    args = build_parser().parse_args()
    report = nontransitive_audit(args.database)
    text = json.dumps(report, indent=2, sort_keys=True)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(text + "\n", encoding="utf-8")
        print(f"wrote non-transitivity report to {args.output}")
    else:
        print(text)


if __name__ == "__main__":
    main()
