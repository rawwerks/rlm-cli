#!/usr/bin/env python3
"""
E2E test: Full PageIndex PDF processing using rlm backend.
"""

import sys
import os
import json

# Set up Python path properly
sys.path.insert(0, "/home/raw/Documents/GitHub/rlm-cli/rlm")
sys.path.insert(0, "/home/raw/Documents/GitHub/rlm-cli/pageindex")

from rlm.clients import get_client
from pageindex.lm_adapter import set_lm_client
from pageindex.page_index import page_index

def main():
    print("\n" + "=" * 60)
    print("PageIndex Full PDF Test")
    print("Using rlm backend (OpenRouter)")
    print("=" * 60 + "\n")

    # Create rlm client
    client = get_client(
        backend="openrouter",
        backend_kwargs={
            "model_name": "google/gemini-2.0-flash-001",
        },
    )

    # Configure PageIndex
    set_lm_client(client)

    # Use the truncated test PDF (smaller, faster)
    pdf_path = "/home/raw/Documents/GitHub/rlm-cli/pageindex/tests/pdfs/2023-annual-report-truncated.pdf"

    print(f"Processing: {pdf_path}")
    print("This may take a moment...\n")

    try:
        result = page_index(
            doc=pdf_path,
            toc_check_page_num=5,  # Check fewer pages for speed
            max_page_num_each_node=5,
            if_add_node_id="yes",
            if_add_node_summary="no",  # Skip summaries for speed
            if_add_doc_description="no",
        )

        print("=" * 60)
        print("SUCCESS! PageIndex result:")
        print("=" * 60)
        print(f"Document: {result.get('doc_name', 'Unknown')}")
        print(f"\nTree structure:")
        print(json.dumps(result.get('structure', []), indent=2, default=str)[:2000])
        if len(json.dumps(result.get('structure', []))) > 2000:
            print("... (truncated)")

        print("\n" + "=" * 60)
        print("E2E TEST PASSED")
        print("PageIndex successfully processed PDF using rlm backend!")
        print("=" * 60)
        return 0

    except Exception as e:
        print(f"\nTEST FAILED: {e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())
