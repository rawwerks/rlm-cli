#!/usr/bin/env python3
"""
Test script to verify SKILL.md documentation is sufficient for PageIndex usage.

Based ONLY on the SKILL.md documentation at:
/home/raw/Documents/GitHub/rlm-cli/skills/rlm/SKILL.md

This script demonstrates:
1. Proper path setup for the submodules
2. Configure PageIndex with OpenRouter
3. Index the test PDF
4. Print the table of contents
5. Print the raw structure to show node IDs
6. Get a specific section and print its attributes
"""

import sys
import json

# Step 1: Setup paths for submodules (from SKILL.md "Setup (REQUIRED before any pi.* operation)")
sys.path.insert(0, "/home/raw/Documents/GitHub/rlm-cli/rlm")        # rlm submodule
sys.path.insert(0, "/home/raw/Documents/GitHub/rlm-cli/pageindex")  # pageindex submodule

# Step 2: Import and configure (from SKILL.md)
from rlm.clients import get_client
from rlm_cli.tools_pageindex import pi

# Configure with OpenRouter backend (from SKILL.md example)
client = get_client(backend="openrouter", backend_kwargs={"model_name": "google/gemini-2.0-flash-001"})
pi.configure(client)

# Verify configuration (from SKILL.md pi.* API Reference)
print("=== PageIndex Status ===")
print(f"Available: {pi.available()}")
print(f"Configured: {pi.configured()}")
status = pi.status()
print(f"Status: {status}")
print()

# Step 3: Index the test PDF (from SKILL.md "Indexing (costs $$$)")
pdf_path = "/home/raw/Documents/GitHub/rlm-cli/pageindex/tests/pdfs/2023-annual-report-truncated.pdf"
print(f"=== Indexing PDF ===")
print(f"Path: {pdf_path}")
tree = pi.index(path=pdf_path)
print(f"Tree type: {type(tree)}")
print()

# Step 4: Print table of contents (from SKILL.md "Viewing structure (free after indexing)")
print("=== Table of Contents ===")
print(pi.toc(tree))
print()

# Step 5: Print raw structure to show node IDs (from SKILL.md "Finding node IDs")
print("=== Raw Structure (showing node IDs) ===")
print(json.dumps(tree.raw["structure"], indent=2))
print()

# Step 6: Get a specific section and print its attributes (from SKILL.md)
print("=== Getting Section by Node ID ===")
section = pi.get_section(tree, "0000")  # Try first node

if section:
    # PINode attributes from SKILL.md: title, node_id, start_index, end_index, summary, children
    print(f"Title: {section.title}")
    print(f"Node ID: {section.node_id}")
    print(f"Start Index: {section.start_index}")
    print(f"End Index: {section.end_index}")
    print(f"Summary: {section.summary}")
    print(f"Children: {section.children}")
else:
    print("Section '0000' not found")

# Try another node ID
print()
print("=== Getting Section '0001' ===")
section2 = pi.get_section(tree, "0001")
if section2:
    print(f"Title: {section2.title}")
    print(f"Node ID: {section2.node_id}")
    print(f"Pages: {section2.start_index}-{section2.end_index}")
else:
    print("Section '0001' not found")

print()
print("=== Test Complete ===")
