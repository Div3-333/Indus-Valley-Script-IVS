param(
    [string]$CorpusPath = "data/ivs_corpus_cleaned.csv",
    [string]$InventoryPath = "outputs/sign_inventory_stats.csv",
    [string]$OutDir = "outputs"
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

function Convert-ToDouble([string]$Value, [double]$Default = 0.0) {
    $parsed = 0.0
    if ([double]::TryParse($Value, [ref]$parsed)) { return $parsed }
    return $Default
}

function Add-Count($Table, [string]$Key, [int]$Increment = 1) {
    if ($null -eq $Key -or $Key.Trim() -eq "") { return }
    if (-not $Table.ContainsKey($Key)) { $Table[$Key] = 0 }
    $Table[$Key] += $Increment
}

function Get-Entropy($Counts) {
    $total = 0
    foreach ($value in $Counts.Values) { $total += [int]$value }
    if ($total -le 0) { return 0.0 }

    $entropy = 0.0
    foreach ($value in $Counts.Values) {
        if ($value -le 0) { continue }
        $p = [double]$value / $total
        $entropy -= $p * ([math]::Log($p) / [math]::Log(2))
    }
    return $entropy
}

function Get-NormalizedEntropy($Counts, [int]$PossibleBins) {
    if ($PossibleBins -le 1) { return 0.0 }
    $entropy = Get-Entropy $Counts
    return [math]::Round($entropy / ([math]::Log($PossibleBins) / [math]::Log(2)), 4)
}

function Get-DominantShare($Counts) {
    $total = 0
    $max = 0
    foreach ($value in $Counts.Values) {
        $total += [int]$value
        if ([int]$value -gt $max) { $max = [int]$value }
    }
    if ($total -eq 0) { return 0.0 }
    return [math]::Round($max / $total, 4)
}

function Get-DominantKey($Counts) {
    $bestKey = ""
    $bestValue = -1
    foreach ($key in $Counts.Keys) {
        if ([int]$Counts[$key] -gt $bestValue) {
            $bestValue = [int]$Counts[$key]
            $bestKey = [string]$key
        }
    }
    return $bestKey
}

function Get-CoreGroup([double]$CumulativeCoverage) {
    if ($CumulativeCoverage -le 0.50) { return "Core50" }
    if ($CumulativeCoverage -le 0.75) { return "Core75" }
    if ($CumulativeCoverage -le 0.90) { return "Extension90" }
    if ($CumulativeCoverage -le 0.95) { return "Extension95" }
    if ($CumulativeCoverage -le 0.99) { return "LongTail99" }
    return "RareTail"
}

function Get-PositionRole([double]$StartPct, [double]$MedialPct, [double]$EndPct, [double]$SingletonPct, [double]$PositionEntropy) {
    if ($SingletonPct -ge 0.45) { return "SingletonOrEmblem" }
    if ($EndPct -ge 0.60) { return "TerminalMarker" }
    if ($StartPct -ge 0.55) { return "InitialMarker" }
    if ($MedialPct -ge 0.70) { return "MedialCarrier" }
    if ($PositionEntropy -ge 0.78) { return "FlexibleCarrier" }
    return "MixedPosition"
}

function Get-MechanismHypothesis([string]$CoreGroup, [string]$PositionRole, [int]$TotalTokens, [double]$PositionEntropy, [double]$LeftNeighborEntropy, [double]$RightNeighborEntropy, [double]$DominantLeftShare, [double]$DominantRightShare) {
    if ($PositionRole -in @("InitialMarker", "TerminalMarker")) { return "FormulaOrGrammarMarker" }
    if ($PositionRole -eq "SingletonOrEmblem") { return "ObjectOrEmblemCandidate" }
    if ($CoreGroup -in @("Core50", "Core75") -and $PositionRole -in @("FlexibleCarrier", "MedialCarrier", "MixedPosition") -and ($LeftNeighborEntropy + $RightNeighborEntropy) -ge 0.8) {
        return "CorePhoneticOrMorphemicCandidate"
    }
    if ($TotalTokens -le 20 -and ($DominantLeftShare -ge 0.55 -or $DominantRightShare -ge 0.55)) {
        return "BoundModifierOrFormulaVariantCandidate"
    }
    if ($CoreGroup -in @("Extension90", "Extension95") -and $PositionEntropy -ge 0.65) {
        return "ExtendedInventoryCandidate"
    }
    if ($CoreGroup -in @("LongTail99", "RareTail")) {
        return "RareVariantNumberOrEsotericCandidate"
    }
    return "UnclassifiedComputationalLead"
}

$rows = Import-Csv -Path $CorpusPath
$inventoryRows = Import-Csv -Path $InventoryPath | Where-Object { $_.Sign -notin @("000", "999") }

$positionBins = @{}
$leftNeighbors = @{}
$rightNeighbors = @{}
$regionCounts = @{}
$siteCounts = @{}
$typeCounts = @{}
$adjacentSelfRepeats = @{}

foreach ($row in $rows) {
    $tokens = Get-SignTokens $row.text
    if ($tokens.Count -eq 0) { continue }
    $readingTokens = @($tokens | Where-Object { $_ -notin @("000", "999") })
    [array]::Reverse($readingTokens)
    $length = $readingTokens.Count
    if ($length -eq 0) { continue }

    for ($i = 0; $i -lt $length; $i++) {
        $sign = $readingTokens[$i]

        if (-not $positionBins.ContainsKey($sign)) { $positionBins[$sign] = @{} }
        if (-not $leftNeighbors.ContainsKey($sign)) { $leftNeighbors[$sign] = @{} }
        if (-not $rightNeighbors.ContainsKey($sign)) { $rightNeighbors[$sign] = @{} }
        if (-not $regionCounts.ContainsKey($sign)) { $regionCounts[$sign] = @{} }
        if (-not $siteCounts.ContainsKey($sign)) { $siteCounts[$sign] = @{} }
        if (-not $typeCounts.ContainsKey($sign)) { $typeCounts[$sign] = @{} }
        if (-not $adjacentSelfRepeats.ContainsKey($sign)) { $adjacentSelfRepeats[$sign] = 0 }

        $bin = [int][math]::Ceiling((($i + 1) / [double]$length) * 10.0)
        if ($bin -lt 1) { $bin = 1 }
        if ($bin -gt 10) { $bin = 10 }
        Add-Count $positionBins[$sign] ([string]$bin)

        if ($i -gt 0) {
            Add-Count $leftNeighbors[$sign] $readingTokens[$i - 1]
            if ($readingTokens[$i - 1] -eq $sign) { $adjacentSelfRepeats[$sign] += 1 }
        }
        if ($i -lt ($length - 1)) {
            Add-Count $rightNeighbors[$sign] $readingTokens[$i + 1]
            if ($readingTokens[$i + 1] -eq $sign) { $adjacentSelfRepeats[$sign] += 1 }
        }
        Add-Count $regionCounts[$sign] $row.region
        Add-Count $siteCounts[$sign] $row.site
        Add-Count $typeCounts[$sign] $row.type
    }
}

$totalTokens = ($inventoryRows | Measure-Object -Property TotalTokens -Sum).Sum
$runningTokens = 0
$rank = 0
$signRows = New-Object System.Collections.Generic.List[object]

foreach ($row in ($inventoryRows | Sort-Object @{Expression={[int]$_.TotalTokens}; Descending=$true}, Sign)) {
    $rank += 1
    $sign = $row.Sign
    $tokens = [int]$row.TotalTokens
    $runningTokens += $tokens
    $coverage = [math]::Round($runningTokens / $totalTokens, 6)
    $coreGroup = Get-CoreGroup $coverage

    $startPct = Convert-ToDouble $row.StartPct
    $endPct = Convert-ToDouble $row.EndPct
    $medialPct = Convert-ToDouble $row.MedialPct
    $singletonPct = Convert-ToDouble $row.SingletonPct
    $positionEntropy = if ($positionBins.ContainsKey($sign)) { Get-NormalizedEntropy $positionBins[$sign] 10 } else { 0.0 }
    $leftEntropy = if ($leftNeighbors.ContainsKey($sign)) { Get-NormalizedEntropy $leftNeighbors[$sign] ([math]::Max(2, $leftNeighbors[$sign].Count)) } else { 0.0 }
    $rightEntropy = if ($rightNeighbors.ContainsKey($sign)) { Get-NormalizedEntropy $rightNeighbors[$sign] ([math]::Max(2, $rightNeighbors[$sign].Count)) } else { 0.0 }
    $dominantLeftShare = if ($leftNeighbors.ContainsKey($sign)) { Get-DominantShare $leftNeighbors[$sign] } else { 0.0 }
    $dominantRightShare = if ($rightNeighbors.ContainsKey($sign)) { Get-DominantShare $rightNeighbors[$sign] } else { 0.0 }
    $positionRole = Get-PositionRole $startPct $medialPct $endPct $singletonPct $positionEntropy
    $mechanism = Get-MechanismHypothesis $coreGroup $positionRole $tokens $positionEntropy $leftEntropy $rightEntropy $dominantLeftShare $dominantRightShare

    $signRows.Add([pscustomobject]@{
        Rank = $rank
        Sign = $sign
        TotalTokens = $tokens
        TokenPct = [math]::Round($tokens / $totalTokens, 6)
        CumulativeCoverage = $coverage
        CoreGroup = $coreGroup
        PositionRole = $positionRole
        MechanismHypothesis = $mechanism
        StartPct = $row.StartPct
        MedialPct = $row.MedialPct
        EndPct = $row.EndPct
        SingletonPct = $row.SingletonPct
        PositionEntropy10 = $positionEntropy
        LeftNeighborEntropy = $leftEntropy
        RightNeighborEntropy = $rightEntropy
        DominantLeftNeighbor = if ($leftNeighbors.ContainsKey($sign)) { Get-DominantKey $leftNeighbors[$sign] } else { "" }
        DominantLeftShare = $dominantLeftShare
        DominantRightNeighbor = if ($rightNeighbors.ContainsKey($sign)) { Get-DominantKey $rightNeighbors[$sign] } else { "" }
        DominantRightShare = $dominantRightShare
        RegionEntropy = if ($regionCounts.ContainsKey($sign)) { Get-NormalizedEntropy $regionCounts[$sign] ([math]::Max(2, $regionCounts[$sign].Count)) } else { 0.0 }
        SiteEntropy = if ($siteCounts.ContainsKey($sign)) { Get-NormalizedEntropy $siteCounts[$sign] ([math]::Max(2, $siteCounts[$sign].Count)) } else { 0.0 }
        TypeEntropy = if ($typeCounts.ContainsKey($sign)) { Get-NormalizedEntropy $typeCounts[$sign] ([math]::Max(2, $typeCounts[$sign].Count)) } else { 0.0 }
        AdjacentSelfRepeats = if ($adjacentSelfRepeats.ContainsKey($sign)) { $adjacentSelfRepeats[$sign] } else { 0 }
        CandidateClasses = $row.CandidateClasses
    }) | Out-Null
}

$groupRows = $signRows |
    Group-Object CoreGroup |
    ForEach-Object {
        [pscustomobject]@{
            Group = $_.Name
            Signs = $_.Count
            Tokens = ($_.Group | Measure-Object -Property TotalTokens -Sum).Sum
            TokenPct = [math]::Round((($_.Group | Measure-Object -Property TotalTokens -Sum).Sum / $totalTokens), 4)
            DominantRole = (($_.Group | Group-Object PositionRole | Sort-Object Count -Descending | Select-Object -First 1).Name)
            DominantMechanism = (($_.Group | Group-Object MechanismHypothesis | Sort-Object Count -Descending | Select-Object -First 1).Name)
        }
    } |
    Sort-Object @{Expression={
        switch ($_.Group) {
            "Core50" { 1 }
            "Core75" { 2 }
            "Extension90" { 3 }
            "Extension95" { 4 }
            "LongTail99" { 5 }
            default { 6 }
        }
    }}

$core75Signs = @($signRows | Where-Object { $_.CoreGroup -in @("Core50", "Core75") })
$core90Signs = @($signRows | Where-Object { $_.CoreGroup -in @("Core50", "Core75", "Extension90") })
$core75Flexible = @($core75Signs | Where-Object { $_.PositionRole -in @("FlexibleCarrier", "MedialCarrier", "MixedPosition") })
$core75Markers = @($core75Signs | Where-Object { $_.PositionRole -in @("InitialMarker", "TerminalMarker") })
$tailSigns = @($signRows | Where-Object { $_.CoreGroup -in @("LongTail99", "RareTail") })
$boundTail = @($tailSigns | Where-Object { $_.MechanismHypothesis -eq "BoundModifierOrFormulaVariantCandidate" })

$testRows = @(
    [pscustomobject]@{
        Test = "Abugida-scale core inventory"
        Metric = "Signs covering 75 percent of analyzable tokens"
        Value = $core75Signs.Count
        Interpretation = if ($core75Signs.Count -ge 35 -and $core75Signs.Count -le 80) { "Compatible with a phonetic core plus extensions; not diagnostic by itself." } else { "Outside the expected rough range for the working abugida-like model." }
    },
    [pscustomobject]@{
        Test = "High-frequency grammar split"
        Metric = "Core75 flexible/medial/mixed carriers"
        Value = $core75Flexible.Count
        Interpretation = "Large carrier set supports testing a phonetic or morphemic core, while marker signs must be modeled separately."
    },
    [pscustomobject]@{
        Test = "Formula-marker pressure"
        Metric = "Core75 initial or terminal markers"
        Value = $core75Markers.Count
        Interpretation = "A substantial marker set would push the system toward administrative formula grammar rather than a plain alphabetic inventory."
    },
    [pscustomobject]@{
        Test = "Extension scale"
        Metric = "Signs covering 90 percent of analyzable tokens"
        Value = $core90Signs.Count
        Interpretation = "This is the practical modeling target before the sparse tail dominates uncertainty."
    },
    [pscustomobject]@{
        Test = "Sparse-tail pressure"
        Metric = "Signs after 95 percent coverage"
        Value = $tailSigns.Count
        Interpretation = "The long tail is compatible with variants, numbers, names, object marks, rare logograms, or catalog over-splitting; it should not drive early decipherment."
    },
    [pscustomobject]@{
        Test = "Bound-modifier lead count"
        Metric = "Tail signs with dominant left/right neighbor"
        Value = $boundTail.Count
        Interpretation = "These are computational leads for diacritic, conjunct, affix, or formula-variant behavior."
    }
)

$signPath = Join-Path $OutDir "core_inventory_sign_model.csv"
$groupPath = Join-Path $OutDir "core_inventory_groups.csv"
$testPath = Join-Path $OutDir "core_inventory_abugida_tests.csv"
$texPath = Join-Path $OutDir "core_inventory_model.tex"

$signRows | Export-Csv -NoTypeInformation -Path $signPath
$groupRows | Export-Csv -NoTypeInformation -Path $groupPath
$testRows | Export-Csv -NoTypeInformation -Path $testPath

$topCoreRows = $signRows | Select-Object -First 20 Rank, Sign, TotalTokens, CumulativeCoverage, PositionRole, MechanismHypothesis

$lines = New-Object System.Collections.Generic.List[string]
$lines.Add("\documentclass[11pt,a4paper]{article}") | Out-Null
$lines.Add("\usepackage[margin=1in]{geometry}") | Out-Null
$lines.Add("\usepackage[T1]{fontenc}") | Out-Null
$lines.Add("\usepackage[utf8]{inputenc}") | Out-Null
$lines.Add("\usepackage{booktabs}") | Out-Null
$lines.Add("\begin{document}") | Out-Null
$lines.Add("\section*{Core Inventory Model}") | Out-Null
$lines.Add("This report tests whether the corpus has a compact high-frequency inventory plus a long extension tail. The comparison to abugida-like systems is treated as a compatibility test, not as a claim of Brahmic descent or Sanskrit identity.") | Out-Null
$lines.Add("\subsection*{Coverage Groups}") | Out-Null
$lines.Add("\begin{center}") | Out-Null
$lines.Add("\begin{tabular}{lrrll}") | Out-Null
$lines.Add("\toprule") | Out-Null
$lines.Add("\textbf{Group} & \textbf{Signs} & \textbf{Token pct.} & \textbf{Dominant role} & \textbf{Dominant mechanism} \\") | Out-Null
$lines.Add("\midrule") | Out-Null
foreach ($row in $groupRows) {
    $values = @($row.Group, $row.Signs, $row.TokenPct, $row.DominantRole, $row.DominantMechanism) | ForEach-Object { ConvertTo-LatexText ([string]$_) }
    $lines.Add(($values -join " & ") + " \\") | Out-Null
}
$lines.Add("\bottomrule") | Out-Null
$lines.Add("\end{tabular}") | Out-Null
$lines.Add("\end{center}") | Out-Null
$lines.Add("\subsection*{Working Model Tests}") | Out-Null
$lines.Add("\begin{center}") | Out-Null
$lines.Add("\begin{tabular}{llr}") | Out-Null
$lines.Add("\toprule") | Out-Null
$lines.Add("\textbf{Test} & \textbf{Metric} & \textbf{Value} \\") | Out-Null
$lines.Add("\midrule") | Out-Null
foreach ($row in $testRows) {
    $values = @($row.Test, $row.Metric, $row.Value) | ForEach-Object { ConvertTo-LatexText ([string]$_) }
    $lines.Add(($values -join " & ") + " \\") | Out-Null
}
$lines.Add("\bottomrule") | Out-Null
$lines.Add("\end{tabular}") | Out-Null
$lines.Add("\end{center}") | Out-Null
$lines.Add("\subsection*{Top Core Signs}") | Out-Null
$lines.Add("\begin{center}") | Out-Null
$lines.Add("\begin{tabular}{rlrll}") | Out-Null
$lines.Add("\toprule") | Out-Null
$lines.Add("\textbf{Rank} & \textbf{Sign} & \textbf{Tokens} & \textbf{Role} & \textbf{Mechanism} \\") | Out-Null
$lines.Add("\midrule") | Out-Null
foreach ($row in $topCoreRows) {
    $values = @($row.Rank, $row.Sign, $row.TotalTokens, $row.PositionRole, $row.MechanismHypothesis) | ForEach-Object { ConvertTo-LatexText ([string]$_) }
    $lines.Add(($values -join " & ") + " \\") | Out-Null
}
$lines.Add("\bottomrule") | Out-Null
$lines.Add("\end{tabular}") | Out-Null
$lines.Add("\end{center}") | Out-Null
$lines.Add("\subsection*{Outputs}") | Out-Null
$lines.Add("\begin{itemize}") | Out-Null
foreach ($path in @($signPath, $groupPath, $testPath)) {
    $lines.Add("\item \texttt{" + (ConvertTo-LatexText $path) + "}") | Out-Null
}
$lines.Add("\end{itemize}") | Out-Null
$lines.Add("\end{document}") | Out-Null
$lines | Set-Content -Path $texPath -Encoding UTF8

"Wrote $signPath"
"Wrote $groupPath"
"Wrote $testPath"
"Wrote $texPath"
