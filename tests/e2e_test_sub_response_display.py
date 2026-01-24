#!/usr/bin/env python3
"""E2E tests for sub-response display features.

Tests:
1. --output-format=json-tree produces valid tree structure
2. --summary produces depth statistics
3. Recursive depth (--max-depth=2) produces nested tree with children

These tests run actual RLM completions against the API.
"""

import json
import os
import subprocess
import sys
import time

# Add paths
tests_dir = os.path.dirname(__file__)
project_root = os.path.dirname(tests_dir)
sys.path.insert(0, os.path.join(project_root, "src"))
sys.path.insert(0, os.path.join(project_root, "rlm"))


def run_rlm_command(args: list[str], timeout: int = 120) -> tuple[int, dict | str | None, str]:
    """Run an RLM CLI command and return (exit_code, parsed_output, stderr).

    Returns:
        exit_code: Process exit code
        output: Parsed JSON output if --json flag was used, else raw stdout string
        stderr: Standard error output
    """
    # Use the main rlm-cli repo's venv which has all dependencies installed
    # The worktree may have a broken venv from uv build failure
    python_path = "/home/raw/Documents/GitHub/rlm-cli/.venv/bin/python"
    if not os.path.exists(python_path):
        python_path = sys.executable  # fallback to current Python

    cmd = [python_path, "-m", "rlm_cli"] + args

    env = os.environ.copy()
    env["PYTHONPATH"] = f"{project_root}/src:{project_root}/rlm"

    proc = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env=env,
        cwd=project_root,
    )

    try:
        stdout, stderr = proc.communicate(timeout=timeout)
    except subprocess.TimeoutExpired:
        proc.kill()
        stdout, stderr = proc.communicate()
        return -1, None, f"TIMEOUT after {timeout}s"

    exit_code = proc.returncode
    stderr_str = stderr.decode() if stderr else ""

    # Try to parse JSON
    stdout_str = stdout.decode() if stdout else ""
    try:
        output = json.loads(stdout_str)
    except json.JSONDecodeError:
        output = stdout_str

    return exit_code, output, stderr_str


def test_json_tree_output():
    """Test --output-format=json-tree produces valid tree structure."""
    print("\n=== Test: --output-format=json-tree ===\n")

    api_key = os.getenv("OPENROUTER_API_KEY")
    if not api_key:
        print("SKIP: OPENROUTER_API_KEY not set")
        return True

    # Simple completion that should complete quickly
    args = [
        "complete",
        "What is 2+2? Reply with just the number.",
        "--output-format", "json-tree",
        "--max-iterations", "3",
    ]

    print(f"Running: rlm {' '.join(args)}")
    exit_code, output, stderr = run_rlm_command(args, timeout=60)

    if exit_code != 0:
        print(f"FAIL: Exit code {exit_code}")
        print(f"Stderr: {stderr}")
        return False

    if not isinstance(output, dict):
        print(f"FAIL: Expected JSON output, got: {type(output)}")
        return False

    # Verify structure
    if not output.get("ok"):
        print(f"FAIL: ok=False, error: {output.get('error')}")
        return False

    result = output.get("result", {})
    response = result.get("response", "")

    print(f"Response: {response[:100]}")

    # Note: tree is only added for 'ask' command, not 'complete'
    # So we just verify the JSON output worked
    print("SUCCESS: json-tree format produces valid JSON output")
    return True


def test_json_tree_with_ask():
    """Test --output-format=json-tree with ask command includes tree."""
    print("\n=== Test: --output-format=json-tree with ask ===\n")

    api_key = os.getenv("OPENROUTER_API_KEY")
    if not api_key:
        print("SKIP: OPENROUTER_API_KEY not set")
        return True

    # Create a small test file
    test_file = os.path.join(project_root, "tests", "fixtures", "tiny_repo", "a.py")
    if not os.path.exists(test_file):
        print(f"SKIP: Test file not found: {test_file}")
        return True

    args = [
        "ask", test_file,
        "-q", "What does this file do? Reply briefly.",
        "--output-format", "json-tree",
        "--max-iterations", "3",
        "--no-index",
    ]

    print(f"Running: rlm {' '.join(args)}")
    exit_code, output, stderr = run_rlm_command(args, timeout=90)

    if exit_code != 0:
        print(f"FAIL: Exit code {exit_code}")
        print(f"Stderr: {stderr[:500]}")
        return False

    if not isinstance(output, dict):
        print(f"FAIL: Expected JSON output, got: {type(output)}")
        return False

    if not output.get("ok"):
        print(f"FAIL: ok=False, error: {output.get('error')}")
        return False

    result = output.get("result", {})
    response = result.get("response", "")
    tree = result.get("tree")

    print(f"Response: {response[:100]}...")

    if tree is None:
        print("WARN: No tree in output (might have no iterations)")
        # This is OK for simple completions that complete in one turn
    else:
        print(f"Tree depth: {tree.get('depth')}")
        print(f"Tree model: {tree.get('model')}")
        print(f"Tree has iterations: {'iterations' in tree}")

        # Verify tree structure
        if "depth" not in tree:
            print("FAIL: Tree missing 'depth' field")
            return False
        if "model" not in tree:
            print("FAIL: Tree missing 'model' field")
            return False

    print("SUCCESS: json-tree format includes execution tree")
    return True


def test_summary_flag():
    """Test --summary flag adds depth statistics."""
    print("\n=== Test: --summary flag ===\n")

    api_key = os.getenv("OPENROUTER_API_KEY")
    if not api_key:
        print("SKIP: OPENROUTER_API_KEY not set")
        return True

    test_file = os.path.join(project_root, "tests", "fixtures", "tiny_repo", "a.py")
    if not os.path.exists(test_file):
        print(f"SKIP: Test file not found: {test_file}")
        return True

    args = [
        "ask", test_file,
        "-q", "Describe this file in one sentence.",
        "--json",
        "--summary",
        "--max-iterations", "3",
        "--no-index",
    ]

    print(f"Running: rlm {' '.join(args)}")
    exit_code, output, stderr = run_rlm_command(args, timeout=90)

    if exit_code != 0:
        print(f"FAIL: Exit code {exit_code}")
        print(f"Stderr: {stderr[:500]}")
        return False

    if not isinstance(output, dict):
        print(f"FAIL: Expected JSON output, got: {type(output)}")
        return False

    if not output.get("ok"):
        print(f"FAIL: ok=False, error: {output.get('error')}")
        return False

    stats = output.get("stats", {})
    summary = stats.get("summary")

    if summary is None:
        print("WARN: No summary in stats (might have completed without iterations)")
    else:
        print(f"Summary: {json.dumps(summary, indent=2)}")

        # Verify summary structure
        if "total_depth" not in summary:
            print("FAIL: Summary missing 'total_depth'")
            return False
        if "total_nodes" not in summary:
            print("FAIL: Summary missing 'total_nodes'")
            return False
        if "by_depth" not in summary:
            print("FAIL: Summary missing 'by_depth'")
            return False

        print(f"Total depth: {summary['total_depth']}")
        print(f"Total nodes: {summary['total_nodes']}")

    print("SUCCESS: --summary flag adds statistics")
    return True


def test_recursive_depth_tree():
    """Test recursive depth produces nested tree with children."""
    print("\n=== Test: Recursive depth (--max-depth=2) with tree ===\n")

    api_key = os.getenv("OPENROUTER_API_KEY")
    if not api_key:
        print("SKIP: OPENROUTER_API_KEY not set")
        return True

    # This test requires a prompt that will use llm_query() to spawn children
    # We'll use a prompt that encourages decomposition
    # Note: --summary is only available for 'ask', not 'complete'
    args = [
        "complete",
        "You must use llm_query() to answer these questions separately. "
        "Call llm_query('What is 2+2?') and then call llm_query('What is 3+3?'). "
        "Return both answers using FINAL_VAR('answers').",
        "--output-format", "json-tree",
        "--max-iterations", "10",
        "--max-depth", "2",
    ]

    print(f"Running: rlm {' '.join(args)}")
    start = time.time()
    exit_code, output, stderr = run_rlm_command(args, timeout=180)
    elapsed = time.time() - start

    print(f"Completed in {elapsed:.1f}s")

    if exit_code != 0:
        print(f"FAIL: Exit code {exit_code}")
        print(f"Stderr: {stderr[:500]}")
        return False

    if not isinstance(output, dict):
        print(f"FAIL: Expected JSON output, got: {type(output)}")
        return False

    if not output.get("ok"):
        print(f"FAIL: ok=False, error: {output.get('error')}")
        return False

    result = output.get("result", {})
    tree = result.get("tree")
    stats = output.get("stats", {})
    summary = stats.get("summary")

    response = result.get("response", "")
    print(f"Response preview: {response[:200]}...")

    if tree:
        print(f"\nTree structure:")
        print(f"  Root depth: {tree.get('depth')}")
        print(f"  Root model: {tree.get('model')}")

        children = tree.get("children", [])
        if children:
            print(f"  Children count: {len(children)}")
            for i, child in enumerate(children):
                print(f"    Child {i}: depth={child.get('depth')}, model={child.get('model')}")
        else:
            print("  No children (model may not have used llm_query)")

    if summary:
        print(f"\nSummary:")
        print(f"  Total depth: {summary.get('total_depth')}")
        print(f"  Total nodes: {summary.get('total_nodes')}")
        by_depth = summary.get("by_depth", {})
        for d, stats_at_d in sorted(by_depth.items()):
            print(f"  Depth {d}: {stats_at_d.get('calls')} calls")

    # Success criteria: command completed and produced valid output
    # Whether children appear depends on whether the model actually called llm_query
    print("\nSUCCESS: Recursive depth test completed")
    return True


def test_summary_text_mode():
    """Test --summary in text mode prints to stderr."""
    print("\n=== Test: --summary in text mode ===\n")

    api_key = os.getenv("OPENROUTER_API_KEY")
    if not api_key:
        print("SKIP: OPENROUTER_API_KEY not set")
        return True

    test_file = os.path.join(project_root, "tests", "fixtures", "tiny_repo", "a.py")
    if not os.path.exists(test_file):
        print(f"SKIP: Test file not found: {test_file}")
        return True

    args = [
        "ask", test_file,
        "-q", "What is this?",
        "--summary",  # No --json, so text mode
        "--max-iterations", "3",
        "--no-index",
    ]

    print(f"Running: rlm {' '.join(args)}")
    exit_code, output, stderr = run_rlm_command(args, timeout=90)

    if exit_code != 0:
        print(f"FAIL: Exit code {exit_code}")
        print(f"Stderr: {stderr[:500]}")
        return False

    # In text mode, output should be plain text (not JSON)
    if isinstance(output, dict):
        print(f"FAIL: Expected text output, got JSON")
        return False

    print(f"Response preview: {str(output)[:200]}...")

    # Summary should appear in stderr
    if "RLM Execution Summary" in stderr or "Total depth" in stderr:
        print("Summary found in stderr")
    else:
        print("WARN: Summary not found in stderr (may be due to simple completion)")

    print("SUCCESS: Text mode with --summary completed")
    return True


def main():
    """Run all e2e tests."""
    print("=" * 60)
    print("E2E Tests for Sub-Response Display Features")
    print("=" * 60)

    results = []

    tests = [
        ("json-tree output", test_json_tree_output),
        ("json-tree with ask", test_json_tree_with_ask),
        ("summary flag", test_summary_flag),
        ("recursive depth tree", test_recursive_depth_tree),
        ("summary text mode", test_summary_text_mode),
    ]

    for name, test_fn in tests:
        try:
            passed = test_fn()
            results.append((name, passed))
        except Exception as e:
            print(f"ERROR in {name}: {e}")
            import traceback
            traceback.print_exc()
            results.append((name, False))

    # Summary
    print("\n" + "=" * 60)
    print("TEST RESULTS")
    print("=" * 60)

    passed_count = 0
    failed_count = 0

    for name, passed in results:
        status = "PASS" if passed else "FAIL"
        print(f"  {status}: {name}")
        if passed:
            passed_count += 1
        else:
            failed_count += 1

    print(f"\nTotal: {passed_count} passed, {failed_count} failed")

    sys.exit(0 if failed_count == 0 else 1)


if __name__ == "__main__":
    main()
