"""
LangChain uchun Pydantic schema -- Gemini javobi shu strukturaga
majburiy moslanadi (with_structured_output orqali).
"""
from pydantic import BaseModel, Field


class InteractionAnalysis(BaseModel):
    """Bitta assistant-student chat tarixi bo'yicha AI tahlil natijasi."""

    support_quality_score: int = Field(
        description="Assistantning talabani qo'llab-quvvatlash sifati, 1 dan 10 gacha baho",
        ge=1, le=10,
    )
    assistant_contacted_student: bool = Field(
        description="Assistant talaba bilan berilgan davr ichida umuman bog'langanmi (xabar yozganmi)"
    )
    contact_summary: str = Field(
        default="",
        description=(
            "Assistant qachon va nima haqida bog'langani/so'ragani haqida qisqa tavsif "
            "(masalan: 'so'nggi darsdan keyin uy vazifasi haqida so'ragan'). "
            "Bog'lanish bo'lmagan bo'lsa bo'sh qoldiring."
        ),
    )
    addressed_issues: bool = Field(
        description="Assistant talabaning muammolarini (issues) muhokama qilib, hal qilishga harakat qildimi"
    )
    discussed_flagged_problem: bool = Field(
        description="Assistant talaba qatnashmagan yoki uyga vazifani bajarmagan holatlar sababini so'radimi"
    )
    offered_help: bool = Field(
        description=(
            "Assistant talabaga aniq yordam taklif qildimi (masalan: 'qanday yordam kerak?', "
            "'yordamlashamiz' kabi gaplar bo'ldimi)"
        )
    )
    problem_discussed: bool = Field(
        description=(
            "Berilgan `problem` (talabaning progress muammosi) ushbu chatda assistant va "
            "talaba o'rtasida muhokama qilinganmi (ya'ni assistant shu muammodan xabardor "
            "bo'lib, gaplashganmi)"
        )
    )
    last_contacted_date: str = Field(
        default="",
        description=(
            "Talaba bilan o'quv jarayoni, uy vazifalari yoki yuzaga kelgan muammolar "
            "bo'yicha mazmunli muloqot qilingan eng oxirgi sana ('YYYY-MM-DD' formatida). "
            "Shunchaki salom-alik, rasmiyatchilik yoki darsga aloqasiz xabarlar hisobga olinmaydi. "
            "Agar bunday mazmunli suhbat umuman bo'lmagan bo'lsa, bo'sh string ('') qaytaring."
        ),
    )
    summary: str = Field(
        description="Muloqot haqida 2-3 gapli qisqa xulosa"
    )
    recommendations: str = Field(
        description="Etibor berilmay qolgan lekin so'ralishi, muhokama qilinishi kerak bo'lgan jihatlar"
    )

