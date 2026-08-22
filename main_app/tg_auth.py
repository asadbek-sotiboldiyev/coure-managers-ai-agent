from typing import Dict, Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from pyrogram.client import Client
from pyrogram.errors import (
    PhoneNumberInvalid,
    PhoneCodeInvalid,
    PhoneCodeExpired,
    SessionPasswordNeeded,
    PasswordHashInvalid,
)

from shared.config import tg_config
from shared.db import get_connection
from shared.local_db import upsert_assistant_tg_info
from shared.logger import get_logger

logger = get_logger(__name__)

# APIRouter ob'ektini yaratamiz
router = APIRouter(prefix="/telegram/assistant", tags=["Assistant Telegram Auth"])

# Active sessions cache
active_login_sessions: Dict[str, Dict[str, Any]] = {}


# --- Models (Schemas) ---
class SendCodeRequest(BaseModel):
    assistant_id: int = Field(..., description="user (assistant) ID")
    phone_number: str = Field(..., example="+998901234567", description="Xalqaro formatdagi telefon raqam")

class VerifyCodeRequest(BaseModel):
    phone_number: str = Field(..., example="+998901234567")
    code: str = Field(..., example="12345")

class VerifyPasswordRequest(BaseModel):
    phone_number: str = Field(..., example="+998901234567")
    password: str = Field(...)


# --- Helper Functions ---
def _check_assistant_exists(assistant_id: int) -> bool:
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""SELECT au.full_name
                        FROM app_user au
                        JOIN user_roles ur ON ur.app_user_id = au.id
                        JOIN rbac_role rr ON rr.id = ur.role_id
                        WHERE au.id = %s
                        AND rr.name = 'mentor';""", (assistant_id,))
        return cursor.fetchone() is not None

async def _finish_successful_login(assistant_id: int, phone_number: str, client: Client):
    session_name = f"assistant_{assistant_id}"
    me = await client.get_me()
    tg_user_id = me.id
    await client.disconnect()
    upsert_assistant_tg_info(
        assistant_id=assistant_id,
        session_name=session_name,
        phone=phone_number,
        tg_user_id=tg_user_id,
        is_active=True,
    )
    active_login_sessions.pop(phone_number, None)
    return {
        "status": "success",
        "message": "Login muvaffaqiyatli yakunlandi.",
        "assistant_id": assistant_id,
        "tg_user_id": tg_user_id,
        "session_name": session_name,
    }


# --- Endpoints ---
@router.post("/send-code")
async def send_code(payload: SendCodeRequest):
    if not _check_assistant_exists(payload.assistant_id):
        raise HTTPException(status_code=404, detail=f"Assistant_id={payload.assistant_id} topilmadi.")

    session_name = f"assistant_{payload.assistant_id}"
    session_path = f"{tg_config.sessions_dir}/{session_name}"

    client = Client(session_path, api_id=tg_config.api_id, api_hash=tg_config.api_hash, phone_number=payload.phone_number)
    await client.connect()

    try:
        sent_code = await client.send_code(payload.phone_number)
    except PhoneNumberInvalid:
        await client.disconnect()
        raise HTTPException(status_code=400, detail="Telefon raqami noto'g'ri.")

    active_login_sessions[payload.phone_number] = {
        "client": client,
        "phone_code_hash": sent_code.phone_code_hash,
        "assistant_id": payload.assistant_id,
    }
    return {"status": "code_sent", "message": "Kod yuborildi.", "phone_number": payload.phone_number}

@router.post("/verify-code")
async def verify_code(payload: VerifyCodeRequest):
    session_data = active_login_sessions.get(payload.phone_number)
    if not session_data:
        raise HTTPException(status_code=400, detail="Aktiv sessiya topilmadi.")

    client: Client = session_data["client"]
    try:
        await client.sign_in(payload.phone_number, session_data["phone_code_hash"], payload.code)
        return await _finish_successful_login(session_data["assistant_id"], payload.phone_number, client)
    except PhoneCodeInvalid:
        raise HTTPException(status_code=400, detail="Kod noto'g'ri.")
    except SessionPasswordNeeded:
        return {"status": "2fa_required", "message": "2FA paroli talab qilinadi.", "phone_number": payload.phone_number}

@router.post("/verify-password")
async def verify_password(payload: VerifyPasswordRequest):
    session_data = active_login_sessions.get(payload.phone_number)
    if not session_data:
        raise HTTPException(status_code=400, detail="Aktiv sessiya topilmadi.")

    client: Client = session_data["client"]
    try:
        await client.check_password(payload.password)
        return await _finish_successful_login(session_data["assistant_id"], payload.phone_number, client)
    except PasswordHashInvalid:
        raise HTTPException(status_code=400, detail="2FA paroli noto'g'ri.")