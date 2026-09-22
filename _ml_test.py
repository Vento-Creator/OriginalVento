"""ML modul sinovi: matn modellari + yuz + gender."""
import os
import sys

sys.path.insert(0, r"D:\Vento_atag_timer_fixed_final\Vento")

from profile_analyzer.ml import TextGenderModel, FaceDetector, GenderClassifier, assets_status

print("=== 1. ASSETS HOLATI ===")
for k, v in assets_status().items():
    print(f"  {k}: {v}")

print("\n=== 2. ISM MODELI ===")
name_model = TextGenderModel("name")
print("  manba:", name_model.source if name_model.ensure_ready() else "FAIL", "| tayyor:", name_model.available)
for n in ["Madina", "Gulnora", "Nilufar", "Sevinch", "Bekzod", "Ali", "Ravshan", "Jasur", "John", "Olga"]:
    p = name_model.predict_female_prob(n)
    verdict = "AYOL" if p >= 0.6 else "erkak?"
    print(f"  {n:14s} female_prob={p:.3f}  -> {verdict}")

print("\n=== 3. BIO MODELI ===")
bio_model = TextGenderModel("bio")
print("  manba:", bio_model.source if bio_model.ensure_ready() else "FAIL", "| tayyor:", bio_model.available)
tests = [
    "qiz", "men qizman, onam bilan yashayman", "девушка из Ташкента", "she/her 💁",
    "yigit, dasturchi", "reklama xizmati", "Работа, услуги", "kanal uchun admin",
]
for b in tests:
    p = bio_model.predict_female_prob(b)
    verdict = "AYOL" if p >= 0.6 else "erkak/neutral"
    print(f"  {b[:32]:34s} female_prob={p:.3f}  -> {verdict}")

print("\n=== 4. YUZ DETEKTORI ===")
fd = FaceDetector()
print("  method:", fd.method, "| available:", fd.available)

print("\n=== 5. GENDER MODELI (yuklash, ~40s) ===")
gc = GenderClassifier()
print("  yuklash:", gc.warmup(), "| vaqt:", f"{gc.last_load_seconds:.1f}s")

print("\n=== 6. TO'LIQ PIPELINE ===")
import cv2
MODELS = r"D:\Vento_atag_timer_fixed_final\Vento\profile_analyzer\data\models"
for label, path in [
    ("obama (erkak)", os.path.join(MODELS, "_probe_obama.jpg")),
    ("mona (ayol)", os.path.join(MODELS, "_probe_mona.jpg")),
]:
    if not os.path.exists(path):
        print(f"  {label}: fayl yo'q")
        continue
    img = cv2.imread(path)
    if max(img.shape[:2]) > 1600:
        sc = 1600 / max(img.shape[:2])
        img = cv2.resize(img, None, fx=sc, fy=sc)
    faces = fd.detect(img)
    if not faces:
        print(f"  {label}: yuz yo'q")
        continue
    H, W = img.shape[:2]
    box = faces[0].expand(W, H, 0.25)
    crop = img[box.y1:box.y2, box.x1:box.x2]
    res = gc.classify_face(crop)
    print(f"  {label}: yuz conf={faces[0].confidence:.2f} | female_prob={res['female_prob']:.3f} -> {res['label']}")

print("\nTAYYOR")
