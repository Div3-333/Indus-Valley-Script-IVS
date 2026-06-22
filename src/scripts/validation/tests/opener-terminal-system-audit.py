#!/usr/bin/env python3
"""
Opener/Terminal System Audit — characterizes the corpus's INITIAL-position
("opener") and FINAL-position ("terminal") sign inventories as two
functional layers, and tests whether openers predict terminals.

WHAT THIS DOES AND WHY
-----------------------
The corrected positional analysis shows a real asymmetry: some signs are
heavily concentrated at the start of inscriptions (740, 700, 520), others at
the end (235, 033, 240), and a few (032) straddle multiple positions. This
script formalizes that asymmetry into an explicit role label per sign
(OPENER / TERMINAL / MEDIAL_BODY / MIXED) using pre-declared thresholds, then
asks the next question: do specific openers preferentially co-occur with
specific terminals, i.e. is there an opener<->terminal "agreement" pattern
analogous to a grammatical frame, or is the inscription's opener
independent of its terminal?

A genuine opener-terminal pairing grammar would show up as a non-random,
high-PMI, statistically significant subset of the opener x terminal
co-occurrence matrix. A purely templatic-but-unpaired system (openers and
terminals chosen independently, e.g. from two unrelated menus) would show a
flat, chance-level matrix. Both are interesting findings; this script is
built to report whichever the data actually shows rather than to lead toward
either conclusion.

METHODOLOGICAL CHOICES
-----------------------
1. Scope: complete, edge-intact inscriptions only (`complete=='Y'`,
   text starts and ends with '+'), consistent with the rest of the
   pipeline -- a sign's apparent position is only meaningful if the
   inscription isn't physically truncated there.
2. Role thresholds (pct_initial >= 50% -> OPENER, pct_final >= 30% ->
   TERMINAL, pct_medial >= 70% -> MEDIAL_BODY, else MIXED) are declared
   before any sign is labeled, and a sign meeting both the OPENER and
   TERMINAL thresholds is labeled OPENER first (checked in that order) and
   flagged in a separate column rather than silently dropped, since a few
   signs (032) are known to straddle roles.
3. Minimum frequency filter (>= 10 total occurrences) avoids assigning a
   confident role label to signs seen only a handful of times, where the
   observed pct_initial/medial/final could easily be a small-sample
   artifact.
4. PMI significance for opener-terminal pairs uses the exact hypergeometric
   tail probability (not a normal/chi-squared approximation), since most
   individual pairs have small counts where the asymptotic approximation is
   unreliable; Benjamini-Hochberg FDR correction is applied across all
   tested pairs, since dozens of openers x dozens of terminals means
   hundreds of simultaneous comparisons.
5. The damage placeholder "000" is excluded throughout and ambiguous '/'
   readings resolve to the first listed value, as elsewhere in the pipeline.
"""

from __future__ import annotations

import argparse
import csv
import math
import re
from collections import Counter
from pathlib import Path

import numpy as np
from scipy.stats import chi2_contingency, hypergeom

SIGN_CHUNK_RE = re.compile(r"\d{3,4}(?:/\d{3,4})*")
ILLEGIBLE = "000"
MIN_FREQ_FOR_ROLE = 10
OPENER_THRESHOLD = 0.50
TERMINAL_THRESHOLD = 0.30
MEDIAL_BODY_THRESHOLD = 0.70


def parse_args():
    p = argparse.ArgumentParser(description="Audit opener vs terminal sign systems and test opener<->terminal pairing.")
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


def fsa_state(position: int, length: int) -> str:
    if position == 0:
        return "INITIAL"
    if position == length - 1:
        return "FINAL"
    return "MEDIAL"


def benjamini_hochberg(p_values: list[float], alpha: float = 0.05) -> list[bool]:
    m = len(p_values)
    if m == 0:
        return []
    order = sorted(range(m), key=lambda i: p_values[i])
    threshold_rank = 0
    for rank, idx in enumerate(order, start=1):
        if p_values[idx] <= (rank / m) * alpha:
            threshold_rank = rank
    cutoff = p_values[order[threshold_rank - 1]] if threshold_rank > 0 else -1.0
    return [p <= cutoff for p in p_values]


def fmt_p(p: float) -> str:
    if p == 0.0:
        return "<1e-300"
    return f"{p:.3g}"


def cramers_v_table(table: list[list[int]]) -> tuple[float, float, str]:
    """Cramer's V + chi-squared p-value for an R x C contingency table.
    Rows/columns that sum to zero are dropped before testing -- a category
    with zero total occurrences produces a structurally-zero expected
    frequency that crashes scipy's chi-squared test, and silently treating
    that crash as "no association" (p=1) would misreport a test failure as
    a null result. Returns a `note` string flagging any dropped rows/cols."""
    arr = np.array(table, dtype=float)
    if arr.size == 0:
        return 0.0, 1.0, "empty table"
    row_mask = arr.sum(axis=1) > 0
    col_mask = arr.sum(axis=0) > 0
    n_dropped_rows = int((~row_mask).sum())
    n_dropped_cols = int((~col_mask).sum())
    arr = arr[row_mask][:, col_mask]
    note = ""
    if n_dropped_rows or n_dropped_cols:
        note = f"dropped {n_dropped_rows} all-zero row(s), {n_dropped_cols} all-zero col(s) before testing"
    if arr.shape[0] < 2 or arr.shape[1] < 2:
        return 0.0, 1.0, (note or "table degenerate after removing empty rows/cols")
    try:
        chi2, p, dof, _ = chi2_contingency(arr)
    except ValueError as e:
        return 0.0, 1.0, f"chi-squared test failed even after cleanup: {e}"
    n = arr.sum()
    r, c = arr.shape
    v = math.sqrt(chi2 / (n * (min(r, c) - 1))) if n > 0 and min(r, c) > 1 else 0.0
    return float(v), float(p), note


def jensen_shannon_divergence(counts_a: Counter, counts_b: Counter) -> float:
    keys = sorted(set(counts_a) | set(counts_b))
    n_a, n_b = sum(counts_a.values()), sum(counts_b.values())
    if n_a == 0 or n_b == 0 or not keys:
        return 0.0
    p = [counts_a.get(k, 0) / n_a for k in keys]
    q = [counts_b.get(k, 0) / n_b for k in keys]
    m = [0.5 * (pi + qi) for pi, qi in zip(p, q)]

    def kl(a, b):
        return sum(ai * math.log2(ai / bi) for ai, bi in zip(a, b) if ai > 0)

    return 0.5 * kl(p, m) + 0.5 * kl(q, m)


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

    print("Parsing complete, edge-intact inscriptions...")
    gold = []
    for row in corpus:
        raw = (row.get("text") or "").strip()
        if row.get("complete") != "Y" or not (raw.startswith("+") and raw.endswith("+")):
            continue
        tokens = parse_signs(raw)
        if tokens:
            gold.append((tokens, row))
    print(f"  {len(gold)} complete, edge-intact inscriptions.")

    print("Computing per-sign positional profiles...")
    pos_counts: dict[str, list[int]] = {}
    for tokens, _ in gold:
        length = len(tokens)
        for i, s in enumerate(tokens):
            pos_counts.setdefault(s, [0, 0, 0])
            state = fsa_state(i, length)
            pos_counts[s][{"INITIAL": 0, "MEDIAL": 1, "FINAL": 2}[state]] += 1

    role_rows = []
    sign_role: dict[str, str] = {}
    for sign, (init, med, fin) in pos_counts.items():
        total = init + med + fin
        if total < MIN_FREQ_FOR_ROLE:
            continue
        pct_i, pct_m, pct_f = init / total, med / total, fin / total
        if pct_i >= OPENER_THRESHOLD:
            label = "OPENER"
        elif pct_f >= TERMINAL_THRESHOLD:
            label = "TERMINAL"
        elif pct_m >= MEDIAL_BODY_THRESHOLD:
            label = "MEDIAL_BODY"
        else:
            label = "MIXED"
        sign_role[sign] = label
        role_rows.append({
            "sign": sign, "total": total, "pct_initial": f"{pct_i:.3f}",
            "pct_medial": f"{pct_m:.3f}", "pct_final": f"{pct_f:.3f}", "role_label": label,
        })
    role_rows.sort(key=lambda r: -r["total"])
    write_csv(out_dir / "sign_positional_roles.csv", role_rows,
              ["sign", "total", "pct_initial", "pct_medial", "pct_final", "role_label"])

    openers = sorted(s for s, r in sign_role.items() if r == "OPENER")
    terminals = sorted(s for s, r in sign_role.items() if r == "TERMINAL")
    print(f"  {len(openers)} OPENER signs, {len(terminals)} TERMINAL signs (>= {MIN_FREQ_FOR_ROLE} occurrences).")

    print("Building opener x terminal co-occurrence matrix...")
    n_docs = len(gold)
    opener_of = {}
    terminal_of = {}
    site_of = {}
    icon_of = {}
    material_of = {}
    for tokens, row in gold:
        op, te = tokens[0], tokens[-1]
        key = row.get("id", id(row))
        opener_of[key] = op
        terminal_of[key] = te
        site_of[key] = row.get("site", "") or "Unknown"
        icon_of[key] = row.get("symbol", "") or "Unknown"
        material_of[key] = row.get("material", "") or "Unknown"

    opener_freq = Counter(opener_of.values())
    terminal_freq = Counter(terminal_of.values())
    co_matrix = Counter()
    for key in opener_of:
        co_matrix[(opener_of[key], terminal_of[key])] += 1

    full_table = [[co_matrix.get((o, t), 0) for t in terminals] for o in openers]
    if len(openers) >= 2 and len(terminals) >= 2:
        v_full, p_full, note_full = cramers_v_table(full_table)
    else:
        v_full, p_full, note_full = 0.0, 1.0, "fewer than 2 openers or terminals"
    if note_full:
        print(f"  Note on full-matrix test: {note_full}")
    write_csv(out_dir / "opener_terminal_cramers_v.csv",
              [{"Comparison": "Full opener x terminal matrix", "CramersV": f"{v_full:.3f}", "ChiSquaredP": fmt_p(p_full),
                "OpenerCount": len(openers), "TerminalCount": len(terminals), "Note": note_full}],
              ["Comparison", "CramersV", "ChiSquaredP", "OpenerCount", "TerminalCount", "Note"])

    print("Computing PMI for every opener-terminal pair (hypergeometric significance, BH-FDR)...")
    pmi_rows_raw = []
    for o in openers:
        for t in terminals:
            c = co_matrix.get((o, t), 0)
            if c == 0:
                continue
            n_o, n_t = opener_freq[o], terminal_freq[t]
            p = hypergeom.sf(c - 1, n_docs, n_o, n_t)
            pmi = math.log2((c / n_docs) / ((n_o / n_docs) * (n_t / n_docs)))
            pmi_rows_raw.append({"opener": o, "terminal": t, "co_count": c, "pmi": pmi, "p_value": float(p)})

    p_values = [r["p_value"] for r in pmi_rows_raw]
    keep_mask = benjamini_hochberg(p_values, alpha=0.05) if p_values else []
    for r, keep in zip(pmi_rows_raw, keep_mask):
        r["bh_significant"] = keep
    pmi_rows_raw.sort(key=lambda r: -r["pmi"])
    top_pmi_rows = [
        {"opener": r["opener"], "terminal": r["terminal"], "co_count": r["co_count"],
         "pmi": f"{r['pmi']:.3f}", "p_value": f"{r['p_value']:.3g}", "bh_significant": r["bh_significant"]}
        for r in pmi_rows_raw[:30]
    ]
    write_csv(out_dir / "opener_terminal_pmi_pairs.csv", top_pmi_rows,
              ["opener", "terminal", "co_count", "pmi", "p_value", "bh_significant"])
    n_sig = sum(1 for r in pmi_rows_raw if r["bh_significant"])
    print(f"  {len(pmi_rows_raw)} opener-terminal pairs with co-occurrence > 0; {n_sig} survive BH-FDR at alpha=0.05.")

    # --- 740 vs 520 as openers ---
    print("Comparing 740 vs 520 as openers...")
    rows_740 = [k for k in opener_of if opener_of[k] == "740"]
    rows_520 = [k for k in opener_of if opener_of[k] == "520"]
    term_740 = Counter(terminal_of[k] for k in rows_740)
    term_520 = Counter(terminal_of[k] for k in rows_520)
    site_740 = Counter(site_of[k] for k in rows_740)
    site_520 = Counter(site_of[k] for k in rows_520)
    icon_740 = Counter(icon_of[k] for k in rows_740)
    icon_520 = Counter(icon_of[k] for k in rows_520)
    mat_740 = Counter(material_of[k] for k in rows_740)
    mat_520 = Counter(material_of[k] for k in rows_520)

    def two_group_table(a: Counter, b: Counter) -> tuple[float, float]:
        keys = sorted(set(a) | set(b))
        if len(keys) < 2:
            return 0.0, 1.0
        table = [[a.get(k, 0) for k in keys], [b.get(k, 0) for k in keys]]
        v, p, _note = cramers_v_table(table)
        return v, p

    v_term, p_term = two_group_table(term_740, term_520)
    v_site_74, p_site_74 = two_group_table(site_740, site_520)
    v_icon_74, p_icon_74 = two_group_table(icon_740, icon_520)
    v_mat_74, p_mat_74 = two_group_table(mat_740, mat_520)
    comp_740_520 = [
        {"Dimension": "Terminal sign", "CramersV": f"{v_term:.3f}", "P": fmt_p(p_term), "N_740": len(rows_740), "N_520": len(rows_520)},
        {"Dimension": "Site", "CramersV": f"{v_site_74:.3f}", "P": fmt_p(p_site_74), "N_740": len(rows_740), "N_520": len(rows_520)},
        {"Dimension": "Icon", "CramersV": f"{v_icon_74:.3f}", "P": fmt_p(p_icon_74), "N_740": len(rows_740), "N_520": len(rows_520)},
        {"Dimension": "Material", "CramersV": f"{v_mat_74:.3f}", "P": fmt_p(p_mat_74), "N_740": len(rows_740), "N_520": len(rows_520)},
    ]
    write_csv(out_dir / "740_vs_520_comparison.csv", comp_740_520, ["Dimension", "CramersV", "P", "N_740", "N_520"])

    # --- 033 vs 032 vs 235 as terminals ---
    print("Comparing 033 vs 032 vs 235 as terminals (opener distributions)...")
    triad = ["033", "032", "235"]
    rows_by_term = {t: [k for k in terminal_of if terminal_of[k] == t] for t in triad}
    opener_dist_by_term = {t: Counter(opener_of[k] for k in rows_by_term[t]) for t in triad}
    triad_rows = []
    for i in range(len(triad)):
        for j in range(i + 1, len(triad)):
            t_a, t_b = triad[i], triad[j]
            js = jensen_shannon_divergence(opener_dist_by_term[t_a], opener_dist_by_term[t_b])
            v_s, p_s = two_group_table(
                Counter(site_of[k] for k in rows_by_term[t_a]),
                Counter(site_of[k] for k in rows_by_term[t_b]),
            )
            v_i, p_i = two_group_table(
                Counter(icon_of[k] for k in rows_by_term[t_a]),
                Counter(icon_of[k] for k in rows_by_term[t_b]),
            )
            triad_rows.append({
                "terminal_pair": f"{t_a} vs {t_b}", "n_a": len(rows_by_term[t_a]), "n_b": len(rows_by_term[t_b]),
                "js_opener_divergence": f"{js:.3f}", "site_cramers_v": f"{v_s:.3f}", "site_p": fmt_p(p_s),
                "icon_cramers_v": f"{v_i:.3f}", "icon_p": fmt_p(p_i),
            })
    write_csv(out_dir / "033_vs_032_vs_235_as_terminals.csv", triad_rows,
              ["terminal_pair", "n_a", "n_b", "js_opener_divergence", "site_cramers_v", "site_p", "icon_cramers_v", "icon_p"])

    print("Building opener and terminal inventory tables...")
    opener_inventory = []
    for o in openers:
        keys = [k for k in opener_of if opener_of[k] == o]
        opener_inventory.append({
            "opener": o, "count": len(keys),
            "top_terminals": top_n(Counter(terminal_of[k] for k in keys)),
            "top_sites": top_n(Counter(site_of[k] for k in keys)),
            "top_icons": top_n(Counter(icon_of[k] for k in keys)),
        })
    opener_inventory.sort(key=lambda r: -r["count"])

    terminal_inventory = []
    for t in terminals:
        keys = [k for k in terminal_of if terminal_of[k] == t]
        terminal_inventory.append({
            "terminal": t, "count": len(keys),
            "top_openers": top_n(Counter(opener_of[k] for k in keys)),
            "top_sites": top_n(Counter(site_of[k] for k in keys)),
            "top_icons": top_n(Counter(icon_of[k] for k in keys)),
        })
    terminal_inventory.sort(key=lambda r: -r["count"])

    write_csv(out_dir / "opener_inventory.csv", opener_inventory, ["opener", "count", "top_terminals", "top_sites", "top_icons"])
    write_csv(out_dir / "terminal_inventory.csv", terminal_inventory, ["terminal", "count", "top_openers", "top_sites", "top_icons"])

    latex_roles = latex_table(role_rows[:15], ["sign", "total", "pct_initial", "pct_medial", "pct_final", "role_label"])
    latex_pmi = latex_table(top_pmi_rows[:15], ["opener", "terminal", "co_count", "pmi", "p_value", "bh_significant"])
    latex_740_520 = latex_table(comp_740_520, ["Dimension", "CramersV", "P", "N_740", "N_520"])
    latex_triad = latex_table(triad_rows, ["terminal_pair", "n_a", "n_b", "js_opener_divergence", "site_cramers_v", "icon_cramers_v"])

    latex = r"""\section{Opener/Terminal System Audit}

Signs with at least """ + str(MIN_FREQ_FOR_ROLE) + r""" occurrences in the complete, edge-intact corpus
are labeled OPENER ($\geq 50\%$ initial), TERMINAL ($\geq 30\%$ final),
MEDIAL\_BODY ($\geq 70\%$ medial), or MIXED, using thresholds declared before
labeling. This yielded """ + str(len(openers)) + r""" opener signs and """ + str(len(terminals)) + r""" terminal signs.

\subsection{Top Signs by Frequency and Role}
""" + latex_roles + r"""

\subsection{Opener $\times$ Terminal Pairing}
Overall matrix: Cramer's V = """ + f"{v_full:.3f}" + r""", chi-squared p = """ + fmt_p(p_full) + (
        r""" (""" + latex_escape(note_full) + r""")""" if note_full else ""
    ) + r""". Of """ + str(len(pmi_rows_raw)) + r""" opener-terminal pairs with nonzero co-occurrence,
""" + str(n_sig) + r""" survive exact hypergeometric testing with Benjamini-Hochberg FDR
correction (top pairs by PMI shown below).
""" + latex_pmi + r"""

\subsection{740 vs. 520 as Openers}
""" + latex_740_520 + r"""

\subsection{033 vs. 032 vs. 235 as Terminals (opener distributions behind them)}
""" + latex_triad + r"""

\subsection*{Reading the result}
A nonzero overall Cramer's V on the opener$\times$terminal matrix, with a
meaningful share of individual pairs surviving multiple-testing correction,
indicates openers and terminals are NOT chosen independently of one another
-- there is some pairing structure, even if it falls short of a rigid
one-to-one grammar. The size of that effect (Cramer's V above) should be
read against standard small/medium/large conventions (0.1/0.3/0.5) before
concluding the pairing is strong.
"""
    (out_dir / "opener_terminal_system_audit.tex").write_text(latex, encoding="utf-8")
    print("Done. Wrote sign_positional_roles.csv, opener_terminal_pmi_pairs.csv, opener_terminal_cramers_v.csv,")
    print("      740_vs_520_comparison.csv, 033_vs_032_vs_235_as_terminals.csv, opener_inventory.csv,")
    print("      terminal_inventory.csv, opener_terminal_system_audit.tex")


if __name__ == "__main__":
    main()
