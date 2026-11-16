"""An account the gateway refuses (403 browser_user_not_provisioned) gets a clear message.

Run inside the Open WebUI image (the module imports the app configuration):
    python -m unittest open_webui.test.test_gateway_refusals
"""

import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from fastapi import HTTPException
from open_webui.routers import openai, tasks
from open_webui.utils import gateway_refusals
from open_webui.utils.gateway_refusals import NOT_SET_UP_MESSAGE

BODY = {'error': {'code': 'browser_user_not_provisioned', 'message': 'no key for this account'}}
CHILD = SimpleNamespace(id='child-1', name='Child', role='user', email='child@example.test')
OTHER = SimpleNamespace(id='parent-1', name='Parent', role='user', email='parent@example.test')


class FakeResponse:
    def __init__(self, status, body):
        self.status = status
        self._body = body

    async def json(self, loads=None):
        return self._body

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False


class FakeSession:
    def __init__(self, status, body):
        self._response = FakeResponse(status, body)

    def get(self, *args, **kwargs):
        return self._response

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False


async def list_models(user, status, body):
    with patch.object(openai.aiohttp, 'ClientSession', lambda *a, **k: FakeSession(status, body)):
        return await openai.send_get_request(url='http://gateway/webui/v1/models', key='unused', user=user)


class GatewayRefusalTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        gateway_refusals.clear_refusals()

    async def test_refused_listing_is_remembered_per_user(self):
        self.assertEqual(BODY, await list_models(CHILD, 403, BODY))
        self.assertEqual('browser_user_not_provisioned', gateway_refusals.refusal_code(CHILD))
        self.assertIsNone(gateway_refusals.refusal_code(OTHER))
        self.assertEqual(NOT_SET_UP_MESSAGE, gateway_refusals.model_unavailable_message(CHILD, 'x'))
        self.assertEqual('x', gateway_refusals.model_unavailable_message(OTHER, 'x'))

    async def test_401_with_a_code_counts_and_a_refusal_without_one_does_not(self):
        await list_models(CHILD, 401, {'error': {'code': 'key_revoked'}})
        self.assertEqual('key_revoked', gateway_refusals.refusal_code(CHILD))
        await list_models(OTHER, 403, {'detail': 'Forbidden'})
        self.assertIsNone(gateway_refusals.refusal_code(OTHER))

    async def test_successful_listing_clears_the_refusal(self):
        await list_models(CHILD, 403, BODY)
        await list_models(CHILD, 200, {'data': [{'id': 'm'}]})
        self.assertIsNone(gateway_refusals.refusal_code(CHILD))

    async def test_refusal_expires(self):
        await list_models(CHILD, 403, BODY)
        with patch.object(gateway_refusals.time, 'monotonic', return_value=10**9):
            self.assertIsNone(gateway_refusals.refusal_code(CHILD))

    async def test_cache_is_bounded(self):
        for n in range(gateway_refusals.REFUSAL_MAX_USERS + 5):
            gateway_refusals.record_model_list_response(SimpleNamespace(id=f'u{n}'), 403, BODY)
        self.assertEqual(gateway_refusals.REFUSAL_MAX_USERS, len(gateway_refusals._refusals))
        self.assertIsNone(gateway_refusals.refusal_code(SimpleNamespace(id='u0')))

    async def test_log_has_the_code_but_no_key(self):
        with self.assertLogs(gateway_refusals.log, 'WARNING') as logs:
            await list_models(CHILD, 403, BODY)
        text = '\n'.join(logs.output)
        self.assertIn('browser_user_not_provisioned', text)
        self.assertNotIn('unused', text)

    async def test_chat_without_models_says_account_is_not_set_up(self):
        await list_models(CHILD, 403, BODY)
        request = SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(OPENAI_MODELS={})), state=SimpleNamespace())
        with (
            patch.object(openai.Config, 'get', new=AsyncMock(return_value=True)),
            patch.object(openai.Models, 'get_model_by_id', new=AsyncMock(return_value=None)),
            patch.object(openai, 'check_model_access', new=AsyncMock()),
            patch.object(openai, 'get_all_models', new=AsyncMock()),
        ):
            with self.assertRaises(HTTPException) as raised:
                await openai.generate_chat_completion(request, {'model': 'Qwen'}, user=CHILD)
        self.assertEqual(NOT_SET_UP_MESSAGE, raised.exception.detail)

    async def test_normal_provider_keeps_upstream_error_and_names_the_model(self):
        request = SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(OPENAI_MODELS={})), state=SimpleNamespace())
        with (
            patch.object(openai.Config, 'get', new=AsyncMock(return_value=True)),
            patch.object(openai.Models, 'get_model_by_id', new=AsyncMock(return_value=None)),
            patch.object(openai, 'check_model_access', new=AsyncMock()),
            patch.object(openai, 'get_all_models', new=AsyncMock()),
        ):
            with self.assertRaises(HTTPException) as raised:
                await openai.generate_chat_completion(request, {'model': 'Qwen'}, user=OTHER)
        self.assertEqual("Model 'Qwen' was not found", raised.exception.detail)

    async def test_title_for_refused_account_fails_quietly_and_others_get_404(self):
        await list_models(CHILD, 403, BODY)
        request = SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(MODELS={})), state=SimpleNamespace())
        with patch.object(tasks.Config, 'get', new=AsyncMock(return_value=True)):
            quiet = await tasks.generate_title(request, {'model': 'Qwen'}, user=CHILD)
            self.assertEqual(200, quiet.status_code)
            with self.assertRaises(HTTPException) as raised:
                await tasks.generate_title(request, {'model': 'Qwen'}, user=OTHER)
        self.assertEqual(404, raised.exception.status_code)
        self.assertEqual("Model 'Qwen' was not found", raised.exception.detail)


if __name__ == '__main__':
    unittest.main()
