"""Shared effective standard-tier pricing lookup; no reservation or fallback policy."""

from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agent_runtime.infrastructure.models import PricingCatalog


async def standard_price(session: AsyncSession, provider: str, model: str) -> PricingCatalog | None:
    price: PricingCatalog | None = await session.scalar(
        select(PricingCatalog)
        .where(
            PricingCatalog.provider == provider,
            PricingCatalog.model == model,
            PricingCatalog.context_tier == "standard",
            PricingCatalog.service_tier == "standard",
            PricingCatalog.effective_at <= datetime.now(UTC),
        )
        .order_by(PricingCatalog.effective_at.desc())
        .limit(1)
    )
    return price
