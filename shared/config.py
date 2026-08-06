"""
Umumiy konfiguratsiya. .env fayldan o'qiladi.
"""
import os
from dataclasses import dataclass
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

# Loyiha ildiz papkasi (bu fayldan ikki daraja yuqorida: shared/config.py -> loyiha root)
PROJECT_ROOT = Path(__file__).resolve().parent.parent


@dataclass(frozen=True)
class DBConfig:
    """Asosiy biznes ma'lumotlar bazasi (PostgreSQL)."""
    host: str = os.getenv("DB_HOST", "localhost")
    port: int = int(os.getenv("DB_PORT", "5432"))
    database: str = os.getenv("DB_DATABASE", "your_db")
    username: str = os.getenv("DB_USERNAME", "postgres")
    password: str = os.getenv("DB_PASSWORD", "changeme")

    @property
    def conn_string(self) -> str:
        return (
            f"host={self.host} port={self.port} dbname={self.database} "
            f"user={self.username} password={self.password}"
        )


@dataclass(frozen=True)
class LocalDBConfig:
    """
    Lokal SQLite baza: faqat ai_reports va chats_last_check jadvallari
    shu yerda saqlanadi (asosiy PostgreSQL bazadan mustaqil).
    .env dagi qiymat nisbiy bo'lsa ham, doim loyiha ildiziga nisbatan
    ABSOLYUT yo'lga aylantiriladi.
    """
    path: str = str(PROJECT_ROOT / os.getenv("LOCAL_SQLITE_PATH", "local_data.sqlite3"))


@dataclass(frozen=True)
class TelegramConfig:
    api_id: int = int(os.getenv("TG_API_ID", "0"))
    api_hash: str = os.getenv("TG_API_HASH", "")
    # .env dagi qiymat nisbiy (masalan "sessions") bo'lsa ham, doim loyiha
    # ildiziga nisbatan ABSOLYUT yo'lga aylantiriladi -- buyruq qaysi papkadan
    # ishga tushirilishidan qat'i nazar bir xil joyni ko'rsatishi uchun.
    sessions_dir: str = str(PROJECT_ROOT / os.getenv("TG_SESSIONS_DIR", "sessions"))


@dataclass(frozen=True)
class AIConfig:
    google_api_key: str = os.getenv("GOOGLE_API_KEY", "")
    model: str = os.getenv("AI_MODEL", "gemini-2.0-flash")
    max_tokens: int = int(os.getenv("AI_MAX_TOKENS", "1024"))
    temperature: float = float(os.getenv("AI_TEMPERATURE", "0.2"))


@dataclass(frozen=True)
class AppConfig:
    log_level: str = os.getenv("LOG_LEVEL", "INFO")
    fetch_days_fallback: int = int(os.getenv("FETCH_DAYS_FALLBACK", "30"))
    flood_wait_max_retries: int = int(os.getenv("FLOOD_WAIT_MAX_RETRIES", "5"))
    # Progress-tekshirish bosqichida guruhlar nechtadan bo'lib (pagination)
    # AI'ga yuborilishi -- studentlari ko'p bo'lganda AI kontekstiga sig'maslikning oldini oladi.
    progress_group_batch_size: int = int(os.getenv("PROGRESS_GROUP_BATCH_SIZE", "3"))


db_config = DBConfig()
local_db_config = LocalDBConfig()
tg_config = TelegramConfig()
ai_config = AIConfig()
app_config = AppConfig()

# sessions papka mavjudligini kafolatlaydi (Pyrogram papkani o'zi yaratmaydi)
Path(tg_config.sessions_dir).mkdir(parents=True, exist_ok=True)
