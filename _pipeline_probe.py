"""To'liq ML pipeline sinovi: yuz aniqlash + kesish + gender klassifikatsiya."""
import os
import time

import cv2
import numpy as np
from PIL import Image
from transformers import pipeline

MODELS = r"D:\Vento_atag_timer_fixed_final\Vento\profile_analyzer\data\models"
PB = os.path.join(MODELS, "opencv_face_detector_uint8.pb")
PBTXT = os.path.join(MODELS, "opencv_face_detector.pbtxt")
TEST_IMAGES = r"D:\Vento_atag_timer_fixed_final\Vento\profile_analyzer\test_images"

CASES = [
    ("obama.jpg (erkak)", os.path.join(MODELS, "_probe_obama.jpg")),
    ("mona.jpg (ayol)", os.path.join(MODELS, "_probe_mona.jpg")),
    ("logo.jpg (yuzsiz)", os.path.join(TEST_IMAGES, "logo.jpg")),
]

print("[1] Modellar yuklanmoqda...", flush=True)
net = cv2.dnn.readNet(PB, PBTXT)
clf = pipeline("image-classification", model="rizvandwiki/gender-classification")
print("    tayyor", flush=True)


def detect_faces(img, conf=0.5):
    h, w = img.shape[:2]
    blob = cv2.dnn.blobFromImage(img, 1.0, (300, 300), [104, 117, 123], swapRB=False, crop=False)
    net.setInput(blob)
    det = net.forward()
    faces = []
    for i in range(det.shape[2]):
        c = float(det[0, 0, i, 2])
        if c < conf:
            continue
        x1 = int(det[0, 0, i, 3] * w); y1 = int(det[0, 0, i, 4] * h)
        x2 = int(det[0, 0, i, 5] * w); y2 = int(det[0, 0, i, 6] * h)
        faces.append((max(0, x1), max(0, y1), max(0, x2), max(0, y2), c))
    return sorted(faces, key=lambda f: -f[4])


def classify_crop(img, face, pad=0.25):
    x1, y1, x2, y2, c = face
    px = int((x2 - x1) * pad); py = int((y2 - y1) * pad)
    H, W = img.shape[:2]
    crop = img[max(0, y1 - py):min(H, y2 + py), max(0, x1 - px):min(W, x2 + px)]
    if crop.size == 0:
        return None
    rgb = cv2.cvtColor(crop, cv2.COLOR_BGR2RGB)
    return clf(Image.fromarray(rgb), top_k=2)


print("[2] Pipeline natijalari:", flush=True)
for label, path in CASES:
    if not os.path.exists(path):
        print(f"  {label:22s} fayl yo'q")
        continue
    img = cv2.imread(path)
    if img is None:
        print(f"  {label:22s} o'qilmadi")
        continue
    if max(img.shape[:2]) > 1600:
        sc = 1600 / max(img.shape[:2])
        img = cv2.resize(img, None, fx=sc, fy=sc)
    t0 = time.time()
    faces = detect_faces(img)
    t_det = (time.time() - t0) * 1000
    if not faces:
        print(f"  {label:22s} yuz topilmadi -> signal 0 ({t_det:.0f}ms)")
        continue
    t0 = time.time()
    res = classify_crop(img, faces[0])
    t_cls = (time.time() - t0) * 1000
    top = ", ".join(f"{r['label']}={r['score']:.3f}" for r in res)
    print(f"  {label:22s} yuzlar={len(faces)} conf={faces[0][4]:.2f} | {top} | det {t_det:.0f}ms + cls {t_cls:.0f}ms")

print("TAYYOR")
