#!/usr/bin/env python3
"""Proper Name / Filler Candidate Detector (v2 — corrected).

WHAT CHANGED FROM THE PREVIOUS VERSION AND WHY
------------------------------------------------
1. INHERITED ASSUMPTION, MADE EXPLICIT (not fixed, since it cannot be fixed
   by this script alone): the "002 = open-slot classifier marker, signs
   between it and a terminal = filler" parsing convention is a structural
   hypothesis carried over from earlier project stages, not something this
   script discovers independently. Using it to extract candidate fillers is
   fine; using the resulting fillers to later argue "002 must be a
   classifier" or "740/520 must be terminals" would be circular. This
   script does not make that second move, and says so.
2. TERMINAL SET: now a parameter, populated from this corpus's own most
   frequent edge-intact sequence-final signs (see terminal-contrast-model.py)
   rather than the old hardcoded, empirically-wrong {740,520,390,090}.
3. SCORE-ZEROING BUG: the previous formula,
       freq * log(1 + max(0, site_pmi) + max(0, icon_pmi))
   forces the score to exactly zero for any filler that is NOT
   over-represented at one specific site/icon relative to chance -- which
   includes fillers that are genuinely common and widespread (candidate
   titles, common nouns, or very frequent personal names used across many
   communities). It is built to find ONLY localized candidates and silently
   discards everything else, regardless of frequency. This version reports
   frequency, site-concentration, and icon-concentration as separate,
   non-zeroing signals (entropy-based, not single-PMI-based) and produces
   two distinct candidate lists instead of forcing them into one number:
     - "Localized candidates" (low site/icon entropy): plausible personal
       names, family/clan marks, or place-specific toponyms/commodities.
     - "Frequent, widespread candidates" (high frequency, high entropy):
       plausible titles, common nouns, or administrative terms.
   Both lists carry an explicit caveat: localization alone does not prove
   "personal name" -- it is equally consistent with a toponym or a
   commodity name specific to one region.
4. DAMAGE-PLACEHOLDER / AMBIGUOUS-READING handling, as in the other scripts.
5. STATISTICAL GROUNDING: site/icon localization claims are now backed by a
   chi-squared goodness-of-fit test against the corpus-wide site/icon base
   rates (not just a point-estimate entropy number), so "this filler is
   significantly localized" is a testable claim with a p-value attached.
"""

from __future__ import annotations

import argparse
import csv
import math
import re
from collections import Counter, defaultdict
from pathlib import Path

from scipy.stats import chisquare


SIGN_CHUNK_RE = re.compile(r"\d{3,4}(?:/\d{3,4})*")
ILLEGIBLE = "000"
# Populated empirically below from this corpus's own edge-intact final-sign
# frequencies (see terminal-contrast-model.py for the same derivation).
DEFAULT_N_TERMINALS = 8


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


def parse_signs(text: str | None) -> list[str]:
    raw = (text or "").strip()
    tokens: list[str] = []
    for chunk in SIGN_CHUNK_RE.findall(raw):
        sign = chunk.split("/")[0]
        if sign != ILLEGIBLE:
            tokens.append(sign)
    return tokens


def normalized_entropy(counts: Counter[str]) -> float:
    """Shannon entropy of a distribution, normalized to [0, 1] by dividing by
    log2(number of categories). 0 = fully concentrated in one category
    (maximally localized), 1 = perfectly spread across all observed
    categories. Unlike a single max-PMI term, this never collapses to a
    single fixed value just because no one category dominates -- it
    captures the whole shape of the distribution."""
    n = sum(counts.values())
    k = len(counts)
    if n == 0 or k <= 1:
        return 0.0
    h = 0.0
    for c in counts.values():
        p = c / n
        if p > 0:
            h -= p * math.log2(p)
    return h / math.log2(k)


def localization_chi2(observed: Counter[str], base_rates: Counter[str], total_base: int) -> tuple[float, float]:
    """Test whether this filler's site/icon distribution differs
    significantly from the corpus-wide base rate. Returns (chi2, p_value).

    The fully-concentrated case (every occurrence at a single site/icon) is
    a degenerate chi-squared table (one category, zero degrees of freedom),
    so it is handled separately with the exact multinomial probability of
    all n occurrences landing in that one category by chance."""
    n = sum(observed.values())
    if n < 2 or total_base == 0:
        return 0.0, 1.0
    categories = list(observed.keys())
    if len(categories) == 1:
        cat = categories[0]
        p_cat = base_rates.get(cat, 0) / total_base
        if p_cat <= 0:
            return float("inf"), 0.0
        p_value = p_cat ** n
        return float("inf"), p_value
    obs_vec = [observed[c] for c in categories]
    exp_vec = [max(n * (base_rates.get(c, 0) / total_base), 1e-6) for c in categories]
    scale = sum(obs_vec) / sum(exp_vec)
    exp_vec = [e * scale for e in exp_vec]
    try:
        chi2, p = chisquare(obs_vec, f_exp=exp_vec)
    except ValueError:
        return 0.0, 1.0
    return float(chi2), float(p)


def derive_terminal_set(corpus: list[dict[str, str]], n: int = DEFAULT_N_TERMINALS) -> set[str]:
    finals = Counter()
    for row in corpus:
        if row.get("complete") != "Y":
            continue
        raw = (row.get("text") or "").strip()
        if not (raw.startswith("+") and raw.endswith("+")):
            continue
        toks = parse_signs(raw)
        if len(toks) >= 2:
            finals[toks[-1]] += 1
    return {s for s, _ in finals.most_common(n)}


def get_fillers(corpus: list[dict[str, str]], terminal_set: set[str]) -> dict[str, dict]:
    fillers = defaultdict(lambda: {
        "count": 0, "sites": Counter(), "icons": Counter(),
        "terminals": Counter(), "classifiers": Counter(),
    })
    for row in corpus:
        tokens = parse_signs(row.get("text", ""))
        site = row.get("site", "Unknown") or "Unknown"
        icon = row.get("symbol", "Unknown") or "Unknown"

        indices_002 = [i for i, x in enumerate(tokens) if x == "002"]
        for idx in indices_002:
            if idx + 1 >= len(tokens):
                continue
            filler_tokens = []
            term = "END"
            for i in range(idx + 1, len(tokens)):
                if tokens[i] in terminal_set:
                    term = tokens[i]
                    break
                filler_tokens.append(tokens[i])
            if not filler_tokens:
                continue
            filler = "-".join(filler_tokens)
            classifier = "-".join(tokens[:idx]) if idx > 0 else "START"

            data = fillers[filler]
            data["count"] += 1
            data["sites"][site] += 1
            data["icons"][icon] += 1
            data["terminals"][term] += 1
            data["classifiers"][classifier] += 1
    return fillers


def analyze_names(corpus: list[dict[str, str]], out_dir: Path) -> None:
    terminal_set = derive_terminal_set(corpus)
    fillers = get_fillers(corpus, terminal_set)

    site_base = Counter()
    icon_base = Counter()
    for row in corpus:
        site_base[row.get("site", "Unknown") or "Unknown"] += 1
        icon_base[row.get("symbol", "Unknown") or "Unknown"] += 1
    total_base = sum(site_base.values())

    candidates = []
    for filler, data in fillers.items():
        if data["count"] < 2:
            continue
        freq = data["count"]
        site_entropy = normalized_entropy(data["sites"])
        icon_entropy = normalized_entropy(data["icons"])
        top_site = data["sites"].most_common(1)[0]
        top_icon = data["icons"].most_common(1)[0]
        site_chi2, site_p = localization_chi2(data["sites"], site_base, total_base)
        icon_chi2, icon_p = localization_chi2(data["icons"], icon_base, total_base)

        candidates.append({
            "Filler": filler,
            "Frequency": freq,
            "TopSite": top_site[0], "TopSiteCount": top_site[1],
            "SiteEntropy": f"{site_entropy:.3f}", "SiteLocalization_p": f"{site_p:.4f}",
            "TopIcon": top_icon[0], "TopIconCount": top_icon[1],
            "IconEntropy": f"{icon_entropy:.3f}", "IconLocalization_p": f"{icon_p:.4f}",
        })

    write_csv(out_dir / "filler_candidates_full.csv", candidates,
              ["Filler", "Frequency", "TopSite", "TopSiteCount", "SiteEntropy", "SiteLocalization_p",
               "TopIcon", "TopIconCount", "IconEntropy", "IconLocalization_p"])

    localized = [c for c in candidates if float(c["SiteEntropy"]) < 0.5 and float(c["SiteLocalization_p"]) < 0.05]
    localized.sort(key=lambda c: (float(c["SiteEntropy"]), -c["Frequency"]))

    widespread = [c for c in candidates if float(c["SiteEntropy"]) >= 0.7]
    widespread.sort(key=lambda c: -c["Frequency"])

    write_csv(out_dir / "filler_candidates_localized.csv", localized[:30],
              ["Filler", "Frequency", "TopSite", "TopSiteCount", "SiteEntropy", "SiteLocalization_p",
               "TopIcon", "TopIconCount", "IconEntropy", "IconLocalization_p"])
    write_csv(out_dir / "filler_candidates_widespread.csv", widespread[:30],
              ["Filler", "Frequency", "TopSite", "TopSiteCount", "SiteEntropy", "SiteLocalization_p",
               "TopIcon", "TopIconCount", "IconEntropy", "IconLocalization_p"])

    latex_terminals = ", ".join(sorted(terminal_set)) if terminal_set else "(none derived)"
    latex_localized = latex_table(localized[:10],
                                   ["Filler", "Frequency", "TopSite", "SiteEntropy", "SiteLocalization_p"],
                                   ["l", "r", "l", "r", "r"]) if localized else "No statistically localized candidates found."
    latex_widespread = latex_table(widespread[:10],
                                    ["Filler", "Frequency", "TopSite", "SiteEntropy", "SiteLocalization_p"],
                                    ["l", "r", "l", "r", "r"]) if widespread else "No widespread high-frequency candidates found."

    latex = r"""\section{Proper Name / Filler Candidate Detector}

Filler candidates are sign sequences extracted between the classifier marker
``002'' and the next terminal sign (terminal set derived empirically from
this corpus: """ + latex_escape(latex_terminals) + r"""). This parsing
convention is inherited from earlier project stages and is NOT independently
re-derived here; results are conditional on it being correct, and should not
be used to retroactively argue for the terminal/classifier identification
itself -- that would be circular.

We report two separate candidate lists rather than one composite score. A
single multiplicative score that rewards localization and zeroes out
anything not localized would systematically discard common, widespread
fillers regardless of how frequent they are -- which is itself a strong,
unstated assumption about what a name should look like.

\subsection{Localized candidates (low site entropy, $p<0.05$ vs. corpus base rate)}
Plausible personal names, clan marks, or place-specific toponyms/commodities.
Localization alone does not distinguish between these three readings.
""" + latex_localized + r"""

\subsection{Frequent, widespread candidates (site entropy $\geq 0.7$)}
Plausible titles, common nouns, or administrative terms used across many
sites/communities.
""" + latex_widespread + r"""
"""
    (out_dir / "proper_name_detector.tex").write_text(latex, encoding="utf-8")


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

    analyze_names(read_csv(corpus_path), out_dir)
    print("Proper name detection model complete.")


if __name__ == "__main__":
    main()
