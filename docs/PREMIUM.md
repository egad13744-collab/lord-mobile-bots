# Panduan Premium Plan LMBot

**Dibuat oleh Egandika** · Bahasa: Indonesia · Target: Windows via RDP + MuMu Player

Panduan ini untuk fitur operasional baru di branch upgrade. Fitur tambahan tidak
mengubah nama/token perintah inti yang sudah ada. Fitur game tetap dibatasi
ADB/flow yang dikalibrasi; bot tidak melakukan bypass anti-cheat.

> **Penting:** “Premium plan” di sini berarti peningkatan engineering lokal
> (audit, antrean, jadwal, kontrol akses, backup, metrik), bukan klaim bahwa
> bot sudah siap mengelola akun/game tanpa kalibrasi. MuMu dan akun game tidak
> tersedia di lingkungan pengujian ini. Jangan aktifkan flow berisiko sebelum
> diuji `--dry-run`, screenshot, lalu pada akun uji.

## 1. Pasang / cek instalasi

Ikuti [tutorial salin-tempel](TUTORIAL-CODEPASTE.md) dari awal. Sesudah instalasi,
jalankan dari root repository:

```powershell
python code.py doctor --fix
python code.py --dry-run serve --once "!help OPS" "!audit verify" "!queue"
```

`doctor --fix` membuat folder runtime yang hilang dan hanya menyimpan perubahan
konfigurasi otomatis bila memang perlu; file sebelum perubahan disimpan sebagai
`config/settings.yaml.bak`. Perintah game nyata tidak dijalankan oleh contoh
`--dry-run`.

## 2. Perintah tambahan

| Perintah | Kegunaan | Akses |
|---|---|---|
| `!queue` | Lihat antrean dan posisi job | semua rank yang dapat memakai bot |
| `!jobs` | Riwayat job terbaru | R4+ |
| `!cancel <id>` | Batalkan job antrean | R4+ |
| `!retry <id>` | Masukkan job gagal kembali ke antrean | R4+ |
| `!cron list` | Lihat jadwal | R5+ |
| `!cron add "0 2 * * *" !top food` | Jadwalkan perintah aman setiap hari pukul 02.00 | R5+ |
| `!cron del <id>` | Hapus jadwal | R5+ |
| `!quota` | Lihat pemakaian RSS hari ini | semua rank yang dapat memakai bot |
| `!audit verify` | Verifikasi hash chain transaksi | R4+ |
| `!audit log` | Lihat transaksi terakhir | R4+ |
| `!undo` | Balikkan transaksi mutabel terakhir | R5+ |
| `!backup` | Buat backup bank + audit saat ini | R4+ |

Penjadwal/antrian hanya aktif pada proses `serve` normal (bukan `cmd` atau
`serve --once`). `queue.always: false` mempertahankan eksekusi langsung pada
keadaan normal; permintaan masuk antrean bila perangkat sedang dipakai alur
lain. Atur `queue.always: true` jika semua pengiriman harus melewati antrean.
Job yang berstatus `running` saat proses mati dikembalikan ke antrean saat
restart. Satu worker menjalankan job; antrean persisten memakai JSON lokal.

`cron` hanya menerima ekspresi 5-field dan daftar perintah query/status yang
diizinkan (`bal`, `top`, `quota`, `audit verify|log`, `queue`, `jobs`, `version`,
`help`). Perintah lain ditolak; tidak ada transfer/aksi game terjadwal. Jadwal berjalan memakai zona waktu lokal komputer RDP;
pastikan jam Windows benar. Hanya jadwalkan perintah yang memang sudah
terkalibrasi dan dapat berjalan otomatis.

### Batas harian

Di `config/settings.yaml`, isi:

```yaml
safety:
  daily_limit_per_type: 50000000  # batas Food/Stone/Wood/Ore/Gold masing-masing
  daily_limit_all_types: 0        # 0 = tidak membatasi total gabungan
```

`0` berarti tanpa batas untuk opsi terkait. Pemakaian dihitung dari catatan debit yang bertanda pengiriman
(transfer/donate/RSS) pada audit log berdasarkan tanggal lokal. `!quota` memperlihatkan sisa batas
per tipe. Jika file audit lama dimulai sebelum hash-chain diterapkan, data lama
masih dapat dipakai menghitung kuota tetapi belum seluruhnya dilindungi hash.

## 3. Undo, audit, dan backup

Setiap transaksi baru diberi ID, `prev_hash` dan hash SHA-256 yang mencakup
identitas transaksi serta saldo sebelum/sesudah. `!audit verify` melaporkan
baris pertama yang tidak cocok. Hash chain **mendeteksi** perubahan; ia bukan
backup, bukan tanda tangan digital dengan kunci rahasia, dan tidak mencegah
pemilik mesin mengganti seluruh file sekaligus.

`!undo` hanya membalik credit/debit ledger lokal terakhir yang belum dibalik.
Transfer/donasi/RSS, refund, dan `setbal` yang mungkin telah memengaruhi game
sengaja ditolak: mengubah saldo JSON tidak bisa mengembalikan RSS di dalam game.
Undo menulis entri baru (tidak menghapus histori). Jalankan `!audit verify` sesudah
operasi penting. Backup manual:

```text
!backup
```

Backup disimpan di `state/backups/`; jumlah rotasi default tujuh. Backup otomatis
terjadi tiap `backup.every_commands` perintah yang ditangani (`50` secara
default). Simpan salinan tambahan di media offline yang dikelola operator;
backup pada disk yang sama tidak melindungi dari kerusakan disk.

## 4. OCR angka offline

OCR ini hanya membaca **digit** dengan template lokal, bukan mengenali seluruh
teks atau nama anggota. Ia belum menggantikan rekonsiliasi manual tas bank.
Tidak ada gambar yang diunggah ke layanan pihak ketiga.

1. Siapkan screenshot mentah dengan baris digit `0123456789` dalam font UI yang
   sama, tanpa label/pemisah di dalam kotak. Bot sendiri akan crop dari screenshot.
2. Jalankan (box adalah `x,y,w,h`, fraksi layar 0..1 atau piksel):

```powershell
python code.py ocr train --screen "logs/screen.png" --box "0.20,0.35,0.60,0.12"
python code.py ocr read --screen "logs/screen.png" --box "0.30,0.40,0.25,0.08"
```

Template digit tersimpan pada `assets/ocr/`. Bentuk glyph dan kontras harus
mirip dengan screenshot yang dibaca. Periksa teks dan confidence sebelum
menggunakannya untuk keputusan saldo. OCR **belum** terhubung otomatis ke
`!adminbag`, `!sync`, atau keputusan transaksi; hasilnya masih perlu diperiksa
operator. `!chat` juga belum menjadi OCR chat penuh.

## 5. Alias, balasan custom, dan bahasa

`config/commands.yaml` sudah berisi contoh alias dan perintah statis:

- `!b` → `!bal`
- `!aturan`, `!cara`, `!donate_info` → balasan dari YAML

Ubah file YAML tersebut, lalu restart proses `serve`. Perintah custom hanya
membalas teks, tidak menjalankan aksi game. Periksa rank minimum dan isi balasan
sebelum dipakai di klan.

`ui.lang: id|en` memilih katalog terjemahan. Katalog ID/EN sudah tersedia untuk
pesan operasional baru dan sebagian pesan inti; **belum semua** respons lama
diterjemahkan dan Bahasa Indonesia tetap fallback.

## 6. Dashboard, webhook, dan akses web

Dashboard berisi ringkasan bank; webhook HTTP sekarang memakai lapisan
keamanan yang sama. Endpoint:

- `GET /` — dashboard
- `GET /api/status` — status lebih lengkap (viewer+)
- `GET /api/health` — liveness (viewer+)
- `GET /metrics` — Prometheus text format (viewer+)
- `POST /` — perintah (admin+)
- `POST /api/confirm` — menyelesaikan konfirmasi perintah berisiko

Gunakan token di header `X-Bot-Token` atau `Authorization: Bearer ...`; token
pada URL sengaja tidak didukung agar tidak bocor ke access log. Contoh konfigurasi:

```yaml
web:
  enabled: true
  host: 0.0.0.0
  port: 8081
  roles:
    owner: "GANTI-DENGAN-TOKEN-OWNER-PANJANG"
    admin: "GANTI-DENGAN-TOKEN-ADMIN-PANJANG"
    viewer: "GANTI-DENGAN-TOKEN-VIEWER-PANJANG"
  identities:
    owner: arken_ega
    admin: nick_admin_yang_sudah_whitelist
  rate_limit_per_minute: 60
  access_log: logs/access.jsonl
```

Token role mengikat `sender` ke nick pada `web.identities` (owner default dapat
menggunakan `bot.owner_nick`). Admin/viewer harus mempunyai identity sesuai
role untuk menjalankan aksi; viewer tidak dapat POST. Token adalah rahasia:
jangan unggah `settings.yaml`, gunakan firewall LAN, dan pasang reverse proxy
TLS bila akses melewati jaringan tidak tepercaya. Server bawaan tidak
menyediakan HTTPS. Jika `web.roles` kosong, token lama `web.token` masih dapat
dipakai sebagai akses owner; tanpa token, akses loopback saja.

Perintah berisiko melalui API menghasilkan `202` dan `nonce`; kirim kembali
**text, sender, dan nonce yang sama** ke `/api/confirm`. Nonce sekali pakai,
terikat alamat IP/role, dan kedaluwarsa setelah dua menit. Rate limit per IP dan
`logs/access.jsonl` berlaku di dashboard/webhook. Jangan letakkan port ini
langsung ke internet.

Prometheus bisa scrape `http://<host>:8081/metrics` menggunakan header token
viewer. Endpoint tidak mengirim data keluar sendiri.

## 7. Profil MuMu / multi-instance

Contoh `config/settings.yaml`:

```yaml
device:
  profiles:
    emu1:
      serial: "127.0.0.1:16384"
      width: 1280
      height: 720
    emu2:
      serial: "127.0.0.1:16416"
      width: 1280
      height: 720
```

Pilih instance saat menjalankan bot:

```powershell
python code.py --instance emu1 serve
python code.py --instance emu2 serve
```

Data saldo, antrean, dan jadwal dipisahkan ke `state/<nama>/`. Gunakan
**satu proses serve per emulator** dan port ADB yang benar. MuMu mungkin
menggunakan resolusi/port berbeda menurut versi dan konfigurasi instance;
verifikasi dengan `adb devices` dan `doctor` sebelum menyalakan bot kedua.

## 8. Status nyata / yang belum termasuk

Upgrade ini menambah fondasi operasional, tetapi sejumlah fitur komersial belum
termasuk: OCR teks/chat penuh; rekonsiliasi saldo otomatis dengan layar; cloud
HA/replication; panel web dengan tombol UI untuk semua aksi; notifikasi multi-
channel; penemuan koordinat template otomatis (perintah `template auto` hanya
batch crop berdasarkan manifest box); pengelolaan key/secret eksternal; dan
jaminan operasi tanpa pengawasan.

Di repository saat audit masih ada flow yang sengaja `enabled: false` dan
beberapa template game yang belum tersedia. Template/flow harus dikalibrasi
untuk resolusi MuMu milik pengguna. Untuk menguji crop batch dari screenshot
mentah, isi `config/template_boxes.yaml`, lalu jalankan:

```powershell
python code.py template auto --screen "logs/screen.png" --manifest "config/template_boxes.yaml" --preview
```

Jangan menyimpulkan aksi game berhasil hanya dari balasan bot; cek layar,
audit log, dan saldo di game. Fitur anti-cheat bypass, injeksi memori, dan cloud
sync saldo sengaja tidak dibuat.
