# First Findings: Positional Grammar Pass

Generated on 2026-05-15 from:

- `outputs/positional_analysis.md`
- `outputs/physical_order_positional_analysis.md`

## Scope

This pass used a stricter subset of the cleaned corpus:

- complete inscriptions only;
- directions limited to `R/L` and `L/R`;
- rows containing `000` excluded;
- `R/L` rows reversed under the provisional assumption that the CSV text field is physical order rather than reading order.

Rows analyzed: 3,154.

Unique non-zero sign codes analyzed: 606.

## Early Functional Classes

The following are not readings. They are behavioral classes.

### Strong End Candidates

The strongest terminal signs in this pass include:

- `527`: 47 total, 87.23 percent terminal.
- `151`: 71 total, 83.10 percent terminal.
- `400`: 360 total, 82.22 percent terminal.
- `520`: 255 total, 80.78 percent terminal.
- `090`: 125 total, 77.60 percent terminal.
- `700`: 448 total, 75.45 percent terminal.
- `740`: 1,361 total, 65.03 percent terminal.

This suggests a terminal class that may include formula closers, titles, classifiers, commodities, or grammatical endings.

### Strong Start Candidates

The strongest initial signs in this pass include:

- `501`: 31 total, 93.55 percent initial.
- `817`: 164 total, 87.80 percent initial.
- `034`: 132 total, 81.06 percent initial.
- `503`: 69 total, 75.36 percent initial.
- `820`: 165 total, 74.55 percent initial.
- `692`: 54 total, 74.07 percent initial.
- `861`: 212 total, 58.96 percent initial.
- `003`: 195 total, 57.95 percent initial.

This suggests an opening class that may include prefixes, header signs, owner/title markers, or object-class indicators.

### Strong Medial Candidates

The strongest medial signs in this pass include:

- `845`: 48 total, 100.00 percent medial.
- `752`: 49 total, 97.96 percent medial.
- `060`: 181 total, 97.79 percent medial.
- `760`: 90 total, 97.78 percent medial.
- `002`: 593 total, 94.94 percent medial.
- `741`: 170 total, 88.82 percent medial.

This suggests a medial class that may carry core lexical, classifying, or internal-formula functions.

## Caution

The reading-order assumption is not yet verified. Running the script in physical-order mode produces an almost clean inversion of the strong start and end classes. The medial class, however, remains stable: signs such as `002`, `060`, `741`, `845`, `752`, and `760` remain strongly medial under both modes.

Therefore, terminal and initial interpretations must wait until corpus provenance is established. Medial positional behavior is already more robust.

## Directionality Diagnostic

Two output modes now exist:

- `reading-order mode`: `outputs/positional_analysis.md`
- `physical-order mode`: `outputs/physical_order_positional_analysis.md`

The next task is to identify the source convention of `text`: whether signs were recorded in physical artifact order or intended reading order.
