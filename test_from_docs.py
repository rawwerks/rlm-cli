#!/usr/bin/env python3
"""
Test script for PageIndex based ONLY on SKILL.md documentation.

This script attempts to:
1. Configure PageIndex with an OpenRouter backend
2. Index a test PDF
3. Print the table of contents
4. Get a specific section
"""

from rlm.clients import get_client
from rlm_cli.tools_pageindex import pi

# Configure with existing rlm backend (as documented)
client = get_client(backend="openrouter", backend_kwargs={"model_name": "google/gemini-2.0-flash-001"})
pi.configure(client)

# Check status (documented as free)
print("Status check:")
print(pi.status())
print()

# Index the PDF (documented as costing $$$)
print("Indexing PDF...")
tree = pi.index(path="/home/raw/Documents/GitHub/rlm-cli/pageindex/tests/pdfs/2023-annual-report-truncated.pdf")
print(f"Tree result: {tree}")
print()

# Print table of contents (documented as free after indexing)
print("Table of Contents:")
print(pi.toc(tree))
print()

# Get a specific section (trying node ID "0003" as shown in docs)
print("Getting section 0003:")
section = pi.get_section(tree, "0003")
print(section)
