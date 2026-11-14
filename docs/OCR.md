# OCR angka dan pembacaan chat

## Yang tersedia di LMBot 1.1.0

`lmbot/ocr.py` menyediakan OCR **digit saja** secara offline, memakai template
lokal. Latih dari screenshot mentah dengan baris `0123456789` yang bentuk
font/ukurannya serupa:

```powershell
python code.py ocr train --screen "logs/screen.png" --box "0.20,0.35,0.60,0.12"
python code.py ocr read --screen "logs/screen.png" --box "0.30,0.40,0.25,0.08"
```

Kotak dapat berupa fraksi layar atau piksel. Hasil OCR belum terhubung ke
rekonsiliasi otomatis `!adminbag`/`!sync`, dan bukan OCR teks/nick. Verifikasi
confidence dan hasil pada screenshot sendiri; informasi detail ada di
[PREMIUM.md](PREMIUM.md).

## Membaca chat game (belum terintegrasi)

Mode `--source chat` membuat bot **mendengar chat in-game** seperti bot asli:
menunggu `[R4] !food 10m` dari member, lalu membalas di chat. Ini butuh OCR
teks di layar. **OCR digit di atas bukan OCR chat**, sehingga sumber chat
in-game belum aktif hanya dengan melatih template digit.

Mode `--source chat` membuat bot **mendengar chat in-game** seperti bot asli:
menunggu `[R4] !food 10m` dari member, lalu membalas di chat. Ini butuh OCR
karena teks chat adalah piksel di layar.

Bot tetap **100% berfungsi tanpa OCR** — pakai mode `terminal`, `file`, atau
`http` (lihat README). OCR hanya menambah kenyamanan.

## Kenapa tidak aktif secara default

- OCR Indonesia + nick campuran (huruf besar/kecil, `_`) rawan salah baca.
- Tiap frame chat perlu screenshot → CPU naik (~5–10% di 720p).
- Tanpa verifikasi pengirim yang akurat, bot bisa salah percaya nick palsu.

Karena itu desainnya: verifikasi tetap di `roster` (whitelist + rank) sehingga
kesalahan OCR tidak otomatis memberi akses.

## Opsi A — Windows OCR (tanpa dependensi berat)

PowerShell bisa memakai API `Windows.Media.Ocr`:

```powershell
# simpan sebagai scripts/ocr.ps1
param([string]$Path)
Add-Type -AssemblyName System.Runtime.WindowsRuntime
$null = [Windows.Media.Ocr.OcrEngine, Windows.Foundation, ContentType = WindowsRuntime]
$null = [Windows.Graphics.Imaging.BitmapDecoder, Windows.Foundation, ContentType = WindowsRuntime]
$null = [Windows.Storage.StorageFile, Windows.Foundation, ContentType = WindowsRuntime]

$asTask = ([System.WindowsRuntimeSystemExtensions].GetMethods() | Where-Object {
    $_.Name -eq 'AsTask' -and $_.GetParameters().Count -eq 1 -and
    $_.GetParameters()[0].ParameterType.Name -eq 'IAsyncOperation`1' })[0]

function Await($op, $type) {
    $task = $asTask.MakeGenericMethod($type).Invoke($null, @($op))
    $task.Wait(-1) | Out-Null
    $task.Result
}

$file     = Await ([Windows.Storage.StorageFile]::GetFileFromPathAsync($Path)) ([Windows.Storage.StorageFile])
$stream   = Await ($file.OpenAsync([Windows.Storage.FileAccessMode]::Read)) ([Windows.Storage.Streams.IRandomAccessStream])
$decoder  = Await ([Windows.Graphics.Imaging.BitmapDecoder]::CreateAsync($stream)) ([Windows.Graphics.Imaging.BitmapDecoder])
$bitmap   = Await ($decoder.GetSoftwareBitmapAsync()) ([Windows.Graphics.Imaging.SoftwareBitmap])
$engine   = [Windows.Media.Ocr.OcrEngine]::TryCreateFromUserProfileLanguages()
$result   = Await ($engine.RecognizeAsync($bitmap)) ([Windows.Media.Ocr.OcrResult])
$result.Lines | ForEach-Object { $_.Text }
```

Lalu isi `lmbot/ops.py` → `AdbOps.read_chat`:

1. `shot = self.driver.screenshot()` lalu `shot.save("logs/chat.png")`.
2. Potong area chat (fraksi di `ui.chat_area`, tambahkan ke settings).
3. Jalankan `powershell -File scripts/ocr.ps1 -Path logs/chat.png`.
4. Parse baris `[R4] nick: !perintah` → `ChatLine(sender=..., text=...)`.

## Opsi B — Tesseract

```powershell
winget install UB-Mannheim.TesseractOCR
pip install pytesseract pillow
```

```python
import pytesseract
from PIL import Image

def read_chat_ocr(path="logs/chat.png"):
    text = pytesseract.image_to_string(Image.open(path), lang="eng", config="--psm 6")
    return text.splitlines()
```

`pytesseract` tidak menambah beban ke inti bot — tetap opsional.

## Opsi C — Modul bridge Discord/WhatsApp

Alih-alih OCR, hubungkan sumber perintah dari platform chat yang sudah punya
API (Discord bot, Telegram bot). Ini umum dipakai komunitas bank klan karena
lebih andal dan bisa dipakai dari HP:

```python
# contoh kerangka, butuh token bot kamu sendiri
from lmbot.bot import Bot

def on_message(msg):
    if not msg.content.startswith("!"):
        return
    reply = bot.handle_line(msg.content, sender=msg.author.display_name)
    await msg.reply(reply.message)
```

---

## Format baris chat yang diharapkan

```
[R4] arken_ega: !food 10m
[R4] !transfer budi ore 1m
```

Parser sudah membuang prefix `[R4]` (lihat `ui.msg_prefix`) dan tanda `!`.
Nick pengirim harus ada di whitelist agar perintah dieksekusi.

## Uji parser tanpa OCR

```powershell
python code.py --dry-run serve --once "[R4] arken_ega: !shield"
```
