"""
Config Loader — Đọc file YAML cấu hình và chuyển thành AppConfig.
"""
import os
from pathlib import Path

import yaml
from loguru import logger

from models import (
    AppConfig,
    ServiceInfo,
    GroupConfig,
    AccountConfig,
    BrowserConfig,
    FilterConfig,
    CommentConfig,
    TelegramConfig,
    OpenAIConfig,
    DatabaseConfig,
)
from constants import BROWSER_CHANNEL, BROWSER_HEADLESS_DEFAULT


def _resolve_env(value: str) -> str:
    """Thay thế biến môi trường trong giá trị cấu hình.
    
    Hỗ trợ: $ENV_VAR hoặc ${ENV_VAR} trong chuỗi YAML.
    """
    if not isinstance(value, str):
        return value
    if value.startswith("$"):
        env_name = value.lstrip("$").strip("{}")
        env_val = os.environ.get(env_name)
        if env_val:
            return env_val
        logger.warning(f"Biến môi trường {env_name} không tồn tại, giữ nguyên giá trị gốc")
    return value


def load_config(config_path: str) -> AppConfig:
    """Đọc file YAML và trả về AppConfig.
    
    Args:
        config_path: Đường dẫn đến file YAML cấu hình.
    
    Returns:
        AppConfig chứa toàn bộ cấu hình ứng dụng.
    
    Raises:
        FileNotFoundError: Nếu file không tồn tại.
        ValueError: Nếu file YAML không hợp lệ.
    """
    path = Path(config_path)
    if not path.exists():
        raise FileNotFoundError(f"File cấu hình không tồn tại: {config_path}")

    with open(path, "r", encoding="utf-8") as f:
        raw = yaml.safe_load(f)

    if not isinstance(raw, dict):
        raise ValueError(f"File YAML không hợp lệ (phải là dict): {config_path}")

    logger.info(f"Đã load cấu hình từ {config_path}")

    # Parse service info
    svc_raw = raw.get("service", {})
    service = ServiceInfo(
        name=svc_raw.get("name", ""),
        specialties=svc_raw.get("specialties", ""),
        strengths=svc_raw.get("strengths", ""),
        landing_page_note=svc_raw.get("landing_page_note", ""),
    )

    # Parse groups
    groups = []
    for g in raw.get("groups", []):
        groups.append(GroupConfig(
            url=g.get("url", ""),
            name=g.get("name", ""),
            scan_interval_minutes=g.get("scan_interval_minutes", 10),
        ))

    # Parse accounts
    accounts = {}
    for role, acc_raw in raw.get("accounts", {}).items():
        accounts[role] = AccountConfig(
            cookie_file=acc_raw.get("cookie_file", ""),
            profile_dir=acc_raw.get("profile_dir", ""),
            proxy=acc_raw.get("proxy"),
            cdp_endpoint=acc_raw.get("cdp_endpoint"),
        )

    # Parse browser runtime
    br_raw = raw.get("browser", {}) or {}
    browser_cfg = BrowserConfig(
        channel=br_raw.get("channel", BROWSER_CHANNEL),
        headless=bool(br_raw.get("headless", BROWSER_HEADLESS_DEFAULT)),
        attach_cdp=br_raw.get("attach_cdp"),
    )

    # Parse filter
    flt_raw = raw.get("filter", {})
    filter_cfg = FilterConfig(
        whitelist_keywords=flt_raw.get("whitelist_keywords", []),
        blacklist_keywords=flt_raw.get("blacklist_keywords", []),
        ai_filter_prompt=flt_raw.get("ai_filter_prompt", ""),
        min_relevance_score=flt_raw.get("min_relevance_score", 0.7),
        max_competitor_comments=flt_raw.get("max_competitor_comments", 8),
    )

    # Parse comment config
    cmt_raw = raw.get("comment", {})
    comment_cfg = CommentConfig(
        mode=cmt_raw.get("mode", "semi_auto"),
        use_ai=bool(cmt_raw.get("use_ai", True)),
        template_file=cmt_raw.get("template_file"),
        ai_model=cmt_raw.get("ai_model", "gpt-4o-mini"),
        max_comments_per_day=cmt_raw.get("max_comments_per_day", 20),
        delay_min_seconds=cmt_raw.get("delay_min_seconds", 300),
        delay_max_seconds=cmt_raw.get("delay_max_seconds", 900),
        typing_delay_min_ms=cmt_raw.get("typing_delay_min_ms", 80),
        typing_delay_max_ms=cmt_raw.get("typing_delay_max_ms", 350),
        typo_probability=cmt_raw.get("typo_probability", 0.05),
    )

    # Parse telegram config
    tg_raw = raw.get("telegram", {})
    telegram_cfg = TelegramConfig(
        bot_token=_resolve_env(tg_raw.get("bot_token", "")),
        chat_id=_resolve_env(tg_raw.get("chat_id", "")),
    )

    # Parse openai config
    ai_raw = raw.get("openai", {})
    openai_cfg = OpenAIConfig(
        api_key=_resolve_env(ai_raw.get("api_key", "")),
        model=ai_raw.get("model", "gpt-4o-mini"),
    )

    # Parse database config
    db_raw = raw.get("database", {})
    database_cfg = DatabaseConfig(
        path=db_raw.get("path", "data/commhunter.db"),
    )

    config = AppConfig(
        service=service,
        groups=groups,
        filter=filter_cfg,
        accounts=accounts,
        browser=browser_cfg,
        comment=comment_cfg,
        telegram=telegram_cfg,
        openai=openai_cfg,
        database=database_cfg,
    )

    _validate_config(config)
    return config


def _validate_config(config: AppConfig) -> None:
    """Validate cấu hình cơ bản."""
    if not config.groups:
        logger.warning("Chưa cấu hình group nào để giám sát")

    if not config.openai.api_key or config.openai.api_key.startswith("sk-xxxx"):
        logger.warning("OpenAI API key chưa được cấu hình hợp lệ")

    if not config.telegram.bot_token or config.telegram.bot_token == "BOT_TOKEN_HERE":
        logger.warning("Telegram bot token chưa được cấu hình")

    if config.comment.delay_min_seconds < 60:
        logger.warning(
            f"delay_min_seconds={config.comment.delay_min_seconds}s quá thấp, "
            "khuyến nghị >= 300s để tránh bị Facebook phát hiện"
        )

    if config.comment.max_comments_per_day > 30:
        logger.warning(
            f"max_comments_per_day={config.comment.max_comments_per_day} quá cao, "
            "khuyến nghị <= 20 để tránh bị ban"
        )
