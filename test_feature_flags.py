"""
feature_flags + gate_feature testlari (stub DB/config bilan, real pyrogram).
Ishga tushirish: python test_feature_flags.py
"""
import sys
import os
import types
import time
import asyncio
import importlib.util

BASE = os.path.dirname(os.path.abspath(__file__))
VENTO = os.path.join(BASE, "Vento")
sys.path.insert(0, VENTO)

# ---------------- Stub: config ----------------
cfg = types.ModuleType("config")
cfg.is_admin = lambda uid: uid == 999
cfg.SUPER_ADMIN_ID = 999
cfg.SECOND_ADMIN_ID = 998
sys.modules["config"] = cfg

# ---------------- Stub: database ----------------
db_mod = types.ModuleType("database")
STORE_USER = {}    # (uid, feature) -> 0/1
STORE_GLOBAL = {}  # key -> "0"/"1"
QUERY_COUNT = {"n": 0}


class FakeDB:
    async def execute(self, sql, *args):
        s = " ".join(sql.split())
        if s.startswith("INSERT INTO user_feature_flags"):
            STORE_USER[(args[0], args[1])] = args[2]
        elif s.startswith("INSERT INTO bot_settings"):
            STORE_GLOBAL[args[0]] = args[1]

    async def fetchrow(self, sql, *args):
        QUERY_COUNT["n"] += 1
        s = " ".join(sql.split())
        if "FROM user_feature_flags" in s:
            en = STORE_USER.get((args[0], args[1]))
            return {"enabled": en} if en is not None else None
        if "FROM bot_settings" in s:
            val = STORE_GLOBAL.get(args[0])
            return {"value": val} if val is not None else None
        return None

    async def fetch(self, sql, *args):
        QUERY_COUNT["n"] += 1
        s = " ".join(sql.split())
        if "FROM user_feature_flags" in s:
            uid = args[0]
            return [{"feature": f, "enabled": v} for (u, f), v in STORE_USER.items() if u == uid]
        if "FROM bot_settings" in s:
            return [{"key": k, "value": v} for k, v in STORE_GLOBAL.items()]
        return []


class FakeCM:
    async def __aenter__(self):
        return FakeDB()

    async def __aexit__(self, *a):
        return False


def get_db_connection():
    return FakeCM()


db_mod.get_db_connection = get_db_connection
db_mod.get_violation_count = lambda *a, **k: asyncio.sleep(0, result=0)
sys.modules["database"] = db_mod

# ---------------- feature_flags import ----------------
import feature_flags as ff  # noqa: E402

# ---------------- Fake eventlar ----------------
class FakeUser:
    def __init__(self, uid):
        self.id = uid


class FakeMessage:
    def __init__(self, uid):
        self.from_user = FakeUser(uid)
        self.replies = []

    async def reply_text(self, text, **kwargs):
        self.replies.append(text)
        return self


class FakeCallback:
    def __init__(self, uid):
        self.from_user = FakeUser(uid)
        self.answers = []

    async def answer(self, text=None, show_alert=False):
        self.answers.append(text)


# isinstance tekshiruvlari ishlashi uchun haqiqiy sinflarni almashtiramiz
ff.Message = FakeMessage
ff.CallbackQuery = FakeCallback

PASS, FAIL = [], []


def check(name, cond, extra=""):
    (PASS if cond else FAIL).append(name)
    print(f"  {'✅ PASS' if cond else '❌ FAIL'} — {name} {extra}")


async def run_tests():
    print("=== feature_flags testlari ===\n")

    # T1: default — hech qanday yozuv yo'q, hamma funksiya yoqilgan
    msg = FakeMessage(100)
    r = await ff.gate_feature(msg, "utag")
    check("T1 default: yozuv yo'q → ruxsat", r is True and len(msg.replies) == 0)

    # T2: user uchun o'chirilsa → 'siz uchun ochirilgan' xabari
    await ff.set_user_feature(100, "utag", False)
    msg2 = FakeMessage(100)
    r = await ff.gate_feature(msg2, "utag")
    ok = r is False and len(msg2.replies) == 1 and "siz uchun o'chirilgan" in msg2.replies[0]
    check("T2 user off: bloklandi + xabar", ok, f"| replies={msg2.replies}")

    # T3: global o'chirilsa → 'administrator tomonidan cheklangan'
    await ff.set_user_feature(100, "utag", True)
    await ff.set_global_feature("utag", False)
    msg3 = FakeMessage(100)
    r = await ff.gate_feature(msg3, "utag")
    ok = r is False and len(msg3.replies) == 1 and "administrator tomonidan cheklangan" in msg3.replies[0]
    check("T3 global off: bloklandi + xabar", ok)

    # T4: admin bypass
    await ff.set_user_feature(999, "utag", False)
    adm = FakeMessage(999)
    r = await ff.gate_feature(adm, "utag")
    check("T4 admin bypass: o'chirilgan bo'lsa ham ruxsat", r is True and len(adm.replies) == 0)
    await ff.set_global_feature("utag", True)

    # T5: flood — 30s da 3 ogohlantirish, 4-chidan jim
    ff._reset_state_for_tests()
    await ff.set_user_feature(200, "massdm", False)
    replies = 0
    for i in range(6):
        m = FakeMessage(200)
        await ff.gate_feature(m, "massdm")
        replies += len(m.replies)
    check("T5 flood: 3 ta xabar, keyin jim (6 urinish)", replies == 3, f"| replies={replies}")

    # T6: mute tugagach yana ogohlantiradi
    ff._flood_state[200]["muted_until"] = time.time() - 1
    m = FakeMessage(200)
    await ff.gate_feature(m, "massdm")
    check("T6 mute tugadi: yana javob beradi", len(m.replies) == 1)

    # T7: 30s oyna reset
    ff._reset_state_for_tests()
    await ff.set_user_feature(300, "chat", False)
    for i in range(4):
        ff._flood_check(300)
    st = ff._flood_state[300]
    st["muted_until"] = 0.0                          # mute ni bekor qilamiz
    st["window_start"] = time.time() - 31            # oyna eskirdi
    v = ff._flood_check(300)
    check("T7 window reset: eskirgan oyna = yana 'warn'", v == "warn")

    # T8: kesh — TTL ichida takroriy DB so'rov yo'q
    ff._reset_state_for_tests()
    QUERY_COUNT["n"] = 0
    await ff.get_user_flag(400, "memory")
    await ff.get_user_flag(400, "memory")
    await ff.get_user_flag(400, "memory")
    check("T8 kesh: 3 o'qishda 1 DB so'rov", QUERY_COUNT["n"] == 1, f"| queries={QUERY_COUNT['n']}")

    # T9: get_user_features xaritasi
    await ff.set_user_feature(400, "chat", False)
    flags = await ff.get_user_features(400)
    ok = flags["chat"] is False and flags["utag"] is True and set(flags) == set(ff.FEATURES)
    check("T9 get_user_features: chat=False, qolganlari True", ok)

    # T10: global features xaritasi
    await ff.set_global_feature("memory", False)
    g = await ff.get_global_features()
    ok = g["memory"] is False and g["utag"] is True
    check("T10 get_global_features: memory=False", ok)

    # T11: CallbackQuery yo'li — answer orqali ogohlantirish
    ff._reset_state_for_tests()
    await ff.set_user_feature(500, "memory", False)
    cb = FakeCallback(500)
    r = await ff.gate_feature(cb, "memory")
    ok = r is False and len(cb.answers) == 1
    check("T11 callback: show_alert ogohlantirish", ok)

    # T12: security whitelist feat| ni qabul qiladi
    spec = importlib.util.spec_from_file_location(
        "security_test", os.path.join(VENTO, "plugins", "security.py"))
    sec = importlib.util.module_from_spec(spec)
    try:
        spec.loader.exec_module(sec)
        ok = sec.is_valid_callback_data("feat|toggle|utag") and sec.is_valid_callback_data("feat|global|memory")
        check("T12 security whitelist: 'feat|...' valid", ok)
    except Exception as e:
        check("T12 security whitelist: 'feat|...' valid", False, f"({e})")

    # T13: noma'lum feature → ruxsat (xavfsiz default)
    m = FakeMessage(600)
    r = await ff.gate_feature(m, "unknown_feature")
    check("T13 noma'lum feature: gate True", r is True)

    print(f"\n{'='*40}\nNatija: {len(PASS)} PASS, {len(FAIL)} FAIL")
    return len(FAIL) == 0


if __name__ == "__main__":
    ok = asyncio.run(run_tests())
    sys.exit(0 if ok else 1)
