# Manager Agent v2

Group leaderlarning Telegram orqali talabalar bilan muloqot sifatini AI yordamida
avtomatik tahlil qiluvchi tizim.

## Arxitektura (4 modul)

- **accounts_app** — DB'dan faol leader va studentlarni oladi (data provider).
- **chat_history_app** — Pyrogram orqali chat tarixini oladi, ismlarni scrub qiladi,
  `chats_last_check` orqali faqat yangi xabarlarni oladi.
- **ai_agent_app** — LangChain + Google Gemini orqali muloqot sifatini tahlil qilib,
  strukturaviy report qaytaradi.
- **main_app** — 3 modulni ketma-ket ishga tushiradi, natijani Web API yoki CLI orqali beradi.

## O'rnatish

```bash
pip install -r requirements.txt
cp .env.example .env   # va qiymatlarni to'ldiring
```

Asosiy biznes ma'lumotlar (Groups, Students, Leaders va h.k.) **PostgreSQL**da saqlanadi --
tizimda PostgreSQL server ishga tushirilgan va `.env`dagi `DB_HOST`/`DB_PORT`/`DB_DATABASE`/
`DB_USERNAME`/`DB_PASSWORD` to'g'ri sozlangan bo'lishi kerak. Sxema `sql/` papkasidagi
`.sql` fayllar orqali (psql yoki boshqa PostgreSQL klient bilan) yaratiladi.

`ai_reports` va `chats_last_check` jadvallari esa **lokal SQLite** faylida
(`.env`dagi `LOCAL_SQLITE_PATH`, standart: `local_data.sqlite3`) saqlanadi va
ilova birinchi marta ishga tushganda avtomatik yaratiladi -- bu ikkala jadval
asosiy PostgreSQL bazasidan butunlay mustaqil.

`GOOGLE_API_KEY`ni Google AI Studio'dan olib `.env`ga qo'ying.

## 1-qadam: Leaderlarni Telegram'ga login qilish (bir martalik)

Har bir group leader uchun Pyrogram session avvaldan yaratilishi kerak
(telefon raqam + Telegramdan kelgan kod bilan). Buning uchun:

```bash
python -m scripts.login_leader
```

Skript:
1. `Group_Leaders` jadvalidan leader_id'ni tekshiradi.
2. Telefon raqam va tasdiqlash kodini (kerak bo'lsa 2FA parolini) so'raydi.
3. Muvaffaqiyatli login bo'lsa, `sessions/leader_<id>.session` faylini yaratadi
   va **lokal SQLite'dagi `leader_tg_info` jadvaliga avtomatik yozadi**
   (assistant_id, session_name, phone, tg_user_id, is_active, created_at).
4. Har bir akkaunt qo'shilgach, "Yana leader qo'shasizmi?" deb so'raydi —
   shu tariqa bir nechta leaderni ketma-ket ro'yxatdan o'tkazish mumkin.

Bu jarayon faqat **yangi leader qo'shilganda yoki session yo'qolganda** bir marta
bajariladi. Keyingi barcha `main_app` ishga tushirishlari avtomatik, interaktiv
so'rovlarsiz ishlaydi (chunki session fayllar allaqachon tayyor).

## Pipeline'ni ishga tushirish

**Web API orqali:**
```bash
uvicorn main_app.api:app --reload
```

Keyin:
- `GET /run-stream` — pipeline'ni STREAMING (NDJSON) tarzida ishga tushiradi
- `GET /reports` — oxirgi natijalarni ko'radi
- `GET /health` — health check

## Lokal SQLite jadvallari

Ilova birinchi marta ishga tushganda quyidagi jadvallarni (`shared/local_db.py`
orqali) lokal SQLite faylida avtomatik yaratadi:

```sql
CREATE TABLE chats_last_check (
    leader_id INTEGER NOT NULL,
    student_id INTEGER NOT NULL,
    last_check_date TEXT NOT NULL DEFAULT (datetime('now')),
    PRIMARY KEY (leader_id, student_id)
);

CREATE TABLE ai_reports (
    report_id INTEGER PRIMARY KEY AUTOINCREMENT,
    student_id INTEGER NOT NULL,
    leader_id INTEGER NOT NULL,
    problem TEXT,
    ai_summary TEXT,
    raw_json TEXT,
    last_contacted_date TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE leader_tg_info (
    assistant_id INTEGER PRIMARY KEY,
    session_name TEXT NOT NULL UNIQUE,
    phone TEXT NOT NULL,
    tg_user_id INTEGER,
    is_active INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);
```

## Xavfsizlik eslatmalari

- Pyrogram'dagi `FloodWait` xatosi `chat_history_app/fetcher.py` ichida
  avtomatik qayta urinish (retry) bilan boshqariladi.
- Talaba/leader ismlari AI'ga yuborilishidan oldin har doim `leader_id`/`student_id`
  bilan almashtiriladi (`chat_history_app/scrubber.py`).
- AI tahlil (`ai_agent_app`) LangChain'ning `with_structured_output` mexanizmi orqali
  Gemini javobini Pydantic schema (`schema.py`) ga majburiy moslaydi -- JSON parse
  xatolarining oldi olinadi.
- Telegram login (`scripts/login_leader.py`) faqat bir martalik, qo'lda ishga
  tushiriladigan jarayon -- asosiy pipeline hech qachon interaktiv login so'ramaydi.
