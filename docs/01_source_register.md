# Source Register

This register tracks sources we may use and how much evidentiary weight they should carry.

| Source | Use | Status | Notes |
| --- | --- | --- | --- |
| Local `data/ivs_corpus_cleaned.csv` | Initial working corpus | Active, provenance to verify | 5,679 rows; excludes claimed Sanskrit readings/translations. |
| Local `data/ivs_corpus.csv` | Hypothesis archive only | Restricted | Includes proposed Sanskrit readings/translations; not baseline data. |
| Mahadevan, *The Indus Script: Texts, Concordance and Tables* (1977) | Standard concordance reference | Foundational | Often cited as M77; sign counts and text lines differ depending on filtering. |
| Parpola et al., *Corpus of Indus Seals and Inscriptions* | Corpus/reference tradition | Foundational | Important for artifact cataloging and sign traditions. |
| mayig `indus-valley-script-corpus` | Open digital CISI-oriented corpus | Candidate comparative corpus | Repository states it is a WIP digitization of CISI in JSON and records graphemes left-to-right while assuming right-to-left reading for the script. See https://github.com/mayig/indus-valley-script-corpus |
| Yadav et al. 2010, PLOS ONE | N-gram/statistical baseline | Active methodological reference | Reports Zipf-Mandelbrot behavior, positional asymmetry, strong bigram correlations, and Markov modeling. DOI: https://doi.org/10.1371/journal.pone.0009506 |
| Rao et al. 2009, Science | Conditional entropy comparison | Active methodological reference | Argues Indus conditional entropy resembles linguistic systems more than tested non-linguistic controls. DOI: https://doi.org/10.1126/science.1170391 |
| Rao et al. 2009, PNAS | Markov modeling | Active methodological reference | Uses positional statistics and Markov methods for syntax and missing-sign prediction. DOI: https://doi.org/10.1073/pnas.0906237106 |
| Farmer, Sproat, Witzel 2004 | Non-linguistic critique | Required adversarial model | Argues against a linguistic-script thesis and stresses brevity, lack of long texts, and non-linguistic symbol-system parallels. DOI: https://doi.org/10.11588/ejvs.2004.2.620 |
| Sinha et al. 2010/2011 | Network analysis | Candidate methodological reference | Reports network patterns suggestive of syntactic organization. arXiv: https://arxiv.org/abs/1005.4997 |
| Nair 2026, arXiv | Recent synthetic non-linguistic baseline | Provisional | New preprint; useful as an emerging baseline design, not yet treated as settled. arXiv: https://arxiv.org/abs/2604.17828 |

## Immediate Source Tasks

1. Identify the provenance of the two local CSV files.
2. Determine the sign numbering system used locally.
3. Build concordance crosswalks where possible: local code, Mahadevan, Parpola, Wells.
4. Decide whether to import the open JSON corpus as a second corpus layer.

