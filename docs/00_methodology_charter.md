# Methodology Charter

Date opened: 2026-05-15

## North Star

The project will pursue decipherment only through constraints. We will not begin by assigning phonetic or semantic values to signs. We will begin by asking what the corpus permits.

## Core Rules

1. The cleaned corpus is the initial data layer. Claimed readings and translations are hypothesis material, not evidence.
2. Any language-family claim must predict distributional behavior before it is used to explain individual signs.
3. Iconographic resemblance is not a reading. It can generate a hypothesis, but not validate one.
4. A proposed value must be tested against more inscriptions than the one that inspired it.
5. Negative evidence matters: failed hypotheses stay in the ledger so we do not rediscover them under new names.
6. We distinguish at least four levels: sign, allograph, sign cluster, and artifact formula.
7. Archaeological context is part of the grammar. Site, medium, object type, iconography, completeness, and directionality are not metadata afterthoughts.

## Data Tiers

- `Tier A`: complete inscriptions with known or strongly supported directionality, clean sign sequence, stable artifact metadata.
- `Tier B`: complete or near-complete inscriptions with uncertain directionality or minor damage.
- `Tier C`: damaged, fragmentary, unusual, or contextually uncertain inscriptions.
- `Tier D`: disputed, unprovenanced, translated-only, or otherwise circular records. These are excluded from baseline analysis.

## Initial Research Questions

- Which signs are strongly initial, medial, or terminal?
- Which signs behave like numerals, classifiers, titles, commodities, names, or formula delimiters?
- Do object types have distinct sign grammars?
- Does the system look more like language, restricted writing, emblematic identifiers, administrative coding, or a mixed system?
- Do any observed structures resemble Dravidian or Indo-Aryan morphology strongly enough to produce testable predictions?

## Decision Rule For Candidate Readings

A reading is not allowed into the main model unless it satisfies all three conditions:

1. It explains a distributional fact in the corpus.
2. It predicts at least one additional distributional fact not used to invent it.
3. It is more economical than credible non-linguistic and alternative linguistic explanations.

## Bias Controls

- Maintain rival models in parallel.
- Score claims by evidence level.
- Prefer blind tests: train on one site or object class, test on another.
- Keep sign-number mappings distinct across Mahadevan, Parpola, Wells, and local datasets.
- Document every normalization step.

