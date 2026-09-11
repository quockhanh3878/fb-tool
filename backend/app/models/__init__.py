"""Nạp toàn bộ ORM model để SQLAlchemy metadata biết đủ bảng."""
from app.models.app_setting import AppSetting
from app.models.campaign import BumpSchedule, Campaign, CampaignGroup, CommentScript
from app.models.clone_account import AccountHealthLog, CloneAccount, Proxy
from app.models.mention import Mention
from app.models.post import CommentAction, DiscoveredPost, PostPublish
from app.models.user import Subscription, User

__all__ = [
    "User",
    "Subscription",
    "Campaign",
    "CampaignGroup",
    "CommentScript",
    "BumpSchedule",
    "CloneAccount",
    "AccountHealthLog",
    "Proxy",
    "DiscoveredPost",
    "CommentAction",
    "PostPublish",
    "Mention",
    "AppSetting",
]
