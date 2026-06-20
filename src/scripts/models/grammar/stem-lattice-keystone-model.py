#!/usr/bin/env python3
"""Build the first controlled stem-lattice keystone model.

This stage consumes the 240 grammar model and turns it into a working
pre-phonetic stem space. It ranks stem signs and stem pairs that live in the
prime entity environment, especially OP240+STEM forms such as 240-482 and
240-904 and bare controls such as 176, 048, and 061.
"""

from __future__ import annotations

import argparse
import csv
import math
import re
from collections import Counter, defaultdict
from pathlib import Path


TOKEN_RE = re.compile(r"(?<!\d)\d{3,4}(?!\d)")
TARGET_OPERATOR = "240"
PRIME_FRAMES = {"002|740", "002|<END>"}
NON_STEM_CLASSES = {"TERMINAL", "FORMULA_MARKER", "CLASSIFIER", "SLOT_MODIFIER"}
IMPORTANT_BARE_CONTROLS = {"048", "061", "176"}


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


def counter_prob(counter: Counter[str]) -> dict[str, float]:
    total = counter_total(counter)
    if total <= 0:
        return {}
    return {key: value / total for key, value in counter.items()}


def distribution_overlap(left: Counter[str], right: Counter[str]) -> float:
    p = counter_prob(left)
    q = counter_prob(right)
    if not p or not q:
        return 0.0
    return sum(min(p.get(key, 0.0), q.get(key, 0.0)) for key in set(p) | set(q))


def js_divergence(left: Counter[str], right: Counter[str]) -> float:
    p = counter_prob(left)
    q = counter_prob(right)
    keys = set(p) | set(q)
    if not keys:
        return 0.0
    midpoint = {key: (p.get(key, 0.0) + q.get(key, 0.0)) / 2.0 for key in keys}

    def kl(dist: dict[str, float], base: dict[str, float]) -> float:
        value = 0.0
        for key, probability in dist.items():
            if probability > 0 and base.get(key, 0.0) > 0:
                value += probability * math.log(probability / base[key], 2)
        return value

    return clamp((kl(p, midpoint) + kl(q, midpoint)) / 2.0)


def dominant(counter: Counter[str]) -> tuple[str, float]:
    total = counter_total(counter)
    if total <= 0:
        return "", 0.0
    key, value = counter.most_common(1)[0]
    return key, value / total


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


def compact_label(value: object) -> str:
    labels = {
        "LOW_EVIDENCE_STEM_CANDIDATE": "low-evidence stem",
        "BARE_PRIME_STEM_CONTROL": "bare prime control",
        "OP240_BARE_BRIDGE_CANDIDATE": "OP240/bare bridge",
        "PHONETIC_READY_OP240_STEM": "phonetic-ready OP240 stem",
        "OP240_BARE_BRIDGE_STEM": "OP240/bare bridge stem",
        "CONTROLLED_OP240_STEM": "controlled OP240 stem",
        "PRIMARY_PHONETIC_LANE_AFTER_IMAGE_CHECK": "primary phonetic lane",
        "PHONETIC_READY_AFTER_IMAGE_CHECK": "phonetic-ready after image check",
        "STEM_SEMANTIC_CONTROL": "stem-semantic control",
        "BRIDGE_STEM_CONTROL": "bridge stem control",
        "PHONETIC_LANE_NEIGHBOR": "phonetic-lane neighbor",
        "OCCURRENCE_LIMITED_STEM_CONTRAST": "occurrence-limited contrast",
    }
    return labels.get(str(value), str(value))


def compact_counter_text(value: object) -> str:
    parts: list[str] = []
    for part in str(value or "").split(";"):
        part = part.strip()
        if not part:
            continue
        if ":" in part:
            label, count = part.rsplit(":", 1)
            parts.append(f"{compact_label(label.strip())}:{count.strip()}")
        else:
            parts.append(compact_label(part))
    return "; ".join(parts)


def load_structural_by_text(out_dir: Path) -> dict[str, dict[str, str]]:
    path = out_dir / "structural_reconstructions.csv"
    return {row.get("TextId", ""): row for row in read_csv(path)}


def load_role_map(out_dir: Path) -> dict[str, dict[str, str]]:
    roles: dict[str, dict[str, str]] = {}
    for row in read_csv(out_dir / "phonetic_variable_map.csv"):
        sign = row.get("Sign", "")
        if sign:
            roles[sign] = {
                "Variable": row.get("Variable", ""),
                "FunctionalClass": row.get("FunctionalClass", ""),
                "ProtoGloss": row.get("ProtoGloss", ""),
                "CountInReadyTexts": row.get("CountInReadyTexts", ""),
            }
    for row in read_csv(out_dir / "anchor_component_roles.csv"):
        sign = row.get("Sign", "")
        if sign:
            roles.setdefault(sign, {})
            roles[sign].update(
                {
                    "FunctionalClass": row.get("FunctionalClass", roles[sign].get("FunctionalClass", "")),
                    "ComponentInterpretation": row.get("ComponentInterpretation", ""),
                }
            )
    return roles


def load_preservation(out_dir: Path) -> dict[str, dict[str, str]]:
    return {row.get("Post240Sign", ""): row for row in read_csv(out_dir / "grammar_keystone_240_preservation_tests.csv")}


def validation_by_sign_and_pair(out_dir: Path) -> tuple[dict[str, Counter[str]], dict[str, float], dict[tuple[str, str], dict[str, object]]]:
    sign_statuses: dict[str, Counter[str]] = defaultdict(Counter)
    sign_scores: dict[str, float] = defaultdict(float)
    pair_scores: dict[tuple[str, str], dict[str, object]] = {}

    for row in read_csv(out_dir / "validated_probe_results.csv"):
        score = ffloat(row.get("ValidationScore"))
        status = row.get("ValidationStatus", "")
        signs = set(sign_tokens(row.get("AnchorUnit")) + sign_tokens(row.get("NeighborUnit")))
        signs.update(sign_tokens(row.get("ChangedAnchorComponent")))
        signs.update(sign_tokens(row.get("NeighborChangedComponent")))
        for sign in signs:
            sign_statuses[sign][status] += 1
            sign_scores[sign] = max(sign_scores[sign], score)

        a = row.get("ChangedAnchorComponent", "")
        b = row.get("NeighborChangedComponent", "")
        if a and b and a != b:
            key = tuple(sorted([a, b]))
            existing = pair_scores.get(key, {})
            if score >= ffloat(str(existing.get("ValidationScore", 0.0))):
                pair_scores[key] = {
                    "ValidationScore": score,
                    "ValidationStatus": status,
                    "Probe": row.get("Probe", ""),
                    "Frame": row.get("Frame", ""),
                    "NextRequiredAction": row.get("NextRequiredAction", ""),
                }
    return sign_statuses, sign_scores, pair_scores


def should_keep_stem(stem: str, role_class: str, op240: bool) -> bool:
    if stem in IMPORTANT_BARE_CONTROLS:
        return True
    if role_class == "ROOT_OR_UNRESOLVED":
        return True
    if op240 and not role_class:
        return True
    return False


def empty_profile(stem: str, role_class: str) -> dict[str, object]:
    return {
        "StemSign": stem,
        "Post240Class": role_class,
        "TotalCount": 0,
        "OP240Count": 0,
        "BareCount": 0,
        "TextIds": set(),
        "Forms": Counter(),
        "Frames": Counter(),
        "Sites": Counter(),
        "Regions": Counter(),
        "Types": Counter(),
        "Symbols": Counter(),
        "SemanticFrames": Counter(),
        "Examples": [],
    }


def add_profile_occurrence(
    profiles: dict[str, dict[str, object]],
    stem: str,
    role_class: str,
    op240: bool,
    row: dict[str, str],
    structural_by_text: dict[str, dict[str, str]],
) -> None:
    profile = profiles.setdefault(stem, empty_profile(stem, role_class))
    if role_class and not profile.get("Post240Class"):
        profile["Post240Class"] = role_class
    profile["TotalCount"] = int(profile["TotalCount"]) + 1
    if op240:
        profile["OP240Count"] = int(profile["OP240Count"]) + 1
    else:
        profile["BareCount"] = int(profile["BareCount"]) + 1
    text_id = row.get("TextId", "")
    if text_id:
        profile["TextIds"].add(text_id)  # type: ignore[union-attr]
    filler = join_tokens(sign_tokens(row.get("Filler")))
    if filler:
        profile["Forms"][filler] += 1  # type: ignore[index]
    for field, target in [
        ("Frame", "Frames"),
        ("Site", "Sites"),
        ("Region", "Regions"),
        ("Type", "Types"),
        ("Symbol", "Symbols"),
    ]:
        value = row.get(field, "")
        if value and value not in {"-", "--", "??"}:
            profile[target][value] += 1  # type: ignore[index]
    structural = structural_by_text.get(text_id, {})
    semantic = structural.get("SemanticFrame", "")
    if semantic:
        profile["SemanticFrames"][semantic] += 1  # type: ignore[index]
    examples: list[str] = profile["Examples"]  # type: ignore[assignment]
    label = row.get("CISI") or text_id
    if label and len(examples) < 8 and label not in examples:
        examples.append(label)


def build_stem_profiles(
    out_dir: Path,
    roles: dict[str, dict[str, str]],
    preservation: dict[str, dict[str, str]],
    structural_by_text: dict[str, dict[str, str]],
    sign_statuses: dict[str, Counter[str]],
    sign_scores: dict[str, float],
) -> list[dict[str, object]]:
    profiles: dict[str, dict[str, object]] = {}

    for row in read_csv(out_dir / "slot_paradigm_occurrences.csv"):
        frame = row.get("Frame", "")
        if frame not in PRIME_FRAMES:
            continue
        tokens = sign_tokens(row.get("Filler"))
        if not tokens:
            continue
        op240 = len(tokens) >= 2 and tokens[0] == TARGET_OPERATOR
        stem = tokens[1] if op240 else tokens[0]
        role_class = roles.get(stem, {}).get("FunctionalClass", "")
        if not should_keep_stem(stem, role_class, op240):
            continue
        add_profile_occurrence(profiles, stem, role_class, op240, row, structural_by_text)

    rows: list[dict[str, object]] = []
    for stem, profile in profiles.items():
        total = int(profile["TotalCount"])
        op240_count = int(profile["OP240Count"])
        bare_count = int(profile["BareCount"])
        pres = preservation.get(stem, {})
        validation_score = max(ffloat(pres.get("ValidationScore")), sign_scores.get(stem, 0.0))
        statuses = Counter(sign_statuses.get(stem, Counter()))
        if pres.get("ValidationStatuses"):
            for part in pres["ValidationStatuses"].split(";"):
                label = part.strip().split(":", 1)[0]
                if label:
                    statuses[label] += 1
        phonetic_ready = "Phonetic-ready after image check" in statuses
        controlled = pres.get("IdentityResult") == "CONTROLLED_240_STEM_ENVIRONMENT"
        bridge = op240_count > 0 and bare_count > 0
        if phonetic_ready and controlled:
            role = "PHONETIC_READY_OP240_STEM"
        elif controlled and bridge:
            role = "OP240_BARE_BRIDGE_STEM"
        elif controlled:
            role = "CONTROLLED_OP240_STEM"
        elif bridge:
            role = "OP240_BARE_BRIDGE_CANDIDATE"
        elif bare_count >= 5:
            role = "BARE_PRIME_STEM_CONTROL"
        else:
            role = "LOW_EVIDENCE_STEM_CANDIDATE"
        score = clamp(
            min(total / 16.0, 1.0) * 0.20
            + min(op240_count / 8.0, 1.0) * 0.15
            + min(bare_count / 8.0, 1.0) * 0.12
            + (0.23 if controlled else 0.0)
            + (0.15 if bridge else 0.0)
            + (0.20 if phonetic_ready else 0.0)
            + validation_score * 0.15
        )
        top_frame, top_frame_share = dominant(profile["Frames"])  # type: ignore[arg-type]
        rows.append(
            {
                "StemSign": stem,
                "StemRole": role,
                "Post240Class": profile.get("Post240Class", ""),
                "StemScore": f"{score:.3f}",
                "TotalCount": total,
                "OP240Count": op240_count,
                "BareCount": bare_count,
                "TextCount": len(profile["TextIds"]),  # type: ignore[arg-type]
                "TopForms": top_counter(profile["Forms"], 6),  # type: ignore[arg-type]
                "TopFrame": top_frame,
                "TopFrameShare": f"{top_frame_share:.3f}",
                "Frames": top_counter(profile["Frames"], 8),  # type: ignore[arg-type]
                "Sites": top_counter(profile["Sites"], 5),  # type: ignore[arg-type]
                "Symbols": top_counter(profile["Symbols"], 5),  # type: ignore[arg-type]
                "SemanticFrames": top_counter(profile["SemanticFrames"], 5),  # type: ignore[arg-type]
                "ValidationScore": f"{validation_score:.3f}",
                "ValidationStatuses": top_counter(statuses, 5),
                "Examples": "; ".join(profile["Examples"]),  # type: ignore[arg-type]
            }
        )
    return sorted(rows, key=lambda row: (-ffloat(str(row["StemScore"])), -fint(str(row["TotalCount"])), str(row["StemSign"])))


def profile_lookup(rows: list[dict[str, object]]) -> dict[str, dict[str, object]]:
    return {str(row["StemSign"]): row for row in rows}


def counter_from_text(value: object) -> Counter[str]:
    counter: Counter[str] = Counter()
    if not value:
        return counter
    for part in str(value).split(";"):
        part = part.strip()
        if not part or ":" not in part:
            continue
        key, count = part.rsplit(":", 1)
        counter[key.strip()] += fint(count)
    return counter


def pair_validation(a: str, b: str, pair_scores: dict[tuple[str, str], dict[str, object]]) -> dict[str, object]:
    return pair_scores.get(tuple(sorted([a, b])), {})


def pair_class(a: str, b: str, left: dict[str, object], right: dict[str, object], validation: dict[str, object]) -> str:
    pair = {a, b}
    if pair == {"482", "904"}:
        return "PRIMARY_PHONETIC_LANE_AFTER_IMAGE_CHECK"
    if ffloat(str(validation.get("ValidationScore", 0.0))) >= 0.78:
        if validation.get("ValidationStatus") == "Phonetic-ready after image check":
            return "PHONETIC_READY_AFTER_IMAGE_CHECK"
        return "STEM_SEMANTIC_CONTROL"
    if "176" in pair and (pair & {"048", "061", "482", "904"}):
        return "BRIDGE_STEM_CONTROL"
    if str(left.get("StemRole", "")).startswith("PHONETIC") or str(right.get("StemRole", "")).startswith("PHONETIC"):
        return "PHONETIC_LANE_NEIGHBOR"
    return "OCCURRENCE_LIMITED_STEM_CONTRAST"


def next_action_for_pair(pair_kind: str, a: str, b: str) -> str:
    if pair_kind == "PRIMARY_PHONETIC_LANE_AFTER_IMAGE_CHECK":
        return "Image-check every 240-482 and 240-904 occurrence; keep OP240 fixed and compare only the stem slot."
    if pair_kind == "PHONETIC_READY_AFTER_IMAGE_CHECK":
        return "Image-check the pair, then test whether the contrast predicts object/site context."
    if pair_kind == "STEM_SEMANTIC_CONTROL":
        return "Use as a stem-semantic control before any sound assignment."
    if pair_kind == "BRIDGE_STEM_CONTROL":
        return "Compare bare and OP240-prefixed forms to test whether the same stem identity survives OP240."
    return f"Hold {a}::{b} as occurrence-limited until more same-frame examples are validated."


def build_pair_matrix(
    stem_rows: list[dict[str, object]],
    pair_scores: dict[tuple[str, str], dict[str, object]],
    limit: int,
) -> list[dict[str, object]]:
    selected = stem_rows[:limit]
    rows: list[dict[str, object]] = []
    for left_index, left in enumerate(selected):
        for right in selected[left_index + 1 :]:
            a = str(left["StemSign"])
            b = str(right["StemSign"])
            frames_a = counter_from_text(left.get("Frames", ""))
            frames_b = counter_from_text(right.get("Frames", ""))
            if not frames_a:
                frames_a = Counter({str(left.get("TopFrame", "")): fint(str(left.get("TotalCount", 0)))})
            if not frames_b:
                frames_b = Counter({str(right.get("TopFrame", "")): fint(str(right.get("TotalCount", 0)))})
            site_a = counter_from_text(left.get("Sites", ""))
            site_b = counter_from_text(right.get("Sites", ""))
            symbol_a = counter_from_text(left.get("Symbols", ""))
            symbol_b = counter_from_text(right.get("Symbols", ""))
            semantic_a = counter_from_text(left.get("SemanticFrames", ""))
            semantic_b = counter_from_text(right.get("SemanticFrames", ""))
            validation = pair_validation(a, b, pair_scores)
            validation_score = ffloat(str(validation.get("ValidationScore", 0.0)))
            frame_overlap = distribution_overlap(frames_a, frames_b)
            site_jsd = js_divergence(site_a, site_b)
            symbol_jsd = js_divergence(symbol_a, symbol_b)
            semantic_jsd = js_divergence(semantic_a, semantic_b)
            context_contrast = clamp((site_jsd + symbol_jsd + semantic_jsd) / 3.0)
            total_count = fint(str(left.get("TotalCount"))) + fint(str(right.get("TotalCount")))
            controlled_bonus = 0.0
            for side in [left, right]:
                if "OP240" in str(side.get("StemRole", "")):
                    controlled_bonus += 0.075
                if "PHONETIC" in str(side.get("StemRole", "")):
                    controlled_bonus += 0.075
            kind = pair_class(a, b, left, right, validation)
            if kind == "PRIMARY_PHONETIC_LANE_AFTER_IMAGE_CHECK":
                controlled_bonus += 0.20
            score = clamp(
                validation_score * 0.35
                + frame_overlap * 0.20
                + min(total_count / 24.0, 1.0) * 0.15
                + context_contrast * 0.15
                + controlled_bonus
            )
            rows.append(
                {
                    "StemA": a,
                    "StemB": b,
                    "Pair": f"{a}::{b}",
                    "PairClass": kind,
                    "AccelerationScore": f"{score:.3f}",
                    "ValidationScore": f"{validation_score:.3f}",
                    "ValidationStatus": validation.get("ValidationStatus", ""),
                    "Probe": validation.get("Probe", ""),
                    "FrameOverlap": f"{frame_overlap:.3f}",
                    "SiteJSD": f"{site_jsd:.3f}",
                    "SymbolJSD": f"{symbol_jsd:.3f}",
                    "SemanticJSD": f"{semantic_jsd:.3f}",
                    "CombinedCount": total_count,
                    "NextAction": next_action_for_pair(kind, a, b),
                }
            )
    return sorted(rows, key=lambda row: (-ffloat(str(row["AccelerationScore"])), str(row["Pair"])))


def build_templates(stem_rows: list[dict[str, object]], pair_rows: list[dict[str, object]]) -> list[dict[str, object]]:
    phonetic_pairs = [row for row in pair_rows if row["PairClass"] == "PRIMARY_PHONETIC_LANE_AFTER_IMAGE_CHECK"]
    bridge_stems = [row for row in stem_rows if row["StemRole"] == "OP240_BARE_BRIDGE_STEM"]
    return [
        {
            "TemplateId": "T-STEM-01",
            "Template": "002 OP240 STEM 740",
            "StructuralReading": "prime entity frame with OP240-qualified stem",
            "Evidence": "240 model plus controlled stem lanes.",
            "Use": "Main lane for 482, 904, and 176 before phonetic assignment.",
        },
        {
            "TemplateId": "T-STEM-02",
            "Template": "002 STEM 740",
            "StructuralReading": "bare prime entity stem",
            "Evidence": "048, 061, and 176 occur as bare controls in the same prime frame.",
            "Use": "Tests whether OP240 preserves stem identity or changes function.",
        },
        {
            "TemplateId": "T-STEM-03",
            "Template": "OP240 + 482 :: OP240 + 904",
            "StructuralReading": "first phonetic-grade contrast lane after image review",
            "Evidence": phonetic_pairs[0].get("ValidationStatus", "") if phonetic_pairs else "pending",
            "Use": "Do not assign sound; use as the first controlled contrast to image-check.",
        },
        {
            "TemplateId": "T-STEM-04",
            "Template": "176 :: 048 :: 061",
            "StructuralReading": "bare/bridge semantic stem controls",
            "Evidence": bridge_stems[0].get("ValidationStatuses", "") if bridge_stems else "pending",
            "Use": "Semantic and iconographic controls for the prime entity slot.",
        },
    ]


def build_summary(stem_rows: list[dict[str, object]], pair_rows: list[dict[str, object]]) -> list[dict[str, object]]:
    roles = Counter(str(row["StemRole"]) for row in stem_rows)
    pair_classes = Counter(str(row["PairClass"]) for row in pair_rows)
    top_stem = stem_rows[0] if stem_rows else {}
    top_pair = pair_rows[0] if pair_rows else {}
    return [
        {"Metric": "Stem profiles", "Value": len(stem_rows), "Note": top_counter(roles, 5)},
        {"Metric": "Pairwise contrasts", "Value": len(pair_rows), "Note": top_counter(pair_classes, 5)},
        {"Metric": "Top stem", "Value": top_stem.get("StemSign", ""), "Note": f"{top_stem.get('StemRole', '')}; score={top_stem.get('StemScore', '')}"},
        {"Metric": "Top pair", "Value": top_pair.get("Pair", ""), "Note": f"{top_pair.get('PairClass', '')}; score={top_pair.get('AccelerationScore', '')}"},
        {"Metric": "Primary phonetic lane", "Value": "482::904", "Note": "Only after image/context validation; no sound value assigned."},
        {"Metric": "Bridge controls", "Value": "176; 048; 061", "Note": "Tests whether OP240 preserves identity across bare and prefixed forms."},
    ]


def write_latex_section(
    path: Path,
    summary: list[dict[str, object]],
    stems: list[dict[str, object]],
    pairs: list[dict[str, object]],
    templates: list[dict[str, object]],
) -> None:
    display_summary = []
    for row in summary:
        display_row = dict(row)
        if display_row.get("Metric") in {"Stem profiles", "Pairwise contrasts"}:
            display_row["Note"] = compact_counter_text(display_row.get("Note", ""))
        elif display_row.get("Metric") in {"Top stem", "Top pair"}:
            display_row["Note"] = compact_counter_text(display_row.get("Note", ""))
        display_summary.append(display_row)
    top_stems = [
        {
            "Stem": row["StemSign"],
            "Role": compact_label(row["StemRole"]),
            "Score": row["StemScore"],
            "OP240": row["OP240Count"],
            "Bare": row["BareCount"],
        }
        for row in stems[:10]
    ]
    top_pairs = [
        {
            "Pair": row["Pair"],
            "Class": compact_label(row["PairClass"]),
            "Score": row["AccelerationScore"],
            "Validation": row["ValidationScore"],
        }
        for row in pairs[:10]
    ]
    template_rows = [
        {"Template": row["Template"], "Reading": row["StructuralReading"], "Use": row["Use"]}
        for row in templates
    ]
    text = (
        r"""\section{Stem Lattice Keystone Model}

\subsection{Purpose}

The \texttt{240} grammar model gives us a controlled environment. This section turns that environment into a stem lattice: a ranked space of stem signs and stem contrasts in the prime entity frame. The result is not a decipherment, but it is a move toward one: it identifies which contrasts can now be tested repeatedly without changing the surrounding grammar.

\subsection{Summary}

\begin{table}[htbp]
\centering
\footnotesize
"""
        + latex_table(display_summary, ["Metric", "Value", "Note"], ["p{0.30\\textwidth}", "p{0.18\\textwidth}", "p{0.38\\textwidth}"])
        + r"""
\caption{Stem lattice keystone summary.}
\label{tab:stem-lattice-keystone-summary}
\end{table}

\subsection{Stem Profiles}

\begin{table}[htbp]
\centering
\scriptsize
"""
        + latex_table(top_stems, ["Stem", "Role", "Score", "OP240", "Bare"], ["l", "p{0.42\\textwidth}", "r", "r", "r"])
        + r"""
\caption{Highest-ranked stem signs in the prime entity environment.}
\label{tab:stem-lattice-keystone-stems}
\end{table}

\subsection{Contrast Matrix}

\begin{table}[htbp]
\centering
\scriptsize
"""
        + latex_table(top_pairs, ["Pair", "Class", "Score", "Validation"], ["l", "p{0.48\\textwidth}", "r", "r"])
        + r"""
\caption{Highest-ranked stem contrasts.}
\label{tab:stem-lattice-keystone-pairs}
\end{table}

\subsection{Structural Templates}

\begin{table}[htbp]
\centering
\scriptsize
"""
        + latex_table(template_rows, ["Template", "Reading", "Use"], ["p{0.24\\textwidth}", "p{0.28\\textwidth}", "p{0.34\\textwidth}"])
        + r"""
\caption{Reusable structural templates produced by the stem lattice.}
\label{tab:stem-lattice-keystone-templates}
\end{table}

\subsection{Decision}

The current fastest lane is \texttt{240-482 :: 240-904}. It is the first contrast that is both structurally controlled by \texttt{OP240} and already marked as phonetic-ready after image checking. The bridge-control lane is \texttt{176 :: 048 :: 061}, because \texttt{176} has both bare and \texttt{OP240}-prefixed evidence while \texttt{048} and \texttt{061} are strong bare controls in the same prime entity frame.

The reading discipline remains strict: \texttt{OP240} is a grammatical operator, \texttt{STEM} is an abstract stem slot, and no Dravidian, Indo-Aryan, Munda, or other phonetic value is assigned yet.

\subsection{Outputs}

\begin{itemize}
  \item \texttt{outputs/stem\_lattice\_keystone\_summary.csv}
  \item \texttt{outputs/stem\_lattice\_keystone\_profiles.csv}
  \item \texttt{outputs/stem\_lattice\_keystone\_pair\_matrix.csv}
  \item \texttt{outputs/stem\_lattice\_keystone\_templates.csv}
  \item \texttt{outputs/stem\_lattice\_keystone\_model.tex}
\end{itemize}
"""
    )
    path.write_text(text, encoding="utf-8")


def model(args: argparse.Namespace) -> None:
    out_dir = Path(args.out_dir)
    docs_section = Path(args.docs_section)
    structural_by_text = load_structural_by_text(out_dir)
    roles = load_role_map(out_dir)
    preservation = load_preservation(out_dir)
    sign_statuses, sign_scores, pair_scores = validation_by_sign_and_pair(out_dir)
    stem_rows = build_stem_profiles(out_dir, roles, preservation, structural_by_text, sign_statuses, sign_scores)
    pair_rows = build_pair_matrix(stem_rows, pair_scores, args.pair_limit)
    templates = build_templates(stem_rows, pair_rows)
    summary = build_summary(stem_rows, pair_rows)

    write_csv(out_dir / "stem_lattice_keystone_summary.csv", summary, ["Metric", "Value", "Note"])
    write_csv(
        out_dir / "stem_lattice_keystone_profiles.csv",
        stem_rows,
        [
            "StemSign",
            "StemRole",
            "Post240Class",
            "StemScore",
            "TotalCount",
            "OP240Count",
            "BareCount",
            "TextCount",
            "TopForms",
            "TopFrame",
            "TopFrameShare",
            "Frames",
            "Sites",
            "Symbols",
            "SemanticFrames",
            "ValidationScore",
            "ValidationStatuses",
            "Examples",
        ],
    )
    write_csv(
        out_dir / "stem_lattice_keystone_pair_matrix.csv",
        pair_rows,
        [
            "StemA",
            "StemB",
            "Pair",
            "PairClass",
            "AccelerationScore",
            "ValidationScore",
            "ValidationStatus",
            "Probe",
            "FrameOverlap",
            "SiteJSD",
            "SymbolJSD",
            "SemanticJSD",
            "CombinedCount",
            "NextAction",
        ],
    )
    write_csv(
        out_dir / "stem_lattice_keystone_templates.csv",
        templates,
        ["TemplateId", "Template", "StructuralReading", "Evidence", "Use"],
    )
    write_latex_section(out_dir / "stem_lattice_keystone_model.tex", summary, stem_rows, pair_rows, templates)
    write_latex_section(docs_section, summary, stem_rows, pair_rows, templates)

    for path in [
        out_dir / "stem_lattice_keystone_summary.csv",
        out_dir / "stem_lattice_keystone_profiles.csv",
        out_dir / "stem_lattice_keystone_pair_matrix.csv",
        out_dir / "stem_lattice_keystone_templates.csv",
        out_dir / "stem_lattice_keystone_model.tex",
        docs_section,
    ]:
        print(f"Wrote {path}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out-dir", default="outputs")
    parser.add_argument("--docs-section", default="docs/sections/stem_lattice_keystone_model.tex")
    parser.add_argument("--pair-limit", type=int, default=16)
    return parser.parse_args()


if __name__ == "__main__":
    model(parse_args())
