"""Tests for LLM client model selection and lifecycle management.

Covers:
- RAM-based model selection (14B vs 8B)
- User override bypass
- Preload with keep_alive=-1
- Unload with keep_alive=0
- Active model tracking
- call_llm_structured uses active model
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from pydantic import BaseModel

from src.attribution import llm_client


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


class _DummySchema(BaseModel):
    """Minimal Pydantic model for call_llm_structured tests."""

    value: str


def _make_vmem(available_gb: float) -> MagicMock:
    """Create a mock virtual_memory result with given available GB."""
    vmem = MagicMock()
    vmem.available = int(available_gb * (1024**3))
    return vmem


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _reset_active_model():
    """Reset module-level _active_model before each test."""
    llm_client._active_model = None
    yield
    llm_client._active_model = None


# ---------------------------------------------------------------------------
# Tests: select_model
# ---------------------------------------------------------------------------


class TestSelectModel:
    """Tests for select_model() RAM-based selection."""

    @patch("src.attribution.llm_client.psutil")
    def test_select_model_14b_when_enough_ram(self, mock_psutil: MagicMock) -> None:
        """Should return 14B model when available RAM >= threshold."""
        mock_psutil.virtual_memory.return_value = _make_vmem(14.0)

        result = llm_client.select_model()

        assert result == "qwen3:14b"
        assert llm_client._active_model == "qwen3:14b"

    @patch("src.attribution.llm_client.psutil")
    def test_select_model_8b_when_low_ram(self, mock_psutil: MagicMock) -> None:
        """Should return 8B model when available RAM < threshold."""
        mock_psutil.virtual_memory.return_value = _make_vmem(8.0)

        result = llm_client.select_model()

        assert result == "qwen3:8b"
        assert llm_client._active_model == "qwen3:8b"

    @patch("src.attribution.llm_client.psutil")
    def test_select_model_override(self, mock_psutil: MagicMock) -> None:
        """Should return override model regardless of RAM."""
        result = llm_client.select_model(override="custom:model")

        assert result == "custom:model"
        assert llm_client._active_model == "custom:model"
        # psutil should NOT be called when override is provided
        mock_psutil.virtual_memory.assert_not_called()

    @patch("src.attribution.llm_client.psutil")
    def test_select_model_at_exact_threshold(self, mock_psutil: MagicMock) -> None:
        """Should return 14B when RAM is exactly at threshold."""
        mock_psutil.virtual_memory.return_value = _make_vmem(
            llm_client.RAM_THRESHOLD_GB
        )

        result = llm_client.select_model()

        assert result == "qwen3:14b"


# ---------------------------------------------------------------------------
# Tests: preload_model
# ---------------------------------------------------------------------------


class TestPreloadModel:
    """Tests for preload_model() Ollama keep_alive=-1 pinning."""

    @patch("src.attribution.llm_client.ollama_chat")
    @patch("src.attribution.llm_client.psutil")
    def test_preload_model_calls_ollama_with_keep_alive(
        self, mock_psutil: MagicMock, mock_chat: MagicMock
    ) -> None:
        """Should call ollama_chat with keep_alive=-1 to pin model."""
        mock_psutil.virtual_memory.return_value = _make_vmem(14.0)

        result = llm_client.preload_model("qwen3:14b")

        assert result == "qwen3:14b"
        mock_chat.assert_called_once_with(
            model="qwen3:14b",
            messages=[],
            keep_alive=-1,
        )
        assert llm_client._active_model == "qwen3:14b"

    @patch("src.attribution.llm_client.ollama_chat")
    @patch("src.attribution.llm_client.psutil")
    def test_preload_model_auto_selects_when_no_model(
        self, mock_psutil: MagicMock, mock_chat: MagicMock
    ) -> None:
        """Should auto-select model via select_model() when None passed."""
        mock_psutil.virtual_memory.return_value = _make_vmem(14.0)

        result = llm_client.preload_model(None)

        assert result == "qwen3:14b"
        assert llm_client._active_model == "qwen3:14b"


# ---------------------------------------------------------------------------
# Tests: unload_model
# ---------------------------------------------------------------------------


class TestUnloadModel:
    """Tests for unload_model() Ollama keep_alive=0 eviction."""

    @patch("src.attribution.llm_client.ollama_chat")
    def test_unload_model_calls_ollama_with_zero(
        self, mock_chat: MagicMock
    ) -> None:
        """Should call ollama_chat with keep_alive=0 to evict model."""
        llm_client._active_model = "qwen3:14b"

        llm_client.unload_model("qwen3:14b")

        mock_chat.assert_called_once_with(
            model="qwen3:14b",
            messages=[],
            keep_alive=0,
        )
        assert llm_client._active_model is None

    @patch("src.attribution.llm_client.ollama_chat")
    def test_unload_model_uses_active_model_when_none(
        self, mock_chat: MagicMock
    ) -> None:
        """Should unload the active model when no model specified."""
        llm_client._active_model = "qwen3:8b"

        llm_client.unload_model()

        mock_chat.assert_called_once_with(
            model="qwen3:8b",
            messages=[],
            keep_alive=0,
        )
        assert llm_client._active_model is None


# ---------------------------------------------------------------------------
# Tests: get_active_model
# ---------------------------------------------------------------------------


class TestGetActiveModel:
    """Tests for get_active_model() caching and auto-selection."""

    def test_get_active_model_returns_preloaded(self) -> None:
        """Should return the preloaded model without calling select_model."""
        llm_client._active_model = "qwen3:14b"

        result = llm_client.get_active_model()

        assert result == "qwen3:14b"

    @patch("src.attribution.llm_client.psutil")
    def test_get_active_model_selects_when_none(
        self, mock_psutil: MagicMock
    ) -> None:
        """Should auto-select via select_model() when no active model."""
        mock_psutil.virtual_memory.return_value = _make_vmem(14.0)
        llm_client._active_model = None

        result = llm_client.get_active_model()

        assert result == "qwen3:14b"


# ---------------------------------------------------------------------------
# Tests: call_llm_structured
# ---------------------------------------------------------------------------


class TestCallLlmStructured:
    """Tests for call_llm_structured() using active model."""

    @patch("src.attribution.llm_client.ollama_chat")
    def test_call_llm_structured_uses_active_model(
        self, mock_chat: MagicMock
    ) -> None:
        """Should use the active model (not hardcoded) for LLM calls."""
        llm_client._active_model = "qwen3:14b"

        # Mock a valid response
        mock_response = MagicMock()
        mock_response.message.content = '{"value": "test"}'
        mock_chat.return_value = mock_response

        result = llm_client.call_llm_structured(
            system_prompt="test prompt",
            user_content="test content",
            schema_class=_DummySchema,
        )

        assert result is not None
        assert result.value == "test"

        # Verify the model used in the call
        call_args = mock_chat.call_args
        assert call_args.kwargs["model"] == "qwen3:14b"
        assert call_args.kwargs["keep_alive"] == -1
