import time
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from auth import get_current_user
from db import get_pool

router = APIRouter()

DEFAULT_COMMANDS = {
    "atag": "atag",
    "stop": "stop",
    "pause": "pause",
    "resume": "resume",
}


@router.get("/")
async def get_commands(user: dict = Depends(get_current_user)):
    """Foydalanuvchining custom komandalari."""
    uid = user["id"]
    pool = await get_pool()

    rows = await pool.fetch(
        "SELECT command, message FROM utag_custom_commands WHERE user_id = $1",
        uid
    )

    prefs = await pool.fetchrow(
        """SELECT utag_atag_cmd, utag_stop_cmd, utag_pause_cmd, utag_resume_cmd
           FROM user_preferences WHERE user_id = $1""",
        uid
    )

    commands = dict(DEFAULT_COMMANDS)
    if prefs:
        commands["atag"] = prefs["utag_atag_cmd"] or "atag"
        commands["stop"] = prefs["utag_stop_cmd"] or "stop"
        commands["pause"] = prefs["utag_pause_cmd"] or "pause"
        commands["resume"] = prefs["utag_resume_cmd"] or "resume"

    for row in rows:
        commands[row["command"]] = row["message"]

    return {"commands": commands, "defaults": DEFAULT_COMMANDS}


class UpdateCommandRequest(BaseModel):
    command: str
    value: str


@router.put("/")
async def update_command(
    body: UpdateCommandRequest,
    user: dict = Depends(get_current_user)
):
    """Custom komandani yangilash."""
    uid = user["id"]
    allowed = {"atag", "stop", "pause", "resume"}
    if body.command not in allowed:
        raise HTTPException(status_code=400, detail=f"Faqat {allowed} komandalar o'zgartirilishi mumkin")

    value = body.value.strip()
    if not value or len(value) > 30:
        raise HTTPException(status_code=400, detail="Komanda 1-30 belgi bo'lishi kerak")

    col_map = {
        "atag": "utag_atag_cmd",
        "stop": "utag_stop_cmd",
        "pause": "utag_pause_cmd",
        "resume": "utag_resume_cmd",
    }
    col = col_map[body.command]

    pool = await get_pool()

    await pool.execute(
        f"""INSERT INTO user_preferences (user_id, {col})
            VALUES ($1, $2)
            ON CONFLICT(user_id) DO UPDATE SET {col} = EXCLUDED.{col}""",
        uid, value
    )

    return {"success": True, "command": body.command, "value": value}


@router.delete("/{command}")
async def reset_command(command: str, user: dict = Depends(get_current_user)):
    """Custom komandani default qiymatga qaytarish."""
    uid = user["id"]
    defaults = {"atag": "atag", "stop": "stop", "pause": "pause", "resume": "resume"}
    if command not in defaults:
        raise HTTPException(status_code=400, detail="Noto'g'ri komanda")

    col_map = {
        "atag": "utag_atag_cmd",
        "stop": "utag_stop_cmd",
        "pause": "utag_pause_cmd",
        "resume": "utag_resume_cmd",
    }
    col = col_map[command]
    default_val = defaults[command]

    pool = await get_pool()

    await pool.execute(
        f"UPDATE user_preferences SET {col} = $1 WHERE user_id = $2",
        default_val, uid
    )

    return {"success": True, "command": command, "reset_to": default_val}
