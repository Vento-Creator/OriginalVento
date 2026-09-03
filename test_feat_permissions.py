# Test: feature_settings yangi ruxsatnoma qoidalarini tekshirish (real pyrogram bilan)
import sys
import types
import asyncio

# --- config stub ---
fake_config = types.ModuleType("config")
fake_config.SUPER_ADMIN_ID = 1          # owner
fake_config.ADMIN_IDS = [1, 20, 21]     # 20, 21 — adminlar
fake_config.is_admin = lambda uid: uid in fake_config.ADMIN_IDS
sys.modules["config"] = fake_config

# --- database stub (bot_settings xotirada) ---
bot_settings_store = {}

class FakeDB:
    async def fetchrow(self, query, *args):
        key = args[0] if args else None
        if key in bot_settings_store:
            return {"key": key, "value": bot_settings_store[key]}
        return None

    async def fetch(self, query, *args):
        if "user_feature_flags" in query:
            return []
        return [{"key": k, "value": v} for k, v in bot_settings_store.items()
                if k.startswith("feature_manager_")]

    async def execute(self, query, *args):
        if len(args) >= 2:
            bot_settings_store[args[0]] = args[1]

class FakeConn:
    async def __aenter__(self):
        return FakeDB()
    async def __aexit__(self, *a):
        return False

fake_db = types.ModuleType("database")
fake_db.get_db_connection = lambda: FakeConn()
sys.modules["database"] = fake_db

sys.path.insert(0, r"d:\Vento_atag_timer_fixed_final\Vento")

OWNER = 1
ADMIN_MGR = 20      # ruxsatnomali admin
ADMIN_NOMGR = 21    # ruxsatnomasiz admin
PLAIN_USER = 999

class FakeMsg:
    def __init__(self, uid, text=""):
        self.from_user = types.SimpleNamespace(id=uid)
        self.text = text
        self.replies = []
    async def reply_text(self, text, **kw):
        self.replies.append(text)

async def main():
    import importlib
    import feature_flags as ff
    ff._tables_ready = True  # DB yaratishni o'tkazib yuborish (stub bor)
    fs = importlib.import_module("plugins.feature_settings")

    results = []
    def check(name, cond):
        results.append((name, bool(cond)))

    # 1) Owner doim boshqara oladi
    check("owner can_manage_features", await ff.can_manage_features(OWNER))

    # 2) Oddiy admin hali boshqara olmaydi (ruxsatnoma yo'q)
    check("admin w/o permission denied", not await ff.can_manage_features(ADMIN_MGR))

    # 3) Owner ruxsatnoma beradi
    ok = await ff.set_feature_manager(ADMIN_MGR, True)
    check("featmgr on saved", ok and bot_settings_store.get("feature_manager_20") == "1")
    ff._manager_cache.clear()
    check("admin w/ permission allowed", await ff.can_manage_features(ADMIN_MGR))

    # 4) Ruxsatnomasiz admin /gfeat -> 'ruxsat yo'q'
    m = FakeMsg(ADMIN_NOMGR, "/gfeat")
    await fs.global_features_command(None, m)
    check("no-perm admin /gfeat denied", any("ruxsat yo'q" in r for r in m.replies))

    # 5) Ruxsatnomali admin /gfeat -> panel ochiladi
    m2 = FakeMsg(ADMIN_MGR, "/gfeat")
    await fs.global_features_command(None, m2)
    check("perm admin /gfeat opens", len(m2.replies) == 1 and "Global" in m2.replies[0])

    # 6) Admin o'zini /feat qila olmaydi
    m3 = FakeMsg(ADMIN_MGR, f"/feat {ADMIN_MGR}")
    await fs.user_feature_command(None, m3)
    check("admin self-edit denied", any("o'zgartira olmaysiz" in r for r in m3.replies))

    # 7) Admin boshqa userga /feat qila oladi
    m4 = FakeMsg(ADMIN_MGR, f"/feat {PLAIN_USER}")
    await fs.user_feature_command(None, m4)
    check("admin edits other user", len(m4.replies) == 1 and str(PLAIN_USER) in m4.replies[0])

    # 8) Owner o'ziga ham /feat qila oladi (owner mustasno)
    m5 = FakeMsg(OWNER, f"/feat {OWNER}")
    await fs.user_feature_command(None, m5)
    check("owner self-edit allowed", len(m5.replies) == 1 and "o'zgartira olmaysiz" not in m5.replies[0])

    # 9) Ruxsatnomasiz admin /feat -> ruxsat yo'q
    m6 = FakeMsg(ADMIN_NOMGR, f"/feat {PLAIN_USER}")
    await fs.user_feature_command(None, m6)
    check("no-perm admin /feat denied", any("ruxsat yo'q" in r for r in m6.replies))


    # 10) Oddiy user '⚙️ Funksiyalar' tugmasi -> ruxsat yo'q + StopPropagation
    from pyrogram import StopPropagation
    m7 = FakeMsg(PLAIN_USER, "⚙️ Funksiyalar")
    stopped = False
    try:
        await fs.features_menu_command(None, m7)
    except StopPropagation:
        stopped = True
    check("plain user button denied+stopped", stopped and any("ruxsat yo'q" in r for r in m7.replies))

    # 11) Ruxsatnomali admin uchun tugma ishlaydi
    m8 = FakeMsg(ADMIN_MGR, "⚙️ Funksiyalar")
    stopped2 = False
    try:
        await fs.features_menu_command(None, m8)
    except StopPropagation:
        stopped2 = True
    check("perm admin button opens", stopped2 and any("Global" in r for r in m8.replies))

    # 12) /featmgr faqat owner uchun
    m9 = FakeMsg(ADMIN_MGR, "/featmgr")
    await fs.feature_manager_command(None, m9)
    check("featmgr owner-only", any("faqat" in r for r in m9.replies))

    m10 = FakeMsg(OWNER, f"/featmgr {ADMIN_NOMGR} on")
    await fs.feature_manager_command(None, m10)
    check("featmgr on by owner", bot_settings_store.get("feature_manager_21") == "1")
    ff._manager_cache.clear()
    check("nomgr admin now allowed", await ff.can_manage_features(ADMIN_NOMGR))

    m11 = FakeMsg(OWNER, f"/featmgr {ADMIN_NOMGR} off")
    await fs.feature_manager_command(None, m11)
    ff._manager_cache.clear()
    check("featmgr off works", not await ff.can_manage_features(ADMIN_NOMGR))

    # 13) User callback feat|toggle| endi mavjud emas (self-yoqish o'chirildi)
    check("self-toggle callback removed", not hasattr(fs, "feature_toggle_callback"))

    # 14) Gate bypass: faqat owner; admin flaglarga bo'ysunadi
    check("gate: owner bypass", await ff.gate_feature(FakeMsg(OWNER, "/utag"), "utag"))
    check("gate: admin allowed by default", await ff.gate_feature(FakeMsg(ADMIN_MGR, "/utag"), "utag"))
    await ff.set_global_feature("utag", False)
    ff._global_flag_cache.clear()
    check("gate: admin blocked when global off", not await ff.gate_feature(FakeMsg(ADMIN_MGR, "/utag"), "utag"))
    check("gate: owner still allowed", await ff.gate_feature(FakeMsg(OWNER, "/utag"), "utag"))
    await ff.set_global_feature("utag", True)
    ff._global_flag_cache.clear()

    failed = [n for n, ok in results if not ok]
    for n, ok in results:
        print(("PASS" if ok else "FAIL"), "-", n)
    print(f"\n{len(results) - len(failed)}/{len(results)} PASS")
    sys.exit(1 if failed else 0)

asyncio.run(main())

