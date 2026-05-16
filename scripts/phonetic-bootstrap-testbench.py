#!/usr/bin/env python3
"""Build an abstract phonetic bootstrap testbench.

This stage does not assign phonetic values to Indus signs. It builds the
controlled environment needed to test future values: abstract sign variables,
reusable filler units, minimal alternation tests, and sentence-like structural
reconstructions that any proposed reading must satisfy.
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


@dataclass
class UnitEvidence:
    filler: str
    tokens: tuple[str, ...]
    occurrences: int = 0
    text_ids: set[str] = field(default_factory=set)
    sites: Counter[str] = field(default_factory=Counter)
    frames: Counter[str] = field(default_factory=Counter)
    semantic_frames: Counter[str] = field(default_factory=Counter)
    roles: Counter[str] = field(default_factory=Counter)
    examples: list[str] = field(default_factory=list)
    confidence_sum: float = 0.0


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
        filler = filler.strip()
        if "|" in frame:
            left, right = frame.split("|", 1)
        else:
            left, right = "", ""
        tokens = tuple(sign_tokens(filler))
        if not tokens:
            continue
        slots.append(
            {
                "frame": frame,
                "left": left,
                "right": right,
                "filler": "-".join(tokens),
                "tokens": tokens,
                "position": position.strip(),
            }
        )
    return slots


def dominant(counter: Counter[str], default: str = "") -> str:
    if not counter:
        return default
    return counter.most_common(1)[0][0]


def top_counter(counter: Counter[str], limit: int = 5) -> str:
    return "; ".join(f"{key}:{value}" for key, value in counter.most_common(limit))


def infer_unit_role(frame: str, semantic_frame: str) -> str:
    left, right = frame.split("|", 1) if "|" in frame else ("", "")
    if frame == "002|740":
        return "PrimeEntityFiller"
    if left == START:
        return "InitialFiller"
    if right == END:
        return "TerminalFiller"
    if right in {"740", "520", "400", "151", "527"}:
        return "PreTerminalFiller"
    if semantic_frame.startswith("NameLike"):
        return "NameLikeFiller"
    return "SlotFiller"


def controlled_sentence_gloss(semantic_frame: str) -> str:
    glosses = {
        "PrimeEntitySealFormula": "seal formula: classifier/title plus entity filler plus terminal/final marker",
        "PrimeEntityAdministrativeFormula": "administrative formula: entity filler embedded in a longer control phrase",
        "ClassifierSlotTerminalFormula": "classifier formula: initial class/title plus slot filler plus terminal marker",
        "InitialClassifierFormula": "initial classifier/title followed by a short formula",
        "ClassifierTerminalFormula": "classifier/title plus terminal marker",
        "NameLikeTerminalFormula": "name-like block followed by a terminal marker",
        "TerminalFormula": "short terminal label, title, suffix, or object marker",
        "LowEvidenceSequence": "unresolved sequence with insufficient structural evidence",
    }
    return glosses.get(semantic_frame, "unresolved formula")


def functional_class(proto_gloss: str) -> str:
    if "INITIAL_TITLE_OR_CLASSIFIER" in proto_gloss:
        return "CLASSIFIER"
    if "TERMINAL_TITLE_OR_SUFFIX" in proto_gloss:
        return "TERMINAL"
    if "LEADING_FORMULA_MARKER" in proto_gloss or "CLOSING_FORMULA_MARKER" in proto_gloss:
        return "FORMULA_MARKER"
    if "SLOT_INITIAL_MODIFIER" in proto_gloss or "SLOT_FINAL_MODIFIER" in proto_gloss:
        return "SLOT_MODIFIER"
    return "ROOT_OR_UNRESOLVED"


def variable_prefix(func_class: str) -> str:
    return {
        "CLASSIFIER": "C",
        "TERMINAL": "T",
        "FORMULA_MARKER": "M",
        "SLOT_MODIFIER": "A",
        "ROOT_OR_UNRESOLVED": "R",
    }[func_class]


def reading_constraint(func_class: str) -> str:
    if func_class == "CLASSIFIER":
        return "must behave like an initial title, classifier, or determinative in matching frames"
    if func_class == "TERMINAL":
        return "must behave like a terminal title, suffix, or formula ending across seals"
    if func_class == "FORMULA_MARKER":
        return "must remain formulaic across repeated contexts before phonetic value is proposed"
    if func_class == "SLOT_MODIFIER":
        return "must explain slot alternations without breaking frame identity"
    return "must be tested as a possible lexical root or unresolved sign"


def make_variable_map(
    rows: list[dict[str, str]],
    proto_glosses: dict[str, str],
) -> tuple[dict[str, str], list[dict[str, object]]]:
    sign_counts: Counter[str] = Counter()
    role_contexts: dict[str, Counter[str]] = defaultdict(Counter)
    semantic_contexts: dict[str, Counter[str]] = defaultdict(Counter)

    for row in rows:
        semantic = row.get("SemanticFrame", "")
        tokens = sign_tokens(row.get("ReadingTokens"))
        sign_counts.update(tokens)
        for token in tokens:
            semantic_contexts[token][semantic] += 1
        for slot in parse_slot_fillers(row.get("SlotFillers")):
            role = infer_unit_role(str(slot["frame"]), semantic)
            for token in slot["tokens"]:
                role_contexts[token][role] += 1

    all_signs = set(sign_counts) | set(proto_glosses)
    class_order = {
        "CLASSIFIER": 0,
        "TERMINAL": 1,
        "FORMULA_MARKER": 2,
        "SLOT_MODIFIER": 3,
        "ROOT_OR_UNRESOLVED": 4,
    }
    ordered = sorted(
        all_signs,
        key=lambda sign: (
            class_order[functional_class(proto_glosses.get(sign, ""))],
            -sign_counts[sign],
            sign,
        ),
    )
    counters: Counter[str] = Counter()
    variable_map: dict[str, str] = {}
    rows_out: list[dict[str, object]] = []

    for sign in ordered:
        func = functional_class(proto_glosses.get(sign, ""))
        counters[func] += 1
        variable = f"{variable_prefix(func)}{counters[func]:02d}"
        variable_map[sign] = variable
        rows_out.append(
            {
                "Sign": sign,
                "Variable": variable,
                "FunctionalClass": func,
                "ProtoGloss": proto_glosses.get(sign, "UNRESOLVED"),
                "CountInReadyTexts": sign_counts[sign],
                "RoleContexts": top_counter(role_contexts[sign]),
                "SemanticFrames": top_counter(semantic_contexts[sign]),
                "ReadingConstraint": reading_constraint(func),
            }
        )

    return variable_map, rows_out


def abstract_sequence(tokens: tuple[str, ...] | list[str], variable_map: dict[str, str]) -> str:
    return "-".join(variable_map.get(token, "R??") for token in tokens)


def test_class_for_unit(
    unit: UnitEvidence,
    minimal_count: int,
    reuse_frame_count: int,
) -> str:
    role = dominant(unit.roles)
    site_count = len(unit.sites)
    frame_count = max(len(unit.frames), reuse_frame_count)
    if role == "PrimeEntityFiller" and site_count >= 2 and minimal_count >= 1:
        return "StrongOnomasticAnchor"
    if frame_count >= 3 and site_count >= 2 and minimal_count >= 1:
        return "CrossFramePhoneticAnchor"
    if role in {"InitialFiller", "TerminalFiller", "PreTerminalFiller"} and frame_count >= 2:
        return "AffixOrFormulaAnchor"
    if role == "PrimeEntityFiller":
        return "PrimeEntityContextNeeded"
    return "ControlOrLowPriority"


def unit_hypothesis(role: str, test_class: str) -> str:
    if test_class == "StrongOnomasticAnchor":
        return "test as a proper-name, title, office, place, or lineage unit across all seal contexts"
    if test_class == "CrossFramePhoneticAnchor":
        return "test whether the same sound-bearing unit survives frame changes"
    if test_class == "AffixOrFormulaAnchor":
        return "test as a suffix, prefix, title marker, classifier, or formula morpheme"
    if role == "PrimeEntityFiller":
        return "collect image and site context before proposing lexical or phonetic value"
    return "retain as control evidence until stronger semantic context appears"


def score_unit(
    unit: UnitEvidence,
    max_occurrences: int,
    minimal_count: int,
    reuse_frame_count: int,
) -> float:
    occurrence_score = math.log1p(unit.occurrences) / math.log1p(max_occurrences or 1)
    frame_score = min(max(len(unit.frames), reuse_frame_count) / 6.0, 1.0)
    site_score = min(len(unit.sites) / 5.0, 1.0)
    minimal_score = min(minimal_count / 5.0, 1.0)
    role = dominant(unit.roles)
    role_score = {
        "PrimeEntityFiller": 1.0,
        "NameLikeFiller": 0.9,
        "InitialFiller": 0.75,
        "TerminalFiller": 0.75,
        "PreTerminalFiller": 0.7,
        "SlotFiller": 0.55,
    }.get(role, 0.5)
    semantic_score = 0.4
    if unit.semantic_frames["PrimeEntitySealFormula"]:
        semantic_score = 1.0
    elif unit.semantic_frames["NameLikeTerminalFormula"]:
        semantic_score = 0.85
    elif unit.semantic_frames["TerminalFormula"]:
        semantic_score = 0.7
    avg_conf = unit.confidence_sum / max(len(unit.text_ids), 1)

    score = (
        0.18 * occurrence_score
        + 0.18 * frame_score
        + 0.16 * site_score
        + 0.16 * minimal_score
        + 0.16 * role_score
        + 0.10 * semantic_score
        + 0.06 * avg_conf
    )
    return round(score, 3)


def build_minimal_lookup(rows: list[dict[str, str]]) -> tuple[dict[str, int], dict[str, list[str]]]:
    counts: dict[str, int] = defaultdict(int)
    examples: dict[str, list[str]] = defaultdict(list)
    for row in rows:
        frame = row.get("Frame", "")
        filler_a = row.get("FillerA", "")
        filler_b = row.get("FillerB", "")
        relation = row.get("Relation", "")
        combined = fint(row.get("CombinedCount"), 1)
        for filler, other in ((filler_a, filler_b), (filler_b, filler_a)):
            if not filler:
                continue
            counts[filler] += combined
            if len(examples[filler]) < 6:
                examples[filler].append(f"{frame}:{filler}->{other}({relation})")
    return counts, examples


def load_proto_glosses(path: Path) -> dict[str, str]:
    rows = read_csv(path)
    return {row.get("Sign", ""): row.get("ProtoGloss", "") for row in rows if row.get("Sign")}


def build_unit_rows(
    candidate_rows: list[dict[str, str]],
    cross_reuse_rows: list[dict[str, str]],
    minimal_counts: dict[str, int],
    minimal_examples: dict[str, list[str]],
    variable_map: dict[str, str],
) -> tuple[list[dict[str, object]], dict[str, UnitEvidence]]:
    units: dict[str, UnitEvidence] = {}

    for row in candidate_rows:
        semantic = row.get("SemanticFrame", "")
        confidence = ffloat(row.get("ReconstructionConfidence"))
        site = row.get("Site", "")
        text_id = row.get("TextId", "")
        cisi = row.get("CISI", "")
        for slot in parse_slot_fillers(row.get("SlotFillers")):
            filler = str(slot["filler"])
            tokens = tuple(slot["tokens"])
            frame = str(slot["frame"])
            role = infer_unit_role(frame, semantic)
            if filler not in units:
                units[filler] = UnitEvidence(filler=filler, tokens=tokens)
            unit = units[filler]
            unit.occurrences += 1
            unit.text_ids.add(text_id)
            unit.sites[site or "Unknown"] += 1
            unit.frames[frame] += 1
            unit.semantic_frames[semantic] += 1
            unit.roles[role] += 1
            unit.confidence_sum += confidence
            if len(unit.examples) < 8:
                unit.examples.append(f"{cisi or text_id}:{frame}")

    reuse_map: dict[str, dict[str, str]] = {}
    for row in cross_reuse_rows:
        filler = row.get("Filler", "")
        if filler:
            reuse_map[filler] = row

    max_occurrences = max((unit.occurrences for unit in units.values()), default=1)
    rows_out: list[dict[str, object]] = []
    for filler, unit in units.items():
        reuse_frame_count = fint(reuse_map.get(filler, {}).get("FrameCount"), len(unit.frames))
        minimal_count = minimal_counts.get(filler, 0)
        role = dominant(unit.roles)
        test_class = test_class_for_unit(unit, minimal_count, reuse_frame_count)
        score = score_unit(unit, max_occurrences, minimal_count, reuse_frame_count)
        rows_out.append(
            {
                "Unit": filler,
                "AbstractUnit": abstract_sequence(unit.tokens, variable_map),
                "UnitLength": len(unit.tokens),
                "Role": role,
                "TestClass": test_class,
                "Score": score,
                "Occurrences": unit.occurrences,
                "CandidateTextCount": len(unit.text_ids),
                "FrameCount": max(len(unit.frames), reuse_frame_count),
                "SiteCount": len(unit.sites),
                "Frames": top_counter(unit.frames, 8),
                "SemanticFrames": top_counter(unit.semantic_frames, 6),
                "Sites": top_counter(unit.sites, 6),
                "MinimalPairCount": minimal_count,
                "MinimalPairExamples": "; ".join(minimal_examples.get(filler, [])[:4]),
                "ExampleTexts": "; ".join(unit.examples[:6]),
                "HypothesisToTest": unit_hypothesis(role, test_class),
            }
        )

    rows_out.sort(
        key=lambda row: (
            -ffloat(str(row["Score"])),
            -fint(str(row["SiteCount"])),
            -fint(str(row["FrameCount"])),
            str(row["Unit"]),
        )
    )
    return rows_out, units


def build_abstract_reconstructions(
    candidate_rows: list[dict[str, str]],
    variable_map: dict[str, str],
) -> list[dict[str, object]]:
    rows_out: list[dict[str, object]] = []
    for row in candidate_rows:
        tokens = sign_tokens(row.get("ReadingTokens"))
        semantic = row.get("SemanticFrame", "")
        rows_out.append(
            {
                "TextId": row.get("TextId", ""),
                "CISI": row.get("CISI", ""),
                "Site": row.get("Site", ""),
                "Type": row.get("Type", ""),
                "ReadingTokens": "-".join(tokens),
                "AbstractSigns": abstract_sequence(tokens, variable_map),
                "SemanticFrame": semantic,
                "ControlledSentenceGloss": controlled_sentence_gloss(semantic),
                "StructuralParse": row.get("StructuralParse", ""),
                "SlotFillers": row.get("SlotFillers", ""),
                "ReconstructionConfidence": row.get("ReconstructionConfidence", ""),
                "PhoneticReadiness": row.get("PhoneticReadiness", ""),
                "PhoneticTest": row.get("NextTest", ""),
            }
        )
    rows_out.sort(
        key=lambda row: (
            {"High": 0, "Medium": 1}.get(str(row["PhoneticReadiness"]), 2),
            -ffloat(str(row["ReconstructionConfidence"])),
            str(row["CISI"]),
        )
    )
    return rows_out


def test_type(relation: str) -> str:
    if relation.startswith("Substitution"):
        return "Same-frame substitution"
    if relation.startswith("PrefixAddition"):
        return "Prefix addition"
    if relation.startswith("SuffixAddition"):
        return "Suffix addition"
    return "Minimal alternation"


def minimal_constraint(relation: str) -> str:
    if relation.startswith("Substitution"):
        return "same frame, same slot; any phonetic proposal must explain the contrast without changing the formula"
    if relation.startswith("PrefixAddition"):
        return "added initial sign may be prefix, classifier, allograph, numeral, or graphic modifier"
    if relation.startswith("SuffixAddition"):
        return "added final sign may be suffix, terminal marker, allograph, numeral, or graphic modifier"
    return "alternation must preserve the frame before a phonetic value is accepted"


def build_minimal_test_rows(
    rows: list[dict[str, str]],
    variable_map: dict[str, str],
    limit: int = 300,
) -> list[dict[str, object]]:
    out: list[dict[str, object]] = []
    for row in rows:
        filler_a = row.get("FillerA", "")
        filler_b = row.get("FillerB", "")
        tokens_a = tuple(sign_tokens(filler_a))
        tokens_b = tuple(sign_tokens(filler_b))
        relation = row.get("Relation", "")
        out.append(
            {
                "Frame": row.get("Frame", ""),
                "FillerA": filler_a,
                "AbstractA": abstract_sequence(tokens_a, variable_map),
                "FillerB": filler_b,
                "AbstractB": abstract_sequence(tokens_b, variable_map),
                "Relation": relation,
                "CombinedCount": row.get("CombinedCount", ""),
                "TestType": test_type(relation),
                "Constraint": minimal_constraint(relation),
            }
        )
    out.sort(key=lambda row: (-fint(str(row["CombinedCount"])), str(row["Frame"]), str(row["FillerA"])))
    return out[:limit]


def latex_table(rows: list[dict[str, object]], fields: list[str], widths: list[str] | None = None) -> str:
    if widths:
        spec = "".join(widths)
    else:
        spec = "l" * len(fields)
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
    unit_rows: list[dict[str, object]],
    abstract_rows: list[dict[str, object]],
    minimal_rows: list[dict[str, object]],
) -> None:
    top_units = [
        {
            "Unit": row["Unit"],
            "Abstract": row["AbstractUnit"],
            "Role": row["Role"],
            "Score": row["Score"],
            "Sites": row["SiteCount"],
            "Class": row["TestClass"],
        }
        for row in unit_rows[:8]
    ]
    examples = [
        {
            "Text": row["CISI"] or row["TextId"],
            "Site": row["Site"],
            "Frame": row["SemanticFrame"],
            "Abstract": row["AbstractSigns"],
        }
        for row in abstract_rows[:6]
    ]
    tests = [
        {
            "Frame": row["Frame"],
            "A": row["FillerA"],
            "B": row["FillerB"],
            "Relation": row["TestType"],
        }
        for row in minimal_rows[:8]
    ]

    text = r"""\section{Phonetic Bootstrap Testbench}

\subsection{Purpose}

This generated note formalizes a strictly abstract phonetic layer. Variables such as \texttt{C01}, \texttt{T01}, and \texttt{R01} are not sound values. They are placeholders for signs that may later receive phonetic, morphemic, or classifier readings if external evidence supports them.

\subsection{Summary}

\begin{table}[htbp]
\centering
""" + latex_table(summary_rows, ["Metric", "Value"]) + r"""
\caption{Abstract phonetic bootstrap summary.}
\end{table}

\subsection{Top Reading Units}

\begin{table}[htbp]
\centering
\footnotesize
""" + latex_table(top_units, ["Unit", "Abstract", "Role", "Score", "Sites", "Class"]) + r"""
\caption{Highest-scoring sound-bearing or morpheme-bearing units for testing.}
\end{table}

\subsection{Abstract Sentence Reconstructions}

\begin{table}[htbp]
\centering
\footnotesize
""" + latex_table(examples, ["Text", "Site", "Frame", "Abstract"], ["l", "l", "l", "p{0.32\\textwidth}"]) + r"""
\caption{Examples of phonetic-variable reconstruction.}
\end{table}

\subsection{Minimal Alternation Tests}

\begin{table}[htbp]
\centering
\footnotesize
""" + latex_table(tests, ["Frame", "A", "B", "Relation"]) + r"""
\caption{Same-frame alternations that can constrain future readings.}
\end{table}
"""
    path.write_text(text, encoding="utf-8")


def build_summary(
    candidate_rows: list[dict[str, str]],
    variable_rows: list[dict[str, object]],
    unit_rows: list[dict[str, object]],
    abstract_rows: list[dict[str, object]],
    minimal_rows: list[dict[str, object]],
) -> list[dict[str, object]]:
    strong = sum(1 for row in unit_rows if row["TestClass"] == "StrongOnomasticAnchor")
    cross = sum(1 for row in unit_rows if row["TestClass"] == "CrossFramePhoneticAnchor")
    affix = sum(1 for row in unit_rows if row["TestClass"] == "AffixOrFormulaAnchor")
    prime = sum(1 for row in unit_rows if row["Role"] == "PrimeEntityFiller")
    return [
        {
            "Metric": "Medium/high ready reconstructions",
            "Value": len(candidate_rows),
            "Note": "Rows with structural evidence strong enough for phonetic test design.",
        },
        {
            "Metric": "Abstract sign variables",
            "Value": len(variable_rows),
            "Note": "Variables are functional placeholders, not readings.",
        },
        {
            "Metric": "Distinct reading units",
            "Value": len(unit_rows),
            "Note": "Slot fillers extracted from ready reconstructions.",
        },
        {
            "Metric": "Strong onomastic anchors",
            "Value": strong,
            "Note": "Prime-entity fillers with cross-site and minimal-pair evidence.",
        },
        {
            "Metric": "Cross-frame phonetic anchors",
            "Value": cross,
            "Note": "Reusable fillers in multiple frames with minimal alternations.",
        },
        {
            "Metric": "Affix/formula anchors",
            "Value": affix,
            "Note": "Initial, terminal, or pre-terminal units suited to morpheme tests.",
        },
        {
            "Metric": "Prime-entity fillers",
            "Value": prime,
            "Note": "Candidate owner/name/title/place/lineage units.",
        },
        {
            "Metric": "Abstract reconstructions exported",
            "Value": len(abstract_rows),
            "Note": "Sentence-like structural reconstructions with phonetic variables.",
        },
        {
            "Metric": "Minimal alternation tests",
            "Value": len(minimal_rows),
            "Note": "Top same-frame contrasts for falsification.",
        },
    ]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--outputs", default="outputs", help="Directory containing model outputs")
    args = parser.parse_args()

    out_dir = Path(args.outputs)
    structural_rows = read_csv(out_dir / "structural_reconstructions.csv")
    cross_reuse_rows = read_csv(out_dir / "slot_paradigm_cross_frame_reuse.csv")
    minimal_pair_rows = read_csv(out_dir / "slot_paradigm_minimal_pairs.csv")
    proto_glosses = load_proto_glosses(out_dir / "sign_proto_glosses.csv")

    candidate_rows = [
        row
        for row in structural_rows
        if row.get("PhoneticReadiness") in {"High", "Medium"}
        and ffloat(row.get("ReconstructionConfidence")) >= 0.5
    ]

    variable_map, variable_rows = make_variable_map(candidate_rows, proto_glosses)
    minimal_counts, minimal_examples = build_minimal_lookup(minimal_pair_rows)
    unit_rows, _units = build_unit_rows(
        candidate_rows,
        cross_reuse_rows,
        minimal_counts,
        minimal_examples,
        variable_map,
    )
    abstract_rows = build_abstract_reconstructions(candidate_rows, variable_map)
    minimal_rows = build_minimal_test_rows(minimal_pair_rows, variable_map)
    summary_rows = build_summary(candidate_rows, variable_rows, unit_rows, abstract_rows, minimal_rows)

    write_csv(
        out_dir / "phonetic_bootstrap_summary.csv",
        summary_rows,
        ["Metric", "Value", "Note"],
    )
    write_csv(
        out_dir / "phonetic_variable_map.csv",
        variable_rows,
        [
            "Sign",
            "Variable",
            "FunctionalClass",
            "ProtoGloss",
            "CountInReadyTexts",
            "RoleContexts",
            "SemanticFrames",
            "ReadingConstraint",
        ],
    )
    write_csv(
        out_dir / "phonetic_reading_units.csv",
        unit_rows,
        [
            "Unit",
            "AbstractUnit",
            "UnitLength",
            "Role",
            "TestClass",
            "Score",
            "Occurrences",
            "CandidateTextCount",
            "FrameCount",
            "SiteCount",
            "Frames",
            "SemanticFrames",
            "Sites",
            "MinimalPairCount",
            "MinimalPairExamples",
            "ExampleTexts",
            "HypothesisToTest",
        ],
    )
    write_csv(
        out_dir / "abstract_phonetic_reconstructions.csv",
        abstract_rows,
        [
            "TextId",
            "CISI",
            "Site",
            "Type",
            "ReadingTokens",
            "AbstractSigns",
            "SemanticFrame",
            "ControlledSentenceGloss",
            "StructuralParse",
            "SlotFillers",
            "ReconstructionConfidence",
            "PhoneticReadiness",
            "PhoneticTest",
        ],
    )
    write_csv(
        out_dir / "phonetic_minimal_tests.csv",
        minimal_rows,
        [
            "Frame",
            "FillerA",
            "AbstractA",
            "FillerB",
            "AbstractB",
            "Relation",
            "CombinedCount",
            "TestType",
            "Constraint",
        ],
    )
    write_latex_summary(
        out_dir / "phonetic_bootstrap_testbench.tex",
        summary_rows,
        unit_rows,
        abstract_rows,
        minimal_rows,
    )

    print("Wrote phonetic bootstrap testbench outputs:")
    for name in [
        "phonetic_bootstrap_summary.csv",
        "phonetic_variable_map.csv",
        "phonetic_reading_units.csv",
        "abstract_phonetic_reconstructions.csv",
        "phonetic_minimal_tests.csv",
        "phonetic_bootstrap_testbench.tex",
    ]:
        print(f"  - {out_dir / name}")


if __name__ == "__main__":
    main()
