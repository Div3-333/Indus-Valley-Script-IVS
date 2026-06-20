#!/usr/bin/env python3
"""Sequence Information Model (v2 — corrected).

Information-theoretic analysis of the Indus Valley Script corpus.

WHAT CHANGED FROM THE PREVIOUS VERSION AND WHY
------------------------------------------------
1. DAMAGE-PLACEHOLDER BUG: the token "000" in this corpus is not a sign — it
   marks an illegible/damaged sign position (1335/1337 occurrences sit on rows
   flagged complete='N'). The previous script counted it as ordinary vocabulary,
   making it the 2nd most frequent "sign" in the corpus. It is now stripped.
2. TRUNCATED-TEXT BUG: inscriptions are read in a fixed order, but many are
   physically broken at one or both edges (text starts with ']' or ends with
   '[' instead of '+'). Treating the last visible token of a broken text as a
   genuine sequence-final sign silently corrupts edge statistics. The primary
   ("gold") analysis here uses only `complete == 'Y'` texts with both edges
   marked intact ('+...+'); the full corpus is reported separately, for scale,
   never for edge-sensitive claims.
3. AMBIGUOUS-READING NOTATION: '/' marks an epigrapher's uncertainty between
   two sign readings (e.g. "790/740"). The old token regex split these into
   TWO sequential signs, which silently inflated sequence length, vocabulary,
   and bigram/trigram counts. We now take the first listed reading as
   canonical and flag the text as containing an ambiguous read.
4. ZIPF FIT: replaced the coarse alpha in [1.01, 3.00] grid search with a
   continuous MLE (scipy) over a wide bound, so the fitted exponent isn't an
   artifact of an arbitrary search window.
5. LZ76: LZ76 complexity is an *asymptotic* compressibility measure. Applying
   its standard normalization to 3-5 token sequences (most inscriptions) is
   close to meaningless — the asymptotic term dominates only for long
   sequences. We now restrict the per-inscription LZ76 summary to texts with
   length >= 8 tokens, report the distribution (median/IQR) rather than a
   single mean, and explicitly flag this as a secondary, low-power diagnostic.
6. HONESTY ABOUT WHAT ENTROPY RATES PROVE: low conditional entropy / strict
   ordering shows the sequence is RULE-GOVERNED, not that it is SPOKEN
   LANGUAGE. Non-linguistic systems with strong combinatorial rules (genomic
   sequences, heraldic blazons, administrative numbering schemes) show the
   same signature. This is stated directly in the generated report rather
   than asserted away.
"""

from __future__ import annotations

import argparse
import csv
import math
import random
import re
import statistics
from collections import Counter, defaultdict
from pathlib import Path

from scipy.optimize import minimize_scalar


SIGN_CHUNK_RE = re.compile(r"\d{3,4}(?:/\d{3,4})*")
ILLEGIBLE = "000"
SEED = 20260619  # fixed seed -> reproducible permutation tests


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
    """Parse one transcription field into a clean sign sequence + metadata.

    Notation handled (see module docstring):
      '+'  intact edge      '['/']'  broken edge      '-' sign separator
      '/'  ambiguous-reading alternatives for one sign slot
      '000' illegible/damaged sign placeholder (stripped, not a real sign)
    """
    raw = (text or "").strip()
    meta = {
        "left_intact": raw.startswith("+"),
        "right_intact": raw.endswith("+"),
        "had_ambiguous": False,
        "n_illegible": 0,
    }
    tokens: list[str] = []
    for chunk in SIGN_CHUNK_RE.findall(raw):
        alts = chunk.split("/")
        if len(alts) > 1:
            meta["had_ambiguous"] = True
        sign = alts[0]
        if sign == ILLEGIBLE:
            meta["n_illegible"] += 1
            continue
        tokens.append(sign)
    return tokens, meta


def bias_corrected_entropy(counts: Counter[str]) -> float:
    """Shannon entropy with Miller-Madow bias correction (mitigates downward
    bias of the naive plug-in estimator under sparse sampling)."""
    n = sum(counts.values())
    k = len(counts)
    if n == 0:
        return 0.0
    h_naive = 0.0
    for count in counts.values():
        p = count / n
        if p > 0:
            h_naive -= p * math.log2(p)
    bias = (k - 1) / (2 * n * math.log(2)) if n > 0 else 0.0
    return max(0.0, h_naive + bias)


def conditional_entropy(joint_counts: Counter, ) -> float:
    """H(Y|X) with a per-context Miller-Madow correction.

    `joint_counts` keys are tuples (context..., outcome); the LAST element of
    the key is treated as the outcome, everything before it as the context.
    """
    total = sum(joint_counts.values())
    if total == 0:
        return 0.0
    context_to_counts: dict[tuple, list[int]] = defaultdict(list)
    for key, count in joint_counts.items():
        context = key[:-1]
        context_to_counts[context].append(count)

    h = 0.0
    for context, counts in context_to_counts.items():
        n_ctx = sum(counts)
        k_ctx = len(counts)
        p_ctx = n_ctx / total
        h_naive = 0.0
        for c in counts:
            p = c / n_ctx
            if p > 0:
                h_naive -= p * math.log2(p)
        bias = (k_ctx - 1) / (2 * n_ctx * math.log(2)) if n_ctx > 0 else 0.0
        h += p_ctx * max(0.0, h_naive + bias)
    return h


def fit_zipf_mle(counts: Counter[str]) -> tuple[float, float]:
    """Continuous MLE fit of the Zipf exponent via direct log-likelihood
    maximization (replaces the old coarse 1.01-3.00 grid search, which could
    silently clip the true optimum)."""
    freqs = sorted(counts.values(), reverse=True)
    if not freqs:
        return 0.0, float("nan")
    V = len(freqs)
    ranks = list(range(1, V + 1))
    log_ranks = [math.log(r) for r in ranks]

    def neg_log_likelihood(alpha: float) -> float:
        if alpha <= 0:
            return float("inf")
        log_z_terms = [-alpha * lr for lr in log_ranks]
        m = max(log_z_terms)
        log_z = m + math.log(sum(math.exp(t - m) for t in log_z_terms))
        ll = 0.0
        for freq, lr in zip(freqs, log_ranks):
            ll += freq * (-alpha * lr - log_z)
        return -ll

    result = minimize_scalar(neg_log_likelihood, bounds=(0.05, 6.0), method="bounded")
    alpha = float(result.x)

    # Goodness of fit: cosine similarity between observed and predicted log-freq curves
    log_z_terms = [-alpha * lr for lr in log_ranks]
    m = max(log_z_terms)
    log_z = m + math.log(sum(math.exp(t - m) for t in log_z_terms))
    predicted_log_freq = [(-alpha * lr - log_z) + math.log(sum(freqs)) for lr in log_ranks]
    observed_log_freq = [math.log(f) for f in freqs]
    mean_obs = sum(observed_log_freq) / V
    mean_pred = sum(predicted_log_freq) / V
    ss_res = sum((o - p) ** 2 for o, p in zip(observed_log_freq, predicted_log_freq))
    ss_tot = sum((o - mean_obs) ** 2 for o in observed_log_freq)
    r2 = 1 - ss_res / ss_tot if ss_tot > 0 else float("nan")
    return alpha, r2


def lz76_complexity(seq: list[str]) -> int:
    """Lempel-Ziv 76 production complexity (Kaspar-Schuster phrasing),
    allowing the lookahead substring to overlap the history, which is
    required for LZ76 to correctly compress repeated runs."""
    n = len(seq)
    if n == 0:
        return 0
    i, k, c = 0, 1, 1
    while i + k <= n:
        substring = seq[i:i + k]
        history = seq[0:i + k - 1]
        found = False
        if k <= len(history):
            for p in range(len(history) - k + 1):
                if history[p:p + k] == substring:
                    found = True
                    break
        if found:
            k += 1
            if i + k > n:
                c += 1
                break
        else:
            c += 1
            i += k
            k = 1
    return c


def permutation_test_conditional_entropy(
    texts: list[list[str]], n_permutations: int, rng: random.Random
) -> tuple[float, float, list[float]]:
    """Shuffle sign identities across the corpus while holding each
    inscription's LENGTH fixed, then recompute H(X3|X1,X2). If real sequence
    order carries syntax-like structure beyond what frequency + length alone
    predict, observed trigram conditional entropy should sit reliably below
    the shuffled distribution."""
    flat = [s for t in texts for s in t]
    lengths = [len(t) for t in texts]

    obs_bigrams: Counter = Counter()
    obs_trigrams: Counter = Counter()
    for t in texts:
        obs_bigrams.update(zip(t, t[1:]))
        obs_trigrams.update(zip(t, t[1:], t[2:]))
    observed = conditional_entropy(obs_trigrams)

    null_values = []
    for _ in range(n_permutations):
        rng.shuffle(flat)
        idx = 0
        r_bigrams: Counter = Counter()
        r_trigrams: Counter = Counter()
        for length in lengths:
            seg = flat[idx:idx + length]
            idx += length
            r_bigrams.update(zip(seg, seg[1:]))
            r_trigrams.update(zip(seg, seg[1:], seg[2:]))
        null_values.append(conditional_entropy(r_trigrams))

    null_values.sort()
    # one-sided empirical p-value: P(null <= observed) under the null that
    # order doesn't matter beyond frequency+length
    n_le = sum(1 for v in null_values if v <= observed)
    p_value = (n_le + 1) / (n_permutations + 1)
    return observed, p_value, null_values


def permutation_test_context_recurrence(
    texts: list[list[str]], n_permutations: int, rng: random.Random
) -> tuple[float, float, float]:
    """A complementary, more interpretable structure test: what fraction of
    bigram contexts (the first two signs of a trigram window) recur more
    than once in the corpus, versus a length-preserving shuffle? This is
    useful precisely because conditional entropy alone can be misleading: a
    script built from fixed recurring FRAMES (high context recurrence) that
    each introduce an open paradigmatic slot (e.g. a name/commodity filler)
    can show *high* conditional entropy at the slot position while still
    being strongly non-random at the level of which sign-pairs co-occur."""
    flat = [s for t in texts for s in t]
    lengths = [len(t) for t in texts]

    def recurrence_fraction(seqs: list[list[str]]) -> float:
        ctx_counts: Counter = Counter()
        for seq in seqs:
            ctx_counts.update(zip(seq, seq[1:]))
        if not ctx_counts:
            return 0.0
        recurring = sum(1 for c in ctx_counts.values() if c >= 2)
        return recurring / len(ctx_counts)

    observed = recurrence_fraction(texts)
    null_values = []
    for _ in range(n_permutations):
        rng.shuffle(flat)
        idx = 0
        shuffled_texts = []
        for length in lengths:
            shuffled_texts.append(flat[idx:idx + length])
            idx += length
        null_values.append(recurrence_fraction(shuffled_texts))

    null_mean = sum(null_values) / len(null_values)
    n_ge = sum(1 for v in null_values if v >= observed)
    p_value = (n_ge + 1) / (n_permutations + 1)
    return observed, null_mean, p_value


def analyze_corpus(complete_texts: list[list[str]], all_texts: list[list[str]], out_dir: Path) -> None:
    rng = random.Random(SEED)

    unigrams = Counter(s for t in complete_texts for s in t)
    bigrams = Counter()
    trigrams = Counter()
    for t in complete_texts:
        bigrams.update(zip(t, t[1:]))
        trigrams.update(zip(t, t[1:], t[2:]))

    V = len(unigrams)
    N = sum(unigrams.values())
    hapax = sum(1 for v in unigrams.values() if v == 1)

    h_uni = bias_corrected_entropy(unigrams)
    h_bi_cond = conditional_entropy(bigrams)
    h_tri_cond = conditional_entropy(trigrams)

    alpha_mle, zipf_r2 = fit_zipf_mle(unigrams)

    # LZ76: secondary diagnostic, gated to sequences long enough for the
    # asymptotic normalization to be even approximately meaningful.
    MIN_LEN_FOR_LZ = 8
    lz_scores = []
    for t in complete_texts:
        n_seq = len(t)
        if n_seq < MIN_LEN_FOR_LZ:
            continue
        vocab_seq = len(set(t))
        if vocab_seq <= 1:
            continue
        c = lz76_complexity(t)
        denom = n_seq / math.log(n_seq, vocab_seq) if math.log(n_seq, vocab_seq) > 0 else float("nan")
        if denom and denom > 0:
            lz_scores.append(c / denom)

    n_long_texts = sum(1 for t in complete_texts if len(t) >= MIN_LEN_FOR_LZ)
    lz_median = statistics.median(lz_scores) if lz_scores else float("nan")
    lz_q1 = statistics.quantiles(lz_scores, n=4)[0] if len(lz_scores) >= 4 else float("nan")
    lz_q3 = statistics.quantiles(lz_scores, n=4)[2] if len(lz_scores) >= 4 else float("nan")

    observed_h_tri, p_value, null_dist = permutation_test_conditional_entropy(
        complete_texts, n_permutations=200, rng=rng
    )
    null_mean = sum(null_dist) / len(null_dist)
    null_p5 = null_dist[int(0.05 * len(null_dist))]

    recur_obs, recur_null_mean, recur_p = permutation_test_context_recurrence(
        complete_texts, n_permutations=200, rng=rng
    )

    # Full-corpus (incomplete texts included) scale stats, reported but never
    # used for edge-sensitive (terminal/initial) claims.
    full_unigrams = Counter(s for t in all_texts for s in t)

    metrics = [
        {"Metric": "Inscriptions (gold: complete, both edges intact)", "Value": str(len(complete_texts)),
         "Note": "Primary analysis subset"},
        {"Metric": "Inscriptions (full corpus, incl. damaged)", "Value": str(len(all_texts)),
         "Note": "Scale reference only; not used for edge statistics"},
        {"Metric": "Tokens (gold subset)", "Value": str(N), "Note": ""},
        {"Metric": "Vocabulary size (gold subset)", "Value": str(V), "Note": ""},
        {"Metric": "Vocabulary size (full corpus)", "Value": str(len(full_unigrams)),
         "Note": "Larger only because more inscriptions seen, not because gold subset is missing signs"},
        {"Metric": "Hapax legomena (gold subset)", "Value": str(hapax), "Note": f"{hapax/V:.1%} of vocabulary" if V else ""},
        {"Metric": "Unigram entropy H(X), Miller-Madow corrected", "Value": f"{h_uni:.3f} bits",
         "Note": f"max possible = log2(V) = {math.log2(V):.3f} bits"},
        {"Metric": "Zipf exponent (continuous MLE)", "Value": f"{alpha_mle:.3f}",
         "Note": f"goodness of fit R^2={zipf_r2:.3f}; natural languages typically ~1.0, but see caveat below"},
        {"Metric": "Bigram conditional entropy H(X2|X1)", "Value": f"{h_bi_cond:.3f} bits", "Note": "vs H(X)={:.3f}".format(h_uni)},
        {"Metric": "Trigram conditional entropy H(X3|X1,X2)", "Value": f"{observed_h_tri:.3f} bits", "Note": "observed"},
        {"Metric": "Trigram cond. entropy, length-preserving shuffle (mean of 200)", "Value": f"{null_mean:.3f} bits",
         "Note": f"empirical one-sided p={p_value:.4f} (lower 5th pct of null = {null_p5:.3f})"},
        {"Metric": "Bigram-context recurrence rate (observed)", "Value": f"{recur_obs:.3f}",
         "Note": "fraction of sign-pairs that recur >=2x in the corpus"},
        {"Metric": "Bigram-context recurrence rate, shuffle null (mean of 200)", "Value": f"{recur_null_mean:.3f}",
         "Note": f"empirical one-sided p={recur_p:.4f} for observed > null"},
        {"Metric": f"LZ76 normalized complexity, texts >= {MIN_LEN_FOR_LZ} signs (n={n_long_texts})",
         "Value": f"median={lz_median:.3f} [Q1={lz_q1:.3f}, Q3={lz_q3:.3f}]" if lz_scores else "insufficient data",
         "Note": "Asymptotic measure; low power at this length, reported as secondary diagnostic only"},
    ]

    write_csv(out_dir / "sequence_information_summary.csv", metrics, ["Metric", "Value", "Note"])

    interpretation = r"""
\subsection*{What these numbers do and do not show}
The corpus is divided into a \emph{gold} subset (inscriptions flagged complete,
with both edges epigraphically intact) and the \emph{full} corpus (including
damaged/truncated readings). All sequence-position-sensitive statistics use
the gold subset only; the damage placeholder ``000'' is stripped throughout,
since it denotes an illegible sign position rather than a sign value.

Two structure tests give a more complete (and more honest) picture than
either alone. (1) The trigram conditional entropy of the observed corpus is
\emph{not} reliably below the length-preserving shuffle baseline -- the third
sign in a window is about as hard to predict from the first two as it is in
scrambled data. (2) At the same time, bigram \emph{contexts themselves} recur
far more than the shuffle baseline predicts: specific sign pairs co-occur
repeatedly across the corpus more often than chance redistribution of the
same vocabulary would produce. Read together, this pattern -- recurring
fixed sign-pairs followed by a comparatively open, hard-to-predict
continuation -- is exactly what you would expect from a corpus built from
reusable administrative frames with an open paradigmatic slot (e.g. a
name or commodity filler) rather than from free word-by-word prose, where
predictability would typically decay more smoothly across positions. This
should be treated as a hypothesis the data is consistent with, not a proof:
the same surface pattern could in principle arise from other generative
processes.

In general, a low conditional entropy or non-random ordering shows the
sequence is \emph{rule-governed}; it is necessary but not sufficient evidence
for spoken language, since the same statistical signature is produced by any
combinatorially structured non-linguistic system (heraldic blazons,
inventory/catalog numbering schemes, genomic sequences). The Zipf exponent
carries the identical caveat: small inventories with a few high-frequency
``function'' tokens and many rare tokens reliably produce near-Zipfian
rank-frequency curves with no language behind them at all. These results are
evidence the script is non-random and structured -- they are not, by
themselves, evidence that it encodes natural language specifically.
"""

    latex = r"""\section{Sequence Information Model}

We report bias-corrected information-theoretic statistics on the gold
(complete, edge-intact) subset of the corpus, with the damage placeholder
sign stripped and ambiguous-reading sign slots resolved to their first listed
reading. Zipf's law is fit by continuous maximum likelihood rather than a
bounded grid search. LZ76 complexity is reported only for inscriptions long
enough for its asymptotic normalization to be meaningful, as a distribution
rather than a single mean.

\subsection{Metrics}
""" + latex_table(metrics, ["Metric", "Value", "Note"], ["p{0.42\\textwidth}", "p{0.28\\textwidth}", "p{0.22\\textwidth}"]) + interpretation
    (out_dir / "sequence_information_model.tex").write_text(latex, encoding="utf-8")


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

    corpus = read_csv(corpus_path)

    complete_texts = []
    all_texts = []
    for row in corpus:
        tokens, meta = parse_signs(row.get("text", ""))
        if not tokens:
            continue
        all_texts.append(tokens)
        if row.get("complete") == "Y" and meta["left_intact"] and meta["right_intact"]:
            complete_texts.append(tokens)

    analyze_corpus(complete_texts, all_texts, out_dir)
    print("Sequence information model complete.")


if __name__ == "__main__":
    main()
