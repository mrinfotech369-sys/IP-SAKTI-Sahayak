"""Thin adapter over rag.embeddings.provider using app settings."""
import logging

from app.core.config import settings
from rag.embeddings.provider import EmbeddingProvider, get_embedding_provider

logger = logging.getLogger("ipsakti.embeddings")


def get_embedder() -> EmbeddingProvider:
    try:
        return get_embedding_provider(settings.EMBEDDING_PROVIDER)
    except Exception as exc:  # missing key / model -> degrade, don't crash
        logger.error("Embedding provider '%s' unavailable (%s); using hashing.", settings.EMBEDDING_PROVIDER, exc)
        return get_embedding_provider("hashing")
