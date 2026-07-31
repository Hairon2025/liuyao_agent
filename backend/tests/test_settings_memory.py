"""长期记忆配置回退与阈值校验测试。"""
from __future__ import annotations

import pytest
from pydantic import ValidationError

from backend.config.settings import Settings


def test_memory_model_config_falls_back_to_main_llm():
    configured = Settings(
        _env_file=None,
        llm_api_key="main-key",
        llm_base_url="https://main.example/v1",
        llm_model="main-model",
        llm_timeout_seconds=90,
        memory_llm_api_key="",
        memory_llm_base_url="",
        memory_llm_model="",
        memory_llm_timeout_seconds=None,
    )

    assert configured.effective_memory_llm_api_key == "main-key"
    assert (
        configured.effective_memory_llm_base_url
        == "https://main.example/v1"
    )
    assert configured.effective_memory_llm_model == "main-model"
    assert configured.effective_memory_llm_timeout_seconds == 90


def test_memory_model_config_can_override_each_main_llm_field():
    configured = Settings(
        _env_file=None,
        memory_llm_api_key="memory-key",
        memory_llm_base_url="https://memory.example/v1",
        memory_llm_model="memory-model",
        memory_llm_timeout_seconds=15,
    )

    assert configured.effective_memory_llm_api_key == "memory-key"
    assert (
        configured.effective_memory_llm_base_url
        == "https://memory.example/v1"
    )
    assert configured.effective_memory_llm_model == "memory-model"
    assert configured.effective_memory_llm_timeout_seconds == 15


def test_memory_summary_threshold_cannot_exceed_context_window():
    with pytest.raises(ValidationError):
        Settings(
            _env_file=None,
            chat_context_recent_limit=8,
            memory_summary_trigger_items=10,
            memory_summary_keep_recent_items=5,
        )
