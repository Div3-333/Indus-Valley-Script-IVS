#!/usr/bin/env python3
"""Extract productive slot paradigms for proto-decipherment.

This stage asks a sharper question than "which signs are common?": when a
stable frame such as 002 _ 740 admits many fillers, do those fillers show
stem/final-sign paradigms, cross-frame reuse, or minimal alternations?
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


@dataclass(frozen=True)
class Slot:
    frame: str
    left: str
    right: str
    score: float
    count: int
    distinct_fillers: int


@dataclass
class FillerStats:
    frame: str
    left: str
    right: str
    filler: tuple[str, ...]
    count: int = 0
    texts: set[str] = field(default_factory=set)
    regions: Counter[str] = field(default_factory=Counter)
    sites: Counter[str] = field(default_factory=Counter)
    types: Counter[str] = field(default_factory=Counter)
    symbols: Counter[str] = field(default_factory=Counter)
    materials: Counter[str] = field(default_factory=Counter)
    complete: Counter[str] = field(default_factory=Counter)
    examples: list[str] = field(default_factory=list)


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


def add_count(counter: Counter[str], value: str | None) -> None:
    if value is None:
        return
    clean = value.strip()
    if clean and clean not in {"-", "--", "- -", "?", "??"}:
        counter[clean] += 1


def dominant(counter: Counter[str]) -> tuple[str, float]:
    total = sum(counter.values())
    if total <= 0:
        return "", 0.0
    key, count = counter.most_common(1)[0]
    return key, round(count / total, 4)


def entropy(counter: Counter[str]) -> float:
    total = sum(counter.values())
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
    return round(entropy(counter) / math.log2(len(counter)), 4)


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


def load_slots(path: Path, threshold: float, limit: int) -> list[Slot]:
    slots: list[Slot] = []
    for row in read_csv(path):
        score = ffloat(row.get("NameSlotScore"))
        if score < threshold:
            continue
        slots.append(
            Slot(
                frame=row["Frame"],
                left=row["Left"],
                right=row["Right"],
                score=score,
                count=fint(row.get("Count")),
                distinct_fillers=fint(row.get("DistinctFillers")),
            )
        )
    slots.sort(key=lambda item: (-item.score, -item.distinct_fillers, -item.count, item.frame))
    return slots[:limit]


def extract_segments(tokens: list[str], slot: Slot, max_len: int) -> list[tuple[int, int, tuple[str, ...]]]:
    """Return (start_index, end_index_exclusive, filler_tokens)."""
    segments: list[tuple[int, int, tuple[str, ...]]] = []
    n = len(tokens)
    if n < 2:
        return segments

    if slot.left == START and slot.right == END:
        if 1 <= n <= max_len:
            segments.append((0, n, tuple(tokens)))
        return segments

    if slot.left == START:
        for right_index in range(1, min(n, max_len + 1)):
            if tokens[right_index] == slot.right:
                filler = tuple(tokens[0:right_index])
                if filler:
                    segments.append((0, right_index, filler))
        return segments

    if slot.right == END:
        for left_index, token in enumerate(tokens[:-1]):
            if token != slot.left:
                continue
            filler = tuple(tokens[left_index + 1 :])
            if 1 <= len(filler) <= max_len:
                segments.append((left_index + 1, n, filler))
        return segments

    for left_index, token in enumerate(tokens[:-2]):
        if token != slot.left:
            continue
        max_right_index = min(n - 1, left_index + max_len + 1)
        for right_index in range(left_index + 2, max_right_index + 1):
            if tokens[right_index] == slot.right:
                filler = tuple(tokens[left_index + 1 : right_index])
                if filler:
                    segments.append((left_index + 1, right_index, filler))
    return segments


def context(tokens: list[str], start: int, end: int, window: int = 3) -> tuple[str, str]:
    return " ".join(tokens[max(0, start - window) : start]), " ".join(tokens[end : min(len(tokens), end + window)])


def join_tokens(tokens: tuple[str, ...] | list[str]) -> str:
    return "-".join(tokens)


def one_edit_relation(a: tuple[str, ...], b: tuple[str, ...]) -> str:
    if a == b:
        return ""
    if len(a) == len(b):
        diffs = [i for i, (x, y) in enumerate(zip(a, b)) if x != y]
        if len(diffs) == 1:
            idx = diffs[0]
            return f"Substitution@{idx + 1}:{a[idx]}>{b[idx]}"
        return ""
    if len(a) + 1 == len(b):
        for idx in range(len(b)):
            if a == b[:idx] + b[idx + 1 :]:
                if idx == 0:
                    return f"PrefixAddition:{b[idx]}"
                if idx == len(b) - 1:
                    return f"SuffixAddition:{b[idx]}"
                return f"InfixAddition@{idx + 1}:{b[idx]}"
        return ""
    if len(b) + 1 == len(a):
        relation = one_edit_relation(b, a)
        if relation.startswith("PrefixAddition"):
            return relation.replace("PrefixAddition", "PrefixDeletion", 1)
        if relation.startswith("SuffixAddition"):
            return relation.replace("SuffixAddition", "SuffixDeletion", 1)
        if relation.startswith("InfixAddition"):
            return relation.replace("InfixAddition", "InfixDeletion", 1)
    return ""


def row_base(row: dict[str, str], tokens: list[str]) -> dict[str, object]:
    return {
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
    }


def final_role(distinct_stems: int, frame_count: int, count: int) -> str:
    if distinct_stems >= 20 and frame_count >= 3:
        return "HIGH_REUSE_FINAL_MODIFIER"
    if distinct_stems >= 10 and frame_count >= 2:
        return "POSSIBLE_SUFFIX_OR_FINAL_MODIFIER"
    if count >= 10 and distinct_stems >= 4:
        return "FRAME_LOCAL_FINAL"
    return "LOW_EVIDENCE_FINAL"


def initial_role(distinct_remainders: int, frame_count: int, count: int) -> str:
    if distinct_remainders >= 20 and frame_count >= 3:
        return "HIGH_REUSE_INITIAL_MODIFIER"
    if distinct_remainders >= 10 and frame_count >= 2:
        return "POSSIBLE_PREFIX_OR_CLASSIFIER"
    if count >= 10 and distinct_remainders >= 4:
        return "FRAME_LOCAL_INITIAL"
    return "LOW_EVIDENCE_INITIAL"


def model(args: argparse.Namespace) -> None:
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    slots = load_slots(Path(args.slot_candidates), args.slot_threshold, args.slot_limit)
    slot_by_frame = {slot.frame: slot for slot in slots}

    filler_stats: dict[tuple[str, tuple[str, ...]], FillerStats] = {}
    occurrence_rows: list[dict[str, object]] = []
    frame_occurrence_counts: Counter[str] = Counter()

    with Path(args.corpus_path).open(newline="", encoding="utf-8-sig") as handle:
        for row in csv.DictReader(handle):
            tokens = [token for token in sign_tokens(row.get("text")) if token not in {"000", "999"}]
            tokens.reverse()
            if not tokens:
                continue

            for slot in slots:
                for start, end, filler in extract_segments(tokens, slot, args.max_filler_length):
                    frame_occurrence_counts[slot.frame] += 1
                    key = (slot.frame, filler)
                    stats = filler_stats.setdefault(
                        key,
                        FillerStats(frame=slot.frame, left=slot.left, right=slot.right, filler=filler),
                    )
                    stats.count += 1
                    stats.texts.add(row.get("id", ""))
                    add_count(stats.regions, row.get("region"))
                    add_count(stats.sites, row.get("site"))
                    add_count(stats.types, row.get("type"))
                    add_count(stats.symbols, row.get("symbol"))
                    add_count(stats.materials, row.get("material"))
                    add_count(stats.complete, row.get("complete"))
                    if len(stats.examples) < 5:
                        stats.examples.append(f"{row.get('id')}/{row.get('cisi')}/{row.get('site')}")

                    left_context, right_context = context(tokens, start, end)
                    occurrence_rows.append(
                        {
                            **row_base(row, tokens),
                            "Frame": slot.frame,
                            "Left": slot.left,
                            "Right": slot.right,
                            "Filler": join_tokens(filler),
                            "FillerLength": len(filler),
                            "StartPos": start + 1,
                            "EndPos": end,
                            "LeftContext": left_context,
                            "RightContext": right_context,
                            "SlotScore": slot.score,
                        }
                    )

    filler_rows: list[dict[str, object]] = []
    final_stats: dict[str, dict[str, object]] = defaultdict(lambda: {"count": 0, "stems": Counter(), "frames": Counter(), "fillers": Counter(), "sites": Counter()})
    initial_stats: dict[str, dict[str, object]] = defaultdict(lambda: {"count": 0, "remainders": Counter(), "frames": Counter(), "fillers": Counter(), "sites": Counter()})
    stem_final_stats: dict[tuple[str, str], Counter[str]] = defaultdict(Counter)
    stem_final_frames: dict[tuple[str, str], Counter[str]] = defaultdict(Counter)
    filler_cross_frames: dict[str, Counter[str]] = defaultdict(Counter)
    filler_cross_sites: dict[str, Counter[str]] = defaultdict(Counter)

    for (frame, filler), stats in filler_stats.items():
        filler_text = join_tokens(filler)
        first = filler[0]
        final = filler[-1]
        stem_minus_final = join_tokens(filler[:-1]) if len(filler) > 1 else ""
        rest_after_initial = join_tokens(filler[1:]) if len(filler) > 1 else ""
        site, site_share = dominant(stats.sites)
        region, region_share = dominant(stats.regions)
        typ, type_share = dominant(stats.types)
        symbol, symbol_share = dominant(stats.symbols)
        complete_y = stats.complete.get("Y", 0)
        seal_count = sum(count for key, count in stats.types.items() if key.startswith("SEAL"))

        filler_rows.append(
            {
                "Frame": frame,
                "Left": stats.left,
                "Right": stats.right,
                "Filler": filler_text,
                "FillerLength": len(filler),
                "Count": stats.count,
                "TextCount": len(stats.texts),
                "SiteCount": len(stats.sites),
                "RegionCount": len(stats.regions),
                "TypeCount": len(stats.types),
                "FirstSign": first,
                "FinalSign": final,
                "StemMinusFinal": stem_minus_final,
                "RestAfterInitial": rest_after_initial,
                "DominantSite": site,
                "DominantSiteShare": site_share,
                "DominantRegion": region,
                "DominantRegionShare": region_share,
                "DominantType": typ,
                "DominantTypeShare": type_share,
                "DominantSymbol": symbol,
                "DominantSymbolShare": symbol_share,
                "SealPct": round(seal_count / stats.count, 4),
                "CompletePct": round(complete_y / stats.count, 4),
                "Examples": "; ".join(stats.examples),
            }
        )

        final_entry = final_stats[final]
        final_entry["count"] += stats.count
        final_entry["frames"][frame] += stats.count
        final_entry["fillers"][filler_text] += stats.count
        if stem_minus_final:
            final_entry["stems"][stem_minus_final] += stats.count
        for site_key, count in stats.sites.items():
            final_entry["sites"][site_key] += count

        initial_entry = initial_stats[first]
        initial_entry["count"] += stats.count
        initial_entry["frames"][frame] += stats.count
        initial_entry["fillers"][filler_text] += stats.count
        if rest_after_initial:
            initial_entry["remainders"][rest_after_initial] += stats.count
        for site_key, count in stats.sites.items():
            initial_entry["sites"][site_key] += count

        if len(filler) > 1:
            stem_key = (frame, stem_minus_final)
            stem_final_stats[stem_key][final] += stats.count
            stem_final_frames[stem_key][frame] += stats.count

        filler_cross_frames[filler_text][frame] += stats.count
        for site_key, count in stats.sites.items():
            filler_cross_sites[filler_text][site_key] += count

    frame_rows: list[dict[str, object]] = []
    for slot in slots:
        frame_fillers = [row for row in filler_rows if row["Frame"] == slot.frame]
        filler_count = sum(int(row["Count"]) for row in frame_fillers)
        length_counter = Counter()
        final_counter = Counter()
        initial_counter = Counter()
        for row in frame_fillers:
            length_counter[str(row["FillerLength"])] += int(row["Count"])
            final_counter[str(row["FinalSign"])] += int(row["Count"])
            initial_counter[str(row["FirstSign"])] += int(row["Count"])
        top_filler = sorted(frame_fillers, key=lambda row: (-int(row["Count"]), str(row["Filler"])))[:1]
        dom_final, dom_final_share = dominant(final_counter)
        dom_initial, dom_initial_share = dominant(initial_counter)
        frame_rows.append(
            {
                "Frame": slot.frame,
                "Left": slot.left,
                "Right": slot.right,
                "SlotScore": slot.score,
                "ExtractedOccurrences": filler_count,
                "DistinctFillers": len(frame_fillers),
                "MeanFillerLength": round(sum(int(row["FillerLength"]) * int(row["Count"]) for row in frame_fillers) / filler_count, 4) if filler_count else 0,
                "LengthEntropy": normalized_entropy(length_counter),
                "TopFiller": top_filler[0]["Filler"] if top_filler else "",
                "TopFillerCount": top_filler[0]["Count"] if top_filler else 0,
                "DominantInitial": dom_initial,
                "DominantInitialShare": dom_initial_share,
                "DominantFinal": dom_final,
                "DominantFinalShare": dom_final_share,
                "FinalEntropy": normalized_entropy(final_counter),
                "InitialEntropy": normalized_entropy(initial_counter),
            }
        )

    final_rows: list[dict[str, object]] = []
    for sign, entry in final_stats.items():
        frames = entry["frames"]
        stems = entry["stems"]
        fillers = entry["fillers"]
        sites = entry["sites"]
        final_rows.append(
            {
                "FinalSign": sign,
                "TotalCount": entry["count"],
                "FrameCount": len(frames),
                "DistinctStems": len(stems),
                "DistinctFillers": len(fillers),
                "SiteCount": len(sites),
                "DominantFrame": dominant(frames)[0],
                "DominantFrameShare": dominant(frames)[1],
                "RoleLead": final_role(len(stems), len(frames), entry["count"]),
            }
        )

    initial_rows: list[dict[str, object]] = []
    for sign, entry in initial_stats.items():
        frames = entry["frames"]
        remainders = entry["remainders"]
        fillers = entry["fillers"]
        sites = entry["sites"]
        initial_rows.append(
            {
                "InitialSign": sign,
                "TotalCount": entry["count"],
                "FrameCount": len(frames),
                "DistinctRemainders": len(remainders),
                "DistinctFillers": len(fillers),
                "SiteCount": len(sites),
                "DominantFrame": dominant(frames)[0],
                "DominantFrameShare": dominant(frames)[1],
                "RoleLead": initial_role(len(remainders), len(frames), entry["count"]),
            }
        )

    stem_rows: list[dict[str, object]] = []
    for (frame, stem), finals in stem_final_stats.items():
        if len(finals) < 2:
            continue
        total = sum(finals.values())
        if total < args.min_paradigm_count:
            continue
        stem_rows.append(
            {
                "Frame": frame,
                "Stem": stem,
                "TotalCount": total,
                "DistinctFinals": len(finals),
                "FinalSet": "; ".join(f"{sign}:{count}" for sign, count in finals.most_common()),
                "ParadigmLead": "StemWithAlternatingFinals",
            }
        )

    cross_rows: list[dict[str, object]] = []
    for filler, frames in filler_cross_frames.items():
        if len(frames) < 2:
            continue
        total = sum(frames.values())
        if total < args.min_cross_frame_count:
            continue
        sites = filler_cross_sites[filler]
        cross_rows.append(
            {
                "Filler": filler,
                "TotalCount": total,
                "FrameCount": len(frames),
                "SiteCount": len(sites),
                "Frames": "; ".join(f"{frame}:{count}" for frame, count in frames.most_common()),
                "DominantSite": dominant(sites)[0],
                "DominantSiteShare": dominant(sites)[1],
                "Lead": "SameFillerAcrossFrames",
            }
        )

    pair_rows: list[dict[str, object]] = []
    fillers_by_frame: dict[str, list[tuple[tuple[str, ...], int]]] = defaultdict(list)
    for (frame, filler), stats in filler_stats.items():
        if stats.count >= args.min_pair_filler_count:
            fillers_by_frame[frame].append((filler, stats.count))
    for frame, values in fillers_by_frame.items():
        values = sorted(values, key=lambda item: (-item[1], item[0]))[: args.max_pair_fillers_per_frame]
        for i, (a, count_a) in enumerate(values):
            for b, count_b in values[i + 1 :]:
                relation = one_edit_relation(a, b)
                if not relation:
                    continue
                pair_rows.append(
                    {
                        "Frame": frame,
                        "FillerA": join_tokens(a),
                        "CountA": count_a,
                        "FillerB": join_tokens(b),
                        "CountB": count_b,
                        "Relation": relation,
                        "CombinedCount": count_a + count_b,
                        "Lead": "MinimalAlternation",
                    }
                )

    summary_rows = [
        {"Metric": "Productive frames modeled", "Value": len(slots), "Note": f"slot score >= {args.slot_threshold}"},
        {"Metric": "Slot occurrences extracted", "Value": len(occurrence_rows), "Note": f"fillers up to {args.max_filler_length} signs"},
        {"Metric": "Distinct frame/filler pairs", "Value": len(filler_rows), "Note": "Unique fillers per selected frame."},
        {"Metric": "Final-sign leads", "Value": len(final_rows), "Note": "Final sign behavior across slot fillers."},
        {"Metric": "Initial-sign leads", "Value": len(initial_rows), "Note": "Initial sign behavior across slot fillers."},
        {"Metric": "Alternating stem/final paradigms", "Value": len(stem_rows), "Note": "Same stem with multiple final signs."},
        {"Metric": "Cross-frame reused fillers", "Value": len(cross_rows), "Note": "Same filler seen in multiple productive frames."},
        {"Metric": "Minimal filler pairs", "Value": len(pair_rows), "Note": "One-edit alternations within the same frame."},
    ]

    paths = {
        "summary": out_dir / "slot_paradigm_summary.csv",
        "frames": out_dir / "slot_paradigm_frames.csv",
        "fillers": out_dir / "slot_paradigm_fillers.csv",
        "occurrences": out_dir / "slot_paradigm_occurrences.csv",
        "finals": out_dir / "slot_paradigm_final_signs.csv",
        "initials": out_dir / "slot_paradigm_initial_signs.csv",
        "stems": out_dir / "slot_paradigm_stem_finals.csv",
        "cross": out_dir / "slot_paradigm_cross_frame_reuse.csv",
        "pairs": out_dir / "slot_paradigm_minimal_pairs.csv",
        "tex": out_dir / "slot_paradigm_model.tex",
    }

    write_csv(paths["summary"], summary_rows, ["Metric", "Value", "Note"])
    write_csv(
        paths["frames"],
        sorted(frame_rows, key=lambda row: (-float(row["SlotScore"]), -int(row["DistinctFillers"]))),
        [
            "Frame",
            "Left",
            "Right",
            "SlotScore",
            "ExtractedOccurrences",
            "DistinctFillers",
            "MeanFillerLength",
            "LengthEntropy",
            "TopFiller",
            "TopFillerCount",
            "DominantInitial",
            "DominantInitialShare",
            "DominantFinal",
            "DominantFinalShare",
            "FinalEntropy",
            "InitialEntropy",
        ],
    )
    write_csv(
        paths["fillers"],
        sorted(filler_rows, key=lambda row: (str(row["Frame"]), -int(row["Count"]), str(row["Filler"]))),
        [
            "Frame",
            "Left",
            "Right",
            "Filler",
            "FillerLength",
            "Count",
            "TextCount",
            "SiteCount",
            "RegionCount",
            "TypeCount",
            "FirstSign",
            "FinalSign",
            "StemMinusFinal",
            "RestAfterInitial",
            "DominantSite",
            "DominantSiteShare",
            "DominantRegion",
            "DominantRegionShare",
            "DominantType",
            "DominantTypeShare",
            "DominantSymbol",
            "DominantSymbolShare",
            "SealPct",
            "CompletePct",
            "Examples",
        ],
    )
    write_csv(
        paths["occurrences"],
        occurrence_rows,
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
            "Frame",
            "Left",
            "Right",
            "Filler",
            "FillerLength",
            "StartPos",
            "EndPos",
            "LeftContext",
            "RightContext",
            "SlotScore",
        ],
    )
    write_csv(
        paths["finals"],
        sorted(final_rows, key=lambda row: (-int(row["DistinctStems"]), -int(row["TotalCount"]), str(row["FinalSign"]))),
        ["FinalSign", "TotalCount", "FrameCount", "DistinctStems", "DistinctFillers", "SiteCount", "DominantFrame", "DominantFrameShare", "RoleLead"],
    )
    write_csv(
        paths["initials"],
        sorted(initial_rows, key=lambda row: (-int(row["DistinctRemainders"]), -int(row["TotalCount"]), str(row["InitialSign"]))),
        ["InitialSign", "TotalCount", "FrameCount", "DistinctRemainders", "DistinctFillers", "SiteCount", "DominantFrame", "DominantFrameShare", "RoleLead"],
    )
    write_csv(
        paths["stems"],
        sorted(stem_rows, key=lambda row: (-int(row["DistinctFinals"]), -int(row["TotalCount"]), str(row["Frame"]), str(row["Stem"]))),
        ["Frame", "Stem", "TotalCount", "DistinctFinals", "FinalSet", "ParadigmLead"],
    )
    write_csv(
        paths["cross"],
        sorted(cross_rows, key=lambda row: (-int(row["FrameCount"]), -int(row["TotalCount"]), str(row["Filler"]))),
        ["Filler", "TotalCount", "FrameCount", "SiteCount", "Frames", "DominantSite", "DominantSiteShare", "Lead"],
    )
    write_csv(
        paths["pairs"],
        sorted(pair_rows, key=lambda row: (str(row["Frame"]), -int(row["CombinedCount"]), str(row["Relation"]), str(row["FillerA"]))),
        ["Frame", "FillerA", "CountA", "FillerB", "CountB", "Relation", "CombinedCount", "Lead"],
    )

    top_frame_rows = sorted(frame_rows, key=lambda row: (-float(row["SlotScore"]), -int(row["DistinctFillers"])))[:10]
    top_final_rows = sorted(final_rows, key=lambda row: (-int(row["DistinctStems"]), -int(row["TotalCount"]), str(row["FinalSign"])))[:12]
    top_initial_rows = sorted(initial_rows, key=lambda row: (-int(row["DistinctRemainders"]), -int(row["TotalCount"]), str(row["InitialSign"])))[:10]
    top_cross_rows = sorted(cross_rows, key=lambda row: (-int(row["FrameCount"]), -int(row["TotalCount"]), str(row["Filler"])))[:10]
    top_pair_rows = sorted(pair_rows, key=lambda row: (-int(row["CombinedCount"]), str(row["Frame"]), str(row["Relation"])))[:12]

    lines: list[str] = [
        r"\documentclass[11pt,a4paper]{article}",
        r"\usepackage[margin=1in]{geometry}",
        r"\usepackage[T1]{fontenc}",
        r"\usepackage[utf8]{inputenc}",
        r"\usepackage{booktabs}",
        r"\begin{document}",
        r"\section*{Slot Paradigm Model}",
        "This report extracts concrete paradigms from productive frames. It searches for repeated fillers, reusable final signs, cross-frame reuse, and one-edit alternations that could become future phonetic or grammatical constraints.",
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
            r"\subsection*{Top Productive Frames}",
            r"\begin{center}",
            r"\begin{tabular}{lrrrr}",
            r"\toprule",
            r"\textbf{Frame} & \textbf{Occ.} & \textbf{Fillers} & \textbf{Mean len.} & \textbf{Top filler} \\",
            r"\midrule",
        ]
    )
    for row in top_frame_rows:
        values = [row["Frame"], row["ExtractedOccurrences"], row["DistinctFillers"], row["MeanFillerLength"], row["TopFiller"]]
        lines.append(" & ".join(latex_escape(value) for value in values) + r" \\")
    lines.extend(
        [
            r"\bottomrule",
            r"\end{tabular}",
            r"\end{center}",
            r"\subsection*{Final-Sign Leads Inside Slots}",
            r"\begin{center}",
            r"\begin{tabular}{lrrrl}",
            r"\toprule",
            r"\textbf{Final} & \textbf{Count} & \textbf{Stems} & \textbf{Frames} & \textbf{Role lead} \\",
            r"\midrule",
        ]
    )
    for row in top_final_rows:
        values = [row["FinalSign"], row["TotalCount"], row["DistinctStems"], row["FrameCount"], row["RoleLead"]]
        lines.append(" & ".join(latex_escape(value) for value in values) + r" \\")
    lines.extend(
        [
            r"\bottomrule",
            r"\end{tabular}",
            r"\end{center}",
            r"\subsection*{Initial-Sign Leads Inside Slots}",
            r"\begin{center}",
            r"\begin{tabular}{lrrrl}",
            r"\toprule",
            r"\textbf{Initial} & \textbf{Count} & \textbf{Remainders} & \textbf{Frames} & \textbf{Role lead} \\",
            r"\midrule",
        ]
    )
    for row in top_initial_rows:
        values = [row["InitialSign"], row["TotalCount"], row["DistinctRemainders"], row["FrameCount"], row["RoleLead"]]
        lines.append(" & ".join(latex_escape(value) for value in values) + r" \\")
    lines.extend(
        [
            r"\bottomrule",
            r"\end{tabular}",
            r"\end{center}",
            r"\subsection*{Cross-Frame Reused Fillers}",
            r"\begin{center}",
            r"\begin{tabular}{lrrp{0.42\textwidth}}",
            r"\toprule",
            r"\textbf{Filler} & \textbf{Count} & \textbf{Frames} & \textbf{Frame distribution} \\",
            r"\midrule",
        ]
    )
    for row in top_cross_rows:
        values = [row["Filler"], row["TotalCount"], row["FrameCount"], row["Frames"]]
        lines.append(" & ".join(latex_escape(value) for value in values) + r" \\")
    lines.extend(
        [
            r"\bottomrule",
            r"\end{tabular}",
            r"\end{center}",
            r"\subsection*{Minimal Alternation Leads}",
            r"\begin{center}",
            r"\begin{tabular}{llllr}",
            r"\toprule",
            r"\textbf{Frame} & \textbf{A} & \textbf{B} & \textbf{Relation} & \textbf{Count} \\",
            r"\midrule",
        ]
    )
    for row in top_pair_rows:
        values = [row["Frame"], row["FillerA"], row["FillerB"], row["Relation"], row["CombinedCount"]]
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
    for key in ["summary", "frames", "fillers", "occurrences", "finals", "initials", "stems", "cross", "pairs"]:
        lines.append(r"\item \texttt{" + latex_escape(paths[key]) + "}")
    lines.extend([r"\end{itemize}", r"\end{document}"])
    paths["tex"].write_text("\n".join(lines) + "\n", encoding="utf-8")

    for path in paths.values():
        print(f"Wrote {path}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--corpus-path", default="data/ivs_corpus_cleaned.csv")
    parser.add_argument("--slot-candidates", default="outputs/onomastic_formula_slots.csv")
    parser.add_argument("--out-dir", default="outputs")
    parser.add_argument("--slot-threshold", type=float, default=0.91)
    parser.add_argument("--slot-limit", type=int, default=20)
    parser.add_argument("--max-filler-length", type=int, default=5)
    parser.add_argument("--min-paradigm-count", type=int, default=3)
    parser.add_argument("--min-cross-frame-count", type=int, default=3)
    parser.add_argument("--min-pair-filler-count", type=int, default=2)
    parser.add_argument("--max-pair-fillers-per-frame", type=int, default=220)
    return parser.parse_args()


if __name__ == "__main__":
    model(parse_args())
