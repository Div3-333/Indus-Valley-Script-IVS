param(
    [string]$CorpusPath = "data/ivs_corpus_cleaned.csv",
    [string]$InventoryPath = "outputs/sign_inventory_stats.csv",
    [string]$PairPath = "outputs/sign_neighbor_similarity.csv",
    [string]$ClusterPath = "outputs/sign_neighbor_clusters.csv",
    [string]$OutDir = "outputs",
    [int]$TopPairs = 80,
    [int]$TopReportRows = 20
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

function Get-Jaccard($A, $B) {
    $setA = @{}
    $setB = @{}
    foreach ($item in $A) {
        if ($null -ne $item -and [string]$item -ne "") { $setA[[string]$item] = $true }
    }
    foreach ($item in $B) {
        if ($null -ne $item -and [string]$item -ne "") { $setB[[string]$item] = $true }
    }
    if ($setA.Count -eq 0 -and $setB.Count -eq 0) { return 0.0 }

    $intersection = 0
    foreach ($key in $setA.Keys) {
        if ($setB.ContainsKey($key)) { $intersection += 1 }
    }
    $union = $setA.Count
    foreach ($key in $setB.Keys) {
        if (-not $setA.ContainsKey($key)) { $union += 1 }
    }
    return [math]::Round($intersection / $union, 4)
}

function Get-PriorityTier($Pair, $InventoryA, $InventoryB, [int]$SameTextCount) {
    $cosine = [double]$Pair.Cosine
    $minTokens = [math]::Min([int]$Pair.TotalA, [int]$Pair.TotalB)
    $shared = [int]$Pair.SharedFeatures

    if ($cosine -ge 0.95 -and $minTokens -ge 50 -and $shared -ge 7) { return "Tier1" }
    if ($cosine -ge 0.95 -and ($minTokens -ge 20 -or $shared -ge 5)) { return "Tier2" }
    if ($cosine -ge 0.90 -and ($minTokens -ge 10 -or $SameTextCount -gt 0)) { return "Tier3" }
    return "Sparse"
}

function Get-TierRank([string]$Tier) {
    if ($Tier -eq "Tier1") { return 1 }
    if ($Tier -eq "Tier2") { return 2 }
    if ($Tier -eq "Tier3") { return 3 }
    return 4
}

$rows = Import-Csv -Path $CorpusPath
$inventoryRows = Import-Csv -Path $InventoryPath
$pairRows = Import-Csv -Path $PairPath
$clusterRows = Import-Csv -Path $ClusterPath

$inventoryBySign = @{}
foreach ($row in $inventoryRows) {
    $inventoryBySign[$row.Sign] = $row
}

$clusterBySign = @{}
foreach ($cluster in $clusterRows) {
    $signs = @(([string]$cluster.Signs).Split(" ", [System.StringSplitOptions]::RemoveEmptyEntries))
    foreach ($sign in $signs) {
        if (-not $clusterBySign.ContainsKey($sign)) {
            $clusterBySign[$sign] = New-Object System.Collections.Generic.List[string]
        }
        $clusterBySign[$sign].Add($cluster.ClusterId) | Out-Null
    }
}

$records = New-Object System.Collections.Generic.List[object]
$contextsBySign = @{}

foreach ($row in $rows) {
    $tokens = Get-SignTokens $row.text
    if ($tokens.Count -eq 0) { continue }

    $dir = ([string]$row.'dir.').Trim()
    $readingTokens = @($tokens | Where-Object { $_ -ne "999" })
    [array]::Reverse($readingTokens)

    $record = [pscustomobject]@{
        Id = $row.id
        Cisi = $row.cisi
        Site = $row.site
        Region = $row.region
        Type = $row.type
        Complete = $row.complete
        Direction = $dir
        Text = $row.text
        Tokens = @($readingTokens)
    }
    $records.Add($record) | Out-Null

    foreach ($token in ($readingTokens | Where-Object { $_ -notin @("000", "999") } | Select-Object -Unique)) {
        if (-not $contextsBySign.ContainsKey($token)) {
            $contextsBySign[$token] = New-Object System.Collections.Generic.List[object]
        }
        $contextsBySign[$token].Add($record) | Out-Null
    }
}

$candidatePairs = $pairRows |
    Sort-Object -Property @{Expression={[double]$_.Cosine}; Descending=$true}, @{Expression={[int]$_.SharedFeatures}; Descending=$true} |
    Select-Object -First $TopPairs

$reviewRows = New-Object System.Collections.Generic.List[object]
$exampleRows = New-Object System.Collections.Generic.List[object]

foreach ($pair in $candidatePairs) {
    $a = $pair.SignA
    $b = $pair.SignB
    $invA = if ($inventoryBySign.ContainsKey($a)) { $inventoryBySign[$a] } else { $null }
    $invB = if ($inventoryBySign.ContainsKey($b)) { $inventoryBySign[$b] } else { $null }
    $contextsA = if ($contextsBySign.ContainsKey($a)) { @($contextsBySign[$a]) } else { @() }
    $contextsB = if ($contextsBySign.ContainsKey($b)) { @($contextsBySign[$b]) } else { @() }

    $idsB = @{}
    foreach ($record in $contextsB) { $idsB[$record.Id] = $record }
    $sameTextRecords = @($contextsA | Where-Object { $idsB.ContainsKey($_.Id) })

    $adjacentCount = 0
    foreach ($record in $sameTextRecords) {
        $tokens = @($record.Tokens)
        for ($i = 0; $i -lt ($tokens.Count - 1); $i++) {
            if (($tokens[$i] -eq $a -and $tokens[$i + 1] -eq $b) -or ($tokens[$i] -eq $b -and $tokens[$i + 1] -eq $a)) {
                $adjacentCount += 1
            }
        }
    }

    $sitesA = @($contextsA | Select-Object -ExpandProperty Site -Unique)
    $sitesB = @($contextsB | Select-Object -ExpandProperty Site -Unique)
    $typesA = @($contextsA | Select-Object -ExpandProperty Type -Unique)
    $typesB = @($contextsB | Select-Object -ExpandProperty Type -Unique)
    $siteJaccard = Get-Jaccard $sitesA $sitesB
    $typeJaccard = Get-Jaccard $typesA $typesB

    $clusterIds = New-Object System.Collections.Generic.List[string]
    if ($clusterBySign.ContainsKey($a)) {
        foreach ($id in $clusterBySign[$a]) { $clusterIds.Add($id) | Out-Null }
    }
    if ($clusterBySign.ContainsKey($b)) {
        foreach ($id in $clusterBySign[$b]) {
            if (-not $clusterIds.Contains($id)) { $clusterIds.Add($id) | Out-Null }
        }
    }
    $clusterText = if ($clusterIds.Count -gt 0) { ($clusterIds | Sort-Object) -join " " } else { "" }
    $sameCluster = "N"
    if ($clusterBySign.ContainsKey($a) -and $clusterBySign.ContainsKey($b)) {
        foreach ($id in $clusterBySign[$a]) {
            if ($clusterBySign[$b].Contains($id)) { $sameCluster = "Y" }
        }
    }

    $priorityTier = Get-PriorityTier $pair $invA $invB $sameTextRecords.Count
    $reviewAction = switch ($priorityTier) {
        "Tier1" { "Immediate visual/catalog review" }
        "Tier2" { "High-priority visual/catalog review" }
        "Tier3" { "Review after Tier1/Tier2" }
        default { "Sparse-data hold" }
    }

    $reviewRows.Add([pscustomobject]@{
        SignA = $a
        SignB = $b
        Cosine = $pair.Cosine
        SharedFeatures = $pair.SharedFeatures
        TotalA = $pair.TotalA
        TotalB = $pair.TotalB
        CandidateA = if ($null -ne $invA) { $invA.CandidateClasses } else { "" }
        CandidateB = if ($null -ne $invB) { $invB.CandidateClasses } else { "" }
        StartPctA = if ($null -ne $invA) { $invA.StartPct } else { "" }
        StartPctB = if ($null -ne $invB) { $invB.StartPct } else { "" }
        EndPctA = if ($null -ne $invA) { $invA.EndPct } else { "" }
        EndPctB = if ($null -ne $invB) { $invB.EndPct } else { "" }
        MedialPctA = if ($null -ne $invA) { $invA.MedialPct } else { "" }
        MedialPctB = if ($null -ne $invB) { $invB.MedialPct } else { "" }
        SiteJaccard = $siteJaccard
        TypeJaccard = $typeJaccard
        SameTextCount = $sameTextRecords.Count
        AdjacentCount = $adjacentCount
        ClusterIds = $clusterText
        SameCluster = $sameCluster
        ReviewRank = Get-TierRank $priorityTier
        ReviewTier = $priorityTier
        ReviewAction = $reviewAction
        VisualCatalogStatus = "Pending"
        PreliminaryVerdict = "Distributional candidate only"
    }) | Out-Null

    foreach ($record in ($sameTextRecords | Select-Object -First 5)) {
        $exampleRows.Add([pscustomobject]@{
            SignA = $a
            SignB = $b
            ReviewRank = Get-TierRank $priorityTier
            ReviewTier = $priorityTier
            Id = $record.Id
            Cisi = $record.Cisi
            Site = $record.Site
            Type = $record.Type
            Complete = $record.Complete
            Direction = $record.Direction
            Text = $record.Text
        }) | Out-Null
    }
}

$reviewPath = Join-Path $OutDir "visual_catalog_review_candidates.csv"
$examplesPath = Join-Path $OutDir "visual_catalog_review_examples.csv"
$protocolPath = Join-Path $OutDir "visual_catalog_review_protocol.csv"
$sourceStatusPath = Join-Path $OutDir "visual_catalog_source_status.csv"
$summaryPath = Join-Path $OutDir "visual_catalog_review.tex"

$reviewRows |
    Sort-Object -Property ReviewRank, @{Expression={[double]$_.Cosine}; Descending=$true} |
    Export-Csv -NoTypeInformation -Path $reviewPath

$exampleRows |
    Where-Object { $_.ReviewTier -ne "Sparse" } |
    Sort-Object ReviewRank, SignA, SignB, Id |
    Export-Csv -NoTypeInformation -Path $examplesPath

$protocolRows = @(
    [pscustomobject]@{Step="1"; Criterion="Shape"; Question="Are the two catalog signs graphically similar enough to be variants?"; RequiredEvidence="Catalog image or artifact image"},
    [pscustomobject]@{Step="2"; Criterion="Direction"; Question="Could mirroring or reversal explain the difference?"; RequiredEvidence="Directionality, asymmetric signs, artifact layout"},
    [pscustomobject]@{Step="3"; Criterion="Space"; Question="Could crowding or line-end compression explain the difference?"; RequiredEvidence="Artifact image and sign position"},
    [pscustomobject]@{Step="4"; Criterion="Context"; Question="Do positions, neighbors, sites, and artifact types support functional equivalence?"; RequiredEvidence="Inventory and neighbor outputs"},
    [pscustomobject]@{Step="5"; Criterion="Independence"; Question="Do both signs occur in enough independent texts to avoid a repeated-object artifact?"; RequiredEvidence="CISI/ICIT IDs and duplicate checks"},
    [pscustomobject]@{Step="6"; Criterion="Verdict"; Question="Should the pair be merged, linked as variants, kept distinct, or held pending?"; RequiredEvidence="All previous fields"}
)
$protocolRows | Export-Csv -NoTypeInformation -Path $protocolPath

$sourceStatusRows = @(
    [pscustomobject]@{Source="Local workspace images"; Status="Unavailable"; Use="No local sign or artifact image assets were found in this workspace."},
    [pscustomobject]@{Source="ICIT/Epigraphica"; Status="Catalog described, images not harvested"; Use="Primary sign-catalog target; requires direct catalog/image access before visual verdicts."},
    [pscustomobject]@{Source="Harappa catalog review"; Status="Public descriptive source"; Use="Confirms catalog scope and scholarly importance, but not a machine-readable sign-image table."},
    [pscustomobject]@{Source="Daggumati and Revesz 2021"; Status="Open-access method source"; Use="Supplies allograph-review logic: shape, mirroring, direction, space, and catalog error checks."},
    [pscustomobject]@{Source="CISI volumes"; Status="Not locally available"; Use="Artifact-image authority; images must be consulted through legitimate access before merge decisions."}
)
$sourceStatusRows | Export-Csv -NoTypeInformation -Path $sourceStatusPath

$tierRows = $reviewRows |
    Group-Object ReviewTier |
    Select-Object @{Name="Rank"; Expression={Get-TierRank $_.Name}}, @{Name="Tier"; Expression={$_.Name}}, @{Name="Pairs"; Expression={$_.Count}} |
    Sort-Object Rank

$topReviewRows = $reviewRows |
    Where-Object { $_.ReviewTier -in @("Tier1", "Tier2", "Tier3") } |
    Sort-Object -Property @{Expression={ if ($_.ReviewTier -eq "Tier1") { 1 } elseif ($_.ReviewTier -eq "Tier2") { 2 } elseif ($_.ReviewTier -eq "Tier3") { 3 } else { 4 } }}, @{Expression={[double]$_.Cosine}; Descending=$true} |
    Select-Object -First $TopReportRows SignA, SignB, Cosine, TotalA, TotalB, SiteJaccard, TypeJaccard, SameTextCount, ReviewTier

$summary = New-Object System.Collections.Generic.List[string]
$summary.Add("\documentclass[11pt,a4paper]{article}") | Out-Null
$summary.Add("\usepackage[margin=1in]{geometry}") | Out-Null
$summary.Add("\usepackage[T1]{fontenc}") | Out-Null
$summary.Add("\usepackage[utf8]{inputenc}") | Out-Null
$summary.Add("\usepackage{booktabs}") | Out-Null
$summary.Add("\begin{document}") | Out-Null
$summary.Add("\section*{Visual and Catalog Review Pack}") | Out-Null
$summary.Add("") | Out-Null
$summary.Add("This report prepares distributional candidates for visual/catalog review. It does not merge signs. All candidates remain pending until sign-catalog images or artifact images are inspected.") | Out-Null
$summary.Add("") | Out-Null
$summary.Add("\subsection*{Review Tiers}") | Out-Null
Format-LatexTable $tierRows @("Tier", "Pairs") | ForEach-Object { $summary.Add($_) | Out-Null }
$summary.Add("") | Out-Null
$summary.Add("\subsection*{Source Status}") | Out-Null
Format-LatexTable $sourceStatusRows @("Source", "Status") | ForEach-Object { $summary.Add($_) | Out-Null }
$summary.Add("") | Out-Null
$summary.Add("\subsection*{Top Review Candidates}") | Out-Null
Format-LatexTable $topReviewRows @("SignA", "SignB", "Cosine", "TotalA", "TotalB", "SiteJaccard", "TypeJaccard", "SameTextCount", "ReviewTier") | ForEach-Object { $summary.Add($_) | Out-Null }
$summary.Add("") | Out-Null
$summary.Add("\subsection*{Protocol}") | Out-Null
$summary.Add("\begin{enumerate}") | Out-Null
foreach ($row in $protocolRows) {
    $summary.Add("\item \textbf{" + (ConvertTo-LatexText $row.Criterion) + ":} " + (ConvertTo-LatexText $row.Question)) | Out-Null
}
$summary.Add("\end{enumerate}") | Out-Null
$summary.Add("\subsection*{Output Files}") | Out-Null
$summary.Add("\begin{itemize}") | Out-Null
foreach ($path in @($reviewPath, $examplesPath, $protocolPath, $sourceStatusPath)) {
    $summary.Add("\item \texttt{" + (ConvertTo-LatexText $path) + "}") | Out-Null
}
$summary.Add("\end{itemize}") | Out-Null
$summary.Add("\end{document}") | Out-Null

$summary | Set-Content -Path $summaryPath -Encoding UTF8

"Wrote $reviewPath"
"Wrote $examplesPath"
"Wrote $protocolPath"
"Wrote $sourceStatusPath"
"Wrote $summaryPath"
