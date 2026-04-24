#!/usr/bin/env python3
"""Test agent-native graph generation"""

# Simulate what an agent would do
from blockintql.graph.builder import GraphBuilder
from blockintql.graph.agent import AgentGraph
import json

# Test 1: Build graph from trace data (simulated API response)
print("Test 1: Building graph from trace data...")
trace_data = {
    "address": "bc1qxy2kgdygjrsqtzq2n0yrf2493p83kkfjhx0wlh",
    "hops": [
        {
            "txid": "tx1",
            "from": "bc1qxy2kgdygjrsqtzq2n0yrf2493p83kkfjhx0wlh",
            "to": "bc1qabc123",
            "amount": 1.5
        },
        {
            "txid": "tx2",
            "from": "bc1qabc123",
            "to": "bc1qdef456",
            "amount": 0.8
        },
        {
            "txid": "tx3",
            "from": "bc1qdef456",
            "to": "bc1qexchange",
            "amount": 0.75
        }
    ]
}

html = AgentGraph.from_api_response(trace_data, graph_type="force")
print(f"✓ Generated {len(html)} bytes of HTML")

# Save test output
with open('/tmp/test_trace_graph.html', 'w') as f:
    f.write(html)
print("✓ Saved to /tmp/test_trace_graph.html")

# Test 2: Build graph from cluster data
print("\nTest 2: Building graph from cluster data...")
cluster_data = {
    "seed_address": "bc1qseed",
    "cluster_addresses": [
        "bc1qcluster1",
        "bc1qcluster2",
        "bc1qcluster3",
        "bc1qcluster4"
    ]
}

html2 = AgentGraph.from_api_response(cluster_data, graph_type="force")
with open('/tmp/test_cluster_graph.html', 'w') as f:
    f.write(html2)
print("✓ Saved to /tmp/test_cluster_graph.html")

# Test 3: Manual graph building (what agents can do programmatically)
print("\nTest 3: Manual graph building...")
builder = GraphBuilder()
builder.add_address("wallet_a", "Sender", "#ff6b6b", 15)
builder.add_address("wallet_b", "Receiver", "#4ecdc4", 10)
builder.add_address("wallet_c", "Exchange", "#feca57", 20)
builder.add_transaction("tx1", "wallet_a", "wallet_b", 100)
builder.add_transaction("tx2", "wallet_b", "wallet_c", 95)

html3 = builder.to_html(template="force")
with open('/tmp/test_manual_graph.html', 'w') as f:
    f.write(html3)
print("✓ Saved to /tmp/test_manual_graph.html")

print("\n✅ All tests passed!")
print("\nGenerated graphs:")
print("  1. file:///tmp/test_trace_graph.html")
print("  2. file:///tmp/test_cluster_graph.html")
print("  3. file:///tmp/test_manual_graph.html")
