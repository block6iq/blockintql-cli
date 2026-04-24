#!/usr/bin/env python3
"""
Demo: AI Agent Autonomous Blockchain Investigation

This demonstrates how an agent can investigate a suspicious address
and generate a visual report WITHOUT human intervention.
"""

import time
from blockintql.graph.builder import GraphBuilder

def demo_agent_workflow():
    """Simulate an autonomous agent investigation"""
    
    print("\n" + "="*60)
    print("🤖 AUTONOMOUS AGENT INVESTIGATION")
    print("="*60)
    
    # Step 1: Agent receives alert
    print("\n📢 ALERT: Suspicious transaction detected")
    suspicious_addr = "bc1qxy2kgdygjrsqtzq2n0yrf2493p83kkfjhx0wlh"
    print(f"   Address: {suspicious_addr}")
    time.sleep(1)
    
    # Step 2: Agent checks risk verdict
    print("\n🔍 Step 1: Checking risk verdict...")
    time.sleep(0.5)
    print("   ✓ Verdict: CAUTION (mixing service detected)")
    
    # Step 3: Agent traces funds
    print("\n🔍 Step 2: Tracing fund flows...")
    time.sleep(0.5)
    print("   ✓ Traced 3 hops")
    print("   ✓ Found connection to known exchange")
    
    # Step 4: Agent maps exposure
    print("\n🔍 Step 3: Mapping exposure to known entities...")
    time.sleep(0.5)
    print("   ✓ 15% exposure to sanctioned addresses")
    print("   ✓ 45% exposure to mixing services")
    
    # Step 5: Agent generates visual graph
    print("\n📊 Step 4: Generating visual report...")
    time.sleep(0.5)
    
    # Build the investigation graph
    builder = GraphBuilder()
    
    # Target address
    builder.add_address(suspicious_addr, "Target (CAUTION)", "#fed330", 25)
    
    # Traced addresses
    builder.add_address("bc1qabc123", "Hop 1", "#4ecdc4", 12)
    builder.add_address("bc1qdef456", "Hop 2", "#4ecdc4", 12)
    builder.add_address("bc1qexchange", "Known Exchange", "#26de81", 15)
    
    # Risky entities
    builder.add_address("bc1qmixer", "Mixing Service", "#fc5c65", 18)
    builder.add_address("bc1qsanctioned", "Sanctioned", "#fc5c65", 18)
    
    # Transactions
    builder.add_transaction("tx1", suspicious_addr, "bc1qabc123", 1.5)
    builder.add_transaction("tx2", "bc1qabc123", "bc1qdef456", 0.8)
    builder.add_transaction("tx3", "bc1qdef456", "bc1qexchange", 0.75)
    builder.add_transaction("tx4", suspicious_addr, "bc1qmixer", 2.3)
    builder.add_transaction("tx5", "bc1qmixer", "bc1qsanctioned", 1.1)
    
    html = builder.to_html(template="force")
    
    # Save report
    report_path = "/tmp/agent_investigation_demo.html"
    with open(report_path, 'w') as f:
        f.write(html)
    
    print(f"   ✓ Report generated: {report_path}")
    
    # Step 6: Agent actions
    print("\n✅ INVESTIGATION COMPLETE")
    print("\n📧 Agent actions taken:")
    print("   • Report saved to case management system")
    print("   • Alert sent to compliance team")
    print("   • Visual graph attached to ticket")
    print("   • Transaction flagged for review")
    
    print("\n" + "="*60)
    print("🎯 Total time: 3 seconds")
    print("💰 Total cost: $0.04 (4 credits)")
    print("🚫 Human intervention: ZERO")
    print("="*60 + "\n")
    
    print(f"\n👉 View interactive report:")
    print(f"   file://{report_path}")
    
    return report_path

if __name__ == "__main__":
    demo_agent_workflow()
