"""
Privacy invariant tests for BlockINTQL CLI.

CORE INVARIANT: Provider API keys (BLOCKINTQL_PROVIDER_KEY) must NEVER appear
in any request sent to the BlockINTQL API.
"""

import json
import pytest
from unittest.mock import patch, MagicMock
from click.testing import CliRunner

FAKE_PROVIDER_KEY = "cha_test_FAKE_PROVIDER_KEY_12345"
FAKE_API_KEY = "biq_sk_live_testkey_00000"
API_BASE = "https://btc-index-api-385334043904.us-central1.run.app"


class APICallRecorder:
    def __init__(self):
        self.calls = []

    def _record(self, method, url, **kwargs):
        self.calls.append({
            "method": method, "url": str(url),
            "headers": dict(kwargs.get("headers", {})),
            "json_body": kwargs.get("json"),
            "params": kwargs.get("params"),
        })
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.raise_for_status = MagicMock()
        mock_resp.json.return_value = {
            "verdict": "CLEAR", "risk_score": 0, "safe": True,
            "address": "1A1zP1eP5QGefi2DMPTfTL5SLmv7DivfNa",
            "chain": "bitcoin", "entity": None,
        }
        return mock_resp

    def mock_get(self, url, **kwargs):
        return self._record("GET", url, **kwargs)

    def mock_post(self, url, **kwargs):
        return self._record("POST", url, **kwargs)

    @property
    def blockintql_calls(self):
        return [c for c in self.calls if API_BASE in c["url"]]

    def assert_no_provider_key_leak(self, provider_key):
        for call in self.blockintql_calls:
            for hdr_name, hdr_val in call["headers"].items():
                assert provider_key not in str(hdr_val), \
                    f"Provider key leaked in header '{hdr_name}' of {call['method']} {call['url']}"
            if call["json_body"] is not None:
                body_str = json.dumps(call["json_body"])
                assert provider_key not in body_str, \
                    f"Provider key leaked in JSON body of {call['method']} {call['url']}"
            if call["params"] is not None:
                assert provider_key not in str(call["params"]), \
                    f"Provider key leaked in params of {call['method']} {call['url']}"
            assert provider_key not in call["url"], \
                f"Provider key leaked in URL: {call['url']}"


@pytest.fixture
def recorder():
    return APICallRecorder()

@pytest.fixture
def cli_env():
    return {
        "BLOCKINTQL_API_KEY": FAKE_API_KEY,
        "BLOCKINTQL_PROVIDER_KEY": FAKE_PROVIDER_KEY,
        "HOME": "/tmp/blockintql_test",
    }

@pytest.fixture
def runner():
    return CliRunner()


class TestProviderKeyNeverSentToBlockINTQL:
    def test_verdict_with_provider(self, runner, recorder, cli_env):
        from blockintql.cli import cli
        with patch("httpx.post", side_effect=recorder.mock_post), \
             patch("httpx.get", side_effect=recorder.mock_get):
            runner.invoke(cli, [
                "verdict", "--address", "1A1zP1eP5QGefi2DMPTfTL5SLmv7DivfNa",
                "--chain", "bitcoin", "--provider", "chainalysis",
                "--provider-key", FAKE_PROVIDER_KEY, "--agent",
            ], env=cli_env)
        recorder.assert_no_provider_key_leak(FAKE_PROVIDER_KEY)

    def test_screen_with_provider(self, runner, recorder, cli_env):
        from blockintql.cli import cli
        with patch("httpx.post", side_effect=recorder.mock_post), \
             patch("httpx.get", side_effect=recorder.mock_get):
            runner.invoke(cli, [
                "screen", "--address", "0x742d35Cc6634C0532925a3b844Bc9e7595f2bD53",
                "--chain", "ethereum", "--provider", "trm",
                "--provider-key", FAKE_PROVIDER_KEY, "--agent",
            ], env=cli_env)
        recorder.assert_no_provider_key_leak(FAKE_PROVIDER_KEY)

    def test_verdict_provider_key_in_env(self, runner, recorder, cli_env):
        from blockintql.cli import cli
        with patch("httpx.post", side_effect=recorder.mock_post), \
             patch("httpx.get", side_effect=recorder.mock_get):
            runner.invoke(cli, [
                "verdict", "--address", "1A1zP1eP5QGefi2DMPTfTL5SLmv7DivfNa",
                "--provider", "chainalysis", "--agent",
            ], env=cli_env)
        recorder.assert_no_provider_key_leak(FAKE_PROVIDER_KEY)

    def test_analyze_never_sends_provider_key(self, runner, recorder, cli_env):
        from blockintql.cli import cli
        with patch("httpx.post", side_effect=recorder.mock_post):
            runner.invoke(cli, [
                "analyze", "check 1A1zP1eP5QGefi2DMPTfTL5SLmv7DivfNa for sanctions",
                "--agent",
            ], env=cli_env)
        recorder.assert_no_provider_key_leak(FAKE_PROVIDER_KEY)

    def test_profile_never_sends_provider_key(self, runner, recorder, cli_env):
        from blockintql.cli import cli
        with patch("httpx.get", side_effect=recorder.mock_get):
            runner.invoke(cli, [
                "profile", "--identifier", "test@example.com", "--agent",
            ], env=cli_env)
        recorder.assert_no_provider_key_leak(FAKE_PROVIDER_KEY)

    def test_trace_never_sends_provider_key(self, runner, recorder, cli_env):
        from blockintql.cli import cli
        with patch("httpx.post", side_effect=recorder.mock_post):
            runner.invoke(cli, [
                "trace", "--txid", "abc123def456", "--agent",
            ], env=cli_env)
        recorder.assert_no_provider_key_leak(FAKE_PROVIDER_KEY)

    def test_query_never_sends_provider_key(self, runner, recorder, cli_env):
        from blockintql.cli import cli
        with patch("httpx.post", side_effect=recorder.mock_post):
            runner.invoke(cli, [
                "query", "is this address safe?", "--agent",
            ], env=cli_env)
        recorder.assert_no_provider_key_leak(FAKE_PROVIDER_KEY)


class TestProviderKeyStaysLocal:
    def test_chainalysis_call_goes_to_chainalysis(self, runner, recorder, cli_env):
        from blockintql.cli import cli
        with patch("httpx.post", side_effect=recorder.mock_post), \
             patch("httpx.get", side_effect=recorder.mock_get):
            runner.invoke(cli, [
                "verdict", "--address", "1A1zP1eP5QGefi2DMPTfTL5SLmv7DivfNa",
                "--provider", "chainalysis",
                "--provider-key", FAKE_PROVIDER_KEY, "--agent",
            ], env=cli_env)
        provider_calls = [c for c in recorder.calls if "chainalysis.com" in c["url"]]
        for call in provider_calls:
            assert FAKE_PROVIDER_KEY in str(call["headers"].values()), \
                "Provider key should be sent TO the provider"
        recorder.assert_no_provider_key_leak(FAKE_PROVIDER_KEY)
