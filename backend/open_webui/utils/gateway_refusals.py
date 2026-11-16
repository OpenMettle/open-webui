"""Remember which users the workstation gateway refused, and say so plainly.

The gateway (an OpenAI-compatible connection whose URL ends in ``/webui/v1``)
answers a chat account that has no gateway key with 403
``browser_user_not_provisioned``, on the per-user model list and on chat calls.
Open WebUI then either has no models for that user ("Model '' was not found") or
passes the raw code through. A per-account refusal is kept per user and
connection, in a bounded cache with a short TTL, so a chat or title request can
say "ask a parent". Only the gateway's error code is stored: never headers or keys.

Other refusals are not per-account and are never shown as such: for example 401
``invalid_application_credential`` means Open WebUI's own service key is wrong
for everyone, so it keeps the upstream error and gets a clear log line.
"""

import logging
import time
from collections import OrderedDict
from urllib.parse import urlparse

log = logging.getLogger(__name__)

NOT_SET_UP_MESSAGE = "This account isn't set up for chat yet — please ask a parent."

GATEWAY_PATH_SUFFIX = '/webui/v1'
# Gateway codes that mean "this account has no key", as opposed to a fault that affects everyone.
ACCOUNT_REFUSAL_CODES = frozenset({'browser_user_not_provisioned'})
REFUSAL_STATUSES = (401, 403)
REFUSAL_TTL_SECONDS = 300
REFUSAL_MAX_ENTRIES = 1024

# (user id, connection base URL) -> (gateway error code, expiry on the monotonic clock), oldest first.
_refusals: OrderedDict[tuple[str, str], tuple[str, float]] = OrderedDict()


def _base_url(url) -> str:
    return str(url or '').rstrip('/').removesuffix('/models').rstrip('/')


def is_gateway_url(url) -> bool:
    return urlparse(_base_url(url)).path.endswith(GATEWAY_PATH_SUFFIX)


def gateway_error_code(body) -> str | None:
    """The ``error.code`` of a gateway error body such as ``{"error": {"code": "..."}}``."""
    error = body.get('error') if isinstance(body, dict) else None
    code = error.get('code') if isinstance(error, dict) else None
    return code if isinstance(code, str) and code else None


def _remember(user_id: str, base: str, code: str) -> None:
    key = (user_id, base)
    _refusals.pop(key, None)
    _refusals[key] = (code, time.monotonic() + REFUSAL_TTL_SECONDS)
    while len(_refusals) > REFUSAL_MAX_ENTRIES:
        _refusals.popitem(last=False)


def record_gateway_response(user, url, status: int, body) -> bool:
    """Note a gateway answer for the user. True when it is a per-account refusal.

    Only the gateway connection counts. A refusal is remembered; a success clears
    only that connection's entry, so another connection's 200 cannot hide it.
    """
    user_id = getattr(user, 'id', None)
    if not user_id or not is_gateway_url(url):
        return False
    base = _base_url(url)

    if status in REFUSAL_STATUSES:
        code = gateway_error_code(body)
        if code is None:
            return False
        if code in ACCOUNT_REFUSAL_CODES:
            log.warning('Gateway refused user %s: HTTP %s %s', user_id, status, code)
            _remember(user_id, base, code)
            return True
        log.error('Gateway refused Open WebUI itself, not one account: HTTP %s %s', status, code)
    elif 200 <= status < 300:
        _refusals.pop((user_id, base), None)
    return False


def refusal_code(user) -> str | None:
    """The gateway code of the user's recent refusal on any connection, if it has not expired."""
    user_id = getattr(user, 'id', None)
    if not user_id:
        return None
    now = time.monotonic()
    found = None
    for key in [k for k in _refusals if k[0] == user_id]:
        code, expiry = _refusals[key]
        if expiry <= now:
            del _refusals[key]
        else:
            found = code
    return found


def model_unavailable_message(user, fallback: str) -> str:
    """The clear message for a refused account, otherwise ``fallback`` (upstream behaviour)."""
    code = refusal_code(user)
    if code is None:
        return fallback
    log.warning('Model request from user %s with no models: gateway refused the account (%s)', user.id, code)
    return NOT_SET_UP_MESSAGE


def refused_chat_response(user, url, status: int, body):
    """The error body to return for a chat call the gateway refused for this account, else None."""
    if status not in REFUSAL_STATUSES or not record_gateway_response(user, url, status, body):
        return None
    code = gateway_error_code(body)
    return {'error': {'message': NOT_SET_UP_MESSAGE, 'code': code}, 'detail': NOT_SET_UP_MESSAGE}


def clear_refusals() -> None:
    _refusals.clear()
