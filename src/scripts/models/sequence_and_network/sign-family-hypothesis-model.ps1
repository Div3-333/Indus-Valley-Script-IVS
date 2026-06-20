param(
    [string]$CorpusPath = "data/ivs_corpus_cleaned.csv",
    [string]$PairPath = "outputs/visual_catalog_review_candidates.csv",
    [string]$OutDir = "outputs",
    [int]$PermutationIterations = 75,
    [int]$RandomSeed = 1729
)

if (-not (Test-Path $OutDir)) {
    New-Item -ItemType Directory -Force -Path $OutDir | Out-Null
}

function Get-SignTokens([string]$Text) {
    return @([regex]::Matches($Text, '(?<!\d)\d{3,4}(?!\d)') | ForEach-Object { $_.Value })
}

function Test-MissingValue([string]$Value) {
    if ($null -eq $Value) { return $true }
    $trimmed = $Value.Trim()
    return ($trimmed -eq "" -or $trimmed -in @("-", "--", "- -", "?", "??", "None", "none"))
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

function Get-PairKey([string]$A, [string]$B) {
    $values = @($A, $B) | Sort-Object
    return ($values -join "/")
}

function Add-NestedCount($Root, [string]$Sign, [string]$Field, [string]$Value) {
    if (-not $Root.ContainsKey($Sign)) {
        $Root[$Sign] = @{}
    }
    if (-not $Root[$Sign].ContainsKey($Field)) {
        $Root[$Sign][$Field] = @{}
    }
    if (-not $Root[$Sign][$Field].ContainsKey($Value)) {
        $Root[$Sign][$Field][$Value] = 0
    }
    $Root[$Sign][$Field][$Value] += 1
}

function Get-Counts($Root, [string]$Sign, [string]$Field) {
    if ($Root.ContainsKey($Sign) -and $Root[$Sign].ContainsKey($Field)) {
        return $Root[$Sign][$Field]
    }
    return @{}
}

function Get-CountSum($Counts) {
    $sum = 0
    foreach ($value in $Counts.Values) {
        $sum += [int]$value
    }
    return $sum
}

function Get-JensenShannonDivergence($CountsA, $CountsB) {
    $totalA = Get-CountSum $CountsA
    $totalB = Get-CountSum $CountsB
    if ($totalA -eq 0 -or $totalB -eq 0) { return $null }

    $keys = @{}
    foreach ($key in $CountsA.Keys) { $keys[[string]$key] = $true }
    foreach ($key in $CountsB.Keys) { $keys[[string]$key] = $true }

    $jsd = 0.0
    foreach ($key in $keys.Keys) {
        $p = 0.0
        $q = 0.0
        if ($CountsA.ContainsKey($key)) { $p = [double]$CountsA[$key] / $totalA }
        if ($CountsB.ContainsKey($key)) { $q = [double]$CountsB[$key] / $totalB }
        $m = ($p + $q) / 2.0
        if ($p -gt 0) { $jsd += 0.5 * $p * ([math]::Log($p / $m) / [math]::Log(2)) }
        if ($q -gt 0) { $jsd += 0.5 * $q * ([math]::Log($q / $m) / [math]::Log(2)) }
    }
    return [math]::Round($jsd, 6)
}

function Expand-Counts($Counts) {
    $items = New-Object System.Collections.Generic.List[string]
    foreach ($key in $Counts.Keys) {
        for ($i = 0; $i -lt [int]$Counts[$key]; $i++) {
            $items.Add([string]$key) | Out-Null
        }
    }
    return $items.ToArray()
}

function Convert-ArrayToCounts($Values, [int]$Start, [int]$Length) {
    $counts = @{}
    for ($i = $Start; $i -lt ($Start + $Length); $i++) {
        $value = [string]$Values[$i]
        if (-not $counts.ContainsKey($value)) { $counts[$value] = 0 }
        $counts[$value] += 1
    }
    return $counts
}

function Get-PermutationPValue($CountsA, $CountsB, [Nullable[double]]$Observed, [int]$Iterations, $Random) {
    if ($null -eq $Observed -or $Iterations -le 0) { return "" }
    $valuesA = Expand-Counts $CountsA
    $valuesB = Expand-Counts $CountsB
    $nA = $valuesA.Count
    $nB = $valuesB.Count
    if ($nA -eq 0 -or $nB -eq 0) { return "" }

    $combined = New-Object string[] ($nA + $nB)
    [array]::Copy($valuesA, 0, $combined, 0, $nA)
    [array]::Copy($valuesB, 0, $combined, $nA, $nB)

    $extreme = 0
    for ($iter = 0; $iter -lt $Iterations; $iter++) {
        $work = [string[]]$combined.Clone()
        for ($i = $work.Count - 1; $i -gt 0; $i--) {
            $j = $Random.Next(0, $i + 1)
            $tmp = $work[$i]
            $work[$i] = $work[$j]
            $work[$j] = $tmp
        }
        $simA = Convert-ArrayToCounts $work 0 $nA
        $simB = Convert-ArrayToCounts $work $nA $nB
        $simJsd = Get-JensenShannonDivergence $simA $simB
        if ($null -ne $simJsd -and $simJsd -ge ([double]$Observed - 0.0000001)) {
            $extreme += 1
        }
    }
    return [math]::Round(($extreme + 1.0) / ($Iterations + 1.0), 4)
}

function Get-DistributionStats($CountRoot, $TotalRoot, [string]$A, [string]$B, [string]$Field, [int]$Iterations, $Random) {
    $countsA = Get-Counts $CountRoot $A $Field
    $countsB = Get-Counts $CountRoot $B $Field
    $totalA = if ($TotalRoot.ContainsKey($A)) { [int]$TotalRoot[$A] } else { 0 }
    $totalB = if ($TotalRoot.ContainsKey($B)) { [int]$TotalRoot[$B] } else { 0 }
    $fieldTotal = (Get-CountSum $countsA) + (Get-CountSum $countsB)
    $coverage = 0.0
    if (($totalA + $totalB) -gt 0) {
        $coverage = [math]::Round($fieldTotal / ($totalA + $totalB), 4)
    }
    $jsd = Get-JensenShannonDivergence $countsA $countsB
    $p = Get-PermutationPValue $countsA $countsB $jsd $Iterations $Random
    return [pscustomobject]@{
        JSD = if ($null -eq $jsd) { "" } else { $jsd }
        Coverage = $coverage
        PValue = $p
    }
}

function Convert-ToDouble([string]$Value, [double]$Default = 0.0) {
    $parsed = 0.0
    if ([double]::TryParse($Value, [ref]$parsed)) { return $parsed }
    return $Default
}

function Clamp01([double]$Value) {
    if ($Value -lt 0) { return 0.0 }
    if ($Value -gt 1) { return 1.0 }
    return $Value
}

$rows = Import-Csv -Path $CorpusPath
$pairRows = Import-Csv -Path $PairPath
$random = [System.Random]::new($RandomSeed)

$fields = @("Region", "Site", "Type", "Period", "Phase", "Time")
$countsBySignField = @{}
$totalBySign = @{}

foreach ($row in $rows) {
    $tokens = Get-SignTokens $row.text
    if ($tokens.Count -eq 0) { continue }

    $readingTokens = @($tokens | Where-Object { $_ -notin @("000", "999") })
    [array]::Reverse($readingTokens)

    foreach ($sign in $readingTokens) {
        if (-not $totalBySign.ContainsKey($sign)) { $totalBySign[$sign] = 0 }
        $totalBySign[$sign] += 1

        $values = @{
            Region = $row.region
            Site = $row.site
            Type = $row.type
            Period = $row.period
            Phase = $row.phase
            Time = $row.time
        }
        foreach ($field in $fields) {
            $value = [string]$values[$field]
            if (-not (Test-MissingValue $value)) {
                Add-NestedCount $countsBySignField $sign $field $value.Trim()
            }
        }
    }
}

$visualPrior = @{
    (Get-PairKey "705" "706") = [pscustomobject]@{VisualClass="StrongBaseFamily"; VisualStrength=1.0; VisualNote="Same open-U/long-stem family with an added or emphasized inner nested stroke."}
    (Get-PairKey "817" "861") = [pscustomobject]@{VisualClass="ModerateEnclosedFamily"; VisualStrength=0.65; VisualNote="Both enclosed signs with angular internal marking, but outline and internal geometry differ."}
    (Get-PairKey "817" "820") = [pscustomobject]@{VisualClass="ModerateEnclosedFamily"; VisualStrength=0.65; VisualNote="Both enclosed signs, but internal structure differs."}
    (Get-PairKey "692" "920") = [pscustomobject]@{VisualClass="WeakVisualMatch"; VisualStrength=0.15; VisualNote="Crossed/X-shaped sign versus curved single-stroke sign."}
}

$featureRows = New-Object System.Collections.Generic.List[object]
$scoreRows = New-Object System.Collections.Generic.List[object]

foreach ($pair in $pairRows) {
    $a = [string]$pair.SignA
    $b = [string]$pair.SignB
    $pairKey = Get-PairKey $a $b
    $cosine = Convert-ToDouble $pair.Cosine
    $sameCluster = if ($pair.SameCluster -eq "Y") { 1.0 } else { 0.0 }

    $startA = Convert-ToDouble $pair.StartPctA
    $startB = Convert-ToDouble $pair.StartPctB
    $endA = Convert-ToDouble $pair.EndPctA
    $endB = Convert-ToDouble $pair.EndPctB
    $medialA = Convert-ToDouble $pair.MedialPctA
    $medialB = Convert-ToDouble $pair.MedialPctB
    $positionalDistance = 0.5 * ([math]::Abs($startA - $startB) + [math]::Abs($endA - $endB) + [math]::Abs($medialA - $medialB))
    $positionalSimilarity = Clamp01 (1.0 - $positionalDistance)

    $region = Get-DistributionStats $countsBySignField $totalBySign $a $b "Region" $PermutationIterations $random
    $site = Get-DistributionStats $countsBySignField $totalBySign $a $b "Site" $PermutationIterations $random
    $type = Get-DistributionStats $countsBySignField $totalBySign $a $b "Type" $PermutationIterations $random
    $period = Get-DistributionStats $countsBySignField $totalBySign $a $b "Period" $PermutationIterations $random
    $phase = Get-DistributionStats $countsBySignField $totalBySign $a $b "Phase" $PermutationIterations $random
    $time = Get-DistributionStats $countsBySignField $totalBySign $a $b "Time" $PermutationIterations $random

    $regionJsd = Convert-ToDouble ([string]$region.JSD)
    $siteJsd = Convert-ToDouble ([string]$site.JSD)
    $typeJsd = Convert-ToDouble ([string]$type.JSD)
    $periodJsd = Convert-ToDouble ([string]$period.JSD)
    $phaseJsd = Convert-ToDouble ([string]$phase.JSD)
    $timeJsd = Convert-ToDouble ([string]$time.JSD)
    $geoSeparation = [math]::Max($regionJsd, $siteJsd)
    $chronSeparation = [math]::Max($timeJsd, [math]::Max($periodJsd, $phaseJsd))
    $chronCoverage = [math]::Max([double]$time.Coverage, [math]::Max([double]$period.Coverage, [double]$phase.Coverage))
    $typeSimilarity = Clamp01 (1.0 - $typeJsd)

    if ($visualPrior.ContainsKey($pairKey)) {
        $visual = $visualPrior[$pairKey]
    } else {
        $visual = [pscustomobject]@{VisualClass="Unreviewed"; VisualStrength=0.25; VisualNote="No catalog-level visual adjudication yet."}
    }
    $visualReviewed = if ($visual.VisualClass -eq "Unreviewed") { "N" } else { "Y" }
    $visualStrength = [double]$visual.VisualStrength

    $allographScore = Clamp01 ((0.35 * $cosine) + (0.25 * $positionalSimilarity) + (0.25 * $visualStrength) + (0.15 * $typeSimilarity))
    $regionalScore = Clamp01 ($cosine * $positionalSimilarity * $geoSeparation * $typeSimilarity)
    $chronScore = Clamp01 ($cosine * $positionalSimilarity * $chronSeparation * $chronCoverage)
    $modifierScore = Clamp01 ($visualStrength * ((0.45 * $cosine) + (0.25 * $positionalDistance) + (0.15 * $typeSimilarity) + (0.15 * $sameCluster)))
    $functionalClusterScore = Clamp01 ($cosine * $positionalSimilarity * (1.0 - (0.65 * $visualStrength)))

    $topHypothesis = "NeedsVisualReview"
    $recommendedNextStep = "Acquire or inspect visual evidence before interpreting the distributional match."
    if ($visual.VisualClass -eq "WeakVisualMatch") {
        $topHypothesis = "FunctionalClusterNotAllograph"
        $recommendedNextStep = "Use as a control: high distributional similarity without visual equivalence."
    } elseif ($visual.VisualClass -eq "StrongBaseFamily") {
        $topHypothesis = "ModifierOrVariantCandidate"
        $recommendedNextStep = "Prioritize artifact-image review and test whether the added stroke changes context."
    } elseif ($visual.VisualClass -like "Moderate*") {
        $topHypothesis = "VisualFunctionalFamily"
        $recommendedNextStep = "Keep distinct for now; test whether related shapes mark the same syntactic family."
    } elseif ($allographScore -ge 0.82 -and $visualReviewed -eq "Y" -and $visualStrength -ge 0.85) {
        $topHypothesis = "AllographCandidate"
        $recommendedNextStep = "Run artifact-level review before changing the inventory."
    } elseif ($regionalScore -ge 0.18) {
        $topHypothesis = "RegionalAllographyTest"
        $recommendedNextStep = "Test whether the pair separates by site or region while retaining syntactic behavior."
    } elseif ($chronScore -ge 0.15) {
        $topHypothesis = "ChronologicalLayeringTest"
        $recommendedNextStep = "Audit period/phase metadata and test temporal split."
    } elseif ($functionalClusterScore -ge 0.55) {
        $topHypothesis = "FunctionalCluster"
        $recommendedNextStep = "Treat as a syntactic/functional class until visual evidence is reviewed."
    }

    $featureRows.Add([pscustomobject]@{
        SignA = $a
        SignB = $b
        ReviewTier = $pair.ReviewTier
        Cosine = [math]::Round($cosine, 6)
        PositionalDistance = [math]::Round($positionalDistance, 6)
        PositionalSimilarity = [math]::Round($positionalSimilarity, 6)
        VisualClass = $visual.VisualClass
        VisualReviewed = $visualReviewed
        VisualStrength = $visualStrength
        RegionJSD = $region.JSD
        RegionCoverage = $region.Coverage
        RegionPermutationP = $region.PValue
        SiteJSD = $site.JSD
        SiteCoverage = $site.Coverage
        SitePermutationP = $site.PValue
        TypeJSD = $type.JSD
        TypeCoverage = $type.Coverage
        TypePermutationP = $type.PValue
        PeriodJSD = $period.JSD
        PeriodCoverage = $period.Coverage
        PeriodPermutationP = $period.PValue
        PhaseJSD = $phase.JSD
        PhaseCoverage = $phase.Coverage
        PhasePermutationP = $phase.PValue
        TimeJSD = $time.JSD
        TimeCoverage = $time.Coverage
        TimePermutationP = $time.PValue
        SameCluster = $pair.SameCluster
        VisualNote = $visual.VisualNote
    }) | Out-Null

    $scoreRows.Add([pscustomobject]@{
        SignA = $a
        SignB = $b
        ReviewTier = $pair.ReviewTier
        VisualClass = $visual.VisualClass
        DistributionalSimilarity = [math]::Round($cosine, 6)
        PositionalSimilarity = [math]::Round($positionalSimilarity, 6)
        GeographicSeparation = [math]::Round($geoSeparation, 6)
        ChronologySeparation = [math]::Round($chronSeparation, 6)
        ChronologyCoverage = [math]::Round($chronCoverage, 4)
        AllographScore = [math]::Round($allographScore, 6)
        RegionalAllographyScore = [math]::Round($regionalScore, 6)
        ChronologicalLayeringScore = [math]::Round($chronScore, 6)
        ModifierScore = [math]::Round($modifierScore, 6)
        FunctionalClusterScore = [math]::Round($functionalClusterScore, 6)
        TopHypothesis = $topHypothesis
        RecommendedNextStep = $recommendedNextStep
    }) | Out-Null
}

$featurePath = Join-Path $OutDir "sign_family_pair_features.csv"
$scorePath = Join-Path $OutDir "sign_family_hypothesis_scores.csv"
$summaryPath = Join-Path $OutDir "sign_family_model_summary.csv"
$texPath = Join-Path $OutDir "sign_family_model.tex"

$featureRows | Export-Csv -NoTypeInformation -Path $featurePath
$scoreRows |
    Sort-Object ReviewTier, @{Expression={[double]$_.AllographScore}; Descending=$true} |
    Export-Csv -NoTypeInformation -Path $scorePath

$summaryRows = $scoreRows |
    Group-Object TopHypothesis |
    ForEach-Object {
        [pscustomobject]@{
            Hypothesis = $_.Name
            PairCount = $_.Count
            MeanAllographScore = [math]::Round((($_.Group | Measure-Object -Property AllographScore -Average).Average), 4)
            MeanModifierScore = [math]::Round((($_.Group | Measure-Object -Property ModifierScore -Average).Average), 4)
            MeanFunctionalClusterScore = [math]::Round((($_.Group | Measure-Object -Property FunctionalClusterScore -Average).Average), 4)
        }
    } |
    Sort-Object Hypothesis
$summaryRows | Export-Csv -NoTypeInformation -Path $summaryPath

$topRows = $scoreRows |
    Where-Object { $_.ReviewTier -in @("Tier1", "Tier2", "Tier3") } |
    Sort-Object @{Expression={ if ($_.ReviewTier -eq "Tier1") { 1 } elseif ($_.ReviewTier -eq "Tier2") { 2 } else { 3 } }}, @{Expression={[double]$_.AllographScore}; Descending=$true} |
    Select-Object -First 16

$lines = New-Object System.Collections.Generic.List[string]
$lines.Add("\documentclass[11pt,a4paper]{article}") | Out-Null
$lines.Add("\usepackage[margin=1in]{geometry}") | Out-Null
$lines.Add("\usepackage[T1]{fontenc}") | Out-Null
$lines.Add("\usepackage[utf8]{inputenc}") | Out-Null
$lines.Add("\usepackage{booktabs}") | Out-Null
$lines.Add("\begin{document}") | Out-Null
$lines.Add("\section*{Sign-Family Hypothesis Model}") | Out-Null
$lines.Add("This report scores candidate sign pairs as allograph, regional, chronological, modifier, or functional-cluster hypotheses. Scores are heuristic and auditable; they do not change the sign inventory.") | Out-Null
$lines.Add("\subsection*{Model Features}") | Out-Null
$lines.Add("\begin{itemize}") | Out-Null
$lines.Add("\item Neighbor-profile cosine similarity from the crosswalk/neighbor stage.") | Out-Null
$lines.Add("\item Positional similarity from initial, medial, and terminal proportions.") | Out-Null
$lines.Add("\item Jensen-Shannon divergence by region, site, type, period, phase, and time metadata.") | Out-Null
$lines.Add("\item Permutation simulations with seed " + $RandomSeed + " and " + $PermutationIterations + " iterations per pair/field.") | Out-Null
$lines.Add("\item Visual priors only for catalog-reviewed Tier 1 pairs; all other pairs remain visual-pending.") | Out-Null
$lines.Add("\end{itemize}") | Out-Null
$lines.Add("\subsection*{Hypothesis Counts}") | Out-Null
$lines.Add("\begin{center}") | Out-Null
$lines.Add("\begin{tabular}{lrrrr}") | Out-Null
$lines.Add("\toprule") | Out-Null
$lines.Add("\textbf{Hypothesis} & \textbf{Pairs} & \textbf{Allograph} & \textbf{Modifier} & \textbf{Functional} \\") | Out-Null
$lines.Add("\midrule") | Out-Null
foreach ($row in $summaryRows) {
    $values = @($row.Hypothesis, $row.PairCount, $row.MeanAllographScore, $row.MeanModifierScore, $row.MeanFunctionalClusterScore) | ForEach-Object { ConvertTo-LatexText ([string]$_) }
    $lines.Add(($values -join " & ") + " \\") | Out-Null
}
$lines.Add("\bottomrule") | Out-Null
$lines.Add("\end{tabular}") | Out-Null
$lines.Add("\end{center}") | Out-Null
$lines.Add("\subsection*{Top Reviewed/High-Priority Rows}") | Out-Null
$lines.Add("\begin{center}") | Out-Null
$lines.Add("\begin{tabular}{lllrrrr}") | Out-Null
$lines.Add("\toprule") | Out-Null
$lines.Add("\textbf{A} & \textbf{B} & \textbf{Hypothesis} & \textbf{Allograph} & \textbf{Regional} & \textbf{Chron.} & \textbf{Modifier} \\") | Out-Null
$lines.Add("\midrule") | Out-Null
foreach ($row in $topRows) {
    $values = @($row.SignA, $row.SignB, $row.TopHypothesis, $row.AllographScore, $row.RegionalAllographyScore, $row.ChronologicalLayeringScore, $row.ModifierScore) | ForEach-Object { ConvertTo-LatexText ([string]$_) }
    $lines.Add(($values -join " & ") + " \\") | Out-Null
}
$lines.Add("\bottomrule") | Out-Null
$lines.Add("\end{tabular}") | Out-Null
$lines.Add("\end{center}") | Out-Null
$lines.Add("\subsection*{Outputs}") | Out-Null
$lines.Add("\begin{itemize}") | Out-Null
foreach ($path in @($featurePath, $scorePath, $summaryPath)) {
    $lines.Add("\item \texttt{" + (ConvertTo-LatexText $path) + "}") | Out-Null
}
$lines.Add("\end{itemize}") | Out-Null
$lines.Add("\end{document}") | Out-Null
$lines | Set-Content -Path $texPath -Encoding UTF8

"Wrote $featurePath"
"Wrote $scorePath"
"Wrote $summaryPath"
"Wrote $texPath"
