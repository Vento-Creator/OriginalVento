# -*- coding: utf-8 -*-
"""MassDM fix 1/2: xato turlarini kengaytirish (Noma'lum kamayadi)."""
SVC = r"D:\Vento_atag_timer_fixed_final\Vento_mini\massdm_system\massdm_service.py"

t = open(SVC, encoding="utf-8-sig", newline="").read()
crlf = "\r\n" in t
t = t.replace("\r\n", "\n")

anchor = 'ERROR_BLOCKED = '
i = t.find(anchor)
assert i != -1, "ERROR_BLOCKED topilmadi"
le = t.find("\n", i)
mark = t[i:le].split('"')[1].split()[0]
t = t[:le] + '\nERROR_YOU_BLOCKED = "%s Siz bloklagansiz (blokdan chiqaring)"' % mark + t[le:]
print("const OK")

pairs = [
('XXX_A_XXX', '''YYY_A_YYY'''),
]
print("PART1 CREATED")
