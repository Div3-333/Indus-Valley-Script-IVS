param(
    [string]$Path = "data/ivs_corpus_cleaned.csv",
    [string]$OutDir = "outputs",
    [int]$MinCount = 20,
    [switch]$IncludeAmbiguousRows,
    [switch]$NoDirectionNormalization
)

if (-not (Test-Path $OutDir)) {
    New-Item -ItemType Directory -Force -Path $OutDir | Out-Null
}

$rows = Import-Csv -Path $Path
$records = New-Object System.Collections.Generic.List[object]

foreach ($row in $rows) {
    $dir = [string]$row.'dir.'
    $dir = $dir.Trim()
    $tokens = @([regex]::Matches($row.text, '\d{3}') | ForEach-Object { $_.Value })

    if (-not $IncludeAmbiguousRows) {
        if ($row.complete -ne "Y") { continue }
        if ($dir -notin @("R/L", "L/R")) { continue }
        if ($tokens -contains "000") { continue }
    }

    if ($tokens.Count -eq 0) { continue }

    # Default assumption: the CSV text field is physical order. For R/L
    # inscriptions, reverse tokens to approximate reading order.
    if ((-not $NoDirectionNormalization) -and $dir -eq "R/L") {
        [array]::Reverse($tokens)
    }

    $records.Add([pscustomobject]@{
        Id = $row.id
        Site = $row.site
        Region = $row.region
        Type = $row.type
        Direction = $dir
        Length = $tokens.Count
        Tokens = $tokens
    }) | Out-Null
}

$stats = @{}
$lengthRows = New-Object System.Collections.Generic.List[object]

foreach ($record in $records) {
    $tokens = @($record.Tokens)
    $n = $tokens.Count

    $lengthRows.Add([pscustomobject]@{
        Length = $n
        Count = 1
    }) | Out-Null

    for ($i = 0; $i -lt $n; $i++) {
        $sign = $tokens[$i]
        if ($sign -eq "000") { continue }

        if (-not $stats.ContainsKey($sign)) {
            $stats[$sign] = [pscustomobject]@{
                Sign = $sign
                Total = 0
                Start = 0
                End = 0
                Medial = 0
                Singleton = 0
                NormPosSum = 0.0
            }
        }

        $item = $stats[$sign]
        $item.Total += 1

        if ($n -eq 1) {
            $item.Singleton += 1
            $item.NormPosSum += 0.5
        }
        else {
            $item.NormPosSum += ($i / ($n - 1))

            if ($i -eq 0) {
                $item.Start += 1
            }
            elseif ($i -eq ($n - 1)) {
                $item.End += 1
            }
            else {
                $item.Medial += 1
            }
        }
    }
}

$signStats = foreach ($item in $stats.Values) {
    $total = [double]$item.Total
    [pscustomobject]@{
        Sign = $item.Sign
        Total = $item.Total
        Start = $item.Start
        End = $item.End
        Medial = $item.Medial
        Singleton = $item.Singleton
        StartPct = [math]::Round($item.Start / $total, 4)
        EndPct = [math]::Round($item.End / $total, 4)
        MedialPct = [math]::Round($item.Medial / $total, 4)
        SingletonPct = [math]::Round($item.Singleton / $total, 4)
        MeanNormPosition = [math]::Round($item.NormPosSum / $total, 4)
        EndMinusStart = [math]::Round(($item.End - $item.Start) / $total, 4)
    }
}

$prefix = if ($NoDirectionNormalization) { "physical_order_" } else { "" }
$statsPath = Join-Path $OutDir ($prefix + "positional_sign_stats.csv")
$lengthPath = Join-Path $OutDir ($prefix + "tier_a_length_distribution.csv")
$summaryPath = Join-Path $OutDir ($prefix + "positional_analysis.md")

$signStats |
    Sort-Object -Property @{Expression="Total"; Descending=$true}, @{Expression="Sign"; Descending=$false} |
    Export-Csv -NoTypeInformation -Path $statsPath

$lengthSummary = $records |
    Group-Object Length |
    Sort-Object { [int]$_.Name } |
    Select-Object @{Name="Length"; Expression={$_.Name}}, Count

$lengthSummary |
    Export-Csv -NoTypeInformation -Path $lengthPath

$topStarts = $signStats |
    Where-Object { $_.Total -ge $MinCount } |
    Sort-Object -Property @{Expression="StartPct"; Descending=$true}, @{Expression="Total"; Descending=$true} |
    Select-Object -First 15

$topEnds = $signStats |
    Where-Object { $_.Total -ge $MinCount } |
    Sort-Object -Property @{Expression="EndPct"; Descending=$true}, @{Expression="Total"; Descending=$true} |
    Select-Object -First 15

$topMedials = $signStats |
    Where-Object { $_.Total -ge $MinCount } |
    Sort-Object -Property @{Expression="MedialPct"; Descending=$true}, @{Expression="Total"; Descending=$true} |
    Select-Object -First 15

function Format-MarkdownTable($rowsToFormat, $columns) {
    $lines = New-Object System.Collections.Generic.List[string]
    $lines.Add("| " + ($columns -join " | ") + " |") | Out-Null
    $lines.Add("| " + (($columns | ForEach-Object { "---" }) -join " | ") + " |") | Out-Null

    foreach ($row in $rowsToFormat) {
        $values = foreach ($column in $columns) { [string]$row.$column }
        $lines.Add("| " + ($values -join " | ") + " |") | Out-Null
    }

    return $lines
}

$summary = New-Object System.Collections.Generic.List[string]
$summary.Add("# Positional Analysis") | Out-Null
$summary.Add("") | Out-Null
$summary.Add('Generated from `' + $Path + '`.') | Out-Null
$summary.Add("") | Out-Null
$summary.Add('Filtering: complete rows, directions `R/L` or `L/R`, and no `000` ambiguous sign tokens unless `-IncludeAmbiguousRows` is supplied.') | Out-Null
$summary.Add("") | Out-Null
if ($NoDirectionNormalization) {
    $summary.Add('Direction mode: physical-order mode. Token order is analyzed exactly as it appears in the CSV.') | Out-Null
}
else {
    $summary.Add('Direction mode: reading-order mode. The CSV text field is assumed to be physical order; `R/L` rows are reversed for this pass.') | Out-Null
}
$summary.Add("") | Out-Null
$summary.Add("Rows analyzed: $($records.Count)") | Out-Null
$summary.Add("Unique non-zero signs analyzed: $($signStats.Count)") | Out-Null
$summary.Add("") | Out-Null
$summary.Add("## Strong Start Candidates") | Out-Null
$summary.Add("") | Out-Null
Format-MarkdownTable $topStarts @("Sign", "Total", "Start", "StartPct", "MeanNormPosition") | ForEach-Object { $summary.Add($_) | Out-Null }
$summary.Add("") | Out-Null
$summary.Add("## Strong End Candidates") | Out-Null
$summary.Add("") | Out-Null
Format-MarkdownTable $topEnds @("Sign", "Total", "End", "EndPct", "MeanNormPosition") | ForEach-Object { $summary.Add($_) | Out-Null }
$summary.Add("") | Out-Null
$summary.Add("## Strong Medial Candidates") | Out-Null
$summary.Add("") | Out-Null
Format-MarkdownTable $topMedials @("Sign", "Total", "Medial", "MedialPct", "MeanNormPosition") | ForEach-Object { $summary.Add($_) | Out-Null }
$summary.Add("") | Out-Null
$summary.Add("## Output Files") | Out-Null
$summary.Add("") | Out-Null
$summary.Add("- ``$statsPath``") | Out-Null
$summary.Add("- ``$lengthPath``") | Out-Null

$summary | Set-Content -Path $summaryPath -Encoding UTF8

"Wrote $summaryPath"
"Wrote $statsPath"
"Wrote $lengthPath"
