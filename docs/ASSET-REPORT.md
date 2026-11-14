# Laporan audit aset UI dan flow

Tanggal audit: 2026-11-13 · Google Drive, folder sumber `1cvS14jEMwk_5MPp_62V6yo7e7mnzH-iW` · 27 screenshot JPEG beresolusi 1600×720 (9 tanggal 13 Nov, 18 tanggal 14 Nov).

## Ringkasan hasil

- Seluruh **16 template lama** yang ada dicocokkan terhadap semua 27 screenshot. Ke-16 crop lama cocok 100% dengan crop sumber yang menjadi asalnya. Tidak ada crop lama yang perlu diganti berdasarkan bukti ini.
- Skor lintas screenshot diperiksa pada ambang 0,86. Kecocokan berulang pada tombol bottom bar, `main_profile`, dan `close_button` adalah tampilan UI yang memang berulang, bukan otomatis false positive. Template layar yang spesifik hanya muncul pada layar sumbernya; `barak_actions` cocok pada dua screenshot Barak yang hampir identik.
- Audit menemukan tiga aset baru yang dapat diverifikasi langsung: `mail_panel`, `supply_panel`, dan `supply_button`. Crop dibuat dari screenshot sumber di Drive dan disimpan di `assets/templates/`.
- Dua flow yang aktif diperbaiki: `open_mail` sekarang memeriksa profil + ikon surat dan memvalidasi panel Sistem, sedangkan `open_barak` memeriksa profil + ikon Barak sebelum tap. Ini mengganti pra-kondisi `main_hud` yang terlalu spesifik.
- **Belum ada jaminan live MuMu**: audit ini memakai screenshot statis, tidak menjalankan tap ADB di emulator.

## Inventaris crop

Crop 16 template lama (pixel pada sumber 1600×720):

| Template | Screenshot sumber | Crop `[x,y,w,h]` | Titik tap fraksi `[x,y]` |
|---|---|---:|---:|
| `main_hud` | `Screenshot_20261113_200150.jpg` | `[1200,560,380,135]` | `[0.8688,0.8716]` |
| `main_profile` | sama | `[0,0,270,115]` | `[0.0844,0.0799]` |
| `gift_button` | sama | `[862,645,80,70]` | `[0.5638,0.9444]` |
| `mail_button` | sama | `[1005,650,80,65]` | `[0.6531,0.9472]` |
| `report_button` | sama | `[1105,645,80,70]` | `[0.7156,0.9444]` |
| `settings_button` | sama | `[1205,648,78,70]` | `[0.7775,0.9486]` |
| `bag_button` | sama | `[1305,645,80,70]` | `[0.8406,0.9444]` |
| `barak_button` | sama | `[1408,640,78,75]` | `[0.9044,0.9403]` |
| `guild_tabs` | `Screenshot_20261113_200157.jpg` | `[270,235,980,78]` | `[0.4751,0.3805]` |
| `hadiah_klan_tab` | `Screenshot_20261113_200200.jpg` | `[640,210,320,60]` | `[0.5000,0.3334]` |
| `buka_button` | sama | `[1145,272,150,52]` | `[0.7625,0.4139]` |
| `misi_tabs` | `Screenshot_20261113_200222.jpg` | `[230,120,1085,55]` | `[0.4828,0.2049]` |
| `btn_selesaikan` | `Screenshot_20261113_200227.jpg` | `[1130,252,200,48]` | `[0.7688,0.3833]` |
| `peti_vip` | `Screenshot_20261113_200231.jpg` | `[430,300,145,110]` | `[0.3140,0.4931]` |
| `barak_actions` | `Screenshot_20261113_200241.jpg` | `[930,555,400,110]` | `[0.7063,0.8472]` |
| `close_button` | `Screenshot_20261113_200157.jpg` | `[1470,5,125,95]` | `[0.9577,0.0728]` |

Crop baru yang dibuat dari screenshot 14 Nov:

| Template | Screenshot sumber | Crop `[x,y,w,h]` | Hasil uji lintas 27 screenshot |
|---|---|---:|---|
| `mail_panel` | `Screenshot_20261114_085456.jpg` | `[670,85,260,60]` | 1 screenshot cocok ≥0,86; skor sumber 1,000 |
| `supply_panel` | `Screenshot_20261114_085601.jpg` | `[660,75,280,60]` | 3 screenshot Suplai cocok ≥0,86 (1,000 / 0,997 / 0,994) |
| `supply_button` | sama | `[970,603,306,76]` | 2 screenshot cocok ≥0,86; satu kondisi tombol berbeda pada screenshot ketiga |

## Hasil uji lintas-screenshot dan catatan false match

Uji menggunakan matcher template proyek (grayscale/OpenCV), semua 27 screenshot, ambang 0,86. Hasil tertinggi per template lama:

- Semua 16 template mencapai 1,000 pada salah satu screenshot sumber yang tepat.
- `main_profile` bernilai 0,882–0,909 di screenshot kota 14 Nov karena panel profil tetap muncul; ini konsisten dengan penggunaan sebagai penanda HUD.
- Ikon `mail_button`, `report_button`, `settings_button`, `bag_button`, dan `barak_button` cocok sekitar 0,98–0,997 di screenshot kota lain—memang ikon bottom bar yang sama.
- `gift_button` cocok sekitar 0,896–0,965 di screenshot kota lain; badge/keadaan ikon berubah, tetapi tetap di atas ambang.
- `close_button` cocok ≥0,948 pada banyak layar panel—perilaku yang diharapkan karena tombol X merah dipakai lintas panel. Crop-nya cocok 1,000 dengan screenshot panel yang sesuai; ketidakcocokan pada satu screenshot kota bukan bukti crop rusak.
- `barak_actions` cocok pada dua screenshot Barak 13 Nov, bukan pada layar lain.
- Template layar khusus `guild_tabs`, `hadiah_klan_tab`, `buka_button`, `misi_tabs`, `btn_selesaikan`, dan `peti_vip` tidak menunjukkan kecocokan lintas layar ≥0,86.
- **Pengecualian operasional:** `main_hud` hanya cocok 1,000 pada screenshot asal; pada screenshot kota baru terbaiknya 0,810 (di bawah threshold default 0,86). Flow yang memakai `assert: main_hud` dapat gagal pada variasi kota baru. `open_mail` dan `open_barak` kini memakai `main_profile`, yang cocok pada semua screenshot kota baru yang diuji.

Angka ini menunjukkan deteksi pola pada koleksi gambar tersebut, bukan jaminan bebas false positive untuk semua keadaan UI, resolusi, badge, animasi, atau versi game.

## Temuan UI dan flow

1. **Suplai RSS bukan panel Bank.** Screenshot `Screenshot_20261114_085601.jpg`, `085606.jpg`, dan `085616.jpg` memperlihatkan form berjudul **Suplai**, pilihan resource, jumlah, kapasitas, penerima `Yuna RSS`, serta tombol `Suplai`. `085606` memperlihatkan keypad numerik. Ini bukti alur Suplai yang berbeda dari dugaan lama “Bank klan”.
2. Screenshot Klan `Screenshot_20261113_200157.jpg` memperlihatkan tab Dewan Diplomasi, Anggota, Lamaran, dan Level Hadiah; tidak terlihat tab Bank.
3. Flow `bank_open_member`, `bank_send_one_type`, dan `bank_send_rss` tetap `enabled: false`. Koordinatnya merupakan placeholder, template `bank_panel`/`guild_menu`/`popup_ok` yang dibutuhkan belum tersedia, dan tidak boleh diaktifkan atau dipakai untuk transfer. Belum ada flow Suplai otomatis yang dibuat karena aksi keypad, batas kapasitas, pajak, penerima, konfirmasi, dan perilaku setelah menekan Suplai belum divalidasi live.
4. `open_mail` kini menggunakan `main_profile` + `mail_button`, lalu memverifikasi `mail_panel` setelah tap. `open_barak` memakai `main_profile` + `barak_button`, lalu memverifikasi `barak_actions`. Koordinat tap berasal dari pusat crop ikon di resolusi 1600×720.
5. `chat_open` dan `chat_send` juga masih aktif, tetapi koordinatnya tidak bisa dikonfirmasi dari koleksi ini karena tidak ada screenshot panel chat. Jangan anggap keduanya lolos audit visual.
6. Flow `open_guild` masih `enabled: false` karena titik buka Klan belum terukur. Flow misi/diagnostik juga tidak dinyatakan lulus live.

## Batas validasi dan langkah MuMu

Belum diuji: koneksi ADB live, tap di MuMu, variasi skala/resolusi, keberhasilan berpindah panel, OCR angka/nick, keypad jumlah, pajak/kapasitas, maupun dialog konfirmasi. Jalankan dari Windows/MuMu dengan screenshot resolusi yang sama dan periksa hasil sebelum mengaktifkan flow apa pun. Jangan menyimpulkan “tanpa kesalahan” sampai uji tersebut lolos.
