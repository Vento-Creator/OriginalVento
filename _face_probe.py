"""Face detection probe: DNN res10 + Haar, test rasmlarda."""
import os
import time
import urllib.request

import cv2
import numpy as np

BASE = r"D:\Vento_atag_timer_fixed_final\Vento\profile_analyzer\test_images"
MODELS = r"D:\Vento_atag_timer_fixed_final\Vento\profile_analyzer\data\models"
os.makedirs(MODELS, exist_ok=True)

PB = os.path.join(MODELS, "opencv_face_detector_uint8.pb")
PBTXT = os.path.join(MODELS, "opencv_face_detector.pbtxt")


def _dl(url, path):
    if os.path.exists(path) and os.path.getsize(path) > 1000:
        return
    urllib.request.urlretrieve(url, path)


_dl("https://github.com/spmallick/learnopencv/raw/master/AgeGender/opencv_face_detector_uint8.pb", PB)
_dl("https://raw.githubusercontent.com/spmallick/learnopencv/master/AgeGender/opencv_face_detector.pbtxt", PBTXT)
print("DNN model tayyor:", os.path.getsize(PB), "bytes")

net = cv2.dnn.readNet(PB, PBTXT)
haar_face = cv2.CascadeClassifier(cv2.data.haarcascades + "haarcascade_frontalface_default.xml")
haar_profile = cv2.CascadeClassifier(cv2.data.haarcascades + "haarcascade_profileface.xml")

IMAGES = sorted(f for f in os.listdir(BASE) if f.lower().endswith((".jpg", ".jpeg", ".png")))


def dnn_faces(img, conf=0.5):
    h, w = img.shape[:2]
    blob = cv2.dnn.blobFromImage(img, 1.0, (300, 300), [104, 117, 123], swapRB=False, crop=False)
    net.setInput(blob)
    det = net.forward()
    out = []
    for i in range(det.shape[2]):
        c = float(det[0, 0, i, 2])
        if c < conf:
            continue
        x1 = int(det[0, 0, i, 3] * w); y1 = int(det[0, 0, i, 4] * h)
        x2 = int(det[0, 0, i, 5] * w); y2 = int(det[0, 0, i, 6] * h)
        out.append((max(0, x1), max(0, y1), max(0, x2), max(0, y2), c))
    return out


def haar_faces(img, conf=5):
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    gray = cv2.equalizeHist(gray)
    res = list(haar_face.detectMultiScale(gray, 1.1, conf, minSize=(24, 24)))
    res += list(haar_profile.detectMultiScale(gray, 1.1, conf, minSize=(24, 24)))
    return [(int(x), int(y), int(x + w), int(y + h), 1.0) for (x, y, w, h) in res]


print("-" * 78)
for name in IMAGES:
    p = os.path.join(BASE, name)
    img = cv2.imread(p)
    if img is None:
        print(f"{name:26s} o'qilmadi")
        continue
    t0 = time.time()
    d = dnn_faces(img)
    t_dnn = (time.time() - t0) * 1000
    t0 = time.time()
    hr = haar_faces(img)
    t_haar = (time.time() - t0) * 1000
    print(f"{name:26s} {img.shape[1]}x{img.shape[0]} | DNN: {len(d)} ({t_dnn:5.0f}ms) | Haar: {len(hr)} ({t_haar:5.0f}ms)")

print("TAYYOR")
