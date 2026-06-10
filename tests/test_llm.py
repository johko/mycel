import pytest

from mycel.llm import chat_with_retry, parse_tool_arguments


class FlakyClient:
    def __init__(self, failures: int):
        self.failures = failures
        self.calls = 0

    async def chat_completion(self, **kwargs):
        self.calls += 1
        if self.calls <= self.failures:
            raise ConnectionError("provider hiccup")
        return "ok"


async def test_chat_with_retry_recovers(monkeypatch):
    monkeypatch.setattr("mycel.llm.asyncio.sleep", _no_sleep)
    client = FlakyClient(failures=2)
    assert await chat_with_retry(client, attempts=3, messages=[]) == "ok"
    assert client.calls == 3


async def test_chat_with_retry_exhausted(monkeypatch):
    monkeypatch.setattr("mycel.llm.asyncio.sleep", _no_sleep)
    client = FlakyClient(failures=5)
    with pytest.raises(ConnectionError):
        await chat_with_retry(client, attempts=3, messages=[])


async def _no_sleep(_):
    pass


def test_parse_tool_arguments_variants():
    assert parse_tool_arguments('{"id": "R1"}') == {"id": "R1"}
    assert parse_tool_arguments({"id": "R1"}) == {"id": "R1"}
    assert parse_tool_arguments(None) == {}
    assert parse_tool_arguments("") == {}
