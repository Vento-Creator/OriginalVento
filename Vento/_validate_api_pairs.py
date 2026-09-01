"""Validate API_ID/API_HASH pairs by connecting to Telegram (no code is sent).

Checks that each pair is accepted by Telegram. A fresh/invalid/restricted
api_id will fail here with ApiIdInvalid / AuthKeyUnregistered / etc.
Usage: python _validate_api_pairs.py
"""
import asyncio
import os
import sys

PAIRS = [
    ("primary", int(os.getenv("API_ID", "0")), os.getenv("API_HASH", "")),
    ("extra_2", int(os.getenv("API_ID_2", "0")), os.getenv("API_HASH_2", "")),
    ("extra_3", int(os.getenv("API_ID_3", "0")), os.getenv("API_HASH_3", "")),
]


async def validate(label: str, api_id: int, api_hash: str) -> bool:
    from pyrogram import Client
    from pyrogram.errors import ApiIdInvalid, ApiIdPublishedFlood
    from pyrogram.raw.functions.help import GetConfig
    if not api_id or not api_hash:
        print(f"[{label}] SKIP: bo'sh")
        return False
    try:
        app = Client(
            f":memory:{label}",
            api_id=api_id,
            api_hash=api_hash,
            in_memory=True,
        )
        await app.connect()
        # GetConfig confirms Telegram accepts this api_id pair
        cfg = await app.invoke(GetConfig())
        dc = cfg.this_dc
        await app.disconnect()
        print(f"[{label}] OK: api_id={api_id} accepted (DC{dc})")
        return True
    except ApiIdInvalid:
        print(f"[{label}] FAIL: api_id={api_id} — API_ID/API_HASH mos emas yoki noto'g'ri")
    except ApiIdPublishedFlood:
        print(f"[{label}] FAIL: api_id={api_id} — Telegram bu API_ID ni public joyda e'lon qilingan deb bloklagan")
    except Exception as e:
        print(f"[{label}] FAIL: api_id={api_id} — {type(e).__name__}: {e}")
    return False


async def main():
    results = []
    for label, aid, ahash in PAIRS:
        results.append((label, await validate(label, aid, ahash)))
    print()
    for label, ok in results:
        print(f"  {label}: {'VALID' if ok else 'INVALID/SKIP'}")
    if not any(ok for _, ok in results):
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
