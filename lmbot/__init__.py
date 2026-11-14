"""LMBot — kerangka bot Guild Bank Lord Mobile.

Bot ini TIDAK memodifikasi game, tidak melakukan injection, dan tidak
membaca memori proses. Ia bekerja persis seperti manusia: melihat layar
(screenshot via ADB), memahami tampilan (template matching), lalu menyentuh
layar (tap/swipe via ADB). Semua aksi dijalankan lewat MuMu Player yang
terpasang di Windows dan diakses dari terminal (RDP/SSH/PowerShell).
"""

__version__ = "1.1.0"
__author__ = "Egandika"
__all__ = ["__version__", "__author__"]
