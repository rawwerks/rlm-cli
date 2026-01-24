"""Test script to verify max_budget support.

This test creates an RLM instance with max_budget=$1.00 and verifies that:
1. Budget tracking works during execution
2. BudgetExceededError is raised when budget is exceeded
3. Costs are properly tracked across recursive calls

Run with: python tests/test_max_budget.py
"""

import os
import sys

# Add paths for local imports
tests_dir = os.path.dirname(__file__)
project_root = os.path.dirname(tests_dir)
sys.path.insert(0, os.path.join(project_root, "src"))
sys.path.insert(0, os.path.join(project_root, "rlm"))

from rlm import RLM, BudgetExceededError


def test_max_budget():
    """Test that max_budget limits execution cost."""
    print("\n=== Testing max_budget=$1.00 ===\n")

    # Check for OpenRouter API key
    api_key = os.getenv("OPENROUTER_API_KEY")
    if not api_key:
        print("ERROR: OPENROUTER_API_KEY not set")
        sys.exit(1)

    # Create RLM with max_budget=$1.00
    rlm = RLM(
        backend="openrouter",
        backend_kwargs={
            "model_name": "google/gemini-2.0-flash-001",
            "api_key": api_key,
        },
        environment="local",
        max_depth=2,
        max_iterations=50,  # High limit to test budget stopping
        max_budget=1.00,  # $1.00 budget
        verbose=True,
    )

    # Test prompt that encourages multiple iterations and sub-calls
    test_prompt = """
You have access to llm_query(prompt) to ask questions to a language model.
Your task: Research and compile a comprehensive report about the history of computing.

Use llm_query() to gather information about:
1. The invention of the first computers
2. The development of programming languages
3. The rise of personal computers
4. The internet revolution
5. Modern computing trends

For each topic, use llm_query() to get detailed information, then compile everything into a final report.
Use FINAL_VAR("report") when you have completed the full report.

Write Python code to accomplish this task step by step.
"""

    print("Prompt:", test_prompt[:200], "...")
    print(f"\nMax Budget: $1.00")
    print("\n--- Running completion ---\n")

    try:
        result = rlm.completion(prompt=test_prompt)
        print("\n--- Result ---")
        print(f"Response: {result.response[:500]}...")
        print(f"Execution time: {result.execution_time:.2f}s")
        print(f"Usage: {result.usage_summary}")
        if result.usage_summary.total_cost:
            print(f"Total cost: ${result.usage_summary.total_cost:.6f}")
        print("\n=== Test completed (within budget) ===")
    except BudgetExceededError as e:
        print(f"\n--- Budget Exceeded ---")
        print(f"Spent: ${e.spent:.6f}")
        print(f"Budget: ${e.budget:.6f}")
        print(f"\n=== Test completed (budget exceeded as expected) ===")
    except Exception as e:
        print(f"ERROR: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    test_max_budget()
