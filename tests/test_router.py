# tests/test_router.py
from unittest.mock import patch

import pytest

from src.llm_router import LLMRouter

    
def test_local_backend_is_configured_without_calling_the_model():
    choice = "Local Machine (Ollama - Llama3.2:3b)"

    with patch("src.llm_router.LLM") as llm_factory:
        LLMRouter.create_backend(choice)

    assert llm_factory.call_args.kwargs == {
        "model": "ollama/llama3.2:3b",
        "base_url": "http://localhost:11434",
        "timeout": 90,
        "max_tokens": 1024,
    }


def test_qwen_backend_is_configured_without_calling_the_model():
    choice = "Local Machine (Ollama - Qwen3.5:9b)"

    with patch("src.llm_router.LLM") as llm_factory:
        LLMRouter.create_backend(choice)

    assert llm_factory.call_args.kwargs == {
        "model": "ollama/qwen3.5:9b",
        "base_url": "http://localhost:11434",
        "timeout": 90,
        "max_tokens": 1024,
        "reasoning_effort": "none",
    }


def test_bedrock_backend_uses_sdk_credential_chain_without_static_key_gate():
    choice = "Enterprise Cloud (AWS Bedrock - Claude 3.5 Sonnet) - NOT IMPLEMENTED"

    with patch("src.llm_router.LLM") as llm_factory:
        LLMRouter.create_backend(choice)

    assert llm_factory.call_args.kwargs == {
        "model": "bedrock/anthropic.claude-3-5-sonnet-v1:0",
        "base_url": None,
        "timeout": 90,
    }


def test_unsupported_backend_is_rejected():
    with pytest.raises(ValueError, match="Unsupported infrastructure selection"):
        LLMRouter.create_backend("unlisted backend")
