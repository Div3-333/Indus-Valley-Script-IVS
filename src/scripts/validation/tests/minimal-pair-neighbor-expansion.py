#!/usr/bin/env python3
"""Expand constrained anchors into their minimal-pair neighborhoods.

The constraint solver ranks a small set of anchor skeletons. This script takes
the next step: it finds exact and component-level same-frame neighbors, classifies
the contrast, and builds a queue of morphology/phonetic probes. It remains
pre-phonetic; every phonetic gate stays closed until a contrast predicts all
matching contexts.
"""

from __future__ import annotations

import argparse
import csv
import re
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path


TOKEN_RE = re.compile(r"(?<!\d)\d{3,4}(?!\d)")
SUB_RE = re.compile(r"Substitution@(\d+):(\d{3,4})>(\d{3,4})")
ADD_DEL_RE = re.compile(r"(Prefix|Suffix)(Addition|Deletion):(\d{3,4})")


@dataclass(frozen=True)
class SignRole:
    sign: str
    variable: str
    functional_class: str
    proto_gloss: str
    proposed_role: str = ""
    interpretation: str = ""


@dataclass
class FillerProfile:
    count: int = 0
    frames: Counter[str] = None  # type: ignore[assignment]
    semantic_frames: Counter[str] = None  # type: ignore[assignment]
    sites: Counter[str] = None  # type: ignore[assignment]
    symbols: Counter[str] = None  # type: ignore[assignment]
    types: Counter[str] = None  # type: ignore[assignment]

    def __post_init__(self) -> None:
        if self.frames is None:
            self.frames = Counter()
        if self.semantic_frames is None:
            self.semantic_frames = Counter()
        if self.sites is None:
            self.sites = Counter()
        if self.symbols is None:
            self.symbols = Counter()
        if self.types is None:
            self.types = Counter()


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


def load_sign_roles(out_dir: Path) -> dict[str, SignRole]:
    roles: dict[str, SignRole] = {}
    for row in read_csv(out_dir / "phonetic_variable_map.csv"):
        sign = row["Sign"]
        roles[sign] = SignRole(
            sign=sign,
            variable=row.get("Variable", ""),
            functional_class=row.get("FunctionalClass", ""),
            proto_gloss=row.get("ProtoGloss", ""),
        )

    for row in read_csv(out_dir / "morpheme_slot_assignments.csv"):
        sign = row["Sign"]
        base = roles.get(sign, SignRole(sign, row.get("AbstractVariable", ""), row.get("FunctionalClass", ""), ""))
        roles[sign] = SignRole(
            sign=sign,
            variable=row.get("AbstractVariable", base.variable),
            functional_class=row.get("FunctionalClass", base.functional_class),
            proto_gloss=base.proto_gloss,
            proposed_role=row.get("ProposedRole", ""),
            interpretation=row.get("ComponentInterpretation", ""),
        )
    return roles


def role_label(sign: str, roles: dict[str, SignRole]) -> str:
    role = roles.get(sign)
    if not role:
        return "UNRESOLVED_SIGN"
    if role.proposed_role:
        return role.proposed_role
    if role.functional_class == "CLASSIFIER":
        return "CLASSIFIER_TITLE"
    if role.functional_class == "TERMINAL":
        return "TERMINAL_TITLE_SUFFIX"
    if role.functional_class == "FORMULA_MARKER":
        return "FORMULA_MARKER"
    if role.functional_class == "ROOT_OR_UNRESOLVED":
        return "ENTITY_STEM_CANDIDATE"
    if role.functional_class == "SLOT_MODIFIER":
        return "SLOT_MODIFIER"
    return role.functional_class or "UNRESOLVED_SIGN"


def build_filler_profiles(structural_rows: list[dict[str, str]]) -> dict[str, FillerProfile]:
    profiles: dict[str, FillerProfile] = defaultdict(FillerProfile)
    for row in structural_rows:
        if row.get("PhoneticReadiness") not in {"High", "Medium"}:
            continue
        for slot in parse_slot_fillers(row.get("SlotFillers")):
            filler = slot["Filler"]
            profile = profiles[filler]
            profile.count += 1
            profile.frames[slot["Frame"]] += 1
            profile.semantic_frames[row.get("SemanticFrame", "")] += 1
            profile.sites[row.get("Site", "") or "Unknown"] += 1
            profile.symbols[normalize_symbol(row.get("Symbol"))] += 1
            profile.types[normalize_type(row.get("Type"))] += 1
    return profiles


def parse_relation(row: dict[str, str]) -> dict[str, object]:
    relation = row.get("Relation", "")
    sub = SUB_RE.match(relation)
    if sub:
        position, left, right = sub.groups()
        return {
            "Kind": "Substitution",
            "Position": fint(position),
            "ChangedLeft": left,
            "ChangedRight": right,
            "ChangedSigns": [left, right],
        }
    add_del = ADD_DEL_RE.match(relation)
    if add_del:
        side, operation, sign = add_del.groups()
        return {
            "Kind": f"{side}{operation}",
            "Position": 1 if side == "Prefix" else -1,
            "ChangedLeft": sign,
            "ChangedRight": "",
            "ChangedSigns": [sign],
        }
    return {"Kind": "Other", "Position": 0, "ChangedLeft": "", "ChangedRight": "", "ChangedSigns": []}


def changed_for_side(row: dict[str, str], side: str, relation: dict[str, object]) -> tuple[str, str]:
    tokens_a = sign_tokens(row.get("FillerA"))
    tokens_b = sign_tokens(row.get("FillerB"))
    kind = str(relation["Kind"])
    if kind == "Substitution":
        index = int(relation["Position"]) - 1
        if 0 <= index < len(tokens_a) and 0 <= index < len(tokens_b):
            if side == "A":
                return tokens_a[index], tokens_b[index]
            return tokens_b[index], tokens_a[index]
    if kind.endswith("Addition"):
        sign = str(relation["ChangedLeft"])
        if side == "A":
            return "", sign
        return sign, ""
    if kind.endswith("Deletion"):
        sign = str(relation["ChangedLeft"])
        if side == "A":
            return sign, ""
        return "", sign
    return "", ""


def classify_contrast(
    frame: str,
    relation: dict[str, object],
    anchor_component: str,
    neighbor_component: str,
    roles: dict[str, SignRole],
    anchor_skeleton: str,
) -> str:
    kind = str(relation["Kind"])
    anchor_role = role_label(anchor_component, roles)
    neighbor_role = role_label(neighbor_component, roles)
    anchor_entity = "ENTITY_STEM" in anchor_role or "ROOT" in anchor_role
    neighbor_entity = "ENTITY_STEM" in neighbor_role or "ROOT" in neighbor_role
    anchor_qualifier = "QUALIFIER" in anchor_role or "CLASSIFIER" in anchor_role or "FORMULA" in anchor_role
    neighbor_qualifier = "QUALIFIER" in neighbor_role or "CLASSIFIER" in neighbor_role or "FORMULA" in neighbor_role
    anchor_terminal = "TERMINAL" in anchor_role or "FINAL" in anchor_role or "TERMINAL" in anchor_skeleton
    neighbor_terminal = "TERMINAL" in neighbor_role or "FINAL" in neighbor_role

    if kind.startswith("Prefix"):
        return "prefix/title/classifier test"
    if kind.startswith("Suffix"):
        return "suffix/terminal/numeral-or-allograph test"
    if anchor_entity and neighbor_entity and not ("TERMINAL" in anchor_skeleton and len(sign_tokens(anchor_component)) == 1):
        return "entity-stem contrast"
    if (anchor_entity and neighbor_qualifier) or (neighbor_entity and anchor_qualifier):
        return "role-boundary control"
    if (anchor_entity and neighbor_terminal) or (neighbor_entity and anchor_terminal):
        return "role-boundary control"
    if anchor_qualifier and neighbor_qualifier:
        return "classifier/title contrast"
    if anchor_terminal and neighbor_terminal:
        return "terminal/suffix contrast"
    if "CLASSIFIER" in f"{anchor_role} {neighbor_role}" or frame.startswith("<START>"):
        return "classifier/title contrast"
    if "TERMINAL" in f"{anchor_role} {neighbor_role}" or "<END>" in frame:
        return "terminal/suffix contrast"
    if "FORMULA_MARKER" in f"{anchor_role} {neighbor_role}":
        return "formula-marker contrast"
    if "SLOT_MODIFIER" in f"{anchor_role} {neighbor_role}":
        return "slot-modifier or allograph test"
    return "same-frame semantic/phonetic contrast"


def contrast_quality(contrast_class: str, count: int, exact: bool, anchor_tier: str) -> float:
    count_score = clamp(count / 20.0)
    contrast_score = {
        "entity-stem contrast": 1.0,
        "prefix/title/classifier test": 0.86,
        "suffix/terminal/numeral-or-allograph test": 0.82,
        "classifier/title contrast": 0.78,
        "terminal/suffix contrast": 0.74,
        "formula-marker contrast": 0.68,
        "slot-modifier or allograph test": 0.62,
        "role-boundary control": 0.58,
    }.get(contrast_class, 0.56)
    tier_score = {"A": 1.0, "B": 0.82, "C": 0.62}.get(anchor_tier, 0.45)
    return clamp(count_score * 0.36 + contrast_score * 0.34 + tier_score * 0.18 + (0.12 if exact else 0.02))


def phonetic_gate(contrast_class: str, score: float, exact: bool) -> str:
    if contrast_class == "entity-stem contrast" and score >= 0.78 and exact:
        return "Phonetic probe after image/context validation"
    if contrast_class == "entity-stem contrast" and score >= 0.70:
        return "High-priority stem semantics before phonetics"
    if contrast_class in {"prefix/title/classifier test", "classifier/title contrast"}:
        return "Morphology probe before phonetics"
    if contrast_class in {"suffix/terminal/numeral-or-allograph test", "terminal/suffix contrast"}:
        return "Suffix/numeral/allograph probe before phonetics"
    if contrast_class == "role-boundary control":
        return "Role-boundary control before phonetics"
    return "Structural neighbor only"


def required_next_test(contrast_class: str, anchor: str, neighbor: str, frame: str) -> str:
    if contrast_class == "entity-stem contrast":
        return f"Image-check all {anchor} and {neighbor} occurrences in frame {frame}; test whether context changes with the substituted stem."
    if "prefix" in contrast_class or "classifier" in contrast_class:
        return f"Test whether the added/substituted initial component changes title/classifier class without changing frame {frame}."
    if "suffix" in contrast_class or "terminal" in contrast_class:
        return f"Test whether the final component behaves as suffix, terminal marker, numeral, or allograph in frame {frame}."
    if contrast_class == "role-boundary control":
        return f"Check whether {anchor} and {neighbor} occupy the same functional role in frame {frame}; do not use for phonetics until roles match."
    return f"Keep as same-frame control for {anchor} against {neighbor} in frame {frame}."


def build_neighbor_rows(out_dir: Path) -> list[dict[str, object]]:
    candidates = read_csv(out_dir / "constrained_reading_candidates.csv")
    candidate_map = {row["Unit"]: row for row in candidates}
    anchor_units = set(candidate_map)
    anchor_components = {unit: sign_tokens(unit) for unit in anchor_units}
    roles = load_sign_roles(out_dir)
    profiles = build_filler_profiles(read_csv(out_dir / "structural_reconstructions.csv"))
    minimal_rows = read_csv(out_dir / "phonetic_minimal_tests.csv")

    rows_by_key: dict[tuple[object, ...], dict[str, object]] = {}
    for row in minimal_rows:
        relation = parse_relation(row)
        filler_a = row.get("FillerA", "")
        filler_b = row.get("FillerB", "")
        tokens_a = sign_tokens(filler_a)
        tokens_b = sign_tokens(filler_b)
        changed_signs = set(str(sign) for sign in relation.get("ChangedSigns", []))

        for anchor in anchor_units:
            candidate = candidate_map[anchor]
            tier = candidate.get("EvidenceTier", "")
            anchor_score = ffloat(candidate.get("Score"))
            anchor_skeleton = candidate.get("SkeletonReading", "")
            anchor_side = ""
            evidence_scope = ""
            neighbor = ""
            anchor_component = ""
            neighbor_component = ""

            if filler_a == anchor:
                anchor_side = "A"
                evidence_scope = "ExactAnchorNeighbor"
                neighbor = filler_b
                anchor_component, neighbor_component = changed_for_side(row, "A", relation)
            elif filler_b == anchor:
                anchor_side = "B"
                evidence_scope = "ExactAnchorNeighbor"
                neighbor = filler_a
                anchor_component, neighbor_component = changed_for_side(row, "B", relation)
            else:
                component_hits = changed_signs.intersection(anchor_components[anchor])
                if not component_hits:
                    continue
                anchor_component = sorted(component_hits)[0]
                evidence_scope = "ComponentNeighbor"
                if anchor_component in tokens_a:
                    anchor_side = "A"
                    neighbor = filler_b
                    anchor_component, neighbor_component = changed_for_side(row, "A", relation)
                elif anchor_component in tokens_b:
                    anchor_side = "B"
                    neighbor = filler_a
                    anchor_component, neighbor_component = changed_for_side(row, "B", relation)
                else:
                    continue

            if not anchor_component and evidence_scope == "ExactAnchorNeighbor":
                anchor_tokens = sign_tokens(anchor)
                anchor_component = anchor_tokens[0] if anchor_tokens else ""
            if not neighbor_component:
                changed = [sign for sign in relation.get("ChangedSigns", []) if sign != anchor_component]
                neighbor_component = str(changed[0]) if changed else ""

            exact = evidence_scope == "ExactAnchorNeighbor"
            count = fint(row.get("CombinedCount"))
            frame = row.get("Frame", "")
            contrast_class = classify_contrast(
                frame,
                relation,
                anchor_component,
                neighbor_component,
                roles,
                anchor_skeleton,
            )
            profile = profiles.get(neighbor, FillerProfile())
            context_presence = clamp(profile.count / 8.0)
            score = clamp(
                contrast_quality(contrast_class, count, exact, tier) * 0.72
                + anchor_score * 0.18
                + context_presence * 0.10
            )
            gate = phonetic_gate(contrast_class, score, exact)
            key = (anchor, evidence_scope, frame, filler_a, filler_b, row.get("Relation", ""))
            candidate_row = {
                "AnchorUnit": anchor,
                "AnchorSkeleton": anchor_skeleton,
                "AnchorTier": tier,
                "EvidenceScope": evidence_scope,
                "Frame": frame,
                "AnchorSide": anchor_side,
                "NeighborUnit": neighbor,
                "NeighborAbstract": row.get("AbstractB", "") if anchor_side == "A" else row.get("AbstractA", ""),
                "Relation": row.get("Relation", ""),
                "TestType": row.get("TestType", ""),
                "CombinedCount": count,
                "ContrastClass": contrast_class,
                "ChangedAnchorComponent": anchor_component,
                "NeighborChangedComponent": neighbor_component,
                "AnchorComponentRole": role_label(anchor_component, roles),
                "NeighborComponentRole": role_label(neighbor_component, roles),
                "NeighborOccurrences": profile.count,
                "NeighborTopFrames": top_counter(profile.frames),
                "NeighborTopSemanticFrames": top_counter(profile.semantic_frames),
                "NeighborTopSites": top_counter(profile.sites),
                "NeighborTopSymbols": top_counter(profile.symbols),
                "Score": f"{score:.3f}",
                "PhoneticGate": gate,
                "RequiredNextTest": required_next_test(contrast_class, anchor, neighbor, frame),
            }
            previous = rows_by_key.get(key)
            if previous is None or ffloat(str(previous["Score"])) < score:
                rows_by_key[key] = candidate_row

    rows = list(rows_by_key.values())
    rows.sort(key=lambda item: (-ffloat(str(item["Score"])), str(item["AnchorUnit"]), str(item["NeighborUnit"])))
    return rows


def build_anchor_summaries(rows: list[dict[str, object]]) -> list[dict[str, object]]:
    grouped: dict[str, list[dict[str, object]]] = defaultdict(list)
    for row in rows:
        grouped[str(row["AnchorUnit"])].append(row)

    summaries: list[dict[str, object]] = []
    for anchor, anchor_rows in grouped.items():
        exact = [row for row in anchor_rows if row["EvidenceScope"] == "ExactAnchorNeighbor"]
        component = [row for row in anchor_rows if row["EvidenceScope"] == "ComponentNeighbor"]
        contrast_counter = Counter(str(row["ContrastClass"]) for row in anchor_rows)
        top = anchor_rows[0]
        summaries.append(
            {
                "AnchorUnit": anchor,
                "AnchorSkeleton": top["AnchorSkeleton"],
                "AnchorTier": top["AnchorTier"],
                "NeighborTests": len(anchor_rows),
                "ExactNeighborTests": len(exact),
                "ComponentNeighborTests": len(component),
                "TopNeighbor": top["NeighborUnit"],
                "TopContrastClass": top["ContrastClass"],
                "TopScore": top["Score"],
                "ContrastMix": top_counter(contrast_counter),
                "NextSafeMove": top["RequiredNextTest"],
            }
        )
    summaries.sort(key=lambda row: (-ffloat(str(row["TopScore"])), str(row["AnchorUnit"])))
    return summaries


def build_component_contrasts(rows: list[dict[str, object]]) -> list[dict[str, object]]:
    grouped: dict[tuple[str, str, str], list[dict[str, object]]] = defaultdict(list)
    for row in rows:
        key = (
            str(row["ChangedAnchorComponent"]),
            str(row["NeighborChangedComponent"]),
            str(row["ContrastClass"]),
        )
        grouped[key].append(row)

    output: list[dict[str, object]] = []
    for (anchor_component, neighbor_component, contrast_class), group in grouped.items():
        frames = Counter(str(row["Frame"]) for row in group)
        anchors = Counter(str(row["AnchorUnit"]) for row in group)
        scopes = Counter(str(row["EvidenceScope"]) for row in group)
        max_score = max(ffloat(str(row["Score"])) for row in group)
        max_count = max(fint(str(row["CombinedCount"])) for row in group)
        gate_counter = Counter(str(row["PhoneticGate"]) for row in group)
        output.append(
            {
                "AnchorComponent": anchor_component,
                "NeighborComponent": neighbor_component,
                "ContrastClass": contrast_class,
                "EvidenceRows": len(group),
                "MaxCombinedCount": max_count,
                "MaxScore": f"{max_score:.3f}",
                "Frames": top_counter(frames),
                "Anchors": top_counter(anchors),
                "EvidenceScopes": top_counter(scopes),
                "DominantGate": gate_counter.most_common(1)[0][0] if gate_counter else "",
            }
        )
    output.sort(key=lambda row: (-ffloat(str(row["MaxScore"])), -fint(str(row["MaxCombinedCount"]))))
    return output


def build_probe_queue(rows: list[dict[str, object]]) -> list[dict[str, object]]:
    priority_gates = {
        "Phonetic probe after image/context validation",
        "High-priority stem semantics before phonetics",
        "Morphology probe before phonetics",
        "Suffix/numeral/allograph probe before phonetics",
    }
    queue: list[dict[str, object]] = []
    seen: set[tuple[str, str, str]] = set()
    for row in rows:
        gate = str(row["PhoneticGate"])
        if gate not in priority_gates:
            continue
        key = (str(row["AnchorUnit"]), str(row["NeighborUnit"]), str(row["ContrastClass"]))
        if key in seen:
            continue
        seen.add(key)
        queue.append(
            {
                "Rank": len(queue) + 1,
                "Probe": f"{row['AnchorUnit']} :: {row['NeighborUnit']}",
                "Frame": row["Frame"],
                "ContrastClass": row["ContrastClass"],
                "Score": row["Score"],
                "Gate": gate,
                "WhyPriority": row["RequiredNextTest"],
            }
        )
        if len(queue) >= 30:
            break
    return queue


def build_summary_rows(
    rows: list[dict[str, object]],
    anchor_summaries: list[dict[str, object]],
    component_rows: list[dict[str, object]],
    probe_rows: list[dict[str, object]],
) -> list[dict[str, object]]:
    scope_counter = Counter(str(row["EvidenceScope"]) for row in rows)
    contrast_counter = Counter(str(row["ContrastClass"]) for row in rows)
    gate_counter = Counter(str(row["PhoneticGate"]) for row in rows)
    top = rows[0] if rows else {}
    return [
        {"Metric": "Anchor neighborhoods expanded", "Value": len(anchor_summaries), "Note": "Anchors with at least one neighbor test."},
        {"Metric": "Neighbor tests", "Value": len(rows), "Note": "Exact-anchor plus component-level tests."},
        {"Metric": "Exact anchor-neighbor tests", "Value": scope_counter["ExactAnchorNeighbor"], "Note": "Whole anchor unit participates directly."},
        {"Metric": "Component neighbor tests", "Value": scope_counter["ComponentNeighbor"], "Note": "Reusable anchor component participates in a contrast."},
        {"Metric": "Component contrast groups", "Value": len(component_rows), "Note": "Aggregated component-to-component tests."},
        {"Metric": "Probe queue items", "Value": len(probe_rows), "Note": "Highest-priority next tests."},
        {"Metric": "Top contrast class", "Value": contrast_counter.most_common(1)[0][0] if contrast_counter else "", "Note": top_counter(contrast_counter, 3)},
        {"Metric": "Top gate", "Value": gate_counter.most_common(1)[0][0] if gate_counter else "", "Note": top_counter(gate_counter, 3)},
        {"Metric": "Best neighbor probe", "Value": f"{top.get('AnchorUnit', '')} :: {top.get('NeighborUnit', '')}", "Note": top.get("ContrastClass", "")},
    ]


def write_latex_summary(
    path: Path,
    summary: list[dict[str, object]],
    anchor_summaries: list[dict[str, object]],
    probe_rows: list[dict[str, object]],
) -> None:
    top_anchors = [
        {
            "Anchor": row["AnchorUnit"],
            "Tests": row["NeighborTests"],
            "Top contrast": row["TopContrastClass"],
            "Score": row["TopScore"],
        }
        for row in anchor_summaries[:8]
    ]
    top_probes = [
        {
            "Probe": row["Probe"],
            "Frame": row["Frame"],
            "Class": row["ContrastClass"],
            "Score": row["Score"],
        }
        for row in probe_rows[:8]
    ]
    text = (
        r"""\section{Minimal-Pair Neighbor Expansion}

\subsection{Purpose}

This generated note expands the constrained anchor skeletons into their nearest same-frame minimal-pair neighborhoods. Its purpose is to find the contrasts most likely to separate titles, stems, suffixes, numerals, allographs, and eventual phonetic values.

\subsection{Summary}

\begin{table}[htbp]
\centering
"""
        + latex_table(summary, ["Metric", "Value"], ["p{0.58\\textwidth}", "r"])
        + r"""
\caption{Minimal-pair neighbor expansion summary.}
\end{table}

\subsection{Top Anchor Neighborhoods}

\begin{table}[htbp]
\centering
\footnotesize
"""
        + latex_table(top_anchors, ["Anchor", "Tests", "Top contrast", "Score"], ["l", "r", "p{0.42\\textwidth}", "r"])
        + r"""
\caption{Anchor neighborhoods with highest-scoring neighbor tests.}
\end{table}

\subsection{Probe Queue}

\begin{table}[htbp]
\centering
\footnotesize
"""
        + latex_table(top_probes, ["Probe", "Frame", "Class", "Score"], ["p{0.26\\textwidth}", "l", "p{0.34\\textwidth}", "r"])
        + r"""
\caption{Top next tests. These probes remain pre-phonetic until image and context checks pass.}
\end{table}
"""
    )
    path.write_text(text, encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--outputs", default="outputs", help="Directory containing model outputs")
    args = parser.parse_args()

    out_dir = Path(args.outputs)
    rows = build_neighbor_rows(out_dir)
    anchor_summaries = build_anchor_summaries(rows)
    component_rows = build_component_contrasts(rows)
    probe_rows = build_probe_queue(rows)
    summary = build_summary_rows(rows, anchor_summaries, component_rows, probe_rows)

    write_csv(out_dir / "neighbor_expansion_summary.csv", summary, ["Metric", "Value", "Note"])
    write_csv(
        out_dir / "expanded_anchor_neighborhoods.csv",
        anchor_summaries,
        [
            "AnchorUnit",
            "AnchorSkeleton",
            "AnchorTier",
            "NeighborTests",
            "ExactNeighborTests",
            "ComponentNeighborTests",
            "TopNeighbor",
            "TopContrastClass",
            "TopScore",
            "ContrastMix",
            "NextSafeMove",
        ],
    )
    write_csv(
        out_dir / "neighbor_reading_tests.csv",
        rows,
        [
            "AnchorUnit",
            "AnchorSkeleton",
            "AnchorTier",
            "EvidenceScope",
            "Frame",
            "AnchorSide",
            "NeighborUnit",
            "NeighborAbstract",
            "Relation",
            "TestType",
            "CombinedCount",
            "ContrastClass",
            "ChangedAnchorComponent",
            "NeighborChangedComponent",
            "AnchorComponentRole",
            "NeighborComponentRole",
            "NeighborOccurrences",
            "NeighborTopFrames",
            "NeighborTopSemanticFrames",
            "NeighborTopSites",
            "NeighborTopSymbols",
            "Score",
            "PhoneticGate",
            "RequiredNextTest",
        ],
    )
    write_csv(
        out_dir / "component_contrast_tests.csv",
        component_rows,
        [
            "AnchorComponent",
            "NeighborComponent",
            "ContrastClass",
            "EvidenceRows",
            "MaxCombinedCount",
            "MaxScore",
            "Frames",
            "Anchors",
            "EvidenceScopes",
            "DominantGate",
        ],
    )
    write_csv(
        out_dir / "phonetic_probe_queue.csv",
        probe_rows,
        ["Rank", "Probe", "Frame", "ContrastClass", "Score", "Gate", "WhyPriority"],
    )
    write_latex_summary(out_dir / "minimal_pair_neighbor_expansion.tex", summary, anchor_summaries, probe_rows)

    print("Wrote minimal-pair neighbor expansion outputs:")
    for name in [
        "neighbor_expansion_summary.csv",
        "expanded_anchor_neighborhoods.csv",
        "neighbor_reading_tests.csv",
        "component_contrast_tests.csv",
        "phonetic_probe_queue.csv",
        "minimal_pair_neighbor_expansion.tex",
    ]:
        print(f"  - {out_dir / name}")


if __name__ == "__main__":
    main()
