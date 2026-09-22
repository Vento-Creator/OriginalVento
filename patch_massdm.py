import sys
p = r"D:\Vento_atag_timer_fixed_final\Vento_mini\plugins\massdm.py"
t = open(p, encoding="utf-8").read()
old = '    massdm_states[user_id] = {\n        "state": "CONFIRM",\n        "group_id": state_info["group_id"],\n        "message": message_text,\n    }\n    raise ContinuePropagation'
assert t.count(old) == 1, t.count(old)
new = (
    '    ents = None\n'
    '    try:\n'
    '        me = getattr(message, "entities", None)\n'
    '        if me:\n'
    '            ents = [e.write() for e in me]\n'
    '    except Exception:\n'
    '        ents = None\n'
    '    massdm_states[user_id] = {\n'
    '        "state": "CONFIRM",\n'
    '        "group_id": state_info["group_id"],\n'
    '        "message": message_text,\n'
    '        "entities": ents,\n'
    '        "from_chat_id": message.chat.id,\n'
    '        "source_msg_id": message.id,\n'
    '    }\n'
    '    raise ContinuePropagation'
)
t = t.replace(old, new)
open(p, "w", encoding="utf-8").write(t)
print("patched handler")
