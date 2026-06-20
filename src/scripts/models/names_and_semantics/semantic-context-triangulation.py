#!/usr/bin/env python3
"""Triangulate semantic context for phonetic and onomastic anchors.

This stage connects the abstract phonetic testbench to external metadata that
is already present in the corpus: site, region, seal/object type, material, and
iconographic symbol labels. It does not translate signs. It ranks semantic
contexts that can constrain future readings.
"""

from __future__ import annotations

import argparse
import csv
import math
import re
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from pathlib import Path


TOKEN_RE = re.compile(r"(?<!\d)\d{3,4}(?!\d)")
START = "<START>"
END = "<END>"
UNKNOWN = "Unknown"
PRIORITY_CLASSES = {"StrongOnomasticAnchor", "CrossFramePhoneticAnchor", "AffixOrFormulaAnchor"}


@dataclass
class UnitContext:
    unit: str
    abstract_unit: str = ""
    role: str = ""
    test_class: str = ""
    phonetic_score: float = 0.0
    occurrences: int = 0
    text_ids: set[str] = field(default_factory=set)
    examples: list[str] = field(default_factory=list)
    dimensions: dict[str, Counter[str]] = field(default_factory=lambda: defaultdict(Counter))
    semantic_frames: Counter[str] = field(default_factory=Counter)
    frames: Counter[str] = field(default_factory=Counter)


def sign_tokens(text: str | None) -> list[str]:
    return TOKEN_RE.findall(text or "")


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


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8-sig") as handle:
        return list(csv.DictReader(handle))


def write_csv(path: Path, rows: list[dict[str, object]], fields: list[str]) -> None:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


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


def split_list(value: str | None) -> list[str]:
    if not value:
        return []
    return [part.strip() for part in value.split(";") if part.strip()]


def parse_slot_fillers(value: str | None) -> list[dict[str, object]]:
    slots: list[dict[str, object]] = []
    for part in split_list(value):
        if ":" not in part:
            continue
        frame, rest = part.split(":", 1)
        if "@" in rest:
            filler, position = rest.split("@", 1)
        else:
            filler, position = rest, ""
        frame = frame.strip()
        filler_tokens = tuple(sign_tokens(filler))
        if not filler_tokens:
            continue
        left, right = ("", "")
        if "|" in frame:
            left, right = frame.split("|", 1)
        slots.append(
            {
                "frame": frame,
                "left": left,
                "right": right,
                "filler": "-".join(filler_tokens),
                "tokens": filler_tokens,
                "position": position.strip(),
            }
        )
    return slots


def normalize(value: str | None, dimension: str) -> str:
    text = (value or "").strip()
    if not text or text == "-":
        return UNKNOWN
    if dimension == "Symbol":
        if text.startswith("Bull1"):
            return "Bull"
        aliases = {
            "Bult": "Bull/uncertain",
            "Bull1": "Bull",
            "Bull1:W": "Bull",
            "Bull1:J": "Bull",
            "Bull1:S": "Bull",
            "Bull1:I": "Bull",
            "Bull1:L": "Bull",
            "Bull": "Bull",
            "CompBull": "Composite Bull",
            "Mult": "Composite/Multiple",
            "Othr": "Other",
            "Elep": "Elephant",
            "Phyt": "Plant",
            "Rhin": "Rhinoceros",
            "Gavi": "Gavial",
        }
        return aliases.get(text, text)
    if dimension == "Type":
        return text.split(":")[0]
    return text


def top_counter(counter: Counter[str], limit: int = 5) -> str:
    return "; ".join(f"{key}:{value}" for key, value in counter.most_common(limit))


def dominant(counter: Counter[str]) -> str:
    if not counter:
        return UNKNOWN
    return counter.most_common(1)[0][0]


def load_unit_metadata(path: Path) -> dict[str, dict[str, str]]:
    return {row.get("Unit", ""): row for row in read_csv(path) if row.get("Unit")}


def candidate_rows(rows: list[dict[str, str]]) -> list[dict[str, str]]:
    return [
        row
        for row in rows
        if row.get("PhoneticReadiness") in {"High", "Medium"}
        and ffloat(row.get("ReconstructionConfidence")) >= 0.5
    ]


def context_dimensions(row: dict[str, str]) -> dict[str, str]:
    return {
        "Region": normalize(row.get("Region"), "Region"),
        "Site": normalize(row.get("Site"), "Site"),
        "Type": normalize(row.get("Type"), "Type"),
        "Material": normalize(row.get("Material"), "Material"),
        "Symbol": normalize(row.get("Symbol"), "Symbol"),
        "SemanticFrame": normalize(row.get("SemanticFrame"), "SemanticFrame"),
    }


def semantic_options_for(unit: UnitContext, best_symbol: str, best_site: str, best_region: str) -> str:
    role = unit.role
    if role == "PrimeEntityFiller":
        options = ["proper name", "office/title", "lineage or clan", "place", "authority formula"]
        if best_symbol != UNKNOWN:
            options.append("emblem-linked identity")
        if best_site != UNKNOWN or best_region != UNKNOWN:
            options.append("regional or institutional name")
        return "; ".join(options)
    if role in {"InitialFiller", "PreTerminalFiller"}:
        return "classifier; title; office marker; prefix; regional formula marker"
    if role == "TerminalFiller":
        return "title/suffix; terminal formula; object marker; administrative ending"
    return "lexical root; classifier; affix; formula marker; unresolved semantic unit"


def next_test_for(unit: UnitContext, best_dimension: str, best_category: str) -> str:
    if best_dimension == "Symbol" and best_category != UNKNOWN:
        return f"inspect seal images for all {unit.unit} occurrences with {best_category}; test emblem-linked reading"
    if best_dimension in {"Site", "Region"}:
        return f"compare all {unit.unit} occurrences inside and outside {best_category}; test regional/administrative value"
    if best_dimension in {"Type", "Material"}:
        return f"compare artifact function for {unit.unit} in {best_category}; test administrative/object-class value"
    return f"collect more context for {unit.unit}; keep phonetic value unassigned"


def association_strength(count: int, unit_total: int, category_total: int, baseline_total: int) -> dict[str, float]:
    if unit_total <= 0 or category_total <= 0 or baseline_total <= 0:
        return {"expected": 0.0, "lift": 0.0, "log2_lift": 0.0, "score": 0.0}
    observed_rate = count / unit_total
    baseline_rate = category_total / baseline_total
    expected = unit_total * baseline_rate
    lift = observed_rate / baseline_rate if baseline_rate else 0.0
    log2_lift = math.log(lift, 2) if lift > 0 else 0.0
    support = min(count / 5.0, 1.0)
    purity = observed_rate
    lift_score = min(max(log2_lift, 0.0) / 2.5, 1.0)
    expected_bonus = min(max(count - expected, 0.0) / 5.0, 1.0)
    score = 0.34 * support + 0.28 * purity + 0.28 * lift_score + 0.10 * expected_bonus
    return {
        "expected": round(expected, 3),
        "lift": round(lift, 3),
        "log2_lift": round(log2_lift, 3),
        "score": round(score, 3),
    }


def strength_label(count: int, lift: float, score: float) -> str:
    if count >= 3 and lift >= 2.0 and score >= 0.55:
        return "Strong"
    if count >= 2 and lift >= 1.4 and score >= 0.38:
        return "Moderate"
    if count >= 1 and lift >= 1.2:
        return "Exploratory"
    return "Weak"


def build_contexts(
    rows: list[dict[str, str]],
    unit_metadata: dict[str, dict[str, str]],
) -> tuple[dict[str, UnitContext], dict[str, Counter[str]], Counter[str]]:
    units: dict[str, UnitContext] = {}
    baselines: dict[str, Counter[str]] = defaultdict(Counter)
    usable_iconography = Counter()

    for row in rows:
        dims = context_dimensions(row)
        for dimension, category in dims.items():
            baselines[dimension][category] += 1
        if dims["Symbol"] != UNKNOWN:
            usable_iconography["usable"] += 1
        else:
            usable_iconography["unknown"] += 1

        for slot in parse_slot_fillers(row.get("SlotFillers")):
            unit_id = str(slot["filler"])
            if unit_id not in unit_metadata:
                continue
            meta = unit_metadata[unit_id]
            if unit_id not in units:
                units[unit_id] = UnitContext(
                    unit=unit_id,
                    abstract_unit=meta.get("AbstractUnit", ""),
                    role=meta.get("Role", ""),
                    test_class=meta.get("TestClass", ""),
                    phonetic_score=ffloat(meta.get("Score")),
                )
            unit = units[unit_id]
            unit.occurrences += 1
            unit.text_ids.add(row.get("TextId", ""))
            unit.frames[str(slot["frame"])] += 1
            unit.semantic_frames[row.get("SemanticFrame", UNKNOWN)] += 1
            for dimension, category in dims.items():
                unit.dimensions[dimension][category] += 1
            if len(unit.examples) < 8:
                cisi = row.get("CISI") or row.get("TextId") or "?"
                symbol = dims["Symbol"]
                site = dims["Site"]
                unit.examples.append(f"{cisi}@{site}/{symbol}")

    return units, baselines, usable_iconography


def build_profiles(units: dict[str, UnitContext]) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for unit in units.values():
        best_symbol = dominant(unit.dimensions["Symbol"])
        best_site = dominant(unit.dimensions["Site"])
        best_region = dominant(unit.dimensions["Region"])
        rows.append(
            {
                "Unit": unit.unit,
                "AbstractUnit": unit.abstract_unit,
                "Role": unit.role,
                "TestClass": unit.test_class,
                "PhoneticScore": unit.phonetic_score,
                "Occurrences": unit.occurrences,
                "TextCount": len(unit.text_ids),
                "TopRegion": top_counter(unit.dimensions["Region"], 4),
                "TopSite": top_counter(unit.dimensions["Site"], 5),
                "TopSymbol": top_counter(unit.dimensions["Symbol"], 5),
                "TopType": top_counter(unit.dimensions["Type"], 4),
                "TopMaterial": top_counter(unit.dimensions["Material"], 4),
                "Frames": top_counter(unit.frames, 5),
                "SemanticFrames": top_counter(unit.semantic_frames, 5),
                "ExampleTexts": "; ".join(unit.examples),
            }
        )
    rows.sort(
        key=lambda row: (
            {"StrongOnomasticAnchor": 0, "CrossFramePhoneticAnchor": 1, "AffixOrFormulaAnchor": 2}.get(
                str(row["TestClass"]),
                3,
            ),
            -ffloat(str(row["PhoneticScore"])),
            str(row["Unit"]),
        )
    )
    return rows


def build_correlations(
    units: dict[str, UnitContext],
    baselines: dict[str, Counter[str]],
    baseline_total: int,
) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for unit in units.values():
        for dimension, counter in unit.dimensions.items():
            for category, count in counter.items():
                if category == UNKNOWN and dimension == "Symbol":
                    continue
                assoc = association_strength(
                    count=count,
                    unit_total=unit.occurrences,
                    category_total=baselines[dimension][category],
                    baseline_total=baseline_total,
                )
                label = strength_label(count, assoc["lift"], assoc["score"])
                rows.append(
                    {
                        "Unit": unit.unit,
                        "AbstractUnit": unit.abstract_unit,
                        "Role": unit.role,
                        "TestClass": unit.test_class,
                        "Dimension": dimension,
                        "Category": category,
                        "Count": count,
                        "UnitOccurrences": unit.occurrences,
                        "BaselineCount": baselines[dimension][category],
                        "Expected": assoc["expected"],
                        "Lift": assoc["lift"],
                        "Log2Lift": assoc["log2_lift"],
                        "AssociationScore": assoc["score"],
                        "Strength": label,
                    }
                )
    rows.sort(
        key=lambda row: (
            {"Strong": 0, "Moderate": 1, "Exploratory": 2, "Weak": 3}.get(str(row["Strength"]), 4),
            -ffloat(str(row["AssociationScore"])),
            -fint(str(row["Count"])),
            str(row["Unit"]),
        )
    )
    return rows


def build_semantic_candidates(
    units: dict[str, UnitContext],
    correlations: list[dict[str, object]],
) -> list[dict[str, object]]:
    by_unit: dict[str, list[dict[str, object]]] = defaultdict(list)
    for row in correlations:
        if row["Strength"] in {"Strong", "Moderate"}:
            by_unit[str(row["Unit"])].append(row)

    rows: list[dict[str, object]] = []
    for unit in units.values():
        if unit.test_class not in PRIORITY_CLASSES:
            continue
        useful = by_unit.get(unit.unit, [])
        useful = sorted(
            useful,
            key=lambda row: (
                {"Symbol": 0, "Site": 1, "Region": 2, "Type": 3, "Material": 4, "SemanticFrame": 5}.get(
                    str(row["Dimension"]),
                    6,
                ),
                -ffloat(str(row["AssociationScore"])),
            ),
        )
        best = useful[0] if useful else {
            "Dimension": "None",
            "Category": UNKNOWN,
            "AssociationScore": 0.0,
            "Strength": "Unresolved",
        }
        best_symbol = dominant(unit.dimensions["Symbol"])
        best_site = dominant(unit.dimensions["Site"])
        best_region = dominant(unit.dimensions["Region"])
        rows.append(
            {
                "Unit": unit.unit,
                "AbstractUnit": unit.abstract_unit,
                "Role": unit.role,
                "TestClass": unit.test_class,
                "PhoneticScore": unit.phonetic_score,
                "Occurrences": unit.occurrences,
                "BestContextDimension": best["Dimension"],
                "BestContextCategory": best["Category"],
                "BestContextStrength": best["Strength"],
                "BestContextScore": best["AssociationScore"],
                "TopSymbol": top_counter(unit.dimensions["Symbol"], 4),
                "TopSite": top_counter(unit.dimensions["Site"], 4),
                "TopRegion": top_counter(unit.dimensions["Region"], 3),
                "SemanticOptions": semantic_options_for(unit, best_symbol, best_site, best_region),
                "NextEmpiricalTest": next_test_for(unit, str(best["Dimension"]), str(best["Category"])),
                "ExampleTexts": "; ".join(unit.examples[:5]),
            }
        )

    rows.sort(
        key=lambda row: (
            {"StrongOnomasticAnchor": 0, "CrossFramePhoneticAnchor": 1, "AffixOrFormulaAnchor": 2}.get(
                str(row["TestClass"]),
                3,
            ),
            {"Strong": 0, "Moderate": 1, "Unresolved": 2, "Exploratory": 3}.get(
                str(row["BestContextStrength"]),
                4,
            ),
            -ffloat(str(row["BestContextScore"])),
            str(row["Unit"]),
        )
    )
    return rows


def build_iconography_matrix(rows: list[dict[str, str]]) -> list[dict[str, object]]:
    matrix: dict[tuple[str, str], Counter[str]] = defaultdict(Counter)
    for row in rows:
        dims = context_dimensions(row)
        symbol = dims["Symbol"]
        if symbol == UNKNOWN:
            continue
        frame = dims["SemanticFrame"]
        matrix[(symbol, frame)]["count"] += 1
    out: list[dict[str, object]] = []
    symbol_totals: Counter[str] = Counter()
    frame_totals: Counter[str] = Counter()
    for (symbol, frame), counter in matrix.items():
        symbol_totals[symbol] += counter["count"]
        frame_totals[frame] += counter["count"]
    total = sum(symbol_totals.values())
    for (symbol, frame), counter in matrix.items():
        count = counter["count"]
        expected = symbol_totals[symbol] * frame_totals[frame] / total if total else 0.0
        lift = count / expected if expected else 0.0
        out.append(
            {
                "Symbol": symbol,
                "SemanticFrame": frame,
                "Count": count,
                "SymbolTotal": symbol_totals[symbol],
                "FrameTotal": frame_totals[frame],
                "Expected": round(expected, 3),
                "Lift": round(lift, 3),
            }
        )
    out.sort(key=lambda row: (-ffloat(str(row["Lift"])), -fint(str(row["Count"])), str(row["Symbol"])))
    return out


def build_summary(
    candidate_count: int,
    units: dict[str, UnitContext],
    correlations: list[dict[str, object]],
    semantic_candidates: list[dict[str, object]],
    iconography: Counter[str],
) -> list[dict[str, object]]:
    strong_corr = sum(
        1
        for row in correlations
        if row["Strength"] == "Strong" and row["TestClass"] in PRIORITY_CLASSES
    )
    moderate_corr = sum(
        1
        for row in correlations
        if row["Strength"] == "Moderate" and row["TestClass"] in PRIORITY_CLASSES
    )
    strong_onomastic = sum(1 for unit in units.values() if unit.test_class == "StrongOnomasticAnchor")
    symbol_linked = sum(
        1
        for row in semantic_candidates
        if row["BestContextDimension"] == "Symbol" and row["BestContextStrength"] in {"Strong", "Moderate"}
    )
    return [
        {
            "Metric": "Ready reconstructions tested",
            "Value": candidate_count,
            "Note": "Medium/high phonetic-readiness inscriptions with structural context.",
        },
        {
            "Metric": "Reading units profiled",
            "Value": len(units),
            "Note": "Units from the phonetic bootstrap testbench observed in ready rows.",
        },
        {
            "Metric": "Strong onomastic units profiled",
            "Value": strong_onomastic,
            "Note": "Prime-entity fillers suitable for proper-name style testing.",
        },
        {
            "Metric": "Usable iconography labels",
            "Value": iconography["usable"],
            "Note": "Ready reconstructions with non-empty, non-dash symbol labels.",
        },
        {
            "Metric": "Unknown iconography labels",
            "Value": iconography["unknown"],
            "Note": "Rows where iconographic context remains unavailable.",
        },
        {
            "Metric": "Strong context associations",
            "Value": strong_corr,
            "Note": "Unit/category links with repeated support, high lift, and high score.",
        },
        {
            "Metric": "Moderate context associations",
            "Value": moderate_corr,
            "Note": "Promising but less secure unit/category links.",
        },
        {
            "Metric": "Symbol-linked semantic candidates",
            "Value": symbol_linked,
            "Note": "Candidate units where iconography should be inspected first.",
        },
        {
            "Metric": "Semantic candidates exported",
            "Value": len(semantic_candidates),
            "Note": "Ranked unit-level semantic test plans.",
        },
    ]


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


def write_latex_summary(
    path: Path,
    summary_rows: list[dict[str, object]],
    semantic_candidates: list[dict[str, object]],
    correlations: list[dict[str, object]],
) -> None:
    top_candidates = [
        {
            "Unit": row["Unit"],
            "Abstract": row["AbstractUnit"],
            "Role": row["Role"],
            "Best context": f"{row['BestContextDimension']}={row['BestContextCategory']}",
            "Strength": row["BestContextStrength"],
        }
        for row in semantic_candidates[:8]
    ]
    top_correlations = [
        {
            "Unit": row["Unit"],
            "Dimension": row["Dimension"],
            "Category": row["Category"],
            "Count": row["Count"],
            "Lift": row["Lift"],
            "Strength": row["Strength"],
        }
        for row in correlations
        if row["Strength"] in {"Strong", "Moderate"} and row["TestClass"] in PRIORITY_CLASSES
    ][:10]
    text = r"""\section{Semantic Context Triangulation}

\subsection{Purpose}

This generated note connects the structural and abstract phonetic models to external corpus metadata: site, region, artifact type, material, and iconographic symbol label. It is a semantic testbench, not a translation stage.

\subsection{Summary}

\begin{table}[htbp]
\centering
""" + latex_table(summary_rows, ["Metric", "Value"], ["p{0.56\\textwidth}", "r"]) + r"""
\caption{Semantic context triangulation summary.}
\end{table}

\subsection{Top Semantic Candidates}

\begin{table}[htbp]
\centering
\footnotesize
""" + latex_table(top_candidates, ["Unit", "Abstract", "Role", "Best context", "Strength"]) + r"""
\caption{Highest-priority semantic context tests.}
\end{table}

\subsection{Strong and Moderate Context Associations}

\begin{table}[htbp]
\centering
\footnotesize
""" + latex_table(top_correlations, ["Unit", "Dimension", "Category", "Count", "Lift", "Strength"]) + r"""
\caption{Context associations that should be checked against artifact images.}
\end{table}
"""
    path.write_text(text, encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--outputs", default="outputs", help="Directory containing model outputs")
    args = parser.parse_args()

    out_dir = Path(args.outputs)
    structural_rows = candidate_rows(read_csv(out_dir / "structural_reconstructions.csv"))
    unit_metadata = load_unit_metadata(out_dir / "phonetic_reading_units.csv")
    units, baselines, iconography = build_contexts(structural_rows, unit_metadata)
    profiles = build_profiles(units)
    correlations = build_correlations(units, baselines, len(structural_rows))
    semantic_candidates = build_semantic_candidates(units, correlations)
    iconography_matrix = build_iconography_matrix(structural_rows)
    summary = build_summary(len(structural_rows), units, correlations, semantic_candidates, iconography)

    write_csv(out_dir / "semantic_context_summary.csv", summary, ["Metric", "Value", "Note"])
    write_csv(
        out_dir / "anchor_context_profiles.csv",
        profiles,
        [
            "Unit",
            "AbstractUnit",
            "Role",
            "TestClass",
            "PhoneticScore",
            "Occurrences",
            "TextCount",
            "TopRegion",
            "TopSite",
            "TopSymbol",
            "TopType",
            "TopMaterial",
            "Frames",
            "SemanticFrames",
            "ExampleTexts",
        ],
    )
    write_csv(
        out_dir / "anchor_context_correlations.csv",
        correlations,
        [
            "Unit",
            "AbstractUnit",
            "Role",
            "TestClass",
            "Dimension",
            "Category",
            "Count",
            "UnitOccurrences",
            "BaselineCount",
            "Expected",
            "Lift",
            "Log2Lift",
            "AssociationScore",
            "Strength",
        ],
    )
    write_csv(
        out_dir / "semantic_reconstruction_candidates.csv",
        semantic_candidates,
        [
            "Unit",
            "AbstractUnit",
            "Role",
            "TestClass",
            "PhoneticScore",
            "Occurrences",
            "BestContextDimension",
            "BestContextCategory",
            "BestContextStrength",
            "BestContextScore",
            "TopSymbol",
            "TopSite",
            "TopRegion",
            "SemanticOptions",
            "NextEmpiricalTest",
            "ExampleTexts",
        ],
    )
    write_csv(
        out_dir / "iconography_semantic_matrix.csv",
        iconography_matrix,
        ["Symbol", "SemanticFrame", "Count", "SymbolTotal", "FrameTotal", "Expected", "Lift"],
    )
    write_latex_summary(
        out_dir / "semantic_context_triangulation.tex",
        summary,
        semantic_candidates,
        correlations,
    )

    print("Wrote semantic context triangulation outputs:")
    for name in [
        "semantic_context_summary.csv",
        "anchor_context_profiles.csv",
        "anchor_context_correlations.csv",
        "semantic_reconstruction_candidates.csv",
        "iconography_semantic_matrix.csv",
        "semantic_context_triangulation.tex",
    ]:
        print(f"  - {out_dir / name}")


if __name__ == "__main__":
    main()
