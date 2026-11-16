"""Provider contracts shared by model discovery and conversation reconstruction."""


def get_reasoning_format(model: dict) -> str | None:
    """Return the configured provider's structured reasoning replay field.

    Unknown providers omit reconstructed reasoning. Caller-supplied messages are
    a separate pass-through contract; model names never establish support.
    """
    if model.get('owned_by') == 'ollama':
        return 'thinking'
    if model.get('provider') == 'llama.cpp':
        return 'reasoning_content'
    return None
