param(
    [switch]$fresh,
    [switch]$resume,
    [switch]$retryFailed,
    [int]$limit = 0
)

$env:PYTHONIOENCODING = "utf-8"
$python = "D:\IFB\Project\IT\zoho-image-pipeline\.venv\Scripts\python.exe"
Set-Location "D:\IFB\Project\IT\zoho-image-pipeline"

if (-not $fresh -and -not $resume) {
    Write-Host ""
    Write-Host "  Usage:" -ForegroundColor Cyan
    Write-Host ""
    Write-Host "    .\run.ps1 -fresh              Clear DB, process ALL rows from row 1"
    Write-Host "    .\run.ps1 -fresh  -limit 100  Clear DB, process first 100 rows only"
    Write-Host "    .\run.ps1 -resume             Continue all remaining rows"
    Write-Host "    .\run.ps1 -resume -limit 100  Continue next 100 rows only"
    Write-Host "    .\run.ps1 -resume -retryFailed  Also re-attempt rows that previously got NO_ORDER_ID/NO_STAR"
    Write-Host ""
    exit
}

if ($fresh) {
    Write-Host ""
    Write-Host "  Clearing database..." -ForegroundColor Yellow
    & $python -c "import sqlite3; c=sqlite3.connect('data/zoho_pipeline.db'); c.execute('DELETE FROM zoho_records'); c.execute('DELETE FROM sqlite_sequence WHERE name='+chr(39)+'zoho_records'+chr(39)); c.commit(); c.close(); print('  Done. DB is empty.')"
    Write-Host ""
}

$args_list = @()
if ($limit -gt 0) {
    $args_list += "--limit"
    $args_list += "$limit"
    Write-Host "  Processing $limit rows..." -ForegroundColor Green
} else {
    Write-Host "  Processing all rows..." -ForegroundColor Green
}
if ($retryFailed) {
    $args_list += "--retry-failed"
    Write-Host "  Also retrying previously-failed rows (NO_ORDER_ID/NO_STAR)..." -ForegroundColor Yellow
}

Write-Host "  Dashboard: http://localhost:8501" -ForegroundColor Cyan
Write-Host ""

& $python pipeline.py @args_list
