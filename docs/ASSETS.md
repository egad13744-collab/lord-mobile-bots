# Kirim screenshot → bot bisa kalibrasi sendiri

Bagian ini menjelaskan alur kerja "kamu kirim screenshot mentah, saya/alat
memotongnya jadi template + koordinat". **Tidak perlu crop manual** — cukup
tentukan area dengan angka, semua pemotongan & pengecilan dilakukan script.

## 1. Screenshot yang paling berguna

Kirim **fullscreen, tanpa di-crop, tanpa di-resize** (WhatsApp/Telegram sering
mengecilkan gambar — kirim sebagai *dokumen/file* agar utuh). Urutan prioritas:

| # | Layar | Untuk apa |
|---|---|---|
| 1 | Peta klan (castle bank terlihat) | `guild_map`, deteksi posisi aman |
| 2 | Menu klan (tombol Bank, Member, …) | `guild_menu` + tombol Bank |
| 3 | Panel **Bank klan** terbuka | `bank_panel`, tab Food/Stone/Wood/Ore/Gold |
| 4 | Kolom cari member + hasilnya | `search_member`, `member_row` |
| 5 | Kolom jumlah + tombol **Kirim** | `send_button` → inti `!food`, `!transfer` |
| 6 | Dialog konfirmasi (OK/Cancel) | `popup_ok` |
| 7 | Chat in-game terbuka | `chat_panel` (opsional, untuk OCR) |

Sertakan juga: **resolusi asli** (biasanya terbaca dari file) dan **DPI/ukuran
window MuMu** kalau kamu mengubahnya.

## 2. Alat yang sudah tersedia

```powershell
# cek template mana yang masih kurang
python code.py template list

# ambil screenshot langsung dari emulator
python code.py record --out logs/screen.png

# potong satu area jadi template (fraksi 0..1 ATAU piksel)
python code.py template add --screen logs/screen.png --name send_button --box 0.70,0.80,0.12,0.08
python code.py template add --screen shot_hp.jpg --name bank_panel --box 896,576,153,57 --scale 0.5

# uji apakah template benar-benar ketemu di screenshot (skor + posisi tap)
python code.py verify --screen logs/screen.png
python code.py verify --adb            # ambil screenshot baru lalu uji semua template
```

Output `template add` langsung memberi angka untuk flow:

```
✔ template 'send_button' dibuat: assets/templates/send_button.png
  fraksi   : [0.7, 0.8, 0.1195, 0.0792]
  untuk tap: tap: [0.7597, 0.8396]   ← tempel di flow YAML
```

Script kecil untuk satu kali crop cepat:

```powershell
python tools/crop.py logs/screen.png --box 0.70,0.80,0.12,0.08 --out logs/kirim.png --scale 2
```

## 3. Format `--box`

Dua gaya, keduanya diterima:

- **Fraksi layar**: `x,y,w,h` dengan nilai 0..1 → `0.70,0.80,0.12,0.08`
  artinya mulai 70% lebar, 80% tinggi, ukuran 12% × 8%.
- **Piksel**: `x,y,w,h` dengan nilai > 1 → `896,576,153,57`.

Kalau ragu, pakai fraksi: tetap benar di resolusi lain, dan template hasil crop
sudah otomatis diskalakan.

> **Penting:** template yang saya buat dari screenshot HP (rasio lain) tetap
> berfungsi karena bot mencocokkan **pola**, bukan posisi. Namun kalau rasio
> sangat berbeda (HP portrait vs MuMu landscape), tombol bisa berada di tempat
> lain — crop ulang dari screenshot MuMu untuk hasil terbaik.

## 4. Ukuran template yang disarankan

| Elemen | Lebar template | Catatan |
|---|---|---|
| Ikon/tombol kecil | 60–160 px | jangan lebih kecil dari 40 px (rawan noise) |
| Tab kategori (Food/Stone…) | 120–260 px | ikutkan teks labelnya |
| Panel/judul bank | 200–500 px | pakai `--max-width` bila perlu |
| Dialog popup | 100–300 px | tombol OK saja, bukan seluruh dialog |

Simpan **grayscale** (default) — lebih cepat & tahan perbedaan warna tema.
Pakai `--color` hanya bila dua elemen mirip secara bentuk tapi beda warna.

## 5. Setelah template siap

1. `python code.py template list` → target semua ✔ (14 template).
2. Sesuaikan flow: buka `config/flows/bank_open_member.yaml` dan
   `bank_send_one_type.yaml`, ganti angka `tap:` dengan nilai dari langkah 2,
   lalu set `enabled: true`.
3. Uji tanpa risiko:
   ```powershell
   python code.py --dry-run cmd "!food 1m"
   python code.py verify --adb           # posisi masih ketemu?
   python code.py cmd "!shield"          # aksi ringan dulu
   ```
4. Baru naik ke nominal kecil: `python code.py cmd "!food 100k"`.

## 6. Kalau skor rendah (< 0.75)

Penyebab umum dan solusinya:

| Gejala | Solusi |
|---|---|
| Skor ~0.3–0.5 | Area crop salah (kena latar) → geser box, lihat `logs/crop.png` hasil `tools/crop.py` |
| Skor naik-turun antar run | Ada animasi/partikel → crop bagian statis saja (mis. teks label) |
| Skor bagus di screenshot uji, gagal di emulator | Resolusi beda → crop ulang dari `record` (screenshot MuMu), bukan dari HP |
| Ditemukan di posisi salah | Template terlalu umum (mis. kotak kosong) → perbesar area & ikutkan teks unik |

Turunkan `templates.threshold` (default `0.86`) hanya sebagai langkah terakhir,
mis. ke `0.80`. Di bawah `0.75` risiko salah tap mulai besar.

## 7. Tips pengiriman aset

- Kirim **1 screenshot per kondisi layar**, bukan GIF/video.
- Jangan diberi coretan/anotasi — kotak merah di gambar bisa ikut tercrop.
- Bila ada beberapa akun/ukuran font berbeda, kirim satu set per akun.
- Simpan nama file deskriptif: `bank_panel.png`, `bank_menu.png`,
  `chat_open.png` agar mudah dipetakan ke `template list`.
