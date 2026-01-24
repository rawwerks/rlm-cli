"""E2E test for depth=3 decomposition.

Tests that RLM correctly handles recursive decomposition:
- Root (depth=0) spawns child RLM (depth=1)
- Child spawns grandchild RLM (depth=2)
- Grandchild calls fall back to leaf LM (depth=3 >= max_depth)

Run with: python tests/test_depth_3_e2e.py
"""

import os
import sys

# Add paths for local imports
tests_dir = os.path.dirname(__file__)
project_root = os.path.dirname(tests_dir)
sys.path.insert(0, os.path.join(project_root, "src"))
sys.path.insert(0, os.path.join(project_root, "rlm"))

from rlm import RLM


def test_depth_3_decomposition():
    """Verify depth=3 creates proper decomposition tree and produces correct answer."""
    print("\n=== Testing depth=3 decomposition ===\n")

    api_key = os.getenv("OPENROUTER_API_KEY")
    if not api_key:
        print("ERROR: OPENROUTER_API_KEY not set")
        sys.exit(1)

    rlm = RLM(
        backend="openrouter",
        backend_kwargs={
            "model_name": "google/gemini-2.0-flash-001",
            "api_key": api_key,
        },
        environment="local",
        max_depth=3,
        max_iterations=5,  # tight to keep cost down
        max_budget=0.05,   # 5 cents cap
        verbose=True,
    )

    # Task that naturally benefits from decomposition
    # Root should delegate to children, children delegate to grandchildren
    prompt = """
You have access to llm_query(prompt) to delegate sub-tasks to another AI.

Task: Calculate the result of (2+3) * (4+5)

IMPORTANT: You MUST delegate each sub-calculation using llm_query():
1. First, call llm_query("What is 2+3? Reply with just the number.")
2. Then, call llm_query("What is 4+5? Reply with just the number.")
3. Multiply those two results together
4. Return the final answer using FINAL(your_answer)

Write Python code to solve this using llm_query() calls.
"""

    print("Prompt:", prompt[:200], "...")
    print("\n--- Running completion ---\n")

    try:
        result = rlm.completion(prompt=prompt)
        print("\n--- Result ---")
        print(f"Response: {result.response}")
        print(f"Execution time: {result.execution_time:.2f}s")
        if result.usage_summary:
            print(f"Total cost: ${result.usage_summary.total_cost:.4f}")

        # Verify correctness
        # (2+3) * (4+5) = 5 * 9 = 45
        if "45" in result.response:
            print("\n✓ Answer is correct (45)")
        else:
            print(f"\n✗ Expected 45 in response, got: {result.response}")

        # Verify budget
        if result.usage_summary and result.usage_summary.total_cost:
            if result.usage_summary.total_cost < 0.05:
                print(f"✓ Cost under budget (${result.usage_summary.total_cost:.4f} < $0.05)")
            else:
                print(f"✗ Cost exceeded budget: ${result.usage_summary.total_cost:.4f}")

    except Exception as e:
        print(f"ERROR: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

    print("\n=== Test completed ===")


if __name__ == "__main__":
    test_depth_3_decomposition()
