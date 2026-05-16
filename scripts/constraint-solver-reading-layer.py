#!/usr/bin/env python3
"""Build constrained reading skeletons from the strongest anchor dossiers.

This is a pre-phonetic solver. It does not assign sound values or language
families. It ranks structural and semantic reading skeletons only when they
survive explicit order, context, minimal-pair, frame, and lexical-gate
constraints.
"""

from __future__ import annotations

import argparse
import csv
import re
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path


TOKEN_RE = re.compile(r"(?<!\d)\d{3,4}(?!\d)")


@dataclass(frozen=True)
class Component:
    sign: str
    variable: str
    functional_class: str
    anchor_units: str
    positions: Counter[str]
    interpretation: str
    constraint: str


@dataclass
class Candidate:
    unit: str
    abstract_unit: str
    role: str
    reading_class: str
    skeleton: str
    score: float
    status: str
    tier: str
    components: list[str]
    component_labels: list[str]
    dossier_confidence: float
    occurrence_count: int
    direct_minimal_tests: int
    component_minimal_tests: int
    context_score: float
    frame_purity: float
    minimal_score: float
    component_score: float
    best_context: str
    best_context_strength: str
    dominant_frame: str
    accepted_claims: str
    rejected_claims: str
    next_test: str
    hard_failures: list[str]
    warnings: list[str]


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


def parse_counter_text(value: str | None) -> Counter[str]:
    counter: Counter[str] = Counter()
    if not value:
        return counter
    for part in value.split(";"):
        part = part.strip()
        if not part or ":" not in part:
            continue
        key, count = part.rsplit(":", 1)
        counter[key.strip()] += fint(count)
    return counter


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


def load_components(out_dir: Path) -> dict[str, Component]:
    components: dict[str, Component] = {}
    for row in read_csv(out_dir / "anchor_component_roles.csv"):
        sign = row["Sign"]
        components[sign] = Component(
            sign=sign,
            variable=row.get("Variable", ""),
            functional_class=row.get("FunctionalClass", ""),
            anchor_units=row.get("AnchorUnits", ""),
            positions=parse_counter_text(row.get("Positions")),
            interpretation=row.get("ComponentInterpretation", ""),
            constraint=row.get("ReadingConstraint", ""),
        )
    return components


def label_component(component: Component | None, index: int, length: int) -> str:
    if component is None:
        return "UNRESOLVED_SIGN"
    interpretation = component.interpretation.lower()
    fclass = component.functional_class
    positions = component.positions

    if "prefix/title/classifier-like" in interpretation:
        return "QUALIFIER_TITLE_CLASSIFIER"
    if "lexical root" in interpretation:
        return "ENTITY_STEM"
    if "root-like component" in interpretation:
        return "ENTITY_STEM_OR_SUBTYPE"
    if "suffix/final qualifier" in interpretation:
        return "FINAL_QUALIFIER"

    if fclass == "CLASSIFIER":
        return "CLASSIFIER_TITLE"
    if fclass == "TERMINAL":
        return "TERMINAL_TITLE_SUFFIX"
    if fclass == "FORMULA_MARKER":
        if length > 1 and index == 0:
            return "FORMULA_TITLE_PREFIX"
        if length > 1 and index == length - 1:
            return "FINAL_FORMULA_MARKER"
        return "FORMULA_MARKER"
    if fclass == "SLOT_MODIFIER":
        if length > 1 and index == 0:
            return "QUALIFIER_MODIFIER"
        if length > 1 and index == length - 1:
            return "FINAL_MODIFIER"
        if positions.get("standalone"):
            return "ENTITY_OR_SLOT_MODIFIER"
        return "SLOT_MODIFIER"
    if fclass == "ROOT_OR_UNRESOLVED":
        return "ENTITY_STEM_CANDIDATE"
    return "UNRESOLVED_COMPONENT"


def skeleton_from_labels(labels: list[str], reading_class: str, role: str) -> str:
    if not labels:
        return "UNRESOLVED"
    if len(labels) == 1:
        label = labels[0]
        if "suffix/title/object-ending" in reading_class:
            return "TERMINAL_TITLE_OR_OBJECT_ENDING"
        if "classifier/title/prefix" in reading_class:
            return "CLASSIFIER_OR_TITLE_PREFIX"
        if "administrative object/formula" in reading_class:
            return "ADMINISTRATIVE_FORMULA_OPENER"
        if "ENTITY" in label:
            return "ENTITY_STEM"
        return label

    joined = " + ".join(labels)
    if labels[0] in {"QUALIFIER_TITLE_CLASSIFIER", "FORMULA_TITLE_PREFIX", "QUALIFIER_MODIFIER"}:
        if any(label.startswith("ENTITY_STEM") or label == "ENTITY_STEM_OR_SUBTYPE" for label in labels[1:]):
            if len(labels) > 2 and labels[-1] == "ENTITY_STEM_OR_SUBTYPE":
                return "QUALIFIER_TITLE_PREFIX + ENTITY_STEM + SUBTYPE_OR_SECOND_STEM"
            if labels[-1] in {"FINAL_QUALIFIER", "FINAL_MODIFIER", "FINAL_FORMULA_MARKER"} and len(labels) > 2:
                return "QUALIFIER_TITLE_PREFIX + ENTITY_STEM + FINAL_QUALIFIER"
            return "QUALIFIER_TITLE_PREFIX + ENTITY_STEM"
        if any("TERMINAL" in label for label in labels[1:]):
            return "ADMINISTRATIVE_OBJECT_FORMULA"
        if labels[-1] in {"FINAL_QUALIFIER", "FINAL_MODIFIER", "FINAL_FORMULA_MARKER"}:
            return "QUALIFIER_TITLE_PREFIX + FINAL_QUALIFIER"
    if labels[0] == "CLASSIFIER_TITLE":
        return "CLASSIFIER_TITLE + FINAL_QUALIFIER"
    if labels[-1] in {"FINAL_QUALIFIER", "FINAL_MODIFIER", "FINAL_FORMULA_MARKER"}:
        return "ENTITY_STEM + FINAL_QUALIFIER"
    return joined


def context_support(strength: str, occurrences: int) -> float:
    base = {
        "Strong": 1.0,
        "Moderate": 0.72,
        "Weak": 0.42,
    }.get(strength, 0.35)
    occurrence_bonus = clamp(occurrences / 10.0, 0.0, 1.0) * 0.15
    return clamp(base + occurrence_bonus)


def purity(counter: Counter[str], total: int) -> tuple[float, str]:
    if total <= 0 or not counter:
        return 0.0, ""
    key, value = counter.most_common(1)[0]
    return value / total, key


def minimal_support(direct: int, component: int) -> float:
    weighted = direct + component * 0.25
    return clamp(weighted / 12.0)


def component_support(labels: list[str]) -> float:
    if not labels:
        return 0.0
    strong = 0
    for label in labels:
        if label not in {"UNRESOLVED_SIGN", "UNRESOLVED_COMPONENT", "SLOT_MODIFIER"}:
            strong += 1
    return strong / len(labels)


def evaluate_constraints(
    unit: str,
    row: dict[str, str],
    components: dict[str, Component],
    labels: list[str],
    frame_purity_score: float,
    min_score: float,
) -> tuple[list[str], list[str], list[dict[str, object]]]:
    hard: list[str] = []
    warnings: list[str] = []
    checks: list[dict[str, object]] = []
    tokens = unit.split("-")

    def add_check(cid: str, constraint: str, severity: str, result: str, evidence: str) -> None:
        checks.append(
            {
                "Unit": unit,
                "ConstraintId": cid,
                "Constraint": constraint,
                "Severity": severity,
                "Result": result,
                "Evidence": evidence,
            }
        )

    order_failures: list[str] = []
    for index, sign in enumerate(tokens):
        component = components.get(sign)
        if not component:
            warnings.append(f"{sign} has no component role")
            continue
        interp = component.interpretation.lower()
        fclass = component.functional_class
        if "prefix/title/classifier-like" in interp and index != 0:
            order_failures.append(f"{sign} is prefix-like but occurs at position {index + 1}")
        if "suffix/final qualifier" in interp and len(tokens) > 1 and index != len(tokens) - 1:
            order_failures.append(f"{sign} is final-like but occurs before the end")
        if fclass == "CLASSIFIER" and len(tokens) > 1 and index != 0:
            order_failures.append(f"{sign} is classifier-like but not initial")

    if order_failures:
        hard.extend(order_failures)
        add_check("C1", "Component order must match prefix/root/suffix behavior.", "Hard", "FAIL", "; ".join(order_failures))
    else:
        add_check("C1", "Component order must match prefix/root/suffix behavior.", "Hard", "PASS", "No ordering contradiction detected.")

    context_strength = row.get("BestContextStrength", "")
    occurrences = fint(row.get("OccurrenceCount"))
    if context_strength == "Strong" or occurrences >= 5:
        add_check("C2", "Reading skeleton must be context-supported.", "Hard", "PASS", f"{context_strength} context; {occurrences} occurrence(s).")
    elif context_strength == "Moderate" and occurrences >= 2:
        warnings.append("context is moderate rather than strong")
        add_check("C2", "Reading skeleton must be context-supported.", "Soft", "WARN", f"{context_strength} context; {occurrences} occurrence(s).")
    else:
        hard.append("insufficient context support")
        add_check("C2", "Reading skeleton must be context-supported.", "Hard", "FAIL", f"{context_strength} context; {occurrences} occurrence(s).")

    if min_score >= 0.55:
        add_check("C3", "Minimal-pair or component alternation evidence should exist.", "Soft", "PASS", f"Minimal support score {min_score:.3f}.")
    elif fint(row.get("DirectMinimalTests")) > 0:
        warnings.append("direct minimal support exists but is still thin")
        add_check("C3", "Minimal-pair or component alternation evidence should exist.", "Soft", "WARN", f"Direct tests: {row.get('DirectMinimalTests')}.")
    else:
        warnings.append("minimal-pair support is indirect or absent")
        add_check("C3", "Minimal-pair or component alternation evidence should exist.", "Soft", "WARN", "No direct minimal tests.")

    if frame_purity_score >= 0.80:
        add_check("C4", "Anchor should stay stable in a dominant frame.", "Soft", "PASS", f"Frame purity {frame_purity_score:.3f}.")
    elif frame_purity_score >= 0.50:
        warnings.append("frame purity is mixed")
        add_check("C4", "Anchor should stay stable in a dominant frame.", "Soft", "WARN", f"Frame purity {frame_purity_score:.3f}.")
    else:
        warnings.append("frame evidence is diffuse")
        add_check("C4", "Anchor should stay stable in a dominant frame.", "Soft", "WARN", f"Frame purity {frame_purity_score:.3f}.")

    blocked = row.get("BlockedShortcut", "")
    if blocked:
        add_check("C5", "Lexical shortcuts must remain blocked until predictive.", "Hard", "PASS", blocked)
    else:
        warnings.append("lexical gate is missing")
        add_check("C5", "Lexical shortcuts must remain blocked until predictive.", "Soft", "WARN", "No blocked shortcut recorded.")

    add_check("C6", "No phonetic value may be assigned by this solver.", "Hard", "PASS", "All outputs are semantic/structural skeletons only.")
    if all(label in {"UNRESOLVED_SIGN", "UNRESOLVED_COMPONENT"} for label in labels):
        hard.append("all components unresolved")
        add_check("C7", "At least one component must have a functional role.", "Hard", "FAIL", "No component role available.")
    else:
        add_check("C7", "At least one component must have a functional role.", "Hard", "PASS", ", ".join(labels))

    return hard, warnings, checks


def status_from_score(score: float, hard: list[str], warnings: list[str]) -> tuple[str, str]:
    if hard:
        return "Hold: violates hard constraint", "Rejected/Hold"
    if score >= 0.86 and len(warnings) <= 1:
        return "Accepted pre-phonetic skeleton", "A"
    if score >= 0.74:
        return "Promising constrained skeleton", "B"
    if score >= 0.62:
        return "Exploratory constrained skeleton", "C"
    return "Hold: insufficient evidence", "Rejected/Hold"


def build_candidates(out_dir: Path) -> tuple[list[Candidate], list[dict[str, object]], list[dict[str, object]]]:
    components = load_components(out_dir)
    candidates: list[Candidate] = []
    constraint_rows: list[dict[str, object]] = []
    morpheme_rows: list[dict[str, object]] = []

    for row in read_csv(out_dir / "anchor_dossiers.csv"):
        unit = row["Unit"]
        tokens = unit.split("-")
        labels = [label_component(components.get(sign), index, len(tokens)) for index, sign in enumerate(tokens)]
        skeleton = skeleton_from_labels(labels, row.get("ReadingClass", ""), row.get("Role", ""))
        frames = parse_counter_text(row.get("Frames"))
        occurrence_count = fint(row.get("OccurrenceCount"))
        frame_purity_score, dominant_frame = purity(frames, occurrence_count)
        min_score = minimal_support(fint(row.get("DirectMinimalTests")), fint(row.get("ComponentMinimalTests")))
        comp_score = component_support(labels)
        ctx_score = context_support(row.get("BestContextStrength", ""), occurrence_count)
        dossier_conf = ffloat(row.get("DossierConfidence"))

        hard, warnings, checks = evaluate_constraints(row["Unit"], row, components, labels, frame_purity_score, min_score)
        score = clamp(
            dossier_conf * 0.42
            + ctx_score * 0.18
            + min_score * 0.16
            + frame_purity_score * 0.14
            + comp_score * 0.10
            - len(hard) * 0.25
            - min(len(warnings), 4) * 0.025
        )
        status, tier = status_from_score(score, hard, warnings)
        constraint_rows.extend(checks)

        accepted_claims = (
            f"{unit} may be modeled as {skeleton}; "
            f"context={row.get('BestContext', '')}; dominant frame={dominant_frame or 'mixed'}"
        )
        rejected_claims = "phonetic value; language-family value; icon-only animal equation; one-off lexical resemblance"

        for index, sign in enumerate(tokens):
            component = components.get(sign)
            morpheme_rows.append(
                {
                    "Unit": unit,
                    "Sign": sign,
                    "AbstractVariable": component.variable if component else "",
                    "Position": index + 1,
                    "UnitLength": len(tokens),
                    "ProposedRole": labels[index],
                    "FunctionalClass": component.functional_class if component else "",
                    "ComponentInterpretation": component.interpretation if component else "unresolved",
                    "OrderStatus": "FAIL" if any(sign in failure for failure in hard) else "PASS",
                    "ReadingConstraint": component.constraint if component else "no role available",
                }
            )

        candidates.append(
            Candidate(
                unit=unit,
                abstract_unit=row.get("AbstractUnit", ""),
                role=row.get("Role", ""),
                reading_class=row.get("ReadingClass", ""),
                skeleton=skeleton,
                score=score,
                status=status,
                tier=tier,
                components=tokens,
                component_labels=labels,
                dossier_confidence=dossier_conf,
                occurrence_count=occurrence_count,
                direct_minimal_tests=fint(row.get("DirectMinimalTests")),
                component_minimal_tests=fint(row.get("ComponentMinimalTests")),
                context_score=ctx_score,
                frame_purity=frame_purity_score,
                minimal_score=min_score,
                component_score=comp_score,
                best_context=row.get("BestContext", ""),
                best_context_strength=row.get("BestContextStrength", ""),
                dominant_frame=dominant_frame,
                accepted_claims=accepted_claims,
                rejected_claims=rejected_claims,
                next_test=row.get("NextTest", ""),
                hard_failures=hard,
                warnings=warnings,
            )
        )

    candidates.sort(key=lambda cand: (-cand.score, cand.unit))
    return candidates, constraint_rows, morpheme_rows


def replace_unit_tokens(reading_tokens: str, unit: str, skeleton: str) -> str:
    tokens = reading_tokens.split("-")
    unit_tokens = unit.split("-")
    if not tokens or not unit_tokens:
        return reading_tokens
    output: list[str] = []
    index = 0
    while index < len(tokens):
        if tokens[index : index + len(unit_tokens)] == unit_tokens:
            output.append(f"[{skeleton}:{unit}]")
            index += len(unit_tokens)
        else:
            output.append(tokens[index])
            index += 1
    return " ".join(output)


def clause_type(semantic_frame: str) -> str:
    if semantic_frame == "PrimeEntitySealFormula":
        return "seal/entity formula"
    if semantic_frame == "PrimeEntityAdministrativeFormula":
        return "administrative/entity formula"
    if semantic_frame == "TerminalFormula":
        return "object or closing formula"
    if semantic_frame == "ClassifierSlotTerminalFormula":
        return "classifier-title-terminal formula"
    if semantic_frame == "InitialClassifierFormula":
        return "initial classifier formula"
    return "low-evidence or mixed formula"


def build_clause_rows(out_dir: Path, candidates: list[Candidate]) -> list[dict[str, object]]:
    candidate_map = {candidate.unit: candidate for candidate in candidates if not candidate.hard_failures}
    rows: list[dict[str, object]] = []
    for row in read_csv(out_dir / "anchor_occurrence_evidence.csv"):
        unit = row["Unit"]
        candidate = candidate_map.get(unit)
        if not candidate:
            continue
        rows.append(
            {
                "Unit": unit,
                "TextId": row.get("TextId", ""),
                "CISI": row.get("CISI", ""),
                "Site": row.get("Site", ""),
                "Type": row.get("Type", ""),
                "Symbol": row.get("Symbol", ""),
                "SemanticFrame": row.get("SemanticFrame", ""),
                "ClauseType": clause_type(row.get("SemanticFrame", "")),
                "Frame": row.get("Frame", ""),
                "SkeletonReading": candidate.skeleton,
                "TokenSkeleton": replace_unit_tokens(row.get("ReadingTokens", ""), unit, candidate.skeleton),
                "StructuralParse": row.get("StructuralParse", ""),
                "ConstraintTier": candidate.tier,
            }
        )
    rows.sort(key=lambda item: (str(item["Unit"]), str(item["CISI"]), str(item["TextId"])))
    return rows


def build_progress_rows(candidates: list[Candidate]) -> list[dict[str, object]]:
    accepted = sum(1 for candidate in candidates if candidate.tier in {"A", "B"})
    total = len(candidates)
    accepted_ratio = accepted / total if total else 0.0
    top_score = candidates[0].score if candidates else 0.0
    avg_score = sum(candidate.score for candidate in candidates) / total if total else 0.0

    return [
        {
            "Goal": "Corpus and provenance control",
            "MaturityEstimate": "0.70",
            "Meaning": "The corpus is usable for modeling, though visual adjudication remains incomplete.",
            "FastestSafeMove": "Continue image-backed adjudication for high-value anchors only.",
        },
        {
            "Goal": "Structural grammar",
            "MaturityEstimate": "0.48",
            "Meaning": "Productive frames and slots are strong, but not yet a complete grammar.",
            "FastestSafeMove": "Use the solver to reject readings that violate frame behavior.",
        },
        {
            "Goal": "Morpheme segmentation",
            "MaturityEstimate": f"{clamp(0.12 + accepted_ratio * 0.28):.2f}",
            "Meaning": f"{accepted} of {total} anchor skeletons now pass or mostly pass constraints.",
            "FastestSafeMove": "Expand from anchor units to their nearest minimal-pair neighbors.",
        },
        {
            "Goal": "Semantic anchoring",
            "MaturityEstimate": f"{clamp(0.10 + avg_score * 0.25):.2f}",
            "Meaning": "Some contexts are strong, but most readings remain broad classes rather than meanings.",
            "FastestSafeMove": "Prioritize anchors with strong site, object, or iconographic concentration.",
        },
        {
            "Goal": "Phonetic values",
            "MaturityEstimate": "0.03",
            "Meaning": "No sign has a validated sound value; current variables are abstract only.",
            "FastestSafeMove": "Search for proper-name clusters and cross-frame alternations before any phonetic proposal.",
        },
        {
            "Goal": "Language identification",
            "MaturityEstimate": "0.06",
            "Meaning": "Dravidian-compatible structure is interesting, but compatibility is not identification.",
            "FastestSafeMove": "Require any language claim to predict all occurrences of at least one strong anchor.",
        },
        {
            "Goal": "Strict full decipherment",
            "MaturityEstimate": f"{clamp(0.04 + top_score * 0.06):.2f}",
            "Meaning": "Full decipherment is not guaranteed from the public corpus without bilingual or securely identified names.",
            "FastestSafeMove": "Build a falsifiable chain: anchors -> components -> proper names/titles -> phonetic tests.",
        },
    ]


def build_summary_rows(candidates: list[Candidate], clause_rows: list[dict[str, object]]) -> list[dict[str, object]]:
    status_counter = Counter(candidate.status for candidate in candidates)
    tier_counter = Counter(candidate.tier for candidate in candidates)
    hard_failures = sum(1 for candidate in candidates if candidate.hard_failures)
    top = candidates[0] if candidates else None
    return [
        {"Metric": "Candidate anchor skeletons", "Value": len(candidates), "Note": "Anchor-level reading skeletons tested."},
        {"Metric": "Accepted/promising skeletons", "Value": tier_counter["A"] + tier_counter["B"], "Note": "Tier A or B skeletons."},
        {"Metric": "Exploratory skeletons", "Value": tier_counter["C"], "Note": "Pass hard constraints but need more evidence."},
        {"Metric": "Hard-constraint holds", "Value": hard_failures, "Note": "Rejected or held because a hard constraint failed."},
        {"Metric": "Best skeleton", "Value": top.unit if top else "", "Note": top.skeleton if top else ""},
        {"Metric": "Best skeleton score", "Value": f"{top.score:.3f}" if top else "0.000", "Note": top.status if top else ""},
        {"Metric": "Clause reconstructions exported", "Value": len(clause_rows), "Note": "Occurrence-level structural/semantic skeletons."},
        {"Metric": "Phonetic readings assigned", "Value": 0, "Note": "The solver is intentionally pre-phonetic."},
    ]


def candidate_rows(candidates: list[Candidate]) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for rank, candidate in enumerate(candidates, start=1):
        rows.append(
            {
                "Rank": rank,
                "Unit": candidate.unit,
                "AbstractUnit": candidate.abstract_unit,
                "Role": candidate.role,
                "ReadingClass": candidate.reading_class,
                "SkeletonReading": candidate.skeleton,
                "ConstraintStatus": candidate.status,
                "EvidenceTier": candidate.tier,
                "Score": f"{candidate.score:.3f}",
                "DossierConfidence": f"{candidate.dossier_confidence:.3f}",
                "OccurrenceCount": candidate.occurrence_count,
                "DirectMinimalTests": candidate.direct_minimal_tests,
                "ComponentMinimalTests": candidate.component_minimal_tests,
                "ContextScore": f"{candidate.context_score:.3f}",
                "FramePurity": f"{candidate.frame_purity:.3f}",
                "MinimalSupport": f"{candidate.minimal_score:.3f}",
                "ComponentSupport": f"{candidate.component_score:.3f}",
                "BestContext": candidate.best_context,
                "BestContextStrength": candidate.best_context_strength,
                "DominantFrame": candidate.dominant_frame,
                "Components": "; ".join(
                    f"{sign}={label}" for sign, label in zip(candidate.components, candidate.component_labels)
                ),
                "AcceptedClaims": candidate.accepted_claims,
                "RejectedClaims": candidate.rejected_claims,
                "Warnings": "; ".join(candidate.warnings),
                "HardFailures": "; ".join(candidate.hard_failures),
                "NextSafeTest": candidate.next_test,
            }
        )
    return rows


def write_latex_summary(
    path: Path,
    summary: list[dict[str, object]],
    candidates: list[Candidate],
    progress_rows: list[dict[str, object]],
) -> None:
    top_candidates = [
        {
            "Unit": candidate.unit,
            "Skeleton": candidate.skeleton,
            "Tier": candidate.tier,
            "Score": f"{candidate.score:.3f}",
        }
        for candidate in candidates[:8]
    ]
    compact_progress = [
        {
            "Goal": row["Goal"],
            "Maturity": row["MaturityEstimate"],
        }
        for row in progress_rows
    ]

    text = (
        r"""\section{Constraint-Solver Reading Layer}

\subsection{Purpose}

This generated note ranks pre-phonetic reading skeletons from the anchor dossiers. It is a constraint solver, not a decipherment claim engine. A skeleton may pass only if it respects component order, context support, minimal-pair evidence, frame stability, lexical gates, and phonetic restraint.

\subsection{Solver Result}

\begin{table}[htbp]
\centering
"""
        + latex_table(summary, ["Metric", "Value"], ["p{0.58\\textwidth}", "r"])
        + r"""
\caption{Constraint-solver summary.}
\end{table}

\subsection{Highest-Ranked Skeletons}

\begin{table}[htbp]
\centering
\footnotesize
"""
        + latex_table(top_candidates, ["Unit", "Skeleton", "Tier", "Score"], ["l", "p{0.48\\textwidth}", "l", "r"])
        + r"""
\caption{Top constrained reading skeletons. These are not phonetic readings.}
\end{table}

\subsection{Progress Estimate}

\begin{table}[htbp]
\centering
\footnotesize
"""
        + latex_table(compact_progress, ["Goal", "Maturity"], ["p{0.62\\textwidth}", "r"])
        + r"""
\caption{Approximate maturity by decipherment subproblem. Values are heuristic maturity scores, not probabilities of success.}
\end{table}
"""
    )
    path.write_text(text, encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--outputs", default="outputs", help="Directory containing model outputs")
    args = parser.parse_args()

    out_dir = Path(args.outputs)
    candidates, constraint_rows, morpheme_rows = build_candidates(out_dir)
    clause_rows = build_clause_rows(out_dir, candidates)
    progress_rows = build_progress_rows(candidates)
    summary = build_summary_rows(candidates, clause_rows)

    write_csv(out_dir / "constraint_solver_summary.csv", summary, ["Metric", "Value", "Note"])
    write_csv(
        out_dir / "constrained_reading_candidates.csv",
        candidate_rows(candidates),
        [
            "Rank",
            "Unit",
            "AbstractUnit",
            "Role",
            "ReadingClass",
            "SkeletonReading",
            "ConstraintStatus",
            "EvidenceTier",
            "Score",
            "DossierConfidence",
            "OccurrenceCount",
            "DirectMinimalTests",
            "ComponentMinimalTests",
            "ContextScore",
            "FramePurity",
            "MinimalSupport",
            "ComponentSupport",
            "BestContext",
            "BestContextStrength",
            "DominantFrame",
            "Components",
            "AcceptedClaims",
            "RejectedClaims",
            "Warnings",
            "HardFailures",
            "NextSafeTest",
        ],
    )
    write_csv(
        out_dir / "constraint_violations.csv",
        constraint_rows,
        ["Unit", "ConstraintId", "Constraint", "Severity", "Result", "Evidence"],
    )
    write_csv(
        out_dir / "morpheme_slot_assignments.csv",
        morpheme_rows,
        [
            "Unit",
            "Sign",
            "AbstractVariable",
            "Position",
            "UnitLength",
            "ProposedRole",
            "FunctionalClass",
            "ComponentInterpretation",
            "OrderStatus",
            "ReadingConstraint",
        ],
    )
    write_csv(
        out_dir / "reconstructed_clause_frames.csv",
        clause_rows,
        [
            "Unit",
            "TextId",
            "CISI",
            "Site",
            "Type",
            "Symbol",
            "SemanticFrame",
            "ClauseType",
            "Frame",
            "SkeletonReading",
            "TokenSkeleton",
            "StructuralParse",
            "ConstraintTier",
        ],
    )
    write_csv(
        out_dir / "decipherment_progress_estimate.csv",
        progress_rows,
        ["Goal", "MaturityEstimate", "Meaning", "FastestSafeMove"],
    )
    write_latex_summary(out_dir / "constraint_solver_model.tex", summary, candidates, progress_rows)

    print("Wrote constraint-solver outputs:")
    for name in [
        "constraint_solver_summary.csv",
        "constrained_reading_candidates.csv",
        "constraint_violations.csv",
        "morpheme_slot_assignments.csv",
        "reconstructed_clause_frames.csv",
        "decipherment_progress_estimate.csv",
        "constraint_solver_model.tex",
    ]:
        print(f"  - {out_dir / name}")


if __name__ == "__main__":
    main()
