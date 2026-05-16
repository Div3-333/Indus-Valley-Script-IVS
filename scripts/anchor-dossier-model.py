#!/usr/bin/env python3
"""Build evidence dossiers for the strongest decipherment anchors.

The language testbench says the fastest route forward is not a global reading,
but controlled case files for the strongest anchors. This script collects those
anchors, every ready occurrence, minimal-pair evidence, component reuse, and
allowed/blocked reading classes.
"""

from __future__ import annotations

import argparse
import csv
import re
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from pathlib import Path


TOKEN_RE = re.compile(r"(?<!\d)\d{3,4}(?!\d)")
PRIORITY_TEST_CLASSES = {"StrongOnomasticAnchor", "CrossFramePhoneticAnchor"}


@dataclass
class Anchor:
    unit: str
    abstract_unit: str
    role: str
    test_class: str
    phonetic_score: float
    best_context: str
    best_context_strength: str
    semantic_options: str
    next_test: str
    allowed_lexical_search: str = ""
    blocked_shortcut: str = ""
    min_evidence: str = ""
    occurrences: list[dict[str, object]] = field(default_factory=list)
    minimal_tests: list[dict[str, object]] = field(default_factory=list)
    component_links: Counter[str] = field(default_factory=Counter)


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


def sign_tokens(text: str | None) -> list[str]:
    return TOKEN_RE.findall(text or "")


def split_list(value: str | None) -> list[str]:
    if not value:
        return []
    return [part.strip() for part in value.split(";") if part.strip()]


def parse_slot_fillers(value: str | None) -> list[dict[str, str]]:
    slots: list[dict[str, str]] = []
    for part in split_list(value):
        if ":" not in part:
            continue
        frame, rest = part.split(":", 1)
        if "@" in rest:
            filler, position = rest.split("@", 1)
        else:
            filler, position = rest, ""
        tokens = sign_tokens(filler)
        if not tokens:
            continue
        slots.append(
            {
                "Frame": frame.strip(),
                "Filler": "-".join(tokens),
                "Position": position.strip(),
            }
        )
    return slots


def top_counter(counter: Counter[str], limit: int = 5) -> str:
    return "; ".join(f"{key}:{value}" for key, value in counter.most_common(limit))


def normalize_symbol(value: str | None) -> str:
    text = (value or "").strip()
    if not text or text == "-":
        return "Unknown"
    if text.startswith("Bull1"):
        return "Bull"
    aliases = {
        "Bult": "Bull/uncertain",
        "Bull": "Bull",
        "CompBull": "Composite Bull",
        "Elep": "Elephant",
        "Gavi": "Gavial",
        "Mult": "Composite/Multiple",
        "Othr": "Other",
        "Phyt": "Plant",
        "Rhin": "Rhinoceros",
    }
    return aliases.get(text, text)


def normalize_type(value: str | None) -> str:
    text = (value or "").strip()
    if not text or text == "-":
        return "Unknown"
    return text.split(":")[0]


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


def load_anchor_candidates(out_dir: Path) -> dict[str, Anchor]:
    semantic_rows = read_csv(out_dir / "semantic_reconstruction_candidates.csv")
    lexical_rows = {row["Unit"]: row for row in read_csv(out_dir / "lexical_reading_gate.csv")}

    anchors: dict[str, Anchor] = {}
    for row in semantic_rows:
        test_class = row.get("TestClass", "")
        role = row.get("Role", "")
        if test_class == "StrongOnomasticAnchor":
            keep = True
        elif test_class == "CrossFramePhoneticAnchor" and row.get("BestContextStrength") == "Strong":
            keep = True
        else:
            keep = False
        if not keep:
            continue
        unit = row["Unit"]
        lexical = lexical_rows.get(unit, {})
        anchors[unit] = Anchor(
            unit=unit,
            abstract_unit=row.get("AbstractUnit", ""),
            role=role,
            test_class=test_class,
            phonetic_score=ffloat(row.get("PhoneticScore")),
            best_context=f"{row.get('BestContextDimension', '')}={row.get('BestContextCategory', '')}",
            best_context_strength=row.get("BestContextStrength", ""),
            semantic_options=row.get("SemanticOptions", ""),
            next_test=row.get("NextEmpiricalTest", ""),
            allowed_lexical_search=lexical.get("AllowedLexicalSearch", ""),
            blocked_shortcut=lexical.get("BlockedShortcut", ""),
            min_evidence=lexical.get("MinimumEvidenceBeforeReading", ""),
        )
    return anchors


def collect_occurrences(anchors: dict[str, Anchor], structural_rows: list[dict[str, str]]) -> list[dict[str, object]]:
    occurrence_rows: list[dict[str, object]] = []
    for row in structural_rows:
        if row.get("PhoneticReadiness") not in {"High", "Medium"}:
            continue
        for slot in parse_slot_fillers(row.get("SlotFillers")):
            unit = slot["Filler"]
            if unit not in anchors:
                continue
            occurrence = {
                "Unit": unit,
                "TextId": row.get("TextId", ""),
                "CISI": row.get("CISI", ""),
                "Region": row.get("Region", ""),
                "Site": row.get("Site", ""),
                "Type": normalize_type(row.get("Type")),
                "Symbol": normalize_symbol(row.get("Symbol")),
                "Material": row.get("Material", ""),
                "Complete": row.get("Complete", ""),
                "ReadingTokens": row.get("ReadingTokens", ""),
                "Frame": slot["Frame"],
                "Position": slot["Position"],
                "SemanticFrame": row.get("SemanticFrame", ""),
                "ReconstructionConfidence": row.get("ReconstructionConfidence", ""),
                "StructuralParse": row.get("StructuralParse", ""),
            }
            anchors[unit].occurrences.append(occurrence)
            occurrence_rows.append(occurrence)
    occurrence_rows.sort(key=lambda row: (str(row["Unit"]), str(row["CISI"]), str(row["TextId"])))
    return occurrence_rows


def collect_minimal_tests(anchors: dict[str, Anchor], minimal_rows: list[dict[str, str]]) -> list[dict[str, object]]:
    anchor_units = set(anchors)
    anchor_components = {component for unit in anchor_units for component in unit.split("-")}
    out: list[dict[str, object]] = []
    for row in minimal_rows:
        filler_a = row.get("FillerA", "")
        filler_b = row.get("FillerB", "")
        tokens_a = set(filler_a.split("-")) if filler_a else set()
        tokens_b = set(filler_b.split("-")) if filler_b else set()
        direct = []
        component = []
        for unit in anchor_units:
            if unit in {filler_a, filler_b}:
                direct.append(unit)
        if not direct:
            shared = sorted((tokens_a | tokens_b) & anchor_components)
            component.extend(shared)
        if not direct and not component:
            continue
        linked_units = direct or [
            unit
            for unit in anchor_units
            if set(unit.split("-")) & set(component)
        ]
        for unit in linked_units:
            evidence_type = "DirectAnchorAlternation" if unit in direct else "ComponentAlternation"
            test = {
                "Unit": unit,
                "EvidenceType": evidence_type,
                "Frame": row.get("Frame", ""),
                "FillerA": filler_a,
                "AbstractA": row.get("AbstractA", ""),
                "FillerB": filler_b,
                "AbstractB": row.get("AbstractB", ""),
                "Relation": row.get("Relation", ""),
                "CombinedCount": row.get("CombinedCount", ""),
                "Constraint": row.get("Constraint", ""),
            }
            anchors[unit].minimal_tests.append(test)
            out.append(test)
    out.sort(key=lambda row: (str(row["Unit"]), 0 if row["EvidenceType"] == "DirectAnchorAlternation" else 1, -fint(str(row["CombinedCount"]))))
    return out


def component_position(tokens: list[str], index: int) -> str:
    if len(tokens) == 1:
        return "standalone"
    if index == 0:
        return "initial"
    if index == len(tokens) - 1:
        return "final"
    return "internal"


def component_interpretation(sign: str, positions: Counter[str], variable_class: str) -> str:
    if positions["standalone"] and (positions["final"] or positions["internal"]):
        return "root-like component; appears independently and inside compounds"
    if positions["initial"] and variable_class in {"SLOT_MODIFIER", "FORMULA_MARKER"}:
        return "prefix/title/classifier-like component"
    if positions["final"] and variable_class in {"SLOT_MODIFIER", "TERMINAL", "FORMULA_MARKER"}:
        return "suffix/final qualifier candidate"
    if variable_class == "ROOT_OR_UNRESOLVED":
        return "lexical root candidate"
    if variable_class == "SLOT_MODIFIER":
        return "slot-modifier component"
    return "unresolved component"


def build_component_graph(
    anchors: dict[str, Anchor],
    variable_rows: list[dict[str, str]],
) -> tuple[list[dict[str, object]], list[dict[str, object]]]:
    variable_map = {row["Sign"]: row for row in variable_rows}
    component_units: dict[str, set[str]] = defaultdict(set)
    component_positions: dict[str, Counter[str]] = defaultdict(Counter)
    component_neighbors: dict[str, Counter[str]] = defaultdict(Counter)
    edges: Counter[tuple[str, str]] = Counter()

    for unit, anchor in anchors.items():
        tokens = unit.split("-")
        for index, sign in enumerate(tokens):
            component_units[sign].add(unit)
            component_positions[sign][component_position(tokens, index)] += 1
            for other in tokens:
                if other != sign:
                    component_neighbors[sign][other] += 1
        for left, right in zip(tokens, tokens[1:]):
            edges[(left, right)] += 1

    component_rows: list[dict[str, object]] = []
    for sign, units in component_units.items():
        var = variable_map.get(sign, {})
        positions = component_positions[sign]
        variable_class = var.get("FunctionalClass", "UNMAPPED")
        component_rows.append(
            {
                "Sign": sign,
                "Variable": var.get("Variable", ""),
                "FunctionalClass": variable_class,
                "AnchorUnitCount": len(units),
                "AnchorUnits": "; ".join(sorted(units)),
                "Positions": top_counter(positions, 4),
                "Neighbors": top_counter(component_neighbors[sign], 6),
                "ComponentInterpretation": component_interpretation(sign, positions, variable_class),
                "ReadingConstraint": var.get("ReadingConstraint", ""),
            }
        )
    component_rows.sort(key=lambda row: (-fint(str(row["AnchorUnitCount"])), str(row["Sign"])))

    edge_rows = [
        {
            "LeftSign": left,
            "RightSign": right,
            "LeftVariable": variable_map.get(left, {}).get("Variable", ""),
            "RightVariable": variable_map.get(right, {}).get("Variable", ""),
            "AnchorCount": count,
            "AnchorUnits": "; ".join(sorted(unit for unit in anchors if f"{left}-{right}" in unit)),
        }
        for (left, right), count in edges.items()
    ]
    edge_rows.sort(key=lambda row: (-fint(str(row["AnchorCount"])), str(row["LeftSign"]), str(row["RightSign"])))
    return component_rows, edge_rows


def reading_class(anchor: Anchor) -> str:
    site_counts = Counter(str(row["Site"] or "Unknown") for row in anchor.occurrences)
    symbol_counts = Counter(str(row["Symbol"] or "Unknown") for row in anchor.occurrences)
    type_counts = Counter(str(row["Type"] or "Unknown") for row in anchor.occurrences)
    if anchor.unit == "240-482":
        return "institutional/admin label candidate"
    if anchor.role == "PrimeEntityFiller" and symbol_counts["Bull"] >= 2:
        return "emblem-linked name/title candidate"
    if anchor.role == "PrimeEntityFiller" and len(site_counts) >= 3:
        return "cross-site name/title/place candidate"
    if type_counts["TAB"] >= 3:
        return "administrative object/formula candidate"
    if anchor.role == "InitialFiller":
        return "classifier/title/prefix candidate"
    if anchor.role == "TerminalFiller":
        return "suffix/title/object-ending candidate"
    return "controlled lexical candidate"


def dossier_confidence(anchor: Anchor) -> float:
    occurrence_score = min(len(anchor.occurrences) / 8.0, 1.0)
    minimal_score = min(len(anchor.minimal_tests) / 8.0, 1.0)
    context_score = 1.0 if anchor.best_context_strength == "Strong" else 0.72 if anchor.best_context_strength == "Moderate" else 0.45
    class_score = 1.0 if anchor.test_class == "StrongOnomasticAnchor" else 0.76
    score = 0.30 * occurrence_score + 0.20 * minimal_score + 0.25 * context_score + 0.15 * class_score + 0.10 * anchor.phonetic_score
    return round(score, 3)


def build_dossiers(anchors: dict[str, Anchor]) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for anchor in anchors.values():
        site_counts = Counter(str(row["Site"] or "Unknown") for row in anchor.occurrences)
        symbol_counts = Counter(str(row["Symbol"] or "Unknown") for row in anchor.occurrences)
        type_counts = Counter(str(row["Type"] or "Unknown") for row in anchor.occurrences)
        frame_counts = Counter(str(row["Frame"]) for row in anchor.occurrences)
        semantic_counts = Counter(str(row["SemanticFrame"]) for row in anchor.occurrences)
        direct_tests = sum(1 for row in anchor.minimal_tests if row["EvidenceType"] == "DirectAnchorAlternation")
        component_tests = sum(1 for row in anchor.minimal_tests if row["EvidenceType"] == "ComponentAlternation")
        rows.append(
            {
                "Unit": anchor.unit,
                "AbstractUnit": anchor.abstract_unit,
                "Role": anchor.role,
                "TestClass": anchor.test_class,
                "ReadingClass": reading_class(anchor),
                "DossierConfidence": dossier_confidence(anchor),
                "OccurrenceCount": len(anchor.occurrences),
                "DirectMinimalTests": direct_tests,
                "ComponentMinimalTests": component_tests,
                "BestContext": anchor.best_context,
                "BestContextStrength": anchor.best_context_strength,
                "TopSites": top_counter(site_counts),
                "TopSymbols": top_counter(symbol_counts),
                "TopTypes": top_counter(type_counts),
                "Frames": top_counter(frame_counts),
                "SemanticFrames": top_counter(semantic_counts),
                "AllowedLexicalSearch": anchor.allowed_lexical_search,
                "BlockedShortcut": anchor.blocked_shortcut,
                "NextTest": anchor.next_test,
            }
        )
    rows.sort(key=lambda row: (0 if row["TestClass"] == "StrongOnomasticAnchor" else 1, -ffloat(str(row["DossierConfidence"])), str(row["Unit"])))
    return rows


def build_reading_hypotheses(dossiers: list[dict[str, object]], component_rows: list[dict[str, object]]) -> list[dict[str, object]]:
    component_lookup = {row["Sign"]: row for row in component_rows}
    rows: list[dict[str, object]] = []
    for dossier in dossiers:
        unit = str(dossier["Unit"])
        tokens = unit.split("-")
        segmentation = []
        for token in tokens:
            component = component_lookup.get(token, {})
            interp = str(component.get("ComponentInterpretation", "unresolved component")).split(";")[0]
            segmentation.append(f"{token}={interp}")
        if unit == "176":
            hypothesis = "root-like entity name/title component; compare with 240-176"
        elif unit == "240-176":
            hypothesis = "240 may qualify or classify root-like 176"
        elif unit == "240-482":
            hypothesis = "240 may mark institutional/admin class; 482 may be local entity stem"
        elif unit == "235-222":
            hypothesis = "235 may be formula/title prefix; 222 may be entity stem"
        elif unit == "032-220":
            hypothesis = "032 may qualify 220 or mark a subtype in bull-seal context"
        elif unit == "235-840-032":
            hypothesis = "multi-part entity/title formula sharing 235 and 032 with other anchors"
        elif unit == "590-390":
            hypothesis = "compound name/title/place candidate with final formula-marker-like 390"
        else:
            hypothesis = str(dossier["ReadingClass"])
        rows.append(
            {
                "Unit": unit,
                "AbstractUnit": dossier["AbstractUnit"],
                "WorkingHypothesis": hypothesis,
                "SegmentationProbe": "; ".join(segmentation),
                "MustExplain": f"{dossier['OccurrenceCount']} occurrence(s); {dossier['BestContext']}; {dossier['Frames']}",
                "DisallowedShortcut": dossier["BlockedShortcut"],
                "Status": "Pre-phonetic; semantic reading class only",
            }
        )
    return rows


def summary_rows(dossiers: list[dict[str, object]], occurrence_rows: list[dict[str, object]], minimal_rows: list[dict[str, object]], component_rows: list[dict[str, object]]) -> list[dict[str, object]]:
    strong_onomastic = sum(1 for row in dossiers if row["TestClass"] == "StrongOnomasticAnchor")
    cross_frame = sum(1 for row in dossiers if row["TestClass"] == "CrossFramePhoneticAnchor")
    direct_tests = sum(1 for row in minimal_rows if row["EvidenceType"] == "DirectAnchorAlternation")
    component_tests = sum(1 for row in minimal_rows if row["EvidenceType"] == "ComponentAlternation")
    root_like = sum(1 for row in component_rows if str(row["ComponentInterpretation"]).startswith("root-like"))
    prefix_like = sum(1 for row in component_rows if str(row["ComponentInterpretation"]).startswith("prefix"))
    suffix_like = sum(1 for row in component_rows if str(row["ComponentInterpretation"]).startswith("suffix"))
    return [
        {"Metric": "Anchor dossiers", "Value": len(dossiers), "Note": "Strong onomastic plus strong-context cross-frame anchors."},
        {"Metric": "Strong onomastic dossiers", "Value": strong_onomastic, "Note": "Prime-entity fillers closest to proper-name tests."},
        {"Metric": "Cross-frame dossiers", "Value": cross_frame, "Note": "Non-prime anchors with strong context associations."},
        {"Metric": "Anchor occurrence rows", "Value": len(occurrence_rows), "Note": "Ready inscriptions gathered into case files."},
        {"Metric": "Direct minimal tests", "Value": direct_tests, "Note": "Minimal alternations where the anchor is directly present."},
        {"Metric": "Component minimal tests", "Value": component_tests, "Note": "Minimal alternations involving anchor components."},
        {"Metric": "Anchor components", "Value": len(component_rows), "Note": "Unique signs inside the dossier anchor units."},
        {"Metric": "Root-like components", "Value": root_like, "Note": "Components that appear independently and inside compounds."},
        {"Metric": "Prefix-like components", "Value": prefix_like, "Note": "Initial modifier/formula components in anchor units."},
        {"Metric": "Suffix-like components", "Value": suffix_like, "Note": "Final qualifier candidates in anchor units."},
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
    summary: list[dict[str, object]],
    dossiers: list[dict[str, object]],
    components: list[dict[str, object]],
    reading_hypotheses: list[dict[str, object]],
) -> None:
    top_dossiers = [
        {
            "Unit": row["Unit"],
            "Class": row["ReadingClass"],
            "Context": row["BestContext"],
            "Conf.": row["DossierConfidence"],
        }
        for row in dossiers[:10]
    ]
    top_components = [
        {
            "Sign": row["Sign"],
            "Variable": row["Variable"],
            "Units": row["AnchorUnits"],
            "Interpretation": row["ComponentInterpretation"],
        }
        for row in components[:8]
    ]
    top_hypotheses = [
        {
            "Unit": row["Unit"],
            "Working hypothesis": row["WorkingHypothesis"],
        }
        for row in reading_hypotheses[:8]
    ]
    text = r"""\section{Anchor Dossier Model}

\subsection{Purpose}

This generated note turns the strongest anchors into case files. Each dossier gathers occurrences, contexts, minimal alternations, component reuse, and lexical search gates. It is designed to move from structural and semantic compatibility toward controlled partial decipherment.

\subsection{Summary}

\begin{table}[htbp]
\centering
""" + latex_table(summary, ["Metric", "Value"], ["p{0.58\\textwidth}", "r"]) + r"""
\caption{Anchor dossier summary.}
\end{table}

\subsection{Top Dossiers}

\begin{table}[htbp]
\centering
\footnotesize
""" + latex_table(top_dossiers, ["Unit", "Class", "Context", "Conf."], ["l", "p{0.36\\textwidth}", "p{0.28\\textwidth}", "r"]) + r"""
\caption{Highest-priority anchor dossiers.}
\end{table}

\subsection{Component Probe}

\begin{table}[htbp]
\centering
\footnotesize
""" + latex_table(top_components, ["Sign", "Variable", "Units", "Interpretation"], ["l", "l", "p{0.28\\textwidth}", "p{0.34\\textwidth}"]) + r"""
\caption{Recurring components inside anchor units.}
\end{table}

\subsection{Working Reading Classes}

\begin{table}[htbp]
\centering
\footnotesize
""" + latex_table(top_hypotheses, ["Unit", "Working hypothesis"], ["l", "p{0.72\\textwidth}"]) + r"""
\caption{Reading classes allowed by current evidence. These are not phonetic readings.}
\end{table}
"""
    path.write_text(text, encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--outputs", default="outputs", help="Directory containing model outputs")
    args = parser.parse_args()

    out_dir = Path(args.outputs)
    anchors = load_anchor_candidates(out_dir)
    occurrence_rows = collect_occurrences(anchors, read_csv(out_dir / "structural_reconstructions.csv"))
    minimal_rows = collect_minimal_tests(anchors, read_csv(out_dir / "phonetic_minimal_tests.csv"))
    component_rows, edge_rows = build_component_graph(anchors, read_csv(out_dir / "phonetic_variable_map.csv"))
    dossier_rows = build_dossiers(anchors)
    reading_rows = build_reading_hypotheses(dossier_rows, component_rows)
    summary = summary_rows(dossier_rows, occurrence_rows, minimal_rows, component_rows)

    write_csv(out_dir / "anchor_dossier_summary.csv", summary, ["Metric", "Value", "Note"])
    write_csv(
        out_dir / "anchor_dossiers.csv",
        dossier_rows,
        [
            "Unit",
            "AbstractUnit",
            "Role",
            "TestClass",
            "ReadingClass",
            "DossierConfidence",
            "OccurrenceCount",
            "DirectMinimalTests",
            "ComponentMinimalTests",
            "BestContext",
            "BestContextStrength",
            "TopSites",
            "TopSymbols",
            "TopTypes",
            "Frames",
            "SemanticFrames",
            "AllowedLexicalSearch",
            "BlockedShortcut",
            "NextTest",
        ],
    )
    write_csv(
        out_dir / "anchor_occurrence_evidence.csv",
        occurrence_rows,
        [
            "Unit",
            "TextId",
            "CISI",
            "Region",
            "Site",
            "Type",
            "Symbol",
            "Material",
            "Complete",
            "ReadingTokens",
            "Frame",
            "Position",
            "SemanticFrame",
            "ReconstructionConfidence",
            "StructuralParse",
        ],
    )
    write_csv(
        out_dir / "anchor_minimal_evidence.csv",
        minimal_rows,
        [
            "Unit",
            "EvidenceType",
            "Frame",
            "FillerA",
            "AbstractA",
            "FillerB",
            "AbstractB",
            "Relation",
            "CombinedCount",
            "Constraint",
        ],
    )
    write_csv(
        out_dir / "anchor_component_roles.csv",
        component_rows,
        [
            "Sign",
            "Variable",
            "FunctionalClass",
            "AnchorUnitCount",
            "AnchorUnits",
            "Positions",
            "Neighbors",
            "ComponentInterpretation",
            "ReadingConstraint",
        ],
    )
    write_csv(
        out_dir / "anchor_component_edges.csv",
        edge_rows,
        ["LeftSign", "RightSign", "LeftVariable", "RightVariable", "AnchorCount", "AnchorUnits"],
    )
    write_csv(
        out_dir / "anchor_reading_hypotheses.csv",
        reading_rows,
        [
            "Unit",
            "AbstractUnit",
            "WorkingHypothesis",
            "SegmentationProbe",
            "MustExplain",
            "DisallowedShortcut",
            "Status",
        ],
    )
    write_latex_summary(out_dir / "anchor_dossier_model.tex", summary, dossier_rows, component_rows, reading_rows)

    print("Wrote anchor dossier outputs:")
    for name in [
        "anchor_dossier_summary.csv",
        "anchor_dossiers.csv",
        "anchor_occurrence_evidence.csv",
        "anchor_minimal_evidence.csv",
        "anchor_component_roles.csv",
        "anchor_component_edges.csv",
        "anchor_reading_hypotheses.csv",
        "anchor_dossier_model.tex",
    ]:
        print(f"  - {out_dir / name}")


if __name__ == "__main__":
    main()
