#!/usr/bin/env python3
"""Score language and decipherment hypotheses against current evidence.

This model is deliberately conservative. It does not pick a language by lexical
resemblance. It turns each language/script hypothesis into explicit diagnostics
and scores those diagnostics against the structural, phonetic, and semantic
testbenches already built.
"""

from __future__ import annotations

import argparse
import csv
import math
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path


UNKNOWN = "Unknown"


@dataclass(frozen=True)
class Hypothesis:
    hypothesis_id: str
    name: str
    claim: str
    prior: float
    decisive_tests: tuple[str, ...]


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


def pct(part: int, whole: int) -> float:
    if whole <= 0:
        return 0.0
    return part / whole


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


def top_counter(counter: Counter[str], limit: int = 5) -> str:
    return "; ".join(f"{key}:{value}" for key, value in counter.most_common(limit))


def split_counter_text(value: str | None) -> Counter[str]:
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


def load_hypotheses() -> list[Hypothesis]:
    return [
        Hypothesis(
            "L0",
            "Restricted Administrative/Onomastic Script",
            "The inscriptions encode restricted names, titles, institutions, commodities, or authority formulae rather than full prose.",
            0.72,
            (
                "Prime-entity fillers must correlate with object, site, emblem, or administrative context.",
                "Terminal and classifier signs must remain functionally stable across sites.",
                "Longer prose-like syntax should remain rare.",
            ),
        ),
        Hypothesis(
            "L1",
            "Multilingual Administrative Ecology",
            "The system is a shared administrative script with possible language-local names or titles at different sites.",
            0.60,
            (
                "Regional/site distributions should explain units better than one global phonetic inventory.",
                "A core of signs should remain stable while some fillers show site-specific behavior.",
                "Image/context validation should reveal local administrative practices.",
            ),
        ),
        Hypothesis(
            "L2",
            "Dravidian-Compatible Linguistic Layer",
            "Some signs encode a Dravidian or para-Dravidian linguistic layer, probably through suffixing formulae and names/titles.",
            0.48,
            (
                "Suffix-like terminal signs should attach productively to entity fillers.",
                "A proposed Dravidian morpheme must predict all structural occurrences, not just one sign.",
                "Proper-name or title readings must survive cross-site minimal alternations.",
            ),
        ),
        Hypothesis(
            "L3",
            "Indo-Iranian/Indo-Aryan Linguistic Layer",
            "Some signs encode an early Indo-Iranian or Indo-Aryan linguistic layer, probably in names, titles, or ritual/administrative terms.",
            0.34,
            (
                "Any reading must be chronology-sensitive and avoid later Sanskrit back-projection.",
                "Inflectional or title morphology must explain terminal signs and minimal pairs.",
                "A proposed name/title must recur in compatible semantic contexts.",
            ),
        ),
        Hypothesis(
            "L4",
            "Munda/Para-Munda Linguistic Layer",
            "Some signs encode a Munda-like or para-Munda linguistic layer, potentially with prefixing or mixed morphology.",
            0.32,
            (
                "Prefix-like or classifier-like behavior should be stronger than suffix-only analysis.",
                "Regional distributions should fit plausible eastern or contact-zone contexts.",
                "Readings must explain both initial and terminal alternations.",
            ),
        ),
        Hypothesis(
            "L5",
            "Logo-Syllabic or Logo-Phonetic Writing",
            "The system combines semantic signs with phonetic or syllabic complements.",
            0.44,
            (
                "Minimal pairs should isolate recurring sound-bearing contrasts.",
                "Sign variables should appear in both semantic and phonetic roles.",
                "Allograph compression should preserve phonetic or morphemic structure.",
            ),
        ),
        Hypothesis(
            "L6",
            "Primarily Non-Linguistic Emblem System",
            "The signs are mostly emblematic or administrative symbols with little direct language encoding.",
            0.42,
            (
                "Context associations should dominate over internal grammatical structure.",
                "Phonetic anchors should fail to generalize across artifacts.",
                "Minimal pairs should behave as graphic variants rather than linguistic contrasts.",
            ),
        ),
    ]


def evidence_metrics(out_dir: Path) -> dict[str, float | int | str]:
    structural_summary = {row["Metric"]: row for row in read_csv(out_dir / "structural_reconstruction_summary.csv")}
    phonetic_summary = {row["Metric"]: row for row in read_csv(out_dir / "phonetic_bootstrap_summary.csv")}
    semantic_summary = {row["Metric"]: row for row in read_csv(out_dir / "semantic_context_summary.csv")}
    semantic_frames = {row["SemanticFrame"]: fint(row["Count"]) for row in read_csv(out_dir / "structural_semantic_frames.csv")}
    sign_vars = read_csv(out_dir / "phonetic_variable_map.csv")
    semantic_candidates = read_csv(out_dir / "semantic_reconstruction_candidates.csv")
    correlations = read_csv(out_dir / "anchor_context_correlations.csv")
    reading_units = read_csv(out_dir / "phonetic_reading_units.csv")
    abstract_rows = read_csv(out_dir / "abstract_phonetic_reconstructions.csv")

    total_reconstructed = fint(structural_summary["Texts reconstructed"]["Value"])
    ready = fint(phonetic_summary["Medium/high ready reconstructions"]["Value"])
    structural_templates = fint(structural_summary["Structural templates"]["Value"])
    semantic_frame_count = fint(structural_summary["Semantic frames"]["Value"])
    strong_onomastic = fint(semantic_summary["Strong onomastic units profiled"]["Value"])
    strong_context = fint(semantic_summary["Strong context associations"]["Value"])
    moderate_context = fint(semantic_summary["Moderate context associations"]["Value"])
    symbol_linked = fint(semantic_summary["Symbol-linked semantic candidates"]["Value"])
    usable_icons = fint(semantic_summary["Usable iconography labels"]["Value"])
    unknown_icons = fint(semantic_summary["Unknown iconography labels"]["Value"])

    terminal = semantic_frames.get("TerminalFormula", 0)
    prime = semantic_frames.get("PrimeEntitySealFormula", 0) + semantic_frames.get("PrimeEntityAdministrativeFormula", 0)
    classifier = semantic_frames.get("ClassifierSlotTerminalFormula", 0) + semantic_frames.get("InitialClassifierFormula", 0)
    low_evidence = semantic_frames.get("LowEvidenceSequence", 0)

    sign_class_counts = Counter(row["FunctionalClass"] for row in sign_vars)
    terminal_sign_count = sign_class_counts["TERMINAL"]
    classifier_sign_count = sign_class_counts["CLASSIFIER"]
    modifier_sign_count = sign_class_counts["SLOT_MODIFIER"]
    unresolved_sign_count = sign_class_counts["ROOT_OR_UNRESOLVED"]

    role_counts = Counter(row["Role"] for row in reading_units)
    test_counts = Counter(row["TestClass"] for row in reading_units)

    best_context_counts = Counter(row["BestContextDimension"] for row in semantic_candidates)
    best_strength_counts = Counter(row["BestContextStrength"] for row in semantic_candidates)
    prime_context_candidates = sum(1 for row in semantic_candidates if row["Role"] == "PrimeEntityFiller")

    high_abs = sum(1 for row in abstract_rows if row["PhoneticReadiness"] == "High")
    medium_abs = sum(1 for row in abstract_rows if row["PhoneticReadiness"] == "Medium")

    strong_priority_context = sum(
        1
        for row in correlations
        if row["Strength"] == "Strong"
        and row["TestClass"] in {"StrongOnomasticAnchor", "CrossFramePhoneticAnchor", "AffixOrFormulaAnchor"}
    )
    symbol_context = sum(
        1
        for row in correlations
        if row["Dimension"] == "Symbol" and row["Strength"] in {"Strong", "Moderate"}
    )
    site_context = sum(
        1
        for row in correlations
        if row["Dimension"] in {"Site", "Region"} and row["Strength"] in {"Strong", "Moderate"}
    )
    type_context = sum(
        1
        for row in correlations
        if row["Dimension"] in {"Type", "Material"} and row["Strength"] in {"Strong", "Moderate"}
    )

    suffixing_strength = clamp((terminal_sign_count / 9.0 + pct(terminal, total_reconstructed) * 2.2) / 2.0)
    classifier_strength = clamp((classifier_sign_count / 4.0 + pct(classifier, total_reconstructed) * 3.0) / 2.0)
    prime_entity_strength = clamp((strong_onomastic / 7.0 + pct(prime, total_reconstructed) * 5.0) / 2.0)
    context_strength = clamp((strong_context / 60.0 + moderate_context / 220.0 + symbol_linked / 40.0) / 3.0)
    phonetic_readiness_strength = clamp((ready / 700.0 + high_abs / 180.0 + strong_onomastic / 10.0) / 3.0)
    unresolved_penalty = clamp(pct(low_evidence, total_reconstructed) * 1.5)
    formula_restriction = clamp(1.0 - (structural_templates / max(total_reconstructed, 1)))
    regional_strength = clamp(site_context / 180.0)
    icon_strength = clamp(usable_icons / max(usable_icons + unknown_icons, 1))
    minimal_anchor_strength = clamp(test_counts["CrossFramePhoneticAnchor"] / 40.0)

    return {
        "total_reconstructed": total_reconstructed,
        "ready_reconstructions": ready,
        "structural_templates": structural_templates,
        "semantic_frame_count": semantic_frame_count,
        "terminal_formulae": terminal,
        "prime_entity_formulae": prime,
        "classifier_formulae": classifier,
        "low_evidence_sequences": low_evidence,
        "terminal_sign_count": terminal_sign_count,
        "classifier_sign_count": classifier_sign_count,
        "modifier_sign_count": modifier_sign_count,
        "unresolved_sign_count": unresolved_sign_count,
        "strong_onomastic": strong_onomastic,
        "strong_context": strong_context,
        "moderate_context": moderate_context,
        "symbol_linked": symbol_linked,
        "usable_iconography": usable_icons,
        "unknown_iconography": unknown_icons,
        "high_abstract_reconstructions": high_abs,
        "medium_abstract_reconstructions": medium_abs,
        "prime_context_candidates": prime_context_candidates,
        "strong_priority_context": strong_priority_context,
        "symbol_context_associations": symbol_context,
        "site_region_associations": site_context,
        "type_material_associations": type_context,
        "role_counts": top_counter(role_counts),
        "test_class_counts": top_counter(test_counts),
        "best_context_dimensions": top_counter(best_context_counts),
        "best_context_strengths": top_counter(best_strength_counts),
        "suffixing_strength": round(suffixing_strength, 3),
        "classifier_strength": round(classifier_strength, 3),
        "prime_entity_strength": round(prime_entity_strength, 3),
        "context_strength": round(context_strength, 3),
        "phonetic_readiness_strength": round(phonetic_readiness_strength, 3),
        "unresolved_penalty": round(unresolved_penalty, 3),
        "formula_restriction": round(formula_restriction, 3),
        "regional_strength": round(regional_strength, 3),
        "icon_strength": round(icon_strength, 3),
        "minimal_anchor_strength": round(minimal_anchor_strength, 3),
    }


def feature_rows(metrics: dict[str, float | int | str]) -> list[dict[str, object]]:
    specs = [
        ("Formula restriction", "formula_restriction", "Short, repeated, structured inscriptions rather than free prose."),
        ("Suffix/final structure", "suffixing_strength", "Terminal signs and final formulae behave productively."),
        ("Classifier/title structure", "classifier_strength", "Initial classifier/title-like signs are stable and productive."),
        ("Prime entity structure", "prime_entity_strength", "Name/title/place-like fillers occupy productive entity slots."),
        ("Context association", "context_strength", "Units correlate with site, object, material, or iconography."),
        ("Phonetic readiness", "phonetic_readiness_strength", "Minimal-pair and cross-frame evidence exists for controlled testing."),
        ("Regional differentiation", "regional_strength", "Site/region context explains some unit distributions."),
        ("Usable iconography", "icon_strength", "Iconographic labels are present for many ready reconstructions."),
        ("Unresolved mass", "unresolved_penalty", "Large unresolved portion limits language claims."),
    ]
    return [
        {
            "Feature": name,
            "Score": metrics[key],
            "Interpretation": note,
        }
        for name, key, note in specs
    ]


def hypothesis_feature_weights() -> dict[str, dict[str, float]]:
    return {
        "L0": {
            "formula_restriction": 1.3,
            "context_strength": 1.2,
            "prime_entity_strength": 1.0,
            "classifier_strength": 0.9,
            "suffixing_strength": 0.7,
            "regional_strength": 0.4,
            "phonetic_readiness_strength": 0.2,
            "unresolved_penalty": -0.2,
        },
        "L1": {
            "formula_restriction": 1.0,
            "regional_strength": 1.2,
            "context_strength": 1.1,
            "prime_entity_strength": 0.8,
            "classifier_strength": 0.8,
            "phonetic_readiness_strength": 0.5,
            "suffixing_strength": 0.4,
            "unresolved_penalty": -0.1,
        },
        "L2": {
            "suffixing_strength": 1.3,
            "prime_entity_strength": 1.0,
            "phonetic_readiness_strength": 0.9,
            "formula_restriction": 0.6,
            "context_strength": 0.4,
            "classifier_strength": 0.3,
            "regional_strength": 0.2,
            "unresolved_penalty": -0.6,
        },
        "L3": {
            "prime_entity_strength": 0.9,
            "phonetic_readiness_strength": 1.0,
            "suffixing_strength": 0.5,
            "context_strength": 0.5,
            "formula_restriction": 0.4,
            "classifier_strength": 0.2,
            "regional_strength": 0.2,
            "unresolved_penalty": -0.75,
        },
        "L4": {
            "classifier_strength": 0.8,
            "regional_strength": 0.7,
            "phonetic_readiness_strength": 0.8,
            "suffixing_strength": 0.4,
            "context_strength": 0.4,
            "prime_entity_strength": 0.5,
            "formula_restriction": 0.4,
            "unresolved_penalty": -0.75,
        },
        "L5": {
            "phonetic_readiness_strength": 1.25,
            "minimal_anchor_strength": 1.0,
            "prime_entity_strength": 0.8,
            "classifier_strength": 0.6,
            "suffixing_strength": 0.6,
            "formula_restriction": 0.4,
            "context_strength": 0.3,
            "unresolved_penalty": -0.5,
        },
        "L6": {
            "context_strength": 1.3,
            "icon_strength": 1.0,
            "formula_restriction": 0.9,
            "classifier_strength": 0.6,
            "prime_entity_strength": -0.2,
            "phonetic_readiness_strength": -0.6,
            "suffixing_strength": -0.2,
            "unresolved_penalty": 0.3,
        },
    }


def support_label(score: float) -> str:
    if score >= 0.72:
        return "Strongly supported"
    if score >= 0.58:
        return "Supported"
    if score >= 0.44:
        return "Plausible but unproven"
    if score >= 0.30:
        return "Weakly supported"
    return "Currently weak"


def main_objection(hypothesis_id: str, metrics: dict[str, float | int | str]) -> str:
    unresolved = ffloat(str(metrics["unresolved_penalty"]))
    phonetic = ffloat(str(metrics["phonetic_readiness_strength"]))
    if hypothesis_id in {"L2", "L3", "L4"}:
        return "No sign has a validated phonetic value yet; family assignment remains below decipherment threshold."
    if hypothesis_id == "L5":
        return "Minimal-pair evidence exists, but no phonetic complement has been proven."
    if hypothesis_id == "L6":
        if phonetic > 0.45:
            return "Structured prime-entity slots and phonetic-ready minimal pairs are too strong for a purely emblematic account."
        return "Could still be true, but must explain productive terminal and entity-slot structure."
    if unresolved > 0.5:
        return "A large unresolved sequence class remains and may hide multiple mechanisms."
    return "Needs image-grounded validation of the strongest anchors."


def score_hypotheses(metrics: dict[str, float | int | str]) -> list[dict[str, object]]:
    hypotheses = load_hypotheses()
    weights = hypothesis_feature_weights()
    rows: list[dict[str, object]] = []
    for hyp in hypotheses:
        weighted_sum = 0.0
        weight_total = 0.0
        contributions: list[str] = []
        for feature, weight in weights[hyp.hypothesis_id].items():
            value = ffloat(str(metrics.get(feature, 0.0)))
            if weight >= 0:
                weighted_sum += weight * value
                weight_total += weight
                contributions.append(f"{feature}={value:.3f} x {weight:.2f}")
            else:
                weighted_sum += abs(weight) * (1.0 - value)
                weight_total += abs(weight)
                contributions.append(f"not {feature}={1.0 - value:.3f} x {abs(weight):.2f}")
        evidence_score = weighted_sum / max(weight_total, 1e-9)
        posterior_like = 0.68 * evidence_score + 0.32 * hyp.prior
        rows.append(
            {
                "HypothesisId": hyp.hypothesis_id,
                "Name": hyp.name,
                "Claim": hyp.claim,
                "PriorWeight": hyp.prior,
                "EvidenceScore": round(evidence_score, 3),
                "PosteriorLikeScore": round(posterior_like, 3),
                "SupportLevel": support_label(posterior_like),
                "MainSupportingEvidence": "; ".join(contributions[:5]),
                "MainObjection": main_objection(hyp.hypothesis_id, metrics),
                "DecisiveNextTests": " | ".join(hyp.decisive_tests),
            }
        )
    rows.sort(key=lambda row: (-ffloat(str(row["PosteriorLikeScore"])), row["HypothesisId"]))
    return rows


def lexical_gate_rows(out_dir: Path) -> list[dict[str, object]]:
    candidates = read_csv(out_dir / "semantic_reconstruction_candidates.csv")
    rows: list[dict[str, object]] = []
    for row in candidates:
        role = row["Role"]
        test_class = row["TestClass"]
        if test_class not in {"StrongOnomasticAnchor", "CrossFramePhoneticAnchor"}:
            continue
        if role == "PrimeEntityFiller":
            allowed = "proper names; offices/titles; lineages/clans; places; institutions; emblem-linked identities"
            blocked = "animal-name equation from icon alone; isolated Sanskrit/Dravidian lookalike without frame prediction"
        elif role == "TerminalFiller":
            allowed = "suffixes; titles; terminal formulae; object labels; administrative endings"
            blocked = "free-standing nouns unless the same unit appears independently"
        elif role == "InitialFiller":
            allowed = "classifiers; titles; prefixes; office markers; formula openers"
            blocked = "root nouns unless context and alternations require it"
        else:
            allowed = "morphemes or lexical roots only after context validation"
            blocked = "single-occurrence lexical matches"
        rows.append(
            {
                "Unit": row["Unit"],
                "AbstractUnit": row["AbstractUnit"],
                "Role": role,
                "BestContext": f"{row['BestContextDimension']}={row['BestContextCategory']}",
                "AllowedLexicalSearch": allowed,
                "BlockedShortcut": blocked,
                "MinimumEvidenceBeforeReading": (
                    "all occurrences inspected; minimal pairs checked; sign value predicts every structural frame"
                ),
            }
        )
    rows.sort(key=lambda row: (0 if row["Role"] == "PrimeEntityFiller" else 1, str(row["Unit"])))
    return rows


def reconstruction_claims(metrics: dict[str, float | int | str], hypothesis_rows: list[dict[str, object]]) -> list[dict[str, object]]:
    best = hypothesis_rows[0]
    language_specific = [row for row in hypothesis_rows if row["HypothesisId"] in {"L2", "L3", "L4"}]
    best_language = max(language_specific, key=lambda row: ffloat(str(row["PosteriorLikeScore"])))
    return [
        {
            "ClaimType": "Current script model",
            "Claim": best["Name"],
            "Confidence": best["PosteriorLikeScore"],
            "Status": best["SupportLevel"],
            "Caveat": best["MainObjection"],
        },
        {
            "ClaimType": "Best language-family-compatible model",
            "Claim": best_language["Name"],
            "Confidence": best_language["PosteriorLikeScore"],
            "Status": best_language["SupportLevel"],
            "Caveat": "Compatibility is not identification; phonetic anchors remain abstract.",
        },
        {
            "ClaimType": "Most concrete partial decipherment target",
            "Claim": "The 002 X 740 prime-entity formula",
            "Confidence": metrics["prime_entity_strength"],
            "Status": "Structurally and semantically testable",
            "Caveat": "X may be name, title, office, lineage, place, institution, or commodity.",
        },
        {
            "ClaimType": "Best immediate language test",
            "Claim": "Validate strong anchors against images, then test controlled lexical classes only.",
            "Confidence": metrics["phonetic_readiness_strength"],
            "Status": "Ready for supervised testing",
            "Caveat": "A language claim before image validation is premature.",
        },
    ]


def summary_rows(metrics: dict[str, float | int | str], hypothesis_rows: list[dict[str, object]]) -> list[dict[str, object]]:
    best = hypothesis_rows[0]
    best_lang = max(
        [row for row in hypothesis_rows if row["HypothesisId"] in {"L2", "L3", "L4"}],
        key=lambda row: ffloat(str(row["PosteriorLikeScore"])),
    )
    return [
        {"Metric": "Best overall hypothesis", "Value": best["Name"], "Note": best["SupportLevel"]},
        {"Metric": "Best language-family-compatible hypothesis", "Value": best_lang["Name"], "Note": best_lang["SupportLevel"]},
        {"Metric": "Ready reconstructions", "Value": metrics["ready_reconstructions"], "Note": "Rows available for phonetic/language testing."},
        {"Metric": "Strong onomastic anchors", "Value": metrics["strong_onomastic"], "Note": "Best route toward proper-name decipherment."},
        {"Metric": "Strong context associations", "Value": metrics["strong_context"], "Note": "Semantic grounding evidence."},
        {"Metric": "Suffix/final structure score", "Value": metrics["suffixing_strength"], "Note": "Compatibility with suffixing/agglutinative analyses."},
        {"Metric": "Classifier/title structure score", "Value": metrics["classifier_strength"], "Note": "Compatibility with classifier or title formulae."},
        {"Metric": "Phonetic readiness score", "Value": metrics["phonetic_readiness_strength"], "Note": "Still abstract; no sound values assigned."},
        {"Metric": "Language identification status", "Value": "Not cracked", "Note": "Current evidence supports a script model more strongly than a language family."},
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
    features: list[dict[str, object]],
    hypotheses: list[dict[str, object]],
    claims: list[dict[str, object]],
) -> None:
    hypothesis_short = [
        {
            "Hypothesis": row["Name"],
            "Score": row["PosteriorLikeScore"],
            "Status": row["SupportLevel"],
        }
        for row in hypotheses
    ]
    feature_short = [
        {"Feature": row["Feature"], "Score": row["Score"]}
        for row in features
    ]
    claim_short = [
        {
            "Claim type": row["ClaimType"],
            "Claim": row["Claim"],
            "Status": row["Status"],
        }
        for row in claims
    ]
    text = r"""\section{Language Hypothesis Testbench}

\subsection{Purpose}

This generated note tests language and script hypotheses against the current structural, phonetic, and semantic models. It does not identify the Indus language. It ranks which hypotheses are currently compatible with the evidence and lists what would be needed to turn compatibility into decipherment.

\subsection{Summary}

\begin{table}[htbp]
\centering
\footnotesize
""" + latex_table(summary, ["Metric", "Value"], ["p{0.58\\textwidth}", "p{0.28\\textwidth}"]) + r"""
\caption{Language-hypothesis testbench summary.}
\end{table}

\subsection{Diagnostic Features}

\begin{table}[htbp]
\centering
""" + latex_table(feature_short, ["Feature", "Score"]) + r"""
\caption{Current evidence features used in hypothesis scoring.}
\end{table}

\subsection{Hypothesis Ranking}

\begin{table}[htbp]
\centering
\footnotesize
""" + latex_table(hypothesis_short, ["Hypothesis", "Score", "Status"], ["p{0.50\\textwidth}", "r", "p{0.28\\textwidth}"]) + r"""
\caption{Current hypothesis ranking. Scores are compatibility scores, not proof.}
\end{table}

\subsection{Current Claims}

\begin{table}[htbp]
\centering
\footnotesize
""" + latex_table(claim_short, ["Claim type", "Claim", "Status"], ["p{0.26\\textwidth}", "p{0.42\\textwidth}", "p{0.22\\textwidth}"]) + r"""
\caption{Claims that are currently justified by the model.}
\end{table}
"""
    path.write_text(text, encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--outputs", default="outputs", help="Directory containing model outputs")
    args = parser.parse_args()

    out_dir = Path(args.outputs)
    metrics = evidence_metrics(out_dir)
    features = feature_rows(metrics)
    hypotheses = score_hypotheses(metrics)
    lexical_gates = lexical_gate_rows(out_dir)
    claims = reconstruction_claims(metrics, hypotheses)
    summary = summary_rows(metrics, hypotheses)

    write_csv(out_dir / "language_evidence_features.csv", features, ["Feature", "Score", "Interpretation"])
    write_csv(
        out_dir / "language_hypothesis_scores.csv",
        hypotheses,
        [
            "HypothesisId",
            "Name",
            "Claim",
            "PriorWeight",
            "EvidenceScore",
            "PosteriorLikeScore",
            "SupportLevel",
            "MainSupportingEvidence",
            "MainObjection",
            "DecisiveNextTests",
        ],
    )
    write_csv(
        out_dir / "lexical_reading_gate.csv",
        lexical_gates,
        [
            "Unit",
            "AbstractUnit",
            "Role",
            "BestContext",
            "AllowedLexicalSearch",
            "BlockedShortcut",
            "MinimumEvidenceBeforeReading",
        ],
    )
    write_csv(out_dir / "decipherment_claims.csv", claims, ["ClaimType", "Claim", "Confidence", "Status", "Caveat"])
    write_csv(out_dir / "language_hypothesis_summary.csv", summary, ["Metric", "Value", "Note"])
    write_latex_summary(out_dir / "language_hypothesis_testbench.tex", summary, features, hypotheses, claims)

    print("Wrote language hypothesis testbench outputs:")
    for name in [
        "language_evidence_features.csv",
        "language_hypothesis_scores.csv",
        "lexical_reading_gate.csv",
        "decipherment_claims.csv",
        "language_hypothesis_summary.csv",
        "language_hypothesis_testbench.tex",
    ]:
        print(f"  - {out_dir / name}")


if __name__ == "__main__":
    main()
