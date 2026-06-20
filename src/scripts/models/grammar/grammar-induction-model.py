#!/usr/bin/env python3
"""Grammar Induction Model (v2 — corrected).

WHAT CHANGED FROM THE PREVIOUS VERSION AND WHY
------------------------------------------------
1. REAL BUG FIXED: the previous bigram conditional-entropy calculation did
       b_x = Counter(y for u, y in bigrams if u == x)
   where `bigrams` is itself a `Counter` keyed by (u, y) tuples. Iterating a
   Counter with `for u, y in bigrams` only unpacks its KEYS -- the actual
   counts are silently discarded, so every observed bigram type is treated
   as if it occurred exactly once. This flattens the real bigram frequency
   distribution to uniform before computing entropy, corrupting the
   Bigram-model row of the whole MDL comparison. Fixed by iterating
   `bigrams.items()` and weighting by the actual count.
2. TWO-PART MDL, NOT JUST PARAMETER-COUNT BIC: the previous version costed
   the Bigram model's complexity as `len(observed_bigrams) - 1` parameters,
   which only charges for ESTIMATING the probabilities of bigrams already
   known to exist -- it never charges for SPECIFYING WHICH bigrams exist out
   of the V^2 possible ordered pairs. That omission can make any model with
   a small "observed support" look artificially cheap. This version uses a
   proper two-part code: StructureCost (bits to specify which combinations
   of the model's parameter space are actually used, via a combinatorial/
   universal code) + ParameterCost (k/2 * log2(N), standard BIC) +
   DataCost (cross-entropy). All four models (Null, Unigram, Bigram,
   Positional Template) are now charged on the same basis.
3. SHIFT-INVARIANCE CRITIQUE ADDRESSED: a template keyed to absolute
   position-from-the-left assumes inscriptions are anchored at their start,
   which is not obviously true when optional prefixes/numerals vary in
   length. We now fit and report position-from-the-LEFT and
   position-from-the-RIGHT template variants separately, and use whichever
   achieves the lower description length as the templatic model's best
   representative -- rather than asserting one anchoring is correct.
4. DAMAGE-PLACEHOLDER / AMBIGUOUS-READING handling, as in the other scripts.
5. Conclusions are phrased comparatively ("X achieves a shorter description
   length than Y under this coding scheme") rather than as a flat claim that
   the winning model IS how the script works -- MDL model selection on a
   corpus this size is informative but not dispositive.
"""

from __future__ import annotations

import argparse
import csv
import math
import re
from collections import Counter
from pathlib import Path

from scipy.special import gammaln


SIGN_CHUNK_RE = re.compile(r"\d{3,4}(?:/\d{3,4})*")
ILLEGIBLE = "000"


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


def entropy(counts: Counter[str]) -> float:
    total = sum(counts.values())
    if total <= 0:
        return 0.0
    h = 0.0
    for count in counts.values():
        p = count / total
        if p > 0:
            h -= p * math.log2(p)
    return h


def log2_choose(n: int, k: int) -> float:
    """log2(C(n,k)) via the log-gamma function, stable for large n, k."""
    if k < 0 or k > n:
        return float("-inf")
    if k == 0 or k == n:
        return 0.0
    ln_choose = gammaln(n + 1) - gammaln(k + 1) - gammaln(n - k + 1)
    return ln_choose / math.log(2)


def structure_cost_bits(support_size: int, total_space: int) -> float:
    """Universal-code cost (bits) of specifying WHICH `support_size` items
    out of `total_space` possible items are the ones actually used by a
    model -- the part of two-part MDL that plain parameter-count BIC skips.
    """
    if total_space <= 0 or support_size <= 0:
        return 0.0
    return max(0.0, log2_choose(total_space, support_size))


def two_part_dl(data_cost: float, support_size: int, total_space: int, n: int) -> dict:
    struct_cost = structure_cost_bits(support_size, total_space)
    param_cost = (max(support_size - 1, 0) / 2) * math.log2(max(n, 2))
    total = data_cost + struct_cost + param_cost
    return {"DataCost": data_cost, "StructureCost": struct_cost, "ParamCost": param_cost, "TotalDL": total,
            "SupportSize": support_size}


def fit_positional_template(texts: list[list[str]], anchor: str, V: int, N: int) -> dict:
    """Fit a fixed-slot positional template, anchored either from the left
    (slot = index from start) or the right (slot = index from end)."""
    max_len = max(len(t) for t in texts)
    slot_counts = {i: Counter() for i in range(max_len)}
    for t in texts:
        seq = t if anchor == "left" else list(reversed(t))
        for i, sign in enumerate(seq):
            slot_counts[i][sign] += 1

    h_pos = 0.0
    support_size = 0
    for i in range(max_len):
        pos_n = sum(slot_counts[i].values())
        if pos_n > 0:
            h_pos += (pos_n / N) * entropy(slot_counts[i])
            support_size += len(slot_counts[i])
    data_cost = N * h_pos
    # Structure space: max_len slots, each could in principle hold any of V
    # signs -> total_space = max_len * V "slot,sign" cells, of which
    # support_size are actually attested.
    total_space = max_len * V
    result = two_part_dl(data_cost, support_size, total_space, N)
    result["Anchor"] = anchor
    result["MaxLen"] = max_len
    return result


def analyze_grammar(corpus: list[dict[str, str]], out_dir: Path) -> None:
    texts = []
    for row in corpus:
        if row.get("complete") != "Y":
            continue
        raw = (row.get("text") or "").strip()
        if not (raw.startswith("+") and raw.endswith("+")):
            continue
        tokens = parse_signs(raw)
        if len(tokens) >= 2:
            texts.append(tokens)

    if not texts:
        print("No complete, edge-intact texts found for grammar induction.")
        return

    unigrams: Counter = Counter()
    bigrams: Counter = Counter()
    for t in texts:
        unigrams.update(t)
        bigrams.update(zip(t, t[1:]))

    V = len(unigrams)
    N = sum(unigrams.values())

    # 1. Null model: uniform over the V observed signs.
    dl_null = two_part_dl(N * math.log2(V) if V > 0 else 0.0, V, V, N)

    # 2. Unigram model.
    h_uni = entropy(unigrams)
    dl_uni = two_part_dl(N * h_uni, V, V, N)

    # 3. Bigram model -- FIXED: weight by actual observed counts, not by
    #    treating every distinct (u, y) pair as count 1.
    h_bi = 0.0
    next_given_prev: dict[str, Counter] = {x: Counter() for x in unigrams}
    for (u, y), c in bigrams.items():
        next_given_prev[u][y] += c
    for x, x_count in unigrams.items():
        h_bi += (x_count / N) * entropy(next_given_prev[x])
    data_cost_bi = N * h_bi
    support_bi = len(bigrams)  # number of distinct (u, y) pairs actually observed
    total_space_bi = V * V  # all possible ordered sign pairs
    dl_bi = two_part_dl(data_cost_bi, support_bi, total_space_bi, N)

    # 4. Positional template, both anchorings; report the better one as the
    #    templatic model's representative, and both for transparency.
    dl_pos_left = fit_positional_template(texts, "left", V, N)
    dl_pos_right = fit_positional_template(texts, "right", V, N)
    dl_pos_best = dl_pos_left if dl_pos_left["TotalDL"] <= dl_pos_right["TotalDL"] else dl_pos_right

    mdl = [
        {"Model": "Null (uniform over observed vocab)", **dl_null},
        {"Model": "Unigram", **dl_uni},
        {"Model": "Bigram (fixed counting bug)", **dl_bi},
        {"Model": "Positional template, left-anchored", **dl_pos_left},
        {"Model": "Positional template, right-anchored", **dl_pos_right},
    ]
    for m in mdl:
        m.pop("Anchor", None)
        m.pop("MaxLen", None)
        m["DataCost"] = f"{m['DataCost']:.1f}"
        m["StructureCost"] = f"{m['StructureCost']:.1f}"
        m["ParamCost"] = f"{m['ParamCost']:.1f}"
        m["TotalDL"] = f"{m['TotalDL']:.1f}"
    mdl.sort(key=lambda x: float(x["TotalDL"]))
    for i, m in enumerate(mdl):
        m["Rank"] = i + 1

    write_csv(out_dir / "mdl_comparison.csv", mdl,
              ["Rank", "Model", "TotalDL", "DataCost", "StructureCost", "ParamCost", "SupportSize"])

    best_overall = mdl[0]["Model"]
    best_template = "left-anchored" if dl_pos_left["TotalDL"] <= dl_pos_right["TotalDL"] else "right-anchored"

    latex = r"""\section{Grammar Induction Model}

Each model is scored with a proper two-part Minimum Description Length code:
\textbf{StructureCost} (bits to specify which combinations of the model's
parameter space are actually used -- via $\log_2 \binom{\text{total space}}{\text{support size}}$),
\textbf{ParamCost} (standard BIC, $\frac{k}{2}\log_2 N$, for estimating the
probabilities of the parameters that ARE used), and \textbf{DataCost}
(cross-entropy of the corpus under the fitted model). Charging all
candidate models on the same two-part basis avoids the artifact where a
model with a small \emph{observed} support looks free simply because nothing
was charged for specifying that support in the first place. The Bigram
row also fixes a counting bug in the previous version, where bigram
frequencies were silently discarded and every observed transition was
(incorrectly) treated as equally likely regardless of how often it actually
occurred.

The positional-template model is fit twice -- anchored from the left edge
and from the right edge of each inscription -- since variable-length
optional prefixes make a single fixed anchoring point a substantive,
testable assumption rather than a free given.

\subsection{Two-part MDL Comparison}
""" + latex_table(mdl, ["Rank", "Model", "TotalDL", "DataCost", "StructureCost", "ParamCost", "SupportSize"],
                   ["c", "p{0.28\\textwidth}", "r", "r", "r", "r", "r"]) + r"""

\subsection*{Reading the result}
The """ + latex_escape(best_overall) + r""" model achieves the shortest description length under this
coding scheme (the """ + latex_escape(best_template) + r""" variant was the stronger of the two template
anchorings). This is evidence about which generative account compresses
this specific corpus better under this specific code -- it is not, by
itself, proof of which process actually produced the script. A corpus this
size (""" + str(N) + r""" tokens across """ + str(len(texts)) + r""" inscriptions) limits how strongly any
single MDL comparison can discriminate between close competitors.
"""
    (out_dir / "grammar_induction_model.tex").write_text(latex, encoding="utf-8")


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

    analyze_grammar(read_csv(corpus_path), out_dir)
    print("Grammar induction model complete.")


if __name__ == "__main__":
    main()
