"""
PostgreSQL bilan ulanish uchun umumiy yordamchi (psycopg2 asosida).
Asosiy biznes ma'lumotlar (Groups, Students, Leaders va h.k.) shu bazada saqlanadi.
Barcha modul shu yerdan foydalanadi -> DB kodi bir joyda, takrorlanmaydi.
"""
from contextlib import contextmanager
from typing import Iterator

import psycopg2
import psycopg2.extras

from shared.config import db_config
from shared.logger import get_logger

logger = get_logger(__name__)


@contextmanager
def get_connection() -> Iterator["psycopg2.extensions.connection"]:
    """
    Context manager: PostgreSQL ulanishini ochadi, oxirida albatta yopadi.
    Xatolik bo'lsa rollback qiladi.

    cursor() chaqirilganda satrlar nomlangan (dict-style, `.attr` bilan
    ham, `["attr"]` bilan ham) o'qilishi uchun cursor_factory
    RealDictCursor'ga o'xshab ishlaydigan NamedTupleCursor beriladi --
    shu orqali qolgan kod (row.assistant_id kabi) o'zgarishsiz ishlayveradi.
    """
    conn = None
    try:
        conn = psycopg2.connect(
            db_config.conn_string,
            connect_timeout=10,
            cursor_factory=psycopg2.extras.NamedTupleCursor,
        )
        yield conn
    except psycopg2.Error as e:
        logger.error(f"PostgreSQL ulanish xatosi: {e}")
        if conn:
            conn.rollback()
        raise
    finally:
        if conn:
            conn.close()
