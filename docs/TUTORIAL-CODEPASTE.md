# TUTORIAL SALIN-TEMPEL — LMBot

**Dibuat oleh Egandika**

Semua langkah di bawah berupa blok kode. **Klik blok → Ctrl+C → tempel di
PowerShell → Enter.** Tidak perlu edit apa pun kecuali 1 tempat di Langkah 4
(nama karakter kamu).

> Cara tempel di jendela PowerShell: **klik kanan** (bukan Ctrl+V) atau Ctrl+V.
> Kalau satu baris terpotong jadi beberapa baris — normal, biarkan saja.

Total waktu ±45 menit (unduh MuMu yang paling lama).

---

## LANGKAH 1 — Buka PowerShell sebagai Administrator

Tekan **Win + X**, lalu pilih **Windows PowerShell (Admin)** / **Terminal (Admin)**.

Kalau tidak muncul, tekan **Win + R**, tempel ini, Enter:

```
powershell
```

Lalu klik kanan ikon PowerShell di taskbar → **Run as administrator**.

**Cek kamu di PowerShell:**

```powershell
$PSVersionTable.PSVersion.Major
```

Kalau keluar angka (5 atau 7) → benar, lanjut.

---

## LANGKAH 2 — Cek virtualisasi (wajib untuk emulator)

Salin-tempel:

```powershell
Get-CimInstance Win32_Processor | Select-Object Name, VirtualizationFirmwareEnabled
```

**Kalau hasilnya `True`** → langsung ke Langkah 3.

**Kalau `False`**, aktifkan dulu di BIOS: restart PC → tekan **Del/F2/F10**
berulang → cari **Intel VT-x** / **AMD-V (SVM)** → **Enabled** → Save (F10).
Setelah Windows hidup lagi, jalankan perintah di atas sekali lagi.

---

## LANGKAH 3 — Unduh MuMu Player

Buka browser, buka **https://www.mumuemulator.com** lalu klik **Download**.

Atau langsung salin-tempel ini di PowerShell (membuka halaman unduhan resmi):

```powershell
Start-Process "https://www.mumuemulator.com/en/download/"
```

Setelah file `.exe` selesai terunduh, **jalankan installer** (klik dua kali dari
folder Downloads). Saat wizard muncul:

- **Install path**: tulis `D:\MuMu` (huruf Inggris, **tanpa spasi**).
  Kalau tidak ada drive D, pakai `C:\MuMu`.
- Klik **Install** → tunggu ±10–20 menit.

Setelah MuMu terbuka, **jangan tutup**. Lanjut setting di Langkah 4.

---

## LANGKAH 4 — Setting MuMu (resolusi + ADB) lewat PowerShell

Tutup MuMu dulu (klik X), lalu salin-tempel seluruh blok ini **sekaligus**:

```powershell
$mumu = "C:\Program Files\Netease\MuMuPlayer-12.0\shell\MuMuManager.exe"
if (-not (Test-Path $mumu)) { $mumu = "D:\MuMu\shell\MuMuManager.exe" }
if (-not (Test-Path $mumu)) { Write-Host "MuMuManager tidak ditemukan - cari manual" -ForegroundColor Red }
else {
  & $mumu control -v 0 launch
  Start-Sleep 10
  & $mumu adb -v 0 -cmd enable -adb_host 127.0.0.1 -adb_port 16384
  Write-Host "MuMu OK, ADB aktif di port 16384" -ForegroundColor Green
}
start "" "$mumu"
```

Lalu **di jendela MuMu** (manual, sekali saja):

1. Klik ikon **⚙ (gir)** kanan atas → **Settings**
2. **Resolution** → `1600 x 720`, **DPI** → `240`
3. Menu **Lainnya / Advanced** → **ADB debugging** → **ON**
4. **Save** → restart instance

---

## LANGKAH 5 — Pasang Lords Mobile di MuMu

Di jendela MuMu: buka **Play Store** → login Google → cari **Lords Mobile** →
**Install** → buka game → login akun bank klan kamu.

---

## LANGKAH 6 — Pasang Python

Salin-tempel (memasang Python 3.11 resmi via winget):

```powershell
winget install -e --id Python.Python.3.11 --accept-source-agreements --accept-package-agreements
```

Kalau `winget` tidak ada, unduh manual:

```powershell
Start-Process "https://www.python.org/downloads/windows/"
```

> Saat installer manual terbuka: **centang** ☑ *Add python.exe to PATH* →
> **Install Now**.

**Tutup PowerShell lalu buka lagi** (wajib, agar PATH terbaca), kemudian cek:

```powershell
python --version
```

Harus keluar `Python 3.11.x`.

---

## LANGKAH 7 — Ambil kode bot

Salin-tempel **blok ini utuh**:

```powershell
cd C:\
if (Test-Path "C:\lord-mobile-bots") { Remove-Item -Recurse -Force "C:\lord-mobile-bots" }
git clone https://github.com/egad13744-collab/lord-mobile-bots.git
cd C:\lord-mobile-bots
dir
```

Kalau `git` tidak dikenali, pakai cara tanpa git:

```powershell
cd C:\
Invoke-WebRequest "https://github.com/egad13744-collab/lord-mobile-bots/archive/refs/heads/main.zip" -OutFile "$env:TEMP\lmbot.zip"
Expand-Archive "$env:TEMP\lmbot.zip" -DestinationPath C:\ -Force
Move-Item "C:\lord-mobile-bots-main" "C:\lord-mobile-bots"
cd C:\lord-mobile-bots
```

Di layar harus terlihat `code.py`, `lmbot`, `config`, `scripts`, `docs`.

---

## LANGKAH 8 — Pasang semua kebutuhan (satu perintah)

```powershell
Set-ExecutionPolicy -Scope Process Bypass -Force
.\scripts\setup-windows.ps1
```

Script ini membuat `.venv`, memasang dependensi, memasang ADB, menyalakan
MuMu, menghubungkan ADB, lalu menjalankan `doctor`.

**Atau, kalau ingin tanpa script (semua manual):**

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -U pip
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
adb connect 127.0.0.1:16384
adb devices
.\.venv\Scripts\python.exe code.py doctor
```

Yang benar: `adb devices` menampilkan `127.0.0.1:16384   device`
(kata **device**, bukan `offline`).

Kalau `adb` tidak dikenali:

```powershell
$dst = "$env:LOCALAPPDATA\Android\platform-tools"
New-Item -ItemType Directory -Force -Path (Split-Path $dst) | Out-Null
Invoke-WebRequest "https://dl.google.com/android/repository/platform-tools-latest-windows.zip" -OutFile "$env:TEMP\pt.zip"
Expand-Archive "$env:TEMP\pt.zip" -DestinationPath (Split-Path $dst) -Force
$env:Path += ";$dst"
adb connect 127.0.0.1:16384
adb devices
```

---

## LANGKAH 9 — Set nama karakter kamu (1 tempat, wajib)

Ganti bagian dalam tanda kutip dengan **nama in-game kamu**. Contoh di tutorial
ini memakai `Arken Ega`:

```powershell
.\.venv\Scripts\python.exe code.py setup --nick "Arken Ega" --port 16384 --width 1600 --height 720
```

Hasil yang benar:

```
✔ config/settings.yaml diperbarui:
   - owner_nick = Arken Ega
   - allowed_senders = [Arken Ega]
   - owners = [Arken Ega] (R6)
   - serial = 127.0.0.1:16384
   - resolusi = 1600x720
✔ config valid. Owner 'Arken Ega' akan mendapat rank R6.
```

Kalau kamu pakai instance MuMu kedua, ganti `--port 16416`.

---

## LANGKAH 10 — Lihat cara kerja & status

```powershell
.\.venv\Scripts\python.exe code.py info
```

---

## LANGKAH 11 — Uji tanpa menyentuh game (aman)

Simulasi penuh 23 perintah:

```powershell
.\.venv\Scripts\python.exe code.py demo
```

Latihan interaktif (aksi hanya dicatat, tidak dieksekusi):

```powershell
.\.venv\Scripts\python.exe code.py --dry-run serve --once "!version" "!bal" "!members" "!help RSS"
```

Jalankan semua test (memastikan tidak ada yang rusak):

```powershell
.\.venv\Scripts\python.exe -m pytest -q
```

---

## LANGKAH 12 — Jalankan bot

```powershell
.\scripts\start-bot.ps1
```

Atau klik dua kali: `C:\lord-mobile-bots\scripts\start-bot.bat`

Kamu akan melihat banner, lalu prompt `lmbot>`. Salin-tempel satu per satu:

```
!version
!help
!members
!shield
!bal
```

Keluar dari bot: ketik `:quit` atau tekan **Ctrl+C**.

Uji satu perintah yang mengubah data (aman, hanya buku besar bot):

```powershell
.\.venv\Scripts\python.exe code.py cmd "!whitelist budi R2"
.\.venv\Scripts\python.exe code.py cmd "!setbal budi food 10m"
.\.venv\Scripts\python.exe code.py cmd "!bal" --sender budi
```

---

## LANGKAH 13 — Cek kesehatan & perbaiki

```powershell
.\.venv\Scripts\python.exe code.py doctor
```

Kalau ada ✘, perbaiki satu per satu:

**`adb: device offline`**

```powershell
adb kill-server
adb connect 127.0.0.1:16384
adb devices
```

**Port beda (instance 1)**

```powershell
$mumu = "C:\Program Files\Netease\MuMuPlayer-12.0\shell\MuMuManager.exe"
& $mumu adb -v 1 -cmd enable -adb_host 127.0.0.1 -adb_port 16416
adb connect 127.0.0.1:16416
.\.venv\Scripts\python.exe code.py setup --nick "Arken Ega" --port 16416
```

**Screenshot kosong / hitam** (sesi RDP terkunci)

```powershell
powercfg /change standby-timeout-ac 0
powercfg /change monitor-timeout-ac 0
query session
tscon 1 /dest:console
```

**Bank sedang dijeda** (karena `!stop`/`!abort`)

```powershell
.\.venv\Scripts\python.exe code.py bank unfreeze
```

---

## LANGKAH 14 — Kalibrasi agar bot bisa mengklik tombol

Ambil screenshot dari emulator:

```powershell
.\.venv\Scripts\python.exe code.py record --out logs\screen.png
```

Buat template dari screenshot itu (contoh: tombol Kirim di posisi 70%,80%
dengan ukuran 12% × 8% layar):

```powershell
.\.venv\Scripts\python.exe code.py template add --screen logs\screen.png --name send_button --box 0.70,0.80,0.12,0.08
```

Cek template mana yang masih kurang:

```powershell
.\.venv\Scripts\python.exe code.py template list
```

Buktikan template ketemu di layar nyata:

```powershell
.\.venv\Scripts\python.exe code.py verify --adb
```

Lalu aktifkan flow: buka file berikut, tempel angka `tap: [...]` dari output
`template add`, dan ubah `enabled: false` menjadi `enabled: true`:

```powershell
notepad config\flows\bank_open_member.yaml
notepad config\flows\bank_send_one_type.yaml
```

Panduan lengkap: `docs\CALIBRATION.md`.

---

## LANGKAH 15 — Jalankan 24 jam

Matikan sleep layar:

```powershell
powercfg /change standby-timeout-ac 0
powercfg /change monitor-timeout-ac 0
powercfg /change hibernate-timeout-ac 0
```

Autostart bot setelah reboot:

```powershell
$action  = New-ScheduledTaskAction -Execute "powershell.exe" -Argument "-WindowStyle Hidden -ExecutionPolicy Bypass -File C:\lord-mobile-bots\scripts\start-bot.ps1 -Mode http -Port 8080"
$trigger = New-ScheduledTaskTrigger -AtStartup
Register-ScheduledTask -TaskName "LMBot" -Action $action -Trigger $trigger -RunLevel Highest
```

Dashboard dari HP (buka `http://IP-MESIN:8081/`):

```powershell
.\scripts\start-bot.ps1 -Mode http -Port 8080 -Token rahasia123
```

Kirim perintah lewat webhook (dari PowerShell mana pun / HP):

```powershell
Invoke-RestMethod -Uri "http://127.0.0.1:8080/" -Method Post -ContentType "application/json" -Body '{"text":"!bal","sender":"Arken Ega"}'
```

---

## PERINTAH HARIAN — copy tempel ke PowerShell

```powershell
cd C:\lord-mobile-bots
```

```powershell
# lihat saldo semua member
.\.venv\Scripts\python.exe code.py bank list --key food
```

```powershell
# isi saldo member
.\.venv\Scripts\python.exe code.py bank add budi --amount 10m 0 0 0 0
```

```powershell
# jadikan member jadi R3
.\.venv\Scripts\python.exe code.py bank whitelist budi --rank R3
```

```powershell
# jalankan bot interaktif
.\scripts\start-bot.ps1
```

```powershell
# bot mode webhook + dashboard
.\scripts\start-bot.ps1 -Mode http -Port 8080 -Token rahasia123
```

```powershell
# perintah sekali jalan
.\.venv\Scripts\python.exe code.py cmd "!shield" --sender "Arken Ega"
```

---

## JEBAKAN UMUM (biar tidak gagal)

| Gejala | Solusi cepat |
|---|---|
| `python is not recognized` | tutup & buka ulang PowerShell, atau install ulang Python + centang *Add to PATH* |
| `running scripts is disabled` | `Set-ExecutionPolicy -Scope Process Bypass -Force` |
| `adb` tidak dikenali | jalankan blok platform-tools di Langkah 8 |
| `gagal terhubung ke 127.0.0.1:16384` | MuMu belum jalan / ADB debugging OFF / port beda |
| `screenshot kosong` | jendela MuMu minimized atau sesi RDP terkunci → `tscon` |
| `flow ... dinonaktifkan` | belum dikalibrasi → Langkah 14 |
| `saldo ... hanya 0` | belum ada RSS tercatat → `bank add` atau `!setbal` |
| `belum terdaftar di whitelist` | jalankan ulang Langkah 9 dengan nama yang benar |

Log ada di `logs\bot.log` · audit transaksi `state\transactions.jsonl` ·
peringatan `logs\alerts.jsonl`.

---

**LMBot v1.1.0 — Dibuat oleh Egandika**
