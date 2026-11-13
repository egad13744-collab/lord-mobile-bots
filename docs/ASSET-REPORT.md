# Laporan pemeriksaan aset UI (Google Drive: "mentahan UI lord mobile")

Tanggal cek: 2026-11-13 · 9 screenshot, semua **1600×720** (landscape, JPEG).

## 1. Hasil: 16 template dibuat (skor 1.000, tanpa salah cocok)

Diuji silang ke 9 screenshot: setiap template hanya cocok di layarnya sendiri
(off-diagonal ≤ 0.6). Artinya tidak ada risiko template "ketuker" saat bot
mengecek layar.

| Template | Layar sumber | Crop (px) | Tap (fraksi 1600×720) |
|---|---|---|---|
| `main_hud` | kota utama | 1200,560,380,135 | `[0.8688, 0.8716]` |
| `main_profile` | kota utama | 0,0,270,115 | `[0.0844, 0.0799]` |
| `gift_button` | bottom bar | 862,645,80,70 | `[0.5638, 0.9444]` |
| `mail_button` | bottom bar | 1005,650,80,65 | `[0.6531, 0.9472]` |
| `report_button` | bottom bar | 1105,645,80,70 | `[0.7156, 0.9444]` |
| `settings_button` | bottom bar | 1205,648,78,70 | `[0.7775, 0.9486]` |
| `bag_button` | bottom bar | 1305,645,80,70 | `[0.8406, 0.9444]` |
| `barak_button` | bottom bar | 1408,640,78,75 | `[0.9044, 0.9403]` |
| `guild_tabs` | panel Klan | 270,235,980,78 | `[0.4751, 0.3805]` |
| `hadiah_klan_tab` | Hadiah Klan | 640,210,320,60 | `[0.5000, 0.3334]` |
| `buka_button` | Hadiah Klan | 1145,272,150,52 | `[0.7625, 0.4139]` |
| `misi_tabs` | Misi | 230,120,1085,55 | `[0.4828, 0.2049]` |
| `btn_selesaikan` | Misi Admin | 1130,252,200,48 | `[0.7688, 0.3833]` |
| `peti_vip` | Misi VIP | 430,300,145,110 | `[0.3140, 0.4931]` |
| `barak_actions` | Barak | 930,555,400,110 | `[0.7063, 0.8472]` |
| `close_button` | semua panel | 1470,5,125,95 | `[0.9577, 0.0728]` |

Flow yang sudah **aktif** dengan koordinat terukur ini:
`chat_open`, `chat_send`, `open_mail`, `open_barak`.
`verify_screens`, `open_guild`, `misi_harian` masih `enabled: false` karena
butuh satu titik yang belum terlihat di aset (lihat bagian 3).

## 2. Temuan penting: UI-nya tidak punya "panel Bank"

Asumsi awal (dari daftar perintah di gambar) adalah ada panel bank klan dengan
kolom jumlah + tombol Kirim. Dari 9 screenshot ini **tidak ada panel seperti
itu**. Yang terlihat:

- Panel **Klan** hanya punya 4 tab: **Dewan Diplomasi, Anggota, Lamaran,
  Level Hadiah** — tidak ada tab Bank.
- Bottom bar kota: **hadiah, surat (mail), laporan, pengaturan, tas, barak**.
- Di Lord Mobile, RSS masuk/keluar lewat **Surat (mail)** dan **hadiah klan**,
  dikelola dari **tas/inventory**.

Artinya `bank_open_member.yaml` dan `bank_send_one_type.yaml` kemungkinan
**tidak akan pernah cocok** dengan UI ini. Untuk memastikan, saya butuh 1–2
screenshot lagi (lihat bagian 3). Setelah itu flow-nya akan saya tulis ulang
mengikuti alur yang sebenarnya — bukan menebak.

## 3. Screenshot tambahan yang dibutuhkan (5 menit)

| # | Layar | Kenapa perlu |
|---|---|---|
| 1 | **Tas/Inventory** (klik ikon `bag_button`) | Untuk lihat apakah ada kotak "Guild Bank"/tab resource di sana |
| 2 | **Surat/Mail** terbuka | Tempat klaim RSS; perlu lihat tombol "Klaim Semua", daftar surat, dan apakah ada opsi kirim ke member |
| 3 | **Menu Klan** dari peta (bukan panel yang sudah ada) | Untuk dapat titik tombol buka Klan → `open_guild` bisa aktif |
| 4 | **Dialog kirim/transfer resource** (kalau ada) | Inti `!food`, `!transfer`, `!donate` |
| 5 | **Chat in-game terbuka** | `chat_panel` + area OCR (opsional, untuk mode `--source chat`) |

Cara kirim: buka Drive → folder yang sama → tambah file. Saya akan langsung
memproses begitu ada.

## 4. Catatan teknis lain

- Rasio 1600×720 (20:9) **berbeda tipis** dari default config 1280×720 (16:9).
  Semua template tetap jalan karena cocok berbasis pola, dan semua `tap:`
  memakai fraksi. Tapi:
  - Emulator MuMu sebaiknya di-set **1600×720** agar cocok 1:1, ATAU
  - jalankan `python code.py verify --adb` setelah ganti resolusi untuk
    memastikan semua template masih ketemu.
- Beberapa tombol punya badge angka (mis. `gift_button` punya badge "62").
  Kalau badge berubah/hilang, skor bisa turun. Sudah saya crop agar bagian
  penting (ikon) dominan; kalau nanti skor < 0.75, crop ulang lebih ketat.
- `close_button` cocok di semua panel (skor ≥ 0.95 di 8 screenshot) — aman
  dipakai sebagai langkah pemulihan.

## 5. Yang bisa langsung dicoba sekarang

```powershell
python code.py template list          # 16/25 siap
python code.py --dry-run cmd "!shield"     # lihat urutan aksi tanpa sentuh emulator
python code.py verify --adb                # uji semua template di layar MuMu nyata
```

Perintah berbasis state tetap aman dan berfungsi penuh hari ini:
`!bal`, `!top`, `!members`, `!whitelist`, `!setbal`, `!sync`, `!help`, `!stats`.
