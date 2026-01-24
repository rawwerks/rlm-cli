"""Test script to verify budget exceeded handling.

This test uses a very low budget ($0.0001) to ensure the budget is exceeded.

Run with: python tests/test_budget_exceeded.py
"""

import os
import sys

# Add paths for local imports
tests_dir = os.path.dirname(__file__)
project_root = os.path.dirname(tests_dir)
sys.path.insert(0, os.path.join(project_root, "src"))
sys.path.insert(0, os.path.join(project_root, "rlm"))

from rlm import RLM, BudgetExceededError


def test_budget_exceeded():
    """Test that BudgetExceededError is raised when budget is exceeded."""
    print("\n=== Testing budget exceeded (max_budget=$0.0001) ===\n")

    # Check for OpenRouter API key
    api_key = os.getenv("OPENROUTER_API_KEY")
    if not api_key:
        print("ERROR: OPENROUTER_API_KEY not set")
        sys.exit(1)

    # Create RLM with very low budget to force exceeding
    rlm = RLM(
        backend="openrouter",
        backend_kwargs={
            "model_name": "google/gemini-2.0-flash-001",
            "api_key": api_key,
        },
        environment="local",
        max_depth=2,
        max_iterations=10,
        max_budget=0.0001,  # Very low budget: $0.0001 (will be exceeded quickly)
        verbose=True,
    )

    test_prompt = """
You have access to llm_query(prompt) to ask questions to a language model.
Your task: Write a detailed essay about artificial intelligence.
Use llm_query() multiple times to gather information.
Use FINAL_VAR("essay") when done.
"""

    print(f"Max Budget: $0.0001")
    print("\n--- Running completion (expecting budget exceeded) ---\n")

    try:
        result = rlm.completion(prompt=test_prompt)
        print("\n--- Unexpected: Completed within budget ---")
        print(f"Cost: ${result.usage_summary.total_cost:.6f}")
        print("WARNING: Budget was not exceeded. Test may need adjustment.")
    except BudgetExceededError as e:
        print(f"\n--- Budget Exceeded (as expected) ---")
        print(f"Spent: ${e.spent:.6f}")
        print(f"Budget: ${e.budget:.6f}")
        print(f"\n=== SUCCESS: BudgetExceededError raised correctly ===")
    except Exception as e:
        print(f"ERROR: Unexpected exception: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    test_budget_exceeded()
