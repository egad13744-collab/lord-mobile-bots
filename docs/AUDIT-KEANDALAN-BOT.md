# Audit ulang risiko dan keandalan bot

Tanggal: 2026-11-13 · Audit kode statis, tidak menjalankan akun atau emulator.

## Batas audit

Saya tidak membantu menyamarkan bot, meniru manusia untuk mengelabui anti-cheat, atau menjanjikan bot “99% tidak terdeteksi”. Randomisasi koordinat/waktu bukan jaminan dan justru dapat merusak akurasi. Bagian ini mengaudit keandalan, keselamatan transfer, kontrol akses, dan risiko salah aksi. Perubahan kali ini hanya membetulkan klaim dokumentasi jitter; perilaku bot tidak dibuat lebih tersembunyi.

## Temuan prioritas

| Prioritas | Temuan | Bukti di kode | Dampak / tindak aman |
|---|---|---|---|
| Tinggi | Aksi non-idempoten berpotensi terulang setelah kegagalan parsial. | `lmbot/ops.py` mengulang seluruh flow sampai `flows.max_retries + 1` kali; default 1 retry. Flow transfer memiliki urutan tap/ketik/tap sehingga kegagalan setelah tap kirim bisa terjadi setelah efek game sudah terjadi. | Transfer Bank saat ini `enabled: false`, tetapi jangan mengaktifkan flow transfer placeholder. Untuk flow transaksi kelak, matikan retry otomatis dan minta verifikasi manual sebelum mencoba ulang. |
| Tinggi | Job yang sedang berjalan dimasukkan kembali ke antrean setelah restart. | `TaskQueue.load()` mengubah `status: running` menjadi `queued`. | Jika proses mati setelah aksi game diterima tetapi sebelum hasil tersimpan, job bisa dieksekusi ulang. Tandai hasilnya “tidak diketahui/perlu rekonsiliasi” alih-alih auto-run ulang untuk aksi berkonsekuensi. |
| Tinggi | Assertion template yang hilang dianggap sukses. | `FlowRunner._assert_template()` mengembalikan `True` bila template belum tersedia (mode kalibrasi). | Flow dapat terus melakukan tap tanpa pemeriksaan layar yang diminta. Jangan aktifkan flow yang bergantung pada template hilang; idealnya mode produksi membuat assertion penting gagal tertutup, sedangkan mode kalibrasi harus eksplisit. |
| Sedang | `wait_stable` bisa memberi indikasi stabil yang lemah dan hasil gagal diabaikan. | `wait_for_frame()` membandingkan hanya byte awal PNG + panjang, lalu `_run_step()` tidak memeriksa nilai boolean. | Perubahan pada bagian lain layar bisa terlewat, atau flow lanjut ketika layar belum stabil. Perlu hash/analisis frame penuh dan kebijakan timeout yang eksplisit sebelum mengandalkannya. |
| Sedang | Batas perintah adalah satu limiter global, bukan per pengirim. | `Bot` membuat satu `RateLimiter` dan memakainya untuk semua sender. | Satu pengirim yang banyak mengirim perintah dapat menghabiskan jatah pengirim lain. Ini masalah fairness/availability; pertimbangkan limiter terpisah per identitas plus batas global. |
| Sedang | Flow memakai koordinat tetap dan beberapa belum punya bukti gambar. | `chat_open`/`chat_send` aktif tetapi screenshot chat tidak ada; banyak flow lain masih berisi titik placeholder `[0.50, 0.50]`; aset memakai 1600×720 sedangkan konfigurasi contoh perangkat 1280×720. | Risiko salah tekan atau mengetik ke kontrol yang salah. Hanya jalankan flow yang telah dikalibrasi pada resolusi MuMu aktual dan diverifikasi lewat screenshot; flow placeholder tetap nonaktif. |
| Sedang | Jitter ±4 px bukan perilaku manusia dan dapat mengurangi akurasi. | `jitter_point()` menambahkan offset acak seragam pada kedua sumbu; jeda langkah flow umumnya tetap/didefinisikan tetap. | Tidak memberi jaminan anti-deteksi; pada kontrol kecil/tepi tombol, tap dapat keluar dari target. Kode dan dokumentasi kini tidak lagi menyebutnya fitur anti-deteksi. |

## Yang sudah lebih aman / batas bukti

- Whitelist, otorisasi rank, batas transfer, antrean serial, dan limiter tersedia sebagai kontrol aplikasi; semuanya tetap perlu dikonfigurasi benar. Batas ini tidak membuat otomatisasi diizinkan oleh aturan game.
- Aksi transfer yang terlihat di screenshot adalah form **Suplai**, tetapi flow transfer belum tervalidasi live dan template Bank penting belum ada. Biarkan flow `bank_*` nonaktif.
- Audit screenshot sebelumnya menguji 27 gambar dan 19/28 template tersedia. Itu bukan pengujian ADB, deteksi game, atau jaminan terhadap perubahan UI.
- Tidak ada bukti yang bisa mengukur peluang “99% aman” atau “99% tidak terdeteksi”; klaim persentase seperti itu tidak berdasar dari repo/screenshot ini.

## Prioritas perbaikan aman berikutnya

1. Ubah pemulihan antrean agar job yang sempat `running` memerlukan rekonsiliasi operator sebelum bisa diulang.
2. Tambahkan kebijakan retry khusus flow: tidak ada retry otomatis untuk aksi yang bisa mengirim resource, memakai item, memindahkan akun, atau melakukan pembelian.
3. Sediakan assertion wajib untuk flow produksi dan mode kalibrasi terpisah; jangan melewati guard kritis secara diam-diam.
4. Perbaiki `wait_stable` untuk membandingkan frame penuh dan menghentikan flow dengan error jika stabilitas tidak tercapai.
5. Tambahkan limiter per sender di samping limiter global, lalu uji akses dan fairness.
6. Lengkapi screenshot MuMu untuk chat, Suplai sebelum/sesudah konfirmasi, dialog kesalahan, dan kondisi jaringan putus. Uji hanya tindakan yang diizinkan dan dengan akun/lingkungan yang dapat dipulihkan.

Tidak ada tes anti-cheat atau live emulator yang dijalankan dalam audit ini.
