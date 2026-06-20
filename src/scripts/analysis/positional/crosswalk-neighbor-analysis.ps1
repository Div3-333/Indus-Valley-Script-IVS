param(
    [string]$CorpusPath = "data/ivs_corpus_cleaned.csv",
    [string]$InventoryPath = "outputs/sign_inventory_stats.csv",
    [string]$OutDir = "outputs",
    [int]$MinSignTokens = 5,
    [int]$TopPairs = 200,
    [double]$ClusterCosineThreshold = 0.90,
    [int]$MinSharedFeatures = 2
)

if (-not (Test-Path $OutDir)) {
    New-Item -ItemType Directory -Force -Path $OutDir | Out-Null
}

function Get-SignTokens([string]$Text) {
    return @([regex]::Matches($Text, '(?<!\d)\d{3,4}(?!\d)') | ForEach-Object { $_.Value })
}

function Add-Count($Table, [string]$Key, [int]$Amount = 1) {
    if (-not $Table.ContainsKey($Key)) {
        $Table[$Key] = 0
    }
    $Table[$Key] = [int]$Table[$Key] + $Amount
}

function Add-NestedCount($Table, [string]$Outer, [string]$Inner, [int]$Amount = 1) {
    if (-not $Table.ContainsKey($Outer)) {
        $Table[$Outer] = @{}
    }
    Add-Count $Table[$Outer] $Inner $Amount
}

function ConvertTo-LatexText([string]$Value) {
    if ($null -eq $Value) { return "" }
    $text = $Value -replace '\\', '/'
    $text = $text -replace '_', '\_'
    $text = $text -replace '%', '\%'
    $text = $text -replace '&', '\&'
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
        $values = foreach ($column in $Columns) { ConvertTo-LatexText ([string]$row.$column) }
        $lines.Add(($values -join " & ") + " \\") | Out-Null
    }
    $lines.Add("\bottomrule") | Out-Null
    $lines.Add("\end{tabular}") | Out-Null
    $lines.Add("\end{center}") | Out-Null
    return $lines
}

function Get-Cosine($VectorA, $VectorB) {
    $dot = 0.0
    $normA = 0.0
    $normB = 0.0
    $shared = 0

    foreach ($key in $VectorA.Keys) {
        $a = [double]$VectorA[$key]
        $normA += $a * $a
        if ($VectorB.ContainsKey($key)) {
            $b = [double]$VectorB[$key]
            $dot += $a * $b
            $shared += 1
        }
    }
    foreach ($key in $VectorB.Keys) {
        $b = [double]$VectorB[$key]
        $normB += $b * $b
    }

    if ($normA -eq 0 -or $normB -eq 0) {
        return [pscustomobject]@{ Cosine = 0.0; Shared = 0 }
    }
    return [pscustomobject]@{
        Cosine = [math]::Round($dot / ([math]::Sqrt($normA) * [math]::Sqrt($normB)), 6)
        Shared = $shared
    }
}

function Find-Root($Parent, [string]$Node) {
    if (-not $Parent.ContainsKey($Node)) {
        $Parent[$Node] = $Node
        return $Node
    }
    $root = $Node
    while ($Parent[$root] -ne $root) {
        $root = $Parent[$root]
    }
    $current = $Node
    while ($Parent[$current] -ne $current) {
        $next = $Parent[$current]
        $Parent[$current] = $root
        $current = $next
    }
    return $root
}

function Union-Nodes($Parent, [string]$A, [string]$B) {
    $rootA = Find-Root $Parent $A
    $rootB = Find-Root $Parent $B
    if ($rootA -ne $rootB) {
        $Parent[$rootB] = $rootA
    }
}

$rows = Import-Csv -Path $CorpusPath
$inventoryRows = if (Test-Path $InventoryPath) { Import-Csv -Path $InventoryPath } else { @() }
$inventoryBySign = @{}
foreach ($row in $inventoryRows) {
    $inventoryBySign[$row.Sign] = $row
}

$allCodeCounts = @{}
$featureVectors = @{}
$neighborEdges = @{}
$textsUsed = 0
$textsSkipped = 0

foreach ($row in $rows) {
    $tokens = Get-SignTokens $row.text
    foreach ($token in $tokens) {
        Add-Count $allCodeCounts $token
    }

    $dir = ([string]$row.'dir.').Trim()
    $hasUncertainToken = $tokens -contains "000"
    $hasTextDamage = ([string]$row.text) -match '[\[\]\?]'
    $usable = ($row.complete -eq "Y") -and (-not $hasUncertainToken) -and (-not $hasTextDamage) -and (($dir -in @("R/L", "L/R")) -or ($tokens.Count -eq 1))

    if (-not $usable) {
        $textsSkipped += 1
        continue
    }

    $readingTokens = @($tokens)
    [array]::Reverse($readingTokens)
    $readingTokens = @($readingTokens | Where-Object { $_ -ne "999" })
    if ($readingTokens.Count -eq 0) { continue }
    $textsUsed += 1

    for ($i = 0; $i -lt $readingTokens.Count; $i++) {
        $sign = $readingTokens[$i]
        if ($sign -in @("000", "999")) { continue }

        $prev = if ($i -eq 0) { "START" } else { $readingTokens[$i - 1] }
        $next = if ($i -eq ($readingTokens.Count - 1)) { "END" } else { $readingTokens[$i + 1] }

        Add-NestedCount $featureVectors $sign ("P:" + $prev)
        Add-NestedCount $featureVectors $sign ("N:" + $next)
        Add-NestedCount $neighborEdges $sign ("Prev:" + $prev)
        Add-NestedCount $neighborEdges $sign ("Next:" + $next)
    }
}

$crosswalkRows = foreach ($code in ($allCodeCounts.Keys | Sort-Object)) {
    $inv = if ($inventoryBySign.ContainsKey($code)) { $inventoryBySign[$code] } else { $null }
    $status = "NeedsReview"
    $icitCode = ""
    $evidence = "Observed code does not match the expected local code pattern."

    if ($code -eq "000") {
        $status = "ErodedUnknown"
        $evidence = "ICIT documentation treats 000 as one eroded sign."
    }
    elseif ($code -eq "999") {
        $status = "EncodedSpace"
        $evidence = "ICIT-derived corpora may use 999 for a blank space between signs."
    }
    elseif ($code -match '^\d{3,4}$') {
        $status = "ProvisionalIdentity"
        $icitCode = $code
        $evidence = "Local corpus uses ICIT-style sign-code notation; identity mapping is provisional until checked against the Wells/ICIT sign catalog."
    }

    [pscustomobject]@{
        LocalCode = $code
        IcitWellsCode = $icitCode
        Status = $status
        TotalTokens = [int]$allCodeCounts[$code]
        RarityBand = if ($null -ne $inv) { $inv.RarityBand } else { "" }
        CandidateClasses = if ($null -ne $inv) { $inv.CandidateClasses } else { "" }
        Evidence = $evidence
    }
}

$eligibleSigns = @($featureVectors.Keys |
    Where-Object {
        $_ -ne "000" -and
        $_ -ne "999" -and
        $allCodeCounts.ContainsKey($_) -and
        [int]$allCodeCounts[$_] -ge $MinSignTokens
    } |
    Sort-Object)

$neighborRows = foreach ($sign in ($neighborEdges.Keys | Sort-Object)) {
    foreach ($edgeKey in ($neighborEdges[$sign].Keys | Sort-Object)) {
        $parts = $edgeKey.Split(":", 2)
        [pscustomobject]@{
            Sign = $sign
            Side = $parts[0]
            Neighbor = $parts[1]
            Count = [int]$neighborEdges[$sign][$edgeKey]
        }
    }
}

$pairRows = New-Object System.Collections.Generic.List[object]
for ($i = 0; $i -lt $eligibleSigns.Count; $i++) {
    for ($j = $i + 1; $j -lt $eligibleSigns.Count; $j++) {
        $a = $eligibleSigns[$i]
        $b = $eligibleSigns[$j]
        $score = Get-Cosine $featureVectors[$a] $featureVectors[$b]
        if ($score.Shared -lt $MinSharedFeatures) { continue }

        $pairRows.Add([pscustomobject]@{
            SignA = $a
            SignB = $b
            TotalA = [int]$allCodeCounts[$a]
            TotalB = [int]$allCodeCounts[$b]
            SharedFeatures = $score.Shared
            Cosine = $score.Cosine
            ReviewPriority = if ($score.Cosine -ge $ClusterCosineThreshold) { "High" } elseif ($score.Cosine -ge 0.50) { "Medium" } else { "Low" }
        }) | Out-Null
    }
}

$pairRowsSorted = @($pairRows | Sort-Object -Property @{Expression="Cosine"; Descending=$true}, @{Expression="SharedFeatures"; Descending=$true}, SignA, SignB)

$parent = @{}
foreach ($sign in $eligibleSigns) {
    $parent[$sign] = $sign
}

foreach ($pair in $pairRowsSorted) {
    if ([double]$pair.Cosine -ge $ClusterCosineThreshold -and [int]$pair.SharedFeatures -ge $MinSharedFeatures) {
        Union-Nodes $parent $pair.SignA $pair.SignB
    }
}

$groups = @{}
foreach ($sign in $eligibleSigns) {
    $root = Find-Root $parent $sign
    if (-not $groups.ContainsKey($root)) {
        $groups[$root] = New-Object System.Collections.Generic.List[string]
    }
    $groups[$root].Add($sign) | Out-Null
}

$clusterIndex = 1
$clusterRows = foreach ($group in ($groups.Values | Where-Object { $_.Count -gt 1 } | Sort-Object -Property Count -Descending)) {
    $signs = @($group | Sort-Object)
    $tokenSum = 0
    foreach ($sign in $signs) {
        $tokenSum += [int]$allCodeCounts[$sign]
    }
    [pscustomobject]@{
        ClusterId = "N" + $clusterIndex.ToString("000")
        Size = $signs.Count
        Signs = $signs -join " "
        TokenSum = $tokenSum
        Threshold = $ClusterCosineThreshold
    }
    $clusterIndex += 1
}

$crosswalkPath = Join-Path $OutDir "icit_wells_crosswalk_provisional.csv"
$neighborPath = Join-Path $OutDir "sign_neighbor_edges.csv"
$pairPath = Join-Path $OutDir "sign_neighbor_similarity.csv"
$topPairPath = Join-Path $OutDir "sign_neighbor_similarity_top.csv"
$clusterPath = Join-Path $OutDir "sign_neighbor_clusters.csv"
$summaryPath = Join-Path $OutDir "crosswalk_neighbor_analysis.tex"

$crosswalkRows | Sort-Object LocalCode | Export-Csv -NoTypeInformation -Path $crosswalkPath
$neighborRows | Sort-Object Sign, Side, @{Expression="Count"; Descending=$true} | Export-Csv -NoTypeInformation -Path $neighborPath
$pairRowsSorted | Export-Csv -NoTypeInformation -Path $pairPath
$pairRowsSorted | Select-Object -First $TopPairs | Export-Csv -NoTypeInformation -Path $topPairPath
$clusterRows | Export-Csv -NoTypeInformation -Path $clusterPath

$statusRows = $crosswalkRows |
    Group-Object Status |
    Select-Object @{Name="Status"; Expression={$_.Name}}, @{Name="Codes"; Expression={$_.Count}}, @{Name="Tokens"; Expression={($_.Group | Measure-Object -Property TotalTokens -Sum).Sum}} |
    Sort-Object Status

$topPairsForReport = $pairRowsSorted |
    Select-Object -First 12 SignA, SignB, TotalA, TotalB, SharedFeatures, Cosine

$clustersForReport = $clusterRows |
    Select-Object -First 12 ClusterId, Size, Signs, TokenSum

$overviewRows = @(
    [pscustomobject]@{Measure="TextsUsedForNeighbors"; Value=$textsUsed},
    [pscustomobject]@{Measure="TextsSkipped"; Value=$textsSkipped},
    [pscustomobject]@{Measure="EligibleSigns"; Value=$eligibleSigns.Count},
    [pscustomobject]@{Measure="PairRows"; Value=$pairRowsSorted.Count},
    [pscustomobject]@{Measure="Clusters"; Value=@($clusterRows).Count}
)

$summary = New-Object System.Collections.Generic.List[string]
$summary.Add("\documentclass[11pt,a4paper]{article}") | Out-Null
$summary.Add("\usepackage[margin=1in]{geometry}") | Out-Null
$summary.Add("\usepackage[T1]{fontenc}") | Out-Null
$summary.Add("\usepackage[utf8]{inputenc}") | Out-Null
$summary.Add("\usepackage{booktabs}") | Out-Null
$summary.Add("\begin{document}") | Out-Null
$summary.Add("\section*{Crosswalk and Neighbor-Profile Analysis}") | Out-Null
$summary.Add("") | Out-Null
$summary.Add("This report creates a provisional local-code to ICIT/Wells-code identity crosswalk and groups signs by normalized preceding/following neighbor profiles. Similarity is a triage signal for visual and catalog review, not an allograph claim.") | Out-Null
$summary.Add("") | Out-Null
$summary.Add("\subsection*{Overview}") | Out-Null
Format-LatexTable $overviewRows @("Measure", "Value") | ForEach-Object { $summary.Add($_) | Out-Null }
$summary.Add("") | Out-Null
$summary.Add("\subsection*{Crosswalk Status}") | Out-Null
Format-LatexTable $statusRows @("Status", "Codes", "Tokens") | ForEach-Object { $summary.Add($_) | Out-Null }
$summary.Add("") | Out-Null
$summary.Add("\subsection*{Top Similarity Pairs}") | Out-Null
Format-LatexTable $topPairsForReport @("SignA", "SignB", "TotalA", "TotalB", "SharedFeatures", "Cosine") | ForEach-Object { $summary.Add($_) | Out-Null }
$summary.Add("") | Out-Null
$summary.Add("\subsection*{Neighbor Clusters}") | Out-Null
Format-LatexTable $clustersForReport @("ClusterId", "Size", "Signs", "TokenSum") | ForEach-Object { $summary.Add($_) | Out-Null }
$summary.Add("") | Out-Null
$summary.Add("\subsection*{Output Files}") | Out-Null
$summary.Add("\begin{itemize}") | Out-Null
foreach ($path in @($crosswalkPath, $neighborPath, $pairPath, $topPairPath, $clusterPath)) {
    $summary.Add("\item \texttt{" + (ConvertTo-LatexText $path) + "}") | Out-Null
}
$summary.Add("\end{itemize}") | Out-Null
$summary.Add("\end{document}") | Out-Null

$summary | Set-Content -Path $summaryPath -Encoding UTF8

"Wrote $crosswalkPath"
"Wrote $neighborPath"
"Wrote $pairPath"
"Wrote $topPairPath"
"Wrote $clusterPath"
"Wrote $summaryPath"
