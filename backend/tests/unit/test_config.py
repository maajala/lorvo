import pytest
from pydantic import ValidationError

from lorvo.config import Settings


def test_defaults() -> None:
    s = Settings(_env_file=None)  # type: ignore[call-arg]
    assert s.anthropic_model == "claude-sonnet-5-5"
    assert s.chunk_target_tokens == 350
    assert s.anthropic_api_key is None


def test_env_overrides(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ANTHROPIC_MODEL", "claude-opus-5-5")
    monkeypatch.setenv("EMBEDDER", "fake")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")
    s = Settings(_env_file=None)  # type: ignore[call-arg]
    assert s.anthropic_model == "claude-opus-5-5"
    assert s.embedder == "fake"
    assert s.anthropic_api_key is not None
    # Secrets never leak through repr/logging.
    assert "sk-test" not in repr(s)


def test_overlap_must_be_small() -> None:
    with pytest.raises(ValidationError):
        Settings(_env_file=None, chunk_target_tokens=100, chunk_overlap_tokens=60)  # type: ignore[call-arg]
