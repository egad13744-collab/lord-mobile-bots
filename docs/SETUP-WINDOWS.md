# Setup di Windows (akses via RDP) + MuMu Player

Target: satu mesin Windows yang kamu akses lewat RDP, menjalankan
**MuMu Player 12** dengan Lord Mobile, dan **LMBot** di terminal.

> Catatan RDP: saat sesi RDP di-disconnect (bukan logoff), Windows mengunci
> desktop dan MuMu bisa berhenti render — `screencap` jadi hitam. Supaya bot
> tetap jalan 24 jam, lihat bagian **Menjaga sesi tetap aktif** di bawah.

---

## 1. Prasyarat

| Komponen | Versi/disarankan |
|---|---|
| Windows | 10/11, 64-bit, VT-x/AMD-V aktif di BIOS |
| MuMu Player | 12.x (instance Android 9 atau 12) |
| Python | 3.9+ (centang *Add python.exe to PATH*) |
| ADB | platform-tools (script mengunduh otomatis) |
| Resource | 4 core, 8 GB RAM, GPU mode DirectX |

Resolusi instance MuMu yang disarankan: **1280×720 (landscape, DPI 240)** —
paling ringan untuk screenshot berulang. Boleh beda; semua koordinat di repo
memakai fraksi (0..1) sehingga tetap proporsional.

---

## 2. Aktifkan ADB di MuMu

1. Buka **MuMu Player 12** → ⚙ **Pengaturan** → **Lainnya**.
2. Aktifkan **ADB debugging** (atau *Root permission* tidak diperlukan).
3. Catat **ADB port** — default instance 0: **16384**, instance 1: **16416**, dst.
4. Simpan, lalu restart instance.

Cek dari PowerShell:

```powershell
adb connect 127.0.0.1:16384
adb devices
# expected: 127.0.0.1:16384   device
```

Bila `adb` belum ada, script setup akan mengunduh platform-tools ke
`%LOCALAPPDATA%\Android\platform-tools`.

Bisa juga lewat MuMuManager (dipakai script):

```powershell
& "C:\Program Files\Netease\MuMuPlayer-12.0\shell\MuMuManager.exe" `
    adb -v 0 -cmd enable -adb_host 127.0.0.1 -adb_port 16384
```

---

## 3. Pasang bot

```powershell
cd C:\path\ke\lord-mobile-bots
Set-ExecutionPolicy -Scope Process Bypass -Force
.\scripts\setup-windows.ps1
```

Script melakukan: cek Python → buat `.venv` → `pip install -r requirements.txt`
→ pastikan `adb` → nyalakan instance MuMu + aktifkan ADB → `adb connect` →
jalankan `python code.py doctor`.

Contoh keluaran `doctor` yang sehat:

```
 ✔ adb ditemukan       C:\platform-tools\adb.exe
 ✔ resolusi            1280x720
 ✔ serial              127.0.0.1:16384
 ✔ koneksi device      terhubung
 ✔ screenshot          184223 byte
 ✔ flow YAML           43: abort, addtitle, ... 
 ✔ template PNG        0 file
 ✔ OpenCV              aktif
Semua siap.
```

(`template PNG` boleh 0 — template hanya dipakai untuk `assert` opsional.)

---

## 4. Konfigurasi

Edit `config/settings.yaml`:

```yaml
device:
  adb_path: C:\platform-tools\adb.exe   # atau biarkan "adb" bila sudah di PATH
  serial: 127.0.0.1:16384               # sesuaikan instance
  width: 1280
  height: 720

bot:
  owner_nick: lady_ayu
  allowed_senders: [lady_ayu]           # whitelist awal R5
  reply_confirm: true                   # bot membalas ke chat game
```

Nick pada `allowed_senders` otomatis masuk whitelist **R5** saat state pertama
kali dibuat. Owner **R6** (tidak bisa diturunkan lewat chat) ditambahkan dengan:

```powershell
python code.py bank whitelist lady_ayu --rank R5
# atau edit state/bank.json -> roster.owners
```

---

## 5. Jalankan

```powershell
.\scripts\start-bot.ps1                 # interaktif
.\scripts\start-bot.bat                 # klik dua kali di RDP
.\scripts\start-bot.ps1 -Mode http -Port 8080 -Token rahasia123
```

Mode sumber perintah:

| Mode | Cara pakai | Butuh OCR? |
|---|---|---|
| `terminal` | ketik `!bal` di prompt `lmbot>` | tidak |
| `file` | tambahkan baris `lady_ayu|!food 1m` ke `state/commands.txt` | tidak |
| `http` | `POST http://<ip-rdp>:8080/` body `{"text":"!bal","sender":"lady_ayu"}` + header `X-Bot-Token` | tidak |
| `chat` | bot membaca chat game sendiri | **ya** (docs/OCR.md) |

Contoh webhook dari HP (satu LAN dengan mesin RDP):

```bash
curl -X POST http://192.168.1.10:8080/ -H "Content-Type: application/json" \
     -H "X-Bot-Token: rahasia123" -d '{"text":"!food 10m","sender":"lady_ayu"}'
```

---

## 5b. Dashboard & monitoring dari HP

```powershell
.\scripts\start-bot.ps1 -Mode http -Port 8080
# lalu buka http://<ip-mesin-rdp>:8081/
```

Atau langsung lewat CLI: `python code.py serve --web-port 8081 --token rahasia`.

Isi dashboard: total tabungan, top penabung, 15 transaksi terakhir, status
14 template UI, dan peringatan terakhir. Endpoint JSON: `/api/status`.
Kirim perintah lewat dashboard juga bisa (`POST /`).

Set token bila mesin berada di jaringan bersama (`web.token` atau `--token`).

Peringatan juga bisa dikirim ke Discord/Slack:

```yaml
alerts:
  webhook_url: 'https://discord.com/api/webhooks/xxxx/yyyy'
  min_level: warn
```

---

## 6. Menjaga sesi tetap aktif (penting untuk RDP)

Windows memutus render saat RDP disconnect. Pilih salah satu:

**A. Biarkan sesi RDP tetap login** — jangan klik *Disconnect*, tapi putus
kabel jaringan/koneksi. Bila perlu akses ulang, matikan setting
*"Disconnect session when RDP window is closed"* di klien RDP.

**B. Karena MuMu butuh GPU, jalankan juga lewat konsol fisik** — gunakan
`tscon` untuk mengembalikan sesi ke konsol:

```powershell
# dari sesi RDP (Administrator)
query session
tscon 1 /dest:console        # 1 = ID sesi RDP, console = sesi fisik
```

**C. Matikan kunci layar & sleep**:

```powershell
powercfg /change standby-timeout-ac 0
powercfg /change monitor-timeout-ac 0
powercfg /change hibernate-timeout-ac 0
```

**D. Autostart setelah reboot** — buat scheduled task:

```powershell
$action  = New-ScheduledTaskAction -Execute "powershell.exe" `
           -Argument "-WindowStyle Hidden -ExecutionPolicy Bypass -File C:\path\lord-mobile-bots\scripts\start-bot.ps1 -Mode http -Port 8080"
$trigger = New-ScheduledTaskTrigger -AtStartup
Register-ScheduledTask -TaskName "LMBot" -Action $action -Trigger $trigger -RunLevel Highest
```

Cek juga `device.screenshot_timeout` (naikkan ke 30) bila PC lambat.

---

## 7. Troubleshooting

| Gejala | Penyebab & solusi |
|---|---|
| `adb: device offline` | Restart ADB: `adb kill-server; adb connect 127.0.0.1:16384` |
| `gagal terhubung ke 127.0.0.1:16384` | ADB debugging di MuMu belum aktif, atau port beda (instance 1 = 16416) |
| `screenshot kosong` | Jendela MuMu minimized / sesi RDP terkunci → lihat bagian 6 |
| `flow '...' gagal` / `belum ada di config/flows` | Flow belum dikalibrasi → docs/CALIBRATION.md |
| `perintah tidak dikenal` | Cek ejaan; `python code.py serve` lalu `:help` untuk daftar lengkap |
| `kamu ada di blacklist` | Hapus: `python code.py bank blacklist`/edit `state/bank.json` |
| `bank sedang dijeda` | Ada `!stop`/`!abort` aktif: `python code.py bank unfreeze` |
| Bot lambat | Turunkan resolusi MuMu ke 1280×720, naikkan `bot.poll_interval` |
| Saldo di bot beda dengan game | Bot memakai buku besar sendiri; bandingkan dengan `!sync`/`!adminbag`, koreksi lewat `bank add` atau `!setbal` |
| `flow ... percobaan 1 gagal` di log | Bot otomatis retry; bila berulang, koordinat/template perlu diperbaiki (docs/ASSETS.md) |
| `tidak di layar bank/peta klan` | Bot berada di layar lain; buka peta klan / panel bank, atau sesuaikan template |

Log lengkap: `logs/bot.log` dan audit transaksi `state/transactions.jsonl`.
