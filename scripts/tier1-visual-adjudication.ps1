param(
    [string]$OutDir = "outputs"
)

if (-not (Test-Path $OutDir)) {
    New-Item -ItemType Directory -Force -Path $OutDir | Out-Null
}

function ConvertTo-LatexText([string]$Value) {
    if ($null -eq $Value) { return "" }
    $text = $Value -replace '\\', '/'
    $text = $text -replace '_', '\_'
    $text = $text -replace '%', '\%'
    $text = $text -replace '&', '\&'
    $text = $text -replace '#', '\#'
    return $text
}

$rows = @(
    [pscustomobject]@{
        Pair = "817/861"
        DistributionRank = "Tier1"
        VisualEvidence = "Both sides available"
        ShapeAssessment = "Moderate family resemblance: both are enclosed signs with angular internal marking, but outline and internal geometry differ."
        PositionalContext = "Both behave as high-confidence initial signs in the current corpus."
        ProvisionalVerdict = "Keep distinct; functional-cluster candidate, not a merge candidate."
        NextAction = "Check artifact photos for carving distortion and independent occurrences."
    },
    [pscustomobject]@{
        Pair = "817/820"
        DistributionRank = "Tier1"
        VisualEvidence = "Both sides available"
        ShapeAssessment = "Moderate family resemblance: both are enclosed signs, but 817 has a simple chevron-like interior and 820 has a divided/crossed interior."
        PositionalContext = "Both are initial-heavy and distributionally close."
        ProvisionalVerdict = "Keep distinct; functional-cluster candidate, not a merge candidate."
        NextAction = "Check artifact photos for systematic graphic alternation or catalog separation."
    },
    [pscustomobject]@{
        Pair = "705/706"
        DistributionRank = "Tier1"
        VisualEvidence = "Both sides available"
        ShapeAssessment = "Strong visual resemblance: same open-U/long-stem family, with 706 adding or emphasizing an inner nested stroke."
        PositionalContext = "Distributional similarity is high, but both signs are not confined to initial or terminal position."
        ProvisionalVerdict = "Variant-link candidate; no merge until artifact-level review."
        NextAction = "Prioritize CISI image checks for crowding, carving depth, and object-level independence."
    },
    [pscustomobject]@{
        Pair = "692/920"
        DistributionRank = "Tier1"
        VisualEvidence = "Both sides available"
        ShapeAssessment = "Weak visual resemblance: 692 is crossed/X-shaped, while 920 is a curved single-stroke form."
        PositionalContext = "Distributional similarity likely reflects shared initial-function behavior rather than graphic equivalence."
        ProvisionalVerdict = "Reject visual-allograph hypothesis at catalog level; keep as functional-cluster candidate."
        NextAction = "Use as a control case for distributional similarity without visual similarity."
    }
)

$csvPath = Join-Path $OutDir "tier1_visual_adjudication.csv"
$texPath = Join-Path $OutDir "tier1_visual_adjudication.tex"
$rows | Export-Csv -NoTypeInformation -Path $csvPath

$lines = New-Object System.Collections.Generic.List[string]
$lines.Add("\documentclass[11pt,a4paper]{article}") | Out-Null
$lines.Add("\usepackage[margin=1in]{geometry}") | Out-Null
$lines.Add("\usepackage[T1]{fontenc}") | Out-Null
$lines.Add("\usepackage[utf8]{inputenc}") | Out-Null
$lines.Add("\usepackage{booktabs}") | Out-Null
$lines.Add("\usepackage{longtable}") | Out-Null
$lines.Add("\begin{document}") | Out-Null
$lines.Add("\section*{Tier 1 Visual Adjudication}") | Out-Null
$lines.Add("This report converts the Tier 1 visual evidence into provisional research decisions. It does not merge signs; it separates visual allograph candidates from distributional functional clusters.") | Out-Null
$lines.Add("\begin{longtable}{p{0.10\textwidth}p{0.20\textwidth}p{0.28\textwidth}p{0.28\textwidth}}") | Out-Null
$lines.Add("\toprule") | Out-Null
$lines.Add("\textbf{Pair} & \textbf{Shape assessment} & \textbf{Provisional verdict} & \textbf{Next action} \\") | Out-Null
$lines.Add("\midrule") | Out-Null
$lines.Add("\endhead") | Out-Null
foreach ($row in $rows) {
    $lines.Add((ConvertTo-LatexText $row.Pair) + " & " + (ConvertTo-LatexText $row.ShapeAssessment) + " & " + (ConvertTo-LatexText $row.ProvisionalVerdict) + " & " + (ConvertTo-LatexText $row.NextAction) + " \\") | Out-Null
}
$lines.Add("\bottomrule") | Out-Null
$lines.Add("\end{longtable}") | Out-Null
$lines.Add("\end{document}") | Out-Null
$lines | Set-Content -Path $texPath -Encoding UTF8

"Wrote $csvPath"
"Wrote $texPath"
