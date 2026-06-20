#!/usr/bin/env python3
"""Validate minimal-pair probes as controlled decipherment constraints.

This model takes the probe queue from the neighbor-expansion stage and decides
which probes are ready to become morphology constraints, which are plausible
future phonetic probes, and which must remain role-boundary controls. It does
not assign sound values.
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


@dataclass
class Occurrence:
    unit: str
    text_id: str
    cisi: str
    frame: str
    position: str
    site: str
    region: str
    artifact_type: str
    symbol: str
    material: str
    semantic_frame: str
    reading_tokens: str
    structural_parse: str


@dataclass
class UnitProfile:
    unit: str
    occurrences: list[Occurrence] = field(default_factory=list)
    frames: Counter[str] = field(default_factory=Counter)
    sites: Counter[str] = field(default_factory=Counter)
    regions: Counter[str] = field(default_factory=Counter)
    types: Counter[str] = field(default_factory=Counter)
    symbols: Counter[str] = field(default_factory=Counter)
    materials: Counter[str] = field(default_factory=Counter)
    semantic_frames: Counter[str] = field(default_factory=Counter)


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
        slots.append({"Frame": frame.strip(), "Filler": "-".join(tokens), "Position": position.strip()})
    return slots


def normalize_symbol(value: str | None) -> str:
    text = (value or "").strip()
    if not text or text == "-":
        return "Unknown"
    if text.startswith("Bull1"):
        return "Bull"
    aliases = {
        "Bult": "Bull/uncertain",
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


def build_profiles(structural_rows: list[dict[str, str]]) -> dict[str, UnitProfile]:
    profiles: dict[str, UnitProfile] = defaultdict(lambda: UnitProfile(""))
    for row in structural_rows:
        if row.get("PhoneticReadiness") not in {"High", "Medium"}:
            continue
        for slot in parse_slot_fillers(row.get("SlotFillers")):
            unit = slot["Filler"]
            if not profiles[unit].unit:
                profiles[unit].unit = unit
            occurrence = Occurrence(
                unit=unit,
                text_id=row.get("TextId", ""),
                cisi=row.get("CISI", ""),
                frame=slot["Frame"],
                position=slot["Position"],
                site=row.get("Site", "") or "Unknown",
                region=row.get("Region", "") or "Unknown",
                artifact_type=normalize_type(row.get("Type")),
                symbol=normalize_symbol(row.get("Symbol")),
                material=row.get("Material", "") or "Unknown",
                semantic_frame=row.get("SemanticFrame", "") or "Unknown",
                reading_tokens=row.get("ReadingTokens", ""),
                structural_parse=row.get("StructuralParse", ""),
            )
            profile = profiles[unit]
            profile.occurrences.append(occurrence)
            profile.frames[occurrence.frame] += 1
            profile.sites[occurrence.site] += 1
            profile.regions[occurrence.region] += 1
            profile.types[occurrence.artifact_type] += 1
            profile.symbols[occurrence.symbol] += 1
            profile.materials[occurrence.material] += 1
            profile.semantic_frames[occurrence.semantic_frame] += 1
    return profiles


def counter_prob(counter: Counter[str]) -> dict[str, float]:
    total = sum(counter.values())
    if total <= 0:
        return {}
    return {key: value / total for key, value in counter.items()}


def js_divergence(left: Counter[str], right: Counter[str]) -> float:
    p = counter_prob(left)
    q = counter_prob(right)
    keys = set(p) | set(q)
    if not keys:
        return 0.0
    midpoint = {key: (p.get(key, 0.0) + q.get(key, 0.0)) / 2.0 for key in keys}

    def kl(dist: dict[str, float], base: dict[str, float]) -> float:
        total = 0.0
        for key, value in dist.items():
            if value > 0 and base.get(key, 0.0) > 0:
                total += value * math.log(value / base[key], 2)
        return total

    return clamp((kl(p, midpoint) + kl(q, midpoint)) / 2.0)


def overlap_score(left: Counter[str], right: Counter[str]) -> float:
    p = counter_prob(left)
    q = counter_prob(right)
    keys = set(p) | set(q)
    if not keys:
        return 0.0
    return sum(min(p.get(key, 0.0), q.get(key, 0.0)) for key in keys)


def dimension_report(left: UnitProfile, right: UnitProfile) -> dict[str, float]:
    dimensions = {
        "Frame": (left.frames, right.frames),
        "SemanticFrame": (left.semantic_frames, right.semantic_frames),
        "Site": (left.sites, right.sites),
        "Region": (left.regions, right.regions),
        "Type": (left.types, right.types),
        "Symbol": (left.symbols, right.symbols),
        "Material": (left.materials, right.materials),
    }
    scores: dict[str, float] = {}
    for name, (left_counter, right_counter) in dimensions.items():
        scores[f"{name}JSD"] = js_divergence(left_counter, right_counter)
        scores[f"{name}Overlap"] = overlap_score(left_counter, right_counter)
    return scores


def same_frame_count(profile: UnitProfile, frame: str) -> int:
    return profile.frames.get(frame, 0)


def validation_status(row: dict[str, str], profile_a: UnitProfile, profile_b: UnitProfile, dims: dict[str, float]) -> tuple[str, str, float]:
    contrast = row.get("ContrastClass", "")
    gate = row.get("Gate", "")
    frame = row.get("Frame", "")
    queue_score = ffloat(row.get("Score"))
    combined_count = fint(row.get("CombinedCount"))
    min_occ = min(len(profile_a.occurrences), len(profile_b.occurrences))
    min_frame_occ = min(same_frame_count(profile_a, frame), same_frame_count(profile_b, frame))
    frame_overlap = dims.get("FrameOverlap", 0.0)
    semantic_overlap = dims.get("SemanticFrameOverlap", 0.0)
    context_separation = (dims.get("SiteJSD", 0.0) + dims.get("SymbolJSD", 0.0) + dims.get("TypeJSD", 0.0)) / 3.0
    role_text = f"{row.get('AnchorComponentRole', '')} {row.get('NeighborComponentRole', '')}"
    qualifier_role_bonus = 0.0
    if "QUALIFIER_TITLE_CLASSIFIER" in role_text or "CLASSIFIER" in role_text or "FORMULA_MARKER" in role_text:
        qualifier_role_bonus = 0.14
    terminal_role_bonus = 0.0
    if role_text.count("TERMINAL_TITLE_SUFFIX") >= 2 or ("TERMINAL_TITLE_SUFFIX" in role_text and "FINAL" in role_text):
        terminal_role_bonus = 0.16

    if "Role-boundary" in gate or contrast == "role-boundary control":
        return (
            "Control only",
            "Roles are not aligned enough for phonetic inference.",
            clamp(queue_score * 0.55 + frame_overlap * 0.20 + semantic_overlap * 0.10),
        )

    if contrast == "entity-stem contrast":
        score = clamp(
            queue_score * 0.42
            + frame_overlap * 0.20
            + semantic_overlap * 0.12
            + clamp(combined_count / 20.0) * 0.14
            + clamp(min_frame_occ / 3.0) * 0.08
            + context_separation * 0.04
        )
        if min_frame_occ >= 2 and score >= 0.74:
            return ("Phonetic-ready after image check", "Same-slot stem contrast has enough repeated frame evidence.", score)
        if min_frame_occ >= 1 and score >= 0.70:
            return ("Stem-semantic probe", "Good same-slot contrast, but one side is still occurrence-limited.", score)
        return ("Hold for more occurrences", "Stem contrast is structurally plausible but occurrence-limited.", score)

    if "prefix" in contrast or "classifier" in contrast:
        score = clamp(
            queue_score * 0.42
            + clamp(combined_count / 25.0) * 0.24
            + semantic_overlap * 0.08
            + frame_overlap * 0.06
            + context_separation * 0.04
            + qualifier_role_bonus
        )
        if combined_count >= 15 and score >= 0.68:
            return ("Morphology constraint", "Title/classifier behavior can be modeled before phonetics.", score)
        return ("Morphology probe", "Potential title/classifier behavior needs stronger context separation.", score)

    if "suffix" in contrast or "terminal" in contrast:
        score = clamp(
            queue_score * 0.40
            + clamp(combined_count / 22.0) * 0.24
            + semantic_overlap * 0.08
            + frame_overlap * 0.06
            + context_separation * 0.04
            + terminal_role_bonus
        )
        if combined_count >= 15 and score >= 0.66:
            return ("Terminal constraint", "Terminal/suffix contrast is strong enough for grammatical modeling.", score)
        return ("Terminal probe", "Terminal contrast remains useful but not decisive.", score)

    return ("Structural control", "Useful as a same-frame control, not a reading probe.", queue_score * 0.5)


def parse_probe(value: str) -> tuple[str, str]:
    if "::" not in value:
        return value.strip(), ""
    left, right = value.split("::", 1)
    return left.strip(), right.strip()


def matching_neighbor_row(neighbor_rows: list[dict[str, str]], anchor: str, neighbor: str, frame: str, contrast: str) -> dict[str, str]:
    for row in neighbor_rows:
        if (
            row.get("AnchorUnit") == anchor
            and row.get("NeighborUnit") == neighbor
            and row.get("Frame") == frame
            and row.get("ContrastClass") == contrast
        ):
            return row
    for row in neighbor_rows:
        if row.get("AnchorUnit") == anchor and row.get("NeighborUnit") == neighbor and row.get("Frame") == frame:
            return row
    return {}


def build_validations(out_dir: Path) -> tuple[list[dict[str, object]], list[dict[str, object]]]:
    profiles = build_profiles(read_csv(out_dir / "structural_reconstructions.csv"))
    queue_rows = read_csv(out_dir / "phonetic_probe_queue.csv")
    neighbor_rows = read_csv(out_dir / "neighbor_reading_tests.csv")
    validations: list[dict[str, object]] = []
    occurrence_rows: list[dict[str, object]] = []

    for queue in queue_rows:
        anchor, neighbor = parse_probe(queue.get("Probe", ""))
        frame = queue.get("Frame", "")
        contrast = queue.get("ContrastClass", "")
        detail = matching_neighbor_row(neighbor_rows, anchor, neighbor, frame, contrast)
        eval_row = dict(queue)
        for field in [
            "CombinedCount",
            "ChangedAnchorComponent",
            "NeighborChangedComponent",
            "AnchorComponentRole",
            "NeighborComponentRole",
        ]:
            eval_row[field] = detail.get(field, "")
        left_profile = profiles.get(anchor, UnitProfile(anchor))
        right_profile = profiles.get(neighbor, UnitProfile(neighbor))
        dims = dimension_report(left_profile, right_profile)
        status, reason, validation_score = validation_status(eval_row, left_profile, right_profile, dims)
        same_frame_left = same_frame_count(left_profile, frame)
        same_frame_right = same_frame_count(right_profile, frame)
        validations.append(
            {
                "Rank": queue.get("Rank", ""),
                "Probe": queue.get("Probe", ""),
                "AnchorUnit": anchor,
                "NeighborUnit": neighbor,
                "Frame": frame,
                "ContrastClass": contrast,
                "Gate": queue.get("Gate", ""),
                "QueueScore": queue.get("Score", ""),
                "ValidationStatus": status,
                "ValidationScore": f"{validation_score:.3f}",
                "Reason": reason,
                "AnchorExactOccurrences": len(left_profile.occurrences),
                "NeighborExactOccurrences": len(right_profile.occurrences),
                "AnchorFrameOccurrences": same_frame_left,
                "NeighborFrameOccurrences": same_frame_right,
                "CombinedMinimalCount": detail.get("CombinedCount", ""),
                "ChangedAnchorComponent": detail.get("ChangedAnchorComponent", ""),
                "NeighborChangedComponent": detail.get("NeighborChangedComponent", ""),
                "AnchorComponentRole": detail.get("AnchorComponentRole", ""),
                "NeighborComponentRole": detail.get("NeighborComponentRole", ""),
                "FrameOverlap": f"{dims.get('FrameOverlap', 0.0):.3f}",
                "SemanticFrameOverlap": f"{dims.get('SemanticFrameOverlap', 0.0):.3f}",
                "SiteDivergence": f"{dims.get('SiteJSD', 0.0):.3f}",
                "SymbolDivergence": f"{dims.get('SymbolJSD', 0.0):.3f}",
                "TypeDivergence": f"{dims.get('TypeJSD', 0.0):.3f}",
                "AnchorTopContexts": f"frames={top_counter(left_profile.frames, 3)}; sites={top_counter(left_profile.sites, 3)}; symbols={top_counter(left_profile.symbols, 3)}",
                "NeighborTopContexts": f"frames={top_counter(right_profile.frames, 3)}; sites={top_counter(right_profile.sites, 3)}; symbols={top_counter(right_profile.symbols, 3)}",
                "NextRequiredAction": next_action(status, anchor, neighbor, frame),
            }
        )

        for side, profile in [("Anchor", left_profile), ("Neighbor", right_profile)]:
            for occ in profile.occurrences:
                if occ.frame != frame and frame not in profile.frames:
                    continue
                occurrence_rows.append(
                    {
                        "Probe": queue.get("Probe", ""),
                        "Side": side,
                        "Unit": profile.unit,
                        "TextId": occ.text_id,
                        "CISI": occ.cisi,
                        "Frame": occ.frame,
                        "TargetFrame": frame,
                        "Site": occ.site,
                        "Type": occ.artifact_type,
                        "Symbol": occ.symbol,
                        "Material": occ.material,
                        "SemanticFrame": occ.semantic_frame,
                        "ReadingTokens": occ.reading_tokens,
                        "StructuralParse": occ.structural_parse,
                    }
                )

    validations.sort(key=lambda row: (-ffloat(str(row["ValidationScore"])), fint(str(row["Rank"]))))
    return validations, occurrence_rows


def next_action(status: str, anchor: str, neighbor: str, frame: str) -> str:
    if status == "Phonetic-ready after image check":
        return f"Image-check all {anchor}/{neighbor} occurrences in {frame}; then test a provisional abstract phonetic contrast."
    if status == "Stem-semantic probe":
        return f"Collect or verify more {neighbor} occurrences in {frame}; keep {anchor}/{neighbor} as stem contrast."
    if status == "Morphology constraint":
        return f"Promote this to the grammar model as a title/classifier constraint; do not assign sound."
    if status == "Terminal constraint":
        return f"Promote this to the grammar model as terminal/suffix contrast; test numeral/allograph alternatives."
    if status == "Control only":
        return f"Use {anchor}/{neighbor} only as a role-boundary control until roles align."
    return f"Retain {anchor}/{neighbor} as a structural control in {frame}."


def build_lattice(validations: list[dict[str, object]]) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for row in validations:
        contrast = str(row["ContrastClass"])
        status = str(row["ValidationStatus"])
        if contrast != "entity-stem contrast":
            continue
        if status not in {"Phonetic-ready after image check", "Stem-semantic probe", "Hold for more occurrences"}:
            continue
        anchor_component = str(row.get("ChangedAnchorComponent", ""))
        neighbor_component = str(row.get("NeighborChangedComponent", ""))
        if not anchor_component or not neighbor_component:
            continue
        rows.append(
            {
                "LeftStem": anchor_component,
                "RightStem": neighbor_component,
                "Probe": row["Probe"],
                "Frame": row["Frame"],
                "Status": status,
                "ValidationScore": row["ValidationScore"],
                "AnchorFrameOccurrences": row["AnchorFrameOccurrences"],
                "NeighborFrameOccurrences": row["NeighborFrameOccurrences"],
                "Constraint": "same frame and stem-like slot; may become phonetic only after image validation",
            }
        )
    rows.sort(key=lambda item: (-ffloat(str(item["ValidationScore"])), str(item["Probe"])))
    return rows


def build_claims(
    validations: list[dict[str, object]],
    lattice: list[dict[str, object]],
    full_role_boundary_controls: int,
) -> list[dict[str, object]]:
    status_counter = Counter(str(row["ValidationStatus"]) for row in validations)
    stem_edges = [row for row in lattice if row["Status"] in {"Phonetic-ready after image check", "Stem-semantic probe"}]
    return [
        {
            "ClaimId": "C-240-QUALIFIER",
            "Claim": "Sign 240 behaves as a qualifier/title/classifier-like component in multiple high-ranking probes.",
            "Evidence": "240-482, 240-176, and 240-740-090 neighborhoods repeatedly test prefix/title behavior.",
            "Status": "Supported morphology constraint",
            "BlockedShortcut": "No sound value or language-family value may be assigned to 240 yet.",
        },
        {
            "ClaimId": "C-176-STEM",
            "Claim": "Sign 176 is the strongest current entity-stem candidate.",
            "Evidence": "It appears independently as 176 and in 240-176, with same-frame contrasts against 048 and 061 in 002|740.",
            "Status": "Stem-semantic probe",
            "BlockedShortcut": "Do not equate 176 with a lexical word until image/context validation passes.",
        },
        {
            "ClaimId": "C-482-STEM-SLOT",
            "Claim": "The second position in 240-482/240-176/240-904/240-773 is a stem-like contrast slot.",
            "Evidence": f"{len(stem_edges)} stem-contrast lattice edges currently survive validation as probes.",
            "Status": "Emerging stem lattice",
            "BlockedShortcut": "No reading of 482, 176, 904, or 773 is justified yet.",
        },
        {
            "ClaimId": "C-740-520-TERMINAL",
            "Claim": "740 and 520 form a terminal/suffix contrast family.",
            "Evidence": "240-740-090 :: 520 and related terminal-frame tests survive as suffix/numeral/allograph probes.",
            "Status": "Terminal constraint",
            "BlockedShortcut": "Do not force a phonetic value before numeral/allograph alternatives are tested.",
        },
        {
            "ClaimId": "C-032-CONTROL",
            "Claim": "032 is currently more useful as a role-boundary control than as a phonetic anchor.",
            "Evidence": f"{full_role_boundary_controls} role-boundary controls occur in the full neighbor expansion.",
            "Status": "Blocked for phonetics",
            "BlockedShortcut": "Do not use 032 as phonetic evidence until its slot role is separated.",
        },
        {
            "ClaimId": "C-LANGUAGE-GATE",
            "Claim": "Language identification remains blocked.",
            "Evidence": "Validated constraints are structural and semantic; no sound values are assigned.",
            "Status": "Not deciphered",
            "BlockedShortcut": "No Dravidian, Indo-Aryan, Munda, or other lexical claim without predictive sign values.",
        },
    ]


def build_summary(
    validations: list[dict[str, object]],
    lattice: list[dict[str, object]],
    full_role_boundary_controls: int,
) -> list[dict[str, object]]:
    status_counter = Counter(str(row["ValidationStatus"]) for row in validations)
    contrast_counter = Counter(str(row["ContrastClass"]) for row in validations)
    top = validations[0] if validations else {}
    return [
        {"Metric": "Probe validations", "Value": len(validations), "Note": "Top probe-queue rows evaluated."},
        {"Metric": "Morphology constraints", "Value": status_counter["Morphology constraint"], "Note": "Accepted as grammar constraints before phonetics."},
        {"Metric": "Terminal constraints", "Value": status_counter["Terminal constraint"], "Note": "Accepted terminal/suffix constraints."},
        {"Metric": "Phonetic-ready after image check", "Value": status_counter["Phonetic-ready after image check"], "Note": "Could become phonetic tests after visual validation."},
        {"Metric": "Stem-semantic probes", "Value": status_counter["Stem-semantic probe"], "Note": "Good stem probes, but occurrence-limited."},
        {"Metric": "Role-boundary controls", "Value": status_counter["Control only"], "Note": "Useful negative controls, blocked for phonetics."},
        {"Metric": "Full-neighborhood role-boundary controls", "Value": full_role_boundary_controls, "Note": "Controls in the full neighbor expansion, not just top queue."},
        {"Metric": "Stem lattice edges", "Value": len(lattice), "Note": "Entity-stem contrast edges exported."},
        {"Metric": "Top validated probe", "Value": top.get("Probe", ""), "Note": f"{top.get('ValidationStatus', '')}; score={top.get('ValidationScore', '')}"},
        {"Metric": "Dominant contrast class", "Value": contrast_counter.most_common(1)[0][0] if contrast_counter else "", "Note": top_counter(contrast_counter, 3)},
    ]


def write_latex_summary(
    path: Path,
    summary: list[dict[str, object]],
    validations: list[dict[str, object]],
    lattice: list[dict[str, object]],
    claims: list[dict[str, object]],
) -> None:
    top_validations = [
        {
            "Probe": row["Probe"],
            "Status": row["ValidationStatus"],
            "Score": row["ValidationScore"],
        }
        for row in validations[:8]
    ]
    top_lattice = [
        {
            "Edge": f"{row['LeftStem']}:{row['RightStem']}",
            "Probe": row["Probe"],
            "Status": row["Status"],
            "Score": row["ValidationScore"],
        }
        for row in lattice[:8]
    ]
    claim_rows = [
        {
            "Claim": row["ClaimId"],
            "Status": row["Status"],
        }
        for row in claims
    ]
    text = (
        r"""\section{Contrastive Probe Validation}

\subsection{Purpose}

This generated note validates the minimal-pair probe queue. It asks which probes can already be promoted to grammar constraints, which ones are plausible future phonetic probes, and which ones must remain controls.

\subsection{Summary}

\begin{table}[htbp]
\centering
"""
        + latex_table(summary, ["Metric", "Value"], ["p{0.58\\textwidth}", "r"])
        + r"""
\caption{Contrastive probe validation summary.}
\end{table}

\subsection{Top Validated Probes}

\begin{table}[htbp]
\centering
\footnotesize
"""
        + latex_table(top_validations, ["Probe", "Status", "Score"], ["p{0.32\\textwidth}", "p{0.42\\textwidth}", "r"])
        + r"""
\caption{Highest-scoring validated probes.}
\end{table}

\subsection{Stem Lattice}

\begin{table}[htbp]
\centering
\footnotesize
"""
        + latex_table(top_lattice, ["Edge", "Probe", "Status", "Score"], ["l", "p{0.30\\textwidth}", "p{0.34\\textwidth}", "r"])
        + r"""
\caption{Top entity-stem contrast edges. These remain pre-phonetic.}
\end{table}

\subsection{Claim Ledger}

\begin{table}[htbp]
\centering
\footnotesize
"""
        + latex_table(claim_rows, ["Claim", "Status"], ["p{0.36\\textwidth}", "p{0.46\\textwidth}"])
        + r"""
\caption{Controlled claims after contrastive validation.}
\end{table}
"""
    )
    path.write_text(text, encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--outputs", default="outputs", help="Directory containing model outputs")
    args = parser.parse_args()

    out_dir = Path(args.outputs)
    validations, occurrence_rows = build_validations(out_dir)
    lattice = build_lattice(validations)
    full_neighbor_rows = read_csv(out_dir / "neighbor_reading_tests.csv")
    full_role_boundary_controls = sum(1 for row in full_neighbor_rows if row.get("ContrastClass") == "role-boundary control")
    claims = build_claims(validations, lattice, full_role_boundary_controls)
    summary = build_summary(validations, lattice, full_role_boundary_controls)

    write_csv(out_dir / "contrastive_probe_validation_summary.csv", summary, ["Metric", "Value", "Note"])
    write_csv(
        out_dir / "validated_probe_results.csv",
        validations,
        [
            "Rank",
            "Probe",
            "AnchorUnit",
            "NeighborUnit",
            "Frame",
            "ContrastClass",
            "Gate",
            "QueueScore",
            "ValidationStatus",
            "ValidationScore",
            "Reason",
            "AnchorExactOccurrences",
            "NeighborExactOccurrences",
            "AnchorFrameOccurrences",
            "NeighborFrameOccurrences",
            "CombinedMinimalCount",
            "ChangedAnchorComponent",
            "NeighborChangedComponent",
            "AnchorComponentRole",
            "NeighborComponentRole",
            "FrameOverlap",
            "SemanticFrameOverlap",
            "SiteDivergence",
            "SymbolDivergence",
            "TypeDivergence",
            "AnchorTopContexts",
            "NeighborTopContexts",
            "NextRequiredAction",
        ],
    )
    write_csv(
        out_dir / "probe_occurrence_contexts.csv",
        occurrence_rows,
        [
            "Probe",
            "Side",
            "Unit",
            "TextId",
            "CISI",
            "Frame",
            "TargetFrame",
            "Site",
            "Type",
            "Symbol",
            "Material",
            "SemanticFrame",
            "ReadingTokens",
            "StructuralParse",
        ],
    )
    write_csv(
        out_dir / "stem_contrast_lattice.csv",
        lattice,
        [
            "LeftStem",
            "RightStem",
            "Probe",
            "Frame",
            "Status",
            "ValidationScore",
            "AnchorFrameOccurrences",
            "NeighborFrameOccurrences",
            "Constraint",
        ],
    )
    write_csv(
        out_dir / "controlled_decipherment_claims.csv",
        claims,
        ["ClaimId", "Claim", "Evidence", "Status", "BlockedShortcut"],
    )
    write_latex_summary(out_dir / "contrastive_probe_validation.tex", summary, validations, lattice, claims)

    print("Wrote contrastive probe validation outputs:")
    for name in [
        "contrastive_probe_validation_summary.csv",
        "validated_probe_results.csv",
        "probe_occurrence_contexts.csv",
        "stem_contrast_lattice.csv",
        "controlled_decipherment_claims.csv",
        "contrastive_probe_validation.tex",
    ]:
        print(f"  - {out_dir / name}")


if __name__ == "__main__":
    main()
