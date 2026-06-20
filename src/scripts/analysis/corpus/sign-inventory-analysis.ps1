param(
    [string]$Path = "data/ivs_corpus_cleaned.csv",
    [string]$OutDir = "outputs",
    [int]$MinFunctionalCount = 20,
    [double]$EdgePctThreshold = 0.75,
    [double]$MedialPctThreshold = 0.85
)

if (-not (Test-Path $OutDir)) {
    New-Item -ItemType Directory -Force -Path $OutDir | Out-Null
}

function Get-SignTokens([string]$Text) {
    return @([regex]::Matches($Text, '(?<!\d)\d{3,4}(?!\d)') | ForEach-Object { $_.Value })
}

function Get-RarityBand([int]$Count) {
    if ($Count -eq 1) { return "Hapax" }
    if ($Count -eq 2) { return "DisLegomenon" }
    if ($Count -le 5) { return "Rare3To5" }
    if ($Count -le 19) { return "Low6To19" }
    if ($Count -le 99) { return "Active20To99" }
    if ($Count -le 499) { return "Common100To499" }
    return "Dominant500Plus"
}

function ConvertTo-LatexText([string]$Value) {
    if ($null -eq $Value) { return "" }
    $text = $Value -replace '\\', '/'
    $text = $text -replace '_', '\_'
    $text = $text -replace '%', '\%'
    return $text
}

function Format-LatexTable($RowsToFormat, $Columns) {
    $lines = New-Object System.Collections.Generic.List[string]
    $alignment = "l" + ("r" * ($Columns.Count - 1))
    $headers = $Columns | ForEach-Object { "\textbf{" + $_ + "}" }

    $lines.Add("\begin{center}") | Out-Null
    $lines.Add("\begin{tabular}{$alignment}") | Out-Null
    $lines.Add("\toprule") | Out-Null
    $lines.Add(($headers -join " & ") + " \\") | Out-Null
    $lines.Add("\midrule") | Out-Null

    foreach ($row in $RowsToFormat) {
        $values = foreach ($column in $Columns) { [string]$row.$column }
        $lines.Add(($values -join " & ") + " \\") | Out-Null
    }

    $lines.Add("\bottomrule") | Out-Null
    $lines.Add("\end{tabular}") | Out-Null
    $lines.Add("\end{center}") | Out-Null
    return $lines
}

$rows = Import-Csv -Path $Path
$occurrences = New-Object System.Collections.Generic.List[object]
$positionOccurrences = New-Object System.Collections.Generic.List[object]

foreach ($row in $rows) {
    $tokens = Get-SignTokens $row.text
    if ($tokens.Count -eq 0) { continue }

    $dir = ([string]$row.'dir.').Trim()
    $hasUncertainToken = $tokens -contains "000"
    $hasEncodedSpace = $tokens -contains "999"
    $hasTextDamage = ([string]$row.text) -match '[\[\]\?]'
    $isComplete = $row.complete -eq "Y"
    $isPreservedComplete = $row.preservation -eq "complete"
    $isDamagedContext = (-not $isComplete) -or (-not $isPreservedComplete) -or $hasUncertainToken -or $hasTextDamage

    foreach ($token in $tokens) {
        $occurrences.Add([pscustomobject]@{
            Sign = $token
            Id = $row.id
            Site = $row.site
            Region = $row.region
            Type = $row.type
            Direction = $dir
            Complete = $row.complete
            Preservation = $row.preservation
            DamagedContext = $isDamagedContext
        }) | Out-Null
    }

    $usableForPosition = $isComplete -and (-not $hasUncertainToken) -and (-not $hasEncodedSpace) -and (-not $hasTextDamage) -and (($dir -in @("R/L", "L/R")) -or ($tokens.Count -eq 1))
    if (-not $usableForPosition) { continue }

    $readingTokens = @($tokens)
    [array]::Reverse($readingTokens)
    $n = $readingTokens.Count

    for ($i = 0; $i -lt $n; $i++) {
        $token = $readingTokens[$i]
        if ($token -in @("000", "999")) { continue }

        $position = "Medial"
        if ($n -eq 1) {
            $position = "Singleton"
            $normPos = 0.5
        }
        else {
            $normPos = $i / ($n - 1)
            if ($i -eq 0) {
                $position = "Start"
            }
            elseif ($i -eq ($n - 1)) {
                $position = "End"
            }
        }

        $positionOccurrences.Add([pscustomobject]@{
            Sign = $token
            Position = $position
            NormPosition = $normPos
        }) | Out-Null
    }
}

$positionBySign = @{}
foreach ($group in ($positionOccurrences | Group-Object Sign)) {
    $start = @($group.Group | Where-Object { $_.Position -eq "Start" }).Count
    $end = @($group.Group | Where-Object { $_.Position -eq "End" }).Count
    $medial = @($group.Group | Where-Object { $_.Position -eq "Medial" }).Count
    $singleton = @($group.Group | Where-Object { $_.Position -eq "Singleton" }).Count
    $total = $group.Count
    $normAvg = (($group.Group | Measure-Object -Property NormPosition -Average).Average)

    $positionBySign[$group.Name] = [pscustomobject]@{
        PositionTotal = $total
        Start = $start
        End = $end
        Medial = $medial
        Singleton = $singleton
        StartPct = if ($total -gt 0) { [math]::Round($start / $total, 4) } else { 0 }
        EndPct = if ($total -gt 0) { [math]::Round($end / $total, 4) } else { 0 }
        MedialPct = if ($total -gt 0) { [math]::Round($medial / $total, 4) } else { 0 }
        SingletonPct = if ($total -gt 0) { [math]::Round($singleton / $total, 4) } else { 0 }
        MeanNormPosition = if ($null -ne $normAvg) { [math]::Round($normAvg, 4) } else { 0 }
    }
}

$signStats = foreach ($group in ($occurrences | Group-Object Sign)) {
    $sign = $group.Name
    $items = @($group.Group)
    $position = if ($positionBySign.ContainsKey($sign)) { $positionBySign[$sign] } else {
        [pscustomobject]@{
            PositionTotal = 0
            Start = 0
            End = 0
            Medial = 0
            Singleton = 0
            StartPct = 0
            EndPct = 0
            MedialPct = 0
            SingletonPct = 0
            MeanNormPosition = 0
        }
    }

    $candidateClasses = New-Object System.Collections.Generic.List[string]
    if ($sign -eq "000") {
        $candidateClasses.Add("ErodedUnknown") | Out-Null
    }
    if ($sign -eq "999") {
        $candidateClasses.Add("EncodedSpace") | Out-Null
    }
    if ($group.Count -ge 500 -and $sign -notin @("000", "999")) {
        $candidateClasses.Add("DominantCode") | Out-Null
    }
    if ($group.Count -le 5 -and $sign -notin @("000", "999")) {
        $candidateClasses.Add("RareOrAllographCandidate") | Out-Null
    }
    if ($position.PositionTotal -ge $MinFunctionalCount -and $position.StartPct -ge $EdgePctThreshold) {
        $candidateClasses.Add("InitialCandidate") | Out-Null
    }
    if ($position.PositionTotal -ge $MinFunctionalCount -and $position.EndPct -ge $EdgePctThreshold) {
        $candidateClasses.Add("TerminalCandidate") | Out-Null
    }
    if ($position.PositionTotal -ge $MinFunctionalCount -and $position.MedialPct -ge $MedialPctThreshold) {
        $candidateClasses.Add("MedialCandidate") | Out-Null
    }
    if ($position.PositionTotal -ge $MinFunctionalCount -and $position.SingletonPct -ge 0.50) {
        $candidateClasses.Add("SingletonCandidate") | Out-Null
    }

    [pscustomobject]@{
        Sign = $sign
        TotalTokens = $group.Count
        TextCount = ($items | Select-Object -ExpandProperty Id -Unique).Count
        SiteCount = ($items | Select-Object -ExpandProperty Site -Unique).Count
        RegionCount = ($items | Select-Object -ExpandProperty Region -Unique).Count
        TypeCount = ($items | Select-Object -ExpandProperty Type -Unique).Count
        DamagedContextTokens = @($items | Where-Object { $_.DamagedContext }).Count
        RarityBand = if ($sign -eq "000") { "ErodedUnknown" } elseif ($sign -eq "999") { "EncodedSpace" } else { Get-RarityBand $group.Count }
        PositionTotal = $position.PositionTotal
        Start = $position.Start
        End = $position.End
        Medial = $position.Medial
        Singleton = $position.Singleton
        StartPct = $position.StartPct
        EndPct = $position.EndPct
        MedialPct = $position.MedialPct
        SingletonPct = $position.SingletonPct
        MeanNormPosition = $position.MeanNormPosition
        CandidateClasses = if ($candidateClasses.Count -gt 0) { $candidateClasses -join ";" } else { "Unclassified" }
    }
}

$signStats = $signStats | Sort-Object -Property @{Expression="TotalTokens"; Descending=$true}, @{Expression="Sign"; Descending=$false}

$statsPath = Join-Path $OutDir "sign_inventory_stats.csv"
$bandPath = Join-Path $OutDir "sign_frequency_bands.csv"
$coveragePath = Join-Path $OutDir "sign_coverage_thresholds.csv"
$candidatePath = Join-Path $OutDir "sign_candidate_classes.csv"
$summaryPath = Join-Path $OutDir "sign_inventory_analysis.tex"

$signStats | Export-Csv -NoTypeInformation -Path $statsPath

$nonZeroStats = @($signStats | Where-Object { $_.Sign -notin @("000", "999") })

$bandRows = $nonZeroStats |
    Group-Object RarityBand |
    Select-Object @{Name="Band"; Expression={$_.Name}}, @{Name="Signs"; Expression={$_.Count}}, @{Name="Tokens"; Expression={($_.Group | Measure-Object -Property TotalTokens -Sum).Sum}} |
    Sort-Object @{Expression="Tokens"; Descending=$true}

$bandRows | Export-Csv -NoTypeInformation -Path $bandPath

$totalNonZeroTokens = ($nonZeroStats | Measure-Object -Property TotalTokens -Sum).Sum
$coverageRows = New-Object System.Collections.Generic.List[object]
foreach ($threshold in @(0.50, 0.75, 0.90, 0.95, 0.99)) {
    $running = 0
    $signCount = 0
    foreach ($row in $nonZeroStats) {
        $running += [int]$row.TotalTokens
        $signCount += 1
        if (($running / $totalNonZeroTokens) -ge $threshold) {
            $coverageRows.Add([pscustomobject]@{
                Coverage = $threshold
                Signs = $signCount
                Tokens = $running
                TotalTokens = $totalNonZeroTokens
            }) | Out-Null
            break
        }
    }
}

$coverageRows | Export-Csv -NoTypeInformation -Path $coveragePath

$candidateRows = $signStats |
    Where-Object { $_.CandidateClasses -ne "Unclassified" } |
    Select-Object Sign, TotalTokens, PositionTotal, StartPct, EndPct, MedialPct, SingletonPct, CandidateClasses

$candidateRows | Export-Csv -NoTypeInformation -Path $candidatePath

$topInitial = $signStats |
    Where-Object { $_.CandidateClasses -match "InitialCandidate" } |
    Sort-Object -Property @{Expression="StartPct"; Descending=$true}, @{Expression="TotalTokens"; Descending=$true} |
    Select-Object -First 12 Sign, TotalTokens, StartPct, MeanNormPosition

$topTerminal = $signStats |
    Where-Object { $_.CandidateClasses -match "TerminalCandidate" } |
    Sort-Object -Property @{Expression="EndPct"; Descending=$true}, @{Expression="TotalTokens"; Descending=$true} |
    Select-Object -First 12 Sign, TotalTokens, EndPct, MeanNormPosition

$topMedial = $signStats |
    Where-Object { $_.CandidateClasses -match "MedialCandidate" } |
    Sort-Object -Property @{Expression="MedialPct"; Descending=$true}, @{Expression="TotalTokens"; Descending=$true} |
    Select-Object -First 12 Sign, TotalTokens, MedialPct, MeanNormPosition

$hapaxCount = @($nonZeroStats | Where-Object { $_.TotalTokens -eq 1 }).Count
$rareToFiveCount = @($nonZeroStats | Where-Object { $_.TotalTokens -le 5 }).Count
$dominantCount = @($nonZeroStats | Where-Object { $_.TotalTokens -ge 500 }).Count
$ambiguousTokens = @($occurrences | Where-Object { $_.Sign -eq "000" }).Count
$spaceTokens = @($occurrences | Where-Object { $_.Sign -eq "999" }).Count

$overviewRows = @(
    [pscustomobject]@{Measure="Rows"; Value=$rows.Count},
    [pscustomobject]@{Measure="AnalyzableSignTokens"; Value=$totalNonZeroTokens},
    [pscustomobject]@{Measure="UniqueAnalyzableCodes"; Value=$nonZeroStats.Count},
    [pscustomobject]@{Measure="Eroded000Tokens"; Value=$ambiguousTokens},
    [pscustomobject]@{Measure="EncodedSpace999Tokens"; Value=$spaceTokens},
    [pscustomobject]@{Measure="DominantCodes500Plus"; Value=$dominantCount},
    [pscustomobject]@{Measure="HapaxCodes"; Value=$hapaxCount},
    [pscustomobject]@{Measure="RareCodesOneToFive"; Value=$rareToFiveCount}
)

$summary = New-Object System.Collections.Generic.List[string]
$summary.Add("\documentclass[11pt,a4paper]{article}") | Out-Null
$summary.Add("\usepackage[margin=1in]{geometry}") | Out-Null
$summary.Add("\usepackage[T1]{fontenc}") | Out-Null
$summary.Add("\usepackage[utf8]{inputenc}") | Out-Null
$summary.Add("\usepackage{booktabs}") | Out-Null
$summary.Add("\begin{document}") | Out-Null
$summary.Add("\section*{Sign Inventory Compression Analysis}") | Out-Null
$summary.Add("") | Out-Null
$summary.Add("Generated from \texttt{" + (ConvertTo-LatexText $Path) + "}. Counts are code-level observations, not final graphemic units.") | Out-Null
$summary.Add("") | Out-Null
$summary.Add("\subsection*{Inventory Overview}") | Out-Null
Format-LatexTable $overviewRows @("Measure", "Value") | ForEach-Object { $summary.Add($_) | Out-Null }
$summary.Add("") | Out-Null
$summary.Add("\subsection*{Frequency Bands}") | Out-Null
Format-LatexTable $bandRows @("Band", "Signs", "Tokens") | ForEach-Object { $summary.Add($_) | Out-Null }
$summary.Add("") | Out-Null
$summary.Add("\subsection*{Coverage Thresholds}") | Out-Null
Format-LatexTable $coverageRows @("Coverage", "Signs", "Tokens", "TotalTokens") | ForEach-Object { $summary.Add($_) | Out-Null }
$summary.Add("") | Out-Null
$summary.Add("\subsection*{Candidate Functional Classes}") | Out-Null
$summary.Add("Functional classes are corpus-derived labels using minimum positional count $MinFunctionalCount, edge threshold $EdgePctThreshold, and medial threshold $MedialPctThreshold.") | Out-Null
$summary.Add("") | Out-Null
$summary.Add("\subsubsection*{Initial Candidates}") | Out-Null
Format-LatexTable $topInitial @("Sign", "TotalTokens", "StartPct", "MeanNormPosition") | ForEach-Object { $summary.Add($_) | Out-Null }
$summary.Add("") | Out-Null
$summary.Add("\subsubsection*{Terminal Candidates}") | Out-Null
Format-LatexTable $topTerminal @("Sign", "TotalTokens", "EndPct", "MeanNormPosition") | ForEach-Object { $summary.Add($_) | Out-Null }
$summary.Add("") | Out-Null
$summary.Add("\subsubsection*{Medial Candidates}") | Out-Null
Format-LatexTable $topMedial @("Sign", "TotalTokens", "MedialPct", "MeanNormPosition") | ForEach-Object { $summary.Add($_) | Out-Null }
$summary.Add("") | Out-Null
$summary.Add("\subsection*{Compression Policy}") | Out-Null
$summary.Add("\begin{enumerate}") | Out-Null
$summary.Add("\item Treat all 712 analyzable sign codes as code-level observations, not final signs.") | Out-Null
$summary.Add("\item Freeze dominant and positional candidates for functional testing before any merger.") | Out-Null
$summary.Add("\item Treat hapax and very rare codes as the first allograph/noise candidates, pending image and concordance checks.") | Out-Null
$summary.Add("\item Build a crosswalk to Wells/ICIT before claiming a reduced sign inventory.") | Out-Null
$summary.Add("\end{enumerate}") | Out-Null
$summary.Add("\end{document}") | Out-Null

$summary | Set-Content -Path $summaryPath -Encoding UTF8

"Wrote $statsPath"
"Wrote $bandPath"
"Wrote $coveragePath"
"Wrote $candidatePath"
"Wrote $summaryPath"
