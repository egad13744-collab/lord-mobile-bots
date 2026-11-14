# CARA KERJA BOT — penjelasan lengkap

**LMBot — Dibuat oleh Egandika**

Ringkasnya: bot ini **meniru tangan dan mata manusia** di emulator.
Ia mengambil gambar layar MuMu, mengenali tombol, lalu menyentuhnya lewat ADB —
sama seperti kamu mengklik sendiri. Tidak ada modifikasi game, tidak ada
penyuntikan kode ke aplikasi, tidak ada pembacaan memori atau jaringan.

```
   Chat game / Terminal / File / Webhook / Dashboard
                          │
                          ▼
                  ┌───────────────┐
                  │  1. SUMBER    │  lmbot/chat.py
                  └───────┬───────┘
                          ▼
                  ┌───────────────┐
                  │  2. PARSER    │  lmbot/parser.py
                  └───────┬───────┘
                          ▼
                  ┌───────────────┐
                  │ 3. OTORISASI  │  lmbot/roles.py   (whitelist + rank R1–R6)
                  └───────┬───────┘
                          ▼
                  ┌───────────────┐
                  │  4. HANDLER   │  lmbot/handlers.py
                  └──┬────────┬───┘
                     │        │
        ┌────────────▼──┐  ┌──▼──────────────┐
        │ 5. BUKU BESAR │  │  6. AKSI LAYAR  │  lmbot/ops.py
        │ lmbot/state.py│  └──┬──────────────┘
        └───────────────┘     │
                              ▼
                     ┌────────────────┐
                     │ 7. FLOW (YAML) │  config/flows/*.yaml
                     └────────┬───────┘
                              ▼
                     ┌────────────────┐
                     │ 8. DRIVER ADB  │  lmbot/device.py
                     └────────┬───────┘
                              ▼
                    MuMu Player (Lords Mobile)
```

---

## 1. Sumber perintah

Bot bisa menerima perintah dari empat "pintu":

| Mode | Cara pakai | Butuh OCR? |
|---|---|---|
| `terminal` | ketik `!bal` di prompt `lmbot>` | tidak |
| `file` | baris `Arken Ega|!food 1m` di `state/commands.txt` | tidak |
| `http` | `POST /` dengan JSON `{"text":"!bal","sender":"Arken Ega"}` | tidak |
| `chat` | membaca chat game lewat `ui.chat_tail` (bridge OCR) | ya, untuk membaca |

Bot juga **menolak** pesan tanpa awalan yang benar. Default `ui.msg_prefix: R4`
artinya pesan `[R4] !food 1m` diterima, sedangkan obrolan biasa diabaikan.

## 2. Parser — mengubah teks jadi perintah

`lmbot/parser.py` punya daftar **spesifikasi** semua perintah (nama, pola,
deskripsi, rank minimum, contoh) yang diambil dari daftar di gambar awal.

```
"!transfer Arken Ega ore 1m"
        └──┬───┘ └──┬────┘ └┬┘ └┬┘
           │        │       │    └── amount (diparse: 1m = 1.000.000)
           │        │       └─────── type  (ore = O, diubah ke key "ore")
           │        └─────────────── nick  (target)
           └──────────────────────── command = "transfer"
```

Parser murni bekerja pada teks — tidak menyentuh emulator, sehingga bisa diuji
tanpa game. Karena itu ada **91 test** yang berjalan dalam hitungan detik.
Angka menerima `k`/`m`/`b` (`100m`, `1.5k`, `2b`) atau angka biasa.

## 3. Otorisasi — siapa boleh apa

Dua lapis:

1. **Whitelist** (`state/bank.json` → `roster`). Nick yang tidak terdaftar tidak
   bisa menjalankan apa pun, bahkan `!bal`.
2. **Rank R1–R6** per perintah:

| Rank | Boleh |
|---|---|
| R1 | `!bal`, `!food`, `!rss`, `!findtile`, `!stats`, `!help` |
| R3 | `!buildspam`, `!hunt`, `!gyphon` |
| R4 | `!guild`, `!relocate`, `!shield deploy`, `!stop`, `!abort`, `!blacklist` |
| R5 | `!whitelist`, `!setbal`, `!adminrss`, `!migrate` |
| R6 | owner — melewati semua batas (hanya bisa diatur dari `settings.yaml`) |

Nick dinormalkan (`Arken Ega` = `arken_ega` = `Arken_Ega`), jadi salah ketik
spasi/underscore tidak membuat orang kehilangan akses.

## 4. Handler — logika tiap perintah

Satu fungsi per perintah di `lmbot/handlers.py`. Handler **tidak pernah**
menyentuh koordinat layar. Ia hanya:

- memvalidasi argumen (`ParseError` bila salah),
- memeriksa izin dan batas aman (`safety.max_rss_per_transfer`),
- memanggil **buku besar** dan/atau **operasi layar**,
- mengembalikan teks balasan untuk dikirim ke chat.

Pemisahan ini yang membuat seluruh perilaku bisa diuji dengan emulator palsu
(`MockOps`) dan `--dry-run`.

## 5. Buku besar — sumber kebenaran saldo

`lmbot/state.py` menyimpan saldo per member di `state/bank.json`:

```json
{
  "balances": {
    "arkenega":  {"food": 42000000, "stone": 0, "wood": 0, "ore": 0, "gold": 0},
    "budi":      {"food": 10000000, "stone": 0, "wood": 0, "ore": 0, "gold": 0}
  },
  "roster": { "owners": ["arkenega"], "whitelist": {"budi": "R2"} }
}
```

Setiap perubahan ditulis **atomik** (tulis file sementara → rename) supaya tidak
korup kalau listrik mati, dan dicatat ke `state/transactions.jsonl` (audit).

### Aturan anti-rugi (penting)

Urutan transfer RSS:

```
1. cek saldo cukup        → kalau tidak, tolak (tidak ada perubahan)
2. DEBIT saldo pengirim
3. kirim RSS di game (tap/ketik lewat ADB)
4. kalau langkah 3 GAGAL  → CREDIT balik (refund otomatis) + pesan error
5. kalau langkah 3 SUKSES → CREDIT saldo penerima
```

Artinya: **RSS tidak akan pernah "hilang" dari catatan** walaupun emulator
macet di tengah jalan.

## 6. Operasi layar — dari perintah ke gerakan

`lmbot/ops.py` menerjemahkan niat ("buka panel bank untuk nick budi") menjadi
urutan langkah. Ada dua implementasi:

- **`AdbOps`** — benar-benar menggerakkan MuMu.
- **`MockOps`** — mencatat panggilan saja (dipakai `--dry-run`, `demo`, dan test).

Yang dijaga di lapisan ini:

- **`DEVICE_LOCK`** — hanya satu alur boleh menyentuh layar pada satu waktu,
  sehingga terminal + webhook + loop chat tidak saling menimpa klik.
- **Retry** — flow yang gagal dicoba ulang (`flows.max_retries`), dengan
  pemulihan layar (tombol *back*) sebelum menyerah.
- **Alert** — kegagalan dicatat ke `logs/alerts.jsonl` (opsional dikirim ke
  webhook Discord/Slack), dengan throttle agar tidak spam.

## 7. Flow YAML — koordinat dipisah dari kode

Kenapa YAML? Karena posisi tombol **berbeda di tiap akun/resolusi**. Dengan
memisahkannya, kamu bisa memperbaiki koordinat tanpa menyentuh Python.

Contoh `config/flows/open_mail.yaml`:

```yaml
name: open_mail
enabled: true
steps:
  - assert: main_hud        # tunggu template "main_hud" terlihat (kalau ada)
  - tap: [0.6531, 0.9472]   # koordinat FRAKSI (0..1), bukan piksel
  - wait: 1.5
  - assert: {template: mail_button, timeout: 6}
```

Koordinat ditulis sebagai **fraksi** (`0.5` = tengah layar) sehingga tetap benar
walau resolusi emulator berbeda. Langkah yang tersedia: `tap`, `tap_text`,
`wait`, `wait_stable`, `type`, `swipe`, `back`, `key`, `assert`, `if_template`,
`swipe_until`, `screenshot`.

Flow yang masih `enabled: false` akan **menolak** dengan pesan jelas — bukan
mengklik sembarangan. Ini pengaman saat kalibrasi belum selesai.

## 8. Driver ADB — mata dan tangan

`lmbot/device.py` memakai perintah ADB standar:

| Kebutuhan | Perintah |
|---|---|
| Melihat layar | `adb exec-out screencap -p` |
| Menyentuh | `adb shell input tap X Y` |
| Menggeser | `adb shell input swipe X1 Y1 X2 Y2 MS` |
| Mengetik | `adb shell input text ...` |
| Tombol back | `adb shell input keyevent 4` |

Sentuhan dapat diberi **toleransi koordinat ±4 px** (`flows.tap_jitter`) untuk
mengompensasi titik crop yang sedikit meleset. Ini bukan simulasi perilaku manusia
atau fitur anti-deteksi; jitter juga dapat membuat tap meleset dari kontrol kecil.
Kalau koneksi putus (`DeviceError`), `DeviceSession` menyambung ulang otomatis
dengan backoff.

## 9. Penglihatan (vision) — mengenali layar

`lmbot/vision.py` mencocokkan **template PNG** (`assets/templates/*.png`)
dengan screenshot:

- Dengan OpenCV: `cv2.matchTemplate` (cepat, <100 ms di 1600×720).
- Tanpa OpenCV: fallback murni Python (lebih lambat tapi tetap jalan).
- Template hampir polos memakai `TM_SQDIFF_NORMED` agar tidak salah baca.

Dipakai untuk dua hal: memastikan bot **ada di layar yang benar**
(`assert`, `current_screen`) dan menutup popup nyasar (`close_popup`).

## 10. Dashboard & monitoring

`--web-port 8081` menyalakan halaman status: total tabungan, top penabung,
15 transaksi terakhir, status 25 template, dan peringatan terakhir. Endpoint
`/api/status` mengembalikan JSON. Bisa dibuka dari HP di jaringan yang sama.

## 11. Keamanan berlapis

| Lapis | Fungsi |
|---|---|
| Whitelist | orang asing tidak bisa apa-apa |
| Rank | member biasa tidak bisa memindahkan bank |
| Konfirmasi 2 langkah | `!guild AYU` harus diulang `!guild AYU confirm` |
| Batas nominal | `safety.max_rss_per_transfer` menolak transfer raksasa |
| Jeda bank | `!stop`, `!abort` memblokir semua pengiriman |
| Refund otomatis | saldo tidak hilang saat aksi game gagal |
| Audit log | semua mutasi saldo tercatat dengan waktu & pelaku |
| Diagnosa config | peringatan saat masih memakai nilai contoh/berbahaya |

## 12. Batasan yang perlu kamu tahu

1. **Saldo bot ≠ isi tas game.** Bot memakai buku besarnya sendiri; angka di
   layar tidak dibaca (butuh OCR yang akurat). Cocokkan manual dengan
   `!adminbag`/`!sync`.
2. **Layar harus ter-render.** Sesi RDP yang terkunci membuat screenshot hitam.
   Gunakan `tscon` (lihat tutorial).
3. **Flow yang belum dikalibrasi tidak melakukan apa pun** — ini disengaja.
4. **Teks chat sulit dibaca tanpa OCR**, jadi sumber perintah utama adalah
   terminal/webhook.
5. **Otomatisasi melanggar ToS game.** Risiko ban ada di akunmu; gunakan akun
   bank/alt klan.

---

**LMBot v1.1.0 — Dibuat oleh Egandika**
