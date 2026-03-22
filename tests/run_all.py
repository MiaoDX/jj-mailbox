#!/usr/bin/env python3
"""Run all jj-mailbox tests.

Usage:
    uv run tests/run_all.py            # all tests (needs LLM_API_KEY)
    uv run tests/run_all.py --no-llm   # skip LLM tests
"""
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BIN = str(ROOT / "bin" / "jj-mailbox")

PASS = FAIL = 0


def _load_dotenv():
    env_file = ROOT / ".env"
    if not env_file.exists():
        return
    for line in env_file.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        key, _, val = line.partition("=")
        os.environ.setdefault(key.strip(), val.strip())


def run_test(name: str, args: list[str]) -> bool:
    global PASS, FAIL
    print(f"--- {name}")
    result = subprocess.run(args, capture_output=True)
    if result.returncode == 0:
        print("  PASS")
        PASS += 1
        return True
    print("  FAIL")
    FAIL += 1
    return False


def main():
    global FAIL
    _load_dotenv()
    no_llm = "--no-llm" in sys.argv
    os.chmod(BIN, 0o755)

    # -- Core CLI --
    repo = tempfile.mkdtemp(prefix="jj-mailbox-test-")
    try:
        os.environ["JJ_MAILBOX_REPO"] = repo

        print("=== Core CLI Tests ===")
        run_test("init", [BIN, "init", repo])
        run_test("register alice", [BIN, "register", "alice", "Agent"])
        run_test("register bob", [BIN, "register", "bob", "Agent"])

        os.environ["JJ_MAILBOX_AGENT"] = "alice"
        run_test("send", [BIN, "send", "bob", "Hello", "Test message"])

        os.environ["JJ_MAILBOX_AGENT"] = "bob"
        run_test("inbox", [BIN, "inbox", "bob"])
        run_test("read", [BIN, "read", "bob"])
        run_test("reply", [BIN, "send", "alice", "Reply", "Got it"])
        run_test("status", [BIN, "status"])

        del os.environ["JJ_MAILBOX_AGENT"]
    finally:
        shutil.rmtree(repo, ignore_errors=True)
        os.environ.pop("JJ_MAILBOX_REPO", None)

    # -- Scripted agent --
    print("\n=== Scripted Agent Test ===")
    run_test("scripted/test.py", [sys.executable, str(ROOT / "tests/scripted/test.py")])
    run_test("adapters/test.py", [sys.executable, str(ROOT / "tests/adapters/test.py")])

    # -- Comparison benchmark --
    print("\n=== Comparison Benchmark ===")
    run_test("comparison/benchmark.py", [sys.executable, str(ROOT / "tests/comparison/benchmark.py")])

    # -- LLM tests --
    if not no_llm:
        print("\n=== LLM Tests (requires LLM_API_KEY) ===")
        if not os.environ.get("LLM_API_KEY"):
            print("  FAIL: LLM_API_KEY not set (use --no-llm to skip)")
            FAIL += 1
        else:
            run_test("llm/test.py", [sys.executable, str(ROOT / "tests/llm/test.py")])
            run_test("smolagents/test.py", [sys.executable, str(ROOT / "tests/smolagents/test.py")])

    # -- Summary --
    print(f"\n===============================")
    print(f"  PASS: {PASS}  FAIL: {FAIL}")
    print(f"===============================")
    sys.exit(1 if FAIL else 0)


if __name__ == "__main__":
    main()
