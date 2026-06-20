#!/usr/bin/env python3
"""Terminal Contrast Model (v2 — corrected).

WHAT CHANGED FROM THE PREVIOUS VERSION AND WHY
------------------------------------------------
1. WRONG TERMINAL SET: the previous script hardcoded
   TERMINAL_FAMILY = {"740","520","400","151","156","527"} as "the" terminal
   signs to contrast. Once you (a) restrict to inscriptions whose RIGHT edge
   is epigraphically intact (otherwise the last visible token is an artifact
   of breakage, not the true terminal) and (b) strip the "000"
   illegible-sign placeholder, the empirical most-frequent sequence-final
   signs in this corpus are NOT 740/520 -- those two are actually among the
   most frequent INITIAL signs. This version derives the terminal candidate
   set empirically from the cleaned, edge-intact corpus instead of assuming
   it, and reports the initial-position distribution alongside the final
   one so the asymmetry is visible rather than hidden.
2. AMBIGUOUS-READING NOTATION ('/'): resolved to first listed reading.
3. CONCEPTUAL FIX -- H1 vs H2 UNDERDETERMINATION: the previous script scored
   "Allographic Variation" (H1: same underlying sign, different glyph) against
   "Grammatical Contrast" (H2: distinct morphemes, e.g. case suffixes) using
   stem-overlap as if it could discriminate between them. It cannot: two
   grammatical case suffixes attaching to the same set of stems would produce
   the *same* high-stem-overlap signature as two graphic variants of one
   sign. This version says so explicitly and adds one discriminating signal
   that distributional overlap alone doesn't give: whether the two
   candidate terminals ever co-occur in the SAME inscription. True
   allographs of one underlying sign should essentially never appear
   together in one text (a scribe doesn't write the "same sign" twice with
   two different glyphs side by side); distinct grammatical morphemes
   attaching to different stems within one longer text legitimately could.
   This narrows -- but does not fully resolve -- the question.
4. Hard "Supported / Rejected" verdicts are replaced with descriptive
   findings plus an explicit reading of what each piece of evidence does and
   does not establish, since a single distributional study on a sparse
   corpus cannot adjudicate a long-open linguistic question with binary
   certainty.
"""

from __future__ import annotations

import argparse
import csv
import math
import random
import re
from collections import Counter, defaultdict
from pathlib import Path

from scipy.stats import chi2_contingency


SIGN_CHUNK_RE = re.compile(r"\d{3,4}(?:/\d{3,4})*")
ILLEGIBLE = "000"
SEED = 20260619
N_TERMINAL_CANDIDATES = 8  # top-K most frequent sequence-final signs to contrast


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
    replacements = {"\\": "/", "_": r"\_", "%": r"\%", "&": r"\&", "#": r"\#", "$": r"\$", "{": r"\{", "}": r"\}"}
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


def parse_signs(text: str | None) -> tuple[list[str], dict]:
    raw = (text or "").strip()
    meta = {"left_intact": raw.startswith("+"), "right_intact": raw.endswith("+")}
    tokens: list[str] = []
    for chunk in SIGN_CHUNK_RE.findall(raw):
        sign = chunk.split("/")[0]
        if sign != ILLEGIBLE:
            tokens.append(sign)
    return tokens, meta


def chi_squared_with_p(dist_a: Counter[str], dist_b: Counter[str]) -> tuple[float, float, float]:
    """Exact chi-squared statistic + asymptotic p-value via scipy, plus
    Cramer's V. Falls back gracefully on degenerate tables."""
    keys = sorted(set(dist_a.keys()) | set(dist_b.keys()))
    if len(keys) < 2:
        return 0.0, 0.0, 1.0
    table = [[dist_a[k] for k in keys], [dist_b[k] for k in keys]]
    n_a, n_b = sum(table[0]), sum(table[1])
    total = n_a + n_b
    if total == 0 or n_a == 0 or n_b == 0:
        return 0.0, 0.0, 1.0
    try:
        chi2, p, dof, expected = chi2_contingency(table)
    except ValueError:
        return 0.0, 0.0, 1.0
    v = math.sqrt(chi2 / total) if total > 0 else 0.0
    return chi2, v, p


def monte_carlo_p_value(dist_a: Counter[str], dist_b: Counter[str], rng: random.Random, num_permutations: int = 1000) -> float:
    """Empirical permutation p-value as a robustness check alongside the
    asymptotic chi-squared p-value (the asymptotic test can be unreliable
    with many sparse cells)."""
    n_a, n_b = sum(dist_a.values()), sum(dist_b.values())
    total = n_a + n_b
    if total == 0:
        return 1.0
    chi2_obs, _, _ = chi_squared_with_p(dist_a, dist_b)
    if chi2_obs == 0:
        return 1.0
    pooled = []
    for k, v in dist_a.items():
        pooled.extend([k] * v)
    for k, v in dist_b.items():
        pooled.extend([k] * v)
    exceed = 0
    for _ in range(num_permutations):
        rng.shuffle(pooled)
        sim_a = Counter(pooled[:n_a])
        sim_b = Counter(pooled[n_a:])
        chi2_sim, _, _ = chi_squared_with_p(sim_a, sim_b)
        if chi2_sim >= chi2_obs:
            exceed += 1
    return exceed / num_permutations


def dist_overlap(dist_a: Counter[str], dist_b: Counter[str]) -> float:
    n_a, n_b = sum(dist_a.values()), sum(dist_b.values())
    if n_a == 0 or n_b == 0:
        return 0.0
    keys = set(dist_a.keys()) | set(dist_b.keys())
    return sum(min(dist_a[k] / n_a, dist_b[k] / n_b) for k in keys)


def analyze_terminals(corpus: list[dict[str, str]], out_dir: Path) -> None:
    rng = random.Random(SEED)

    gold_texts_meta = []
    for row in corpus:
        tokens, meta = parse_signs(row.get("text", ""))
        if row.get("complete") == "Y" and meta["left_intact"] and meta["right_intact"] and len(tokens) >= 2:
            gold_texts_meta.append((tokens, row))

    final_signs = Counter(tokens[-1] for tokens, _ in gold_texts_meta)
    initial_signs = Counter(tokens[0] for tokens, _ in gold_texts_meta)

    asymmetry_rows = []
    all_signs = set(final_signs) | set(initial_signs)
    total_final = sum(final_signs.values())
    total_initial = sum(initial_signs.values())
    for sign in sorted(all_signs, key=lambda s: final_signs[s], reverse=True)[:20]:
        asymmetry_rows.append({
            "Sign": sign,
            "FinalCount": final_signs[sign], "FinalRate": f"{final_signs[sign]/total_final:.3f}" if total_final else "0",
            "InitialCount": initial_signs[sign], "InitialRate": f"{initial_signs[sign]/total_initial:.3f}" if total_initial else "0",
        })
    write_csv(out_dir / "initial_vs_final_position_profile.csv", asymmetry_rows,
              ["Sign", "FinalCount", "FinalRate", "InitialCount", "InitialRate"])

    terminal_candidates = [s for s, _ in final_signs.most_common(N_TERMINAL_CANDIDATES)]

    terminal_contexts = defaultdict(lambda: {
        "sites": Counter(), "regions": Counter(), "materials": Counter(),
        "types": Counter(), "symbols": Counter(), "prec_signs": Counter(),
        "lengths": Counter(), "texts": [],
    })
    for tokens, row in gold_texts_meta:
        term = tokens[-1]
        if term in terminal_candidates:
            ctx = terminal_contexts[term]
            ctx["sites"][row.get("site", "")] += 1
            ctx["regions"][row.get("region", "")] += 1
            ctx["materials"][row.get("material", "")] += 1
            ctx["types"][row.get("type", "")] += 1
            ctx["symbols"][row.get("symbol", "")] += 1
            ctx["prec_signs"][tokens[-2]] += 1
            ctx["lengths"][str(len(tokens))] += 1
            ctx["texts"].append(frozenset(tokens))

    comparisons = []
    co_occurrence_rows = []
    for i in range(len(terminal_candidates)):
        for j in range(i + 1, len(terminal_candidates)):
            t_a, t_b = terminal_candidates[i], terminal_candidates[j]
            ctx_a, ctx_b = terminal_contexts[t_a], terminal_contexts[t_b]

            for dim in ["sites", "regions", "materials", "types", "symbols", "prec_signs", "lengths"]:
                dist_a, dist_b = ctx_a[dim], ctx_b[dim]
                if sum(dist_a.values()) + sum(dist_b.values()) > 10:
                    chi2, cramers_v, p_asymp = chi_squared_with_p(dist_a, dist_b)
                    p_mc = monte_carlo_p_value(dist_a, dist_b, rng, num_permutations=500)
                    overlap = dist_overlap(dist_a, dist_b)
                    comparisons.append({
                        "TerminalA": t_a, "TerminalB": t_b, "Dimension": dim,
                        "Overlap": f"{overlap:.3f}", "ChiSquared": f"{chi2:.1f}",
                        "CramersV": f"{cramers_v:.3f}", "P_Asymptotic": f"{p_asymp:.3f}",
                        "P_MonteCarlo": f"{p_mc:.3f}",
                    })

            n_a_texts, n_b_texts = len(ctx_a["texts"]), len(ctx_b["texts"])
            both = sum(1 for t in ctx_a["texts"] if t_b in t) if n_a_texts else 0
            co_occurrence_rows.append({
                "TerminalA": t_a, "TerminalB": t_b,
                "TextsWithA": n_a_texts, "TextsWithB": n_b_texts,
                "TextsWithBoth": both,
                "CoOccurrenceRate": f"{both / n_a_texts:.3f}" if n_a_texts else "0",
            })

    write_csv(out_dir / "terminal_distributional_comparison.csv", comparisons,
              ["TerminalA", "TerminalB", "Dimension", "Overlap", "ChiSquared", "CramersV", "P_Asymptotic", "P_MonteCarlo"])
    write_csv(out_dir / "terminal_cooccurrence_check.csv", co_occurrence_rows,
              ["TerminalA", "TerminalB", "TextsWithA", "TextsWithB", "TextsWithBoth", "CoOccurrenceRate"])

    findings = []
    if len(terminal_candidates) >= 2:
        t1, t2 = terminal_candidates[0], terminal_candidates[1]
        ctx1, ctx2 = terminal_contexts[t1], terminal_contexts[t2]
        overlap_prec = dist_overlap(ctx1["prec_signs"], ctx2["prec_signs"])
        _, v_icon, p_icon = chi_squared_with_p(ctx1["symbols"], ctx2["symbols"])
        _, v_site, p_site = chi_squared_with_p(ctx1["sites"], ctx2["sites"])
        co_row = next((r for r in co_occurrence_rows if {r["TerminalA"], r["TerminalB"]} == {t1, t2}), None)
        co_rate = float(co_row["CoOccurrenceRate"]) if co_row else float("nan")

        findings = [
            {"Question": f"Do {t1} and {t2} attach to the same preceding stems?",
             "Evidence": f"Distributional overlap of preceding sign = {overlap_prec:.3f} (1.0 = identical)",
             "Reading": "High overlap is consistent with EITHER allography OR grammatical alternation on shared stems -- it cannot distinguish them."},
            {"Question": f"Are {t1} / {t2} biased toward particular sites?",
             "Evidence": f"Cramer's V = {v_site:.3f}, chi-squared p = {p_site:.3f}",
             "Reading": "Low V / high p argues against a purely regional-dialect explanation; high V / low p would support one."},
            {"Question": f"Are {t1} / {t2} biased toward particular icons/seal symbols?",
             "Evidence": f"Cramer's V = {v_icon:.3f}, chi-squared p = {p_icon:.3f}",
             "Reading": "Low V / high p argues against a clan/title-marking explanation; high V / low p would support one."},
            {"Question": f"Do {t1} and {t2} ever terminate / appear within the SAME inscription?",
             "Evidence": f"Co-occurrence rate (texts containing {t1} that also contain {t2}) = {co_rate:.3f}" if co_row else "insufficient data",
             "Reading": "Near-zero co-occurrence is consistent with allography (one underlying sign, two glyphs, never doubled); non-trivial co-occurrence is INCONSISTENT with simple allography and favors distinct lexical/grammatical signs."},
        ]
        write_csv(out_dir / "terminal_hypothesis_scores.csv", findings, ["Question", "Evidence", "Reading"])

    latex_top = latex_table(
        [{"Sign": r["Sign"], "FinalRate": r["FinalRate"], "InitialRate": r["InitialRate"]} for r in asymmetry_rows[:10]],
        ["Sign", "FinalRate", "InitialRate"],
    )
    latex_findings = latex_table(findings, ["Question", "Evidence", "Reading"],
                                  ["p{0.3\\textwidth}", "p{0.28\\textwidth}", "p{0.32\\textwidth}"]) if findings else "No findings (insufficient terminal candidates)."

    latex = r"""\section{Terminal Contrast Model}

Terminal candidates are derived empirically from the corpus, restricted to
inscriptions with both edges epigraphically intact (\texttt{complete='Y'}
and both transcription boundaries marked '+'), with the illegible-sign
placeholder stripped. The top sequence-final signs in this corpus are
\textbf{not} the signs assumed in earlier analyses: those signs are in fact
disproportionately \emph{initial}-position signs here, not terminal ones.

\subsection{Initial vs. Final Position Rates (Top 10 by Final Frequency)}
""" + latex_top + r"""

\subsection{Diagnostic Findings on the Two Most Frequent Terminal Candidates}
""" + latex_findings + r"""

\subsection*{Why this stops short of a verdict}
Distributional overlap in preceding stems cannot, on its own, distinguish
graphic allography from grammatical alternation: both predict the same
overlap pattern. The co-occurrence-within-one-text check narrows the
question without fully resolving it. We report this explicitly rather than
assign a confident Supported/Rejected verdict that the evidence does not
support.
"""
    (out_dir / "terminal_contrast_model.tex").write_text(latex, encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data", default="data", help="Directory containing corpus")
    parser.add_argument("--outputs", default="outputs", help="Directory for outputs")
    args = parser.parse_args()

    data_dir = Path(args.data)
    out_dir = Path(args.outputs)
    out_dir.mkdir(parents=True, exist_ok=True)

    corpus_path = data_dir / "ivs_corpus_cleaned.csv"
    if not corpus_path.exists():
        print(f"Error: {corpus_path} not found.")
        return

    analyze_terminals(read_csv(corpus_path), out_dir)
    print("Terminal contrast model complete.")


if __name__ == "__main__":
    main()
