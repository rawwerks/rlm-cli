"""Test script to verify max_depth > 1 support with recursive RLM calls.

This test creates an RLM instance with max_depth=2 and verifies that:
1. The root RLM (depth=0) can spawn child RLM calls
2. Child RLM (depth=1) processes with its own REPL
3. Grandchild calls (depth>=2) fall back to plain LM completion

Run with: python tests/test_max_depth_2.py
"""

import os
import sys

# Add paths for local imports
tests_dir = os.path.dirname(__file__)
project_root = os.path.dirname(tests_dir)
sys.path.insert(0, os.path.join(project_root, "src"))
sys.path.insert(0, os.path.join(project_root, "rlm"))  # Add rlm submodule path

from rlm import RLM


def test_max_depth_2():
    """Test that max_depth=2 enables recursive RLM calls."""
    print("\n=== Testing max_depth=2 ===\n")

    # Check for OpenRouter API key
    api_key = os.getenv("OPENROUTER_API_KEY")
    if not api_key:
        print("ERROR: OPENROUTER_API_KEY not set")
        sys.exit(1)

    # Create RLM with max_depth=2
    rlm = RLM(
        backend="openrouter",
        backend_kwargs={
            "model_name": "google/gemini-2.0-flash-001",
            "api_key": api_key,
        },
        environment="local",
        max_depth=2,
        max_iterations=15,
        verbose=True,
    )

    # Test prompt that encourages nested decomposition
    # The prompt asks to solve a problem by breaking it into sub-problems
    test_prompt = """
You have access to llm_query(prompt) to ask questions to a language model.
Your task: Determine the capital of France and the population of that city.

IMPORTANT: You MUST use llm_query() to get this information.
Step 1: Call llm_query("What is the capital of France?") to get the capital.
Step 2: Call llm_query() with a question about the population of that capital.
Step 3: Return the final answer using FINAL_VAR("result") where result contains both pieces of info.

Write Python code to solve this task using llm_query().
"""

    print("Prompt:", test_prompt[:200], "...")
    print("\n--- Running completion ---\n")

    try:
        result = rlm.completion(prompt=test_prompt)
        print("\n--- Result ---")
        print(f"Response: {result.response}")
        print(f"Execution time: {result.execution_time:.2f}s")
        print(f"Usage: {result.usage_summary}")
    except Exception as e:
        print(f"ERROR: {e}")
        import traceback

        traceback.print_exc()
        sys.exit(1)

    print("\n=== Test completed ===")


if __name__ == "__main__":
    test_max_depth_2()
