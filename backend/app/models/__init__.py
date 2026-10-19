"""Nạp toàn bộ ORM model để SQLAlchemy metadata biết đủ bảng."""
from app.models.app_setting import AppSetting
from app.models.campaign import BumpSchedule, Campaign, CampaignGroup, CommentScript
from app.models.clone_account import AccountHealthLog, CloneAccount, Proxy
from app.models.lead import CommentLead
from app.models.interaction import PageInteraction
from app.models.job import JobRun
from app.models.mention import Mention
from app.models.post import (
    CommentAction,
    DiscoveredPost,
    PostPublish,
    PostPublishHistory,
    PublishingMedia,
)
from app.models.user import Subscription, User
from app.models.operations import (
    NotificationOutbox, NotificationRecipient, PaymentOrder, RefreshSession,
    ResourceLease, TelegramUpdate,
)

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
    "PostPublishHistory",
    "PublishingMedia",
    "Mention",
    "CommentLead",
    "PageInteraction",
    "JobRun",
    "AppSetting",
    "PaymentOrder",
    "RefreshSession",
    "ResourceLease",
    "TelegramUpdate",
    "NotificationOutbox",
    "NotificationRecipient",
]
