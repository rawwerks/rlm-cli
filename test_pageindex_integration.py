#!/usr/bin/env python3
"""
E2E test: PageIndex using rlm's backend system.

This proves that PageIndex can use any rlm backend (openrouter, anthropic, etc.)
instead of being hardcoded to OpenAI.
"""

import sys
import json

# Add paths for local development
sys.path.insert(0, "/home/raw/Documents/GitHub/rlm-cli/rlm")
sys.path.insert(0, "/home/raw/Documents/GitHub/rlm-cli/pageindex/pageindex")

from rlm.clients import get_client
from lm_adapter import set_lm_client
from utils import ChatGPT_API, extract_json

def test_basic_completion():
    """Test that the adapter works with a simple completion."""
    print("=" * 60)
    print("TEST 1: Basic completion via rlm backend")
    print("=" * 60)

    # Create rlm client using OpenRouter
    client = get_client(
        backend="openrouter",
        backend_kwargs={
            "model_name": "google/gemini-2.0-flash-001",  # Fast and cheap for testing
        },
    )

    # Configure PageIndex to use this client
    set_lm_client(client)

    # Test the drop-in ChatGPT_API function
    prompt = "Reply with exactly: INTEGRATION_TEST_SUCCESS"
    response = ChatGPT_API(model=None, prompt=prompt)

    print(f"Prompt: {prompt}")
    print(f"Response: {response}")

    assert "INTEGRATION_TEST_SUCCESS" in response or "SUCCESS" in response.upper(), \
        f"Unexpected response: {response}"
    print("PASSED\n")


def test_json_extraction():
    """Test that PageIndex's JSON extraction prompts work."""
    print("=" * 60)
    print("TEST 2: JSON extraction (core PageIndex pattern)")
    print("=" * 60)

    # This mimics how PageIndex asks for structured output
    prompt = """
    Return the following JSON structure:
    {
        "toc_detected": "yes",
        "thinking": "This is a test"
    }
    Directly return the final JSON structure. Do not output anything else.
    """

    response = ChatGPT_API(model=None, prompt=prompt)
    print(f"Raw response: {response[:200]}...")

    # Parse it like PageIndex does
    parsed = extract_json(response)
    print(f"Parsed JSON: {json.dumps(parsed, indent=2)}")

    assert parsed.get("toc_detected") == "yes", f"JSON parsing failed: {parsed}"
    print("PASSED\n")


def test_toc_detection_prompt():
    """Test actual PageIndex TOC detection prompt pattern."""
    print("=" * 60)
    print("TEST 3: TOC detection prompt (real PageIndex pattern)")
    print("=" * 60)

    # Simulate a page with TOC content
    sample_page = """
    Table of Contents

    Chapter 1: Introduction .................. 1
    Chapter 2: Methods ....................... 15
    Chapter 3: Results ....................... 45
    Chapter 4: Discussion .................... 78
    References ............................... 95
    """

    prompt = f"""
    Your job is to detect if there is a table of content provided in the given text.

    Given text: {sample_page}

    return the following JSON format:
    {{
        "thinking": <why do you think there is a table of content in the given text>
        "toc_detected": "<yes or no>",
    }}

    Directly return the final JSON structure. Do not output anything else.
    Please note: abstract,summary, notation list, figure list, table list, etc. are not table of contents."""

    response = ChatGPT_API(model=None, prompt=prompt)
    print(f"Raw response: {response[:300]}...")

    parsed = extract_json(response)
    print(f"Parsed: {json.dumps(parsed, indent=2)}")

    assert parsed.get("toc_detected") == "yes", f"TOC should be detected: {parsed}"
    print("PASSED\n")


def main():
    print("\n" + "=" * 60)
    print("PageIndex + rlm Integration Test")
    print("Using OpenRouter backend")
    print("=" * 60 + "\n")

    try:
        test_basic_completion()
        test_json_extraction()
        test_toc_detection_prompt()

        print("=" * 60)
        print("ALL TESTS PASSED")
        print("PageIndex successfully using rlm backend!")
        print("=" * 60)
        return 0
    except Exception as e:
        print(f"\nTEST FAILED: {e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())
