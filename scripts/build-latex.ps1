param(
    [string]$DocsDir = "docs",
    [string]$OutputPdf = "outputs/ivs_research_report.pdf",
    [string]$PdfLatexPath = "",
    [string]$BibTexPath = ""
)

function Find-Executable([string]$Name, [string[]]$ExtraCandidates) {
    $command = Get-Command $Name -ErrorAction SilentlyContinue
    if ($null -ne $command -and (Test-Path -LiteralPath $command.Source)) {
        return $command.Source
    }

    foreach ($candidate in $ExtraCandidates) {
        if (Test-Path -LiteralPath $candidate) {
            return $candidate
        }
    }

    return ""
}

$miktexBinCandidates = @(
    "$env:LOCALAPPDATA\Programs\MiKTeX\miktex\bin\x64",
    "$env:APPDATA\MiKTeX\miktex\bin\x64",
    "C:\Program Files\MiKTeX\miktex\bin\x64",
    "C:\Program Files (x86)\MiKTeX\miktex\bin"
)

if ($PdfLatexPath.Trim() -eq "") {
    $PdfLatexPath = Find-Executable "pdflatex" ($miktexBinCandidates | ForEach-Object { Join-Path $_ "pdflatex.exe" })
}
if ($BibTexPath.Trim() -eq "") {
    $BibTexPath = Find-Executable "bibtex" ($miktexBinCandidates | ForEach-Object { Join-Path $_ "bibtex.exe" })
}

if ($PdfLatexPath.Trim() -eq "" -or -not (Test-Path -LiteralPath $PdfLatexPath)) {
    throw "Could not locate pdflatex.exe. Pass -PdfLatexPath explicitly."
}
if ($BibTexPath.Trim() -eq "" -or -not (Test-Path -LiteralPath $BibTexPath)) {
    throw "Could not locate bibtex.exe. Pass -BibTexPath explicitly."
}

$root = (Get-Location).Path
$docsPath = Resolve-Path -LiteralPath $DocsDir
$outputPath = Join-Path $root $OutputPdf
$outputDir = Split-Path -Parent $outputPath
if (-not (Test-Path -LiteralPath $outputDir)) {
    New-Item -ItemType Directory -Force -Path $outputDir | Out-Null
}

Push-Location $docsPath
try {
    & $PdfLatexPath -interaction=nonstopmode -halt-on-error -file-line-error main.tex
    if ($LASTEXITCODE -ne 0) { throw "pdflatex pass 1 failed." }

    & $BibTexPath main
    if ($LASTEXITCODE -ne 0) { throw "bibtex failed." }

    & $PdfLatexPath -interaction=nonstopmode -halt-on-error -file-line-error main.tex
    if ($LASTEXITCODE -ne 0) { throw "pdflatex pass 2 failed." }

    & $PdfLatexPath -interaction=nonstopmode -halt-on-error -file-line-error main.tex
    if ($LASTEXITCODE -ne 0) { throw "pdflatex pass 3 failed." }

    & $PdfLatexPath -interaction=nonstopmode -halt-on-error -file-line-error main.tex
    if ($LASTEXITCODE -ne 0) { throw "pdflatex pass 4 failed." }

    Copy-Item -LiteralPath "main.pdf" -Destination $outputPath -Force
}
finally {
    $cleanupExtensions = @(
        "aux", "bbl", "blg", "fdb_latexmk", "fls", "log", "out", "synctex.gz", "toc"
    )
    foreach ($extension in $cleanupExtensions) {
        Remove-Item -LiteralPath ("main." + $extension) -Force -ErrorAction SilentlyContinue
    }
    Remove-Item -LiteralPath "main.pdf" -Force -ErrorAction SilentlyContinue
    Pop-Location
}

"Wrote $outputPath"
