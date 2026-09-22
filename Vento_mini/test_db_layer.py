"""Vento_mini DB qatlamining funksional testi (vaqtinchalik baza bilan)."""

import asyncio
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import config  # noqa: E402

RESULTS = []


def check(name: str, ok: bool, extra: str = ""):
    RESULTS.append((name, ok, extra))
    print(f"{'PASS' if ok else 'FAIL'} | {name}" + (f" | {extra}" if extra else ""))


async def main():
    tmpdir = tempfile.mkdtemp()
    tmpdb = os.path.join(tmpdir, "test_vento_mini.db")
    config.DB_PATH = tmpdb

    import database as dbm

    # --- 1) Eski sxemani qo'lda yaratamiz (PRIMARY KEY (user_id, group_id)) ---
    import aiosqlite
    async with aiosqlite.connect(tmpdb) as db:
        await db.execute("""
            CREATE TABLE scraped_members (
                user_id INTEGER,
                username TEXT,
                first_name TEXT,
                group_id TEXT,
                PRIMARY KEY (user_id, group_id)
            )
        """)
        for uid, uname in [(111, "scraper_a"), (222, "scraper_b"), (333, None)]:
            await db.execute(
                "INSERT INTO scraped_members VALUES (?, ?, '', 'G1')", (uid, uname)
            )
        await db.commit()

    # --- init_db migratsiyasi ishga tushadi ---
    await dbm.init_db()

    async with aiosqlite.connect(tmpdb) as db:
        async with db.execute("SELECT COUNT(*) FROM scraped_members WHERE group_id='G1'") as c:
            n = (await c.fetchone())[0]
        async with db.execute("PRAGMA table_info(scraped_members)") as c:
            cols = [r[1] for r in await c.fetchall()]
    check("migratsiya: eski 3 ta user saqlandi", n == 3, f"count={n}")
    check("migratsiya: 'id' ustuni bor", "id" in cols, f"cols={cols}")

    # --- 2) 100 ta manual username -> 100 qator ---
    gid = "G1"
    for i in range(1, 101):
        await dbm.add_manual_member(gid, f"user_{i:03d}")
    total = await dbm.get_group_member_count(gid)
    check("100 ta manual username bazaga tushdi", total == 103, f"total={total}")

    # --- 3) Dedup ---
    added_again = await dbm.add_manual_member(gid, "user_050")
    check("duplikat username qabul qilinmaydi", added_again is False)
    added_case = await dbm.add_manual_member(gid, "USER_050")
    print(f"INFO | case-sensitive dedup: USER_050 qoshildi={added_case}")

    # --- 4) Scraper batch dedup ---
    batch = [(111, "scraper_a", "A", gid), (444, "scraper_d", "D", gid)]
    await dbm.add_scraped_members_batch(batch)
    total2 = await dbm.get_group_member_count(gid)
    check("scraper batch: dup qoshilmadi, yangi qoshildi",
          total2 == 104, f"total={total2}")

    await test_pagination_and_delete(dbm, gid)


async def test_pagination_and_delete(dbm, gid):
    # --- 5) Sahifalash tartibi ---
    page1 = await dbm.get_members_by_group_paginated(gid, 0, 50)
    check("sahifa 1: 50 ta qaytardi", len(page1) == 50, f"got={len(page1)}")
    first = page1[0]
    check("tartib: birinchi user scraper_a",
          first["username"] == "scraper_a", f"first={first['username']}")

    page3 = await dbm.get_members_by_group_paginated(gid, 100, 50)
    check("oxirgi sahifa: 4 ta qoldiq", len(page3) == 4, f"got={len(page3)}")
    last = page3[-1]
    check("oxirgi user oxirgi qoshilgan (scraper_d)",
          last["username"] == "scraper_d", f"last={last['username']}")

    # --- 6) Tartib raqam boyicha olish ---
    m3 = await dbm.get_member_by_index(gid, 3)
    check("3-tartib = usernamesiz scraper useri (333)",
          m3 is not None and m3["username"] is None and m3["user_id"] == 333,
          f"got={m3}")
    m4 = await dbm.get_member_by_index(gid, 4)
    check("4-tartib = user_001", m4 and m4["username"] == "user_001", f"got={m4 and m4['username']}")
    m104 = await dbm.get_member_by_index(gid, 104)
    check("104-tartib = scraper_d", m104 and m104["username"] == "scraper_d",
          f"got={m104 and m104['username']}")
    m1 = await dbm.get_member_by_index(gid, 1)
    m0 = await dbm.get_member_by_index(gid, 0)
    check("0-tartib xavfsiz (1-ga teng)", m0 and m0["id"] == m1["id"])

    # --- 7) Usernamesiz user ham ochadi (row_id boyicha) ---
    deleted = await dbm.delete_scraped_member_by_row_id(gid, m3["id"])
    total_after = await dbm.get_group_member_count(gid)
    check("usernamesiz user ochirildi", deleted == 1 and total_after == 103,
          f"deleted={deleted}, total={total_after}")

    m3_new = await dbm.get_member_by_index(gid, 3)
    check("ochirilgach tartib qayta hisoblanadi (3 = user_001)",
          m3_new and m3_new["username"] == "user_001", f"got={m3_new and m3_new['username']}")

    # --- Qoshimcha: baza izolyatsiyasi ---
    await dbm.add_manual_member("G2", "user_050")
    g1 = await dbm.get_group_member_count("G1")
    g2 = await dbm.get_group_member_count("G2")
    check("baza izolyatsiyasi", g2 == 1 and g1 == 103, f"G1={g1}, G2={g2}")

    failed = [r for r in RESULTS if not r[1]]
    print("\n" + "=" * 50)
    print(f"JAMI: {len(RESULTS)} | PASS: {len(RESULTS) - len(failed)} | FAIL: {len(failed)}")
    if failed:
        for name, _, extra in failed:
            print(f"  FAIL: {name} {extra}")
        sys.exit(1)
    print("BARCHA TESTLAR OTDI OK")


if __name__ == "__main__":
    asyncio.run(main())