# Claude Web Prompt — IVS Decipherment: Next 3 Scripts (CORRECTED)

> Paste this entire document into Claude web. It is self-contained and verified
> directly against the raw corpus.

---

## Context

I am working on a computational decipherment project for the **Indus Valley
Script (IVS)**. I have a corrected Python pipeline of 5 core scripts that
analyze ~5500 inscriptions. I need 3 new scripts. Every claim below has been
verified live against the raw corpus — nothing is assumed from prior scripts.

---

## Corpus Format

Main file: `ivs_corpus_cleaned.csv`. Each row = one inscription.

| Column | Meaning |
|---|---|
| `text` | Signs as codes, e.g. `+240-176-740+`. `+` = intact edge, `[`/`]` = broken. Signs separated by `-`. `000` = damaged placeholder. `790/740` = epigraphic uncertainty. |
| `site` | Site name (Mohenjo-daro, Harappa, Kalibangan, Lothal, Chanhu-daro, …) |
| `symbol` | Iconographic seal symbol (Bull1, Elep, Gaur, Rhino, Scene, …) — often blank |
| `complete` | `Y` = both edges intact, `N` = broken |
| `class` | Artifact class (SC=seal, PN=pottery mark, TAG, …) |
| `material` | Steatite, Clay, Copper, … |
| `text length` | Number of sign positions |

**Parsing rules (critical):**
- Strip `+`, `[`, `]` before parsing
- For `790/740` take the **first** value as canonical; flag text as ambiguous
- `000` = damage placeholder — **exclude from all analysis**
- "Complete" for edge-sensitive analysis = `complete == 'Y'` AND text starts
  with `+` AND ends with `+`

---

## Verified Positional Facts (computed live from 3,672 complete inscriptions)

This is ground truth. Do not invert these.

| Sign | INITIAL | MEDIAL | FINAL | %Initial | %Final | Role |
|---|---|---|---|---|---|---|
| **740** | 938 | 410 | 6 | **69%** | 0.4% | Strongly **INITIAL/opener** |
| **700** | 377 | 23 | 77 | **79%** | 16% | Strongly **INITIAL** |
| **520** | 214 | 37 | 2 | **85%** | 0.8% | Strongly **INITIAL/opener** |
| **002** | 38 | 564 | 10 | 6% | 2% | Strongly **MEDIAL/body** |
| **032** | 90 | 208 | 158 | 20% | 35% | **Polyfunctional** (all 3) |
| **033** | 74 | 167 | 166 | 18% | 41% | **Terminal-leaning** |
| **240** | 3 | 210 | 67 | 1% | **24%** | **Terminal-leaning** |
| **235** | 2 | 112 | 82 | 1% | **42%** | **Strongly terminal** |

**Key interpretive facts:**
- 740 and 520 are **initial/opener** signs — they begin inscriptions
- 240 and 235 are **terminal** signs — they end inscriptions
- 032 and 033 cluster together positionally (both polyfunctional, with terminal lean)
- 002 is a medial body sign — a "connector" or "frame filler"

---

## What the 5 Corrected Core Scripts Actually Found

### 1. Sequence Information Model (`sequence-information-model.py`)
- 3,672 complete inscriptions, 13,638 tokens, vocabulary 663 signs
- Unigram entropy H(X) = **6.956 bits** (Miller-Madow corrected)
- Bigram conditional entropy H(X₂|X₁) = **3.898 bits**
- Trigram conditional entropy H(X₃|X₁,X₂) = **1.620 bits** (observed)
  vs. 1.240 bits (shuffled null) — empirical p = 1.000 (**not** significant;
  the observed is *higher* than shuffled, not lower — sequence is more complex
  than random at trigram scale)
- Zipf exponent (continuous MLE) = **1.008**, R² = 0.683
- Hapax legomena = 221 signs (33% of vocabulary)
- LZ76 complexity (texts ≥ 8 signs, n=177): median 1.111 — secondary,
  low-power diagnostic only

### 2. Sign Co-occurrence Network (`sign-cooccurrence-network.py`)
- 846 statistically significant sign pairs (hypergeometric + BH-FDR, PMI > 0)
- 318 signs with ≥ 1 retained edge
- **16 communities** (Louvain)
- Community C5 contains: 025, 027, 028, **032**, **033**, 034, 059, 159, 205,
  226 — the polyfunctional/terminal cluster
- Top PageRank in C5: 032, 033, 700, 575, 491

### 3. Terminal Contrast Model (`terminal-contrast-model.py`)
- Focus signs: **032 vs 033** (the actual terminal candidates by position data)
- Distributional overlap of preceding signs between 032 and 033 = **0.605**
  (1.0 = identical)
- Cramér's V for site difference = 0.275 (chi-squared p = 0.017)
- Cramér's V for icon difference = 0.337 (chi-squared p = 0.098)
- Co-occurrence rate (texts containing both 032 and 033) = **0.006**
  → near-zero, consistent with allography or complementary distribution

### 4. Proper Name Detector (`proper-name-detector.py`)
Top name candidates (PMI-based site and icon localization):

| Rank | Filler | Freq | TopSite | SitePMI | TopIcon | IconPMI |
|---|---|---|---|---|---|---|
| 1 | **817** | 149 | Mohenjo-daro | 0.647 | — | — |
| 2 | **861** | 141 | Mohenjo-daro | 0.690 | — | — |
| 3 | **405-501** | 29 | Harappa | 1.064 | Bull1:I | **5.187** |
| 4 | **000**¹ | 49 | Harappa | — | — | — |
| 5 | **820** | 94 | Mohenjo-daro | 0.593 | — | — |
| 6 | **056-091** | 8 | Kalibangan | 4.744 | Bull1 | 3.771 |

¹ 000 ranked high because the model didn't fully exclude damage tokens —
treat this row as an artifact.

### 5. Grammar Induction Model (`grammar-induction-model.py`)
MDL comparison (lower = better):

| Rank | Model | Total DL |
|---|---|---|
| 1 | **Unigram** | 95,764 |
| 2 | Bigram | 96,842 |
| 3 | Positional template (left-anchored) | 99,384 |
| 4 | Positional template (right-anchored) | 102,084 |
| 5 | Null (uniform) | 128,068 |

**Unigram wins** — meaning the script is NOT free-flowing language. Global
sign-frequency templates dominate; local pairwise dependencies add cost.
**There is no FSA in these results.** Any `induced_fsa_transitions.csv`
file in the repo is a leftover from a previous (discredited) Gemini-generated
script — not from the corrected pipeline.

---

## The 3 Scripts Needed

All scripts must follow the existing codebase style:
- `#!/usr/bin/env python3` shebang
- `argparse` with `--data DATA` (default `data`) and `--outputs OUTPUTS`
  (default `outputs`)
- Load from `{data}/ivs_corpus_cleaned.csv`
- Write CSVs + a `.tex` section to `{outputs}/`
- `000` tokens excluded everywhere
- Ambiguous readings: take first value
- No hardcoded paths
- `print()` progress statements
- scipy/numpy only for stats — no statsmodels
- Report effect sizes (Cramér's V, Cohen's d, etc.) alongside p-values
- Docstring explaining what changed from naïve approaches and why

---

### Script 1: `sign-032-role-splitter.py`

**Goal:** Sign 032 appears in INITIAL (20%), MEDIAL (46%), and FINAL (35%)
positions. Until its roles are functionally separated, it acts as noise in
every downstream model. This script tests whether the three positional
usages are statistically distinct functions or the same sign used freely.

**Method:**

1. Parse all complete inscriptions (`complete == Y`, `+...+`).

2. For every occurrence of sign 032, record:
   - `fsa_state`: INITIAL (position 0), MEDIAL (any middle position), or
     FINAL (last position)
   - `preceding_sign`: sign at position − 1, or `START` if position 0
   - `following_sign`: sign at position + 1, or `END` if last
   - `terminal_sign`: the last sign of the inscription
   - `opener_sign`: the first sign of the inscription
   - `site`, `symbol` (icon), `material`

3. Build a context profile per role (INITIAL-032, MEDIAL-032, FINAL-032):
   - Top-10 preceding signs with frequencies
   - Top-10 following signs with frequencies
   - Site distribution
   - Icon distribution
   - Terminal sign distribution (which sign ends the inscription)
   - Opener sign distribution (which sign begins the inscription)

4. **Distinctiveness tests** for every role pair:
   - Jensen-Shannon divergence of preceding-sign distributions
   - Jensen-Shannon divergence of following-sign distributions
   - Chi-squared + Cramér's V on site distributions
   - Chi-squared + Cramér's V on icon distributions
   - If JS divergence > 0.3 for BOTH preceding AND following: flag `DISTINCT`

5. **Role verdict**: `SPLIT` if any pair is DISTINCT, `UNIFIED` otherwise.
   If SPLIT, specify which roles to separate.

**Outputs:**
- `032_role_occurrences.csv`: one row per 032 occurrence —
  `inscription_id, position, fsa_state, preceding_sign, following_sign,
  opener_sign, terminal_sign, site, icon`
- `032_role_summary.csv`: one row per role —
  `role, count, pct_of_total, top_preceding, top_following, top_terminal,
  top_opener, site_cramers_v, icon_cramers_v, distinct_from`
- `032_role_split_recommendation.csv`: verdict row —
  `role_pair, js_preceding, js_following, site_cramers_v, verdict`
- `sign_032_role_split.tex`: LaTeX section

**Honesty requirement:** If the roles are statistically indistinguishable,
report `UNIFIED` and explain why forcing a split would be wrong.

---

### Script 2: `opener-terminal-system-audit.py`

**Goal:** The corpus has a clear functional asymmetry: some signs are
strongly INITIAL (740=69%, 520=85%, 700=79%), others are strongly FINAL
(235=42%, 033=41%, 240=24%). This script characterizes the **opener system**
and the **terminal system** as two complementary functional layers — and tests
whether openers predict terminals (i.e., is there an opener↔terminal pairing
grammar?).

**Method:**

1. From all complete inscriptions, compute the full positional profile for
   every sign with ≥ 10 total occurrences:
   - `pct_initial`, `pct_medial`, `pct_final`
   - Label as `OPENER` if pct_initial ≥ 50%, `TERMINAL` if pct_final ≥ 30%,
     `MEDIAL_BODY` if pct_medial ≥ 70%, `MIXED` otherwise

2. **Opener inventory**: For all `OPENER` signs, compute:
   - The distribution of terminal signs in inscriptions they open
   - The distribution of sites
   - The distribution of icons

3. **Terminal inventory**: For all `TERMINAL` signs, compute:
   - The distribution of opener signs in inscriptions they close
   - The distribution of sites
   - The distribution of icons

4. **Opener↔terminal pairing test**: Build a co-occurrence matrix:
   `opener × terminal` — count inscriptions containing both.
   - Compute chi-squared + Cramér's V on the full matrix
   - Identify the top 10 (opener, terminal) pairs by PMI:
     PMI(o, t) = log2[ P(o,t) / (P(o) * P(t)) ]
   - A high PMI pair means this opener selects this terminal non-randomly

5. **Comparison: 740 vs 520 as openers**:
   - Do inscriptions opened by 740 end with different terminals than
     inscriptions opened by 520? (Chi-squared on terminal distributions)
   - Do they differ by site, icon, or material?

6. **Comparison: 033 vs 032 vs 235 as terminals**:
   - Do inscriptions ending in 033 have different openers than those ending
     in 032 or 235?
   - JS divergence of opener distributions across the three terminals

**Outputs:**
- `sign_positional_roles.csv`: every sign ≥ 10 occurrences with columns
  `sign, total, pct_initial, pct_medial, pct_final, role_label`
- `opener_terminal_pmi_pairs.csv`: top 30 (opener, terminal) pairs by PMI,
  with `opener, terminal, co_count, pmi, p_value` (Fisher's exact or
  hypergeometric)
- `opener_terminal_cramers_v.csv`: overall Cramér's V of the full
  opener × terminal matrix + chi-squared
- `740_vs_520_comparison.csv`: terminal distributions, site/icon Cramér's V
- `033_vs_032_vs_235_as_terminals.csv`: opener JS divergences, site/icon
  Cramér's V
- `opener_terminal_system_audit.tex`: LaTeX section

---

### Script 3: `name-triad-classifier-system.py`

**Goal:** Signs 817, 861, 820 (Mohenjo-daro concentrated) and 405-501
(Harappa + Bull1:I) are the top proper-name candidates. This script tests
whether they form a **classifier system** — where each name-like sign pairs
with specific opener signs, terminal signs, or iconographic contexts,
suggesting they mark different administrative roles or categories.

**Method:**

1. Parse all inscriptions (complete and incomplete — name candidates can
   appear anywhere; we are not studying edge positions here).

2. For each of the 4 target name candidates (`817`, `861`, `820`, `405-501`),
   find every inscription containing that sign and extract:
   - The INITIAL-position sign (opener) of the inscription
   - The FINAL-position sign (terminal) of the inscription
   - Site, icon (symbol), material, artifact class

3. **Opener consistency per name candidate**: Is there a single opener that
   appears in ≥ 35% of inscriptions containing this name sign?
   - Compute `opener_consistency = max_opener_count / total_occurrences`
   - If > 0.35: flag as having a dominant opener

4. **Cross-candidate opener comparison**:
   - Do 817 and 861 share the same dominant opener? (Jaccard of top-5 openers)
   - Does 405-501 use a different dominant opener than 817/861?
   - Chi-squared + Cramér's V of opener distributions across all 4 candidates

5. **Cross-candidate terminal comparison**:
   - Does each name candidate preferentially co-occur with specific terminal
     signs?
   - Chi-squared + Cramér's V of terminal distributions across all 4

6. **Classifier strength score** per (name candidate, opener) pair:
   - `opener_consistency` = P(opener | name sign in inscription)
   - `site_pmi` = PMI(name sign, top site)
   - `icon_pmi` = PMI(name sign, top icon) — 0 if icon column blank
   - `classifier_score` = (opener_consistency + clip(site_pmi, 0, 3)/3 +
     clip(icon_pmi, 0, 5)/5) / 3
   - Verdict per pair: `STRONG` (≥ 0.5), `MODERATE` (0.3–0.5), `WEAK` (< 0.3)

7. **Icon–name association matrix**:
   - Build a matrix: icon × name candidate (count of co-occurrences)
   - Cramér's V across the full matrix
   - Report which icons most strongly select which name sign (top PMI cells)

**Outputs:**
- `name_triad_openers.csv`:
  `name_candidate, top_opener, opener_freq, opener_consistency,
  site_pmi, icon_pmi, classifier_score, verdict`
- `name_triad_terminals.csv`:
  `name_candidate, top_terminal, terminal_freq, terminal_consistency`
- `classifier_system_hypothesis.csv`:
  `name_candidate, opener, classifier_score, verdict, site_pmi, icon_pmi`
- `icon_name_association.csv`:
  Cramér's V summary + top 10 PMI cells of the icon × name matrix
- `name_triad_classifier_system.tex`: LaTeX section

---

## Quality Bar

Match this style from our existing `sequence-information-model.py`:

```python
#!/usr/bin/env python3
"""
[Script Name] — [short purpose].

WHAT THIS DOES AND WHY
-----------------------
[2-3 paragraphs explaining the scientific question, what naïve approaches
get wrong, and why this method is the right one]

METHODOLOGICAL CHOICES
-----------------------
1. [Choice 1]: [rationale]
2. [Choice 2]: [rationale]
...
"""
import argparse, csv, os
from collections import defaultdict
import numpy as np
from scipy import stats

def parse_args():
    p = argparse.ArgumentParser(description="[one-line description]")
    p.add_argument("--data", default="data")
    p.add_argument("--outputs", default="outputs")
    return p.parse_args()
```

Deliver all 3 scripts: complete, runnable, no stubs.
`python script-name.py --data resources/data --outputs outputs`
