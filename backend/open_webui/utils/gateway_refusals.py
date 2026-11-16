"""Remember which users a connection's gateway refused (HTTP 401/403 with an error code).

The workstation gateway answers a per-user model listing with 403
``browser_user_not_provisioned`` for a chat account that has no gateway key.
Open WebUI then has no models for that user, and the generic "Model '' was not
found" tells nobody what is wrong. The refusal is kept per user, in a bounded
cache with a short TTL, so a chat or title request that cannot find its model can
say so plainly. Only the gateway's error code is stored: never headers or keys.
"""

import logging
import time
from collections import OrderedDict

log = logging.getLogger(__name__)

NOT_SET_UP_MESSAGE = "This account isn't set up for chat yet — please ask a parent."

REFUSAL_STATUSES = (401, 403)
REFUSAL_TTL_SECONDS = 300
REFUSAL_MAX_USERS = 1024

# user id -> (gateway error code, expiry on the monotonic clock), oldest first.
_refusals: OrderedDict[str, tuple[str, float]] = OrderedDict()


def gateway_error_code(body) -> str | None:
    """The ``error.code`` of a gateway error body such as ``{"error": {"code": "..."}}``."""
    error = body.get('error') if isinstance(body, dict) else None
    code = error.get('code') if isinstance(error, dict) else None
    return code if isinstance(code, str) and code else None


def record_model_list_response(user, status: int, body) -> None:
    """Note a refused model listing for the user, or forget it when the listing succeeds."""
    user_id = getattr(user, 'id', None)
    if not user_id:
        return

    if status in REFUSAL_STATUSES:
        code = gateway_error_code(body)
        if code is None:
            return
        log.warning('Model listing refused for user %s by the gateway: HTTP %s %s', user_id, status, code)
        _refusals.pop(user_id, None)
        _refusals[user_id] = (code, time.monotonic() + REFUSAL_TTL_SECONDS)
        while len(_refusals) > REFUSAL_MAX_USERS:
            _refusals.popitem(last=False)
    elif 200 <= status < 300:
        _refusals.pop(user_id, None)


def refusal_code(user) -> str | None:
    """The gateway code of the user's recent refusal, if it has not expired."""
    user_id = getattr(user, 'id', None)
    entry = _refusals.get(user_id) if user_id else None
    if entry is None:
        return None
    if entry[1] <= time.monotonic():
        _refusals.pop(user_id, None)
        return None
    return entry[0]


def model_unavailable_message(user, fallback: str) -> str:
    """The clear message for a refused account, otherwise ``fallback`` (upstream behaviour)."""
    code = refusal_code(user)
    if code is None:
        return fallback
    log.warning('Model request from user %s with no models: gateway refused the listing (%s)', user.id, code)
    return NOT_SET_UP_MESSAGE


def clear_refusals() -> None:
    _refusals.clear()
