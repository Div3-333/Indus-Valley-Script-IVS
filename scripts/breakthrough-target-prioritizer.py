#!/usr/bin/env python3
"""Rank high-leverage decipherment targets.

This script looks for keystone signs, contrasts, and frames where a successful
resolution would unlock many downstream tests. The output is a research target
portfolio rather than a reading proposal.
"""

from __future__ import annotations

import argparse
import csv
import re
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from pathlib import Path


TOKEN_RE = re.compile(r"(?<!\d)\d{3,4}(?!\d)")


@dataclass
class SignStats:
    sign: str
    variable: str = ""
    functional_class: str = ""
    count_ready: int = 0
    role_contexts: str = ""
    semantic_frames: str = ""
    constraints: Counter[str] = field(default_factory=Counter)
    probes: Counter[str] = field(default_factory=Counter)
    neighbor_rows: int = 0
    role_boundary_rows: int = 0
    max_validation_score: float = 0.0
    max_neighbor_score: float = 0.0


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8-sig") as handle:
        return list(csv.DictReader(handle))


def write_csv(path: Path, rows: list[dict[str, object]], fields: list[str]) -> None:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def ffloat(value: str | None, default: float = 0.0) -> float:
    try:
        return float(value or default)
    except ValueError:
        return default


def fint(value: str | None, default: int = 0) -> int:
    try:
        return int(float(value or default))
    except ValueError:
        return default


def clamp(value: float, low: float = 0.0, high: float = 1.0) -> float:
    return max(low, min(high, value))


def sign_tokens(value: str | None) -> list[str]:
    return TOKEN_RE.findall(value or "")


def top_counter(counter: Counter[str], limit: int = 5) -> str:
    return "; ".join(f"{key}:{value}" for key, value in counter.most_common(limit))


def latex_escape(value: object) -> str:
    text = "" if value is None else str(value)
    replacements = {
        "\\": "/",
        "_": r"\_",
        "%": r"\%",
        "&": r"\&",
        "#": r"\#",
        "$": r"\$",
        "{": r"\{",
        "}": r"\}",
    }
    for old, new in replacements.items():
        text = text.replace(old, new)
    return text


def latex_table(rows: list[dict[str, object]], fields: list[str], widths: list[str] | None = None) -> str:
    spec = "".join(widths) if widths else "l" * len(fields)
    lines = [rf"\begin{{tabular}}{{{spec}}}", r"\toprule"]
    lines.append(" & ".join(rf"\textbf{{{latex_escape(field)}}}" for field in fields) + r" \\")
    lines.append(r"\midrule")
    for row in rows:
        lines.append(" & ".join(latex_escape(row.get(field, "")) for field in fields) + r" \\")
    lines.append(r"\bottomrule")
    lines.append(r"\end{tabular}")
    return "\n".join(lines)


def load_sign_stats(out_dir: Path) -> dict[str, SignStats]:
    stats: dict[str, SignStats] = defaultdict(lambda: SignStats(""))
    for row in read_csv(out_dir / "phonetic_variable_map.csv"):
        sign = row["Sign"]
        stats[sign] = SignStats(
            sign=sign,
            variable=row.get("Variable", ""),
            functional_class=row.get("FunctionalClass", ""),
            count_ready=fint(row.get("CountInReadyTexts")),
            role_contexts=row.get("RoleContexts", ""),
            semantic_frames=row.get("SemanticFrames", ""),
        )
    return stats


def touch_sign(stats: dict[str, SignStats], sign: str) -> SignStats:
    if sign not in stats:
        stats[sign] = SignStats(sign=sign)
    if not stats[sign].sign:
        stats[sign].sign = sign
    return stats[sign]


def annotate_stats(out_dir: Path, stats: dict[str, SignStats]) -> None:
    for row in read_csv(out_dir / "validated_probe_results.csv"):
        status = row.get("ValidationStatus", "")
        score = ffloat(row.get("ValidationScore"))
        for sign in sign_tokens(row.get("AnchorUnit")) + sign_tokens(row.get("NeighborUnit")):
            sign_stat = touch_sign(stats, sign)
            sign_stat.constraints[status] += 1
            sign_stat.max_validation_score = max(sign_stat.max_validation_score, score)
        for sign in sign_tokens(row.get("ChangedAnchorComponent")) + sign_tokens(row.get("NeighborChangedComponent")):
            sign_stat = touch_sign(stats, sign)
            sign_stat.probes[row.get("ContrastClass", "")] += 1
            sign_stat.max_validation_score = max(sign_stat.max_validation_score, score)

    for row in read_csv(out_dir / "neighbor_reading_tests.csv"):
        score = ffloat(row.get("Score"))
        contrast = row.get("ContrastClass", "")
        signs = set(sign_tokens(row.get("AnchorUnit")) + sign_tokens(row.get("NeighborUnit")))
        signs.update(sign_tokens(row.get("ChangedAnchorComponent")))
        signs.update(sign_tokens(row.get("NeighborChangedComponent")))
        for sign in signs:
            sign_stat = touch_sign(stats, sign)
            sign_stat.neighbor_rows += 1
            sign_stat.max_neighbor_score = max(sign_stat.max_neighbor_score, score)
            if contrast == "role-boundary control":
                sign_stat.role_boundary_rows += 1


def evidence_for_sign(stats: dict[str, SignStats], sign: str) -> str:
    stat = stats.get(sign, SignStats(sign=sign))
    parts = [
        f"ready-text count={stat.count_ready}",
        f"class={stat.functional_class or 'unresolved'}",
        f"validation={top_counter(stat.constraints, 3) or 'none'}",
        f"neighbor rows={stat.neighbor_rows}",
    ]
    return "; ".join(parts)


def sign_unlock_score(stats: dict[str, SignStats], sign: str, bonus: float = 0.0, penalty: float = 0.0) -> float:
    stat = stats.get(sign, SignStats(sign=sign))
    corpus = clamp(stat.count_ready / 200.0)
    validation = stat.max_validation_score
    neighbor = clamp(stat.neighbor_rows / 60.0)
    role_boundary = clamp(stat.role_boundary_rows / 40.0)
    constraint = clamp(sum(stat.constraints.values()) / 10.0)
    return clamp(corpus * 0.25 + validation * 0.25 + neighbor * 0.20 + constraint * 0.15 + role_boundary * 0.10 + bonus - penalty)


def build_targets(out_dir: Path, stats: dict[str, SignStats]) -> list[dict[str, object]]:
    validations = read_csv(out_dir / "validated_probe_results.csv")
    lattice = read_csv(out_dir / "stem_contrast_lattice.csv")
    component_rows = read_csv(out_dir / "component_contrast_tests.csv")

    terminal_740_520 = next(
        (row for row in validations if row.get("ChangedAnchorComponent") == "740" and row.get("NeighborChangedComponent") == "520"),
        {},
    )
    phonetic_482_904 = next((row for row in validations if row.get("ChangedAnchorComponent") == "482" and row.get("NeighborChangedComponent") == "904"), {})
    stem_176_048 = next((row for row in validations if row.get("ChangedAnchorComponent") == "176" and row.get("NeighborChangedComponent") == "048"), {})
    morph_240 = [row for row in validations if row.get("ChangedAnchorComponent") == "240"]
    contrast_240_235 = [row for row in component_rows if row.get("AnchorComponent") == "240" and row.get("NeighborComponent") == "235"]

    targets: list[dict[str, object]] = []

    def add_target(
        target_id: str,
        target_type: str,
        target: str,
        hypothesis: str,
        unlocks: str,
        evidence: str,
        next_action: str,
        stop_condition: str,
        base_score: float,
        risk: str,
    ) -> None:
        targets.append(
            {
                "TargetId": target_id,
                "TargetType": target_type,
                "Target": target,
                "BreakthroughHypothesis": hypothesis,
                "UnlocksIfSolved": unlocks,
                "Evidence": evidence,
                "BreakthroughScore": f"{clamp(base_score):.3f}",
                "Risk": risk,
                "NextAction": next_action,
                "StopCondition": stop_condition,
            }
        )

    score_240 = sign_unlock_score(stats, "240", bonus=0.18)
    add_target(
        "BT-01",
        "Grammar Keystone",
        "240",
        "240 is a reusable qualifier/title/classifier-like component.",
        "Constrains the 240+STEM family; separates title/classifier behavior from entity stems; stabilizes 240-482, 240-176, and 240-740-090.",
        f"{evidence_for_sign(stats, '240')}; morphology probes={len(morph_240)}; 240:235 contrast rows={len(contrast_240_235)}",
        "Promote all validated 240 morphology constraints into a grammar model and test whether 240 always preserves frame identity.",
        "Stop if 240 behaves as an ordinary stem in same-frame contexts or fails to preserve formula identity.",
        score_240,
        "Medium: 240 is frequent and may be polyfunctional.",
    )

    score_482_904 = max(ffloat(phonetic_482_904.get("ValidationScore")), 0.0)
    add_target(
        "BT-02",
        "Phonetic Keystone",
        "482::904 inside 240+STEM",
        "482 and 904 occupy the same stem slot after 240 and may support the first abstract phonetic contrast after image checking.",
        "Opens the first controlled phonetic-test lane; turns 240+STEM into a repeatable contrast environment.",
        f"validation={score_482_904:.3f}; {phonetic_482_904.get('Reason', '')}; anchor frame occurrences={phonetic_482_904.get('AnchorFrameOccurrences', '')}; neighbor frame occurrences={phonetic_482_904.get('NeighborFrameOccurrences', '')}",
        "Image-check all 240-482 and 240-904 occurrences, then test whether 482/904 contrast correlates with object, site, or administrative context.",
        "Stop if visual review shows mismapped signs, broken directionality, or incompatible object/site distributions.",
        clamp(score_482_904 * 0.78 + sign_unlock_score(stats, "482") * 0.12 + sign_unlock_score(stats, "904") * 0.10),
        "Medium-high: 904 has fewer occurrences than 482.",
    )

    score_740_520 = max(ffloat(terminal_740_520.get("ValidationScore")), sign_unlock_score(stats, "740") * 0.5)
    add_target(
        "BT-03",
        "Terminal Keystone",
        "740::520",
        "740 and 520 form a terminal/suffix contrast family.",
        "Constrains terminal grammar across hundreds of ready texts; tests suffix, title, numeral, and allograph alternatives.",
        f"740: {evidence_for_sign(stats, '740')}; 520: {evidence_for_sign(stats, '520')}; validation={score_740_520:.3f}",
        "Model 740/520 as competing terminal functions and test whether each predicts following/preceding slot frames.",
        "Stop if 740 and 520 collapse into graphic/allographic variants without contextual separation.",
        clamp(score_740_520 * 0.70 + sign_unlock_score(stats, "740") * 0.20 + sign_unlock_score(stats, "520") * 0.10),
        "Medium: terminal signs can be suffixes, titles, numerals, or formula closures.",
    )

    score_176 = max(ffloat(stem_176_048.get("ValidationScore")), sign_unlock_score(stats, "176") * 0.8)
    add_target(
        "BT-04",
        "Stem-Family Keystone",
        "176 with 048/061",
        "176 is a root-like entity stem candidate with same-frame contrasts against 048 and 061.",
        "Could open a stem family in the 002|740 entity slot and connect standalone 176 with compound 240-176.",
        f"176: {evidence_for_sign(stats, '176')}; 048/061 probes are occurrence-limited but same-frame.",
        "Find or validate every 048 and 061 occurrence in 002|740 and compare iconography/material/site against 176.",
        "Stop if 048/061 are transcription noise, rare allographs, or contextually unrelated one-offs.",
        clamp(score_176 * 0.70 + sign_unlock_score(stats, "176") * 0.20 + sign_unlock_score(stats, "048") * 0.05 + sign_unlock_score(stats, "061") * 0.05),
        "High: 048 and 061 are currently occurrence-limited.",
    )

    score_235 = sign_unlock_score(stats, "235", bonus=0.07)
    add_target(
        "BT-05",
        "Formula Boundary Keystone",
        "240::235",
        "240 and 235 compete in title/classifier/formula-opener environments.",
        "Separates qualifier/title behavior from formula-marker behavior; stabilizes readings of 235-222 and 235-840-032.",
        f"235: {evidence_for_sign(stats, '235')}; 240: {evidence_for_sign(stats, '240')}; component contrast rows={len(contrast_240_235)}",
        "Model 240 and 235 as rival opener functions and test whether each selects different terminal or entity slots.",
        "Stop if the contrast is driven by mixed frames rather than functional substitution.",
        score_235,
        "Medium: 235 is formulaic and may serve multiple structural roles.",
    )

    score_032 = sign_unlock_score(stats, "032", bonus=0.10)
    add_target(
        "BT-06",
        "Blocker Removal",
        "032 role split",
        "032 is polyfunctional and must be split into role classes before it can support phonetic inference.",
        "Removes 108 role-boundary controls from the false-phonetic pool; protects the pipeline from contaminated comparisons.",
        f"032: {evidence_for_sign(stats, '032')}; role-boundary rows={stats.get('032', SignStats('032')).role_boundary_rows}",
        "Cluster 032 occurrences by frame, position, and iconography; test whether they are one sign, allographs, or multiple functions.",
        "Stop if the clusters do not produce stable slot-specific behavior.",
        score_032,
        "High: 032 may be genuinely polyfunctional.",
    )

    score_002_740 = clamp((sign_unlock_score(stats, "002") + sign_unlock_score(stats, "740")) / 2.0 + 0.08)
    add_target(
        "BT-07",
        "Frame Keystone",
        "002 X 740",
        "002 and 740 define the prime entity frame that hosts the strongest stem contrasts.",
        "Stabilizes entity-slot grammar; lets stem contrasts be tested under a fixed frame rather than across the whole corpus.",
        f"002: {evidence_for_sign(stats, '002')}; 740: {evidence_for_sign(stats, '740')}",
        "Treat 002|740 as a formal environment and test every X filler against site, object, and terminal behavior.",
        "Stop if 002|740 splits into unrelated frame types after visual/context review.",
        score_002_740,
        "Medium: 002 is a high-frequency slot modifier and may not be a single grammatical value.",
    )

    classifier_score = clamp((sign_unlock_score(stats, "820") + sign_unlock_score(stats, "861") + sign_unlock_score(stats, "817")) / 3.0 + 0.05)
    add_target(
        "BT-08",
        "Classifier System Keystone",
        "820/861/817",
        "820, 861, and 817 form the highest-yield initial classifier/title set.",
        "May unlock the left edge of many inscriptions and separate titles/classes from names or commodities.",
        f"820: {evidence_for_sign(stats, '820')}; 861: {evidence_for_sign(stats, '861')}; 817: {evidence_for_sign(stats, '817')}",
        "Build a three-way classifier substitution model and test whether each classifier selects distinct entity or terminal slots.",
        "Stop if their distributions are driven by site/corpus bias rather than frame function.",
        classifier_score,
        "Medium: classifiers may be determinatives, titles, or graphic families.",
    )

    stem_edges = [row for row in lattice if row.get("Status") in {"Phonetic-ready after image check", "Stem-semantic probe"}]
    stem_score = clamp(len(stem_edges) / 8.0 + max((ffloat(row.get("ValidationScore")) for row in stem_edges), default=0.0) * 0.35)
    add_target(
        "BT-09",
        "Stem Lattice Keystone",
        "176/482/904/048/061/773",
        "The emerging stem lattice can turn isolated stem probes into a network of contrastive values.",
        "If stable, this creates the first reusable pre-phonetic lexeme space.",
        f"validated/semivalid stem edges={len(stem_edges)}; best edge={stem_edges[0].get('Probe', '') if stem_edges else ''}",
        "Build a lattice consistency test: every stem must preserve frame while predicting context differences.",
        "Stop if edges cannot be made transitive or if contexts do not separate beyond chance.",
        stem_score,
        "High: several stems have few exact occurrences.",
    )

    targets.sort(key=lambda row: (-ffloat(str(row["BreakthroughScore"])), str(row["TargetId"])))
    for rank, row in enumerate(targets, start=1):
        row["Rank"] = rank
    return targets


def build_edges(targets: list[dict[str, object]]) -> list[dict[str, object]]:
    edges = [
        ("BT-01", "BT-02", "240 grammar makes 240+STEM contrasts interpretable."),
        ("BT-01", "BT-07", "240 behavior helps separate prime-entity and terminal formulas."),
        ("BT-02", "BT-09", "482::904 anchors the stem lattice."),
        ("BT-04", "BT-09", "176 with 048/061 expands the stem lattice beyond Harappa-heavy 482."),
        ("BT-05", "BT-01", "240::235 separates qualifier from formula-opener behavior."),
        ("BT-03", "BT-07", "740/520 terminal grammar constrains the right edge of 002 X 740."),
        ("BT-06", "BT-09", "032 role split removes contaminated stem-like comparisons."),
        ("BT-08", "BT-07", "Classifier behavior constrains the left edge of entity formulas."),
        ("BT-07", "BT-02", "A stable 002 X 740 frame makes 482::904 a stronger phonetic probe."),
    ]
    scores = {row["TargetId"]: row["BreakthroughScore"] for row in targets}
    return [
        {
            "SourceTarget": source,
            "UnlockedTarget": target,
            "Relation": relation,
            "SourceScore": scores.get(source, ""),
            "TargetScore": scores.get(target, ""),
        }
        for source, target, relation in edges
    ]


def build_action_plan(targets: list[dict[str, object]]) -> list[dict[str, object]]:
    actions: list[dict[str, object]] = []
    for row in targets[:7]:
        actions.append(
            {
                "Rank": len(actions) + 1,
                "TargetId": row["TargetId"],
                "Action": row["NextAction"],
                "ExpectedBreakthrough": row["UnlocksIfSolved"],
                "DecisionRule": row["StopCondition"],
            }
        )
    return actions


def build_summary(targets: list[dict[str, object]], edges: list[dict[str, object]], actions: list[dict[str, object]]) -> list[dict[str, object]]:
    top = targets[0] if targets else {}
    target_types = Counter(str(row["TargetType"]) for row in targets)
    return [
        {"Metric": "Breakthrough targets ranked", "Value": len(targets), "Note": "Keystone targets scored for downstream unlock value."},
        {"Metric": "Dependency edges", "Value": len(edges), "Note": "How one breakthrough unlocks another."},
        {"Metric": "Action-plan items", "Value": len(actions), "Note": "Highest-priority next research moves."},
        {"Metric": "Top target", "Value": top.get("Target", ""), "Note": top.get("BreakthroughHypothesis", "")},
        {"Metric": "Top target score", "Value": top.get("BreakthroughScore", ""), "Note": top.get("TargetType", "")},
        {"Metric": "Target type mix", "Value": top_counter(target_types), "Note": "Portfolio composition."},
    ]


def write_latex_summary(
    path: Path,
    summary: list[dict[str, object]],
    targets: list[dict[str, object]],
    actions: list[dict[str, object]],
) -> None:
    top_targets = [
        {
            "Rank": row["Rank"],
            "Target": row["Target"],
            "Type": row["TargetType"],
            "Score": row["BreakthroughScore"],
        }
        for row in targets[:8]
    ]
    action_rows = [
        {
            "Rank": row["Rank"],
            "Target": row["TargetId"],
            "Action": row["Action"],
        }
        for row in actions[:6]
    ]
    text = (
        r"""\section{Breakthrough Target Portfolio}

\subsection{Purpose}

This generated note ranks high-leverage targets: signs, contrasts, and frames where a successful resolution would make later phases faster. The portfolio is designed to avoid broad exploration and focus on keystones.

\subsection{Summary}

\begin{table}[htbp]
\centering
"""
        + latex_table(summary, ["Metric", "Value"], ["p{0.58\\textwidth}", "r"])
        + r"""
\caption{Breakthrough target summary.}
\end{table}

\subsection{Top Targets}

\begin{table}[htbp]
\centering
\footnotesize
"""
        + latex_table(top_targets, ["Rank", "Target", "Type", "Score"], ["r", "p{0.26\\textwidth}", "p{0.34\\textwidth}", "r"])
        + r"""
\caption{Highest-leverage decipherment targets.}
\end{table}

\subsection{Action Plan}

\begin{table}[htbp]
\centering
\footnotesize
"""
        + latex_table(action_rows, ["Rank", "Target", "Action"], ["r", "l", "p{0.64\\textwidth}"])
        + r"""
\caption{Next actions for exponential leverage.}
\end{table}
"""
    )
    path.write_text(text, encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--outputs", default="outputs", help="Directory containing model outputs")
    args = parser.parse_args()

    out_dir = Path(args.outputs)
    stats = load_sign_stats(out_dir)
    annotate_stats(out_dir, stats)
    targets = build_targets(out_dir, stats)
    edges = build_edges(targets)
    actions = build_action_plan(targets)
    summary = build_summary(targets, edges, actions)

    write_csv(out_dir / "breakthrough_target_summary.csv", summary, ["Metric", "Value", "Note"])
    write_csv(
        out_dir / "breakthrough_targets.csv",
        targets,
        [
            "Rank",
            "TargetId",
            "TargetType",
            "Target",
            "BreakthroughHypothesis",
            "UnlocksIfSolved",
            "Evidence",
            "BreakthroughScore",
            "Risk",
            "NextAction",
            "StopCondition",
        ],
    )
    write_csv(
        out_dir / "breakthrough_dependency_edges.csv",
        edges,
        ["SourceTarget", "UnlockedTarget", "Relation", "SourceScore", "TargetScore"],
    )
    write_csv(
        out_dir / "breakthrough_action_plan.csv",
        actions,
        ["Rank", "TargetId", "Action", "ExpectedBreakthrough", "DecisionRule"],
    )
    write_latex_summary(out_dir / "breakthrough_target_portfolio.tex", summary, targets, actions)

    print("Wrote breakthrough target outputs:")
    for name in [
        "breakthrough_target_summary.csv",
        "breakthrough_targets.csv",
        "breakthrough_dependency_edges.csv",
        "breakthrough_action_plan.csv",
        "breakthrough_target_portfolio.tex",
    ]:
        print(f"  - {out_dir / name}")


if __name__ == "__main__":
    main()
