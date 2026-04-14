"""
BlockINTQL LangChain Integration.

Usage:
  from blockintql.integrations.langchain import BlockINTQLTools
"""

import json
from typing import List, Optional, Type

import httpx
from pydantic import BaseModel, Field

try:
    from langchain.callbacks.manager import CallbackManagerForToolRun
    from langchain.tools import BaseTool
except ImportError as exc:
    raise ImportError("pip install langchain") from exc


API_BASE = "https://btc-index-api-385334043904.us-central1.run.app"


class BlockINTQLBaseTool(BaseTool):
    api_key: str = ""

    def _get_headers(self):
        return {"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"}

    def _api_post(self, path, body):
        try:
            response = httpx.post(f"{API_BASE}{path}", headers=self._get_headers(), json=body, timeout=30)
            response.raise_for_status()
            return response.json()
        except Exception as exc:
            return {"error": str(exc)}

    def _api_get(self, path, params=None):
        try:
            response = httpx.get(f"{API_BASE}{path}", headers=self._get_headers(), params=params, timeout=30)
            response.raise_for_status()
            return response.json()
        except Exception as exc:
            return {"error": str(exc)}


class VerdictInput(BaseModel):
    address: str = Field(description="Bitcoin or Ethereum address to evaluate")
    chain: str = Field(default="bitcoin", description="bitcoin or ethereum")


class VerdictTool(BlockINTQLBaseTool):
    name: str = "blockintql_verdict"
    description: str = (
        "Get a CLEAR/CAUTION/BLOCK verdict for any blockchain address. "
        "Returns verdict, safe, risk_score, entity, and risk indicators."
    )
    args_schema: Type[BaseModel] = VerdictInput

    def _run(self, address: str, chain: str = "bitcoin", run_manager: Optional[CallbackManagerForToolRun] = None) -> str:
        return json.dumps(self._api_post("/v1/verdict", {"address": address, "chain": chain}), indent=2)


class ScreenInput(BaseModel):
    address: str = Field(description="Address to screen before transacting")
    chain: str = Field(default="bitcoin", description="bitcoin or ethereum")


class ScreenTool(BlockINTQLBaseTool):
    name: str = "blockintql_screen"
    description: str = (
        "Screen a counterparty address before transacting. "
        "Returns verdict, safe, risk_score, entity, and any flags."
    )
    args_schema: Type[BaseModel] = ScreenInput

    def _run(self, address: str, chain: str = "bitcoin", run_manager: Optional[CallbackManagerForToolRun] = None) -> str:
        return json.dumps(self._api_post("/v1/screen", {"address": address, "chain": chain}), indent=2)


class AnalyzeInput(BaseModel):
    query: str = Field(description="Natural language analysis query")
    addresses: List[str] = Field(default_factory=list, description="List of addresses to analyze")
    chain: str = Field(default="ethereum", description="bitcoin or ethereum")


class AnalyzeTool(BlockINTQLBaseTool):
    name: str = "blockintql_analyze"
    description: str = "Run multi-agent blockchain analysis for more complex investigations."
    args_schema: Type[BaseModel] = AnalyzeInput

    def _run(
        self,
        query: str,
        addresses: Optional[List[str]] = None,
        chain: str = "ethereum",
        run_manager: Optional[CallbackManagerForToolRun] = None,
    ) -> str:
        payload = {"query": query, "addresses": addresses or [], "chain": chain}
        return json.dumps(self._api_post("/v1/analyze", payload), indent=2)


class ProfileInput(BaseModel):
    identifier: str = Field(description="Email, telegram handle, username, phone, or address")
    identifier_type: str = Field(default="auto")


class ProfileTool(BlockINTQLBaseTool):
    name: str = "blockintql_profile"
    description: str = "Search the identity graph for profiles linked to blockchain addresses."
    args_schema: Type[BaseModel] = ProfileInput

    def _run(
        self,
        identifier: str,
        identifier_type: str = "auto",
        run_manager: Optional[CallbackManagerForToolRun] = None,
    ) -> str:
        payload = {"identifier": identifier, "type": identifier_type}
        return json.dumps(self._api_get("/v1/profile/search", payload), indent=2)


class TraceInput(BaseModel):
    txid: str = Field(description="Bitcoin transaction ID to trace")
    hops: int = Field(default=5, description="Number of hops to trace")
    method: str = Field(default="fifo", description="fifo or lifo")


class TraceTool(BlockINTQLBaseTool):
    name: str = "blockintql_trace"
    description: str = "Trace funds from a Bitcoin transaction using FIFO or LIFO accounting."
    args_schema: Type[BaseModel] = TraceInput

    def _run(
        self,
        txid: str,
        hops: int = 5,
        method: str = "fifo",
        run_manager: Optional[CallbackManagerForToolRun] = None,
    ) -> str:
        payload = {"txid": txid, "hops": hops, "method": method}
        return json.dumps(self._api_post("/v1/trace", payload), indent=2)


class QueryInput(BaseModel):
    query: str = Field(description="Natural language blockchain intelligence query")


class QueryTool(BlockINTQLBaseTool):
    name: str = "blockintql_query"
    description: str = "Ask a natural-language blockchain intelligence question."
    args_schema: Type[BaseModel] = QueryInput

    def _run(self, query: str, run_manager: Optional[CallbackManagerForToolRun] = None) -> str:
        return json.dumps(self._api_post("/v1/intelligence/search", {"query": query}), indent=2)


class BlockINTQLTools:
    """Toolkit wrapper for LangChain users."""

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
        return [
            VerdictTool(api_key=self.api_key),
            ScreenTool(api_key=self.api_key),
        ]
