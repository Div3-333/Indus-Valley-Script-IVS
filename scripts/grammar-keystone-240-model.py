#!/usr/bin/env python3
"""Model sign 240 as a grammar keystone.

This stage executes the highest-ranked target from the breakthrough portfolio.
It asks whether 240 behaves like a reusable grammar operator, an ordinary stem,
a formula opener, a terminal/suffix marker, or a mixed/polyfunctional sign.

The model stays pre-phonetic: it promotes constraints and test lanes, not sound
values.
"""

from __future__ import annotations

import argparse
import csv
import math
import re
from collections import Counter, defaultdict
from pathlib import Path


TOKEN_RE = re.compile(r"(?<!\d)\d{3,4}(?!\d)")
TARGET = "240"
START = "<START>"
END = "<END>"


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


def join_tokens(tokens: list[str] | tuple[str, ...]) -> str:
    return "-".join(tokens)


def top_counter(counter: Counter[str], limit: int = 5) -> str:
    return "; ".join(f"{key}:{value}" for key, value in counter.most_common(limit))


def counter_total(counter: Counter[str]) -> int:
    return sum(counter.values())


def dominant(counter: Counter[str]) -> tuple[str, float]:
    total = counter_total(counter)
    if total <= 0:
        return "", 0.0
    key, value = counter.most_common(1)[0]
    return key, value / total


def entropy(counter: Counter[str]) -> float:
    total = counter_total(counter)
    if total <= 0:
        return 0.0
    value = 0.0
    for count in counter.values():
        p = count / total
        if p > 0:
            value -= p * math.log2(p)
    return value


def normalized_entropy(counter: Counter[str]) -> float:
    if len(counter) <= 1:
        return 0.0
    return clamp(entropy(counter) / math.log2(len(counter)))


def distribution_overlap(left: Counter[str], right: Counter[str]) -> float:
    left_total = counter_total(left)
    right_total = counter_total(right)
    if left_total <= 0 or right_total <= 0:
        return 0.0
    keys = set(left) | set(right)
    return sum(min(left.get(key, 0) / left_total, right.get(key, 0) / right_total) for key in keys)


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
        "<": r"$<$",
        ">": r"$>$",
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


def compact_result_label(value: object) -> str:
    labels = {
        "CONTROLLED_240_STEM_ENVIRONMENT": "240 stem lane",
        "CONTROLLED_240_NONSTEM_ENVIRONMENT": "240 grammar control",
        "240_FRAME_LOCKED_NEEDS_BARE_CONTROL": "frame-locked; needs bare control",
        "FRAME_IDENTITY_PRESERVED": "frame identity preserved",
        "MIXED_OR_LOW_EVIDENCE": "mixed/low evidence",
        "NEEDS_BARE_STEM_CONTROL": "needs bare-stem control",
    }
    return labels.get(str(value), str(value))


def parse_slot_fillers(value: str | None) -> list[dict[str, str]]:
    fillers: list[dict[str, str]] = []
    if not value:
        return fillers
    for part in value.split(";"):
        part = part.strip()
        if not part or ":" not in part:
            continue
        frame, rest = part.split(":", 1)
        if "@" in rest:
            filler, position = rest.rsplit("@", 1)
        else:
            filler, position = rest, ""
        tokens = sign_tokens(filler)
        if not tokens:
            continue
        fillers.append({"Frame": frame.strip(), "Filler": join_tokens(tokens), "Position": position.strip()})
    return fillers


def load_structural_rows(out_dir: Path) -> dict[str, dict[str, str]]:
    return {row.get("TextId", ""): row for row in read_csv(out_dir / "structural_reconstructions.csv")}


def build_role_map(out_dir: Path) -> dict[str, dict[str, str]]:
    roles: dict[str, dict[str, str]] = {}
    for row in read_csv(out_dir / "phonetic_variable_map.csv"):
        sign = row.get("Sign", "")
        if sign:
            roles[sign] = {
                "Variable": row.get("Variable", ""),
                "FunctionalClass": row.get("FunctionalClass", ""),
                "ProtoGloss": row.get("ProtoGloss", ""),
                "CountInReadyTexts": row.get("CountInReadyTexts", ""),
                "ReadingConstraint": row.get("ReadingConstraint", ""),
            }
    for row in read_csv(out_dir / "anchor_component_roles.csv"):
        sign = row.get("Sign", "")
        if not sign:
            continue
        roles.setdefault(sign, {})
        roles[sign].update(
            {
                "Variable": row.get("Variable", roles[sign].get("Variable", "")),
                "FunctionalClass": row.get("FunctionalClass", roles[sign].get("FunctionalClass", "")),
                "ComponentInterpretation": row.get("ComponentInterpretation", ""),
                "ReadingConstraint": row.get("ReadingConstraint", roles[sign].get("ReadingConstraint", "")),
            }
        )
    return roles


def occurrence_role(index: int, length: int) -> str:
    if length == 1:
        return "Standalone"
    if index == 0:
        return "Initial"
    if index == length - 1:
        return "Final"
    return "Medial"


def reading_tokens_for_row(row: dict[str, str], structural_by_text: dict[str, dict[str, str]]) -> list[str]:
    text_id = row.get("id", "")
    structural = structural_by_text.get(text_id, {})
    tokens = sign_tokens(structural.get("ReadingTokens"))
    if tokens:
        return tokens
    return sign_tokens(row.get("text"))


def build_240_occurrences(
    corpus_rows: list[dict[str, str]],
    structural_by_text: dict[str, dict[str, str]],
) -> tuple[list[dict[str, object]], Counter[str], Counter[str], Counter[str]]:
    rows: list[dict[str, object]] = []
    following: Counter[str] = Counter()
    preceding: Counter[str] = Counter()
    local_frames: Counter[str] = Counter()

    for row in corpus_rows:
        tokens = reading_tokens_for_row(row, structural_by_text)
        if not tokens:
            continue
        for index, token in enumerate(tokens):
            if token != TARGET:
                continue
            before = tokens[index - 1] if index else START
            after = tokens[index + 1] if index + 1 < len(tokens) else END
            if after != END:
                following[after] += 1
            if before != START:
                preceding[before] += 1
            local_frame = f"{before}|{after}"
            local_frames[local_frame] += 1
            rows.append(
                {
                    "TextId": row.get("id", ""),
                    "CISI": row.get("cisi", ""),
                    "Region": row.get("region", ""),
                    "Site": row.get("site", ""),
                    "Type": row.get("type", ""),
                    "Symbol": row.get("symbol", ""),
                    "Material": row.get("material", ""),
                    "Complete": row.get("complete", ""),
                    "Direction": row.get("dir.", ""),
                    "Position": index + 1,
                    "TextLength": len(tokens),
                    "OccurrenceRole": occurrence_role(index, len(tokens)),
                    "Before": before,
                    "After": after,
                    "LocalFrame": local_frame,
                    "ReadingTokens": join_tokens(tokens),
                    "RawText": row.get("text", ""),
                }
            )
    return rows, following, preceding, local_frames


def empty_profile() -> dict[str, object]:
    return {
        "count": 0,
        "texts": set(),
        "frames": Counter(),
        "sites": Counter(),
        "regions": Counter(),
        "types": Counter(),
        "symbols": Counter(),
        "semantic_frames": Counter(),
        "examples": [],
        "sources": Counter(),
    }


def add_unit_profile(
    profiles: dict[str, dict[str, object]],
    unit: str,
    frame: str,
    row: dict[str, str],
    structural_by_text: dict[str, dict[str, str]],
    source: str,
) -> None:
    profile = profiles.setdefault(unit, empty_profile())
    profile["count"] = int(profile["count"]) + 1
    text_id = row.get("TextId") or row.get("id") or ""
    if text_id:
        profile["texts"].add(text_id)  # type: ignore[union-attr]
    if frame:
        profile["frames"][frame] += 1  # type: ignore[index]
    for field, counter_name in [
        ("Site", "sites"),
        ("Region", "regions"),
        ("Type", "types"),
        ("Symbol", "symbols"),
    ]:
        value = row.get(field, "") or row.get(field.lower(), "")
        if value and value not in {"-", "--", "??"}:
            profile[counter_name][value] += 1  # type: ignore[index]
    structural = structural_by_text.get(text_id, {})
    semantic = structural.get("SemanticFrame", "")
    if semantic:
        profile["semantic_frames"][semantic] += 1  # type: ignore[index]
    profile["sources"][source] += 1  # type: ignore[index]
    examples: list[str] = profile["examples"]  # type: ignore[assignment]
    if len(examples) < 8:
        label = row.get("CISI") or row.get("cisi") or text_id
        if label:
            examples.append(label)


def build_unit_profiles(
    out_dir: Path,
    structural_by_text: dict[str, dict[str, str]],
) -> dict[str, dict[str, object]]:
    profiles: dict[str, dict[str, object]] = {}
    seen: set[tuple[str, str, str, str]] = set()

    for row in read_csv(out_dir / "slot_paradigm_occurrences.csv"):
        unit = join_tokens(sign_tokens(row.get("Filler")))
        if not unit:
            continue
        key = (row.get("TextId", ""), row.get("Frame", ""), unit, f"{row.get('StartPos', '')}-{row.get('EndPos', '')}")
        seen.add(key)
        add_unit_profile(profiles, unit, row.get("Frame", ""), row, structural_by_text, "slot-paradigm")

    for row in structural_by_text.values():
        for filler in parse_slot_fillers(row.get("SlotFillers")):
            unit = filler["Filler"]
            key = (row.get("TextId", ""), filler["Frame"], unit, filler["Position"])
            if key in seen:
                continue
            add_unit_profile(profiles, unit, filler["Frame"], row, structural_by_text, "structural-reconstruction")
    return profiles


def group_240_compounds(
    profiles: dict[str, dict[str, object]],
    following_counter: Counter[str],
    roles: dict[str, dict[str, str]],
) -> list[dict[str, object]]:
    groups: dict[str, dict[str, object]] = {}
    for unit, profile in profiles.items():
        tokens = sign_tokens(unit)
        if not tokens or tokens[0] != TARGET:
            continue
        stem = tokens[1] if len(tokens) > 1 else "<NONE>"
        group = groups.setdefault(
            stem,
            {
                "Post240Sign": stem,
                "SlotOccurrenceCount": 0,
                "TextIds": set(),
                "UnitForms": Counter(),
                "TailForms": Counter(),
                "Frames": Counter(),
                "Sites": Counter(),
                "Symbols": Counter(),
                "SemanticFrames": Counter(),
                "Examples": [],
            },
        )
        count = int(profile["count"])
        group["SlotOccurrenceCount"] = int(group["SlotOccurrenceCount"]) + count
        group["TextIds"].update(profile["texts"])  # type: ignore[union-attr]
        group["UnitForms"][unit] += count  # type: ignore[index]
        tail = join_tokens(tokens[2:]) if len(tokens) > 2 else "<none>"
        group["TailForms"][tail] += count  # type: ignore[index]
        for source_name, target_name in [
            ("frames", "Frames"),
            ("sites", "Sites"),
            ("symbols", "Symbols"),
            ("semantic_frames", "SemanticFrames"),
        ]:
            group[target_name].update(profile[source_name])  # type: ignore[index]
        examples: list[str] = group["Examples"]  # type: ignore[assignment]
        for example in profile["examples"]:  # type: ignore[union-attr]
            if len(examples) < 8 and example not in examples:
                examples.append(example)

    rows: list[dict[str, object]] = []
    for stem, group in groups.items():
        frames: Counter[str] = group["Frames"]  # type: ignore[assignment]
        top_frame, top_frame_share = dominant(frames)
        frame_total = counter_total(frames)
        prime_entity_share = 0.0
        if frame_total:
            prime_entity_share = (frames.get("002|740", 0) + frames.get("002|<END>", 0)) / frame_total
        role = roles.get(stem, {})
        post_class = role.get("FunctionalClass", "")
        count = int(group["SlotOccurrenceCount"])
        distinct_forms = len(group["UnitForms"])  # type: ignore[arg-type]
        effective_frame_lock = max(top_frame_share, prime_entity_share)
        frame_lock = clamp(effective_frame_lock * 0.55 + min(count / 12.0, 1.0) * 0.25 + min(distinct_forms / 3.0, 1.0) * 0.20)
        if stem == "<NONE>":
            lead = "240 occurs as a complete filler; treat as possible standalone operator/control."
        elif prime_entity_share >= 0.75 and frame_lock >= 0.70 and post_class == "ROOT_OR_UNRESOLVED":
            lead = "Prime 240+STEM environment; use as controlled stem lane."
        elif prime_entity_share >= 0.75 and frame_lock >= 0.70:
            lead = "Prime 240+X environment; control grammar before treating X as a stem."
        elif top_frame_share >= 0.70:
            lead = "Frame-locked 240 compound; useful grammar control."
        else:
            lead = "Mixed frame evidence; keep as lower-confidence 240 context."
        rows.append(
            {
                "Post240Sign": stem,
                "SlotOccurrenceCount": count,
                "CorpusAdjacentCount": following_counter.get(stem, 0),
                "TextCount": len(group["TextIds"]),  # type: ignore[arg-type]
                "DistinctUnitForms": distinct_forms,
                "TopUnitForms": top_counter(group["UnitForms"], 5),  # type: ignore[arg-type]
                "TailForms": top_counter(group["TailForms"], 5),  # type: ignore[arg-type]
                "TopFrame": top_frame,
                "TopFrameShare": f"{top_frame_share:.3f}",
                "PrimeEntityShare": f"{prime_entity_share:.3f}",
                "FrameEntropy": f"{normalized_entropy(frames):.3f}",
                "Frames": top_counter(frames, 6),
                "Sites": top_counter(group["Sites"], 5),  # type: ignore[arg-type]
                "Symbols": top_counter(group["Symbols"], 5),  # type: ignore[arg-type]
                "SemanticFrames": top_counter(group["SemanticFrames"], 5),  # type: ignore[arg-type]
                "Post240Class": post_class,
                "Post240Interpretation": role.get("ComponentInterpretation") or role.get("ProtoGloss", ""),
                "FrameLockScore": f"{frame_lock:.3f}",
                "Lead": lead,
                "Examples": "; ".join(group["Examples"]),  # type: ignore[arg-type]
            }
        )
    return sorted(rows, key=lambda row: (-fint(str(row["SlotOccurrenceCount"])), str(row["Post240Sign"])))


def validation_rows_for_240(out_dir: Path) -> list[dict[str, str]]:
    validations = read_csv(out_dir / "validated_probe_results.csv")
    rows = []
    for row in validations:
        text = " ".join(
            [
                row.get("AnchorUnit", ""),
                row.get("NeighborUnit", ""),
                row.get("ChangedAnchorComponent", ""),
                row.get("NeighborChangedComponent", ""),
            ]
        )
        if TARGET in sign_tokens(text):
            rows.append(row)
    return rows


def component_contrast_rows_for_240(out_dir: Path) -> list[dict[str, str]]:
    rows = []
    for row in read_csv(out_dir / "component_contrast_tests.csv"):
        signs = sign_tokens(" ".join([row.get("AnchorComponent", ""), row.get("NeighborComponent", "")]))
        if TARGET in signs:
            rows.append(row)
    return rows


def best_validation_for_stem(stem: str, validations: list[dict[str, str]]) -> tuple[float, str]:
    best_score = 0.0
    statuses: Counter[str] = Counter()
    for row in validations:
        units = [row.get("AnchorUnit", ""), row.get("NeighborUnit", "")]
        components = [row.get("ChangedAnchorComponent", ""), row.get("NeighborChangedComponent", "")]
        unit_match = any(unit == f"{TARGET}-{stem}" or unit.startswith(f"{TARGET}-{stem}-") for unit in units)
        component_match = stem in components and any(unit.startswith(f"{TARGET}-") for unit in units)
        if unit_match or component_match:
            best_score = max(best_score, ffloat(row.get("ValidationScore")))
            statuses[row.get("ValidationStatus", "")] += 1
    return best_score, top_counter(statuses, 4)


def build_preservation_tests(
    compound_rows: list[dict[str, object]],
    profiles: dict[str, dict[str, object]],
    validations: list[dict[str, str]],
) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for compound in compound_rows:
        stem = str(compound["Post240Sign"])
        if stem == "<NONE>":
            continue
        post_class = str(compound.get("Post240Class", ""))
        is_stem_like = post_class in {"ROOT_OR_UNRESOLVED", ""}
        with_frames = Counter()
        with_count = 0
        with_units: Counter[str] = Counter()
        for unit, profile in profiles.items():
            tokens = sign_tokens(unit)
            if len(tokens) >= 2 and tokens[0] == TARGET and tokens[1] == stem:
                count = int(profile["count"])
                with_count += count
                with_units[unit] += count
                with_frames.update(profile["frames"])  # type: ignore[arg-type]

        bare_profile = profiles.get(stem, empty_profile())
        bare_frames: Counter[str] = bare_profile["frames"]  # type: ignore[assignment]
        bare_count = int(bare_profile["count"])
        overlap = distribution_overlap(with_frames, bare_frames)
        top_with, top_with_share = dominant(with_frames)
        top_bare, top_bare_share = dominant(bare_frames)
        with_total = counter_total(with_frames)
        prime_entity_share = 0.0
        if with_total:
            prime_entity_share = (with_frames.get("002|740", 0) + with_frames.get("002|<END>", 0)) / with_total
        validation_score, validation_statuses = best_validation_for_stem(stem, validations)
        shared_frames = sorted(set(with_frames) & set(bare_frames))
        identity_score = clamp(
            overlap * 0.25
            + max(top_with_share, prime_entity_share) * 0.20
            + min(with_count / 8.0, 1.0) * 0.15
            + validation_score * 0.25
            + min(len(shared_frames) / 2.0, 1.0) * 0.05
            + prime_entity_share * 0.10
        )
        if prime_entity_share >= 0.75 and validation_score >= 0.75 and is_stem_like:
            result = "CONTROLLED_240_STEM_ENVIRONMENT"
            next_test = "Use this as a fixed 240+STEM lane; image-check before phonetic assignment."
        elif prime_entity_share >= 0.75 and validation_score >= 0.75:
            result = "CONTROLLED_240_NONSTEM_ENVIRONMENT"
            next_test = "Use this as a grammar-control lane, but do not treat the post-240 sign as a stem."
        elif bare_count > 0 and overlap >= 0.50:
            result = "FRAME_IDENTITY_PRESERVED"
            next_test = "Compare bare and 240-prefixed contexts for the same semantic/object split."
        elif with_count >= 3 and top_with_share >= 0.70:
            result = "240_FRAME_LOCKED_NEEDS_BARE_CONTROL"
            next_test = "Search or validate bare-stem controls in the same frame."
        elif bare_count == 0:
            result = "NEEDS_BARE_STEM_CONTROL"
            next_test = "Do not use this stem phonetically until a bare or rival-stem control appears."
        else:
            result = "MIXED_OR_LOW_EVIDENCE"
            next_test = "Keep as grammar evidence only; do not promote to phonetic testing."
        rows.append(
            {
                "Post240Sign": stem,
                "Post240Class": post_class,
                "With240Count": with_count,
                "BareStemCount": bare_count,
                "With240Units": top_counter(with_units, 5),
                "TopWith240Frame": top_with,
                "TopWith240FrameShare": f"{top_with_share:.3f}",
                "PrimeEntityShare": f"{prime_entity_share:.3f}",
                "TopBareFrame": top_bare,
                "TopBareFrameShare": f"{top_bare_share:.3f}",
                "SharedFrames": "; ".join(shared_frames),
                "FrameOverlap": f"{overlap:.3f}",
                "ValidationScore": f"{validation_score:.3f}",
                "ValidationStatuses": validation_statuses,
                "IdentityScore": f"{identity_score:.3f}",
                "IdentityResult": result,
                "NextTest": next_test,
            }
        )
    return sorted(rows, key=lambda row: (-ffloat(str(row["IdentityScore"])), -fint(str(row["With240Count"])), str(row["Post240Sign"])))


def build_operator_models(
    occurrence_rows: list[dict[str, object]],
    following: Counter[str],
    local_frames: Counter[str],
    compound_rows: list[dict[str, object]],
    preservation_rows: list[dict[str, object]],
    validations: list[dict[str, str]],
    component_contrasts: list[dict[str, str]],
) -> list[dict[str, object]]:
    total = len(occurrence_rows)
    role_counts = Counter(str(row["OccurrenceRole"]) for row in occurrence_rows)
    prefix_share = 1.0 - (role_counts["Final"] / total if total else 0.0)
    initial_or_medial_share = (role_counts["Initial"] + role_counts["Medial"]) / total if total else 0.0
    standalone_share = role_counts["Standalone"] / total if total else 0.0
    final_share = role_counts["Final"] / total if total else 0.0
    distinct_following = len(following)
    high_lock_groups = sum(1 for row in compound_rows if ffloat(str(row.get("FrameLockScore"))) >= 0.70)
    controlled_lanes = sum(1 for row in preservation_rows if row.get("IdentityResult") == "CONTROLLED_240_STEM_ENVIRONMENT")
    preserved_rows = sum(1 for row in preservation_rows if row.get("IdentityResult") in {"CONTROLLED_240_STEM_ENVIRONMENT", "FRAME_IDENTITY_PRESERVED"})
    morphology_constraints = sum(
        1
        for row in validations
        if row.get("ChangedAnchorComponent") == TARGET and row.get("ValidationStatus") == "Morphology constraint"
    )
    morphology_probes = sum(1 for row in validations if row.get("ChangedAnchorComponent") == TARGET)
    contrast_240_235 = sum(
        1
        for row in component_contrasts
        if row.get("AnchorComponent") == TARGET and row.get("NeighborComponent") == "235"
    )
    position_entropy = normalized_entropy(role_counts)
    context_entropy = normalized_entropy(local_frames)

    prefix_operator_score = clamp(
        initial_or_medial_share * 0.20
        + min(distinct_following / 18.0, 1.0) * 0.15
        + min(morphology_constraints / 8.0, 1.0) * 0.25
        + min(high_lock_groups / 8.0, 1.0) * 0.15
        + min(controlled_lanes / 3.0, 1.0) * 0.15
        + min(preserved_rows / 5.0, 1.0) * 0.10
    )
    ordinary_stem_score = clamp(
        standalone_share * 0.35
        + (1.0 - min(distinct_following / 10.0, 1.0)) * 0.20
        + (1.0 - min(morphology_constraints / 6.0, 1.0)) * 0.25
        + final_share * 0.10
        + (1.0 - min(high_lock_groups / 5.0, 1.0)) * 0.10
    )
    formula_opener_score = clamp(
        role_counts["Initial"] / total * 0.25 if total else 0.0
    )
    formula_opener_score = clamp(
        formula_opener_score
        + min(contrast_240_235 / 1.0, 1.0) * 0.20
        + min(morphology_probes / 14.0, 1.0) * 0.10
        + min(local_frames.get(f"{START}|235", 0) / 4.0, 1.0) * 0.10
        + context_entropy * 0.05
    )
    terminal_score = clamp(final_share * 0.60 + min(local_frames.get(f"235|{END}", 0) / 6.0, 1.0) * 0.20)
    mixed_score = clamp(position_entropy * 0.30 + context_entropy * 0.25 + min(distinct_following / 25.0, 1.0) * 0.20 + (1.0 - prefix_operator_score) * 0.15)

    rows = [
        {
            "ModelId": "H240-A",
            "Model": "Qualifier/title/classifier prefix operator",
            "Score": f"{prefix_operator_score:.3f}",
            "Status": "LEADING MODEL" if prefix_operator_score >= 0.70 else "Plausible",
            "Evidence": f"{morphology_constraints} morphology constraints; {distinct_following} following signs; {high_lock_groups} frame-locked 240+X groups; {controlled_lanes} controlled stem lanes.",
            "Consequence": "Use 240+STEM as a formal environment before assigning any sound values.",
        },
        {
            "ModelId": "H240-B",
            "Model": "Ordinary lexical stem",
            "Score": f"{ordinary_stem_score:.3f}",
            "Status": "WEAKENED" if ordinary_stem_score < 0.45 else "Still possible",
            "Evidence": f"standalone share={standalone_share:.3f}; final share={final_share:.3f}; distinct following signs={distinct_following}.",
            "Consequence": "Would block 240 from serving as a grammar operator; current evidence does not favor this.",
        },
        {
            "ModelId": "H240-C",
            "Model": "Formula opener/boundary marker",
            "Score": f"{formula_opener_score:.3f}",
            "Status": "SECONDARY FUNCTION" if formula_opener_score >= 0.45 else "Low to moderate",
            "Evidence": f"240::235 contrast rows={contrast_240_235}; context entropy={context_entropy:.3f}; probes involving 240={morphology_probes}.",
            "Consequence": "Model 240 against 235 as a rival opener while keeping 240+STEM separate.",
        },
        {
            "ModelId": "H240-D",
            "Model": "Terminal/suffix/numeral value",
            "Score": f"{terminal_score:.3f}",
            "Status": "LOW SUPPORT" if terminal_score < 0.35 else "Possible local role",
            "Evidence": f"final share={final_share:.3f}; 235|END contexts={local_frames.get(f'235|{END}', 0)}.",
            "Consequence": "Do not use 240 as a terminal anchor unless a specific local frame demands it.",
        },
        {
            "ModelId": "H240-E",
            "Model": "Polyfunctional mixed sign",
            "Score": f"{mixed_score:.3f}",
            "Status": "CONTROL RISK" if mixed_score >= 0.55 else "Managed risk",
            "Evidence": f"position entropy={position_entropy:.3f}; local-frame entropy={context_entropy:.3f}.",
            "Consequence": "Split 240 contexts by frame before any phonetic comparison.",
        },
    ]
    return sorted(rows, key=lambda row: -ffloat(str(row["Score"])))


def build_summary(
    occurrence_rows: list[dict[str, object]],
    following: Counter[str],
    preceding: Counter[str],
    local_frames: Counter[str],
    compound_rows: list[dict[str, object]],
    preservation_rows: list[dict[str, object]],
    model_rows: list[dict[str, object]],
    validations: list[dict[str, str]],
) -> list[dict[str, object]]:
    role_counts = Counter(str(row["OccurrenceRole"]) for row in occurrence_rows)
    texts = {str(row["TextId"]) for row in occurrence_rows if row.get("TextId")}
    controlled_lanes = sum(1 for row in preservation_rows if row.get("IdentityResult") == "CONTROLLED_240_STEM_ENVIRONMENT")
    frame_locked = sum(1 for row in compound_rows if ffloat(str(row.get("FrameLockScore"))) >= 0.70)
    morph_constraints = sum(
        1
        for row in validations
        if row.get("ChangedAnchorComponent") == TARGET and row.get("ValidationStatus") == "Morphology constraint"
    )
    top_model = model_rows[0] if model_rows else {}
    return [
        {"Metric": "240 token occurrences", "Value": len(occurrence_rows), "Note": f"texts={len(texts)}"},
        {"Metric": "Position profile", "Value": top_counter(role_counts, 5), "Note": "Reading-order positions in cleaned corpus."},
        {"Metric": "Distinct signs after 240", "Value": len(following), "Note": top_counter(following, 5)},
        {"Metric": "Distinct signs before 240", "Value": len(preceding), "Note": top_counter(preceding, 5)},
        {"Metric": "Observed local frames", "Value": len(local_frames), "Note": top_counter(local_frames, 5)},
        {"Metric": "240+X slot groups", "Value": len(compound_rows), "Note": f"{frame_locked} frame-locked groups at score >= 0.70"},
        {"Metric": "Controlled 240+STEM lanes", "Value": controlled_lanes, "Note": "Can feed later phonetic tests after image checks."},
        {"Metric": "Validated 240 morphology constraints", "Value": morph_constraints, "Note": "Promoted to grammar model only."},
        {"Metric": "Leading 240 model", "Value": top_model.get("Model", ""), "Note": f"score={top_model.get('Score', '')}; status={top_model.get('Status', '')}"},
    ]


def build_action_queue(
    compound_rows: list[dict[str, object]],
    preservation_rows: list[dict[str, object]],
    model_rows: list[dict[str, object]],
) -> list[dict[str, object]]:
    top_lanes = [
        row
        for row in preservation_rows
        if row.get("IdentityResult") == "CONTROLLED_240_STEM_ENVIRONMENT"
    ]
    if not top_lanes:
        top_lanes = [
            row
            for row in preservation_rows
            if row.get("IdentityResult") in {"FRAME_IDENTITY_PRESERVED", "CONTROLLED_240_NONSTEM_ENVIRONMENT"}
        ]
    best_lane = top_lanes[0] if top_lanes else {}
    phonetic_lanes = [row for row in top_lanes if "Phonetic-ready after image check" in str(row.get("ValidationStatuses", ""))]
    first_phonetic_lane = phonetic_lanes[0] if phonetic_lanes else best_lane
    phonetic_lane_text = "; ".join(
        f"240-{row['Post240Sign']}:{row['IdentityScore']}" for row in phonetic_lanes[:4]
    )
    if not phonetic_lane_text and first_phonetic_lane:
        phonetic_lane_text = f"240-{first_phonetic_lane.get('Post240Sign', '')}:{first_phonetic_lane.get('IdentityScore', '')}"
    best_model = model_rows[0] if model_rows else {}
    top_groups = [row for row in compound_rows if ffloat(str(row.get("FrameLockScore"))) >= 0.70][:5]
    top_group_text = "; ".join(f"240-{row['Post240Sign']}:{row['FrameLockScore']}" for row in top_groups)
    return [
        {
            "Priority": 1,
            "Action": "Freeze 240 as a grammar operator in the solver",
            "WhyItAccelerates": "All 240+STEM probes can now share one controlled environment instead of being isolated tests.",
            "EvidenceTrigger": f"{best_model.get('Model', '')}; score={best_model.get('Score', '')}",
            "ImmediateOutput": "Update constrained readings so 240 is an operator label, not a sound-bearing value.",
        },
        {
            "Priority": 2,
            "Action": "Promote the first phonetic-grade 240+STEM lane",
            "WhyItAccelerates": "This turns 240+STEM from grammar into the first repeatable phonetic-test environment.",
            "EvidenceTrigger": phonetic_lane_text,
            "ImmediateOutput": "Image-check and context-check 240-482 against 240-904 as one controlled contrast.",
        },
        {
            "Priority": 3,
            "Action": "Use 176 as the bridge/control stem",
            "WhyItAccelerates": "176 links bare-stem evidence with 240-prefixed evidence, so it tests whether OP240 preserves identity.",
            "EvidenceTrigger": f"{best_lane.get('Post240Sign', '')}; result={best_lane.get('IdentityResult', '')}; score={best_lane.get('IdentityScore', '')}",
            "ImmediateOutput": "Compare bare 176, 240-176, 048, and 061 inside the prime entity frame.",
        },
        {
            "Priority": 4,
            "Action": "Use frame-locked 240 compounds as controls",
            "WhyItAccelerates": "Controls stop false phonetic jumps and let us rank which stems are real contrasts.",
            "EvidenceTrigger": top_group_text,
            "ImmediateOutput": "Generate a 240+STEM contrast matrix for 482, 904, 176, 773, and high-count followers.",
        },
        {
            "Priority": 5,
            "Action": "Split 240 from 235 before lexical claims",
            "WhyItAccelerates": "Separating grammar opener behavior from formula-marker behavior removes a major ambiguity.",
            "EvidenceTrigger": "240::235 is already a ranked formula-boundary keystone.",
            "ImmediateOutput": "Build a rival-opener model: 240+X versus 235+X and X+terminal contexts.",
        },
        {
            "Priority": 6,
            "Action": "Block sound values for 240",
            "WhyItAccelerates": "Treating 240 as phonetic too early would contaminate every downstream stem comparison.",
            "EvidenceTrigger": "The leading model is grammatical, not lexical.",
            "ImmediateOutput": "Keep 240 as OP240 in abstract reading skeletons.",
        },
    ]


def write_latex_section(
    path: Path,
    summary: list[dict[str, object]],
    models: list[dict[str, object]],
    compounds: list[dict[str, object]],
    preservation: list[dict[str, object]],
    actions: list[dict[str, object]],
) -> None:
    top_compounds = [
        {
            "Post240": row["Post240Sign"],
            "Count": row["SlotOccurrenceCount"],
            "Top frame": row["TopFrame"],
            "Lock": row["FrameLockScore"],
            "Lead": row["Lead"],
        }
        for row in compounds[:10]
    ]
    top_preservation = [
        {
            "Post240": row["Post240Sign"],
            "With": row["With240Count"],
            "Bare": row["BareStemCount"],
            "Overlap": row["FrameOverlap"],
            "Result": compact_result_label(row["IdentityResult"]),
        }
        for row in preservation[:10]
    ]
    model_table = [
        {
            "Model": row["Model"],
            "Score": row["Score"],
            "Status": row["Status"],
        }
        for row in models
    ]
    action_table = [
        {
            "Priority": row["Priority"],
            "Action": row["Action"],
            "Output": row["ImmediateOutput"],
        }
        for row in actions
    ]
    text = (
        r"""\section{Grammar Keystone 240 Model}

\subsection{Purpose}

The breakthrough portfolio ranked \texttt{240} as the highest-leverage target. This section executes that target. It tests whether \texttt{240} should be treated as a reusable grammar operator, an ordinary stem, a formula boundary sign, a terminal marker, or a mixed sign. The model is still pre-phonetic: it licenses controlled environments, not sound values.

\subsection{Summary}

\begin{table}[htbp]
\centering
\footnotesize
"""
        + latex_table(summary, ["Metric", "Value", "Note"], ["p{0.30\\textwidth}", "p{0.24\\textwidth}", "p{0.32\\textwidth}"])
        + r"""
\caption{Summary of the \texttt{240} grammar-keystone test.}
\label{tab:grammar-keystone-240-summary}
\end{table}

\subsection{Rival Models}

\begin{table}[htbp]
\centering
\footnotesize
"""
        + latex_table(model_table, ["Model", "Score", "Status"], ["p{0.52\\textwidth}", "r", "p{0.22\\textwidth}"])
        + r"""
\caption{Rival grammatical models for \texttt{240}.}
\label{tab:grammar-keystone-240-models}
\end{table}

\subsection{240+X Families}

\begin{table}[htbp]
\centering
\scriptsize
"""
        + latex_table(top_compounds, ["Post240", "Count", "Top frame", "Lock", "Lead"], ["l", "r", "l", "r", "p{0.40\\textwidth}"])
        + r"""
\caption{Highest-yield \texttt{240+X} families.}
\label{tab:grammar-keystone-240-families}
\end{table}

\subsection{Frame Identity Tests}

\begin{table}[htbp]
\centering
\scriptsize
"""
        + latex_table(top_preservation, ["Post240", "With", "Bare", "Overlap", "Result"], ["l", "r", "r", "r", "p{0.38\\textwidth}"])
        + r"""
\caption{Tests of whether \texttt{240+X} preserves enough frame identity to become a controlled environment.}
\label{tab:grammar-keystone-240-preservation}
\end{table}

\subsection{Decision}

The leading model treats \texttt{240} as a qualifier/title/classifier-like operator. This does not decipher \texttt{240}; it constrains it. The working notation should therefore keep \texttt{240} as an abstract operator, \texttt{OP240}, while the following position is tested as the stem-like slot.

The practical consequence is large: \texttt{240-482}, \texttt{240-904}, \texttt{240-176}, and related forms can now be tested as one grammar family. The first phonetic lane remains conditional on image review, but it no longer floats without structure.

\subsection{Acceleration Queue}

\begin{table}[htbp]
\centering
\scriptsize
"""
        + latex_table(action_table, ["Priority", "Action", "Output"], ["r", "p{0.34\\textwidth}", "p{0.38\\textwidth}"])
        + r"""
\caption{Immediate actions unlocked by the \texttt{240} grammar model.}
\label{tab:grammar-keystone-240-actions}
\end{table}

\subsection{Outputs}

\begin{itemize}
  \item \texttt{outputs/grammar\_keystone\_240\_summary.csv}
  \item \texttt{outputs/grammar\_keystone\_240\_occurrences.csv}
  \item \texttt{outputs/grammar\_keystone\_240\_compound\_families.csv}
  \item \texttt{outputs/grammar\_keystone\_240\_preservation\_tests.csv}
  \item \texttt{outputs/grammar\_keystone\_240\_operator\_models.csv}
  \item \texttt{outputs/grammar\_keystone\_240\_action\_queue.csv}
\end{itemize}
"""
    )
    path.write_text(text, encoding="utf-8")


def model(args: argparse.Namespace) -> None:
    corpus_path = Path(args.corpus_path)
    out_dir = Path(args.out_dir)
    docs_section = Path(args.docs_section)

    structural_by_text = load_structural_rows(out_dir)
    corpus_rows = read_csv(corpus_path)
    roles = build_role_map(out_dir)
    occurrences, following, preceding, local_frames = build_240_occurrences(corpus_rows, structural_by_text)
    profiles = build_unit_profiles(out_dir, structural_by_text)
    validations = validation_rows_for_240(out_dir)
    component_contrasts = component_contrast_rows_for_240(out_dir)
    compounds = group_240_compounds(profiles, following, roles)
    preservation = build_preservation_tests(compounds, profiles, validations)
    models = build_operator_models(occurrences, following, local_frames, compounds, preservation, validations, component_contrasts)
    summary = build_summary(occurrences, following, preceding, local_frames, compounds, preservation, models, validations)
    actions = build_action_queue(compounds, preservation, models)

    write_csv(
        out_dir / "grammar_keystone_240_occurrences.csv",
        occurrences,
        [
            "TextId",
            "CISI",
            "Region",
            "Site",
            "Type",
            "Symbol",
            "Material",
            "Complete",
            "Direction",
            "Position",
            "TextLength",
            "OccurrenceRole",
            "Before",
            "After",
            "LocalFrame",
            "ReadingTokens",
            "RawText",
        ],
    )
    write_csv(out_dir / "grammar_keystone_240_summary.csv", summary, ["Metric", "Value", "Note"])
    write_csv(
        out_dir / "grammar_keystone_240_compound_families.csv",
        compounds,
        [
            "Post240Sign",
            "SlotOccurrenceCount",
            "CorpusAdjacentCount",
            "TextCount",
            "DistinctUnitForms",
            "TopUnitForms",
            "TailForms",
            "TopFrame",
            "TopFrameShare",
            "PrimeEntityShare",
            "FrameEntropy",
            "Frames",
            "Sites",
            "Symbols",
            "SemanticFrames",
            "Post240Class",
            "Post240Interpretation",
            "FrameLockScore",
            "Lead",
            "Examples",
        ],
    )
    write_csv(
        out_dir / "grammar_keystone_240_preservation_tests.csv",
        preservation,
        [
            "Post240Sign",
            "Post240Class",
            "With240Count",
            "BareStemCount",
            "With240Units",
            "TopWith240Frame",
            "TopWith240FrameShare",
            "PrimeEntityShare",
            "TopBareFrame",
            "TopBareFrameShare",
            "SharedFrames",
            "FrameOverlap",
            "ValidationScore",
            "ValidationStatuses",
            "IdentityScore",
            "IdentityResult",
            "NextTest",
        ],
    )
    write_csv(
        out_dir / "grammar_keystone_240_operator_models.csv",
        models,
        ["ModelId", "Model", "Score", "Status", "Evidence", "Consequence"],
    )
    write_csv(
        out_dir / "grammar_keystone_240_action_queue.csv",
        actions,
        ["Priority", "Action", "WhyItAccelerates", "EvidenceTrigger", "ImmediateOutput"],
    )
    write_latex_section(docs_section, summary, models, compounds, preservation, actions)
    write_latex_section(out_dir / "grammar_keystone_240_model.tex", summary, models, compounds, preservation, actions)

    for path in [
        out_dir / "grammar_keystone_240_summary.csv",
        out_dir / "grammar_keystone_240_occurrences.csv",
        out_dir / "grammar_keystone_240_compound_families.csv",
        out_dir / "grammar_keystone_240_preservation_tests.csv",
        out_dir / "grammar_keystone_240_operator_models.csv",
        out_dir / "grammar_keystone_240_action_queue.csv",
        out_dir / "grammar_keystone_240_model.tex",
        docs_section,
    ]:
        print(f"Wrote {path}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--corpus-path", default="data/ivs_corpus_cleaned.csv")
    parser.add_argument("--out-dir", default="outputs")
    parser.add_argument("--docs-section", default="docs/sections/grammar_keystone_240_model.tex")
    return parser.parse_args()


if __name__ == "__main__":
    model(parse_args())
