param(
    [string]$Path = "data/ivs_corpus_cleaned.csv",
    [int]$TopSigns = 20
)

$rows = Import-Csv -Path $Path

$tokenRows = foreach ($row in $rows) {
    $tokens = [regex]::Matches($row.text, '(?<!\d)\d{3,4}(?!\d)') | ForEach-Object { $_.Value }
    [pscustomobject]@{
        Id = $row.id
        Site = $row.site
        Region = $row.region
        Type = $row.type
        Direction = $row.'dir.'
        Complete = $row.complete
        Length = $tokens.Count
        Tokens = $tokens
    }
}

$allTokens = $tokenRows |
    ForEach-Object { $_.Tokens } |
    Where-Object { $_ -and $_ -notin @("000", "999") }

$summary = [pscustomobject]@{
    Rows = $rows.Count
    CompleteRows = ($rows | Where-Object { $_.complete -eq "Y" }).Count
    UniqueSites = ($rows | Select-Object -ExpandProperty site -Unique).Count
    UniqueTypes = ($rows | Select-Object -ExpandProperty type -Unique).Count
    UniqueAnalyzableSigns = ($allTokens | Select-Object -Unique).Count
    AnalyzableSignTokens = $allTokens.Count
    MeanParsedLength = [math]::Round((($tokenRows | Measure-Object -Property Length -Average).Average), 3)
}

"Corpus profile for $Path"
$summary | Format-List

"Length distribution"
$tokenRows |
    Group-Object Length |
    Sort-Object { [int]$_.Name } |
    Select-Object Name, Count |
    Format-Table -AutoSize

"Direction distribution"
$rows |
    Group-Object 'dir.' |
    Sort-Object Count -Descending |
    Select-Object Name, Count |
    Format-Table -AutoSize

"Top $TopSigns analyzable signs"
$allTokens |
    Group-Object |
    Sort-Object Count -Descending |
    Select-Object -First $TopSigns Name, Count |
    Format-Table -AutoSize
