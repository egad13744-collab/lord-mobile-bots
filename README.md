# LMBot — Bot Guild Bank Lord Mobile (MuMu Player + ADB)

Bot yang dijalankan **di terminal sesi RDP Windows**, menemani **MuMu Player**.
Perintahnya mengikuti daftar di gambar: **GUILD, SEARCH, BALANCE, RSS**
(`!bal`, `!transfer`, `!food 100m`, `!relocate 123 456`, `!whitelist nick R3`, …).

Cara kerja: bot **melihat layar** (`adb exec-out screencap`), **menyentuh layar**
(`adb shell input tap`), dan **mengetik** (`adb shell input text`) — persis
seperti tangan manusia memakai emulator. Tidak ada modifikasi APK, tidak ada
inject memori, tidak ada pembacaan paket jaringan.

```
Chat / terminal / webhook
        │
        ▼
   parser.py  ──► roles.py (whitelist + rank R1–R6)
        │
        ▼
   handlers.py  ──► state.py (buku besar saldo + audit log)
        │
        ▼
   ops.py ──► flows.py (YAML: tap/wait/type) ──► device.py (ADB) ──► MuMu Player
                                            └──► vision.py (template matching)
```

---

## 1. Mulai cepat di RDP Windows

```powershell
# di folder repo, PowerShell (Admin)
git clone <repo-ini> lord-mobile-bots
cd lord-mobile-bots

Set-ExecutionPolicy -Scope Process Bypass -Force
.\scripts\setup-windows.ps1          # venv + dependensi + adb + MuMu ADB + doctor
.\scripts\start-bot.ps1              # jalankan bot (interaktif)
```

Setelah bot hidup, di prompt `lmbot>`:

```
!whitelist lady_ayu R5
!setbal lady_ayu food 100m
!bal
!food 10m
```

Panduan langkah demi langkah: **[docs/SETUP-WINDOWS.md](docs/SETUP-WINDOWS.md)**.

### Tanpa emulator (uji logika dulu)

```powershell
.\.venv\Scripts\python.exe code.py demo           # simulasi 18 perintah, tanpa Windows/emulator
.\.venv\Scripts\python.exe code.py --dry-run serve
```

`code.py demo` menjalankan skenario penuh (whitelist, set saldo, kirim RSS,
transfer, penolakan rank rendah, bank dijeda, perintah tak dikenal) memakai
driver **Mock**. `--dry-run` mencatat semua aksi yang *akan* dilakukan tanpa
menyentuh emulator dan tanpa mengubah `state/bank.json`.

---

## 2. Daftar perintah (sesuai gambar)

Semua perintah diawali `!`. Bot hanya merespons pesan berawalan `[R4]`
(bisa diubah di `ui.msg_prefix`), dan hanya dari nick yang ada di whitelist.

### GUILD
| Kode | Fungsi | Rank |
|---|---|---|
| `!guild (nick)` | pindahkan bank klan ke klan tujuan | R4 |
| `!stats` / `!stats all` | report kill monster / hadiah box klan | R1 |
| `!pstats (nick)` | report kill monster anggota | R1 |
| `!stop (detik)` | matikan bank selama N detik | R4 |
| `!pos` / `!pos chat` | kirim lokasi bank | R1 |
| `!shield` / `!shield deploy` | cek / aktifkan shield bank | R1 / R4 |
| `!relocate (X)(Y)` | pindah bank ke koordinat | R4 |
| `!relocatekvk (K)` / `!relocate rand` | pindah acak di KD | R4 |
| `!recall all` | tarik semua troop pulang | R4 |
| `!buildspam (jml)(lvl)` / `!buildspam stop` | spam jahat tangan | R3 |
| `!hunt (X)(Y)` | buru monster | R3 |
| `!addtitle (nick)(gelar)` / `!deltitle (nick)` | kelola gelar | R4 |
| `!whitelist (nick)(rank)` | auto acc & up rank | R5 |
| `!blacklist` / `!unwhitelist` / `!unblacklist` | kelola daftar akses | R4–R5 |
| `!abort` | batalkan semua pengiriman RSS (+ jeda 10 menit) | R4 |
| `!quest` | cek misi GF bank | R1 |
| `!setgather on/off` | bot menambang | R4 |
| `!migrate k x y` | pindah bank ke KD lain | R5 |
| `!snowbeast` | aktifkan familiar snowbeast | R4 |
| `!members` | refresh/lihat daftar member | R1 |
| `!joingvg` / `!leavegvg` | masuk/keluar arena GE | R4 |
| `!clearboard` | hapus seluruh papan misi | R4 |
| `!gyphon` | tarik cepat pasukan | R3 |
| `!joinca (kode) [F]` / `!leaveca` | masuk/keluar arena chaos | R4 |
| `!joinda` / `!leaveda` | masuk/keluar arena DA | R4 |

### SEARCH
`!findtile (type)(level) [chat]` · `!findtile any (level) [chat]` ·
`!findtilelocal (type)(level) [chat]` · `!findmonster (nama)(level) [chat]` ·
`!findnest (level) [chat]` · `!findtile gems (level) [chat]`

### BALANCE
| Kode | Fungsi | Rank |
|---|---|---|
| `!bal` | cek tabungan sendiri | R1 |
| `!adminbal` / `!adminbal (nick)` | RSS di luar tas / tabungan member | R4 |
| `!adminbag` | RSS di dalam tas bank | R4 |
| `!setbal (nick)(type)(jumlah)` | set saldo manual | R5 |
| `!transfer (nick)(type)(jumlah)` | transfer tabungan ke member | R1 |

### RSS
| Kode | Fungsi | Rank |
|---|---|---|
| `!rss F S W O G` | kirim semua tipe sekaligus | R1 |
| `!food` `!stone` `!wood` `!ore` `!gold` `(jumlah)` | kirim satu tipe | R1 |
| `!donate (type)(nick)(jumlah)` | kirim RSS ke player lain | R1 |
| `!adminrss F S W O G (nick)` | kirim semua tipe ke player lain | R5 |

Keterangan: **F**=food, **S**=stone, **W**=wood, **O**=ore, **G**=gold.
Jumlah menerima `k`/`m`/`b`: `100m`, `1.5k`, `2b`, atau angka biasa.

---

## 3. Perintah terminal (bukan chat game)

```powershell
python code.py demo                       # simulasi tanpa emulator
python code.py doctor                     # cek adb, emulator, flow, template
python code.py serve                      # bot interaktif
python code.py serve --source file        # perintah dari state/commands.txt (sender|!cmd)
python code.py serve --http-port 8080     # webhook: POST {"text":"!bal","sender":"lady_ayu"}
python code.py cmd "!shield" --sender lady_ayu
python code.py bank add budi --amount 1m 0 0 0 0
python code.py bank list --key food
python code.py bank whitelist budi --rank R3
python code.py bank unfreeze
python code.py record --out logs/screen.png   # screenshot utk kalibrasi koordinat
```

---

## 4. Yang perlu dikalibrasi (penting)

Bot sudah **100% siap untuk logika**: parser, rank, saldo, whitelist, rate
limit, audit, refund anti-balance-loss. Yang belum bisa ditebak dari gambar
adalah **posisi tombol UI di akunmu** — itu harus direkam sekali:

1. `python code.py record` → screenshot layar MuMu.
2. Catat koordinat tombol (mis. Bank klan, kolom jumlah) lalu ubah ke fraksi:
   `fx = x / lebar`, `fy = y / tinggi`.
3. Isi `config/flows/bank_open_member.yaml` & `bank_send_rss.yaml`,
   ubah `enabled: false` → `true`.

Panduan detail + contoh angka: **[docs/CALIBRATION.md](docs/CALIBRATION.md)**.

Sampai kalibrasi selesai, perintah yang butuh aksi di game (mis. `!food 10m`)
akan menolak dengan pesan jelas dan **saldo tidak berkurang** (debit
di-rollback otomatis). Perintah berbasis state (`!bal`, `!members`,
`!whitelist`, `!stats`, `!adminbal`) langsung berfungsi.

---

## 5. Keamanan & tanggung jawab

- **Whitelist wajib**: nick di luar whitelist tidak bisa apa-apa. Owner R6
  hanya bisa ditambah lewat file state (`bank whitelist` / edit JSON).
- **Batas aman**: `safety.max_rss_per_transfer` menolak transfer di atas batas
  (default 300M per tipe). `!abort` dan `!stop` memblokir semua pengiriman.
- **Audit trail**: setiap perubahan saldo ditulis ke `state/transactions.jsonl`.
- **Rank**: hanya R4+ yang bisa menggerakkan bank; R5 untuk set saldo/whitelist.
- Otomatisasi emulator **melanggar ToS hampir semua game**, termasuk Lord
  Mobile. Risiko ban ada di akunmu. Gunakan hanya untuk akun bank/alt klan,
  jangan akun utama — dan pahami ini sebelum menjalankan bot.

## 6. Struktur repo

```
code.py                  entry point (python code.py ...)
lmbot/
  config.py  device.py   config + driver ADB/Mock
  parser.py  roles.py    perintah & otorisasi rank
  handlers.py state.py   logika bisnis + buku besar saldo
  ops.py  flows.py       operasi game + engine flow YAML
  vision.py              template matching (OpenCV opsional)
  bot.py  chat.py  cli.py
config/settings.yaml     konfigurasi utama
config/flows/*.yaml      koordinat alur UI (kalibrasi di sini)
scripts/                 setup-windows.ps1, start-bot.ps1/.bat
docs/                    SETUP-WINDOWS, CALIBRATION, OCR
tests/                   46 test tanpa emulator (pytest)
```

## 7. Development

```bash
pip install -r requirements.txt
python -m pytest -q          # semua test tanpa emulator
python code.py --dry-run serve
```

Lisensi: MIT (lihat `LICENSE`).
