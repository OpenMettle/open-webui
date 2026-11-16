"""An account the gateway refuses (403 browser_user_not_provisioned) gets a clear message.

Run inside the Open WebUI image (the module imports the app configuration):
    python -m unittest open_webui.test.test_gateway_refusals
"""

import importlib
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from fastapi import HTTPException
from open_webui.routers import openai, tasks
from open_webui.utils import gateway_refusals
from open_webui.utils.gateway_refusals import NOT_SET_UP_MESSAGE

main = importlib.import_module('open_webui.main')  # `open_webui.main` as an attribute is the CLI entry point

GATEWAY = 'http://litellm:4000/webui/v1'
OTHER = 'https://api.example.test/v1'
BODY = {'error': {'code': 'browser_user_not_provisioned', 'message': 'no key for this account'}}
CREDENTIAL_BODY = {'error': {'code': 'invalid_application_credential', 'message': 'bad service key'}}
CHILD = SimpleNamespace(id='child-1', name='Child', role='user', email='child@example.test')
PARENT = SimpleNamespace(id='parent-1', name='Parent', role='user', email='parent@example.test')


class FakeResponse:
    def __init__(self, status, body, content_type='application/json'):
        self.status = status
        self._body = body
        self.headers = {'Content-Type': content_type}

    async def json(self, loads=None):
        return self._body

    async def text(self):
        import json

        return json.dumps(self._body)

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False


class FakeSession:
    def __init__(self, response):
        self._response = response

    def get(self, *args, **kwargs):
        return self._response

    async def request(self, *args, **kwargs):
        return self._response

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False


async def list_models(user, status, body, base=GATEWAY):
    with patch.object(openai.aiohttp, 'ClientSession', lambda *a, **k: FakeSession(FakeResponse(status, body))):
        return await openai.send_get_request(url=f'{base}/models', key='unused', user=user)


def chat_request(models):
    return SimpleNamespace(
        app=SimpleNamespace(state=SimpleNamespace(OPENAI_MODELS=models, MODELS=models)), state=SimpleNamespace()
    )


async def chat(user, status, body, stream, base=GATEWAY):
    """A chat call that reaches the connection, with the shared model list already populated."""
    content_type = 'text/event-stream' if stream else 'application/json'
    response = FakeResponse(status, body, content_type)
    request = chat_request({'Qwen': {'id': 'Qwen', 'urlIdx': 0}})
    with (
        patch.object(openai.Config, 'get', new=AsyncMock(return_value=True)),
        patch.object(openai.Models, 'get_model_by_id', new=AsyncMock(return_value=None)),
        patch.object(openai, 'check_model_access', new=AsyncMock()),
        patch.object(openai, 'get_openai_connection', new=AsyncMock(return_value=(base, 'unused', {}))),
        patch.object(openai, 'get_headers_and_cookies', new=AsyncMock(return_value=({}, None))),
        patch.object(openai, 'get_session', new=AsyncMock(return_value=FakeSession(response))),
        patch.object(openai, 'cleanup_response', new=AsyncMock()),
        patch.object(openai, 'publish_model_provider_request_failed', new=AsyncMock()),
    ):
        return await openai.generate_chat_completion(
            request, {'model': 'Qwen', 'messages': [{'role': 'user', 'content': 'hi'}], 'stream': stream}, user=user
        )


class GatewayRefusalTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        gateway_refusals.clear_refusals()

    async def test_refused_listing_is_remembered_per_user(self):
        self.assertEqual(BODY, await list_models(CHILD, 403, BODY))
        self.assertEqual('browser_user_not_provisioned', gateway_refusals.refusal_code(CHILD))
        self.assertIsNone(gateway_refusals.refusal_code(PARENT))
        self.assertEqual(NOT_SET_UP_MESSAGE, gateway_refusals.model_unavailable_message(CHILD, 'x'))
        self.assertEqual('x', gateway_refusals.model_unavailable_message(PARENT, 'x'))

    async def test_only_per_account_codes_count(self):
        # 401 invalid_application_credential is Open WebUI's own key: everyone is affected.
        with self.assertLogs(gateway_refusals.log, 'ERROR') as logs:
            await list_models(CHILD, 401, CREDENTIAL_BODY)
        self.assertIn('invalid_application_credential', '\n'.join(logs.output))
        self.assertIsNone(gateway_refusals.refusal_code(CHILD))
        await list_models(CHILD, 403, {'error': {'code': 'image_permission_denied'}})
        await list_models(CHILD, 403, {'detail': 'Forbidden'})
        self.assertIsNone(gateway_refusals.refusal_code(CHILD))

    async def test_other_connections_are_ignored(self):
        await list_models(CHILD, 403, BODY, base=OTHER)
        self.assertIsNone(gateway_refusals.refusal_code(CHILD))

    async def test_success_on_another_connection_does_not_clear_a_refusal(self):
        await list_models(CHILD, 403, BODY)
        await list_models(CHILD, 200, {'data': [{'id': 'm'}]}, base='http://second:4000/webui/v1')
        await list_models(CHILD, 200, {'data': [{'id': 'm'}]}, base=OTHER)
        self.assertEqual('browser_user_not_provisioned', gateway_refusals.refusal_code(CHILD))
        await list_models(CHILD, 200, {'data': [{'id': 'm'}]})
        self.assertIsNone(gateway_refusals.refusal_code(CHILD))

    async def test_refusal_expires(self):
        await list_models(CHILD, 403, BODY)
        with patch.object(gateway_refusals.time, 'monotonic', return_value=10**9):
            self.assertIsNone(gateway_refusals.refusal_code(CHILD))

    async def test_cache_is_bounded(self):
        for n in range(gateway_refusals.REFUSAL_MAX_ENTRIES + 5):
            gateway_refusals.record_gateway_response(SimpleNamespace(id=f'u{n}'), GATEWAY, 403, BODY)
        self.assertEqual(gateway_refusals.REFUSAL_MAX_ENTRIES, len(gateway_refusals._refusals))
        self.assertIsNone(gateway_refusals.refusal_code(SimpleNamespace(id='u0')))

    async def test_log_has_the_code_but_no_key(self):
        with self.assertLogs(gateway_refusals.log, 'WARNING') as logs:
            await list_models(CHILD, 403, BODY)
        text = '\n'.join(logs.output)
        self.assertIn('browser_user_not_provisioned', text)
        self.assertNotIn('unused', text)

    async def test_chat_without_models_says_account_is_not_set_up(self):
        await list_models(CHILD, 403, BODY)
        with (
            patch.object(openai.Config, 'get', new=AsyncMock(return_value=True)),
            patch.object(openai.Models, 'get_model_by_id', new=AsyncMock(return_value=None)),
            patch.object(openai, 'check_model_access', new=AsyncMock()),
            patch.object(openai, 'get_all_models', new=AsyncMock()),
        ):
            with self.assertRaises(HTTPException) as raised:
                await openai.generate_chat_completion(chat_request({}), {'model': 'Qwen'}, user=CHILD)
        self.assertEqual(NOT_SET_UP_MESSAGE, raised.exception.detail)

    async def test_normal_provider_keeps_upstream_error_and_names_the_model(self):
        with (
            patch.object(openai.Config, 'get', new=AsyncMock(return_value=True)),
            patch.object(openai.Models, 'get_model_by_id', new=AsyncMock(return_value=None)),
            patch.object(openai, 'check_model_access', new=AsyncMock()),
            patch.object(openai, 'get_all_models', new=AsyncMock()),
        ):
            with self.assertRaises(HTTPException) as raised:
                await openai.generate_chat_completion(chat_request({}), {'model': 'Qwen'}, user=PARENT)
        self.assertEqual("Model 'Qwen' was not found", raised.exception.detail)

    async def test_refused_chat_with_the_shared_model_list_already_populated(self):
        # A provisioned user filled the shared model list, so the child's chat reaches the gateway.
        for stream in (False, True):
            gateway_refusals.clear_refusals()
            reply = await chat(CHILD, 403, BODY, stream)
            self.assertEqual(403, reply.status_code, stream)
            self.assertIn(NOT_SET_UP_MESSAGE.encode(), reply.body, stream)
            self.assertEqual('browser_user_not_provisioned', gateway_refusals.refusal_code(CHILD), stream)

    async def test_application_credential_failure_keeps_the_upstream_error_in_chat(self):
        for stream in (False, True):
            reply = await chat(CHILD, 401, CREDENTIAL_BODY, stream)
            self.assertEqual(401, reply.status_code, stream)
            self.assertIn(b'invalid_application_credential', reply.body, stream)
            self.assertNotIn(NOT_SET_UP_MESSAGE.encode(), reply.body, stream)
            self.assertIsNone(gateway_refusals.refusal_code(CHILD), stream)

    async def test_refusal_from_another_connection_is_not_rewritten(self):
        reply = await chat(CHILD, 403, BODY, False, base=OTHER)
        self.assertEqual(403, reply.status_code)
        self.assertNotIn(NOT_SET_UP_MESSAGE.encode(), reply.body)

    async def test_chat_entry_says_account_is_not_set_up(self):
        await list_models(CHILD, 403, BODY)
        request = SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(MODELS={'other': {}})), state=SimpleNamespace())
        with self.assertRaises(HTTPException) as raised:
            await main.chat_completion(request, {'model': 'Qwen', 'messages': []}, user=CHILD)
        self.assertEqual(NOT_SET_UP_MESSAGE, raised.exception.detail)
        with self.assertRaises(HTTPException) as raised:
            await main.chat_completion(request, {'model': 'Qwen', 'messages': []}, user=PARENT)
        self.assertEqual("Model 'Qwen' was not found", raised.exception.detail)

    async def test_title_for_refused_account_fails_quietly_and_others_get_404(self):
        await list_models(CHILD, 403, BODY)
        request = SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(MODELS={})), state=SimpleNamespace())
        with patch.object(tasks.Config, 'get', new=AsyncMock(return_value=True)):
            quiet = await tasks.generate_title(request, {'model': 'Qwen'}, user=CHILD)
            self.assertEqual(200, quiet.status_code)
            with self.assertRaises(HTTPException) as raised:
                await tasks.generate_title(request, {'model': 'Qwen'}, user=PARENT)
        self.assertEqual(404, raised.exception.status_code)
        self.assertEqual("Model 'Qwen' was not found", raised.exception.detail)


if __name__ == '__main__':
    unittest.main()
