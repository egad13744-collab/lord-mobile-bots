<#
  start-bot.ps1 — start bot di terminal RDP.
    .\scripts\start-bot.ps1                 # mode interaktif
    .\scripts\start-bot.ps1 -Mode file      # baca perintah dari state/commands.txt
    .\scripts\start-bot.ps1 -Mode http -Port 8080   # webhook (bisa diakses HP di LAN)
    .\scripts\start-bot.ps1 -DryRun         # simulasi, emulator tidak disentuh
#>
param(
    [ValidateSet("terminal", "file", "http", "chat")] [string]$Mode = "terminal",
    [int]$Port = 8080,
    [string]$Token = $env:LMBOT_TOKEN,
    [switch]$DryRun,
    [string]$Config = ""
)
$ErrorActionPreference = "Stop"
$py = ".\.venv\Scripts\python.exe"
if (-not (Test-Path $py)) { throw "venv belum ada. Jalankan .\scripts\setup-windows.ps1 dulu." }

$argsList = @("code.py", "serve", "--source", $Mode)
if ($Config) { $argsList += @("--config", $Config) }
if ($DryRun) { $argsList += "--dry-run" }
if ($Mode -eq "http") { $argsList += @("--http-port", "$Port"); if ($Token) { $argsList += @("--token", $Token) } }

Write-Host "[lmbot] Dibuat oleh Egandika" -ForegroundColor DarkGray
Write-Host "[lmbot] $py $($argsList -join ' ')" -ForegroundColor DarkGray
& $py @argsList
