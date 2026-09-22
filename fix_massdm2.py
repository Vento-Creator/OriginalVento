# -*- coding: utf-8 -*-
"""MassDM fix 2/2: copy_message birlamchi + wizard bot peer."""
import re

SVC = r"D:\Vento_atag_timer_fixed_final\Vento_mini\massdm_system\massdm_service.py"
PLG = r"D:\Vento_atag_timer_fixed_final\Vento_mini\plugins\massdm.py"

def load(p):
    t = open(p, encoding="utf-8-sig", newline="").read()
    return ("\r\n" in t), t.replace("\r\n", "\n")

def save(p, t, crlf):
    if crlf:
        t = t.replace("\n", "\r\n")
    open(p, "w", encoding="utf-8", newline="").write(t)

NEW_SEND_ONE = """            async def _send_one():
                # 1-urinish: copy_message - forward sarlavhasi
                # ("quyidagidan uzatildi") chiqmaydi, premium emoji/format
                # server tomonidan 100% saqlanadi.
                if from_chat_id and source_msg_id:
                    try:
                        return await cli.copy_message(
                            chat_id=dest,
                            from_chat_id=from_chat_id,
                            message_id=source_msg_id,
                        )
                    except (FloodWait, PeerFlood, UserPrivacyRestricted,
                            UserIsBlocked, UserDeactivated, PeerIdInvalid,
                            ChatWriteForbidden) as dest_err:
                        # Manzilga oid xato - fallback ham xuddi shunday
                        # yiqiladi, to'g'ridan-to'g'ri yuqoriga beramiz.
                        raise dest_err
                    except Exception as copy_err:
                        logger.info(
                            f"MassDM: Slot {slot} copy_message ishlamadi "
                            f"({dest}): {copy_err}. send_message bilan uriniladi."
                        )
                        # Manba bilan bog'liq muammo - pastda send_message'ga o'tamiz.
                if msg_entities:
                    try:
                        return await cli.send_message(
                            dest, text_message,
                            entities=msg_entities, parse_mode=None,
                        )
                    except Exception as ent_err:
                        ent_blob = f"{type(ent_err).__name__} {ent_err}".lower()
                        entity_like = any(
                            kw in ent_blob
                            for kw in ["entity", "custom_emoji", "premium_emoji",
                                       "parse", "markdown", "html", "message_empty"]
                        )
                        if not entity_like:
                            raise ent_err
                        logger.info(
                            f"MassDM: Slot {slot} entity xatosi "
                            f"({dest}): {ent_err}. Oddiy matn bilan uriniladi."
                        )
                # Oddiy yuborish (entities yo'q yoki entity xatolik berdi)
                return await cli.send_message(dest, text_message)"""

crlf, t = load(SVC)

old_comment = """            # Premium (custom) emoji saqlanishi uchun: entities bor bo'lsa,
            # parse_mode=None + entities bilan yuboramiz. Shunda premium
            # emoji oddiy holga tushib qolmaydi."""
new_comment = """            # Premium (custom) emoji saqlanishi uchun copy_message birlamchi
            # yo'l (forward sarlavhasiz). Entities - faqat fallback uchun."""
assert t.count(old_comment) == 1, "comment miss: %d" % t.count(old_comment)
t = t.replace(old_comment, new_comment)
print("comment OK")

pat = re.compile(r"            async def _send_one\(\):.*?return await cli\.send_message\(dest, text_message\)", re.S)
assert len(pat.findall(t)) == 1, "send_one count=%d" % len(pat.findall(t))
t = pat.sub(lambda m: NEW_SEND_ONE, t)
print("send_one OK")
save(SVC, t, crlf)

crlf2, p = load(PLG)
old_w = """    entities_keep = _serialize_entities(getattr(message, "entities", None), trim_offset=ltrim)
    massdm_states[user_id] = {"""
new_w = """    entities_keep = _serialize_entities(getattr(message, "entities", None), trim_offset=ltrim)
    # copy_message user-akkountdan bajariladi - from_chat botning o'zi
    # (user ko'rinishidagi peer) bo'lishi shart.
    try:
        _me = await client.get_me()
        _bot_peer = _me.id
    except Exception:
        _bot_peer = message.chat.id
    massdm_states[user_id] = {"""
assert p.count(old_w) == 1, "wizard miss: %d" % p.count(old_w)
p = p.replace(old_w, new_w)
print("wizard OK")
old_f = '"from_chat_id": message.chat.id,'
assert p.count(old_f) == 1, "from_chat miss: %d" % p.count(old_f)
p = p.replace(old_f, '"from_chat_id": _bot_peer,')
print("from_chat OK")
save(PLG, p, crlf2)
print("FIX2 DONE")
