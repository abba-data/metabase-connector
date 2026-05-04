from __future__ import annotations

from fastapi import Request

from connector.errors import ForbiddenError, UnauthorizedError
from connector.models import ConsumerIdentity, Scope


def require_scope(required: Scope):
    """FastAPI dependency factory enforcing per-route scope.

    Use as `Depends(require_scope(Scope.GENERAL))` on each catalog RPC route.
    Reads `request.state.consumer` populated by APIKeyAuthMiddleware.
    """

    async def _dep(request: Request) -> ConsumerIdentity:
        consumer: ConsumerIdentity | None = getattr(request.state, "consumer", None)
        if consumer is None:
            raise UnauthorizedError("Consumer identity not populated.")
        if required not in consumer.scope:
            raise ForbiddenError(
                f"Scope {required.value!r} required; caller has {sorted(s.value for s in consumer.scope)}.",
            )
        return consumer

    return _dep
