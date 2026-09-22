"""Haqiqiy yuz rasmlarini yuklab olish sinovi (bir nechta manba)."""
import os
import urllib.request

MODELS = r"D:\Vento_atag_timer_fixed_final\Vento\profile_analyzer\data\models"
UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120 Safari/537.36"}

SOURCES = {
    "face_a.jpg": "https://thispersondoesnotexist.com/",
    "face_b.jpg": "https://thispersondoesnotexist.com/",
    "face_c.jpg": "https://thispersondoesnotexist.com/",
    "mona.jpg": "https://upload.wikimedia.org/wikipedia/commons/e/ec/Mona_Lisa%2C_by_Leonardo_da_Vinci%2C_from_C2RMF_retouched.jpg",
    "obama.jpg": "https://upload.wikimedia.org/wikipedia/commons/8/8d/President_Barack_Obama.jpg",
}

for name, url in SOURCES.items():
    p = os.path.join(MODELS, "_probe_" + name)
    try:
        req = urllib.request.Request(url, headers=UA)
        data = urllib.request.urlopen(req, timeout=60).read()
        open(p, "wb").write(data)
        print(f"OK   {name:12s} {len(data):>9,} bytes")
    except Exception as e:
        print(f"FAIL {name:12s} {type(e).__name__}: {e}")
print("TAYYOR")
