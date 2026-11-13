<#
  setup-windows.ps1 — persiapan sekali jalan di mesin RDP Windows.
  Jalankan di PowerShell (Run as Administrator):
      Set-ExecutionPolicy -Scope Process Bypass -Force
      .\scripts\setup-windows.ps1
#>
param(
    [string]$Python = "py",
    [string]$MuMuManager = "C:\Program Files\Netease\MuMuPlayer-12.0\shell\MuMuManager.exe",
    [int]$Instance = 0,
    [int]$AdbPort = 16384
)

$ErrorActionPreference = "Stop"
function Info($m) { Write-Host "[lmbot] $m" -ForegroundColor Cyan }
function Warn($m) { Write-Host "[lmbot] $m" -ForegroundColor Yellow }

Write-Host @"
  _     __  __ ____        _
 | |   |  \/  |  _ \      | |__
 | |   | |\/| | |_) | ___ | '_ \
 | |___| |  | |  _ < / _ \| |_) |
 |_____|_|  |_|_| \_\___/ |_.__/
  Setup lingkungan bot (MuMu + ADB)
"@ -ForegroundColor Green
Write-Host "  Dibuat oleh Egandika" -ForegroundColor DarkGray

# 1. Python ---------------------------------------------------------------
Info "cek Python..."
try {
    $ver = & $Python -c "import sys;print('.'.join(map(str,sys.version_info[:3])))" 2>$null
} catch { throw "Python tidak ditemukan. Install dari python.org (centang 'Add to PATH')." }
if ([version]$ver -lt [version]"3.9") { throw "Butuh Python >= 3.9, sekarang $ver" }
Info "Python $ver OK"

# 2. venv + dependensi ----------------------------------------------------
if (-not (Test-Path ".venv")) { Info "membuat venv..."; & $Python -m venv .venv }
$py = ".\.venv\Scripts\python.exe"
Info "install dependensi..."
& $py -m pip install --upgrade pip --quiet
& $py -m pip install -r requirements.txt --quiet
Info "dependensi terpasang"

# 3. ADB ------------------------------------------------------------------
$adb = Get-Command adb -ErrorAction SilentlyContinue
if (-not $adb) {
    Warn "adb tidak ada di PATH. Mengunduh platform-tools (butuh internet)..."
    $zip = "$env:TEMP\platform-tools.zip"
    $dst = "$env:LOCALAPPDATA\Android\platform-tools"
    New-Item -ItemType Directory -Force -Path (Split-Path $dst) | Out-Null
    Invoke-WebRequest -Uri "https://dl.google.com/android/repository/platform-tools-latest-windows.zip" -OutFile $zip
    Expand-Archive -Path $zip -DestinationPath (Split-Path $dst) -Force
    [Environment]::SetEnvironmentVariable("Path", $env:Path + ";" + $dst, "Process")
    $env:Path += ";" + $dst
    Info "platform-tools dipasang di $dst (Path permanen: tambahkan manual bila perlu)"
} else { Info "adb ditemukan: $($adb.Source)" }

# 4. MuMu ADB -------------------------------------------------------------
if (-not (Test-Path $MuMuManager)) {
    Warn "MuMuManager tidak ditemukan di $MuMuManager"
    Warn "Cari manual: 'C:\Program Files\Netease\MuMuPlayer-12.0\shell\MuMuManager.exe'"
    Warn "lalu set device.mumu_manager di config/settings.yaml"
} else {
    Info "menyalakan instance $Instance ..."
    & $MuMuManager control -v $Instance launch | Out-Null
    Start-Sleep -Seconds 8
    Info "aktifkan ADB instance $Instance di port $AdbPort ..."
    & $MuMuManager adb -v $Instance -cmd enable -adb_host 127.0.0.1 -adb_port $AdbPort | Out-Null
    Start-Sleep -Seconds 2
}

adb connect "127.0.0.1:$AdbPort"
$devices = adb devices
Info "perangkat terdeteksi:`n$devices"
if ($devices -notmatch "127.0.0.1:$AdbPort\s+device") {
    Warn "device belum 'device'. Buka MuMu > Pengaturan > Lainnya > aktifkan ADB debugging,"
    Warn "atau jalankan: `"$MuMuManager`" adb -v $Instance -cmd enable -adb_host 127.0.0.1 -adb_port $AdbPort"
}

# 5. Cek kesiapan ---------------------------------------------------------
Info "menjalankan doctor..."
& $py code.py doctor

Write-Host ""
Info "Selesai. Jalankan bot dengan:  .\scripts\start-bot.ps1"
Info "Uji tanpa emulator:            $py code.py --dry-run cmd '!bal'"
