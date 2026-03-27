"""
BlockINTQL LangChain Integration

Install:
  pip install blockintql langchain

Usage:
  from blockintql_langchain import BlockINTQLTools
  tools = BlockINTQLTools(api_key="biq_sk_live_...").get_tools()
  agent = initialize_agent(tools, llm, ...)
"""

import json
import httpx
from typing import Optional, Type
from pydantic import BaseModel, Field

try:
    from langchain.tools import BaseTool
    from langchain.callbacks.manager import CallbackManagerForToolRun
except ImportError:
    raise ImportError("pip install langchain")

API_BASE = "https://btc-index-api-385334043904.us-central1.run.app"


class BlockINTQLBaseTool(BaseTool):
    api_key: str = ""

    def _get_headers(self):
        return {"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"}

    def _api_post(self, path, body):
        try:
            r = httpx.post(f"{API_BASE}{path}", headers=self._get_headers(), json=body, timeout=30)
            r.raise_for_status()
            return r.json()
        except Exception as e:
            return {"error": str(e)}

    def _api_get(self, path, params=None):
        try:
            r = httpx.get(f"{API_BASE}{path}", headers=self._get_headers(), params=params, timeout=30)
            r.raise_for_status()
            return r.json()
        except Exception as e:
            return {"error": str(e)}


# ── VERDICT TOOL ───────────────────────────────────────────────────────────────

class VerdictInput(BaseModel):
    address: str = Field(description="Bitcoin or Ethereum address to evaluate")
    chain: str = Field(default="bitcoin", description="bitcoin or ethereum")

class VerdictTool(BlockINTQLBaseTool):
    name: str = "blockintql_verdict"
    description: str = """Get a CLEAR/CAUTION/BLOCK verdict for any blockchain address.
    Use before making payments or accepting funds.
    Returns: verdict, safe (bool), risk_score 0-100, entity, risk_indicators."""
    args_schema: Type[BaseModel] = VerdictInput

    def _run(self, address: str, chain: str = "bitcoin",
             run_manager: Optional[CallbackManagerForToolRun] = None) -> str:
        result = self._api_post("/v1/verdict", {"address": address, "chain": chain})
        return json.dumps(result, indent=2)


# ── SCREEN TOOL ────────────────────────────────────────────────────────────────

class ScreenInput(BaseModel):
    address: str = Field(description="Address to screen before transacting")
    chain: str = Field(default="bitcoin", description="bitcoin or ethereum")

class ScreenTool(BlockINTQLBaseTool):
    name: str = "blockintql_screen"
    description: str = """Screen a counterparty address before transacting.
    Checks sanctions, mixing history, and entity identification.
    Always call this before sending crypto payments.
    Returns: verdict (CLEAR/CAUTION/BLOCK), safe, risk_score, entity."""
    args_schema: Type[BaseModel] = ScreenInput

    def _run(self, address: str, chain: str = "bitcoin",
             run_manager: Optional[CallbackManagerForToolRun] = None) -> str:
        result = self._api_post("/v1/screen", {"address": address, "chain": chain})
        return json.dumps(result, indent=2)


# ── ANALYZE TOOL ───────────────────────────────────────────────────────────────

class AnalyzeInput(BaseModel):
    query: str = Field(description="Natural language analysis query")
    addresses: list = Field(default=[], description="List of addresses to analyze")
    chain: str = Field(default="ethereum", description="bitcoin or ethereum")

class AnalyzeTool(BlockINTQLBaseTool):
    name: str = "blockintql_analyze"
    description: str = """Run autonomous multi-agent blockchain analysis.
    Use for complex queries like:
    - Check if wallets are linked to sanctions
    - Find relationships between addresses
    - Detect money laundering patterns
    Returns: findings, relationships, risk scores, narrative."""
    args_schema: Type[BaseModel] = AnalyzeInput

    def _run(self, query: str, addresses: list = [], chain: str = "ethereum",
             run_manager: Optional[CallbackManagerForToolRun] = None) -> str:
        result = self._api_post("/v1/analyze", {
            "query": query, "addresses": addresses, "chain": chain
        })
        return json.dumps(result, indent=2)


# ── PROFILE TOOL ───────────────────────────────────────────────────────────────

class ProfileInput(BaseModel):
    identifier: str = Field(description="Email, telegram handle, username, phone, or address")
    identifier_type: str = Field(default="auto")

class ProfileTool(BlockINTQLBaseTool):
    name: str = "blockintql_profile"
    description: str = """Search identity graph for profiles linked to blockchain addresses.
    Data sourced from Bitcoin OP_RETURN messages — unique on-chain identity signals.
    Use to connect emails, telegram handles, usernames to crypto addresses.
    Returns: linked addresses, linked identifiers, risk score."""
    args_schema: Type[BaseModel] = ProfileInput

    def _run(self, identifier: str, identifier_type: str = "auto",
             run_manager: Optional[CallbackManagerForToolRun] = None) -> str:
        result = self._api_get("/v1/profile/search", {
            "identifier": identifier, "type": identifier_type
        })
        return json.dumps(result, indent=2)


# ── TRACE TOOL ─────────────────────────────────────────────────────────────────

class TraceInput(BaseModel):
    txid: str = Field(description="Bitcoin transaction ID to trace")
    hops: int = Field(default=5, description="Number of hops to trace")
    method: str = Field(default="fifo", description="fifo or lifo")

class TraceTool(BlockINTQLBaseTool):
    name: str = "blockintql_trace"
    description: str = """Trace funds from a Bitcoin transaction using FIFO/LIFO accounting.
    Follows money across multiple hops to find final destinations.
    Returns: destinations, hop-by-hop breakdown, exchange deposits found."""
    args_schema: Type[BaseModel] = TraceInput

    def _run(self, txid: str, hops: int = 5, method: str = "fifo",
             run_manager: Optional[CallbackManagerForToolRun] = None) -> str:
        result = self._api_post("/v1/trace", {"txid": txid, "hops": hops, "method": method})
        return json.dumps(result, indent=2)


# ── QUERY TOOL ─────────────────────────────────────────────────────────────────

class QueryInput(BaseModel):
    query: str = Field(description="Natural language blockchain intelligence query")

class QueryTool(BlockINTQLBaseTool):
    name: str = "blockintql_query"
    description: str = """Natural language blockchain intelligence.
    Ask any question about blockchain addresses, transactions, or risk.
    Examples:
    - Is this address safe to receive payment from?
    - What is the risk profile of 0xd8dA...?
    - Trace the Lazarus Group recent Bitcoin activity"""
    args_schema: Type[BaseModel] = QueryInput

    def _run(self, query: str,
             run_manager: Optional[CallbackManagerForToolRun] = None) -> str:
        result = self._api_post("/v1/intelligence/search", {"query": query})
        return json.dumps(result, indent=2)


# ── TOOLKIT ────────────────────────────────────────────────────────────────────

class BlockINTQLTools:
    """
    BlockINTQL LangChain Toolkit

    Usage:
      from blockintql_langchain import BlockINTQLTools
      from langchain.agents import initialize_agent, AgentType
      from langchain_openai import ChatOpenAI

      tools = BlockINTQLTools(api_key="biq_sk_live_...").get_tools()
      llm = ChatOpenAI(temperature=0)
      agent = initialize_agent(tools, llm, agent=AgentType.OPENAI_FUNCTIONS)

      # Agent now automatically screens before payments
      agent.run("Screen this address before I send 1 BTC: 1A1zP1e...")
    """

    def __init__(self, api_key: str):
        self.api_key = api_key

    def get_tools(self) -> list:
        kwargs = {"api_key": self.api_key}
        return [
            VerdictTool(**kwargs),
            ScreenTool(**kwargs),
            AnalyzeTool(**kwargs),
            ProfileTool(**kwargs),
            TraceTool(**kwargs),
            QueryTool(**kwargs),
        ]

    def get_screening_tools(self) -> list:
        """Minimal toolset for payment screening agents."""
        return [
            VerdictTool(api_key=self.api_key),
            ScreenTool(api_key=self.api_key),
        ]
