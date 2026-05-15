param(
    [string]$CorpusPath = "data/ivs_corpus_cleaned.csv",
    [string]$OutDir = "outputs",
    [string[]]$TargetSigns = @("705", "706")
)

if (-not (Test-Path $OutDir)) {
    New-Item -ItemType Directory -Force -Path $OutDir | Out-Null
}

function Get-SignTokens([string]$Text) {
    return @([regex]::Matches($Text, '(?<!\d)\d{3,4}(?!\d)') | ForEach-Object { $_.Value })
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

$rows = Import-Csv -Path $CorpusPath
$targetLookup = @{}
foreach ($sign in $TargetSigns) {
    $targetLookup[$sign] = $true
}

$occurrences = New-Object System.Collections.Generic.List[object]

foreach ($row in $rows) {
    $tokens = Get-SignTokens $row.text
    if ($tokens.Count -eq 0) { continue }

    $readingTokens = @($tokens | Where-Object { $_ -ne "999" })
    [array]::Reverse($readingTokens)
    $cleanTokens = @($readingTokens | Where-Object { $_ -ne "000" })
    if ($cleanTokens.Count -eq 0) { continue }

    for ($i = 0; $i -lt $cleanTokens.Count; $i++) {
        $sign = $cleanTokens[$i]
        if (-not $targetLookup.ContainsKey($sign)) { continue }

        $position = $i + 1
        $positionClass = "Medial"
        if ($position -eq 1) {
            $positionClass = "Initial"
        } elseif ($position -eq $cleanTokens.Count) {
            $positionClass = "Terminal"
        }

        $occurrences.Add([pscustomobject]@{
            Sign = $sign
            Id = $row.id
            Cisi = $row.cisi
            Site = $row.site
            Region = $row.region
            Type = $row.type
            Complete = $row.complete
            Direction = ([string]$row.'dir.').Trim()
            Position = $position
            TextLength = $cleanTokens.Count
            PositionClass = $positionClass
            PreviousSign = if ($i -gt 0) { $cleanTokens[$i - 1] } else { "" }
            NextSign = if ($i -lt ($cleanTokens.Count - 1)) { $cleanTokens[$i + 1] } else { "" }
            ReadingOrderText = ($cleanTokens -join "-")
            SourceText = $row.text
            ArtifactReviewStatus = "Queued"
            ReviewQuestion = "Does the artifact image support a 705/706 allograph or variant-link interpretation?"
        }) | Out-Null
    }
}

$summaryRows = New-Object System.Collections.Generic.List[object]
foreach ($sign in $TargetSigns) {
    $signRows = @($occurrences | Where-Object { $_.Sign -eq $sign })
    $completeRows = @($signRows | Where-Object { $_.Complete -eq "Y" })
    $summaryRows.Add([pscustomobject]@{
        Sign = $sign
        Occurrences = $signRows.Count
        CompleteOccurrences = $completeRows.Count
        UniqueTexts = @($signRows | Select-Object -ExpandProperty Id -Unique).Count
        UniqueSites = @($signRows | Select-Object -ExpandProperty Site -Unique).Count
        UniqueTypes = @($signRows | Select-Object -ExpandProperty Type -Unique).Count
        Initial = @($signRows | Where-Object { $_.PositionClass -eq "Initial" }).Count
        Medial = @($signRows | Where-Object { $_.PositionClass -eq "Medial" }).Count
        Terminal = @($signRows | Where-Object { $_.PositionClass -eq "Terminal" }).Count
    }) | Out-Null
}

$queuePath = Join-Path $OutDir "tier1_artifact_review_queue_705_706.csv"
$summaryPath = Join-Path $OutDir "tier1_artifact_review_summary_705_706.csv"
$texPath = Join-Path $OutDir "tier1_artifact_review_705_706.tex"

$occurrences |
    Sort-Object Sign, Complete, Site, Type, Id, Position |
    Export-Csv -NoTypeInformation -Path $queuePath

$summaryRows | Export-Csv -NoTypeInformation -Path $summaryPath

$exampleRows = $occurrences |
    Where-Object { $_.Complete -eq "Y" } |
    Sort-Object Sign, Site, Type, Id |
    Select-Object -First 12

$lines = New-Object System.Collections.Generic.List[string]
$lines.Add("\documentclass[11pt,a4paper]{article}") | Out-Null
$lines.Add("\usepackage[margin=1in]{geometry}") | Out-Null
$lines.Add("\usepackage[T1]{fontenc}") | Out-Null
$lines.Add("\usepackage[utf8]{inputenc}") | Out-Null
$lines.Add("\usepackage{booktabs}") | Out-Null
$lines.Add("\begin{document}") | Out-Null
$lines.Add("\section*{Artifact Review Queue: 705/706}") | Out-Null
$lines.Add("The pair 705/706 is the strongest Tier 1 visual variant-link candidate. This queue identifies corpus occurrences that should be checked against artifact images before any inventory decision.") | Out-Null
$lines.Add("\subsection*{Summary}") | Out-Null
$lines.Add("\begin{center}") | Out-Null
$lines.Add("\begin{tabular}{lrrrrrrr}") | Out-Null
$lines.Add("\toprule") | Out-Null
$lines.Add("\textbf{Sign} & \textbf{Occ.} & \textbf{Complete} & \textbf{Texts} & \textbf{Sites} & \textbf{Initial} & \textbf{Medial} & \textbf{Terminal} \\") | Out-Null
$lines.Add("\midrule") | Out-Null
foreach ($row in $summaryRows) {
    $values = @($row.Sign, $row.Occurrences, $row.CompleteOccurrences, $row.UniqueTexts, $row.UniqueSites, $row.Initial, $row.Medial, $row.Terminal)
    $lines.Add(($values -join " & ") + " \\") | Out-Null
}
$lines.Add("\bottomrule") | Out-Null
$lines.Add("\end{tabular}") | Out-Null
$lines.Add("\end{center}") | Out-Null
$lines.Add("\subsection*{Example Complete Records}") | Out-Null
$lines.Add("\begin{center}") | Out-Null
$lines.Add("\begin{tabular}{llllrr}") | Out-Null
$lines.Add("\toprule") | Out-Null
$lines.Add("\textbf{Sign} & \textbf{ID} & \textbf{CISI} & \textbf{Site} & \textbf{Pos.} & \textbf{Len.} \\") | Out-Null
$lines.Add("\midrule") | Out-Null
foreach ($row in $exampleRows) {
    $values = @($row.Sign, $row.Id, $row.Cisi, $row.Site, $row.Position, $row.TextLength) | ForEach-Object { ConvertTo-LatexText ([string]$_) }
    $lines.Add(($values -join " & ") + " \\") | Out-Null
}
$lines.Add("\bottomrule") | Out-Null
$lines.Add("\end{tabular}") | Out-Null
$lines.Add("\end{center}") | Out-Null
$lines.Add("\subsection*{Outputs}") | Out-Null
$lines.Add("\begin{itemize}") | Out-Null
$lines.Add("\item \texttt{" + (ConvertTo-LatexText $queuePath) + "}") | Out-Null
$lines.Add("\item \texttt{" + (ConvertTo-LatexText $summaryPath) + "}") | Out-Null
$lines.Add("\end{itemize}") | Out-Null
$lines.Add("\end{document}") | Out-Null
$lines | Set-Content -Path $texPath -Encoding UTF8

"Wrote $queuePath"
"Wrote $summaryPath"
"Wrote $texPath"
