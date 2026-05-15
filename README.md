# Indus Valley Script Research Project

This repository contains a disciplined research workspace for studying the Indus Valley sign system.

The canonical research document is now LaTeX:

- `docs/main.tex`
- `docs/sections/*.tex`
- `docs/references.bib`

The working rule is simple: proposed readings are hypotheses, not data. The project begins with corpus hygiene, directionality, positional grammar, sign-inventory normalization, and rival-model testing before any candidate decipherment is allowed into the main model.

To build the research document locally, compile from the `docs` directory:

```powershell
pdflatex main.tex
bibtex main
pdflatex main.tex
pdflatex main.tex
```

