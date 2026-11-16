# Reasoning replay and tool ownership

`GET /api/models` (also `/api/v1/models`) declares the effective provider's
reasoning replay contract on each model, including workspace presets:

```json
{
	"id": "configured-model",
	"provider_capabilities": {
		"reasoning_replay": "reasoning_content"
	}
}
```

`reasoning_replay` is a string or `null`. The existing connection setting selects
the value. This field is a server declaration, not a request parameter or a
model-name heuristic. An upstream model catalogue cannot opt into replay.

| Effective provider                                        | Declaration           | Reconstructed assistant messages   |
| --------------------------------------------------------- | --------------------- | ---------------------------------- |
| OpenAI-compatible connection with `provider: "llama.cpp"` | `"reasoning_content"` | Separate `reasoning_content` field |
| Native Ollama                                             | `"thinking"`          | Separate `thinking` field          |
| Other or unspecified provider, unresolved arena           | `null`                | Omit reconstructed reasoning text  |

A client that supports only `reasoning_content` must enable replay only for that
exact declaration. Missing, `null` and unknown declarations mean no replay for
that client. Do not label a different provider as llama.cpp to enable this field:
that connection setting also controls provider-specific behavior. Additional
provider contracts need separate implementation and qualification.

There are two history paths:

- Raw caller-supplied `messages` pass structured assistant `reasoning_content`
  through the Chat Completions route, including empty or null `content`. The
  reconstruction policy does not remove these caller-supplied fields for strict
  providers. The caller must obey the declared capability. Existing tool-pair
  validation still removes orphan calls and results.
- Saved or supplied assistant `output` items are reconstructed by the server.
  Reasoning follows the provider contract above. Tool-call IDs, tool-result roles
  and round order stay separate from reasoning. Provider-bound `reasoning_details`
  retain their existing same-model rules.

Structured reasoning stays separate from assistant `content`. Existing controlled
UI reasoning rendering remains available. It must not be copied into answer text,
summaries or client exports. Payload debug logs record counts. Chat inference audit
bodies redact structured reasoning fields, aliases and reasoning output items;
incomplete or non-JSON bodies receive a redaction marker. Audit events, request
metadata, response status and usage counters remain available. This does not
sanitize arbitrary reasoning embedded by a provider in ordinary text or error
messages, or configure third-party filters and telemetry.

## Tool ownership

| Original request                                          | Server behavior                                                                                               |
| --------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------- |
| Nonempty `tools` array                                    | Caller owns execution and follow-up messages. Skip server tool resolution and execution.                      |
| `tools: []`                                               | Caller opts out of server tools. Even an unexpected provider tool call cannot enter the server loop.          |
| Absent `tools` (or legacy `tools: null`), with `tool_ids` | Resolve server tools under existing access and approval controls. The streaming chat handler owns their loop. |
| Absent `tools`, no `tool_ids`, plain API request          | No automatic builtin injection.                                                                               |
| Absent `tools`, UI session or internal note chat          | Existing feature and model capability gates select builtin tools.                                             |

Explicit caller tools take precedence over `tool_ids`. Ownership is captured
before model defaults and inlet filters. A later filter cannot transfer that
ownership by injecting schemas. Adding chat metadata or an event emitter does
not transfer execution to the server or resume a saved server approval.
The existing HTTP versus event-based response delivery remains unchanged.

## Offline verification and follow-on work

Run `python -m unittest discover -s backend/tests -p 'test_api_quality.py' -v`.
The Python CI workflow installs a small subset of existing dependencies using
their versions in `pyproject.toml`, and runs this command on Python 3.11 and 3.12.
Run this suite in its own process: its fixture replaces database, configuration,
authentication, plugins and network boundaries before importing complete source
modules. It executes the real payload preparation, response loop, tool execution,
history conversion, model discovery, audit processing and OpenAI route functions.
It does not start the application or use a live provider.

The regression cases cover two tool rounds, multiple IDs, reasoning-only deltas,
empty content, caller versus server ownership, strict-provider defaults and raw
provider forwarding. They do not measure model quality or speed.

API-03 owns continuation errors, cancellation, incomplete tool arguments and
transport framing in `streaming_chat_response_handler`, `process_chat_response`
and the provider route. Preserve `metadata.caller_owned_tools` in that work. Native
server tools currently execute on the streaming path; non-streaming reasoning-only
UI persistence and tool-result behavior need separate qualification.

API-04 owns effective configuration and compatibility guidance. Use the
`provider_capabilities.reasoning_replay` declaration and shared
`utils/model_capabilities.py` policy. Sampling, parser flags, weights,
quantisation and runtime configuration are outside this change.
