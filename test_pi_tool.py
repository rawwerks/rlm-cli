#!/usr/bin/env python3
"""Test the pi.* PageIndex tool integration."""

import sys
sys.path.insert(0, "/home/raw/Documents/GitHub/rlm-cli/src")
sys.path.insert(0, "/home/raw/Documents/GitHub/rlm-cli/rlm")
sys.path.insert(0, "/home/raw/Documents/GitHub/rlm-cli/pageindex")

from rlm.clients import get_client
from rlm_cli.tools_pageindex import pi

def main():
    print("=" * 60)
    print("PageIndex Tool (pi.*) Test")
    print("=" * 60)

    # Check availability
    print(f"\npi.available(): {pi.available()}")
    print(f"pi.configured(): {pi.configured()}")
    print(f"pi.status(): {pi.status()}")

    # Configure with rlm client
    print("\nConfiguring pi with OpenRouter backend...")
    client = get_client(
        backend="openrouter",
        backend_kwargs={"model_name": "google/gemini-2.0-flash-001"},
    )
    pi.configure(client)
    print(f"pi.configured(): {pi.configured()}")

    # Index a test PDF
    print("\n⚠️  Indexing PDF (this costs money)...")
    pdf_path = "/home/raw/Documents/GitHub/rlm-cli/pageindex/tests/pdfs/2023-annual-report-truncated.pdf"
    tree = pi.index(
        path=pdf_path,
        toc_check_pages=5,
        max_pages_per_node=10,
        add_summaries=False,
    )

    print(f"\nResult: {tree}")
    print(f"\nTable of Contents:")
    print(pi.toc(tree))

    # Get a specific section
    section = pi.get_section(tree, "0003")
    if section:
        print(f"\nSection 0003: {section.title} (pages {section.start_index}-{section.end_index})")

    print("\n" + "=" * 60)
    print("pi.* Tool Test PASSED")
    print("=" * 60)
    return 0

if __name__ == "__main__":
    sys.exit(main())
