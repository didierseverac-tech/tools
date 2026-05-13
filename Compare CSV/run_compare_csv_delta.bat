@echo off
REM Compare two CSV files with compare_csv_delta.py
REM Version: 3.01 - Single BAT, writes PS1 to temp

set "T=%TEMP%\cmp_csv_delta.ps1"

> "%T%" echo Add-Type -AssemblyName System.Windows.Forms
>> "%T%" echo.
>> "%T%" echo $PYTHON_EXE      = 'c:\PythonProjects\Venv\Python313\Scripts\python.exe'
>> "%T%" echo $COMPARE_SCRIPT  = Join-Path '%~dp0' 'compare_csv_delta.py'
>> "%T%" echo $DEFAULT_OUT_DIR = Join-Path '%~dp0' 'tmp_csv_delta_test'
>> "%T%" echo.
>> "%T%" echo if (-not (Test-Path $PYTHON_EXE)) { Write-Host "[ERROR] Python not found: $PYTHON_EXE" -ForegroundColor Red; Read-Host "Press Enter to exit"; exit 1 }
>> "%T%" echo if (-not (Test-Path $COMPARE_SCRIPT)) { Write-Host "[ERROR] compare_csv_delta.py not found: $COMPARE_SCRIPT" -ForegroundColor Red; Read-Host "Press Enter to exit"; exit 1 }
>> "%T%" echo if (-not (Test-Path $DEFAULT_OUT_DIR)) { New-Item -ItemType Directory -Path $DEFAULT_OUT_DIR ^| Out-Null }
>> "%T%" echo.
>> "%T%" echo function Pick-File([string]$title) {
>> "%T%" echo     $dlg = New-Object System.Windows.Forms.OpenFileDialog
>> "%T%" echo     $dlg.Title  = $title
>> "%T%" echo     $dlg.Filter = "CSV files (*.csv)|*.csv|All files (*.*)|*.*"
>> "%T%" echo     if ($dlg.ShowDialog() -eq "OK") { return $dlg.FileName }
>> "%T%" echo     return ""
>> "%T%" echo }
>> "%T%" echo.
>> "%T%" echo function Save-File([string]$title, [string]$defaultPath) {
>> "%T%" echo     $dlg = New-Object System.Windows.Forms.SaveFileDialog
>> "%T%" echo     $dlg.Title            = $title
>> "%T%" echo     $dlg.Filter           = "CSV files (*.csv)|*.csv|All files (*.*)|*.*"
>> "%T%" echo     $dlg.FileName         = Split-Path $defaultPath -Leaf
>> "%T%" echo     $dlg.InitialDirectory = Split-Path $defaultPath -Parent
>> "%T%" echo     if ($dlg.ShowDialog() -eq "OK") { return $dlg.FileName }
>> "%T%" echo     return $defaultPath
>> "%T%" echo }
>> "%T%" echo.
>> "%T%" echo Write-Host ""
>> "%T%" echo Write-Host "=== CSV Delta Compare ===" -ForegroundColor Cyan
>> "%T%" echo Write-Host ""
>> "%T%" echo.
>> "%T%" echo Write-Host "Select OLD CSV file..." -ForegroundColor Yellow
>> "%T%" echo $OldFile = Pick-File "Select OLD CSV file"
>> "%T%" echo if ($OldFile -eq "") { Write-Host "Cancelled." -ForegroundColor Red; Read-Host "Press Enter to exit"; exit 1 }
>> "%T%" echo Write-Host "  Old : $OldFile"
>> "%T%" echo.
>> "%T%" echo Write-Host "Select NEW CSV file..." -ForegroundColor Yellow
>> "%T%" echo $NewFile = Pick-File "Select NEW CSV file"
>> "%T%" echo if ($NewFile -eq "") { Write-Host "Cancelled." -ForegroundColor Red; Read-Host "Press Enter to exit"; exit 1 }
>> "%T%" echo Write-Host "  New : $NewFile"
>> "%T%" echo.
>> "%T%" echo $stamp      = Get-Date -Format "yyyyMMdd_HHmmss"
>> "%T%" echo $defaultOut = Join-Path $DEFAULT_OUT_DIR "delta_$stamp.csv"
>> "%T%" echo.
>> "%T%" echo Write-Host "Select OUTPUT CSV location..." -ForegroundColor Yellow
>> "%T%" echo $OutFile = Save-File "Save delta output as" $defaultOut
>> "%T%" echo Write-Host "  Out : $OutFile"
>> "%T%" echo.
>> "%T%" echo Write-Host ""
>> "%T%" echo Write-Host "Running compare..." -ForegroundColor Yellow
>> "%T%" echo Write-Host ""
>> "%T%" echo.
>> "%T%" echo ^& $PYTHON_EXE $COMPARE_SCRIPT --old $OldFile --new $NewFile --out $OutFile
>> "%T%" echo $rc = $LASTEXITCODE
>> "%T%" echo.
>> "%T%" echo if ($rc -ne 0) { Write-Host "[FAILED] Code $rc." -ForegroundColor Red; Read-Host "Press Enter to exit"; exit $rc }
>> "%T%" echo.
>> "%T%" echo Write-Host "[OK] Done." -ForegroundColor Green
>> "%T%" echo Write-Host "Main delta file : $OutFile"
>> "%T%" echo Write-Host "  - *_added.csv  *_removed.csv  *_changed.csv"
>> "%T%" echo Invoke-Item (Split-Path $OutFile -Parent)
>> "%T%" echo Read-Host "Press Enter to exit"

powershell -NoProfile -ExecutionPolicy Bypass -File "%T%"
del "%T%" 2>nul
