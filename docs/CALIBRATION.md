# Kalibrasi koordinat (sekali saja per akun/resolusi)

Bot hanya perlu **satu kali** diajari posisi tombol di layar bank klanmu.
Setelah itu semua perintah (`!food 10m`, `!transfer`, `!adminrss`, …) berjalan
otomatis.

## 1. Ambil screenshot

```powershell
python code.py record --out logs/screen.png
```

Buka `logs/screen.png` (mis. di Paint). Perhatikan resolusi di judul, misalnya
**1280×720**.

## 2. Ubah piksel → fraksi

Setiap koordinat di YAML memakai **fraksi layar** `[fx, fy]` dengan rentang 0–1:

```
fx = x_piksel / lebar      fy = y_piksel / tinggi
```

Contoh pada 1280×720:

| Elemen | Piksel | Fraksi |
|---|---|---|
| tombol Bank di menu klan | (384, 619) | `[0.300, 0.860]` |
| kolom cari member | (640, 86) | `[0.500, 0.120]` |
| hasil pencarian pertama | (640, 180) | `[0.500, 0.250]` |
| tab Food | (384, 396) | `[0.300, 0.550]` |
| kolom jumlah | (704, 446) | `[0.550, 0.620]` |
| tombol Kirim | (998, 619) | `[0.780, 0.860]` |
| tombol OK konfirmasi | (640, 360) | `[0.500, 0.500]` |

Tidak perlu presisi piksel sempurna — `flows.tap_jitter` sudah memberi toleransi
±4 px, dan tombol game cukup besar.

## 3. Isi flow

`config/flows/bank_open_member.yaml`:

```yaml
name: bank_open_member
description: buka panel bank klan dan cari nick member
enabled: true
steps:
  - tap: [0.300, 0.860]     # menu Bank
  - wait: 1.0
  - tap: [0.500, 0.120]     # kolom cari
  - wait: 0.4
  - type: "{nick}"          # diisi otomatis dari perintah
  - wait: 1.0
  - tap: [0.500, 0.250]     # hasil pertama
  - wait: 1.0
```

`config/flows/bank_send_rss.yaml`:

```yaml
name: bank_send_rss
description: kirim RSS ke member dari panel bank
enabled: true
steps:
  - tap: [0.300, 0.550]     # tab Food
  - wait: 0.6
  - tap: [0.550, 0.620]     # kolom jumlah
  - wait: 0.3
  - type: "{amount_food}"
  - wait: 0.3
  - tap: [0.780, 0.860]     # Kirim
  - wait: 1.5
  - tap: [0.500, 0.500]     # OK
  - wait: 1.0
```

### Placeholder yang tersedia

`{nick}` dan `{rss}` (JSON) dikirim oleh `ops.py`. Untuk flow multi-tipe,
tambahkan langkah per tipe dengan placeholder `{amount_food}`, `{amount_stone}`,
`{amount_wood}`, `{amount_ore}`, `{amount_gold}` — nilainya 0 bila tidak dikirim:

```yaml
  - tap: [0.300, 0.550]   # tab Food
  - type: "{amount_food}"
  - tap: [0.300, 0.620]   # tab Stone
  - type: "{amount_stone}"
  # ... lanjutkan sesuai UI-mu
```

## 4. Jenis langkah yang didukung

| Langkah | Arti |
|---|---|
| `tap: [fx, fy]` | sentuh titik (bisa piksel absolut bila angkanya > 1) |
| `tap_text: chat_input` | sentuh titik dari `ui.*` di settings.yaml |
| `wait: 1.5` | jeda detik |
| `type: "{nick}"` | ketik teks (placeholder diisi otomatis) |
| `swipe: [x1,y1,x2,y2]` | geser layar |
| `back` / `key: 4` | tombol back Android |
| `assert: bank_panel` | tunggu template `assets/templates/bank_panel.png` terlihat |
| `swipe_until: {template: x, direction: up, tries: 3}` | geser sampai elemen muncul |
| `if_template: {template: x, then: [fx,fy]}` | tap kondisional |
| `screenshot: logs/x.png` | simpan bukti layar |

## 5. Template (opsional tapi disarankan)

Template membuat bot tahan terhadap perubahan tata letak dan mencegah salah
tap. Caranya: crop gambar kecil (mis. judul "Guild Bank", ikon tab) dari
screenshot → simpan sebagai `assets/templates/bank_panel.png` (PNG, jangan
di-resize). Lalu pakai `assert: bank_panel` di flow.

Threshold default `0.86` (`templates.threshold`). Bila sering gagal padahal
elemen ada, turunkan ke `0.80`. Cek dengan:

```powershell
python -c "from lmbot.vision import TemplateMatcher; print(TemplateMatcher('assets/templates').available())"
```

## 6. Uji aman

```powershell
python code.py --dry-run cmd "!food 1m"     # lihat urutan aksi tanpa menyentuh emulator
python code.py cmd "!food 1m"               # eksekusi nyata (mulai dari nominal kecil!)
```

Dry-run mencetak setiap panggilan `run_action`/`send_rss_to_member` sehingga
kamu tahu flow mana yang akan dipakai.
