import json
import io
import os
import tempfile
import unittest
from unittest.mock import patch
import base64

from click.testing import CliRunner
import httpx
from rich.console import Console

from blockintql.cli import cli, output


class BlockINTQLCliTests(unittest.TestCase):
    def setUp(self):
        self.runner = CliRunner()
        self.temp_dir = tempfile.TemporaryDirectory()
        self.config_file = os.path.join(self.temp_dir.name, "config.json")
        patcher = patch("blockintql.cli.CONFIG_FILE", self.config_file)
        self.addCleanup(patcher.stop)
        patcher.start()

    def tearDown(self):
        self.temp_dir.cleanup()

    def make_response(self, status_code, payload, *, headers=None, method="POST", url="https://blockintql.com/v1/screen"):
        request = httpx.Request(method, url)
        return httpx.Response(status_code, json=payload, headers=headers, request=request)

    def test_expected_commands_are_registered(self):
        expected = {
            "analyze",
            "ask",
            "auth",
            "buy",
            "capabilities",
            "chart",
            "eth",
            "ens",
            "history",
            "login",
            "pay",
            "profile",
            "prediction",
            "providers",
            "query",
            "screen",
            "skills",
            "status",
            "stablecoins",
            "trace",
            "tx",
            "verdict",
            "wallet",
        }
        self.assertTrue(expected.issubset(set(cli.commands)))

    @patch("blockintql.cli.run_ask_flow")
    def test_prediction_market_analysis_routes_through_ask_flow(self, mock_run_ask_flow):
        result = self.runner.invoke(
            cli,
            ["prediction", "market", "analysis", "0xabc", "--agent"],
        )
        self.assertEqual(result.exit_code, 0, result.output)
        mock_run_ask_flow.assert_called_once_with(
            "Investigate prediction market exposure, counterparties, venue interactions, and event-driven flows",
            address="0xabc",
            workspace_id=None,
            chain="ethereum",
            budget_credits=None,
            budget_usd=None,
            upto_budget_usd=None,
            open_workspace=True,
            mode=None,
            agent=True,
            quiet=False,
        )

    @patch("blockintql.cli.run_ask_flow")
    def test_prediction_market_analysis_accepts_execution_mode(self, mock_run_ask_flow):
        result = self.runner.invoke(
            cli,
            ["prediction", "market", "analysis", "0xabc", "--mode", "deep", "--agent"],
        )
        self.assertEqual(result.exit_code, 0, result.output)
        mock_run_ask_flow.assert_called_once_with(
            "Investigate prediction market exposure, counterparties, venue interactions, and event-driven flows",
            address="0xabc",
            workspace_id=None,
            chain="ethereum",
            budget_credits=None,
            budget_usd=None,
            upto_budget_usd=None,
            open_workspace=True,
            mode="deep",
            agent=True,
            quiet=False,
        )

    def test_auth_persists_api_key_with_restricted_permissions(self):
        result = self.runner.invoke(cli, ["auth", "--api-key", "biq_sk_live_test"])
        self.assertEqual(result.exit_code, 0, result.output)
        with open(self.config_file, encoding="utf-8") as handle:
            data = json.load(handle)
        self.assertEqual(data["api_key"], "biq_sk_live_test")
        mode = os.stat(self.config_file).st_mode & 0o777
        self.assertEqual(mode, 0o600)

    @patch("blockintql.cli.api_post")
    def test_buy_works_without_stored_api_key(self, mock_api_post):
        mock_api_post.return_value = {"checkout_url": "https://checkout.example/session"}
        result = self.runner.invoke(cli, ["buy", "--email", "user@example.com", "--agent"])
        self.assertEqual(result.exit_code, 0, result.output)
        payload = json.loads(result.output)
        self.assertEqual(payload["checkout_url"], "https://checkout.example/session")
        mock_api_post.assert_called_once_with(
            "/v1/billing/checkout",
            {"email": "user@example.com", "pack": "starter"},
            require_auth=False,
        )

    @patch("blockintql.cli.httpx.request")
    def test_api_get_falls_back_to_direct_api_on_upstream_timeout_status(self, mock_request):
        first = self.make_response(
            524,
            {"error": "A timeout occurred"},
            method="GET",
            url="https://blockintql.com/v1/eth/stablecoins/flows",
        )
        second = self.make_response(
            200,
            {"data": {"series": []}, "source": "node_fallback"},
            method="GET",
            url="https://btc-index-api-385334043904.us-central1.run.app/v1/eth/stablecoins/flows",
        )
        mock_request.side_effect = [first, second]
        result = self.runner.invoke(
            cli,
            ["chart", "stablecoin-flows", "--hours", "24", "--agent"],
        )
        self.assertEqual(result.exit_code, 0, result.output)
        self.assertEqual(mock_request.call_count, 2)
        first_url = mock_request.call_args_list[0].args[1]
        second_url = mock_request.call_args_list[1].args[1]
        self.assertTrue(first_url.startswith("https://blockintql.com/"))
        self.assertTrue(second_url.startswith("https://btc-index-api-385334043904.us-central1.run.app/"))

    @patch("blockintql.cli.api_post")
    def test_buy_attaches_current_api_key_without_email(self, mock_api_post):
        self.runner.invoke(cli, ["auth", "--api-key", "biq_sk_live_test"])
        mock_api_post.return_value = {"checkout_url": "https://checkout.example/session"}
        result = self.runner.invoke(cli, ["buy", "--agent"])
        self.assertEqual(result.exit_code, 0, result.output)
        payload = json.loads(result.output)
        self.assertTrue(payload["api_key_attached"])
        mock_api_post.assert_called_once_with(
            "/v1/billing/checkout",
            {"pack": "starter", "api_key": "biq_sk_live_test"},
            require_auth=False,
        )

    @patch("blockintql.cli.api_post")
    @patch("blockintql.cli.get_provider")
    def test_generic_provider_receives_provider_url(self, mock_get_provider, mock_api_post):
        mock_api_post.return_value = {
            "verdict": "CLEAR",
            "safe": True,
            "risk_score": 0,
            "risk_indicators": [],
            "entity": None,
            "action": "ok",
            "chain": "bitcoin",
        }

        class Provider:
            requires_api_key = False

            def get_address_risk(self, address, chain):
                return {
                    "entity_name": "Example",
                    "entity_category": "test",
                    "risk_score": 25,
                    "risk_indicators": ["EXAMPLE"],
                    "sanctions_hit": False,
                    "raw": {},
                }

        mock_get_provider.return_value = Provider()
        result = self.runner.invoke(
            cli,
            [
                "verdict",
                "--address",
                "1A1zP1eP5QGefi2DMPTfTL5SLmv7DivfNa",
                "--provider",
                "generic",
                "--provider-url",
                "https://example.com/screen/{address}",
                "--agent",
            ],
        )
        self.assertEqual(result.exit_code, 0, result.output)
        mock_get_provider.assert_called_once_with(
            "generic",
            "",
            url_template="https://example.com/screen/{address}",
            risk_field="risk_score",
            entity_field="entity",
            auth_header="Authorization",
            auth_prefix="Bearer",
        )
        payload = json.loads(result.output)
        self.assertEqual(payload["provider_data"]["provider"], "generic")
        mock_api_post.assert_called_once_with(
            "/v1/verdict",
            {
                "address": "1A1zP1eP5QGefi2DMPTfTL5SLmv7DivfNa",
                "chain": "bitcoin",
                "context": "",
            },
        )

    @patch("blockintql.cli.api_post")
    @patch("blockintql.cli.get_provider")
    def test_verdict_provider_key_and_raw_response_stay_client_side(self, mock_get_provider, mock_api_post):
        mock_api_post.return_value = {
            "verdict": "CLEAR",
            "safe": True,
            "risk_score": 5,
            "risk_indicators": [],
            "entity": None,
            "action": "ok",
            "chain": "ethereum",
        }

        class Provider:
            requires_api_key = True

            def get_address_risk(self, address, chain):
                return {
                    "entity_name": "Vendor Entity",
                    "entity_category": "exchange",
                    "risk_score": 45,
                    "risk_indicators": ["WATCHLIST"],
                    "sanctions_hit": False,
                    "raw": {
                        "secret_token": "should-not-leak",
                        "notes": ["raw vendor payload stays local"],
                    },
                }

        mock_get_provider.return_value = Provider()
        result = self.runner.invoke(
            cli,
            [
                "verdict",
                "--address",
                "0xd8dA6BF26964aF9D7eEd9e03E53415D37aA96045",
                "--provider",
                "chainalysis",
                "--provider-key",
                "provider-secret",
                "--agent",
            ],
        )
        self.assertEqual(result.exit_code, 0, result.output)
        mock_api_post.assert_called_once_with(
            "/v1/verdict",
            {
                "address": "0xd8dA6BF26964aF9D7eEd9e03E53415D37aA96045",
                "chain": "ethereum",
                "context": "",
            },
        )
        mock_get_provider.assert_called_once_with(
            "chainalysis",
            "provider-secret",
            url_template=None,
            risk_field="risk_score",
            entity_field="entity",
            auth_header="Authorization",
            auth_prefix="Bearer",
        )
        payload = json.loads(result.output)
        self.assertNotIn("provider-secret", result.output)
        self.assertNotIn("secret_token", result.output)
        self.assertNotIn("raw", payload.get("provider_data", {}))
        self.assertEqual(payload["provider_data"]["provider"], "chainalysis")
        self.assertEqual(payload["provider_data"]["entity_name"], "Vendor Entity")
        self.assertEqual(payload["provider_data"]["canonical_category"], "exchange")
        self.assertEqual(payload["provider_data"]["recommended_verdict"], "CLEAR")
        self.assertIn("consensus", payload)
        self.assertEqual(payload["consensus"]["mode"], "address_screening")
        self.assertEqual(payload["consensus"]["decision"], "CLEAR")
        self.assertEqual(payload["consensus"]["vote_split"]["clear"], 3)

    @patch("blockintql.cli.api_post")
    @patch("blockintql.cli.get_provider")
    def test_screen_provider_url_and_raw_response_never_reach_blockintql_api(self, mock_get_provider, mock_api_post):
        mock_api_post.return_value = {
            "verdict": "CAUTION",
            "safe": False,
            "risk_score": 20,
            "risk_indicators": ["BLOCKINTQL_SIGNAL"],
            "entity": None,
            "action": "review",
            "chain": "ethereum",
        }

        class Provider:
            requires_api_key = False

            def get_address_risk(self, address, chain):
                return {
                    "entity_name": "Local Provider",
                    "entity_category": "service",
                    "risk_score": 65,
                    "risk_indicators": ["LOCAL_PROVIDER_SIGNAL"],
                    "sanctions_hit": True,
                    "raw": {
                        "provider_url": "https://vendor.example/screen/0xd8...",
                        "full_blob": {"should": "stay-local"},
                    },
                }

        mock_get_provider.return_value = Provider()
        result = self.runner.invoke(
            cli,
            [
                "screen",
                "--address",
                "0xd8dA6BF26964aF9D7eEd9e03E53415D37aA96045",
                "--provider",
                "generic",
                "--provider-url",
                "https://vendor.example/screen/{address}",
                "--agent",
            ],
        )
        self.assertEqual(result.exit_code, 0, result.output)
        mock_api_post.assert_called_once_with(
            "/v1/screen",
            {
                "address": "0xd8dA6BF26964aF9D7eEd9e03E53415D37aA96045",
                "chain": "ethereum",
            },
        )
        mock_get_provider.assert_called_once_with(
            "generic",
            "",
            url_template="https://vendor.example/screen/{address}",
            risk_field="risk_score",
            entity_field="entity",
            auth_header="Authorization",
            auth_prefix="Bearer",
        )
        payload = json.loads(result.output)
        self.assertEqual(payload["verdict"], "BLOCK")
        self.assertNotIn("https://vendor.example", result.output)
        self.assertNotIn("full_blob", result.output)
        self.assertNotIn("raw", payload.get("provider_data", {}))
        self.assertEqual(payload["provider_data"]["provider"], "generic")
        self.assertEqual(payload["provider_data"]["canonical_category"], "sanctions")
        self.assertEqual(payload["provider_data"]["recommended_verdict"], "BLOCK")
        self.assertIn("consensus", payload)
        self.assertEqual(payload["consensus"]["mode"], "address_screening")
        self.assertEqual(payload["consensus"]["decision"], "BLOCK")
        self.assertEqual(payload["consensus"]["vote_split"]["block"], 3)

    @patch("blockintql.cli.api_post")
    @patch("blockintql.cli.get_provider")
    def test_unmapped_high_risk_provider_result_degrades_to_caution_not_clear(self, mock_get_provider, mock_api_post):
        mock_api_post.return_value = {
            "verdict": "CLEAR",
            "safe": True,
            "risk_score": 0,
            "risk_indicators": [],
            "entity": None,
            "action": "ok",
            "chain": "ethereum",
        }

        class Provider:
            requires_api_key = False

            def get_address_risk(self, address, chain):
                return {
                    "entity_name": "Unknown Vendor Class",
                    "entity_category": "proprietary_super_risky_bucket",
                    "risk_score": 91,
                    "risk_indicators": ["UNMAPPED_VENDOR_CATEGORY"],
                    "sanctions_hit": False,
                    "raw": {"opaque": "blob"},
                }

        mock_get_provider.return_value = Provider()
        result = self.runner.invoke(
            cli,
            [
                "screen",
                "--address",
                "0xd8dA6BF26964aF9D7eEd9e03E53415D37aA96045",
                "--provider",
                "generic",
                "--provider-url",
                "https://vendor.example/screen/{address}",
                "--agent",
            ],
        )
        self.assertEqual(result.exit_code, 0, result.output)
        payload = json.loads(result.output)
        self.assertEqual(payload["verdict"], "CAUTION")
        self.assertFalse(payload["safe"])
        self.assertEqual(payload["action"], "review")
        self.assertEqual(payload["provider_data"]["canonical_category"], "unknown_high_risk")
        self.assertEqual(payload["provider_data"]["recommended_verdict"], "CAUTION")
        self.assertEqual(payload["provider_data"]["confidence"], "low")

    @patch("blockintql.cli.api_post")
    def test_verdict_auto_detects_ethereum_from_hex_address(self, mock_api_post):
        mock_api_post.return_value = {
            "verdict": "CLEAR",
            "safe": True,
            "risk_score": 0,
            "risk_indicators": [],
            "entity": None,
            "action": "ok",
            "chain": "ethereum",
        }
        result = self.runner.invoke(
            cli,
            ["verdict", "--address", "0xd8dA6BF26964aF9D7eEd9e03E53415D37aA96045", "--agent"],
        )
        self.assertEqual(result.exit_code, 0, result.output)
        mock_api_post.assert_called_once_with(
            "/v1/verdict",
            {
                "address": "0xd8dA6BF26964aF9D7eEd9e03E53415D37aA96045",
                "chain": "ethereum",
                "context": "",
            },
        )

    @patch("blockintql.cli.api_post")
    def test_screen_auto_detects_ethereum_from_hex_address(self, mock_api_post):
        mock_api_post.return_value = {
            "verdict": "CLEAR",
            "safe": True,
            "risk_score": 0,
            "risk_indicators": [],
            "entity": None,
            "action": "ok",
            "chain": "ethereum",
        }
        result = self.runner.invoke(
            cli,
            ["screen", "--address", "0xd8dA6BF26964aF9D7eEd9e03E53415D37aA96045", "--agent"],
        )
        self.assertEqual(result.exit_code, 0, result.output)
        mock_api_post.assert_called_once_with(
            "/v1/screen",
            {
                "address": "0xd8dA6BF26964aF9D7eEd9e03E53415D37aA96045",
                "chain": "ethereum",
            },
        )

    @patch("blockintql.cli.api_post")
    def test_generic_provider_does_not_require_key(self, mock_api_post):
        mock_api_post.return_value = {
            "verdict": "CLEAR",
            "safe": True,
            "risk_score": 0,
            "risk_indicators": [],
            "entity": None,
            "action": "ok",
            "chain": "ethereum",
        }
        with patch("blockintql.cli.get_provider") as mock_get_provider:
            class Provider:
                requires_api_key = False

                def get_address_risk(self, address, chain):
                    return {
                        "entity_name": None,
                        "entity_category": None,
                        "risk_score": 0,
                        "risk_indicators": [],
                        "sanctions_hit": False,
                        "raw": {},
                    }

            mock_get_provider.return_value = Provider()
            result = self.runner.invoke(
                cli,
                [
                    "screen",
                    "--address",
                    "0xd8dA6BF26964aF9D7eEd9e03E53415D37aA96045",
                    "--chain",
                    "ethereum",
                    "--provider",
                    "generic",
                    "--agent",
                ],
            )
        self.assertEqual(result.exit_code, 0, result.output)

    @patch("blockintql.cli.api_get")
    def test_status_uses_authenticated_account_endpoint(self, mock_api_get):
        mock_api_get.return_value = {
            "key_prefix": "biq_sk_l...1234",
            "email": "user@example.com",
            "org": "block6iq",
            "tier": "internal",
            "credits": 1000000,
        }
        result = self.runner.invoke(cli, ["status", "--agent"])
        self.assertEqual(result.exit_code, 0, result.output)
        payload = json.loads(result.output)
        self.assertEqual(payload["tier"], "internal")
        mock_api_get.assert_called_once_with("/v1/me")

    @patch("blockintql.cli.api_get")
    def test_history_uses_eth_wallet_history_endpoint(self, mock_api_get):
        mock_api_get.return_value = {"data": [], "count": 0, "source": "postgres"}
        result = self.runner.invoke(
            cli,
            ["history", "--address", "0xd8dA6BF26964aF9D7eEd9e03E53415D37aA96045", "--agent"],
        )
        self.assertEqual(result.exit_code, 0, result.output)
        mock_api_get.assert_called_once_with(
            "/v1/eth/address/0xd8dA6BF26964aF9D7eEd9e03E53415D37aA96045/history",
            {"limit": 25},
            timeout=120,
        )

    @patch("blockintql.cli.api_post")
    def test_screen_accepts_positional_address(self, mock_api_post):
        mock_api_post.return_value = {
            "verdict": "CLEAR",
            "safe": True,
            "risk_score": 0,
            "risk_indicators": [],
            "entity": None,
            "action": "ok",
            "chain": "ethereum",
        }
        result = self.runner.invoke(
            cli,
            ["screen", "0xd8dA6BF26964aF9D7eEd9e03E53415D37aA96045", "--agent"],
        )
        self.assertEqual(result.exit_code, 0, result.output)
        mock_api_post.assert_called_once_with(
            "/v1/screen",
            {
                "address": "0xd8dA6BF26964aF9D7eEd9e03E53415D37aA96045",
                "chain": "ethereum",
            },
        )

    @patch("blockintql.cli.api_get")
    def test_history_accepts_positional_address(self, mock_api_get):
        mock_api_get.return_value = {"data": [], "count": 0, "source": "postgres"}
        result = self.runner.invoke(
            cli,
            ["history", "0xd8dA6BF26964aF9D7eEd9e03E53415D37aA96045", "--agent"],
        )
        self.assertEqual(result.exit_code, 0, result.output)
        mock_api_get.assert_called_once_with(
            "/v1/eth/address/0xd8dA6BF26964aF9D7eEd9e03E53415D37aA96045/history",
            {"limit": 25},
            timeout=120,
        )

    @patch("blockintql.cli.api_get")
    def test_tx_uses_eth_verbose_transaction_endpoint(self, mock_api_get):
        txid = "0x" + "a" * 64
        mock_api_get.return_value = {"data": {"txhash": txid}, "source": "node"}
        result = self.runner.invoke(cli, ["tx", "--txid", txid, "--agent"])
        self.assertEqual(result.exit_code, 0, result.output)
        mock_api_get.assert_called_once_with(f"/v1/eth/tx/{txid}/verbose")

    def test_tx_rejects_non_ethereum_hashes(self):
        txid = "d1062eba71942b2d84d4fa52156b56314ade326c886f9b11f997054d5165e020"
        result = self.runner.invoke(cli, ["tx", "--txid", txid, "--agent"])
        self.assertNotEqual(result.exit_code, 0)
        self.assertIn("Ethereum transaction hashes must be passed", result.output)

    @patch("blockintql.cli.api_post")
    def test_query_accepts_unquoted_multiword_prompt(self, mock_api_post):
        mock_api_post.return_value = {"data": {"ok": True}}
        result = self.runner.invoke(
            cli,
            ["query", "what", "is", "the", "address", "for", "ens", "blockint.eth", "--agent"],
        )
        self.assertEqual(result.exit_code, 0, result.output)
        mock_api_post.assert_called_once_with(
            "/v1/intelligence/search",
            {"query": "what is the address for ens blockint.eth"},
        )

    @patch("blockintql.cli.api_post")
    def test_analyze_accepts_unquoted_multiword_prompt(self, mock_api_post):
        mock_api_post.return_value = {"data": {"ok": True}}
        result = self.runner.invoke(
            cli,
            [
                "analyze",
                "check",
                "for",
                "sanctions",
                "on",
                "address",
                "0xB34031a30D16177bdEC81725fFE36397D8eb6E46",
                "--agent",
            ],
        )
        self.assertEqual(result.exit_code, 0, result.output)
        mock_api_post.assert_called_once_with(
            "/v1/analyze",
            {
                "query": "check for sanctions on address 0xB34031a30D16177bdEC81725fFE36397D8eb6E46",
                "addresses": [],
                "chain": "ethereum",
                "output_format": "full",
            },
            timeout=180,
        )

    @patch("blockintql.cli.api_get")
    def test_chart_stablecoin_flows_hits_expected_endpoint(self, mock_api_get):
        mock_api_get.return_value = {"data": {"series": []}, "source": "postgres"}
        result = self.runner.invoke(
            cli,
            ["chart", "stablecoin-flows", "--hours", "12", "--agent"],
        )
        self.assertEqual(result.exit_code, 0, result.output)
        mock_api_get.assert_called_once_with(
            "/v1/eth/stablecoins/flows",
            {"hours": 12, "interval": "hour"},
            timeout=180,
        )

    @patch("blockintql.cli.api_get")
    def test_chart_wallet_stablecoins_hits_expected_endpoint(self, mock_api_get):
        mock_api_get.return_value = {"data": {"rows": []}, "source": "postgres"}
        result = self.runner.invoke(
            cli,
            ["chart", "wallet-stablecoins", "0xabc", "--days", "7", "--agent"],
        )
        self.assertEqual(result.exit_code, 0, result.output)
        mock_api_get.assert_called_once_with(
            "/v1/eth/address/0xabc/stablecoin-history",
            {"days": 7, "interval": "day"},
            timeout=90,
        )

    @patch("blockintql.cli.api_get")
    def test_chart_wallet_stablecoin_balances_hits_expected_endpoint(self, mock_api_get):
        mock_api_get.return_value = {
            "data": {
                "stablecoin_balances": {
                    "USDC": {"balance": 1000.0},
                    "USDT": {"balance": 0.0},
                },
                "wallet_total_usd": 1000.0,
            },
            "source": "node",
        }
        result = self.runner.invoke(
            cli,
            ["chart", "wallet-stablecoin-balances", "0xabc", "--agent"],
        )
        self.assertEqual(result.exit_code, 0, result.output)
        mock_api_get.assert_called_once_with(
            "/v1/eth/address/0xabc/stablecoins",
            timeout=90,
        )

    @patch("blockintql.cli.api_get")
    def test_chart_counterparties_hits_expected_endpoint(self, mock_api_get):
        mock_api_get.return_value = {"data": {"rows": []}, "source": "postgres"}
        result = self.runner.invoke(
            cli,
            ["chart", "counterparties", "0xabc", "--days", "7", "--agent"],
        )
        self.assertEqual(result.exit_code, 0, result.output)
        mock_api_get.assert_called_once_with(
            "/v1/eth/address/0xabc/stablecoin-counterparties",
            {"direction": "both", "days": 7, "limit": 25},
            timeout=90,
        )

    @patch("blockintql.cli.api_get")
    def test_stablecoins_history_hits_expected_endpoint(self, mock_api_get):
        mock_api_get.return_value = {"data": [], "source": "postgres"}
        result = self.runner.invoke(
            cli,
            ["stablecoins", "history", "--address", "0xabc", "--days", "7", "--agent"],
        )
        self.assertEqual(result.exit_code, 0, result.output)
        mock_api_get.assert_called_once_with(
            "/v1/eth/address/0xabc/stablecoin-history",
            {"days": 7, "interval": "day"},
            timeout=180,
        )

    @patch("blockintql.cli.api_get")
    def test_stablecoins_group_defaults_to_balances_when_address_is_passed(self, mock_api_get):
        mock_api_get.return_value = {"balances": {"USDC": "10.0"}, "source": "node"}
        result = self.runner.invoke(
            cli,
            ["stablecoins", "0xabc", "--agent"],
        )
        self.assertEqual(result.exit_code, 0, result.output)
        mock_api_get.assert_called_once_with("/v1/eth/address/0xabc/stablecoins")

    def test_stablecoins_group_without_args_returns_examples_for_agents(self):
        result = self.runner.invoke(
            cli,
            ["stablecoins"],
        )
        self.assertEqual(result.exit_code, 0, result.output)
        payload = json.loads(result.output)
        self.assertEqual(payload["group"], "stablecoins")
        self.assertTrue(payload["examples"])

    @patch("blockintql.cli.api_get")
    def test_eth_stablecoins_history_namespace_hits_expected_endpoint(self, mock_api_get):
        mock_api_get.return_value = {"data": [], "source": "postgres"}
        result = self.runner.invoke(
            cli,
            ["eth", "stablecoins", "history", "0xabc", "--days", "7", "--agent"],
        )
        self.assertEqual(result.exit_code, 0, result.output)
        mock_api_get.assert_called_once_with(
            "/v1/eth/address/0xabc/stablecoin-history",
            {"days": 7, "interval": "day"},
        )

    @patch("blockintql.cli.api_get")
    def test_capabilities_lists_cli_surface(self, mock_api_get):
        mock_api_get.return_value = {"capabilities": []}
        result = self.runner.invoke(cli, ["capabilities", "--agent"])
        self.assertEqual(result.exit_code, 0, result.output)
        mock_api_get.assert_called_once_with("/v1/capabilities", {"surface": "cli"}, require_auth=False)

    def test_wallet_connect_configures_cdp_mode(self):
        with patch.dict(
            os.environ,
            {
                "BLOCKINTQL_CDP_KEY_ID": "cdp-key-id",
                "BLOCKINTQL_CDP_PRIVATE_KEY": "-----BEGIN PRIVATE KEY-----demo",
            },
            clear=False,
        ):
            result = self.runner.invoke(
                cli,
                ["wallet", "connect", "--agent"],
            )
        self.assertEqual(result.exit_code, 0, result.output)
        payload = json.loads(result.output)
        self.assertTrue(payload["ready"])
        with open(self.config_file, encoding="utf-8") as handle:
            data = json.load(handle)
        self.assertEqual(data["payment"]["type"], "cdp")
        self.assertEqual(data["payment"]["private_key_env"], "BLOCKINTQL_CDP_PRIVATE_KEY")
        self.assertEqual(data["payment"]["cdp_key_id"], "cdp-key-id")

    def test_login_configures_cdp_mode(self):
        with patch.dict(
            os.environ,
            {
                "BLOCKINTQL_CDP_KEY_ID": "cdp-key-id",
                "BLOCKINTQL_CDP_PRIVATE_KEY": "-----BEGIN PRIVATE KEY-----demo",
            },
            clear=False,
        ):
            result = self.runner.invoke(
                cli,
                ["login", "--agent"],
            )
        self.assertEqual(result.exit_code, 0, result.output)
        payload = json.loads(result.output)
        self.assertTrue(payload["ready"])

    def test_wallet_status_reports_missing_configuration(self):
        result = self.runner.invoke(cli, ["wallet", "status", "--agent"])
        self.assertEqual(result.exit_code, 0, result.output)
        payload = json.loads(result.output)
        self.assertFalse(payload["ready"])
        self.assertFalse(payload["configured"])

    @patch("blockintql.cli.request_with_x402")
    @patch("blockintql.cli.httpx.request")
    def test_screen_supports_true_x402_payment(self, mock_request, mock_request_with_x402):
        with patch.dict(
            os.environ,
            {
                "BLOCKINTQL_CDP_KEY_ID": "cdp-key-id",
                "BLOCKINTQL_CDP_PRIVATE_KEY": "test-private-key",
            },
            clear=False,
        ):
            self.runner.invoke(
                cli,
                ["pay", "--auto-pay", "--max-payment", "0.10"],
            )
        payment_required = {
            "x402Version": 2,
            "accepts": [
                {
                    "scheme": "exact",
                    "price": "$0.01",
                    "network": "eip155:8453",
                    "payTo": "0xabc",
                    "asset": "0xusdc",
                }
            ],
        }
        encoded = base64.b64encode(json.dumps(payment_required).encode("utf-8")).decode("utf-8")
        with patch.dict(
            os.environ,
            {
                "BLOCKINTQL_CDP_KEY_ID": "cdp-key-id",
                "BLOCKINTQL_CDP_PRIVATE_KEY": "test-private-key",
            },
            clear=False,
        ):
            mock_request.return_value = self.make_response(
                402,
                {"error": "Payment Required"},
                headers={"PAYMENT-REQUIRED": encoded},
            )
            mock_request_with_x402.return_value = {
                "status_code": 200,
                "payload": {
                    "verdict": "CLEAR",
                    "safe": True,
                    "risk_score": 0,
                    "risk_indicators": [],
                    "entity": None,
                    "action": "ok",
                    "chain": "bitcoin",
                },
                "receipt": {"transaction": "0xtruex402"},
            }
            result = self.runner.invoke(
                cli,
                ["screen", "--address", "1A1zP1eP5QGefi2DMPTfTL5SLmv7DivfNa", "--agent"],
            )
        self.assertEqual(result.exit_code, 0, result.output)
        payload = json.loads(result.output)
        self.assertEqual(payload["payment"]["authorization_mode"], "x402-sdk")
        self.assertEqual(payload["payment"]["receipt"]["transaction"], "0xtruex402")
        mock_request_with_x402.assert_called_once()

    @patch("blockintql.cli.httpx.request")
    def test_auto_pay_policy_is_enforced(self, mock_request):
        with patch.dict(
            os.environ,
            {
                "BLOCKINTQL_CDP_KEY_ID": "cdp-key-id",
                "BLOCKINTQL_CDP_PRIVATE_KEY": "test-private-key",
            },
            clear=False,
        ):
            self.runner.invoke(
                cli,
                ["pay", "--max-payment", "0.10"],
            )
        payment_required = {
            "x402Version": 2,
            "accepts": [{"scheme": "exact", "price": "$0.01"}],
        }
        encoded = base64.b64encode(json.dumps(payment_required).encode("utf-8")).decode("utf-8")
        with patch.dict(
            os.environ,
            {
                "BLOCKINTQL_CDP_KEY_ID": "cdp-key-id",
                "BLOCKINTQL_CDP_PRIVATE_KEY": "test-private-key",
            },
            clear=False,
        ):
            mock_request.return_value = self.make_response(
                402,
                {"error": "Payment Required"},
                headers={"PAYMENT-REQUIRED": encoded},
            )
            result = self.runner.invoke(
                cli,
                ["screen", "--address", "1A1zP1eP5QGefi2DMPTfTL5SLmv7DivfNa", "--agent"],
            )
        self.assertEqual(result.exit_code, 0, result.output)
        payload = json.loads(result.output)
        self.assertEqual(payload["code"], "payment_policy_denied")

    @patch("blockintql.cli.httpx.request")
    def test_missing_wallet_configuration_returns_error(self, mock_request):
        self.runner.invoke(
            cli,
            ["pay", "--auto-pay", "--max-payment", "0.10"],
        )
        payment_required = {
            "x402Version": 2,
            "accepts": [{"scheme": "exact", "price": "$0.01"}],
        }
        encoded = base64.b64encode(json.dumps(payment_required).encode("utf-8")).decode("utf-8")
        mock_request.return_value = self.make_response(
            402,
            {"error": "Payment Required"},
            headers={"PAYMENT-REQUIRED": encoded},
        )
        result = self.runner.invoke(
            cli,
            ["screen", "--address", "1A1zP1eP5QGefi2DMPTfTL5SLmv7DivfNa", "--agent"],
        )
        self.assertEqual(result.exit_code, 0, result.output)
        payload = json.loads(result.output)
        self.assertEqual(payload["code"], "payment_configuration_error")

    @patch("blockintql.cli.request_with_x402")
    @patch("blockintql.cli.httpx.request")
    def test_payment_verification_failure_returns_error(self, mock_request, mock_request_with_x402):
        with patch.dict(
            os.environ,
            {
                "BLOCKINTQL_CDP_KEY_ID": "cdp-key-id",
                "BLOCKINTQL_CDP_PRIVATE_KEY": "test-private-key",
            },
            clear=False,
        ):
            self.runner.invoke(
                cli,
                ["pay", "--auto-pay", "--max-payment", "0.10"],
            )
        payment_required = {
            "x402Version": 2,
            "accepts": [{"scheme": "exact", "price": "$0.01"}],
        }
        encoded = base64.b64encode(json.dumps(payment_required).encode("utf-8")).decode("utf-8")
        with patch.dict(
            os.environ,
            {
                "BLOCKINTQL_CDP_KEY_ID": "cdp-key-id",
                "BLOCKINTQL_CDP_PRIVATE_KEY": "test-private-key",
            },
            clear=False,
        ):
            mock_request.return_value = self.make_response(
                402,
                {"error": "Payment Required"},
                headers={"PAYMENT-REQUIRED": encoded},
            )
            mock_request_with_x402.return_value = {
                "status_code": 402,
                "payload": {"error": "Payment verification failed."},
                "receipt": None,
            }
            result = self.runner.invoke(
                cli,
                ["screen", "--address", "1A1zP1eP5QGefi2DMPTfTL5SLmv7DivfNa", "--agent"],
            )
        self.assertEqual(result.exit_code, 0, result.output)
        payload = json.loads(result.output)
        self.assertIn("did not complete successfully", payload["error"])

    @patch("blockintql.cli.api_post")
    def test_ask_open_workspace_creates_recommended_workspace_when_not_executed(self, mock_api_post):
        mock_api_post.side_effect = [
            {
                "execution_mode": "preview",
                "recommended_surface": "workspace",
                "steps": [],
                "recommended_workspace": {
                    "name": "stablecoin-investigation",
                    "modules": ["verdict", "stablecoins", "bridge-activity", "chart"],
                    "payload": {
                        "name": "stablecoin-investigation",
                        "chain": "ethereum",
                        "modules": ["verdict", "stablecoins", "bridge-activity", "chart"],
                    },
                },
            },
            {
                "workspace_id": "ws_123",
                "status": "queued",
                "poll_url": "/v1/workspaces/ws_123",
            },
        ]
        result = self.runner.invoke(
            cli,
            [
                "ask",
                "Open a deeper stablecoin investigation workspace for this wallet",
                "--address",
                "0xd8dA6BF26964aF9D7eEd9e03E53415D37aA96045",
                "--budget-credits",
                "12",
                "--open-workspace",
                "--agent",
            ],
        )
        self.assertEqual(result.exit_code, 0, result.output)
        payload = json.loads(result.output)
        self.assertEqual(payload["execution_mode"], "created_workspace_from_plan")
        self.assertEqual(payload["executed_workspace"]["workspace_id"], "ws_123")
        self.assertTrue(payload["workspace_created_from_plan"])
        self.assertEqual(mock_api_post.call_count, 2)
        first_call = mock_api_post.call_args_list[0]
        self.assertEqual(first_call.args[0], "/v1/plan")
        self.assertTrue(first_call.kwargs["require_auth"])
        self.assertEqual(first_call.args[1]["prefer_surface"], "workspace")
        self.assertTrue(first_call.args[1]["execute_workspace"])
        second_call = mock_api_post.call_args_list[1]
        self.assertEqual(second_call.args[0], "/v1/workspaces/create")

    @patch("blockintql.cli.api_post")
    def test_ask_mode_is_forwarded_to_plan(self, mock_api_post):
        mock_api_post.return_value = {
            "execution_mode": "plan_only",
            "selected_execution_profile": {"id": "cheap", "label": "Cheap"},
            "steps": [],
            "execution_profiles": [],
        }
        result = self.runner.invoke(
            cli,
            [
                "ask",
                "Plan a compliance screening workflow",
                "--address",
                "0xd8dA6BF26964aF9D7eEd9e03E53415D37aA96045",
                "--mode",
                "cheap",
                "--agent",
            ],
        )
        self.assertEqual(result.exit_code, 0, result.output)
        mock_api_post.assert_called_once()
        first_call = mock_api_post.call_args_list[0]
        self.assertEqual(first_call.args[0], "/v1/plan")
        self.assertEqual(first_call.args[1]["execution_profile"], "cheap")

    def test_ask_plan_output_includes_continue_commands_and_workspace_steps(self):
        payload = {
            "execution_mode": "plan_only",
            "recommended_surface": "workspace",
            "estimated_total_credits": 6,
            "estimated_total_usd": 0.06,
            "investigation_brief": {
                "goal": "Investigate prediction market exposure",
                "seed_address": "0xd8dA6BF26964aF9D7eEd9e03E53415D37aA96045",
            },
            "selected_execution_profile": {
                "id": "standard",
                "label": "Standard",
                "description": "Balanced first pass with enough evidence to decide whether deeper analysis is warranted.",
            },
            "steps": [
                {
                    "capability_id": "verdict",
                    "title": "Risk verdict",
                    "surface": "api",
                    "cli_command": "blockintql verdict <address> --chain ethereum",
                    "execution": "sync",
                },
                {
                    "capability_id": "stablecoin_flows",
                    "title": "Stablecoin flow series",
                    "surface": "api",
                    "cli_command": "blockintql stablecoins flows --hours 24",
                    "execution": "sync",
                },
                {
                    "capability_id": "prediction_market_analysis",
                    "title": "Prediction market analysis",
                    "surface": "workspace",
                    "cli_command": "blockintql prediction market analysis <address>",
                    "execution": "interactive",
                },
                {
                    "capability_id": "graph_build",
                    "title": "Investigation graph build",
                    "surface": "cli",
                    "cli_command": "blockintql ask \"Build the investigation graph\" --open-workspace",
                    "execution": "interactive",
                },
            ],
            "execution_profiles": [],
            "resume_workspace": {
                "name": "investigate-prediction-m-dff6ce",
                "status": "planned",
                "activity": {},
            },
        }
        buffer = io.StringIO()
        test_console = Console(file=buffer, force_terminal=False, color_system=None)
        with patch("blockintql.cli.console", test_console), patch("blockintql.cli.sys.stdout.isatty", return_value=True):
            output(payload, agent=False, quiet=False)
        rendered = buffer.getvalue()
        self.assertIn("how to continue", rendered)
        self.assertIn("blockintql verdict --address 0xd8dA6BF26964aF9D7eEd9e03E53415D37aA96045", rendered)
        self.assertIn("blockintql stablecoins flows --hours 24", rendered)
        self.assertIn("If the workspace opens", rendered)
        self.assertIn("Run the suggested expansion", rendered)
        self.assertIn("Hydrate the graph to load the evidence surface", rendered)

    @patch("blockintql.cli.api_post")
    def test_ask_open_workspace_keeps_server_executed_workspace(self, mock_api_post):
        mock_api_post.return_value = {
            "execution_mode": "executed_workspace",
            "recommended_surface": "workspace",
            "steps": [],
            "executed_workspace": {
                "workspace_id": "ws_live",
                "status": "queued",
            },
        }
        result = self.runner.invoke(
            cli,
            [
                "ask",
                "Open a deeper stablecoin investigation workspace for this wallet",
                "--address",
                "0xd8dA6BF26964aF9D7eEd9e03E53415D37aA96045",
                "--budget-credits",
                "12",
                "--open-workspace",
                "--agent",
            ],
        )
        self.assertEqual(result.exit_code, 0, result.output)
        payload = json.loads(result.output)
        self.assertEqual(payload["execution_mode"], "executed_workspace")
        self.assertEqual(payload["executed_workspace"]["workspace_id"], "ws_live")
        mock_api_post.assert_called_once()


if __name__ == "__main__":
    unittest.main()
