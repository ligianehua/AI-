"""SQLAlchemy 模型。集中导入以便 Alembic 拿到完整 metadata。"""

from app.models.account import Account
from app.models.activity import Activity
from app.models.base import AppModel, Base
from app.models.contact import Contact
from app.models.contract import Contract
from app.models.discovery_candidate import DiscoveryCandidate
from app.models.discovery_subscription import DiscoverySubscription
from app.models.forecast_snapshot import ForecastSnapshot
from app.models.knowledge_chunk import KnowledgeChunk
from app.models.knowledge_doc import KnowledgeDoc
from app.models.lead import Lead
from app.models.llm_call import LlmCall
from app.models.notification import Notification
from app.models.opportunity import Opportunity
from app.models.script import Script
from app.models.team import Team
from app.models.user import User

__all__ = [
    "Account",
    "Activity",
    "AppModel",
    "Base",
    "Contact",
    "Contract",
    "DiscoveryCandidate",
    "DiscoverySubscription",
    "ForecastSnapshot",
    "KnowledgeChunk",
    "KnowledgeDoc",
    "Lead",
    "LlmCall",
    "Notification",
    "Opportunity",
    "Script",
    "Team",
    "User",
]
