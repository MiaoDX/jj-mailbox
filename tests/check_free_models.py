#!/usr/bin/env python3
"""
Validate that all models in tests/models.txt are free (zero cost) on OpenRouter.

Usage:
  LLM_API_KEY=sk-or-... python3 tests/check_free_models.py

Exit codes:
  0 — all models are free
  1 — some models are not free or not found
"""
import json
import os
import sys
import urllib.request

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
MODELS_FILE = os.path.join(SCRIPT_DIR, "models.txt")

LLM_API_KEY = os.environ.get("LLM_API_KEY", "")


def load_model_list():
    with open(MODELS_FILE) as f:
        return [
            line.strip()
            for line in f
            if line.strip() and not line.strip().startswith("#")
        ]


def fetch_openrouter_models():
    req = urllib.request.Request(
        "https://openrouter.ai/api/v1/models",
        headers={"Authorization": f"Bearer {LLM_API_KEY}"} if LLM_API_KEY else {},
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read())["data"]


def main():
    wanted = load_model_list()
    print(f"Checking {len(wanted)} models from {MODELS_FILE}")
    print()

    # openrouter/free is a meta-model, always free by definition
    skip = {"openrouter/free"}

    catalog = fetch_openrouter_models()
    by_id = {m["id"]: m for m in catalog}

    fail = False
    for model_id in wanted:
        if model_id in skip:
            print(f"  SKIP  {model_id} (meta-model, always free)")
            continue

        model = by_id.get(model_id)
        if not model:
            print(f"  FAIL  {model_id} — not found in OpenRouter catalog")
            fail = True
            continue

        pricing = model.get("pricing", {})
        prompt_cost = pricing.get("prompt", "?")
        completion_cost = pricing.get("completion", "?")
        is_free = str(prompt_cost) == "0" and str(completion_cost) == "0"

        if is_free:
            print(f"  OK    {model_id}")
        else:
            print(f"  FAIL  {model_id} — prompt={prompt_cost} completion={completion_cost}")
            fail = True

    print()
    if fail:
        print("FAIL: Some models are not free. Update tests/models.txt.")
        sys.exit(1)
    else:
        print("OK: All models are free.")


if __name__ == "__main__":
    main()
