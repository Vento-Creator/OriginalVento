"""ML probe: gender modelini yuklab, test rasmlarda sinash."""
import os
import time

os.environ.setdefault("HF_HUB_DISABLE_TELEMETRY", "1")
os.environ.setdefault("TRANSFORMERS_NO_ADVISORY_WARNINGS", "1")

from PIL import Image
from transformers import pipeline

MODEL_ID = "rizvandwiki/gender-classification"
IMAGES = [
    "portrait_basic.jpg",
    "portrait_long_hair.jpg",
    "portrait_short_hair.jpg",
    "logo.jpg",
    "landscape.jpg",
    "cartoon.jpg",
]

t0 = time.time()
print(f"[1/2] Model yuklanmoqda: {MODEL_ID} ...", flush=True)
clf = pipeline("image-classification", model=MODEL_ID)
print(f"      yuklandi: {time.time() - t0:.1f}s", flush=True)

base = r"D:\Vento_atag_timer_fixed_final\Vento\profile_analyzer\test_images"
print("[2/2] Inferens:", flush=True)
for name in IMAGES:
    p = os.path.join(base, name)
    if not os.path.exists(p):
        print("  skip (yo'q):", name)
        continue
    try:
        img = Image.open(p).convert("RGB")
        t1 = time.time()
        res = clf(img, top_k=3)
        dt = (time.time() - t1) * 1000
        top = ", ".join(f"{r['label']}={r['score']:.2f}" for r in res)
        print(f"  {name:26s} [{dt:6.0f}ms] {top}", flush=True)
    except Exception as e:
        print(f"  {name:26s} XATO: {type(e).__name__}: {e}", flush=True)

print("TAYYOR")
