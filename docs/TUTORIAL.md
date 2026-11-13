# TUTORIAL LENGKAP — dari nol sampai bot jalan

Panduan ini ditulis untuk kamu yang **belum pernah** menyentuh terminal, ADB,
atau emulator. Ikuti berurutan, jangan lompat. Total waktu ±45–60 menit
(termasuk unduh MuMu yang besar).

> **LMBot — Dibuat oleh Egandika**
> Bot ini bekerja seperti tangan manusia: melihat layar emulator, lalu
> menyentuh tombolnya. Tidak memodifikasi game.

---

## Ringkasan cepat (kalau kamu sudah punya MuMu + Python)

```powershell
cd C:\lord-mobile-bots
.\scripts\setup-windows.ps1          # pasang semua otomatis
.\scripts\start-bot.ps1              # jalankan bot
```

Sisanya (kalau belum ada apa-apa) ikuti bagian 1–9 di bawah.

---

# BAGIAN 1 — Nyalakan komputer & buka terminal

## 1.1 Masuk ke Windows (RDP)

Kalau mesinnya diakses jarak jauh:

1. Tekan **Win + R**, ketik `mstsc`, Enter → muncul **Remote Desktop Connection**.
2. **Computer**: `IP:PORT` mesin (contoh `192.168.1.10:3389`).
3. **Username** & password dari penyedia RDP/VPS.
4. Klik **Connect** → muncul desktop Windows.

> Catatan penting: **jangan klik "Disconnect"** saat selesai. Itu mengunci
> desktop dan emulator berhenti render (screenshot jadi hitam). Cara keluar
> yang benar ada di bagian 10.

## 1.2 Buka Terminal

Ada dua jenis terminal di Windows. Kita pakai **PowerShell** (lebih lengkap).

**Cara A — paling cepat:** tekan **Win + R** → ketik `powershell` → Enter.

**Cara B:** klik Start → ketik `powershell` → klik kanan
**Windows PowerShell** → **Run as administrator**
(diperlukan untuk beberapa langkah, mis. memasang ADB ke PATH).

Setelah terbuka, kamu lihat prompt seperti:

```
PS C:\Users\NamaKamu>
```

Itu artinya terminal siap menerima perintah. **Jangan tutup jendela ini.**

## 1.3 Cek apakah komputer mendukung emulator (VT)

Emulator Android butuh virtualisasi. Cek dengan:

```powershell
Get-CimInstance Win32_Processor | Select-Object Name, VirtualizationFirmwareEnabled
```

- `VirtualizationFirmwareEnabled : True` → **aman, lanjut.**
- `False` → harus diaktifkan di BIOS:

  1. Restart PC, tekan **Del / F2 / F10** berulang saat logo muncul (tergantung merek).
  2. Cari menu **Advanced** atau **CPU Configuration**.
  3. Aktifkan **Intel VT-x** / **Intel Virtualization Technology** atau
     **AMD-V / SVM Mode**.
  4. **Save & Exit** (biasanya F10).

Cek juga lewat Task Manager: **Ctrl+Shift+Esc** → tab **Performance** →
**CPU** → baris **Virtualization** harus *Enabled*.

**Alternatif tanpa BIOS:** Windows 11 Pro punya
`Windows Features → Hyper-V`, tapi MuMu lebih stabil dengan VT langsung di BIOS.

---

# BAGIAN 2 — Unduh & pasang MuMu Player

## 2.1 Unduh installer resmi

1. Buka browser, kunjungi situs resmi NetEase:
   **https://www.mumuemulator.com** (versi internasional)
   atau **https://mumu.163.com** (versi Tiongkok).
2. Klik **Download** / **Unduh** untuk **Windows**.
3. Ukuran installer ±4–5 GB karena langsung membawa image Android.

> ⚠️ **Hindari situs pihak ketiga** (domain aneh, "download gratis" beriklan).
> Sering dibundel software lain atau versi palsu. Kalau anti-virus
> memperingatkan, itu wajar untuk software virtualisasi **asalkan** file
> berasal dari domain resmi di atas.

## 2.2 Pasang

1. Jalankan file `MuMu...exe` (klik dua kali).
2. **Install path** — pilih yang penting:
   - **Bukan** drive C kalau bisa (mis. `D:\MuMu`).
   - **Hanya huruf Inggris, tanpa spasi** (`D:\MuMu` ✅, `D:\Emulator Game` ❌,
     `D:\Game 模拟器` ❌).
3. Ikuti wizard sampai **Install** selesai (±10–20 menit tergantung internet).
4. Buka MuMu Player dari desktop.

## 2.3 Atur MuMu untuk bot (penting)

Klik **⚙ ikon gir** (kanan atas MuMu) → **Settings**:

| Setting | Nilai yang disarankan | Kenapa |
|---|---|---|
| **Resolution / Resolusi** | `1600 x 720` (landscape) | sama dengan screenshot kalibrasi kita; hemat RAM |
| **DPI** | `240` | standar |
| **Performance / Performa** | CPU 2 core, RAM 4 GB, mode **DirectX** | cukup untuk 1 game |
| **ADB debugging** (menu *Lainnya/Advanced*) | **ON** | wajib, ini "pintu" bot ke emulator |
| **ADB port** | `16384` (instance 0), `16416` (instance 1) | dicatat nanti di config |
| **Startup / Autostart** | OFF | biar tidak buka sendiri saat boot |

Simpan → **restart instance** MuMu.

> Kalau di pengaturan tidak ada menu ADB, pakai cara MuMuManager di bagian 3.2 —
> script setup sudah otomatis melakukannya.

---

# BAGIAN 3 — Pasang Lord Mobile di emulator

## 3.1 Lewat Play Store (paling mudah)

1. Di MuMu, cari ikon **Play Store**.
2. Login akun Google (bisa akun baru khusus game).
3. Cari **"Lords Mobile"** → **Install**.
4. Buka game, login ke akun bank klan kamu.

## 3.2 Kalau Play Store tidak bisa dibuka

Unduh APK Lords Mobile dari sumber resmi/tepercaya, lalu:
**tarik file APK ke jendela MuMu** → otomatis terpasang.

## 3.3 Catat dua hal ini

- **Nama akun in-game** persis seperti yang muncul di chat
  (contoh tutorial: `Arken Ega`).
- **Instance MuMu** yang dipakai (0 atau 1) → menentukan port ADB.

---

# BAGIAN 4 — Pasang Python & unduh bot

## 4.1 Pasang Python

1. Buka **https://www.python.org/downloads/windows/**.
2. Pilih **Python 3.11** atau **3.12** → **Windows installer (64-bit)**.
3. Jalankan installer, dan **WAJIB centang**
   ☑ **Add python.exe to PATH** (bawah layar).
4. Klik **Install Now** → tunggu selesai.

Verifikasi di PowerShell (tutup & buka ulang PowerShell dulu):

```powershell
python --version
```

Harus muncul `Python 3.11.x` atau lebih baru. Kalau muncul
*"python is not recognized"*, install ulang dan centang opsi PATH tadi.
Alternatif: pakai `py --version`.

## 4.2 Unduh bot (repo ini)

**Cara A — dengan Git** (kalau Git terpasang):

```powershell
cd C:\
git clone https://github.com/egad13744-collab/lord-mobile-bots.git
cd lord-mobile-bots
```

**Cara B — tanpa Git:** buka halaman repo di GitHub → tombol **Code** →
**Download ZIP** → ekstrak ke `C:\lord-mobile-bots`
(perhatikan: di dalamnya harus ada file `code.py`, bukan folder bersarang).

Cek folder sudah benar:

```powershell
cd C:\lord-mobile-bots
dir
```

Harus terlihat: `code.py`, `lmbot`, `config`, `scripts`, `docs`, `tests`.

---

# BAGIAN 5 — Pasang otomatis (satu perintah)

Masih di folder bot, jalankan:

```powershell
Set-ExecutionPolicy -Scope Process Bypass -Force
.\scripts\setup-windows.ps1
```

Script ini melakukan:

1. cek Python (minimal 3.9),
2. buat virtual environment `.venv` (supaya tidak mengotori Python sistem),
3. `pip install` semua dependensi (PyYAML, OpenCV, Pillow, pytest),
4. unduh **platform-tools/ADB** bila belum ada, dan tambahkan ke PATH,
5. nyalakan instance MuMu + **aktifkan ADB** di port `16384`,
6. `adb connect 127.0.0.1:16384`,
7. jalankan `python code.py doctor`.

Contoh hasil yang sehat:

```
[lmbot] Python 3.11.9 OK
[lmbot] dependensi terpasang
[lmbot] adb ditemukan: C:\platform-tools\adb.exe
[lmbot] menyalakan instance 0 ...
[lmbot] aktifkan ADB instance 0 di port 16384 ...
connected to 127.0.0.1:16384

 ✔ adb ditemukan       C:\platform-tools\adb.exe
 ✔ koneksi device      terhubung
 ✔ screenshot          184223 byte
 ✔ flow YAML           49: abort, addtitle, ...
 ✔ template PNG        16 file
 ✔ OpenCV              aktif
Semua siap.
```

**Kalau ada tanda ✘**, lihat bagian 11 (Troubleshooting) sebelum lanjut.

### Kalau script gagal di langkah MuMu

Jalankan manual (sesuaikan path & instance):

```powershell
& "C:\Program Files\Netease\MuMuPlayer-12.0\shell\MuMuManager.exe" `
    adb -v 0 -cmd enable -adb_host 127.0.0.1 -adb_port 16384
adb connect 127.0.0.1:16384
adb devices
```

`adb devices` harus menampilkan `127.0.0.1:16384   device`
(kata **device**, bukan `offline` atau `unauthorized`).

---

# BAGIAN 6 — Isi konfigurasi

Buka file `config\settings.yaml` dengan Notepad:

```powershell
notepad config\settings.yaml
```

Ubah **tiga bagian** ini saja:

```yaml
device:
  serial: 127.0.0.1:16384     # 16416 bila memakai instance 1
  width: 1600                 # samakan dengan resolusi MuMu
  height: 720

bot:
  owner_nick: Arken Ega
  owners:                     # R6 = akses penuh, tidak bisa diturunkan dari chat
    - Arken Ega
  allowed_senders:            # otomatis jadi R5
    - Arken Ega
```

Simpan (**Ctrl+S**), tutup.

> **Nama di sini harus sama persis** dengan nama karakter di game (huruf besar/
> kecil dan spasi tidak masalah — bot menormalkan `Arken Ega` = `arken_ega`).

---

# BAGIAN 7 — Uji dulu tanpa menyentuh game (disarankan)

Ini membuktikan semuanya benar sebelum bot mengklik apa pun.

## 7.1 Simulasi penuh (tanpa emulator)

```powershell
.\.venv\Scripts\python.exe code.py demo
```

Kamu akan melihat 23 perintah dijalankan: whitelist, set saldo, kirim RSS,
transfer, penolakan rank rendah, bank dijeda, konfirmasi 2 langkah, dll.
Tidak ada yang sampai ke game.

## 7.2 Latihan interaktif (dry-run)

```powershell
.\.venv\Scripts\python.exe code.py --dry-run serve
```

Muncul prompt `lmbot>`. Coba ketik:

```
!version
!help
!members
!whitelist budi R2
!setbal budi food 10m
!bal
```

Keluar dengan `:quit`. Semua aksi hanya **dicatat**, tidak dieksekusi.

---

# BAGIAN 8 — Jalankan bot sungguhan

```powershell
.\scripts\start-bot.ps1
```

atau klik dua kali **`scripts\start-bot.bat`** (jendela berjudul
*LMBot - Dibuat oleh Egandika*).

Di prompt `lmbot>`, uji perintah **aman** dulu:

```
!version
!shield
!members
```

Lalu uji satu aksi ringan yang sudah terkalibrasi (buka surat):

```
!pos
```

## 8.1 Pahami hasil `!food` / `!transfer`

```
!food 1m
⚠️ saldo Food arkenega hanya 0, diminta 1M
```

Ini **normal**: kamu hanya bisa menarik RSS yang **sudah tercatat masuk** ke
saldo bot. Isi saldo dengan salah satu cara:

```
!setbal budi food 10m        (R5+)
```

atau dari terminal (tanpa buka bot):

```powershell
.\.venv\Scripts\python.exe code.py bank add budi --amount 10m 0 0 0 0
```

Urutan transfer yang benar: `RSS masuk bank` → `saldo bertambah` → member minta
`!food 1m` → saldo berkurang & RSS dikirim di game. Kalau langkah game gagal,
saldo **otomatis dikembalikan** (anti-balance-loss).

---

# BAGIAN 9 — Kalibrasi (agar bot bisa mengklik)

Ini bagian yang membuat `!food`, `!shield deploy`, `!relocate` benar-benar
bergerak. Bot sudah punya **16 template** dari screenshot-mu, tapi beberapa
layar belum ada (mis. panel bank/transfer).

## 9.1 Rekam layar

```powershell
.\.venv\Scripts\python.exe code.py record --out logs\screen.png
```

## 9.2 Buat template dari screenshot

Contoh: tombol Kirim.

```powershell
.\.venv\Scripts\python.exe code.py template add --screen logs\screen.png `
    --name send_button --box 0.70,0.80,0.12,0.08
```

Angka `--box` = `x,y,width,height` dalam **fraksi layar** (0–1) atau piksel.
Output-nya langsung memberi titik tap untuk flow:

```
✔ template 'send_button' dibuat
  fraksi   : [0.7, 0.8, 0.1195, 0.0792]
  untuk tap: tap: [0.7597, 0.8396]   ← tempel di flow YAML
```

## 9.3 Buktikan template ketemu

```powershell
.\.venv\Scripts\python.exe code.py verify --adb
```

Skor ≥ 0.86 = cocok. Cek daftar template yang masih kurang:

```powershell
.\.venv\Scripts\python.exe code.py template list
```

## 9.4 Aktifkan flow

Buka `config\flows\bank_open_member.yaml`, ganti angka `tap:` dengan hasil
langkah 9.2, lalu ubah `enabled: false` → `enabled: true`.
Ulangi untuk `bank_send_one_type.yaml`.

Panduan rinci + daftar layar yang perlu difoto:
**`docs/CALIBRATION.md`** dan **`docs/ASSET-REPORT.md`**.

> Selama flow belum aktif, perintah yang butuh aksi game akan menolak dengan
> pesan jelas dan **saldo tidak berkurang**. Perintah berbasis data tetap jalan
> penuh: `!bal`, `!top`, `!members`, `!whitelist`, `!setbal`, `!sync`, `!help`,
> `!stats`, `!version`.

---

# BAGIAN 10 — Jalankan 24 jam tanpa mati

## 10.1 Jangan biarkan layar terkunci

```powershell
powercfg /change standby-timeout-ac 0
powercfg /change monitor-timeout-ac 0
powercfg /change hibernate-timeout-ac 0
```

## 10.2 Keluar RDP dengan benar (jangan "Disconnect")

Kalau kamu menutup jendela RDP biasa, sesi terkunci dan emulator berhenti
render. Gunakan `tscon` untuk mengembalikan sesi ke konsol fisik:

```powershell
query session
tscon 1 /dest:console        # 1 = nomor sesi RDP kamu
```

## 10.3 Autostart setelah reboot

```powershell
$action  = New-ScheduledTaskAction -Execute "powershell.exe" `
  -Argument "-WindowStyle Hidden -ExecutionPolicy Bypass -File C:\lord-mobile-bots\scripts\start-bot.ps1 -Mode http -Port 8080"
$trigger = New-ScheduledTaskTrigger -AtStartup
Register-ScheduledTask -TaskName "LMBot" -Action $action -Trigger $trigger -RunLevel Highest
```

## 10.4 Pantau dari HP (opsional)

```powershell
.\scripts\start-bot.ps1 -Mode http -Port 8080 -Token rahasia123
```

Buka di browser HP: `http://IP-MESIN:8081/?token=rahasia123`
(melihat saldo, transaksi, status template, dan peringatan).

---

# BAGIAN 11 — Troubleshooting

| Gejala | Penyebab & solusi |
|---|---|
| `python is not recognized` | Python belum masuk PATH → install ulang, centang *Add to PATH* |
| `running scripts is disabled` | Jalankan `Set-ExecutionPolicy -Scope Process Bypass -Force` |
| `adb: device offline` | `adb kill-server` lalu `adb connect 127.0.0.1:16384` |
| `gagal terhubung ke 127.0.0.1:16384` | ADB debugging di MuMu belum ON, atau port beda (instance 1 = 16416) |
| `adb` tidak ditemukan | Pasang platform-tools, atau isi `device.adb_path` dengan path lengkap `adb.exe` |
| `screenshot kosong` | Jendela MuMu minimized / sesi RDP terkunci → bagian 10 |
| `flow '...' masih dinonaktifkan` | Belum dikalibrasi → bagian 9 |
| `tidak di layar bank/peta klan` | Bot ada di layar lain; buka peta klan atau panel bank |
| `saldo ... hanya 0` | Belum ada RSS tercatat; isi lewat `!setbal` atau `bank add` |
| `bank sedang dijeda` | Ada `!stop`/`!abort` aktif → `code.py bank unfreeze` |
| `kamu belum terdaftar di whitelist` | Nama pengirim ≠ `owner_nick`/`allowed_senders` di config |
| `perintah tidak dikenal` | Ketik `!help`; ejaan perintah harus diawali `!` |
| MuMu lambat / patah-patah | Turunkan resolusi ke 1280×720, naikkan CPU/RAM instance |
| Bot tidak bereaksi di chat game | Mode `--source chat` butuh OCR → lihat `docs/OCR.md`, atau pakai terminal/webhook |

Log lengkap: **`logs\bot.log`** · Audit transaksi: **`state\transactions.jsonl`**
· Peringatan: **`logs\alerts.jsonl`**

---

# BAGIAN 12 — Perintah harian (cheat sheet)

```
!version                     versi & pembuat bot
!help                        daftar semua perintah
!help RSS                    daftar perintah per kategori

!bal                         saldo saya
!food 10m                    kirim 10 juta food ke saya
!rss 5m 5m 0 0 0             kirim food + stone
!transfer budi ore 1m        pindahkan 1m ore saya ke budi
!top food                    peringkat penabung

!members                     daftar whitelist
!whitelist budi R2           daftarkan member (R5+)
!blacklist penipu            tolak nick (R4+)

!shield                      status pengiriman bank
!stop 3600                   jeda bank 1 jam (R4+)
!abort                       batalkan semua pengiriman (R4+)

!guild AYU                   minta konfirmasi
!guild AYU confirm           eksekusi
!relocate 123 456 confirm    pindah bank ke koordinat
!findtile food 4 chat        cari tambang food level 4
```

Rank: **R1** member · **R4** officer · **R5** leader · **R6** owner (dari config).

---

# BAGIAN 13 — Etika & risiko (baca ini)

- Otomatisasi emulator **melanggar ToS hampir semua game**, termasuk Lords
  Mobile. Risiko ban ada di akunmu.
- Gunakan **akun bank/alt klan**, jangan akun utama.
- Bot menyimpan saldo di buku besarnya sendiri (`state/bank.json`), bukan
  membaca angka di layar. Selalu cocokkan dengan `!adminbag`/`!sync`.
- Jangan bagikan `config\settings.yaml`, `state\`, dan token webhook — itu
  kunci akses bot kamu.
- `!abort` dan `!stop` adalah tombol panik: keduanya memblokir semua
  pengiriman RSS.

---

**LMBot v1.0.0 — Dibuat oleh Egandika**
Lisensi MIT · Kendala lain? buka `docs\SETUP-WINDOWS.md` lalu
`docs\ASSET-REPORT.md`.
