# Test: say_admin_filter mantiqini tekshirish (real pyrogram bilan)
import sys
import types
import asyncio

# config modulini stub qilib qo'yamiz (real config.json kerak emas)
fake_config = types.ModuleType("config")
fake_config.ADMIN_IDS = [111, 222]  # bot adminlar
fake_config.DEBUG_MODE = False
fake_config.is_admin = lambda uid: uid in fake_config.ADMIN_IDS
sys.modules["config"] = fake_config

sys.path.insert(0, r"d:\Vento_atag_timer_fixed_final\Vento")

from pyrogram.enums import ChatMemberStatus


class FakeChat:
    def __init__(self, chat_id):
        self.id = chat_id


class FakeUser:
    def __init__(self, uid):
        self.id = uid


class FakeMessage:
    def __init__(self, chat_id, user_id=None, sender_chat=None):
        self.chat = FakeChat(chat_id)
        self.from_user = FakeUser(user_id) if user_id else None
        self.sender_chat = FakeChat(sender_chat) if sender_chat else None


class FakeMember:
    def __init__(self, status):
        self.status = status


class FakeClient:
    def __init__(self, status):
        self.status = status

    async def get_chat_member(self, chat_id, user_id):
        return FakeMember(self.status)


async def main():
    import importlib
    say = importlib.import_module("plugins.say")

    CHAT = -1001234567890
    results = []

    # 1) Oddiy a'zo -> RAD ETILISHI KERAK
    r = await say.say_admin_filter(FakeClient(ChatMemberStatus.MEMBER), None, FakeMessage(CHAT, user_id=999))
    results.append(("oddiy a'zo (member)", r, False))

    # 2) Guruh administratori -> RUXSAT
    r = await say.say_admin_filter(FakeClient(ChatMemberStatus.ADMINISTRATOR), None, FakeMessage(CHAT, user_id=777))
    results.append(("guruh administratori", r, True))

    # 3) Guruh owner -> RUXSAT
    r = await say.say_admin_filter(FakeClient(ChatMemberStatus.OWNER), None, FakeMessage(CHAT, user_id=888))
    results.append(("guruh owner", r, True))

    # 4) Bot admin -> RUXSAT (get_chat_member chaqirilmasligi kerak)
    r = await say.say_admin_filter(FakeClient(ChatMemberStatus.MEMBER), None, FakeMessage(CHAT, user_id=111))
    results.append(("bot admin (is_admin)", r, True))

    # 5) Anonim admin (GroupAnonymousBot) -> RUXSAT
    r = await say.say_admin_filter(FakeClient(ChatMemberStatus.MEMBER), None, FakeMessage(CHAT, user_id=1087968824))
    results.append(("anonim admin (1087968824)", r, True))

    # 6) from_user yo'q (kanal posti) -> RAD
    r = await say.say_admin_filter(FakeClient(ChatMemberStatus.MEMBER), None, FakeMessage(CHAT))
    results.append(("from_user yo'q", r, False))

    # 7) from_user yo'q lekin sender_chat = guruhning o'zi -> RUXSAT
    r = await say.say_admin_filter(FakeClient(ChatMemberStatus.MEMBER), None, FakeMessage(CHAT, sender_chat=CHAT))
    results.append(("sender_chat == chat (anonim admin)", r, True))

    # 8) get_chat_member xato bersa (user guruhda yo'q) -> RAD
    class ErrClient:
        async def get_chat_member(self, chat_id, user_id):
            raise Exception("USER_NOT_PARTICIPANT")
    r = await say.say_admin_filter(ErrClient(), None, FakeMessage(CHAT, user_id=555))
    results.append(("get_chat_member xato", r, False))

    print()
    print("=" * 60)
    all_ok = True
    for name, got, expected in results:
        ok = got == expected
        all_ok = all_ok and ok
        print(f"{'PASS' if ok else 'FAIL'} | {name:38s} | got={got} expected={expected}")
    print("=" * 60)
    print("ALL PASS" if all_ok else "SOME FAILED")

    # 9) Kesh testi: bir xil user uchun 2-marta API chaqirilmasligi kerak
    calls = {"n": 0}
    class CountClient:
        async def get_chat_member(self, chat_id, user_id):
            calls["n"] += 1
            return FakeMember(ChatMemberStatus.MEMBER)
    m = FakeMessage(CHAT, user_id=444)
    await say.say_admin_filter(CountClient(), None, m)
    await say.say_admin_filter(CountClient(), None, m)
    ok = calls["n"] == 1
    print(f"{'PASS' if ok else 'FAIL'} | kesh: 2 marta tekshiruvda 1 ta API so'rovi (calls={calls['n']})")

    # 10) Registratsiya: pyrogram class-decorator handler'ni func.handlers ga saqlaydi
    handlers = getattr(say.say_command_handler, "handlers", [])
    print(f"say handler ro'yxatdan o'tgan: {len(handlers)} ta")
    if handlers:
        mh, _grp = handlers[0]
        print(f"handler filters: {mh.filters}")
        ok_reg = "say_admin_only" in str(mh.filters)
        print(f"{'PASS' if ok_reg else 'FAIL'} | handler filterida say_admin_only bor")

asyncio.run(main())
