"""Load real API processing modules with fail-closed, in-memory service boundaries.

No application startup, environment configuration, DB, credentials or provider is
loaded. AST inspection only enumerates imports to stub; complete source modules
are imported and executed normally. Tests must explicitly configure every service
they exercise. Run this isolated suite in its own Python process.
"""

import ast
import importlib
import sys
import types
from pathlib import Path
from unittest.mock import Mock

BACKEND = Path(__file__).resolve().parents[1]
REAL_MODULES = {
    'open_webui.utils.middleware',
    'open_webui.utils.misc',
    'open_webui.utils.response',
    'open_webui.utils.tool_calling',
    'open_webui.utils.tool_search',
    'open_webui.utils.ask_user',
    'open_webui.utils.chat_id',
    'open_webui.utils.json_codec',
    'open_webui.utils.payload',
    'open_webui.utils.models',
    'open_webui.utils.model_capabilities',
    'open_webui.utils.model_ids',
    'open_webui.utils.chat',
    'open_webui.utils.audit',
    'open_webui.routers.openai',
}


def module(name):
    if name not in sys.modules:
        parent, _, child = name.rpartition('.')
        parent_module = module(parent) if parent else None
        result = types.ModuleType(name)
        result.__path__ = [str(BACKEND.joinpath(*name.split('.')))]
        sys.modules[name] = result
        if parent_module:
            setattr(parent_module, child, result)
    return sys.modules[name]


def load_modules():
    module('open_webui.utils')
    # Inspect imports, never extract or copy function implementations.
    for name in REAL_MODULES:
        path = BACKEND.joinpath(*name.split('.')).with_suffix('.py')
        if not path.exists():
            continue
        for node in ast.walk(ast.parse(path.read_text())):
            if not isinstance(node, ast.ImportFrom) or not (node.module or '').startswith('open_webui.'):
                continue
            if node.module in REAL_MODULES:
                continue
            target = module(node.module)
            for alias in node.names:
                full_name = f'{node.module}.{alias.name}'
                if full_name in REAL_MODULES:
                    continue
                if not hasattr(target, alias.name):
                    setattr(target, alias.name, Mock(name=full_name, side_effect=AssertionError(full_name)))

    env = module('open_webui.env')
    for name in vars(env).copy():
        if name.isupper():
            setattr(env, name, False)
    env.GLOBAL_LOG_LEVEL = 'WARNING'
    env.CHAT_RESPONSE_MAX_TOOL_CALL_ITERATIONS = 5
    env.CHAT_RESPONSE_STREAM_DELTA_CHUNK_SIZE = 1
    env.CHAT_STREAM_RESPONSE_CHUNK_MAX_BUFFER_SIZE = 1024 * 1024
    env.ENABLE_TOOL_SERVERS = True
    env.MAX_BODY_LOG_SIZE = 1024 * 1024
    env.AUDIT_LOG_LEVEL = 'REQUEST_RESPONSE'
    env.AUDIT_INCLUDED_PATHS = []
    env.AIOHTTP_CLIENT_TIMEOUT_MODEL_LIST = 1
    env.MODELS_CACHE_TTL = 1
    module('sqlalchemy.ext.asyncio').AsyncSession = type('AsyncSession', (), {})

    async def unused_dependency():
        raise AssertionError('Unexpected authentication or database access')

    module('open_webui.utils.auth').get_verified_user = unused_dependency
    module('open_webui.utils.auth').get_admin_user = unused_dependency
    module('open_webui.internal.db').get_async_session = unused_dependency
    module('open_webui.models.users').UserModel = type('UserModel', (), {})
    module('open_webui.socket.utils').RedisDict = type('RedisDict', (dict,), {})
    module('open_webui.utils.mcp.apps').MCPAppResult = type('MCPAppResult', (), {})
    module('open_webui.utils.tool_permissions').ToolApprovalRequired = type('ToolApprovalRequired', (Exception,), {})
    return importlib.import_module('open_webui.utils.middleware'), importlib.import_module('open_webui.utils.models')


middleware, models = load_modules()
