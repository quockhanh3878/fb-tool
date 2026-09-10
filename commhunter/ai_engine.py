"""
AI Engine — Bộ lọc bài viết + Sinh comment bằng OpenAI.
Kế thừa pattern từ ai-comment-bot/main.py, cập nhật lên SDK openai mới.
"""
import asyncio
import json
from typing import Optional

from loguru import logger

from constants import (
    AI_MODEL_DEFAULT,
    AI_FILTER_TEMPERATURE,
    AI_COMMENT_TEMPERATURE,
    AI_FILTER_MAX_TOKENS,
    AI_COMMENT_MAX_TOKENS,
    AI_RETRY_COUNT,
    AI_RETRY_DELAY_SEC,
)


class AIEngine:
    """Bộ máy AI: lọc bài viết và sinh comment cá nhân hóa."""

    def __init__(self, api_key_or_config, model: str = None):
        """Khởi tạo bộ máy AI.

        Chấp nhận hai kiểu gọi để không phải sửa mọi call-site:
          * ``AIEngine(api_key, model)`` — kiểu cũ, truyền thẳng khóa.
          * ``AIEngine(config)`` — truyền AppConfig, tự rút ``config.openai``.

        Nợ kỹ thuật N-05: trước đây chỉ nhận chuỗi khóa nên khi truyền
        AppConfig vào, openai SDK vẫn nhận (không kiểm kiểu) và lỗi chỉ lộ
        ra lúc gọi API thật. Nay hợp đồng được nới rõ ràng thay vì im lặng.
        """
        import openai

        openai_cfg = getattr(api_key_or_config, "openai", None)
        if openai_cfg is not None:
            api_key = getattr(openai_cfg, "api_key", "") or ""
            model = model or getattr(openai_cfg, "model", None) or AI_MODEL_DEFAULT
        elif isinstance(api_key_or_config, str):
            api_key = api_key_or_config
            model = model or AI_MODEL_DEFAULT
        else:
            raise TypeError(
                "AIEngine cần api_key (str) hoặc AppConfig có thuộc tính .openai"
            )

        self.client = openai.OpenAI(api_key=api_key)
        self.model = model
        logger.info(f"AIEngine khởi tạo với model {model}")

    async def filter_post(
        self,
        post_content: str,
        user_prompt: str,
        whitelist: list = None,
        blacklist: list = None,
    ) -> dict:
        """Chấm điểm độ phù hợp của bài viết.
        
        Args:
            post_content: Nội dung bài viết.
            user_prompt: Tiêu chí lọc của người dùng.
            whitelist: Danh sách từ khóa ưu tiên.
            blacklist: Danh sách từ khóa loại trừ.
        
        Returns:
            Dict chứa relevance_score (0-1), reason, extracted.
        """
        # Pre-filter bằng keyword trước khi gọi AI (tiết kiệm chi phí)
        content_lower = post_content.lower()

        if blacklist:
            for kw in blacklist:
                if kw.lower() in content_lower:
                    return {
                        "relevance_score": 0.0,
                        "reason": f"Blacklist keyword: {kw}",
                        "extracted": {},
                    }

        whitelist_match = False
        if whitelist:
            for kw in whitelist:
                if kw.lower() in content_lower:
                    whitelist_match = True
                    break

        # Nếu không match whitelist nào thì score thấp
        if whitelist and not whitelist_match:
            return {
                "relevance_score": 0.1,
                "reason": "Không match whitelist keyword nào",
                "extracted": {},
            }

        # Gọi AI chấm điểm
        system_prompt = f"""Bạn là trợ lý lọc bài viết Facebook. 
Tiêu chí của người dùng: {user_prompt}

Trả về JSON duy nhất (không markdown):
{{"relevance_score": 0.0-1.0, "reason": "...", "extracted": {{"genre": "...", "budget": "...", "deadline": "...", "details": "..."}}}}"""

        return await self._call_ai(
            system_prompt=system_prompt,
            user_message=f"Bài viết:\n{post_content[:2000]}",
            temperature=AI_FILTER_TEMPERATURE,
            max_tokens=AI_FILTER_MAX_TOKENS,
            json_mode=True,
        )

    async def generate_comment(
        self,
        post_content: str,
        service_info: dict,
        extracted_details: dict = None,
    ) -> str:
        """Sinh bình luận tự nhiên cá nhân hóa.
        
        Args:
            post_content: Nội dung bài viết cần ứng tuyển.
            service_info: Thông tin dịch vụ (name, specialties, strengths, landing_page_note).
            extracted_details: Chi tiết đã trích xuất từ AI filter.
        
        Returns:
            Bình luận tiếng Việt tự nhiên, 40-120 từ.
        """
        extracted = extracted_details or {}
        service_name = service_info.get("name", "dịch vụ")
        system_prompt = f"""Viết 1 bình luận Facebook ứng tuyển/chào hàng cho {service_name}.

Thông tin dịch vụ:
- Tên: {service_info.get('name', '')}
- Chuyên môn: {service_info.get('specialties', '')}
- Điểm mạnh: {service_info.get('strengths', '')}
- Ghi chú portfolio: {service_info.get('landing_page_note', '')}

Quy tắc bắt buộc:
1. KHÔNG dán bất kỳ link nào.
2. Nhắc đến chi tiết cụ thể trong bài (nhu cầu, thể loại, yêu cầu...).
3. Giọng văn tự nhiên, thân thiện, như người thật gõ.
4. Độ dài 40-120 từ tiếng Việt.
5. Hướng dẫn xem portfolio ở đầu trang cá nhân (nếu có trong thông tin dịch vụ).
6. KHÔNG sử dụng emoji quá nhiều (tối đa 1-2).

Chi tiết đã trích xuất: {json.dumps(extracted, ensure_ascii=False)}"""

        result = await self._call_ai(
            system_prompt=system_prompt,
            user_message=f"Bài viết cần ứng tuyển:\n{post_content[:2000]}",
            temperature=AI_COMMENT_TEMPERATURE,
            max_tokens=AI_COMMENT_MAX_TOKENS,
            json_mode=False,
        )

        if isinstance(result, dict):
            return result.get("comment", str(result))
        return str(result).strip().strip('"')

    async def _call_ai(
        self,
        system_prompt: str,
        user_message: str,
        temperature: float,
        max_tokens: int,
        json_mode: bool = False,
    ) -> dict | str:
        """Gọi OpenAI API với retry logic.
        
        Returns:
            Dict (nếu json_mode) hoặc str.
        """
        for attempt in range(1, AI_RETRY_COUNT + 1):
            try:
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

                # Chạy sync call trong executor để không block event loop
                loop = asyncio.get_running_loop()
                response = await loop.run_in_executor(
                    None,
                    lambda: self.client.chat.completions.create(**kwargs),
                )

                content = response.choices[0].message.content.strip()

                if json_mode:
                    return json.loads(content)
                return content

            except json.JSONDecodeError as e:
                logger.warning(f"AI trả về JSON không hợp lệ (attempt {attempt}): {e}")
                if attempt < AI_RETRY_COUNT:
                    await asyncio.sleep(AI_RETRY_DELAY_SEC)
                else:
                    return {
                        "relevance_score": 0.5,
                        "reason": "AI response parse error",
                        "extracted": {},
                    }

            except Exception as e:
                logger.error(f"AI API error (attempt {attempt}/{AI_RETRY_COUNT}): {e}")
                if attempt < AI_RETRY_COUNT:
                    await asyncio.sleep(AI_RETRY_DELAY_SEC * attempt)
                else:
                    if json_mode:
                        return {
                            "relevance_score": 0.0,
                            "reason": f"AI API error: {str(e)}",
                            "extracted": {},
                        }
                    logger.error(
                        f"AI không thể sinh comment sau {AI_RETRY_COUNT} lần thử — "
                        "trả về chuỗi rỗng để orchestrator an toàn bỏ qua bài."
                    )
                    return ""
