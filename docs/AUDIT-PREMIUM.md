# Audit LMBot dibandingkan bot guild-bank premium

**Dibuat oleh Egandika** · Audit kode per 13 November 2026 · basis awal `c2e12a3`

“Bot premium” komersial bukan satu standar tunggal dan banyak implementasinya
tertutup. Karena itu perbandingan ini memakai checklist kapabilitas lazim
(antrian, audit, akses, pemulihan, dashboard, jadwal), bukan klaim meniru produk
tertentu atau jaminan setara SLA komersial.

## Ringkasan

Repo sudah mempunyai parser perintah, RBAC R1–R6, alur ADB/flow, ledger JSON,
refund transaksi tertentu, dashboard dasar, dan 95 test baseline. Upgrade ini
menambah regresi terotomasi menjadi 112 test. Audit awal menemukan job tidak
persisten, tidak ada cron, audit tanpa rantai hash,
backup/metrics terbatas, dashboard tanpa role/rate limit, tidak ada dukungan
multi-instance dan OCR belum aktif.

Branch upgrade menambahkan queue/worker, cron, hash-chain + undo + backup,
kuota harian, digit OCR offline, watchdog, doctor fix, role/rate limit web,
access log, health/metrics, alias/custom command, katalog ID/EN, dan profil
perangkat. **Persentase tunggal sengaja tidak dipakai:** bobot “premium” tidak
terstandar, dan fitur kalibrasi/integrasi game masih bergantung screenshot serta
MuMu pengguna.

## Checklist pembanding

| Kapabilitas yang biasa dicari | Kondisi awal | Hasil upgrade | Batas/pekerjaan tersisa |
|---|---|---|---|
| Daftar perintah inti dan level rank | ✅ | ✅ dipertahankan | Beberapa handler game memang stub/bergantung flow |
| Serialisasi aksi game (hindari tap bersamaan) | ✅ `DEVICE_LOCK` | ✅ queue worker tunggal | Job normal tetap langsung kecuali perangkat sibuk / `queue.always` |
| Job queue, prioritas, status, recovery restart | ❌ | ✅ `lmbot/tasks.py`, `!queue/jobs/cancel/retry` | JSON lokal, satu worker per proses; bukan distributed queue |
| Jadwal berulang | ❌ | ✅ cron 5-field, `!cron` | Zona waktu lokal; aksi berisiko ditolak; jadwal wajib diuji |
| Buku besar append-only & deteksi edit | 🟡 JSONL tanpa integritas | ✅ SHA-256 chain, `!audit verify` | File lama sebelum upgrade belum punya hash; bukan signature/keyed tamper-proof |
| Rollback transaksi | ❌ | ✅ `!undo` append-only | Hanya mutasi terakhir yang belum di-undo; tidak dapat memilih ID historis |
| Snapshot & rotasi backup | ❌ | ✅ `!backup`, backup periodik | Backup di disk lokal; perlu salinan offsite/offline operator |
| Limit transfer dan kuota harian | 🟡 per transfer | ✅ `daily_limit_*`, `!quota` | Kuota dihitung dari debit audit berdasarkan tanggal lokal |
| OCR angka dari screenshot | ❌ stub | 🟡 OCR digit template offline + CLI | Perlu sample/font cocok; tidak membaca teks/nick; belum wired ke `!adminbag`/`!sync` |
| Auto-recovery perangkat | 🟡 retry driver | 🟡 watchdog + reconnect + doctor fix | Tidak menjamin emulator/game pulih dari semua popup/crash |
| Dashboard/status & monitoring | 🟡 | ✅ `/api/health`, `/api/status`, `/metrics` | Tidak ada UI tombol lengkap, HTTPS bawaan, atau Prometheus alert rules |
| Token/role dan perlindungan endpoint | 🟡 satu token | ✅ owner/admin/viewer, identitas per role, rate limit IP | Role token perlu konfigurasi; gunakan TLS reverse proxy untuk jaringan luar |
| Konfirmasi API untuk aksi berisiko | 🟡 hanya beberapa aksi di handler | ✅ dua langkah nonce di web API | API caller wajib mengimplementasikan POST `/api/confirm`; bukan tombol UI |
| Riwayat akses | ❌ | ✅ `logs/access.jsonl` | Rotasi/retensi log perlu dipantau operator |
| Multi emulator/profil | ❌ | ✅ `--instance`, state per profil | Harus satu proses per instance; belum ada koordinasi antar-proses |
| Alias/perintah teks admin | ❌ | ✅ `config/commands.yaml` | Custom command hanya balasan statis |
| Bahasa | 🟡 dominan Indonesia | 🟡 katalog ID/EN | Belum semua pesan lama diterjemahkan |
| Kalibrasi template massal | 🟡 crop manual satu-satu | 🟡 `template auto` batch dari manifest box | Tidak mendeteksi tombol/koordinat otomatis; box harus dikalibrasi |
| Cloud HA/sync/backup terkelola | ❌ | ❌ sengaja di luar cakupan | Hindari menyebarkan saldo/identitas klan ke pihak ketiga |
| Operasi live tanpa kalibrasi | ❌ | ❌ | 49 flow, 5 aktif pada audit; template game belum lengkap; perlu uji MuMu |

## Temuan audit konkret

1. **Flow dan template:** pada audit awal 49 flow tersedia, hanya 5 yang aktif;
   aset template 16/25 dan beberapa template inti belum ada. Koordinat harus
   sesuai screenshot/resolusi emulator aktual. Jangan mengaktifkan flow hanya
   karena proses Python berjalan.
2. **Handler belum lengkap:** beberapa perintah (`quest`, `snowbeast`, `members`,
   `adminbag`, `adminbal`, `sync`, `migrate`) memiliki implementasi parsial/stub
   atau memerlukan flow yang belum dikalibrasi. Queue/cron tidak membuat
   kemampuan game yang belum ada menjadi tersedia.
3. **OCR:** sekarang hanya pembaca digit terlatih lokal. Belum dapat membaca
   seluruh UI, chat, nama, inventaris, atau melakukan rekonsiliasi saldo otomatis.
4. **Keamanan web:** pakai token acak per role, ikat role ke `web.identities`,
   simpan file config dengan izin terbatas, dan batasi port di firewall. Server
   standar adalah HTTP, bukan HTTPS. Jangan expose langsung ke Internet.
5. **Hash audit:** hash chain berguna mendeteksi edit/penghapusan baris; tanpa
   secret key dan backup terpisah, administrator mesin dapat mengganti semua
   artefak. Transaksi lama yang belum punya kolom hash tidak bisa divalidasi
   terhadap perubahan historis.
6. **Multi-instance:** profil memisahkan state; bukan multi-master. Jangan
   menjalankan dua proses dengan profil/state sama karena file JSON tidak
   mengunci lintas proses.
7. **Validasi live:** seluruh test memakai mock/perangkat simulasi. Tidak ada
   klaim bahwa transfer benar-benar berhasil di Lords Mobile tanpa uji pada
   instance MuMu dan akun uji.

## Upgrade yang ditambahkan

- `lmbot/tasks.py`: job persisten, prioritas rank, retry/cancel, recovery job
  `running` setelah restart dan worker tunggal.
- `lmbot/schedule.py`: parser cron 5 field, penyimpanan jadwal dan scheduler;
  menolak aksi yang ditandai berisiko.
- `lmbot/ledger.py` + `lmbot/state.py`: ID, saldo sebelum/sesudah, hash chain,
  validasi, undo append-only, backup rotasi, hitung kuota.
- `lmbot/ocr.py` + `lmbot/vision.py`: segmentasi kolom dan pencocokan template
  digit; `code.py ocr train|read`.
- `lmbot/guard.py`: watchdog ADB, reconnect best-effort, `doctor --fix`, cek
  disk/rotasi helper.
- `lmbot/web.py` + `lmbot/chat.py`: token role, identitas pengirim, rate limit
  per IP, audit access log, endpoint health/metrics, konfirmasi nonce.
- `lmbot/custom.py` + `config/commands.yaml`: alias dan balasan kustom YAML.
- `lmbot/i18n.py`: katalog ID/EN untuk string yang sudah di-wire.
- `lmbot/config.py` + `lmbot/cli.py`: default operasional dan profil `--instance`.
- `config/template_boxes.yaml`: manifest batch crop; bukan computer vision auto-
  calibration.

Panduan penggunaan dan batasan lengkap: [PREMIUM.md](PREMIUM.md).

## Fitur sengaja tidak dibuat

- Bypass anti-cheat, inject/injeksi memori, atau manipulasi klien game.
- Cloud sync saldo/identitas anggota tanpa persetujuan dan kebijakan privasi.
- Auto-payment/top-up.
- Klaim bahwa OCR digit saja cukup untuk auto-rekonsiliasi atau auto-kirim.

**Kesimpulan:** upgrade menyediakan lapisan operasional yang lebih matang,
tetapi belum menjadikan semua flow game aktif atau menggantikan kalibrasi,
monitoring, backup eksternal, dan verifikasi manual operator.
