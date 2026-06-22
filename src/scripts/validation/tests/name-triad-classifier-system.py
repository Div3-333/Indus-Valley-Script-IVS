#!/usr/bin/env python3
"""
Name-Triad Classifier System — tests whether the top proper-name candidates
(817, 861, 820, and the compound 405-501) form a classifier system: each
paired with a consistent opener, a distinctive icon, or a distinctive site,
the way administrative naming systems often mark category alongside identity.

WHAT THIS DOES AND WHY
-----------------------
The corrected proper-name detector flagged 817, 861, 820 as Mohenjo-daro-
concentrated and 405-501 as Harappa-and-Bull1:I-concentrated, all clearing a
frequency and localization bar that distinguishes them from generic,
corpus-wide signs. Localization alone doesn't tell you whether these
function as personal names, toponyms, or category markers. One thing that
WOULD distinguish a classifier system from a flat list of unrelated localized
signs is internal structure: do these candidates each travel with one
dominant opener sign (suggesting "[opener=class marker] + [candidate=
specific identity]"), and do those openers differ across candidates
(suggesting different classes) or coincide (suggesting one shared class with
multiple members)?

This script is explicitly exploratory and looks for, rather than assumes,
that structure. A flat result -- no candidate has a dominant opener, or all
four share the same one purely because it's the corpus's most common opener
overall -- would itself be a finding (no detectable classifier system), and
is reported as such rather than dressed up as a discovery.

METHODOLOGICAL CHOICES
-----------------------
1. Name candidates can appear ANYWHERE in an inscription (we are not testing
   their own position), so this script does not restrict to complete texts
   when simply counting occurrences, site/icon/material distributions, or
   frequency. However, "opener" and "terminal" are only meaningful labels
   for a text whose edges are intact -- a name candidate found near the
   visible start of a text broken at that very edge does not tell us
   anything about a true "opener" sign, since the inscription may continue
   past the break. So step 2's opener/terminal extraction is restricted to
   complete, edge-intact inscriptions, while frequency/site/icon/material
   counts in earlier exploratory tables use the full corpus. This is a
   deliberate, disclosed deviation from "parse all inscriptions" for the
   specific sub-analyses where edge truncation would invalidate the result.
2. The compound "405-501" is matched as a literal adjacent bigram in the
   sign sequence (not as two independent single-sign hits), since the prior
   proper-name detector identified it as a single recurring multi-sign unit.
3. PMI and the opener-consistency / classifier-score formulas use clipped
   ranges as specified, to prevent one extreme outlier dimension (e.g. a
   very large icon PMI driven by a tiny sample) from dominating the
   composite score; clipping bounds are stated explicitly in the output so
   the scoring is auditable, not just trusted.
4. Chi-squared/Cramer's V tests on the icon x name-candidate matrix drop
   icon categories with fewer than 3 total occurrences (pooled into "Other")
   before testing, since "symbol" is blank for a large share of inscriptions
   and many distinct icon labels are otherwise singleton categories.
5. The damage placeholder "000" is excluded and ambiguous '/' readings
   resolve to the first listed value, as elsewhere in the pipeline.
"""

from __future__ import annotations

import argparse
import csv
import math
import re
from collections import Counter
from pathlib import Path

from scipy.stats import chi2_contingency

SIGN_CHUNK_RE = re.compile(r"\d{3,4}(?:/\d{3,4})*")
ILLEGIBLE = "000"
TARGETS = ["817", "861", "820", "405-501"]
OPENER_CONSISTENCY_THRESHOLD = 0.35
MIN_ICON_CATEGORY_COUNT = 3


def parse_args():
    p = argparse.ArgumentParser(description="Test whether 817/861/820/405-501 form a classifier system.")
    p.add_argument("--data", default="data")
    p.add_argument("--outputs", default="outputs")
    return p.parse_args()


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
    for old, new in {"\\": "/", "_": r"\_", "%": r"\%", "&": r"\&", "#": r"\#", "$": r"\$", "{": r"\{", "}": r"\}"}.items():
        text = text.replace(old, new)
    return text


def latex_table(rows: list[dict[str, object]], fields: list[str], widths: list[str] | None = None) -> str:
    spec = "".join(widths) if widths else "l" * len(fields)
    lines = [rf"\begin{{tabular}}{{{spec}}}", r"\toprule"]
    lines.append(" & ".join(rf"\textbf{{{latex_escape(f)}}}" for f in fields) + r" \\")
    lines.append(r"\midrule")
    for row in rows:
        lines.append(" & ".join(latex_escape(row.get(f, "")) for f in fields) + r" \\")
    lines.append(r"\bottomrule")
    lines.append(r"\end{tabular}")
    return "\n".join(lines)


def parse_signs(text: str | None) -> list[str]:
    raw = (text or "").strip()
    tokens = []
    for chunk in SIGN_CHUNK_RE.findall(raw):
        sign = chunk.split("/")[0]
        if sign != ILLEGIBLE:
            tokens.append(sign)
    return tokens


def fmt_p(p: float) -> str:
    if p == 0.0:
        return "<1e-300"
    return f"{p:.3g}"


def find_target_occurrences(tokens: list[str], target: str) -> bool:
    """True if `target` occurs in `tokens`, where a compound target like
    '405-501' is matched as an adjacent bigram, not two independent hits."""
    if "-" in target:
        parts = target.split("-")
        n = len(parts)
        return any(tokens[i:i + n] == parts for i in range(len(tokens) - n + 1))
    return target in tokens


def pool_rare(counts: Counter, min_count: int, other_label: str = "Other") -> Counter:
    keep = {k for k, c in counts.items() if c >= min_count}
    pooled = Counter()
    for k, c in counts.items():
        pooled[k if k in keep else other_label] += c
    return pooled


def cramers_v_table(table: list[list[int]]) -> tuple[float, float, str]:
    import numpy as np
    arr = np.array(table, dtype=float)
    if arr.size == 0:
        return 0.0, 1.0, "empty table"
    row_mask = arr.sum(axis=1) > 0
    col_mask = arr.sum(axis=0) > 0
    note = ""
    if (~row_mask).sum() or (~col_mask).sum():
        note = f"dropped {int((~row_mask).sum())} all-zero row(s), {int((~col_mask).sum())} all-zero col(s)"
    arr = arr[row_mask][:, col_mask]
    if arr.shape[0] < 2 or arr.shape[1] < 2:
        return 0.0, 1.0, (note or "degenerate table")
    try:
        chi2, p, dof, _ = chi2_contingency(arr)
    except ValueError as e:
        return 0.0, 1.0, f"chi-squared failed: {e}"
    n = arr.sum()
    r, c = arr.shape
    v = math.sqrt(chi2 / (n * (min(r, c) - 1))) if n > 0 and min(r, c) > 1 else 0.0
    return float(v), float(p), note


def pmi(count_ab: int, n_a: int, n_b: int, n_total: int) -> float:
    if count_ab == 0 or n_a == 0 or n_b == 0 or n_total == 0:
        return float("-inf")
    return math.log2((count_ab / n_total) / ((n_a / n_total) * (n_b / n_total)))


def top_n(counts: Counter, n: int = 5) -> str:
    return "; ".join(f"{k}:{c}" for k, c in counts.most_common(n))


def main() -> None:
    args = parse_args()
    data_dir, out_dir = Path(args.data), Path(args.outputs)
    out_dir.mkdir(parents=True, exist_ok=True)

    corpus_path = data_dir / "ivs_corpus_cleaned.csv"
    if not corpus_path.exists():
        print(f"Error: {corpus_path} not found.")
        return

    print("Loading corpus...")
    corpus = read_csv(corpus_path)

    print("Parsing all inscriptions (frequency/site/icon scope)...")
    all_parsed = []
    for row in corpus:
        tokens = parse_signs(row.get("text", ""))
        if tokens:
            all_parsed.append((tokens, row))
    print(f"  {len(all_parsed)} inscriptions with at least one legible sign.")

    print("Parsing complete, edge-intact inscriptions (opener/terminal scope)...")
    gold = []
    for row in corpus:
        raw = (row.get("text") or "").strip()
        if row.get("complete") != "Y" or not (raw.startswith("+") and raw.endswith("+")):
            continue
        tokens = parse_signs(raw)
        if tokens:
            gold.append((tokens, row))
    print(f"  {len(gold)} complete, edge-intact inscriptions.")

    n_corpus = len(all_parsed)
    site_base = Counter(row.get("site", "") or "Unknown" for _, row in all_parsed)
    icon_base = Counter(row.get("symbol", "") or "Unknown" for _, row in all_parsed)
    total_base = sum(site_base.values())

    # --- Per-candidate full-corpus stats (frequency, site, icon, material) ---
    print("Computing per-candidate frequency / site / icon / material stats (full corpus)...")
    cand_full_stats = {}
    for target in TARGETS:
        sites, icons, materials = Counter(), Counter(), Counter()
        freq = 0
        for tokens, row in all_parsed:
            if find_target_occurrences(tokens, target):
                freq += 1
                sites[row.get("site", "") or "Unknown"] += 1
                icons[row.get("symbol", "") or "Unknown"] += 1
                materials[row.get("material", "") or "Unknown"] += 1
        cand_full_stats[target] = {"freq": freq, "sites": sites, "icons": icons, "materials": materials}
        print(f"  {target}: {freq} occurrences across the full corpus.")

    # --- Opener/terminal extraction (gold subset only) ---
    print("Extracting opener/terminal signs per candidate (complete, edge-intact subset only)...")
    cand_gold_rows = {target: [] for target in TARGETS}
    for tokens, row in gold:
        for target in TARGETS:
            if find_target_occurrences(tokens, target):
                cand_gold_rows[target].append({
                    "opener": tokens[0], "terminal": tokens[-1],
                    "site": row.get("site", "") or "Unknown",
                    "icon": row.get("symbol", "") or "Unknown",
                    "material": row.get("material", "") or "Unknown",
                    "class": row.get("class", "") or "Unknown",
                })

    # --- Corpus-wide opener base rates, for lift comparison ---
    opener_base_rate = Counter(tokens[0] for tokens, _ in gold)
    n_gold_total = len(gold)

    opener_rows = []
    terminal_rows = []
    for target in TARGETS:
        occs = cand_gold_rows[target]
        n = len(occs)
        opener_counts = Counter(o["opener"] for o in occs)
        terminal_counts = Counter(o["terminal"] for o in occs)
        top_opener, top_opener_freq = (opener_counts.most_common(1)[0] if opener_counts else ("", 0))
        top_terminal, top_terminal_freq = (terminal_counts.most_common(1)[0] if terminal_counts else ("", 0))
        opener_consistency = top_opener_freq / n if n else 0.0
        terminal_consistency = top_terminal_freq / n if n else 0.0

        baseline_rate = opener_base_rate.get(top_opener, 0) / n_gold_total if n_gold_total else 0.0
        opener_lift = opener_consistency / baseline_rate if baseline_rate > 0 else float("inf")

        full = cand_full_stats[target]
        top_site, top_site_count = (full["sites"].most_common(1)[0] if full["sites"] else ("", 0))
        top_icon, top_icon_count = (full["icons"].most_common(1)[0] if full["icons"] else ("", 0))
        site_pmi = pmi(top_site_count, full["freq"], site_base.get(top_site, 0), total_base) if top_site and top_site != "Unknown" else 0.0
        icon_pmi = pmi(top_icon_count, full["freq"], icon_base.get(top_icon, 0), total_base) if top_icon and top_icon != "Unknown" else 0.0
        site_pmi = max(site_pmi, 0.0) if math.isfinite(site_pmi) else 0.0
        icon_pmi = max(icon_pmi, 0.0) if math.isfinite(icon_pmi) else 0.0

        classifier_score = (
            min(max(opener_consistency, 0.0), 1.0) +
            min(max(site_pmi, 0.0), 3.0) / 3.0 +
            min(max(icon_pmi, 0.0), 5.0) / 5.0
        ) / 3.0
        verdict = "STRONG" if classifier_score >= 0.5 else ("MODERATE" if classifier_score >= 0.3 else "WEAK")

        opener_rows.append({
            "name_candidate": target, "top_opener": top_opener, "opener_freq": top_opener_freq,
            "opener_consistency": f"{opener_consistency:.3f}",
            "corpus_wide_opener_rate": f"{baseline_rate:.3f}",
            "opener_lift_vs_baseline": f"{opener_lift:.2f}" if math.isfinite(opener_lift) else "inf",
            "site_pmi": f"{site_pmi:.3f}",
            "icon_pmi": f"{icon_pmi:.3f}", "classifier_score": f"{classifier_score:.3f}", "verdict": verdict,
            "n_gold_occurrences": n,
        })
        terminal_rows.append({
            "name_candidate": target, "top_terminal": top_terminal, "terminal_freq": top_terminal_freq,
            "terminal_consistency": f"{terminal_consistency:.3f}", "n_gold_occurrences": n,
        })

    write_csv(out_dir / "name_triad_openers.csv", opener_rows,
              ["name_candidate", "top_opener", "opener_freq", "opener_consistency", "corpus_wide_opener_rate",
               "opener_lift_vs_baseline", "site_pmi", "icon_pmi", "classifier_score", "verdict", "n_gold_occurrences"])
    write_csv(out_dir / "name_triad_terminals.csv", terminal_rows,
              ["name_candidate", "top_terminal", "terminal_freq", "terminal_consistency", "n_gold_occurrences"])

    print("Classifier strength per candidate:")
    for r in opener_rows:
        flag = "DOMINANT OPENER" if float(r["opener_consistency"]) >= OPENER_CONSISTENCY_THRESHOLD else "no dominant opener"
        print(f"  {r['name_candidate']}: top_opener={r['top_opener']} consistency={r['opener_consistency']} "
              f"(corpus baseline={r['corpus_wide_opener_rate']}, lift={r['opener_lift_vs_baseline']}x) ({flag}) -> {r['verdict']}")

    # --- Cross-candidate opener Jaccard + chi-squared ---
    print("Cross-candidate opener comparison...")
    top5_openers = {t: set(k for k, _ in Counter(o["opener"] for o in cand_gold_rows[t]).most_common(5)) for t in TARGETS}
    jaccard_rows = []
    for i in range(len(TARGETS)):
        for j in range(i + 1, len(TARGETS)):
            a, b = TARGETS[i], TARGETS[j]
            sa, sb = top5_openers[a], top5_openers[b]
            jacc = len(sa & sb) / len(sa | sb) if (sa | sb) else 0.0
            jaccard_rows.append({"pair": f"{a} vs {b}", "jaccard_top5_openers": f"{jacc:.3f}",
                                  "shared_openers": "; ".join(sorted(sa & sb)) or "none"})
    write_csv(out_dir / "name_triad_opener_jaccard.csv", jaccard_rows, ["pair", "jaccard_top5_openers", "shared_openers"])

    all_openers = sorted({o["opener"] for t in TARGETS for o in cand_gold_rows[t]})
    opener_matrix = [[Counter(o["opener"] for o in cand_gold_rows[t]).get(op, 0) for op in all_openers] for t in TARGETS]
    v_opener, p_opener, note_opener = cramers_v_table(opener_matrix)
    print(f"  Opener distribution across all 4 candidates: Cramer's V={v_opener:.3f}, p={fmt_p(p_opener)} ({note_opener or 'no rows/cols dropped'})")

    # --- Cross-candidate terminal comparison ---
    print("Cross-candidate terminal comparison...")
    all_terminals = sorted({o["terminal"] for t in TARGETS for o in cand_gold_rows[t]})
    terminal_matrix = [[Counter(o["terminal"] for o in cand_gold_rows[t]).get(te, 0) for te in all_terminals] for t in TARGETS]
    v_terminal, p_terminal, note_terminal = cramers_v_table(terminal_matrix)
    print(f"  Terminal distribution across all 4 candidates: Cramer's V={v_terminal:.3f}, p={fmt_p(p_terminal)} ({note_terminal or 'no rows/cols dropped'})")

    cross_summary = [
        {"Test": "Opener distribution, 4 candidates", "CramersV": f"{v_opener:.3f}", "P": fmt_p(p_opener), "Note": note_opener},
        {"Test": "Terminal distribution, 4 candidates", "CramersV": f"{v_terminal:.3f}", "P": fmt_p(p_terminal), "Note": note_terminal},
    ]
    write_csv(out_dir / "name_triad_cross_candidate_tests.csv", cross_summary, ["Test", "CramersV", "P", "Note"])

    # --- Classifier system hypothesis table (one row per name candidate x its top opener) ---
    classifier_rows = sorted(opener_rows, key=lambda r: -float(r["classifier_score"]))
    write_csv(out_dir / "classifier_system_hypothesis.csv",
              [{"name_candidate": r["name_candidate"], "opener": r["top_opener"], "classifier_score": r["classifier_score"],
                "verdict": r["verdict"], "site_pmi": r["site_pmi"], "icon_pmi": r["icon_pmi"]} for r in classifier_rows],
              ["name_candidate", "opener", "classifier_score", "verdict", "site_pmi", "icon_pmi"])

    # --- Icon x name-candidate association matrix ---
    print("Building icon x name-candidate association matrix...")
    icon_counts_by_target = {t: cand_full_stats[t]["icons"] for t in TARGETS}
    pooled_icon_counts = {t: pool_rare(c, MIN_ICON_CATEGORY_COUNT) for t, c in icon_counts_by_target.items()}
    all_icons = sorted({i for t in TARGETS for i in pooled_icon_counts[t]})
    icon_matrix = [[pooled_icon_counts[t].get(i, 0) for i in all_icons] for t in TARGETS]
    v_icon_matrix, p_icon_matrix, note_icon_matrix = cramers_v_table(icon_matrix)
    print(f"  Icon x candidate matrix: Cramer's V={v_icon_matrix:.3f}, p={fmt_p(p_icon_matrix)}")

    icon_pmi_cells = []
    for t in TARGETS:
        n_t = cand_full_stats[t]["freq"]
        for icon, c in cand_full_stats[t]["icons"].items():
            if icon == "Unknown" or c < 2:
                continue
            n_icon = icon_base.get(icon, 0)
            this_pmi = pmi(c, n_t, n_icon, total_base)
            if math.isfinite(this_pmi):
                icon_pmi_cells.append({"name_candidate": t, "icon": icon, "count": c, "pmi": this_pmi})
    icon_pmi_cells.sort(key=lambda r: -r["pmi"])
    top_icon_pmi_rows = [{"name_candidate": r["name_candidate"], "icon": r["icon"], "count": r["count"], "pmi": f"{r['pmi']:.3f}"} for r in icon_pmi_cells[:10]]

    write_csv(out_dir / "icon_name_association.csv",
              [{"Metric": "Overall Cramer's V (icon x candidate, pooled rare icons)", "Value": f"{v_icon_matrix:.3f}"},
               {"Metric": "Chi-squared p-value", "Value": fmt_p(p_icon_matrix)},
               {"Metric": "Note", "Value": note_icon_matrix or "none"}] + top_icon_pmi_rows,
              ["Metric", "Value", "name_candidate", "icon", "count", "pmi"])

    # --- LaTeX report ---
    latex_openers = latex_table(opener_rows, ["name_candidate", "top_opener", "opener_consistency", "corpus_wide_opener_rate",
                                               "opener_lift_vs_baseline", "site_pmi", "icon_pmi", "classifier_score", "verdict"],
                                 ["l", "l", "r", "r", "r", "r", "r", "r", "l"])
    latex_terminals = latex_table(terminal_rows, ["name_candidate", "top_terminal", "terminal_consistency", "n_gold_occurrences"])
    latex_jaccard = latex_table(jaccard_rows, ["pair", "jaccard_top5_openers", "shared_openers"], ["l", "r", "p{0.3\\textwidth}"])
    latex_icon_pmi = latex_table(top_icon_pmi_rows, ["name_candidate", "icon", "count", "pmi"])

    n_with_dominant_opener = sum(1 for r in opener_rows if float(r["opener_consistency"]) >= OPENER_CONSISTENCY_THRESHOLD)

    latex = r"""\section{Name-Triad Classifier System}

Candidates 817, 861, 820 (Mohenjo-daro concentrated) and the compound
405-501 (Harappa, icon Bull1:I concentrated) are tested for classifier-system
structure: a consistent opener per candidate, and divergence (or
convergence) of that opener across candidates. Opener/terminal labels use
only complete, edge-intact inscriptions (truncated texts cannot reliably
supply a true opener or terminal); frequency, site, icon, and material
counts use the full corpus.

\subsection{Opener Consistency and Classifier Score}
Raw opener consistency can be misleadingly high simply because a sign is
the single most common opener in the entire corpus (740 opens """ + f"{opener_base_rate.get('740',0)/n_gold_total:.1%}" + r"""
of \emph{all} complete inscriptions corpus-wide). The \texttt{opener\_lift\_vs\_baseline}
column divides each candidate's observed opener consistency by that
sign's corpus-wide base rate as an opener, so a lift near 1.0 means "no more
consistent than chance given how common that opener already is," while a
high lift means the pairing is specific to this name candidate.
""" + latex_openers + r"""

\subsection{Terminal Sign Consistency}
""" + latex_terminals + r"""

\subsection{Cross-Candidate Opener Overlap (Jaccard of top-5 openers)}
""" + latex_jaccard + r"""

Overall opener distribution across the 4 candidates: Cramer's V = """ + f"{v_opener:.3f}" + r""",
p = """ + fmt_p(p_opener) + r""". Overall terminal distribution: Cramer's V = """ + f"{v_terminal:.3f}" + r""",
p = """ + fmt_p(p_terminal) + r""".

\subsection{Icon $\times$ Name-Candidate Association (top PMI cells)}
Overall matrix Cramer's V = """ + f"{v_icon_matrix:.3f}" + r""", p = """ + fmt_p(p_icon_matrix) + r""".
""" + latex_icon_pmi + r"""

\subsection*{Reading the result}
""" + (
        f"{n_with_dominant_opener} of {len(TARGETS)} name candidates clear the opener-consistency threshold ({OPENER_CONSISTENCY_THRESHOLD:.0%}) for a single dominant opener."
        if n_with_dominant_opener > 0 else
        f"None of the {len(TARGETS)} name candidates clear the opener-consistency threshold ({OPENER_CONSISTENCY_THRESHOLD:.0%}) for a single dominant opener. This is itself informative: it argues against a rigid one-opener-per-name classifier grammar, though it does not rule out a looser, multi-opener classifier system or no classifier function at all."
    ) + r""" A meaningfully nonzero Cramer's V on the cross-candidate opener and
icon matrices indicates these four candidates are not interchangeable with
respect to who introduces them or what icon accompanies them, which is
consistent with -- but does not on its own prove -- a classifier system
distinguishing categories of named entity.
"""
    (out_dir / "name_triad_classifier_system.tex").write_text(latex, encoding="utf-8")
    print("Done. Wrote name_triad_openers.csv, name_triad_terminals.csv, name_triad_opener_jaccard.csv,")
    print("      name_triad_cross_candidate_tests.csv, classifier_system_hypothesis.csv,")
    print("      icon_name_association.csv, name_triad_classifier_system.tex")


if __name__ == "__main__":
    main()
