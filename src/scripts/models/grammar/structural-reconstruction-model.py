#!/usr/bin/env python3
"""Reconstruct inscription-level structural and semantic formulae.

This stage converts sign-level and slot-level evidence into sentence-like
structural parses. It does not assign phonetic values; it identifies the
specific inscriptions and formula families where phonetic testing should begin.
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
START = "<START>"
END = "<END>"


@dataclass(frozen=True)
class Marker:
    sign: str
    score: float
    count: int
    start_pct: float
    end_pct: float
    role: str


@dataclass(frozen=True)
class Slot:
    frame: str
    left: str
    right: str
    score: float
    occurrences: int
    distinct_fillers: int


@dataclass(frozen=True)
class NameBlock:
    tokens: tuple[str, ...]
    score: float
    cross_site_score: float
    formula_risk: float
    count: int


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
        "<": r"$<$",
        ">": r"$>$",
    }
    for source, target in replacements.items():
        text = text.replace(source, target)
    return text


def parse_ngram(value: str) -> tuple[str, ...]:
    return tuple(part for part in value.split("-") if part)


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


def load_markers(path: Path, threshold: float, limit: int) -> dict[str, Marker]:
    markers: list[Marker] = []
    for row in read_csv(path):
        ngram = parse_ngram(row["NGram"])
        if len(ngram) != 1:
            continue
        score = ffloat(row.get("TitleMarkerScore"))
        if score < threshold:
            continue
        start_pct = ffloat(row.get("StartPct"))
        end_pct = ffloat(row.get("EndPct"))
        markers.append(
            Marker(
                sign=ngram[0],
                score=score,
                count=fint(row.get("Count")),
                start_pct=start_pct,
                end_pct=end_pct,
                role=marker_role(start_pct, end_pct),
            )
        )
    markers.sort(key=lambda item: (-item.score, -item.count, item.sign))
    return {marker.sign: marker for marker in markers[:limit]}


def load_slots(path: Path, threshold: float, limit: int) -> list[Slot]:
    slots: list[Slot] = []
    for row in read_csv(path):
        score = ffloat(row.get("SlotScore"))
        if score < threshold:
            continue
        slots.append(
            Slot(
                frame=row["Frame"],
                left=row["Left"],
                right=row["Right"],
                score=score,
                occurrences=fint(row.get("ExtractedOccurrences")),
                distinct_fillers=fint(row.get("DistinctFillers")),
            )
        )
    slots.sort(key=lambda item: (-item.score, -item.distinct_fillers, -item.occurrences, item.frame))
    return slots[:limit]


def load_name_blocks(path: Path, threshold: float, max_formula_risk: float, limit: int) -> dict[tuple[str, ...], NameBlock]:
    blocks: list[NameBlock] = []
    for row in read_csv(path):
        tokens = parse_ngram(row["NGram"])
        if len(tokens) < 2:
            continue
        score = ffloat(row.get("NameAnchorScore"))
        formula_risk = ffloat(row.get("FormulaRiskScore"))
        if score < threshold or formula_risk > max_formula_risk:
            continue
        blocks.append(
            NameBlock(
                tokens=tokens,
                score=score,
                cross_site_score=ffloat(row.get("CrossSiteAnchorScore")),
                formula_risk=formula_risk,
                count=fint(row.get("Count")),
            )
        )
    blocks.sort(key=lambda item: (-item.cross_site_score, -item.score, item.formula_risk, item.tokens))
    return {block.tokens: block for block in blocks[:limit]}


def extract_segments(tokens: list[str], slot: Slot, max_len: int) -> list[tuple[int, int, tuple[str, ...], Slot]]:
    segments: list[tuple[int, int, tuple[str, ...], Slot]] = []
    n = len(tokens)
    if n < 2:
        return segments

    if slot.left == START and slot.right == END:
        if 1 <= n <= max_len:
            segments.append((0, n, tuple(tokens), slot))
        return segments

    if slot.left == START:
        for right_index in range(1, min(n, max_len + 1)):
            if tokens[right_index] == slot.right:
                filler = tuple(tokens[0:right_index])
                if filler:
                    segments.append((0, right_index, filler, slot))
        return segments

    if slot.right == END:
        for left_index, token in enumerate(tokens[:-1]):
            if token != slot.left:
                continue
            filler = tuple(tokens[left_index + 1 :])
            if 1 <= len(filler) <= max_len:
                segments.append((left_index + 1, n, filler, slot))
        return segments

    for left_index, token in enumerate(tokens[:-2]):
        if token != slot.left:
            continue
        max_right_index = min(n - 1, left_index + max_len + 1)
        for right_index in range(left_index + 2, max_right_index + 1):
            if tokens[right_index] == slot.right:
                filler = tuple(tokens[left_index + 1 : right_index])
                if filler:
                    segments.append((left_index + 1, right_index, filler, slot))
    return segments


def non_overlapping_segments(segments: list[tuple[int, int, tuple[str, ...], Slot]]) -> list[tuple[int, int, tuple[str, ...], Slot]]:
    selected: list[tuple[int, int, tuple[str, ...], Slot]] = []
    occupied: set[int] = set()
    for segment in sorted(segments, key=lambda item: (-item[3].score, -(item[1] - item[0]), item[0], item[3].frame)):
        positions = set(range(segment[0], segment[1]))
        if positions & occupied:
            continue
        selected.append(segment)
        occupied |= positions
    return sorted(selected, key=lambda item: item[0])


def find_ngram_matches(tokens: list[str], patterns: dict[tuple[str, ...], NameBlock], max_len: int) -> list[tuple[int, int, tuple[str, ...], NameBlock]]:
    matches: list[tuple[int, int, tuple[str, ...], NameBlock]] = []
    for start in range(len(tokens)):
        for length in range(max_len, 1, -1):
            if start + length > len(tokens):
                continue
            ngram = tuple(tokens[start : start + length])
            block = patterns.get(ngram)
            if block is None:
                continue
            matches.append((start, start + length, ngram, block))
            break
    return matches


def join_tokens(tokens: tuple[str, ...] | list[str]) -> str:
    return "-".join(tokens)


def semantic_candidates(row: dict[str, str], has_prime_slot: bool, has_slot: bool, has_initial: bool, has_terminal: bool, has_name: bool) -> tuple[str, str]:
    typ = row.get("type", "")
    if has_prime_slot and typ.startswith("SEAL"):
        return "PrimeEntitySealFormula", "owner/name; office/title; lineage; place; authority formula"
    if has_prime_slot:
        return "PrimeEntityAdministrativeFormula", "commodity/person/place; measure; object class; title phrase"
    if has_slot and has_initial and has_terminal:
        return "ClassifierSlotTerminalFormula", "classifier + entity/title/place + terminal marker"
    if has_name and has_terminal:
        return "NameLikeTerminalFormula", "name/title/place block + title/suffix/formula final"
    if has_initial and has_terminal:
        return "ClassifierTerminalFormula", "title/classifier + entity phrase + terminal"
    if has_terminal:
        return "TerminalFormula", "short label; title/suffix; object marker; closing formula"
    if has_initial:
        return "InitialClassifierFormula", "classifier/title-led label"
    return "LowEvidenceSequence", "undetermined; requires visual/contextual evidence"


def confidence_score(row: dict[str, str], slots: list[tuple[int, int, tuple[str, ...], Slot]], name_matches: list[tuple[int, int, tuple[str, ...], NameBlock]], marker_count: int, cross_reuse_count: int, minimal_pair_count: int) -> float:
    score = 0.0
    if row.get("complete") == "Y":
        score += 0.12
    if (row.get("type") or "").startswith("SEAL"):
        score += 0.08
    if slots:
        score += min(0.28, 0.14 * len(slots))
    if name_matches:
        score += min(0.20, 0.10 * len(name_matches))
    if marker_count:
        score += min(0.16, 0.06 * marker_count)
    if cross_reuse_count:
        score += min(0.10, 0.04 * cross_reuse_count)
    if minimal_pair_count:
        score += min(0.06, 0.03 * minimal_pair_count)
    return round(min(score, 1.0), 4)


def readiness_label(score: float) -> str:
    if score >= 0.70:
        return "High"
    if score >= 0.50:
        return "Medium"
    if score >= 0.30:
        return "Low"
    return "VeryLow"


def build_structural_parse(tokens: list[str], roles: list[list[str]], slot_segments: list[tuple[int, int, tuple[str, ...], Slot]], name_matches: list[tuple[int, int, tuple[str, ...], NameBlock]]) -> tuple[str, str]:
    slot_by_start = {start: (end, filler, slot) for start, end, filler, slot in slot_segments}
    name_by_start = {start: (end, ngram, block) for start, end, ngram, block in name_matches}

    parts: list[str] = []
    role_parts: list[str] = []
    index = 0
    while index < len(tokens):
        if index in slot_by_start:
            end, filler, slot = slot_by_start[index]
            label = "PRIME_ENTITY_SLOT" if slot.frame == "002|740" else "PRODUCTIVE_SLOT"
            parts.append(f"{label}({slot.left}_{slot.right})[{join_tokens(filler)}]")
            role_parts.append(label)
            index = end
            continue
        if index in name_by_start:
            end, ngram, _block = name_by_start[index]
            parts.append(f"NAME_LIKE_BLOCK[{join_tokens(ngram)}]")
            role_parts.append("NAME_LIKE_BLOCK")
            index = end
            continue

        token_roles = roles[index]
        main_role = token_roles[0] if token_roles else "SIGN"
        parts.append(f"{tokens[index]}:{main_role}")
        role_parts.append(main_role)
        index += 1

    return " | ".join(parts), " ".join(role_parts)


def context_plan(frame_names: list[str], cross_fillers: list[str], minimal_fillers: list[str]) -> str:
    tasks: list[str] = []
    if frame_names:
        tasks.append("compare all artifacts in frames " + ", ".join(sorted(set(frame_names))[:4]))
    if cross_fillers:
        tasks.append("test reused filler(s) " + ", ".join(sorted(set(cross_fillers))[:4]) + " across frames")
    if minimal_fillers:
        tasks.append("inspect minimal alternation(s) involving " + ", ".join(sorted(set(minimal_fillers))[:4]))
    if not tasks:
        return "needs broader context before phonetic testing"
    return "; ".join(tasks)


def model(args: argparse.Namespace) -> None:
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    markers = load_markers(Path(args.title_candidates), args.marker_threshold, args.marker_limit)
    slots = load_slots(Path(args.slot_frames), args.slot_threshold, args.slot_limit)
    name_blocks = load_name_blocks(Path(args.name_candidates), args.name_threshold, args.max_formula_risk, args.name_limit)
    max_name_len = max((len(key) for key in name_blocks), default=2)

    final_rows = read_csv(Path(args.final_signs))
    initial_rows = read_csv(Path(args.initial_signs))
    final_signs = {
        row["FinalSign"]: row
        for row in final_rows
        if fint(row.get("DistinctStems")) >= args.final_stem_threshold and row.get("RoleLead") == "HIGH_REUSE_FINAL_MODIFIER"
    }
    initial_signs = {
        row["InitialSign"]: row
        for row in initial_rows
        if fint(row.get("DistinctRemainders")) >= args.initial_remainder_threshold and row.get("RoleLead") == "HIGH_REUSE_INITIAL_MODIFIER"
    }

    cross_rows = read_csv(Path(args.cross_frame_reuse))
    cross_fillers = {
        row["Filler"]: row
        for row in cross_rows
        if fint(row.get("FrameCount")) >= args.cross_frame_threshold or fint(row.get("TotalCount")) >= args.cross_count_threshold
    }
    minimal_rows = read_csv(Path(args.minimal_pairs))
    minimal_fillers: dict[str, list[str]] = defaultdict(list)
    for row in minimal_rows:
        if fint(row.get("CombinedCount")) < args.minimal_pair_count:
            continue
        minimal_fillers[row["FillerA"]].append(row["Relation"])
        minimal_fillers[row["FillerB"]].append(row["Relation"])

    sign_gloss_rows: list[dict[str, object]] = []
    all_signs = sorted(set(markers) | set(final_signs) | set(initial_signs))
    for sign in all_signs:
        marker = markers.get(sign)
        final = final_signs.get(sign)
        initial = initial_signs.get(sign)
        evidence: list[str] = []
        labels: list[str] = []
        if marker:
            labels.append(marker.role)
            evidence.append(f"title_score={marker.score:.3f}; start={marker.start_pct:.3f}; end={marker.end_pct:.3f}")
        if final:
            labels.append("SLOT_FINAL_MODIFIER")
            evidence.append(f"final_stems={final.get('DistinctStems')}; final_frames={final.get('FrameCount')}")
        if initial:
            labels.append("SLOT_INITIAL_MODIFIER")
            evidence.append(f"initial_remainders={initial.get('DistinctRemainders')}; initial_frames={initial.get('FrameCount')}")
        proto_gloss = " / ".join(labels)
        sign_gloss_rows.append(
            {
                "Sign": sign,
                "ProtoGloss": proto_gloss,
                "Evidence": "; ".join(evidence),
                "PhoneticStatus": "No phonetic value assigned",
            }
        )

    reconstruction_rows: list[dict[str, object]] = []
    template_counter: Counter[str] = Counter()
    frame_counter: Counter[str] = Counter()
    semantic_counter: Counter[str] = Counter()
    high_readiness_rows: list[dict[str, object]] = []

    with Path(args.corpus_path).open(newline="", encoding="utf-8-sig") as handle:
        for row in csv.DictReader(handle):
            tokens = [token for token in sign_tokens(row.get("text")) if token not in {"000", "999"}]
            tokens.reverse()
            if not tokens:
                continue

            all_slot_segments: list[tuple[int, int, tuple[str, ...], Slot]] = []
            for slot in slots:
                all_slot_segments.extend(extract_segments(tokens, slot, args.max_filler_length))
            slot_segments = non_overlapping_segments(all_slot_segments)
            slot_positions = set()
            for start, end, _filler, _slot in slot_segments:
                slot_positions.update(range(start, end))
            name_matches = [
                match
                for match in find_ngram_matches(tokens, name_blocks, max_name_len)
                if not (set(range(match[0], match[1])) & slot_positions)
            ]

            roles: list[list[str]] = [[] for _ in tokens]
            marker_count = 0
            for i, token in enumerate(tokens):
                marker = markers.get(token)
                if marker:
                    roles[i].append(marker.role)
                    marker_count += 1
                if token in final_signs and "SLOT_FINAL_MODIFIER" not in roles[i]:
                    roles[i].append("SLOT_FINAL_MODIFIER")
                if token in initial_signs and "SLOT_INITIAL_MODIFIER" not in roles[i]:
                    roles[i].append("SLOT_INITIAL_MODIFIER")
                if not roles[i]:
                    roles[i].append("SIGN")

            frame_names: list[str] = []
            slot_fillers: list[str] = []
            cross_evidence: list[str] = []
            minimal_evidence: list[str] = []
            for start, end, filler, slot in slot_segments:
                filler_text = join_tokens(filler)
                frame_names.append(slot.frame)
                slot_fillers.append(f"{slot.frame}:{filler_text}@{start + 1}-{end}")
                for pos in range(start, end):
                    label = "PRIME_ENTITY_SLOT_FILLER" if slot.frame == "002|740" else "SLOT_FILLER"
                    if label not in roles[pos]:
                        roles[pos].insert(0, label)
                cross = cross_fillers.get(filler_text)
                if cross:
                    cross_evidence.append(filler_text)
                if filler_text in minimal_fillers:
                    minimal_evidence.append(filler_text)
                frame_counter[slot.frame] += 1

            name_labels: list[str] = []
            for start, end, ngram, block in name_matches:
                label = join_tokens(ngram)
                name_labels.append(f"{label}@{start + 1}-{end}")
                for pos in range(start, end):
                    if "NAME_LIKE_BLOCK" not in roles[pos]:
                        roles[pos].insert(0, "NAME_LIKE_BLOCK")

            structural_parse, structural_template = build_structural_parse(tokens, roles, slot_segments, name_matches)
            has_initial = any(role.startswith("INITIAL") for token_roles in roles for role in token_roles)
            has_terminal = any(role.startswith("TERMINAL") for token_roles in roles for role in token_roles)
            has_prime_slot = any(slot.frame == "002|740" for _s, _e, _f, slot in slot_segments)
            has_slot = bool(slot_segments)
            has_name = bool(name_matches)
            semantic_frame, semantic_options = semantic_candidates(row, has_prime_slot, has_slot, has_initial, has_terminal, has_name)
            semantic_counter[semantic_frame] += 1
            template_counter[structural_template] += 1
            score = confidence_score(row, slot_segments, name_matches, marker_count, len(cross_evidence), len(minimal_evidence))
            readiness = readiness_label(score)
            phonetic_plan = context_plan(frame_names, cross_evidence, minimal_evidence)

            rec = {
                "TextId": row.get("id", ""),
                "CISI": row.get("cisi", ""),
                "Region": row.get("region", ""),
                "Site": row.get("site", ""),
                "Type": row.get("type", ""),
                "Symbol": row.get("symbol", ""),
                "Material": row.get("material", ""),
                "Complete": row.get("complete", ""),
                "Direction": row.get("dir.", ""),
                "RawText": row.get("text", ""),
                "ReadingTokens": join_tokens(tokens),
                "StructuralParse": structural_parse,
                "StructuralTemplate": structural_template,
                "SemanticFrame": semantic_frame,
                "SemanticOptions": semantic_options,
                "SlotFillers": "; ".join(slot_fillers),
                "NameLikeBlocks": "; ".join(name_labels),
                "CrossFrameReuse": "; ".join(sorted(set(cross_evidence))),
                "MinimalPairEvidence": "; ".join(sorted(set(minimal_evidence))),
                "ReconstructionConfidence": score,
                "PhoneticReadiness": readiness,
                "NextTest": phonetic_plan,
            }
            reconstruction_rows.append(rec)
            if readiness in {"High", "Medium"}:
                high_readiness_rows.append(rec)

    template_rows = [
        {"StructuralTemplate": template, "Count": count}
        for template, count in template_counter.most_common()
    ]
    semantic_rows = [
        {"SemanticFrame": frame, "Count": count}
        for frame, count in semantic_counter.most_common()
    ]
    frame_rows = [
        {"Frame": frame, "OccurrencesInReconstruction": count}
        for frame, count in frame_counter.most_common()
    ]

    phonetic_rows: list[dict[str, object]] = []
    for row in sorted(high_readiness_rows, key=lambda item: (-ffloat(str(item["ReconstructionConfidence"])), item["TextId"]))[: args.phonetic_limit]:
        phonetic_rows.append(
            {
                "TextId": row["TextId"],
                "CISI": row["CISI"],
                "Site": row["Site"],
                "Type": row["Type"],
                "ReadingTokens": row["ReadingTokens"],
                "SemanticFrame": row["SemanticFrame"],
                "SlotFillers": row["SlotFillers"],
                "CrossFrameReuse": row["CrossFrameReuse"],
                "MinimalPairEvidence": row["MinimalPairEvidence"],
                "ReconstructionConfidence": row["ReconstructionConfidence"],
                "NextTest": row["NextTest"],
            }
        )

    summary_rows = [
        {"Metric": "Texts reconstructed", "Value": len(reconstruction_rows), "Note": "All analyzable non-empty inscriptions."},
        {"Metric": "Structural templates", "Value": len(template_rows), "Note": "Distinct role templates after slot/name compression."},
        {"Metric": "Semantic frames", "Value": len(semantic_rows), "Note": "Competing high-level semantic interpretations."},
        {"Metric": "Medium/high phonetic-readiness texts", "Value": len(high_readiness_rows), "Note": "Rows with enough structural evidence for image/context review."},
        {"Metric": "Sign proto-glosses", "Value": len(sign_gloss_rows), "Note": "Functional labels only; no phonetic values assigned."},
        {"Metric": "Productive frames used", "Value": len(slots), "Note": f"slot score >= {args.slot_threshold}."},
        {"Metric": "Name-like blocks used", "Value": len(name_blocks), "Note": f"name score >= {args.name_threshold}."},
        {"Metric": "Cross-frame filler leads", "Value": len(cross_fillers), "Note": "Reusable fillers for phonetic testing."},
    ]

    paths = {
        "summary": out_dir / "structural_reconstruction_summary.csv",
        "reconstructions": out_dir / "structural_reconstructions.csv",
        "templates": out_dir / "structural_reconstruction_templates.csv",
        "semantic": out_dir / "structural_semantic_frames.csv",
        "phonetic": out_dir / "phonetic_bootstrap_candidates.csv",
        "glosses": out_dir / "sign_proto_glosses.csv",
        "frames": out_dir / "structural_frame_usage.csv",
        "tex": out_dir / "structural_reconstruction_model.tex",
    }

    write_csv(paths["summary"], summary_rows, ["Metric", "Value", "Note"])
    write_csv(
        paths["reconstructions"],
        sorted(reconstruction_rows, key=lambda item: (-ffloat(str(item["ReconstructionConfidence"])), item["TextId"])),
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
            "RawText",
            "ReadingTokens",
            "StructuralParse",
            "StructuralTemplate",
            "SemanticFrame",
            "SemanticOptions",
            "SlotFillers",
            "NameLikeBlocks",
            "CrossFrameReuse",
            "MinimalPairEvidence",
            "ReconstructionConfidence",
            "PhoneticReadiness",
            "NextTest",
        ],
    )
    write_csv(paths["templates"], template_rows, ["StructuralTemplate", "Count"])
    write_csv(paths["semantic"], semantic_rows, ["SemanticFrame", "Count"])
    write_csv(paths["phonetic"], phonetic_rows, ["TextId", "CISI", "Site", "Type", "ReadingTokens", "SemanticFrame", "SlotFillers", "CrossFrameReuse", "MinimalPairEvidence", "ReconstructionConfidence", "NextTest"])
    write_csv(paths["glosses"], sign_gloss_rows, ["Sign", "ProtoGloss", "Evidence", "PhoneticStatus"])
    write_csv(paths["frames"], frame_rows, ["Frame", "OccurrencesInReconstruction"])

    top_recon = sorted(reconstruction_rows, key=lambda item: (-ffloat(str(item["ReconstructionConfidence"])), item["TextId"]))[:10]
    top_glosses = sorted(sign_gloss_rows, key=lambda item: item["Sign"])[:18]
    top_templates = template_rows[:10]
    top_semantic = semantic_rows[:8]

    lines: list[str] = [
        r"\documentclass[11pt,a4paper]{article}",
        r"\usepackage[margin=1in]{geometry}",
        r"\usepackage[T1]{fontenc}",
        r"\usepackage[utf8]{inputenc}",
        r"\usepackage{booktabs}",
        r"\begin{document}",
        r"\section*{Structural Reconstruction Model}",
        "This report reconstructs inscription-level formulae as structural parses, semantic frame hypotheses, and phonetic-readiness test beds. It stays pre-phonetic: all glosses are functional constraints.",
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
            r"\subsection*{Semantic Frame Counts}",
            r"\begin{center}",
            r"\begin{tabular}{lr}",
            r"\toprule",
            r"\textbf{Frame} & \textbf{Count} \\",
            r"\midrule",
        ]
    )
    for row in top_semantic:
        lines.append(f"{latex_escape(row['SemanticFrame'])} & {latex_escape(row['Count'])} \\\\")
    lines.extend(
        [
            r"\bottomrule",
            r"\end{tabular}",
            r"\end{center}",
            r"\subsection*{Top Structural Templates}",
            r"\begin{center}",
            r"\begin{tabular}{p{0.64\textwidth}r}",
            r"\toprule",
            r"\textbf{Template} & \textbf{Count} \\",
            r"\midrule",
        ]
    )
    for row in top_templates:
        lines.append(f"{latex_escape(row['StructuralTemplate'])} & {latex_escape(row['Count'])} \\\\")
    lines.extend(
        [
            r"\bottomrule",
            r"\end{tabular}",
            r"\end{center}",
            r"\subsection*{Example Proto-Glosses}",
            r"\begin{center}",
            r"\begin{tabular}{lp{0.70\textwidth}}",
            r"\toprule",
            r"\textbf{Sign} & \textbf{Functional proto-gloss} \\",
            r"\midrule",
        ]
    )
    for row in top_glosses:
        lines.append(f"{latex_escape(row['Sign'])} & {latex_escape(row['ProtoGloss'])} \\\\")
    lines.extend(
        [
            r"\bottomrule",
            r"\end{tabular}",
            r"\end{center}",
            r"\subsection*{High-Readiness Reconstruction Examples}",
            r"\begin{center}",
            r"\begin{tabular}{llllp{0.44\textwidth}}",
            r"\toprule",
            r"\textbf{Text} & \textbf{CISI} & \textbf{Site} & \textbf{Frame} & \textbf{Structural parse} \\",
            r"\midrule",
        ]
    )
    for row in top_recon:
        values = [row["TextId"], row["CISI"], row["Site"], row["SemanticFrame"], row["StructuralParse"]]
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
    for key in ["summary", "reconstructions", "templates", "semantic", "phonetic", "glosses", "frames"]:
        lines.append(r"\item \texttt{" + latex_escape(paths[key]) + "}")
    lines.extend([r"\end{itemize}", r"\end{document}"])
    paths["tex"].write_text("\n".join(lines) + "\n", encoding="utf-8")

    for path in paths.values():
        print(f"Wrote {path}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--corpus-path", default="data/ivs_corpus_cleaned.csv")
    parser.add_argument("--title-candidates", default="outputs/onomastic_title_marker_candidates.csv")
    parser.add_argument("--slot-frames", default="outputs/slot_paradigm_frames.csv")
    parser.add_argument("--name-candidates", default="outputs/onomastic_anchor_ngram_candidates.csv")
    parser.add_argument("--final-signs", default="outputs/slot_paradigm_final_signs.csv")
    parser.add_argument("--initial-signs", default="outputs/slot_paradigm_initial_signs.csv")
    parser.add_argument("--cross-frame-reuse", default="outputs/slot_paradigm_cross_frame_reuse.csv")
    parser.add_argument("--minimal-pairs", default="outputs/slot_paradigm_minimal_pairs.csv")
    parser.add_argument("--out-dir", default="outputs")
    parser.add_argument("--marker-threshold", type=float, default=0.78)
    parser.add_argument("--marker-limit", type=int, default=24)
    parser.add_argument("--slot-threshold", type=float, default=0.91)
    parser.add_argument("--slot-limit", type=int, default=20)
    parser.add_argument("--name-threshold", type=float, default=0.90)
    parser.add_argument("--max-formula-risk", type=float, default=0.66)
    parser.add_argument("--name-limit", type=int, default=80)
    parser.add_argument("--max-filler-length", type=int, default=5)
    parser.add_argument("--final-stem-threshold", type=int, default=30)
    parser.add_argument("--initial-remainder-threshold", type=int, default=30)
    parser.add_argument("--cross-frame-threshold", type=int, default=5)
    parser.add_argument("--cross-count-threshold", type=int, default=12)
    parser.add_argument("--minimal-pair-count", type=int, default=10)
    parser.add_argument("--phonetic-limit", type=int, default=120)
    return parser.parse_args()


if __name__ == "__main__":
    model(parse_args())
