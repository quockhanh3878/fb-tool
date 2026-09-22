"""
AI Engine cho backend — lọc bài + sinh comment.

Cùng chiến lược với Phase 1 (commhunter/ai_engine.py) nhưng đọc cấu hình từ
bản ghi Campaign trong PostgreSQL thay vì file YAML, và luôn chạy lọc từ
khoá cục bộ TRƯỚC khi gọi AI để không đốt token vào rác.
"""
import asyncio
import json
import unicodedata
from datetime import datetime, timezone

from pydantic import BaseModel, Field, ValidationError

RETRY_COUNT = 3
RETRY_DELAY_SEC = 2
FILTER_TEMPERATURE = 0.3
COMMENT_TEMPERATURE = 0.8
FILTER_MAX_TOKENS = 500
COMMENT_MAX_TOKENS = 300


class ExtractedFields(BaseModel):
    genre: str = Field(default="", max_length=500)
    budget: str = Field(default="", max_length=500)
    deadline: str = Field(default="", max_length=500)
    details: str = Field(default="", max_length=1000)


class Evaluation(BaseModel):
    relevance_score: float = Field(ge=0, le=1, allow_inf_nan=False)
    reason: str = Field(default="", max_length=500)
    extracted: ExtractedFields = Field(default_factory=ExtractedFields)


def normalize_vi(text: str) -> str:
    """Bỏ dấu + hạ chữ thường để so khớp từ khoá tiếng Việt gõ thiếu dấu."""
    text = (text or "").lower().replace("đ", "d").replace("Đ", "d")
    decomposed = unicodedata.normalize("NFD", text)
    return "".join(c for c in decomposed if unicodedata.category(c) != "Mn")


def keyword_match(text: str, whitelist: list, blacklist: list) -> tuple[bool, str]:
    """Lọc từ khoá cục bộ (miễn phí). Trả về (được_đi_tiếp, lý_do_loại)."""
    haystack = normalize_vi(text)

    for keyword in blacklist or []:
        if keyword and normalize_vi(keyword) in haystack:
            return False, f"blacklist:{keyword}"

    positives = [k for k in (whitelist or []) if k]
    if positives and not any(normalize_vi(k) in haystack for k in positives):
        return False, "no_whitelist_keyword"

    return True, ""


class AIService:
    """Bọc OpenAI SDK; khởi tạo trễ để tiến trình không cần key khi chưa dùng AI."""

    def __init__(self, api_key: str = "", model: str = "gpt-4o-mini"):
        self.api_key = api_key
        self.model = model
        self._client = None

    @property
    def enabled(self) -> bool:
        return bool(self.api_key)

    def _get_client(self):
        if self._client is None:
            import openai

            self._client = openai.OpenAI(api_key=self.api_key, timeout=30.0, max_retries=0)
        return self._client

    async def _call(
        self,
        system_prompt: str,
        user_message: str,
        temperature: float,
        max_tokens: int,
        json_mode: bool = False,
        user_id: str = "",
    ):
        """Gọi OpenAI với retry. Hết retry: JSON trả điểm 0, text trả rỗng."""
        for attempt in range(1, RETRY_COUNT + 1):
            try:
                from app.config import get_settings
                from app.dependencies import enforce_rate_limit

                budget = get_settings().ai_calls_per_user_per_day
                if not user_id or budget == 0:
                    return {"relevance_score": 0.0, "reason": "ai_budget_unavailable", "extracted": {}} if json_mode else ""
                day = datetime.now(timezone.utc).date().isoformat()
                await enforce_rate_limit(f"ai:{user_id}:{day}", budget, 86400)
                kwargs = {
                    "model": self.model,
                    "messages": [
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_message},
                    ],
                    "temperature": temperature,
                    "max_tokens": max_tokens,
                }
                if json_mode:
                    kwargs["response_format"] = {"type": "json_object"}

                loop = asyncio.get_running_loop()
                response = await loop.run_in_executor(
                    None, lambda: self._get_client().chat.completions.create(**kwargs)
                )
                content = (response.choices[0].message.content or "").strip()
                return json.loads(content) if json_mode else content

            except json.JSONDecodeError:
                if attempt >= RETRY_COUNT:
                    return {
                        "relevance_score": 0.0,
                        "reason": "AI trả JSON hỏng",
                        "extracted": {},
                    }
                await asyncio.sleep(RETRY_DELAY_SEC)
            except Exception as exc:
                if attempt >= RETRY_COUNT:
                    if json_mode:
                        return {
                            "relevance_score": 0.0,
                            "reason": "AI upstream unavailable",
                            "extracted": {},
                        }
                    # Trả rỗng để orchestrator bỏ qua bài, KHÔNG bịa comment.
                    return ""
                await asyncio.sleep(RETRY_DELAY_SEC * attempt)
        return {} if json_mode else ""

    async def filter_post(self, content: str, campaign) -> dict:
        """Chấm điểm bài viết theo tiêu chí của chiến dịch."""
        passed, reason = keyword_match(
            content, campaign.whitelist_keywords or [], campaign.blacklist_keywords or []
        )
        if not passed:
            score = 0.0 if reason.startswith("blacklist") else 0.1
            return {"relevance_score": score, "reason": reason, "extracted": {}}

        if not self.enabled:
            # Không có key AI: dựa hoàn toàn vào từ khoá, cho điểm vừa đủ ngưỡng.
            return {
                "relevance_score": max(0.7, float(campaign.min_relevance_score or 0.7)) if any(campaign.whitelist_keywords or []) else 0.0,
                "reason": "keyword_only (chưa cấu hình OpenAI API key)",
                "extracted": {},
            }

        system_prompt = (
            "Bạn là trợ lý lọc bài viết Facebook.\n"
            f"Tiêu chí của người dùng: {campaign.ai_filter_prompt}\n\n"
            "Trả về JSON duy nhất (không markdown):\n"
            '{"relevance_score": 0.0-1.0, "reason": "...", '
            '"extracted": {"genre": "...", "budget": "...", "deadline": "...", "details": "..."}}'
        )
        result = await self._call(
            system_prompt,
            f"Bài viết:\n{content[:2000]}",
            FILTER_TEMPERATURE,
            FILTER_MAX_TOKENS,
            json_mode=True,
            user_id=getattr(campaign, "user_id", ""),
        )
        try:
            return Evaluation.model_validate(result).model_dump()
        except ValidationError:
            return {"relevance_score": 0.0, "reason": "AI trả về dữ liệu không hợp lệ", "extracted": {}}

    async def generate_comment(self, content: str, campaign, extracted: dict | None = None) -> str:
        """Sinh comment ứng tuyển bám thông tin dịch vụ của chiến dịch."""
        if not self.enabled:
            return ""

        system_prompt = (
            f"Viết 1 bình luận Facebook ứng tuyển/chào hàng cho "
            f"{campaign.service_name or campaign.name}.\n\n"
            "Thông tin dịch vụ:\n"
            f"- Tên: {campaign.service_name}\n"
            f"- Chuyên môn: {campaign.service_specialties}\n"
            f"- Điểm mạnh: {campaign.service_strengths}\n"
            f"- Ghi chú portfolio: {campaign.landing_page_note}\n\n"
            "Quy tắc bắt buộc:\n"
            "1. KHÔNG dán bất kỳ link nào.\n"
            "2. Nhắc đến chi tiết cụ thể trong bài.\n"
            "3. Giọng văn tự nhiên, thân thiện, như người thật gõ.\n"
            "4. Độ dài 40-120 từ tiếng Việt.\n"
            "5. Hướng dẫn xem portfolio ở đầu trang cá nhân (nếu có).\n"
            "6. Tối đa 1-2 emoji.\n\n"
            f"Chi tiết đã trích xuất: {json.dumps(extracted or {}, ensure_ascii=False)}"
        )
        result = await self._call(
            system_prompt,
            f"Bài viết cần ứng tuyển:\n{content[:2000]}",
            COMMENT_TEMPERATURE,
            COMMENT_MAX_TOKENS,
            json_mode=False,
            user_id=getattr(campaign, "user_id", ""),
        )
        return (result or "").strip().strip('"') if isinstance(result, str) else ""
