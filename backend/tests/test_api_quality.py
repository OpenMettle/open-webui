"""Offline regressions for reasoning replay and caller/server tool ownership."""

import copy
import importlib
import json
import unittest
from contextlib import ExitStack
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

from api_quality_support import middleware as mw
from api_quality_support import models
from starlette.requests import Request
from starlette.responses import StreamingResponse

PRIVATE = 'synthetic-private-reasoning'
SPEC = {'name': 'lookup', 'parameters': {'type': 'object', 'properties': {'key': {'type': 'string'}}}}
TOOLS = [{'type': 'function', 'function': SPEC}]


def call(call_id, key):
    return {'id': call_id, 'type': 'function', 'function': {'name': 'lookup', 'arguments': json.dumps({'key': key})}}


def stream(*deltas, finish='tool_calls'):
    async def body():
        for delta in deltas:
            yield 'data: ' + json.dumps({'choices': [{'delta': delta, 'finish_reason': None}]}) + '\n\n'
        yield 'data: ' + json.dumps({'choices': [{'delta': {}, 'finish_reason': finish}]}) + '\n\n'
        yield 'data: [DONE]\n\n'

    return StreamingResponse(body(), media_type='text/event-stream')


def round_stream(number):
    calls = [call('a', 'first'), call('b', 'second')] if number == 1 else [call('c', 'third')]
    return stream(
        {'content': '', 'reasoning_content': PRIVATE + str(number)},
        {'tool_calls': [{**item, 'index': index} for index, item in enumerate(calls)]},
    )


class ApiQualityTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.stack = ExitStack()
        self.addCleanup(self.stack.close)
        self.model = {'id': 'fixture-model', 'owned_by': 'openai', 'provider': 'llama.cpp'}
        self.request = SimpleNamespace(
            state=SimpleNamespace(),
            app=SimpleNamespace(state=SimpleNamespace(MODELS={self.model['id']: self.model}, redis=None)),
        )
        self.user = SimpleNamespace(id='fixture-user', role='admin')
        self.events = []
        self.emitter = AsyncMock(side_effect=lambda event: self.events.append(copy.deepcopy(event)))

        async def config_get(key, default=None):
            return default

        self.patch(
            'Config', SimpleNamespace(get=AsyncMock(side_effect=config_get), get_many=AsyncMock(return_value={}))
        )
        self.patch('get_event_emitter', AsyncMock(return_value=None))
        self.patch('get_event_call', AsyncMock(return_value=None))
        self.patch('get_system_oauth_token', AsyncMock(return_value=None))
        self.patch('process_pipeline_inlet_filter', AsyncMock(side_effect=lambda request, body, *args: body))
        self.patch('get_task_model_id', Mock(return_value=self.model['id']))
        self.patch('set_tool_approval_prompt', Mock(side_effect=lambda messages, *args: messages))
        self.patch('has_prior_user_message', Mock(return_value=True))
        self.patch('apply_skills_create_prompt', Mock(return_value=False))
        self.patch('extract_skill_ids_from_messages', Mock(return_value=set()))
        self.patch('strip_skill_mentions', Mock())
        self.patch('filter_user_terminal_tools', AsyncMock())
        self.patch('get_terminal_connections', AsyncMock(return_value=[]))
        self.patch('is_file_context_enabled', Mock(return_value=False))
        self.patch('FilterContext', SimpleNamespace)
        self.patch('process_filter_functions', AsyncMock(side_effect=lambda **kw: (kw['form_data'], {})))
        self.patch('save_response_stream', AsyncMock(return_value=0))
        self.patch('clear_response_stream', AsyncMock())
        self.patch('log_model_usage', Mock())
        self.patch('outlet_filter_handler', AsyncMock())
        self.patch('background_tasks_handler', AsyncMock())

    def patch(self, name, value):
        return self.stack.enter_context(patch.object(mw, name, value))

    async def payload(self, extra=None, metadata=None, messages=None):
        body = {'model': self.model['id'], 'messages': messages or [{'role': 'user', 'content': 'fixture'}]}
        body.update(extra or {})
        return await mw.process_chat_payload(self.request, body, self.user, metadata or {}, self.model)

    def context(self, body, metadata, emitter=None):
        return {
            'request': self.request,
            'form_data': body,
            'user': self.user,
            'model': self.model,
            'metadata': metadata,
            'tasks': {},
            'events': [],
            'event_emitter': emitter,
            'event_caller': None,
        }

    async def test_raw_reasoning_survives_for_strict_and_compatible_providers(self):
        history = [
            {'role': 'user', 'content': 'fixture'},
            {'role': 'assistant', 'content': '', 'reasoning_content': PRIVATE, 'tool_calls': [call('a', 'first')]},
            {'role': 'tool', 'content': 'result', 'tool_call_id': 'a'},
            {'role': 'assistant', 'content': None, 'reasoning_content': PRIVATE + '2'},
        ]
        for provider in ('llama.cpp', 'openai'):
            with self.subTest(provider=provider):
                self.model['provider'] = provider
                body, *_ = await self.payload({'tools': []}, messages=copy.deepcopy(history))
                self.assertEqual(body['messages'], history)

    async def test_raw_messages_reach_actual_openai_route_unchanged(self):
        router = importlib.import_module('open_webui.routers.openai')
        history = [
            {'role': 'user', 'content': 'fixture'},
            {'role': 'assistant', 'content': '', 'reasoning_content': PRIVATE, 'tool_calls': [call('a', 'first')]},
            {'role': 'tool', 'tool_call_id': 'a', 'content': 'result'},
        ]
        self.request.app.state.OPENAI_MODELS = {self.model['id']: {'urlIdx': 0}}
        upstream = SimpleNamespace(status=200, headers={}, json=AsyncMock(return_value={'choices': []}))
        session = SimpleNamespace(request=AsyncMock(return_value=upstream))
        with ExitStack() as stack:
            for name, value in {
                'Config': SimpleNamespace(get=AsyncMock(return_value=True)),
                'Models': SimpleNamespace(get_model_by_id=AsyncMock(return_value=None)),
                'check_model_access': AsyncMock(),
                'get_openai_connection': AsyncMock(return_value=('https://fixture.invalid/v1', '', {})),
                'get_headers_and_cookies': AsyncMock(return_value=({}, None)),
                'get_session': AsyncMock(return_value=session),
                'get_client_timeout': Mock(return_value=None),
                'cleanup_response': AsyncMock(),
            }.items():
                stack.enter_context(patch.object(router, name, value))
            for provider in ('openai', 'llama.cpp'):
                self.model['provider'] = provider
                body, *_ = await self.payload({'tools': TOOLS}, messages=copy.deepcopy(history))
                await router.generate_chat_completion(self.request, body, self.user)
                forwarded = json.loads(session.request.call_args.kwargs['data'])
                self.assertEqual(forwarded['messages'], history)
                self.assertEqual(forwarded['tools'], TOOLS)
                self.assertNotIn('metadata', forwarded)

    async def test_provider_identity_comes_from_connection_not_catalogue(self):
        router = importlib.import_module('open_webui.routers.openai')
        for configured, expected in (({}, None), ({'provider': 'llama.cpp'}, 'reasoning_content')):
            with (
                self.subTest(configured=configured),
                patch.object(
                    router,
                    'get_openai_runtime_config',
                    AsyncMock(return_value=(True, ['https://fixture.invalid/v1'], [''], {'0': configured})),
                ),
                patch.object(
                    router,
                    'get_all_models_responses',
                    AsyncMock(return_value=[{'data': [{'id': 'fixture', 'provider': 'llama.cpp'}]}]),
                ),
            ):
                result = await router.get_all_models.__wrapped__(self.request, self.user)
                self.assertEqual(mw.get_reasoning_format(result['data'][0]), expected)

    async def test_request_diagnostics_do_not_log_reasoning(self):
        chat = importlib.import_module('open_webui.utils.chat')
        boundary = AsyncMock(return_value={'choices': []})
        with patch.object(mw.log, 'debug') as debug:
            body, *_ = await self.payload(
                {'tools': []}, messages=[{'role': 'assistant', 'content': '', 'reasoning_content': PRIVATE}]
            )
        self.assertNotIn(PRIVATE, str(debug.call_args_list))
        with patch.object(chat, 'generate_openai_chat_completion', boundary), patch.object(chat.log, 'debug') as debug:
            await chat.generate_chat_completion(self.request, body, self.user)
        self.assertNotIn(PRIVATE, str(debug.call_args_list))
        self.assertEqual(boundary.call_args.kwargs['form_data']['messages'][0]['reasoning_content'], PRIVATE)

    async def test_audit_retains_metadata_and_usage_without_reasoning(self):
        audit = importlib.import_module('open_webui.utils.audit')
        request = Request(
            {
                'type': 'http',
                'method': 'POST',
                'path': '/api/chat/completions',
                'scheme': 'http',
                'server': ('fixture.invalid', 80),
                'headers': [],
                'query_string': b'',
                'state': {'audit_request_id': 'fixture-request', 'audit_level': 'REQUEST_RESPONSE'},
            }
        )
        logger = Mock()
        auditor = audit.AuditLoggingMiddleware(AsyncMock(), audit_level=audit.AuditLevel.REQUEST_RESPONSE)
        auditor.audit_logger = logger
        auditor._get_authenticated_user = AsyncMock(return_value=None)
        context = audit.AuditContext()
        context.metadata['response_status_code'] = 200
        context.add_request_chunk(
            json.dumps(
                {
                    'messages': [
                        {
                            'role': 'assistant',
                            'content': 'public',
                            'reasoning_content': PRIVATE,
                            'reasoning': PRIVATE,
                            'thinking': PRIVATE,
                            'reasoning_details': [{'text': PRIVATE}],
                        }
                    ]
                }
            ).encode()
        )
        context.add_response_chunk(
            (
                'data: '
                + json.dumps({'type': 'response.reasoning_text.delta', 'delta': PRIVATE})
                + '\n\ndata: [DONE]\n\n'
            ).encode()
        )
        await auditor._log_audit_entry(request, context)
        entry = logger.write.call_args.args[0]
        self.assertEqual(entry.response_status_code, 200)
        self.assertEqual(entry.id, 'fixture-request')
        self.assertIn('public', entry.request_object)
        self.assertNotIn(PRIVATE, str(entry))
        self.assertNotIn(
            PRIVATE,
            audit.redact_chat_reasoning(
                json.dumps(
                    {'output': [{'type': 'reasoning', 'summary': [{'text': PRIVATE}], 'content': [{'text': PRIVATE}]}]}
                )
            ),
        )
        self.assertNotIn(PRIVATE, audit.redact_chat_reasoning('{"reasoning_content":"' + PRIVATE))
        self.assertNotIn(PRIVATE, audit.redact_chat_reasoning('data: {"reasoning_content":"' + PRIVATE))
        self.assertNotIn(PRIVATE, audit.redact_chat_reasoning('  data: ' + json.dumps({'reasoning_content': PRIVATE})))
        nested_reasoning = '[' * 600 + json.dumps({'reasoning_content': PRIVATE}) + ']' * 600
        self.assertNotIn(PRIVATE, audit.redact_chat_reasoning(nested_reasoning))
        with patch.object(audit.JSONCodec, 'loads', side_effect=RecursionError):
            self.assertEqual(
                audit.redact_chat_reasoning(json.dumps({'reasoning_content': PRIVATE})),
                '[redacted: incomplete or non-JSON audit body]',
            )
        user = SimpleNamespace(model_dump=lambda **kwargs: {'id': 'fixture-user'})
        with patch.object(audit, 'AuditLogger', return_value=logger):
            audit.log_model_usage(
                request,
                user,
                'fixture-model',
                {'prompt_tokens': 2, 'completion_tokens': 3, 'reasoning_content': PRIVATE},
            )
        usage_entry = logger.write.call_args.args[0]
        self.assertEqual(usage_entry.usage, {'input_tokens': 2, 'output_tokens': 3, 'total_tokens': 5})
        self.assertNotIn(PRIVATE, str(usage_entry))

    async def test_audit_redacts_nested_responses_reasoning_parts(self):
        audit = importlib.import_module('open_webui.utils.audit')
        for kind in ('reasoning_text', 'reasoning_summary_text'):
            for event in ('response.content_part.added', 'response.content_part.done'):
                payload = {
                    'type': event,
                    'part': {'type': kind, 'text': PRIVATE, 'nested': {'text': PRIVATE}},
                    'public': 'retained-public-metadata',
                }
                for body in (json.dumps(payload), 'data: ' + json.dumps(payload) + '\n\ndata: [DONE]\n\n'):
                    with self.subTest(kind=kind, event=event, body_type='SSE' if body.startswith('data:') else 'JSON'):
                        result = audit.redact_chat_reasoning(body)
                        self.assertNotIn(PRIVATE, result)
                        self.assertIn('retained-public-metadata', result)
                        self.assertIn(kind, result)

    async def test_every_audited_route_redacts_private_reasoning(self):
        audit = importlib.import_module('open_webui.utils.audit')
        for path in (
            '/api/v1/tasks/title/completions',
            '/ollama/api/generate',
            '/api/chat/completed',
            '/openai/responses',
            '/openai/chat/completions',
            '/api/v1/unrelated',
        ):
            with self.subTest(path=path):
                request = Request(
                    {
                        'type': 'http',
                        'method': 'POST',
                        'path': path,
                        'scheme': 'http',
                        'server': ('fixture.invalid', 80),
                        'headers': [],
                        'query_string': b'',
                        'state': {'audit_request_id': 'fixture-request'},
                    }
                )
                logger = Mock()
                auditor = audit.AuditLoggingMiddleware(AsyncMock(), audit_level=audit.AuditLevel.REQUEST_RESPONSE)
                auditor.audit_logger = logger
                auditor._get_authenticated_user = AsyncMock(return_value=None)
                context = audit.AuditContext()
                context.metadata['response_status_code'] = 200
                context.add_request_chunk(
                    json.dumps(
                        {
                            'model': 'opaque-fixture',
                            'messages': [{'reasoning_content': PRIVATE}],
                            'password': 'synthetic-secret',
                        }
                    ).encode()
                )
                context.add_response_chunk(
                    json.dumps(
                        {
                            'thinking': PRIVATE,
                            'reasoning_details': [{'text': PRIVATE}],
                            'output': [{'type': 'reasoning_summary_text', 'text': PRIVATE}],
                            'content': 'public answer',
                        }
                    ).encode()
                )
                await auditor._log_audit_entry(request, context)
                logger.write.assert_called_once()
                entry = logger.write.call_args.args[0]
                self.assertNotIn(PRIVATE, str(entry))
                self.assertNotIn('synthetic-secret', str(entry))
                self.assertIn('opaque-fixture', entry.request_object)
                self.assertIn('public answer', entry.response_object)
                self.assertEqual(entry.response_status_code, 200)
                self.assertEqual(entry.request_uri, 'http://fixture.invalid' + path)

    async def test_audit_preserves_unrelated_bodies_without_exposing_reasoning(self):
        audit = importlib.import_module('open_webui.utils.audit')
        private_text = 'synthetic-confidential-payload'
        self.assertNotRegex(private_text, r'(?i)reason|think|\\u')
        code = json.dumps({'password': 'synthetic-secret', 'content': 'recorded-code-header\n' + 'x' * 3000})
        multipart = '--fixture\r\nContent-Disposition: form-data; name="file"\r\n\r\nrecorded-upload\r\n--fixture--'
        unicode_body = '{"name": "José 日本", "enabled": true}'
        cases = [
            ('/api/v1/tools/create', code, 'recorded-code-header', False),
            ('/api/v1/functions/create', code, 'recorded-code-header', False),
            ('/api/v1/files/', multipart, multipart, False),
            ('/api/v1/tools/create', unicode_body, unicode_body, False),
            ('/api/v1/tools/id/fixture/update', code, 'recorded-code-header', False),
            ('/api/v1/functions/id/fixture/update/version', code, 'recorded-code-header', False),
            ('/api/v1/tools/create', '{"reasoning_content":"' + private_text + 'x' * 3000, None, True),
            ('/api/v1/functions/create', '{"\\u0072easoning_content":"' + private_text + '"}', None, True),
            ('/api/v1/unrelated', '{"reasoning_content":"' + private_text + 'x' * 3000, None, True),
            ('/api/v1/unrelated', '{"reasoning_content":"' + private_text + '"}', None, True),
            ('/api/v1/unrelated', '{"\\u0072easoning_content":"' + private_text + '"}', None, True),
            # A Responses item can put its text before the type, beyond the capture limit.
            ('/openai/responses', '{"part":{"text":"' + private_text + 'x' * 3000, None, True),
            ('/api/v1/tasks/title/completions', '{"text":"' + private_text + 'x' * 3000, None, True),
            ('/ollama/api/generate', '{"text":"' + private_text + 'x' * 3000, None, True),
            ('/api/chat/completed', '{"text":"' + private_text + 'x' * 3000, None, True),
        ]
        # Private text precedes its type beyond the capture limit. No marker can
        # activate the body-based guard; these cases must exercise route handling.
        for path in (
            '/ollama/api/chat/0',
            '/ollama/api/generate/0',
            '/ollama/v1/chat/completions/0',
            '/ollama/v1/responses/0',
            '/api/v1/messages',
            '/api/messages',
            '/api/message',
            '/ollama/v1/messages/0',
            '/openai/responses/subpath',
            '/api/v1/unknown',
            '/api/v1/tools/id/fixture/mcp/app/rpc',
            '/api/v1/functions/future-endpoint',
            '/api/v1/files/future-endpoint',
            '/api/v1/tools-proxy/responses/0',
            '/api/v1/files-proxy/responses/0',
            '/api/v1/functions-proxy/responses/0',
        ):
            cases.append((path, '{"part":{"text":"' + private_text + 'x' * 3000, None, True))
        for level in (audit.AuditLevel.REQUEST, audit.AuditLevel.REQUEST_RESPONSE):
            for path, body, retained, private in cases:
                with self.subTest(level=level, path=path, body=body[:40]):
                    request = Request(
                        {
                            'type': 'http',
                            'method': 'POST',
                            'path': path,
                            'scheme': 'http',
                            'server': ('fixture.invalid', 80),
                            'headers': [],
                            'query_string': b'',
                            'state': {'audit_request_id': 'fixture-request'},
                        }
                    )
                    auditor = audit.AuditLoggingMiddleware(AsyncMock(), audit_level=level)
                    auditor.audit_logger = Mock()
                    auditor._get_authenticated_user = AsyncMock(return_value=None)
                    context = audit.AuditContext(max_body_size=2048)
                    context.add_request_chunk(body.encode())
                    context.add_response_chunk(body.encode())
                    await auditor._log_audit_entry(request, context)
                    entry = auditor.audit_logger.write.call_args.args[0]
                    for observed in (entry.request_object, entry.response_object):
                        self.assertNotIn('synthetic-secret', observed)
                        if private:
                            self.assertNotIn(private_text, observed)
                            self.assertIn('redacted', observed)
                        else:
                            self.assertIn(retained, observed)
                            self.assertEqual(observed, audit.redact_secrets(context.request_body.decode()))

    async def test_caller_two_rounds_return_raw_reasoning_and_finish_reason(self):
        history = [{'role': 'user', 'content': 'fixture'}]
        execute = self.patch('execute_tool_call', AsyncMock(side_effect=AssertionError('caller tool executed')))
        for number in (1, 2):
            body, metadata, _, _ = await self.payload({'tools': TOOLS}, messages=copy.deepcopy(history))
            result = await mw.process_chat_response(round_stream(number), self.context(body, metadata))
            chunks = [chunk async for chunk in result.body_iterator]
            data = [json.loads(chunk.removeprefix('data:').strip()) for chunk in chunks if '[DONE]' not in chunk]
            choices = [choice for frame in data for choice in frame.get('choices', [])]
            reasoning = ''.join(choice['delta'].get('reasoning_content', '') for choice in choices)
            content = ''.join(choice['delta'].get('content') or '' for choice in choices)
            calls = [
                {key: value for key, value in item.items() if key != 'index'}
                for choice in choices
                for item in choice['delta'].get('tool_calls', [])
            ]
            self.assertEqual(reasoning, PRIVATE + str(number))
            self.assertEqual(content, '')
            self.assertEqual(choices[-1]['finish_reason'], 'tool_calls')
            history.append(
                {'role': 'assistant', 'content': content, 'reasoning_content': reasoning, 'tool_calls': calls}
            )
            history.extend({'role': 'tool', 'tool_call_id': item['id'], 'content': 'caller result'} for item in calls)
        body, *_ = await self.payload({'tools': TOOLS}, messages=copy.deepcopy(history))
        self.assertEqual(body['messages'], history)
        execute.assert_not_awaited()

    async def test_model_discovery_declares_effective_provider_including_presets(self):
        bases = [
            {'id': 'compatible', 'owned_by': 'openai', 'provider': 'llama.cpp'},
            {'id': 'Qwen3.8', 'owned_by': 'openai', 'provider_capabilities': {'reasoning_replay': 'reasoning_content'}},
            {'id': 'native', 'owned_by': 'ollama'},
        ]
        preset = SimpleNamespace(
            id='preset',
            base_model_id='compatible',
            is_active=True,
            name='Preset',
            created_at=0,
            params=SimpleNamespace(model_dump=lambda: {}),
            meta=None,
            model_dump=lambda: {'params': {}, 'meta': {}},
        )
        with ExitStack() as stack:
            for name, value in {
                'Config': mw.Config,
                'get_all_base_models': AsyncMock(return_value=bases),
                'publish_model_availability_events': AsyncMock(),
                'Models': SimpleNamespace(get_all_models=AsyncMock(return_value=[preset])),
                'Functions': SimpleNamespace(
                    get_functions_by_ids=AsyncMock(return_value=[]),
                    get_function_valves_by_ids=AsyncMock(return_value={}),
                ),
                'get_functions_cache': Mock(return_value={}),
                'get_chat_variables_schema': Mock(return_value=None),
            }.items():
                stack.enter_context(patch.object(models, name, value))
            result = await models.get_all_models(self.request)
        self.assertEqual(
            {m['id']: m['provider_capabilities']['reasoning_replay'] for m in result},
            {'compatible': 'reasoning_content', 'preset': 'reasoning_content', 'Qwen3.8': None, 'native': 'thinking'},
        )
        for model in result:
            self.assertEqual(model['provider_capabilities']['reasoning_replay'], mw.get_reasoning_format(model))

    async def test_explicit_tools_skip_resolution_including_empty_array_and_ids(self):
        resolver = self.patch('get_tools', AsyncMock(side_effect=AssertionError('server resolution')))
        for tools in (TOOLS, []):
            with self.subTest(tools=tools):
                body, metadata, _, _ = await self.payload({'tools': copy.deepcopy(tools), 'tool_ids': ['server-tool']})
                self.assertEqual(body['tools'], tools)
                self.assertNotIn('tools', metadata)
        resolver.assert_not_awaited()

    async def test_absent_tools_without_ids_does_not_inject_builtin_tools(self):
        body, metadata, _, _ = await self.payload()
        self.assertNotIn('tools', body)
        self.assertNotIn('tools', metadata)

    async def test_absent_or_null_tools_resolves_server_ids(self):
        tool = {'spec': copy.deepcopy(SPEC), 'callable': AsyncMock(return_value='fixture-result')}
        resolver = self.patch('get_tools', AsyncMock(return_value={'lookup': tool}))
        self.patch('apply_tool_search', AsyncMock(return_value=set()))
        for extra in ({}, {'tools': None}):
            body, metadata, _, _ = await self.payload({'tool_ids': ['server-tool'], **extra})
            self.assertEqual(body['tools'], TOOLS)
            self.assertIs(metadata['tools']['lookup'], tool)
        self.assertEqual(resolver.await_count, 2)

    async def test_caller_tools_do_not_resume_saved_server_approval(self):
        pending = {
            'id': 'reply',
            'role': 'assistant',
            'done': False,
            'content': '',
            'output': [
                {
                    'type': 'function_call',
                    'call_id': 'pending',
                    'name': 'lookup',
                    'arguments': '{}',
                    'status': 'pending',
                }
            ],
        }
        self.patch(
            'Chats',
            SimpleNamespace(
                get_chat_by_id=AsyncMock(return_value=SimpleNamespace(user_id=self.user.id, meta={})),
                get_message_by_id_and_message_id=AsyncMock(return_value=pending),
                get_chat_folder_id=AsyncMock(return_value=None),
            ),
        )
        self.patch(
            'load_messages_from_db', AsyncMock(return_value=[{'id': 'question', 'role': 'user', 'content': 'fixture'}])
        )
        self.patch('get_sorted_filters', Mock(return_value=[]))
        self.patch('apply_summary_checkpoint', AsyncMock(side_effect=lambda messages: (messages, None)))
        self.patch(
            'compact_messages_for_request',
            AsyncMock(side_effect=lambda req, form, user, msgs, *a, **kw: (msgs, None, [])),
        )
        resume = self.patch('resume_tool_calls', AsyncMock(side_effect=AssertionError('server approval resumed')))
        _, _, _, paused = await self.payload(
            {'tools': []},
            metadata={
                'chat_id': 'saved-fixture',
                'user_message_id': 'question',
                'assistant_message_id': 'reply',
                'tool_approval_resume': 'tools',
            },
        )
        self.assertFalse(paused)
        resume.assert_not_awaited()

    async def test_caller_tools_with_event_emitter_never_enter_server_loop(self):
        for tools in (TOOLS, []):
            with self.subTest(tools=tools):
                body, metadata, _, _ = await self.payload({'tools': tools, 'tool_ids': ['server-tool']})
                # A filter or stale context must not make a caller tool executable.
                metadata['tools'] = {'lookup': {'spec': SPEC, 'callable': AsyncMock()}}
                # A saved/temporary chat can have an emitter even for an API caller.
                ctx = self.context(body, metadata, self.emitter)
                execute = self.patch('execute_tool_call', AsyncMock(side_effect=AssertionError('caller tool executed')))
                provider = self.patch('generate_chat_completion', AsyncMock(side_effect=AssertionError('extra round')))
                await mw.process_chat_response(round_stream(1), ctx)
                execute.assert_not_awaited()
                provider.assert_not_awaited()
                output = ctx['assistant_message']['output']
                self.assertEqual([item['call_id'] for item in output if item['type'] == 'function_call'], ['a', 'b'])
                self.assertFalse(any(item['type'] == 'function_call_output' for item in output))
                self.assertEqual(ctx['assistant_message']['content'], '')

    async def test_caller_tools_disable_legacy_code_execution(self):
        body, metadata, _, _ = await self.payload({'tools': []})
        metadata.update(params={'function_calling': 'legacy'}, features={'code_interpreter': True})
        # The caller-ownership guard must stop before consulting server execution settings.
        mw.Config.get.side_effect = AssertionError('Server execution settings consulted')
        executor = self.patch('execute_code_jupyter', AsyncMock(side_effect=AssertionError('code executed')))
        provider = self.patch('generate_chat_completion', AsyncMock(side_effect=AssertionError('extra round')))
        await mw.process_chat_response(
            stream({'content': '<code_interpreter>print(1)</code_interpreter>'}, finish='stop'),
            self.context(body, metadata, self.emitter),
        )
        executor.assert_not_awaited()
        provider.assert_not_awaited()

    async def test_server_two_rounds_replay_and_reasoning_only_output(self):
        for provider in ('llama.cpp', 'openai'):
            with self.subTest(provider=provider):
                self.events.clear()
                self.model['provider'] = provider
                executed = []

                async def lookup(key):
                    executed.append(key)
                    return 'result:' + key

                tool = {'spec': copy.deepcopy(SPEC), 'callable': lookup}
                self.patch('get_tools', AsyncMock(return_value={'lookup': tool}))
                self.patch('apply_tool_search', AsyncMock(return_value=set()))
                self.patch('requires_tool_approval', AsyncMock(return_value=False))
                self.patch('get_updated_tool_function', AsyncMock(side_effect=lambda function, **kw: function))
                self.patch(
                    'compact_messages_for_request',
                    AsyncMock(side_effect=lambda req, form, user, msgs, *a, **kw: (msgs, None, [])),
                )
                followups = []

                async def generate(request, form_data, user, **kwargs):
                    followups.append(copy.deepcopy(form_data['messages']))
                    return (
                        round_stream(2) if len(followups) == 1 else stream({'content': 'public answer'}, finish='stop')
                    )

                self.patch('generate_chat_completion', AsyncMock(side_effect=generate))
                body, metadata, _, _ = await self.payload({'tool_ids': ['server-tool']})
                ctx = self.context(body, metadata, self.emitter)
                with self.assertNoLogs(mw.log, level='ERROR'):
                    await mw.process_chat_response(round_stream(1), ctx)
                self.assertEqual(executed, ['first', 'second', 'third'])
                self.assertEqual(len(followups), 2)
                history = followups[-1]
                self.assertEqual(
                    [m['role'] for m in history], ['user', 'assistant', 'tool', 'tool', 'assistant', 'tool']
                )
                self.assertEqual([m['tool_call_id'] for m in history if m['role'] == 'tool'], ['a', 'b', 'c'])
                assistants = [m for m in history if m['role'] == 'assistant']
                self.assertEqual([m['content'] for m in assistants], ['', ''])
                if provider == 'llama.cpp':
                    self.assertEqual([m['reasoning_content'] for m in assistants], [PRIVATE + '1', PRIVATE + '2'])
                else:
                    self.assertTrue(all('reasoning_content' not in m for m in assistants))
                self.assertEqual(ctx['assistant_message']['content'], 'public answer')
                self.assertNotIn(PRIVATE, str(mw.log_model_usage.call_args_list))
                reconstructed = mw.process_messages_with_output(
                    [{'role': 'assistant', 'content': 'UI fallback', 'output': ctx['assistant_message']['output']}],
                    reasoning_format=mw.get_reasoning_format(self.model),
                )
                self.assertEqual(reconstructed, history[1:] + [{'role': 'assistant', 'content': 'public answer'}])

    def test_reasoning_only_and_empty_content_reconstruction(self):
        output = [{'type': 'reasoning', 'content': [{'type': 'output_text', 'text': PRIVATE}]}]
        self.assertEqual(
            mw.process_messages_with_output(
                [{'role': 'assistant', 'content': '', 'output': output}], 'reasoning_content'
            ),
            [{'role': 'assistant', 'content': '', 'reasoning_content': PRIVATE}],
        )
        self.assertEqual(mw.process_messages_with_output([{'role': 'assistant', 'content': '', 'output': output}]), [])
        self.assertEqual(mw.get_output_text(output), '')

    def test_existing_provider_contract_does_not_guess_model_names(self):
        self.assertEqual(mw.get_reasoning_format({'provider': 'llama.cpp'}), 'reasoning_content')
        self.assertEqual(mw.get_reasoning_format({'owned_by': 'ollama'}), 'thinking')
        self.assertIsNone(mw.get_reasoning_format({'id': 'Qwen3.8', 'provider': 'openai'}))


if __name__ == '__main__':
    unittest.main()
