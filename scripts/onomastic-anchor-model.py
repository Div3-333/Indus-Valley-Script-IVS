#!/usr/bin/env python3
"""Score Indus sign n-grams for onomastic anchor hypotheses.

The model is deliberately conservative: it finds repeated name-like blocks,
possible title/classifier markers, and formula frames that may contain variable
fillers. It does not assign readings.
"""

from __future__ import annotations

import argparse
import csv
import math
import re
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path


TOKEN_RE = re.compile(r"(?<!\d)\d{3,4}(?!\d)")
MISSING_VALUES = {"", "-", "--", "- -", "?", "??", "none", "None"}
BOUNDARY_START = "<START>"
BOUNDARY_END = "<END>"


@dataclass
class NGramRecord:
    key: str
    length: int
    count: int = 0
    texts: set[str] = field(default_factory=set)
    regions: Counter[str] = field(default_factory=Counter)
    sites: Counter[str] = field(default_factory=Counter)
    types: Counter[str] = field(default_factory=Counter)
    directions: Counter[str] = field(default_factory=Counter)
    complete: Counter[str] = field(default_factory=Counter)
    left: Counter[str] = field(default_factory=Counter)
    right: Counter[str] = field(default_factory=Counter)
    frames: Counter[str] = field(default_factory=Counter)
    position_bins: Counter[str] = field(default_factory=Counter)
    start_count: int = 0
    end_count: int = 0
    whole_text_count: int = 0
    internal_count: int = 0
    seal_count: int = 0
    complete_y_count: int = 0
    examples: list[str] = field(default_factory=list)


@dataclass
class FrameRecord:
    left: str
    right: str
    count: int = 0
    fillers: Counter[str] = field(default_factory=Counter)
    regions: Counter[str] = field(default_factory=Counter)
    sites: Counter[str] = field(default_factory=Counter)
    types: Counter[str] = field(default_factory=Counter)
    seal_count: int = 0
    complete_y_count: int = 0
    examples: list[str] = field(default_factory=list)


def sign_tokens(text: str | None) -> list[str]:
    return TOKEN_RE.findall(text or "")


def is_missing(value: str | None) -> bool:
    if value is None:
        return True
    return value.strip() in MISSING_VALUES


def add_count(counter: Counter[str], value: str | None, increment: int = 1) -> None:
    if is_missing(value):
        return
    counter[str(value).strip()] += increment


def clamp01(value: float) -> float:
    return max(0.0, min(1.0, value))


def entropy(counter: Counter[str]) -> float:
    total = sum(counter.values())
    if total <= 0:
        return 0.0
    value = 0.0
    for count in counter.values():
        if count <= 0:
            continue
        p = count / total
        value -= p * math.log2(p)
    return value


def normalized_entropy(counter: Counter[str]) -> float:
    if len(counter) <= 1:
        return 0.0
    return round(entropy(counter) / math.log2(len(counter)), 4)


def dominant_key(counter: Counter[str]) -> str:
    if not counter:
        return ""
    return counter.most_common(1)[0][0]


def dominant_share(counter: Counter[str]) -> float:
    total = sum(counter.values())
    if total <= 0:
        return 0.0
    return round(counter.most_common(1)[0][1] / total, 4)


def high_frequency_score(count: int) -> float:
    if count <= 0:
        return 0.0
    return round(clamp01(math.log(count + 1) / math.log(250)), 4)


def mid_frequency_score(count: int) -> float:
    if count < 2:
        return 0.0
    rise = clamp01(math.log(count) / math.log(12))
    penalty = 1.0
    if count > 60:
        penalty = max(0.15, 1.0 - ((count - 60) / 220.0))
    return round(clamp01(rise * penalty), 4)


def name_length_score(length: int) -> float:
    return {2: 0.95, 3: 1.0, 4: 0.9, 5: 0.7}.get(length, 0.0)


def title_length_score(length: int) -> float:
    return {1: 1.0, 2: 0.7}.get(length, 0.1)


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


def write_csv(path: Path, rows: list[dict[str, object]], fieldnames: list[str]) -> None:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def model(args: argparse.Namespace) -> None:
    corpus_path = Path(args.corpus_path)
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    ngrams: dict[str, NGramRecord] = {}
    frames: dict[str, FrameRecord] = {}
    text_total = 0
    complete_text_total = 0

    with corpus_path.open(newline="", encoding="utf-8-sig") as handle:
        for row in csv.DictReader(handle):
            tokens = [token for token in sign_tokens(row.get("text")) if token not in {"000", "999"}]
            tokens.reverse()
            text_length = len(tokens)
            if text_length == 0:
                continue

            text_total += 1
            is_complete = row.get("complete") == "Y"
            if is_complete:
                complete_text_total += 1
            type_value = row.get("type") or ""
            is_seal = type_value.startswith("SEAL")

            for start in range(text_length):
                parts: list[str] = []
                max_length_here = min(args.max_ngram_length, text_length - start)
                for n in range(1, max_length_here + 1):
                    parts.append(tokens[start + n - 1])
                    key = "-".join(parts)
                    rec = ngrams.setdefault(key, NGramRecord(key=key, length=n))
                    rec.count += 1
                    rec.texts.add(row.get("id") or "")
                    add_count(rec.regions, row.get("region"))
                    add_count(rec.sites, row.get("site"))
                    add_count(rec.types, type_value)
                    add_count(rec.directions, row.get("dir."))
                    add_count(rec.complete, row.get("complete"))

                    left = BOUNDARY_START if start == 0 else tokens[start - 1]
                    right = BOUNDARY_END if start + n == text_length else tokens[start + n]
                    frame_key = f"{left}|{right}"
                    add_count(rec.left, left)
                    add_count(rec.right, right)
                    add_count(rec.frames, frame_key)

                    midpoint = start + ((n - 1) / 2.0)
                    bin_index = math.ceil(((midpoint + 1) / text_length) * 10.0)
                    bin_index = max(1, min(10, bin_index))
                    add_count(rec.position_bins, str(bin_index))

                    if start == 0:
                        rec.start_count += 1
                    if start + n == text_length:
                        rec.end_count += 1
                    if start == 0 and start + n == text_length:
                        rec.whole_text_count += 1
                    if start > 0 and start + n < text_length:
                        rec.internal_count += 1
                    if is_seal:
                        rec.seal_count += 1
                    if is_complete:
                        rec.complete_y_count += 1
                    if len(rec.examples) < 5:
                        rec.examples.append(f"{row.get('id')}/{row.get('cisi')}/{row.get('site')}")

                    frame = frames.setdefault(frame_key, FrameRecord(left=left, right=right))
                    frame.count += 1
                    add_count(frame.fillers, key)
                    add_count(frame.regions, row.get("region"))
                    add_count(frame.sites, row.get("site"))
                    add_count(frame.types, type_value)
                    if is_seal:
                        frame.seal_count += 1
                    if is_complete:
                        frame.complete_y_count += 1
                    if len(frame.examples) < 5:
                        frame.examples.append(f"{row.get('id')}/{row.get('cisi')}/{row.get('site')}")

    candidate_rows: list[dict[str, object]] = []
    for rec in ngrams.values():
        if rec.count < args.min_candidate_count:
            continue

        count = rec.count
        start_pct = round(rec.start_count / count, 4)
        end_pct = round(rec.end_count / count, 4)
        whole_pct = round(rec.whole_text_count / count, 4)
        internal_pct = round(rec.internal_count / count, 4)
        seal_pct = round(rec.seal_count / count, 4)
        complete_pct = round(rec.complete_y_count / count, 4)
        left_share = dominant_share(rec.left)
        right_share = dominant_share(rec.right)
        frame_share = dominant_share(rec.frames)
        context_consistency = max(frame_share, left_share, right_share)
        left_entropy = normalized_entropy(rec.left)
        right_entropy = normalized_entropy(rec.right)
        neighbor_diversity = round((left_entropy + right_entropy) / 2.0, 4)
        position_entropy = normalized_entropy(rec.position_bins)
        position_fixedness = max(whole_pct, start_pct, end_pct)
        site_share = dominant_share(rec.sites)
        region_share = dominant_share(rec.regions)
        site_spread = clamp01(len(rec.sites) / 8.0)
        region_spread = clamp01(len(rec.regions) / 4.0)
        mid_freq = mid_frequency_score(count)
        high_freq = high_frequency_score(count)
        name_length = name_length_score(rec.length)
        title_length = title_length_score(rec.length)

        name_score = clamp01(
            (0.20 * mid_freq)
            + (0.18 * name_length)
            + (0.18 * context_consistency)
            + (0.14 * position_fixedness)
            + (0.12 * complete_pct)
            + (0.08 * seal_pct)
            + (0.05 * site_share)
            + (0.05 * region_share)
        )

        title_score = clamp01(
            (0.28 * high_freq)
            + (0.22 * title_length)
            + (0.18 * position_fixedness)
            + (0.17 * neighbor_diversity)
            + (0.10 * seal_pct)
            + (0.05 * complete_pct)
        )

        cross_site_score = clamp01(
            (0.35 * name_score)
            + (0.20 * site_spread)
            + (0.20 * region_spread)
            + (0.15 * context_consistency)
            + (0.10 * seal_pct)
        )

        formula_risk = clamp01(
            (0.35 * high_freq)
            + (0.20 * position_fixedness)
            + (0.20 * context_consistency)
            + (0.15 * whole_pct)
            + (0.10 * (1.0 - name_length))
        )

        working_class = "UnclassifiedOnomasticLead"
        if title_score >= 0.78 and rec.length <= 2:
            working_class = "TitleOrClassifierMarkerCandidate"
        elif name_score >= 0.85 and rec.length >= 2:
            working_class = "RepeatedNameLikeBlockCandidate"
        elif cross_site_score >= 0.75 and rec.length >= 2:
            working_class = "CrossSiteNameAnchorCandidate"
        elif formula_risk >= 0.72:
            working_class = "FormulaChunkCandidate"

        candidate_rows.append(
            {
                "NGram": rec.key,
                "Length": rec.length,
                "Count": count,
                "TextCount": len(rec.texts),
                "SiteCount": len(rec.sites),
                "RegionCount": len(rec.regions),
                "TypeCount": len(rec.types),
                "StartPct": start_pct,
                "EndPct": end_pct,
                "WholeTextPct": whole_pct,
                "InternalPct": internal_pct,
                "PositionEntropy10": position_entropy,
                "DominantLeft": dominant_key(rec.left),
                "DominantLeftShare": left_share,
                "DominantRight": dominant_key(rec.right),
                "DominantRightShare": right_share,
                "DominantFrame": dominant_key(rec.frames),
                "DominantFrameShare": frame_share,
                "LeftEntropy": left_entropy,
                "RightEntropy": right_entropy,
                "NeighborDiversity": neighbor_diversity,
                "DominantSite": dominant_key(rec.sites),
                "DominantSiteShare": site_share,
                "DominantRegion": dominant_key(rec.regions),
                "DominantRegionShare": region_share,
                "SealPct": seal_pct,
                "CompletePct": complete_pct,
                "NameAnchorScore": round(name_score, 4),
                "TitleMarkerScore": round(title_score, 4),
                "CrossSiteAnchorScore": round(cross_site_score, 4),
                "FormulaRiskScore": round(formula_risk, 4),
                "WorkingClass": working_class,
                "Examples": "; ".join(rec.examples),
            }
        )

    frame_rows: list[dict[str, object]] = []
    for frame_key, frame in frames.items():
        if frame.count < 5 or len(frame.fillers) < 2:
            continue

        count = frame.count
        freq_score = high_frequency_score(count)
        distinct_score = clamp01(len(frame.fillers) / 12.0)
        filler_entropy = normalized_entropy(frame.fillers)
        seal_pct = round(frame.seal_count / count, 4)
        complete_pct = round(frame.complete_y_count / count, 4)
        boundary_penalty = 0.25 if frame.left == BOUNDARY_START and frame.right == BOUNDARY_END else 1.0
        slot_score = clamp01(
            boundary_penalty
            * (
                (0.25 * freq_score)
                + (0.30 * distinct_score)
                + (0.25 * filler_entropy)
                + (0.10 * seal_pct)
                + (0.10 * complete_pct)
            )
        )

        frame_rows.append(
            {
                "Frame": frame_key,
                "Left": frame.left,
                "Right": frame.right,
                "Count": count,
                "DistinctFillers": len(frame.fillers),
                "TopFiller": dominant_key(frame.fillers),
                "TopFillerShare": dominant_share(frame.fillers),
                "FillerEntropy": filler_entropy,
                "SiteCount": len(frame.sites),
                "RegionCount": len(frame.regions),
                "TypeCount": len(frame.types),
                "SealPct": seal_pct,
                "CompletePct": complete_pct,
                "NameSlotScore": round(slot_score, 4),
                "Examples": "; ".join(frame.examples),
            }
        )

    ngram_path = out_dir / "onomastic_anchor_ngram_candidates.csv"
    title_path = out_dir / "onomastic_title_marker_candidates.csv"
    slot_path = out_dir / "onomastic_formula_slots.csv"
    summary_path = out_dir / "onomastic_anchor_summary.csv"
    tex_path = out_dir / "onomastic_anchor_model.tex"

    candidate_fields = [
        "NGram",
        "Length",
        "Count",
        "TextCount",
        "SiteCount",
        "RegionCount",
        "TypeCount",
        "StartPct",
        "EndPct",
        "WholeTextPct",
        "InternalPct",
        "PositionEntropy10",
        "DominantLeft",
        "DominantLeftShare",
        "DominantRight",
        "DominantRightShare",
        "DominantFrame",
        "DominantFrameShare",
        "LeftEntropy",
        "RightEntropy",
        "NeighborDiversity",
        "DominantSite",
        "DominantSiteShare",
        "DominantRegion",
        "DominantRegionShare",
        "SealPct",
        "CompletePct",
        "NameAnchorScore",
        "TitleMarkerScore",
        "CrossSiteAnchorScore",
        "FormulaRiskScore",
        "WorkingClass",
        "Examples",
    ]
    frame_fields = [
        "Frame",
        "Left",
        "Right",
        "Count",
        "DistinctFillers",
        "TopFiller",
        "TopFillerShare",
        "FillerEntropy",
        "SiteCount",
        "RegionCount",
        "TypeCount",
        "SealPct",
        "CompletePct",
        "NameSlotScore",
        "Examples",
    ]
    summary_rows = [
        {"Metric": "Analyzable texts", "Value": text_total, "Note": "Texts with at least one non-eroded, non-blank sign."},
        {"Metric": "Complete analyzable texts", "Value": complete_text_total, "Note": "Texts marked complete=Y."},
        {"Metric": "Candidate ngrams", "Value": len(candidate_rows), "Note": f"Repeated ngrams with count at least {args.min_candidate_count}."},
        {
            "Metric": "Title/classifier candidates",
            "Value": sum(row["WorkingClass"] == "TitleOrClassifierMarkerCandidate" for row in candidate_rows),
            "Note": "Length 1-2 ngrams with strong title-marker score.",
        },
        {
            "Metric": "Repeated name-like candidates",
            "Value": sum(row["WorkingClass"] == "RepeatedNameLikeBlockCandidate" for row in candidate_rows),
            "Note": "Length 2-5 repeated blocks with strong name-anchor score.",
        },
        {
            "Metric": "Cross-site name-anchor candidates",
            "Value": sum(row["WorkingClass"] == "CrossSiteNameAnchorCandidate" for row in candidate_rows),
            "Note": "Repeated blocks with broader site/region spread.",
        },
        {"Metric": "Formula slot candidates", "Value": len(frame_rows), "Note": "Immediate frames with multiple fillers."},
    ]

    write_csv(
        ngram_path,
        sorted(
            candidate_rows,
            key=lambda row: (-float(row["NameAnchorScore"]), -float(row["CrossSiteAnchorScore"]), -int(row["Count"])),
        ),
        candidate_fields,
    )
    write_csv(
        title_path,
        sorted(
            [row for row in candidate_rows if int(row["Length"]) <= 2],
            key=lambda row: (-float(row["TitleMarkerScore"]), -int(row["Count"])),
        ),
        candidate_fields,
    )
    write_csv(
        slot_path,
        sorted(frame_rows, key=lambda row: (-float(row["NameSlotScore"]), -int(row["DistinctFillers"]))),
        frame_fields,
    )
    write_csv(summary_path, summary_rows, ["Metric", "Value", "Note"])

    top_names = sorted(
        [
            row
            for row in candidate_rows
            if int(row["Length"]) >= 2 and row["WorkingClass"] != "TitleOrClassifierMarkerCandidate"
        ],
        key=lambda row: (-float(row["NameAnchorScore"]), float(row["FormulaRiskScore"])),
    )[:12]
    top_titles = sorted(
        [row for row in candidate_rows if int(row["Length"]) <= 2],
        key=lambda row: (-float(row["TitleMarkerScore"]), -int(row["Count"])),
    )[:12]
    top_slots = sorted(frame_rows, key=lambda row: (-float(row["NameSlotScore"]), -int(row["DistinctFillers"])))[:12]

    lines: list[str] = [
        r"\documentclass[11pt,a4paper]{article}",
        r"\usepackage[margin=1in]{geometry}",
        r"\usepackage[T1]{fontenc}",
        r"\usepackage[utf8]{inputenc}",
        r"\usepackage{booktabs}",
        r"\begin{document}",
        r"\section*{Onomastic Anchor Model}",
        "This report turns the Linear-Elamite-style proper-name strategy into an internal Indus test: find repeated name-like blocks, possible titles/classifiers, and formula frames with variable fillers. These are anchor candidates only, not readings.",
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
            r"\subsection*{Top Name-Like Blocks}",
            r"\begin{center}",
            r"\begin{tabular}{lrrrr}",
            r"\toprule",
            r"\textbf{Ngram} & \textbf{Count} & \textbf{Sites} & \textbf{Name} & \textbf{Formula risk} \\",
            r"\midrule",
        ]
    )
    for row in top_names:
        values = [row["NGram"], row["Count"], row["SiteCount"], row["NameAnchorScore"], row["FormulaRiskScore"]]
        lines.append(" & ".join(latex_escape(value) for value in values) + r" \\")
    lines.extend(
        [
            r"\bottomrule",
            r"\end{tabular}",
            r"\end{center}",
            r"\subsection*{Top Title or Classifier Markers}",
            r"\begin{center}",
            r"\begin{tabular}{lrrrr}",
            r"\toprule",
            r"\textbf{Ngram} & \textbf{Count} & \textbf{Sites} & \textbf{Title} & \textbf{Diversity} \\",
            r"\midrule",
        ]
    )
    for row in top_titles:
        values = [row["NGram"], row["Count"], row["SiteCount"], row["TitleMarkerScore"], row["NeighborDiversity"]]
        lines.append(" & ".join(latex_escape(value) for value in values) + r" \\")
    lines.extend(
        [
            r"\bottomrule",
            r"\end{tabular}",
            r"\end{center}",
            r"\subsection*{Top Variable Formula Slots}",
            r"\begin{center}",
            r"\begin{tabular}{llrrr}",
            r"\toprule",
            r"\textbf{Left} & \textbf{Right} & \textbf{Count} & \textbf{Fillers} & \textbf{Slot} \\",
            r"\midrule",
        ]
    )
    for row in top_slots:
        values = [row["Left"], row["Right"], row["Count"], row["DistinctFillers"], row["NameSlotScore"]]
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
    for path in [ngram_path, title_path, slot_path, summary_path]:
        lines.append(r"\item \texttt{" + latex_escape(path) + "}")
    lines.extend([r"\end{itemize}", r"\end{document}"])
    tex_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    for path in [ngram_path, title_path, slot_path, summary_path, tex_path]:
        print(f"Wrote {path}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--corpus-path", default="data/ivs_corpus_cleaned.csv")
    parser.add_argument("--out-dir", default="outputs")
    parser.add_argument("--max-ngram-length", type=int, default=5)
    parser.add_argument("--min-candidate-count", type=int, default=2)
    return parser.parse_args()


if __name__ == "__main__":
    model(parse_args())
