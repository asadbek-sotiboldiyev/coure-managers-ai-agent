"""
main_app: Pipeline'ning PREVIEW bosqichi (progress + progress-AI) bilan
CONTINUE bosqichi (chat + AI-summary) orasidagi holatni saqlaydigan
oddiy in-memory kesh.

Nega alohida modul: main_app.orchestrator va main_app.api ikkalasi ham
shu keshga murojaat qiladi -- alohida modulga chiqarish circular import'ni
oldini oladi va keshni yagona joyda boshqarish imkonini beradi.

Eslatma: bu kesh faqat JORIY server jarayoni хotirasida yashaydi -- server
qayta ishga tushsa (masalan --reload bilan), barcha kutilayotgan preview'lar
yo'qoladi. Muddati (TTL) o'tgan preview'lar ham avtomatik tozalanadi.
"""
import time
from threading import Lock
from typing import Any, Optional

from shared.logger import get_logger

logger = get_logger(__name__)

# preview_id -> {"data": {...}, "created_at": float}
_store: dict[str, dict[str, Any]] = {}
_lock = Lock()

# Preview shu vaqtdan ortiq kutilsa, eskirgan deb hisoblanadi va tozalanadi.
_TTL_SECONDS = 60 * 60 * 2  # 2 soat


def _cleanup_expired() -> None:
    now = time.time()
    expired = [pid for pid, entry in _store.items() if now - entry["created_at"] > _TTL_SECONDS]
    for pid in expired:
        _store.pop(pid, None)
    if expired:
        logger.info(f"preview_store: {len(expired)} ta eskirgan preview tozalandi.")


def save_preview(preview_id: str, data: dict[str, Any]) -> None:
    """Preview natijasini (progress snapshot + muammoli studentlar) saqlaydi."""
    with _lock:
        _cleanup_expired()
        _store[preview_id] = {"data": data, "created_at": time.time()}
    logger.info(f"preview_store: preview_id={preview_id} saqlandi.")


def get_preview(preview_id: str) -> Optional[dict[str, Any]]:
    """Saqlangan preview ma'lumotini qaytaradi (topilmasa yoki muddati o'tgan bo'lsa None)."""
    with _lock:
        _cleanup_expired()
        entry = _store.get(preview_id)
        return entry["data"] if entry else None


def delete_preview(preview_id: str) -> None:
    """Preview'ni keshdan olib tashlaydi (masalan continue muvaffaqiyatli tugagach)."""
    with _lock:
        _store.pop(preview_id, None)
