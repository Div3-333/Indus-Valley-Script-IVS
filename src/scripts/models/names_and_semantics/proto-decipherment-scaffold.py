#!/usr/bin/env python3
"""Build a proto-decipherment scaffold from anchor and slot evidence.

This stage stays one step short of assigning phonetic values. It converts the
onomastic-anchor model into artifact-level review queues, abstract templates,
and explicit constraints that any future decipherment must satisfy.
"""

from __future__ import annotations

import argparse
import csv
import math
import re
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path


TOKEN_RE = re.compile(r"(?<!\d)\d{3,4}(?!\d)")
BOUNDARY_START = "<START>"
BOUNDARY_END = "<END>"


@dataclass(frozen=True)
class TitleMarker:
    ngram: tuple[str, ...]
    score: float
    count: int
    start_pct: float
    end_pct: float
    role: str


@dataclass(frozen=True)
class NameBlock:
    ngram: tuple[str, ...]
    name_score: float
    cross_site_score: float
    formula_risk: float
    count: int
    site_count: int
    role: str


@dataclass(frozen=True)
class SlotFrame:
    left: str
    right: str
    score: float
    count: int
    distinct_fillers: int


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


def latex_escape(value: object) -> str:
    text = "" if value is None else str(value)
    replacements = {
        "\\": "/",
        "_": r"\_",
        "%": r"\%",
        "&": r"\&",
        "#": r"\#",
        "$": r"\$",
        "<": r"$<$",
        ">": r"$>$",
    }
    for source, target in replacements.items():
        text = text.replace(source, target)
    return text


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8-sig") as handle:
        return list(csv.DictReader(handle))


def write_csv(path: Path, rows: list[dict[str, object]], fields: list[str]) -> None:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def marker_role(start_pct: float, end_pct: float) -> str:
    if start_pct >= 0.60:
        return "INITIAL_TITLE_OR_CLASSIFIER"
    if end_pct >= 0.60:
        return "TERMINAL_TITLE_OR_SUFFIX"
    if start_pct > end_pct:
        return "LEADING_FORMULA_MARKER"
    if end_pct > start_pct:
        return "CLOSING_FORMULA_MARKER"
    return "FLEXIBLE_FORMULA_MARKER"


def parse_ngram(value: str) -> tuple[str, ...]:
    return tuple(part for part in value.split("-") if part)


def load_title_markers(path: Path, threshold: float, limit: int) -> list[TitleMarker]:
    markers: list[TitleMarker] = []
    for row in read_csv(path):
        score = ffloat(row.get("TitleMarkerScore"))
        if score < threshold:
            continue
        ngram = parse_ngram(row["NGram"])
        start_pct = ffloat(row.get("StartPct"))
        end_pct = ffloat(row.get("EndPct"))
        markers.append(
            TitleMarker(
                ngram=ngram,
                score=score,
                count=fint(row.get("Count")),
                start_pct=start_pct,
                end_pct=end_pct,
                role=marker_role(start_pct, end_pct),
            )
        )
    markers.sort(key=lambda item: (-item.score, -item.count, item.ngram))
    return markers[:limit]


def load_name_blocks(path: Path, threshold: float, formula_risk_max: float, limit: int) -> list[NameBlock]:
    blocks: list[NameBlock] = []
    for row in read_csv(path):
        ngram = parse_ngram(row["NGram"])
        if len(ngram) < 2:
            continue
        name_score = ffloat(row.get("NameAnchorScore"))
        cross_site_score = ffloat(row.get("CrossSiteAnchorScore"))
        formula_risk = ffloat(row.get("FormulaRiskScore"))
        if name_score < threshold or formula_risk > formula_risk_max:
            continue
        role = "CROSS_SITE_NAME_ANCHOR" if cross_site_score >= 0.80 else "NAME_LIKE_BLOCK"
        blocks.append(
            NameBlock(
                ngram=ngram,
                name_score=name_score,
                cross_site_score=cross_site_score,
                formula_risk=formula_risk,
                count=fint(row.get("Count")),
                site_count=fint(row.get("SiteCount")),
                role=role,
            )
        )
    blocks.sort(
        key=lambda item: (
            -item.cross_site_score,
            -item.name_score,
            item.formula_risk,
            -item.site_count,
            item.ngram,
        )
    )
    return blocks[:limit]


def load_slots(path: Path, threshold: float, limit: int) -> list[SlotFrame]:
    slots: list[SlotFrame] = []
    for row in read_csv(path):
        score = ffloat(row.get("NameSlotScore"))
        if score < threshold:
            continue
        slots.append(
            SlotFrame(
                left=row["Left"],
                right=row["Right"],
                score=score,
                count=fint(row.get("Count")),
                distinct_fillers=fint(row.get("DistinctFillers")),
            )
        )
    slots.sort(key=lambda item: (-item.score, -item.distinct_fillers, -item.count, item.left, item.right))
    return slots[:limit]


def find_matches(tokens: list[str], patterns: dict[tuple[str, ...], object], max_length: int) -> list[tuple[int, int, tuple[str, ...], object]]:
    matches: list[tuple[int, int, tuple[str, ...], object]] = []
    for start in range(len(tokens)):
        for length in range(max_length, 0, -1):
            if start + length > len(tokens):
                continue
            ngram = tuple(tokens[start : start + length])
            if ngram in patterns:
                matches.append((start, start + length, ngram, patterns[ngram]))
                break
    return matches


def non_overlapping(matches: list[tuple[int, int, tuple[str, ...], object]]) -> list[tuple[int, int, tuple[str, ...], object]]:
    selected: list[tuple[int, int, tuple[str, ...], object]] = []
    occupied: set[int] = set()
    for match in sorted(matches, key=lambda item: (-(item[1] - item[0]), item[0], item[2])):
        positions = set(range(match[0], match[1]))
        if occupied & positions:
            continue
        selected.append(match)
        occupied |= positions
    return sorted(selected, key=lambda item: item[0])


def compact_template(tokens: list[str], name_matches: list[tuple[int, int, tuple[str, ...], object]], title_patterns: dict[tuple[str, ...], TitleMarker]) -> str:
    name_by_start = {start: (end, data) for start, end, _ngram, data in name_matches}
    parts: list[str] = []
    index = 0
    while index < len(tokens):
        if index in name_by_start:
            end, data = name_by_start[index]
            assert isinstance(data, NameBlock)
            parts.append(f"{data.role}[{end - index}]")
            index = end
            continue

        unigram = (tokens[index],)
        marker = title_patterns.get(unigram)
        if marker is not None:
            parts.append(marker.role)
        else:
            parts.append("SIGN")
        index += 1
    return " ".join(parts)


def token_role_template(tokens: list[str], title_patterns: dict[tuple[str, ...], TitleMarker], slot_patterns: set[tuple[str, str]]) -> str:
    roles: list[str] = []
    for index, token in enumerate(tokens):
        left = BOUNDARY_START if index == 0 else tokens[index - 1]
        right = BOUNDARY_END if index == len(tokens) - 1 else tokens[index + 1]
        marker = title_patterns.get((token,))
        if marker is not None:
            roles.append(marker.role)
        elif (left, right) in slot_patterns:
            roles.append("SLOT_FILLER")
        else:
            roles.append("SIGN")
    return " ".join(roles)


def context(tokens: list[str], start: int, end: int, window: int = 3) -> tuple[str, str]:
    left_start = max(0, start - window)
    right_end = min(len(tokens), end + window)
    left = " ".join(tokens[left_start:start])
    right = " ".join(tokens[end:right_end])
    return left, right


def row_base(row: dict[str, str], tokens: list[str]) -> dict[str, object]:
    return {
        "TextId": row.get("id", ""),
        "CISI": row.get("cisi", ""),
        "Region": row.get("region", ""),
        "Site": row.get("site", ""),
        "Type": row.get("type", ""),
        "Complete": row.get("complete", ""),
        "Direction": row.get("dir.", ""),
        "RawText": row.get("text", ""),
        "ReadingTokens": "-".join(tokens),
    }


def classify_review_question(kind: str, marker_role_value: str | None = None) -> str:
    if kind == "NameBlock":
        return "Inspect artifact image and neighbors: name, office, lineage, place, commodity, or fixed formula?"
    if kind == "SlotFiller":
        return "Inspect whether this filler behaves like a variable name/title field inside a stable frame."
    if marker_role_value == "INITIAL_TITLE_OR_CLASSIFIER":
        return "Test whether this initial marker classifies seal owner, office, group, place, or artifact function."
    if marker_role_value == "TERMINAL_TITLE_OR_SUFFIX":
        return "Test whether this terminal marker is title, suffix, object class, number/unit, or closing formula."
    return "Test marker role against artifact type and neighboring slot fillers."


def model(args: argparse.Namespace) -> None:
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    titles = load_title_markers(Path(args.title_candidates), args.title_threshold, args.title_limit)
    names = load_name_blocks(Path(args.ngram_candidates), args.name_threshold, args.formula_risk_max, args.name_limit)
    slots = load_slots(Path(args.slot_candidates), args.slot_threshold, args.slot_limit)

    title_patterns = {item.ngram: item for item in titles}
    name_patterns = {item.ngram: item for item in names}
    slot_patterns = {(item.left, item.right) for item in slots}
    max_title_len = max((len(item.ngram) for item in titles), default=1)
    max_name_len = max((len(item.ngram) for item in names), default=1)

    text_template_rows: list[dict[str, object]] = []
    review_rows: list[dict[str, object]] = []
    constraint_rows: list[dict[str, object]] = []
    template_counts: Counter[str] = Counter()
    template_sites: dict[str, set[str]] = defaultdict(set)
    template_types: dict[str, set[str]] = defaultdict(set)
    template_examples: dict[str, list[str]] = defaultdict(list)
    name_occurrence_counter: Counter[str] = Counter()
    slot_occurrence_counter: Counter[str] = Counter()
    title_occurrence_counter: Counter[str] = Counter()

    with Path(args.corpus_path).open(newline="", encoding="utf-8-sig") as handle:
        for row in csv.DictReader(handle):
            tokens = [token for token in sign_tokens(row.get("text")) if token not in {"000", "999"}]
            tokens.reverse()
            if not tokens:
                continue

            title_matches = find_matches(tokens, title_patterns, max_title_len)
            name_matches = non_overlapping(find_matches(tokens, name_patterns, max_name_len))
            role_template = token_role_template(tokens, title_patterns, slot_patterns)
            anchor_template = compact_template(tokens, name_matches, title_patterns)
            title_labels = []
            for start, end, ngram, data in title_matches:
                assert isinstance(data, TitleMarker)
                label = "-".join(ngram)
                title_labels.append(f"{label}:{data.role}@{start + 1}-{end}")
                title_occurrence_counter[label] += 1
            name_labels = []
            for start, end, ngram, data in name_matches:
                assert isinstance(data, NameBlock)
                label = "-".join(ngram)
                name_labels.append(f"{label}:{data.role}@{start + 1}-{end}")
                name_occurrence_counter[label] += 1
            slot_labels = []
            for index, token in enumerate(tokens):
                left = BOUNDARY_START if index == 0 else tokens[index - 1]
                right = BOUNDARY_END if index == len(tokens) - 1 else tokens[index + 1]
                if (left, right) in slot_patterns:
                    label = f"{left}|{right}"
                    slot_labels.append(f"{label}:{token}@{index + 1}")
                    slot_occurrence_counter[label] += 1

            has_anchor = bool(title_labels or name_labels or slot_labels)
            text_template_rows.append(
                {
                    **row_base(row, tokens),
                    "Length": len(tokens),
                    "RoleTemplate": role_template,
                    "AnchorTemplate": anchor_template,
                    "TitleMarkers": "; ".join(title_labels),
                    "NameBlocks": "; ".join(name_labels),
                    "SlotFillers": "; ".join(slot_labels),
                    "HasAnchor": "Y" if has_anchor else "N",
                }
            )

            template_counts[anchor_template] += 1
            template_sites[anchor_template].add(row.get("site", ""))
            template_types[anchor_template].add(row.get("type", ""))
            if len(template_examples[anchor_template]) < 6:
                template_examples[anchor_template].append(f"{row.get('id')}/{row.get('cisi')}/{row.get('site')}")

            for start, end, ngram, data in name_matches:
                assert isinstance(data, NameBlock)
                label = "-".join(ngram)
                left, right = context(tokens, start, end)
                priority = "A" if data.cross_site_score >= 0.85 and row.get("complete") == "Y" else "B"
                review_rows.append(
                    {
                        **row_base(row, tokens),
                        "ReviewKind": "NameBlock",
                        "Candidate": label,
                        "RoleHypothesis": data.role,
                        "StartPos": start + 1,
                        "EndPos": end,
                        "LeftContext": left,
                        "RightContext": right,
                        "Score": round(data.name_score, 4),
                        "SecondaryScore": round(data.cross_site_score, 4),
                        "FormulaRisk": round(data.formula_risk, 4),
                        "Priority": priority,
                        "ReviewQuestion": classify_review_question("NameBlock"),
                    }
                )

            for start, end, ngram, data in title_matches:
                assert isinstance(data, TitleMarker)
                label = "-".join(ngram)
                if title_occurrence_counter[label] > args.max_title_examples_per_marker:
                    continue
                left, right = context(tokens, start, end)
                review_rows.append(
                    {
                        **row_base(row, tokens),
                        "ReviewKind": "TitleMarker",
                        "Candidate": label,
                        "RoleHypothesis": data.role,
                        "StartPos": start + 1,
                        "EndPos": end,
                        "LeftContext": left,
                        "RightContext": right,
                        "Score": round(data.score, 4),
                        "SecondaryScore": "",
                        "FormulaRisk": "",
                        "Priority": "A" if data.score >= 0.80 and row.get("complete") == "Y" else "B",
                        "ReviewQuestion": classify_review_question("TitleMarker", data.role),
                    }
                )

            for index, token in enumerate(tokens):
                left = BOUNDARY_START if index == 0 else tokens[index - 1]
                right = BOUNDARY_END if index == len(tokens) - 1 else tokens[index + 1]
                if (left, right) not in slot_patterns:
                    continue
                label = f"{left}|{right}"
                if slot_occurrence_counter[label] > args.max_slot_examples_per_frame:
                    continue
                left_context, right_context = context(tokens, index, index + 1)
                slot_data = next(item for item in slots if item.left == left and item.right == right)
                review_rows.append(
                    {
                        **row_base(row, tokens),
                        "ReviewKind": "SlotFiller",
                        "Candidate": token,
                        "RoleHypothesis": f"FILLER_IN_{label}",
                        "StartPos": index + 1,
                        "EndPos": index + 1,
                        "LeftContext": left_context,
                        "RightContext": right_context,
                        "Score": round(slot_data.score, 4),
                        "SecondaryScore": slot_data.distinct_fillers,
                        "FormulaRisk": "",
                        "Priority": "A" if slot_data.score >= 0.93 and row.get("complete") == "Y" else "B",
                        "ReviewQuestion": classify_review_question("SlotFiller"),
                    }
                )

    template_family_rows: list[dict[str, object]] = []
    for template, count in template_counts.most_common():
        template_family_rows.append(
            {
                "AnchorTemplate": template,
                "Count": count,
                "SiteCount": len({site for site in template_sites[template] if site}),
                "TypeCount": len({typ for typ in template_types[template] if typ}),
                "Examples": "; ".join(template_examples[template]),
            }
        )

    for marker in titles:
        if len(marker.ngram) != 1:
            continue
        sign = marker.ngram[0]
        constraint_rows.append(
            {
                "ConstraintId": f"T-{sign}",
                "EvidenceType": "TitleOrClassifierMarker",
                "Candidate": sign,
                "Constraint": f"Any reading of {sign} must explain its {marker.role.lower()} distribution.",
                "Evidence": f"count={marker.count}; start_pct={marker.start_pct:.3f}; end_pct={marker.end_pct:.3f}; score={marker.score:.3f}",
                "AllowedInterpretations": "title; classifier; suffix/prefix; office/status marker; object/commodity class; formula boundary",
                "DisallowedShortcut": "Do not read it as an ordinary phonetic sign unless the positional skew is explained.",
            }
        )

    for slot in slots[:12]:
        constraint_rows.append(
            {
                "ConstraintId": f"S-{slot.left}_{slot.right}",
                "EvidenceType": "ProductiveSlot",
                "Candidate": f"{slot.left} _ {slot.right}",
                "Constraint": "A future decipherment must explain why many different fillers occupy this same immediate frame.",
                "Evidence": f"count={slot.count}; distinct_fillers={slot.distinct_fillers}; score={slot.score:.3f}",
                "AllowedInterpretations": "personal-name slot; title/office slot; place/lineage slot; commodity/measure slot; productive grammatical frame",
                "DisallowedShortcut": "Do not translate the whole frame as one fixed word.",
            }
        )

    for block in names[:25]:
        label = "-".join(block.ngram)
        constraint_rows.append(
            {
                "ConstraintId": f"N-{label}",
                "EvidenceType": "NameLikeBlock",
                "Candidate": label,
                "Constraint": "If this is a name/title/place, its reading must survive across every listed occurrence and context.",
                "Evidence": f"count={block.count}; sites={block.site_count}; name_score={block.name_score:.3f}; cross_site={block.cross_site_score:.3f}; formula_risk={block.formula_risk:.3f}",
                "AllowedInterpretations": "personal name; dynastic/lineage label; title phrase; place name; repeated administrative phrase",
                "DisallowedShortcut": "Do not assign a phonetic value from one artifact only.",
            }
        )

    review_rows.sort(
        key=lambda row: (
            row["Priority"],
            row["ReviewKind"],
            -ffloat(str(row["Score"])),
            str(row["Candidate"]),
            str(row["TextId"]),
        )
    )

    summary_rows = [
        {"Metric": "Title/classifier markers used", "Value": len(titles), "Note": f"threshold >= {args.title_threshold}"},
        {"Metric": "Name-like blocks used", "Value": len(names), "Note": f"name score >= {args.name_threshold}, formula risk <= {args.formula_risk_max}"},
        {"Metric": "Productive slots used", "Value": len(slots), "Note": f"slot score >= {args.slot_threshold}"},
        {"Metric": "Texts templated", "Value": len(text_template_rows), "Note": "Analyzable non-empty inscriptions."},
        {"Metric": "Texts with any anchor", "Value": sum(row["HasAnchor"] == "Y" for row in text_template_rows), "Note": "Title marker, name block, or selected slot filler present."},
        {"Metric": "Template families", "Value": len(template_family_rows), "Note": "Distinct collapsed anchor templates."},
        {"Metric": "Review queue rows", "Value": len(review_rows), "Note": "Artifact-level checks for concrete follow-up."},
        {"Metric": "Constraint rows", "Value": len(constraint_rows), "Note": "Explicit rules future readings must satisfy."},
    ]

    text_path = out_dir / "proto_decipherment_text_templates.csv"
    families_path = out_dir / "proto_decipherment_template_families.csv"
    review_path = out_dir / "proto_decipherment_anchor_review_queue.csv"
    constraints_path = out_dir / "proto_decipherment_constraints.csv"
    summary_path = out_dir / "proto_decipherment_summary.csv"
    tex_path = out_dir / "proto_decipherment_scaffold.tex"

    text_fields = [
        "TextId",
        "CISI",
        "Region",
        "Site",
        "Type",
        "Complete",
        "Direction",
        "RawText",
        "ReadingTokens",
        "Length",
        "RoleTemplate",
        "AnchorTemplate",
        "TitleMarkers",
        "NameBlocks",
        "SlotFillers",
        "HasAnchor",
    ]
    family_fields = ["AnchorTemplate", "Count", "SiteCount", "TypeCount", "Examples"]
    review_fields = [
        "TextId",
        "CISI",
        "Region",
        "Site",
        "Type",
        "Complete",
        "Direction",
        "RawText",
        "ReadingTokens",
        "ReviewKind",
        "Candidate",
        "RoleHypothesis",
        "StartPos",
        "EndPos",
        "LeftContext",
        "RightContext",
        "Score",
        "SecondaryScore",
        "FormulaRisk",
        "Priority",
        "ReviewQuestion",
    ]
    constraint_fields = [
        "ConstraintId",
        "EvidenceType",
        "Candidate",
        "Constraint",
        "Evidence",
        "AllowedInterpretations",
        "DisallowedShortcut",
    ]

    write_csv(text_path, text_template_rows, text_fields)
    write_csv(families_path, template_family_rows, family_fields)
    write_csv(review_path, review_rows, review_fields)
    write_csv(constraints_path, constraint_rows, constraint_fields)
    write_csv(summary_path, summary_rows, ["Metric", "Value", "Note"])

    top_title_rows = [
        {
            "Candidate": "-".join(marker.ngram),
            "Role": marker.role,
            "Count": marker.count,
            "StartPct": f"{marker.start_pct:.3f}",
            "EndPct": f"{marker.end_pct:.3f}",
            "Score": f"{marker.score:.3f}",
        }
        for marker in titles[:10]
    ]
    top_slot_rows = [
        {
            "Frame": f"{slot.left} _ {slot.right}",
            "Count": slot.count,
            "Fillers": slot.distinct_fillers,
            "Score": f"{slot.score:.3f}",
        }
        for slot in slots[:10]
    ]
    top_family_rows = template_family_rows[:10]
    top_constraint_rows = constraint_rows[:12]

    lines: list[str] = [
        r"\documentclass[11pt,a4paper]{article}",
        r"\usepackage[margin=1in]{geometry}",
        r"\usepackage[T1]{fontenc}",
        r"\usepackage[utf8]{inputenc}",
        r"\usepackage{booktabs}",
        r"\begin{document}",
        r"\section*{Proto-Decipherment Scaffold}",
        "This report converts anchor evidence into concrete constraints: candidate title/classifier signs, productive variable slots, abstract inscription templates, and artifact-level review rows. It remains pre-phonetic.",
        r"\subsection*{Summary}",
        r"\begin{center}",
        r"\begin{tabular}{lr}",
        r"\toprule",
        r"\textbf{Metric} & \textbf{Value} \\",
        r"\midrule",
    ]
    for row in summary_rows:
        lines.append(f"{latex_escape(row['Metric'])} & {latex_escape(row['Value'])} \\\\")
    lines.extend(
        [
            r"\bottomrule",
            r"\end{tabular}",
            r"\end{center}",
            r"\subsection*{Top Functional Markers}",
            r"\begin{center}",
            r"\begin{tabular}{llrrrr}",
            r"\toprule",
            r"\textbf{Candidate} & \textbf{Role} & \textbf{Count} & \textbf{Start} & \textbf{End} & \textbf{Score} \\",
            r"\midrule",
        ]
    )
    for row in top_title_rows:
        values = [row["Candidate"], row["Role"], row["Count"], row["StartPct"], row["EndPct"], row["Score"]]
        lines.append(" & ".join(latex_escape(value) for value in values) + r" \\")
    lines.extend(
        [
            r"\bottomrule",
            r"\end{tabular}",
            r"\end{center}",
            r"\subsection*{Top Productive Slots}",
            r"\begin{center}",
            r"\begin{tabular}{lrrr}",
            r"\toprule",
            r"\textbf{Frame} & \textbf{Count} & \textbf{Fillers} & \textbf{Score} \\",
            r"\midrule",
        ]
    )
    for row in top_slot_rows:
        values = [row["Frame"], row["Count"], row["Fillers"], row["Score"]]
        lines.append(" & ".join(latex_escape(value) for value in values) + r" \\")
    lines.extend(
        [
            r"\bottomrule",
            r"\end{tabular}",
            r"\end{center}",
            r"\subsection*{Top Abstract Template Families}",
            r"\begin{center}",
            r"\begin{tabular}{p{0.52\textwidth}rr}",
            r"\toprule",
            r"\textbf{Template} & \textbf{Count} & \textbf{Sites} \\",
            r"\midrule",
        ]
    )
    for row in top_family_rows:
        values = [row["AnchorTemplate"], row["Count"], row["SiteCount"]]
        lines.append(" & ".join(latex_escape(value) for value in values) + r" \\")
    lines.extend(
        [
            r"\bottomrule",
            r"\end{tabular}",
            r"\end{center}",
            r"\subsection*{Example Constraints}",
            r"\begin{center}",
            r"\begin{tabular}{lp{0.68\textwidth}}",
            r"\toprule",
            r"\textbf{ID} & \textbf{Constraint} \\",
            r"\midrule",
        ]
    )
    for row in top_constraint_rows:
        values = [row["ConstraintId"], row["Constraint"]]
        lines.append(" & ".join(latex_escape(value) for value in values) + r" \\")
    lines.extend(
        [
            r"\bottomrule",
            r"\end{tabular}",
            r"\end{center}",
            r"\subsection*{Outputs}",
            r"\begin{itemize}",
        ]
    )
    for path in [text_path, families_path, review_path, constraints_path, summary_path]:
        lines.append(r"\item \texttt{" + latex_escape(path) + "}")
    lines.extend([r"\end{itemize}", r"\end{document}"])
    tex_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    for path in [text_path, families_path, review_path, constraints_path, summary_path, tex_path]:
        print(f"Wrote {path}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--corpus-path", default="data/ivs_corpus_cleaned.csv")
    parser.add_argument("--ngram-candidates", default="outputs/onomastic_anchor_ngram_candidates.csv")
    parser.add_argument("--title-candidates", default="outputs/onomastic_title_marker_candidates.csv")
    parser.add_argument("--slot-candidates", default="outputs/onomastic_formula_slots.csv")
    parser.add_argument("--out-dir", default="outputs")
    parser.add_argument("--title-threshold", type=float, default=0.78)
    parser.add_argument("--name-threshold", type=float, default=0.90)
    parser.add_argument("--formula-risk-max", type=float, default=0.66)
    parser.add_argument("--slot-threshold", type=float, default=0.91)
    parser.add_argument("--title-limit", type=int, default=24)
    parser.add_argument("--name-limit", type=int, default=80)
    parser.add_argument("--slot-limit", type=int, default=24)
    parser.add_argument("--max-title-examples-per-marker", type=int, default=20)
    parser.add_argument("--max-slot-examples-per-frame", type=int, default=25)
    return parser.parse_args()


if __name__ == "__main__":
    model(parse_args())
