# Referensi perintah

> LMBot — **Dibuat oleh Egandika**

Format umum: `!kode parameter...`
Jumlah: `100m` (juta), `1.5k` (ribu), `2b` (miliar), atau angka polos `250000`.
Nick tidak peka huruf besar/kecil, spasi, atau underscore: `Arken Ega` = `arken_ega`.

## Rank

| Rank | Arti |
|---|---|
| R1 | member baru: cek saldo, kirim RSS milik sendiri, cari tambang |
| R2–R3 | member aktif: buildspam, hunt, gyphon |
| R4 | officer: pindahkan bank, shield, jeda, abort, title, blacklist |
| R5 | leader: whitelist, setbal, adminrss, migrate |
| R6 | owner (hanya via file state): melewati semua batas rank |

Rank bawaan member baru: `R1` (lihat `safety.whitelist_enforced`).

## Contoh lengkap

```text
!bal                            saldo saya
!food 10m                       kirim 10 juta food ke saya
!rss 5m 5m 0 0 0                kirim 5m food + 5m stone
!transfer budi ore 1m           pindahkan 1m ore milik saya ke budi
!donate food budi 500k          donasi 500k food untuk budi
!adminrss 1m 0 0 0 0 budi       kirim 1m food ke budi dari bank (R5)
!setbal budi gold 5m            set saldo budi (R5)
!stop 3600                      jeda bank 1 jam (R4)
!abort                          batalkan semua pengiriman (R4)
!relocate 123 456               pindah bank (R4)
!findtile food 4 chat           cari tambang food lvl 4, kirim ke chat
!findmonster blackwing 2 chat   cari monster
!whitelist budi R3              daftarkan budi (R5)
!blacklist penipu               tolak nick (R4)
```

## Perilaku penting

- **Debit → kirim → refund**: saldo dipotong dulu, RSS dikirim di game; bila
  langkah game gagal, saldo otomatis dikembalikan dan bot melapor gagal.
- **Transfer ke member lain** juga menambah saldo target (mencerminkan RSS yang
  benar-benar diterima di game).
- **Bank dijeda** (`!stop`, `!abort`) menolak semua pengiriman sampai waktu
  habis atau `python code.py bank unfreeze`.
- **Rate limit**: maksimal `bot.max_commands_per_minute` (default 20) per menit
  per bot untuk mencegah spam.
- **Batas aman**: `safety.max_rss_per_transfer` (default 300M per tipe).
