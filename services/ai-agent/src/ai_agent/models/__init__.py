"""ORM model registry.

Importing this package registers every model on the declarative ``Base`` so
SQLAlchemy can configure cross-module relationships before the first query and
Alembic's ``target_metadata`` reflects the full schema.

- ``tenants`` is a read-only projection of identity's shared table.
- ``core_roles``/``core_user_roles`` are read-only projections of the core
  monolith's RBAC tables (SKY-59 tool permission resolution).
- The AI tables (ai_query_log, ai_suggestions, ai_anomalies, ai_audit_log)
  are owned by this service and migrated under ``alembic_version_ai``.
- ``agent_registry`` is global platform data (no tenant scoping).
- RAG tables (ai_rag_parents, ai_rag_chunks) support pgvector semantic search.
- Episodic memory, query cache, and eval runs support RAG infrastructure.
- LangGraph runtime tables (graph_checkpoints, graph_checkpoint_writes,
  agent_interrupts) support AGT-001 orchestration (SKY-59).
"""

from ai_agent.models.agent_interrupt import AgentInterruptModel
from ai_agent.models.agent_registry import AgentRegistryModel
from ai_agent.models.ai_anomaly import AiAnomalyModel
from ai_agent.models.ai_anomaly_rule_stats import AiAnomalyRuleStatsModel
from ai_agent.models.ai_audit_log import AiAuditLogModel
from ai_agent.models.ai_coaching_suggestion import AiCoachingSuggestionModel
from ai_agent.models.ai_conversation import AiConversation
from ai_agent.models.ai_conversation_message import AiConversationMessage
from ai_agent.models.ai_deal_health import AiDealHealthModel
from ai_agent.models.ai_digest import AiDigestModel
from ai_agent.models.ai_document_embeddings import AiDocumentEmbeddingModel
from ai_agent.models.ai_episodic_memory import AiEpisodicMemoryModel
from ai_agent.models.ai_eval_run import AiEvalRunModel
from ai_agent.models.ai_finance_eval_run import AiFinanceEvalRunModel
from ai_agent.models.ai_finance_line_embedding import AiFinanceLineEmbeddingModel
from ai_agent.models.ai_follow_up_suggestion import AiFollowUpSuggestionModel
from ai_agent.models.ai_guardian_event import AiGuardianEventModel
from ai_agent.models.ai_guardian_report import AiGuardianReportModel
from ai_agent.models.ai_inv_item_embedding import AiInvItemEmbeddingModel
from ai_agent.models.ai_lead_score import AiLeadScoreModel
from ai_agent.models.ai_query_cache import AiQueryCacheModel
from ai_agent.models.ai_query_log import AiQueryLogModel
from ai_agent.models.ai_rag_chunk import AiRagChunkModel
from ai_agent.models.ai_rag_parent import AiRagParentModel
from ai_agent.models.ai_restock_demand_stats import AiRestockDemandStatsModel
from ai_agent.models.ai_restock_settings import AiRestockSettingsModel
from ai_agent.models.ai_semantic_memory import AiSemanticMemoryModel
from ai_agent.models.ai_suggestion import AiSuggestionModel
from ai_agent.models.ai_supplier_risk import AiSupplierRiskModel
from ai_agent.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin
from ai_agent.models.core_rbac import CoreRoleModel, CoreUserRoleModel
from ai_agent.models.graph_checkpoint import (
    GraphCheckpointModel,
    GraphCheckpointWriteModel,
)
from ai_agent.models.tenant import TenantModel

__all__ = [
    "AgentInterruptModel",
    "AgentRegistryModel",
    "AiAnomalyModel",
    "AiAnomalyRuleStatsModel",
    "AiAuditLogModel",
    "AiCoachingSuggestionModel",
    "AiConversation",
    "AiConversationMessage",
    "AiDealHealthModel",
    "AiDigestModel",
    "AiDocumentEmbeddingModel",
    "AiEpisodicMemoryModel",
    "AiEvalRunModel",
    "AiFinanceEvalRunModel",
    "AiFinanceLineEmbeddingModel",
    "AiFollowUpSuggestionModel",
    "AiGuardianEventModel",
    "AiGuardianReportModel",
    "AiInvItemEmbeddingModel",
    "AiLeadScoreModel",
    "AiQueryCacheModel",
    "AiQueryLogModel",
    "AiRagChunkModel",
    "AiRagParentModel",
    "AiRestockDemandStatsModel",
    "AiRestockSettingsModel",
    "AiSemanticMemoryModel",
    "AiSuggestionModel",
    "AiSupplierRiskModel",
    "Base",
    "CoreRoleModel",
    "CoreUserRoleModel",
    "GraphCheckpointModel",
    "GraphCheckpointWriteModel",
    "TenantModel",
    "TimestampMixin",
    "UUIDPrimaryKeyMixin",
]
