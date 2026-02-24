"""
Elasticsearch client for immutable audit log storage.

HIPAA requires 7-year retention of audit trails.
Elasticsearch provides:
  - Fast full-text search over audit events
  - Index lifecycle management (ILM) for automated retention
  - Per-tenant index isolation via index patterns
  - Append-only write patterns for immutability

Primary audit storage: PostgreSQL (durability)
Secondary audit storage: Elasticsearch (searchability)
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from elasticsearch import AsyncElasticsearch, NotFoundError

from app.core.config import get_settings
from app.core.logging import get_logger

logger = get_logger("elasticsearch")

# Module-level client (initialized on first use, closed on shutdown)
_client: AsyncElasticsearch | None = None


# ── Index template for audit logs ────────────────────────────────────────────
AUDIT_INDEX_TEMPLATE = {
    "index_patterns": ["lumeops-audit-*"],
    "template": {
        "settings": {
            "number_of_shards": 1,
            "number_of_replicas": 0,  # Dev: 0, Prod: 1+
            "index.lifecycle.name": "lumeops-audit-ilm",
            "index.lifecycle.rollover_alias": "lumeops-audit-write",
        },
        "mappings": {
            "properties": {
                "tenant_id": {"type": "keyword"},
                "action": {"type": "keyword"},
                "resource_type": {"type": "keyword"},
                "resource_id": {"type": "keyword"},
                "user_id": {"type": "keyword"},
                "api_key_prefix": {"type": "keyword"},
                "ip_address": {"type": "ip"},
                "user_agent": {"type": "text"},
                "status": {"type": "keyword"},
                "error_message": {"type": "text"},
                "pii_detected": {"type": "boolean"},
                "pii_types": {"type": "object", "dynamic": True},
                "details": {"type": "object", "dynamic": True},
                "timestamp": {"type": "date"},
                "environment": {"type": "keyword"},
            }
        },
    },
}

# ILM policy: hot -> warm -> cold -> delete after 7 years (HIPAA minimum)
AUDIT_ILM_POLICY = {
    "policy": {
        "phases": {
            "hot": {
                "min_age": "0ms",
                "actions": {
                    "rollover": {
                        "max_size": "10gb",
                        "max_age": "30d",
                    }
                },
            },
            "warm": {
                "min_age": "90d",
                "actions": {
                    "readonly": {},
                    "forcemerge": {"max_num_segments": 1},
                },
            },
            "cold": {
                "min_age": "365d",
                "actions": {
                    "readonly": {},
                },
            },
            "delete": {
                "min_age": "2555d",  # 7 years (HIPAA retention)
                "actions": {
                    "delete": {},
                },
            },
        }
    }
}


async def get_es_client() -> AsyncElasticsearch | None:
    """Get or create the Elasticsearch async client."""
    global _client

    if _client is not None:
        return _client

    settings = get_settings()
    url = settings.ELASTICSEARCH_URL

    if not url:
        logger.warning("elasticsearch_disabled", reason="ELASTICSEARCH_URL not set")
        return None

    try:
        _client = AsyncElasticsearch(
            hosts=[url],
            request_timeout=10,
            max_retries=2,
            retry_on_timeout=True,
        )
        # Verify connection
        info = await _client.info()
        logger.info(
            "elasticsearch_connected",
            version=info["version"]["number"],
            cluster=info["cluster_name"],
        )
        return _client
    except Exception as e:
        logger.error("elasticsearch_connection_failed", error=str(e))
        _client = None
        return None


async def close_es_client() -> None:
    """Close the Elasticsearch client."""
    global _client
    if _client is not None:
        await _client.close()
        _client = None
        logger.info("elasticsearch_closed")


async def setup_audit_indices() -> bool:
    """
    Create ILM policy, index template, and initial index for audit logs.
    Idempotent — safe to call on every startup.
    """
    client = await get_es_client()
    if client is None:
        return False

    settings = get_settings()
    prefix = settings.ELASTICSEARCH_INDEX_PREFIX

    try:
        # 1. Create ILM policy
        try:
            await client.ilm.put_lifecycle(name=f"{prefix}-ilm", body=AUDIT_ILM_POLICY)
            logger.info("ilm_policy_created", name=f"{prefix}-ilm")
        except Exception as e:
            # ILM might not be available in basic license
            logger.warning("ilm_policy_skipped", error=str(e))

        # 2. Create index template
        await client.indices.put_index_template(
            name=f"{prefix}-template",
            body=AUDIT_INDEX_TEMPLATE,
        )
        logger.info("index_template_created", name=f"{prefix}-template")

        # 3. Create initial index if it doesn't exist
        initial_index = f"{prefix}-000001"
        exists = await client.indices.exists(index=initial_index)
        if not exists:
            await client.indices.create(
                index=initial_index,
                body={
                    "aliases": {
                        f"{prefix}-write": {"is_write_index": True},
                        f"{prefix}-read": {},
                    }
                },
            )
            logger.info("initial_index_created", index=initial_index)

        return True

    except Exception as e:
        logger.error("audit_index_setup_failed", error=str(e))
        return False


async def index_audit_event(event: dict[str, Any]) -> bool:
    """
    Index a single audit event into Elasticsearch.

    Writes to the write alias so ILM handles rollover automatically.
    Non-blocking — failures are logged but don't affect the request.
    """
    client = await get_es_client()
    if client is None:
        return False

    settings = get_settings()
    write_alias = f"{settings.ELASTICSEARCH_INDEX_PREFIX}-write"

    try:
        # Add environment tag
        event["environment"] = settings.ENVIRONMENT

        # Ensure timestamp is ISO format string
        if isinstance(event.get("timestamp"), datetime):
            event["timestamp"] = event["timestamp"].isoformat()

        await client.index(
            index=write_alias,
            body=event,
            refresh=False,  # Don't wait for refresh — better throughput
        )
        return True

    except Exception as e:
        logger.error(
            "audit_index_failed",
            error=str(e),
            action=event.get("action"),
            tenant_id=event.get("tenant_id"),
        )
        return False


async def search_audit_logs(
    tenant_id: str,
    *,
    action: str | None = None,
    resource_type: str | None = None,
    start_date: datetime | None = None,
    end_date: datetime | None = None,
    size: int = 100,
) -> dict[str, Any]:
    """
    Search audit logs in Elasticsearch with tenant isolation.

    Returns matching events sorted by timestamp descending.
    """
    client = await get_es_client()
    if client is None:
        return {"total": 0, "events": [], "source": "unavailable"}

    settings = get_settings()
    read_alias = f"{settings.ELASTICSEARCH_INDEX_PREFIX}-read"

    must_clauses: list[dict] = [
        {"term": {"tenant_id": tenant_id}},
    ]

    if action:
        must_clauses.append({"term": {"action": action}})
    if resource_type:
        must_clauses.append({"term": {"resource_type": resource_type}})

    if start_date or end_date:
        range_clause: dict[str, Any] = {}
        if start_date:
            range_clause["gte"] = start_date.isoformat()
        if end_date:
            range_clause["lte"] = end_date.isoformat()
        must_clauses.append({"range": {"timestamp": range_clause}})

    query = {
        "query": {"bool": {"must": must_clauses}},
        "sort": [{"timestamp": {"order": "desc"}}],
        "size": min(size, 1000),  # Cap at 1000 for safety
    }

    try:
        result = await client.search(index=read_alias, body=query)
        hits = result["hits"]
        return {
            "total": hits["total"]["value"],
            "events": [hit["_source"] for hit in hits["hits"]],
            "source": "elasticsearch",
        }
    except NotFoundError:
        return {"total": 0, "events": [], "source": "elasticsearch"}
    except Exception as e:
        logger.error("audit_search_failed", error=str(e))
        return {"total": 0, "events": [], "source": "error"}
