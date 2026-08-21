"""
Bitta martalik, INTERAKTIV skript: har bir assistant uchun Pyrogram session
yaratadi (telefon raqam + SMS/Telegram kod + kerak bo'lsa 2FA parol so'raladi).

Login muvaffaqiyatli bo'lgach:
  1. sessions/ papkaga <session_name>.session fayli yoziladi.
  2. Lokal SQLite'dagi assistant_tg_info jadvaliga (assistant_id, session_name,
     phone, tg_user_id, is_active, created_at) upsert qilinadi.

Ishlatish:
    python -m scripts.login_assistant
"""
import asyncio

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
from shared.local_db import ensure_assistant_tg_info_table_exists, upsert_assistant_tg_info
from shared.logger import get_logger

logger = get_logger(__name__)


def _prompt_assistant_id() -> int:
    """User (role='mentor_assistant') jadvalidagi mavjud assistant_id ni so'raydi va tekshiradi."""
    while True:
        raw = input("Assistant_id (user.id where role='mentor_assistant') ni kiriting: ").strip()
        if not raw.isdigit():
            print("Xato: assistant_id butun son bo'lishi kerak.")
            continue

        assistant_id = int(raw)
        with get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT CONCAT_WS(' ', first_name, last_name) AS name FROM app_user WHERE id = %s AND role = 'mentor_assistant'",
                (assistant_id,)
            )
            row = cursor.fetchone()

        if not row:
            print(f"Xato: user jadvalida mentor_assistant assistant_id={assistant_id} topilmadi. Qayta urinib ko'ring.")
            continue

        print(f"Topildi: {row.name} (assistant_id={assistant_id})")
        return assistant_id


async def _login_single_assistant() -> None:
    """Bitta assistant uchun to'liq login jarayonini bajaradi."""
    assistant_id = _prompt_assistant_id()
    session_name = f"assistant_{assistant_id}"
    session_path = f"{tg_config.sessions_dir}/{session_name}"

    print(f"\n--- Assistant {assistant_id} uchun Telegram login ---")
    phone_number = input("Telefon raqamini xalqaro formatda kiriting (masalan +998901234567): ").strip()

    client = Client(
        session_path,
        api_id=tg_config.api_id,
        api_hash=tg_config.api_hash,
        phone_number=phone_number,
    )

    await client.connect()

    try:
        sent_code = await client.send_code(phone_number)
    except PhoneNumberInvalid:
        print("Xato: telefon raqami noto'g'ri formatda. Jarayon bekor qilindi.")
        await client.disconnect()
        return

    while True:
        code = input("Telegramdan kelgan tasdiqlash kodini kiriting: ").strip()
        try:
            await client.sign_in(phone_number, sent_code.phone_code_hash, code)
            break
        except PhoneCodeInvalid:
            print("Xato: kod noto'g'ri. Qayta kiriting.")
        except PhoneCodeExpired:
            print("Xato: kod muddati tugagan. Jarayon bekor qilindi.")
            await client.disconnect()
            return
        except SessionPasswordNeeded:
            while True:
                password = input("Ikki bosqichli tasdiqlash (2FA) paroli: ").strip()
                try:
                    await client.check_password(password)
                    break
                except PasswordHashInvalid:
                    print("Xato: parol noto'g'ri. Qayta kiriting.")
            break

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

    print(
        f"\n✅ Login muvaffaqiyatli: assistant_id={assistant_id}, "
        f"tg_user_id={tg_user_id}, session='{session_name}'. "
        f"Lokal SQLite (assistant_tg_info) yangilandi.\n"
    )


def _prompt_continue() -> bool:
    answer = input("Yana assistant qo'shasizmi? (ha/yo'q): ").strip().lower()
    return answer in ("ha", "h", "yes", "y")


async def main() -> None:
    print("=== Assistant Telegram login skripti ===")
    ensure_assistant_tg_info_table_exists()
    while True:
        try:
            await _login_single_assistant()
        except Exception as e:
            logger.error(f"Login jarayonida kutilmagan xato: {e}")
            print(f"❌ Xato yuz berdi: {e}")

        if not _prompt_continue():
            break

    print("Barcha assistantlar uchun login jarayoni yakunlandi.")


if __name__ == "__main__":
    asyncio.run(main())
