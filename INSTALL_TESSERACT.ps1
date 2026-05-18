# =============================================================
#  INSTALL_TESSERACT.ps1
#  Run this in PowerShell — installs Tesseract + fixes PATH
#  Right-click PowerShell → "Run as Administrator" → paste:
#  Set-ExecutionPolicy Bypass -Scope Process -Force
#  .\INSTALL_TESSERACT.ps1
# =============================================================

Write-Host ""
Write-Host "=============================================" -ForegroundColor Cyan
Write-Host "  Tesseract Auto-Installer for Windows ARM64" -ForegroundColor Cyan
Write-Host "=============================================" -ForegroundColor Cyan
Write-Host ""

$tess_path = "C:\Program Files\Tesseract-OCR"
$tess_exe  = "$tess_path\tesseract.exe"

# ── STEP 1: Check if already installed ────────────────────────
if (Test-Path $tess_exe) {
    Write-Host "[OK] Tesseract binary found at $tess_exe" -ForegroundColor Green
} else {
    Write-Host "[1/3] Tesseract not found. Downloading installer..." -ForegroundColor Yellow

    $installer_url  = "https://digi.bib.uni-mannheim.de/tesseract/tesseract-ocr-w64-setup-5.5.0.20241111.exe"
    $installer_path = "$env:TEMP\tesseract_setup.exe"

    try {
        # Use BITS transfer — more reliable on Windows ARM
        Start-BitsTransfer -Source $installer_url -Destination $installer_path -ErrorAction Stop
        Write-Host "[OK] Downloaded." -ForegroundColor Green
    } catch {
        Write-Host "[WARN] BITS failed, trying WebClient..." -ForegroundColor Yellow
        try {
            (New-Object System.Net.WebClient).DownloadFile($installer_url, $installer_path)
            Write-Host "[OK] Downloaded via WebClient." -ForegroundColor Green
        } catch {
            Write-Host "[FAIL] Download failed: $_" -ForegroundColor Red
            Write-Host ""
            Write-Host "Manual download link:" -ForegroundColor Yellow
            Write-Host $installer_url -ForegroundColor White
            Write-Host "Save as $installer_path then re-run this script." -ForegroundColor White
            exit 1
        }
    }

    Write-Host "[2/3] Installing silently (no prompts)..." -ForegroundColor Yellow
    $args = "/S /D=C:\Program Files\Tesseract-OCR"
    Start-Process -FilePath $installer_path -ArgumentList $args -Wait -NoNewWindow
    Write-Host "[OK] Installed." -ForegroundColor Green
}

# ── STEP 2: Add to System PATH ────────────────────────────────
Write-Host "[3/3] Updating PATH..." -ForegroundColor Yellow

$sys_path = [System.Environment]::GetEnvironmentVariable("Path", "Machine")
if ($sys_path -notlike "*Tesseract-OCR*") {
    [System.Environment]::SetEnvironmentVariable(
        "Path",
        "$sys_path;$tess_path",
        "Machine"
    )
    Write-Host "[OK] Added $tess_path to System PATH." -ForegroundColor Green
} else {
    Write-Host "[OK] PATH already contains Tesseract-OCR." -ForegroundColor Green
}

# Also update current session PATH so we can test immediately
$env:Path = "$env:Path;$tess_path"

# ── STEP 3: Verify ────────────────────────────────────────────
Write-Host ""
Write-Host "Verifying..." -ForegroundColor Cyan
try {
    $ver = & "$tess_exe" --version 2>&1 | Select-Object -First 1
    Write-Host "[SUCCESS] $ver" -ForegroundColor Green
} catch {
    Write-Host "[FAIL] Could not run tesseract.exe" -ForegroundColor Red
    exit 1
}

# ── STEP 4: Set path in Python file ───────────────────────────
$py_file = Join-Path $PSScriptRoot "ocr_engine.py"
if (Test-Path $py_file) {
    $content = Get-Content $py_file -Raw
    $old = '# pytesseract.pytesseract.tesseract_cmd'
    $new = 'pytesseract.pytesseract.tesseract_cmd'
    if ($content -match [regex]::Escape($old)) {
        $content = $content -replace [regex]::Escape($old), $new
        Set-Content $py_file $content -NoNewline
        Write-Host "[OK] Uncommented tesseract_cmd line in ocr_engine.py" -ForegroundColor Green
    } else {
        Write-Host "[OK] tesseract_cmd already active in ocr_engine.py" -ForegroundColor Green
    }
} else {
    Write-Host "[WARN] ocr_engine.py not found in same folder — set path manually" -ForegroundColor Yellow
}

Write-Host ""
Write-Host "=============================================" -ForegroundColor Cyan
Write-Host "  ALL DONE. Open a NEW PowerShell and run:"  -ForegroundColor Cyan
Write-Host "  tesseract --version"                        -ForegroundColor White
Write-Host "  python pipeline.py --limit 5 --fresh"      -ForegroundColor White
Write-Host "=============================================" -ForegroundColor Cyan
Write-Host ""
