#!/usr/bin/env python3
"""Optional Tavily web search. Requires TAVILY_API_KEY in the environment."""

from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request


TAVILY_URL = "https://api.tavily.com/search"
DEFAULT_MAX = 5


def main(argv: list[str]) -> int:
    if len(argv) < 2 or argv[1] in ("-h", "--help"):
        print('Usage: search.py "query text" [max_results]', file=sys.stderr)
        return 2
    query = argv[1]
    max_results = DEFAULT_MAX
    if len(argv) >= 3:
        try:
            max_results = max(1, min(10, int(argv[2])))
        except ValueError:
            print("max_results must be an int", file=sys.stderr)
            return 2

    key = os.environ.get("TAVILY_API_KEY", "").strip()
    if not key:
        print(
            json.dumps(
                {
                    "ok": False,
                    "error": "TAVILY_API_KEY not set; skip web search or export the key",
                }
            )
        )
        return 1

    body = json.dumps(
        {
            "api_key": key,
            "query": query,
            "search_depth": "basic",
            "include_answer": True,
            "max_results": max_results,
        }
    ).encode("utf-8")
    req = urllib.request.Request(
        TAVILY_URL,
        data=body,
        headers={"Content-Type": "application/json", "User-Agent": "magellen-trade-harness/0.1"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        detail = e.read().decode("utf-8", errors="replace")[:500]
        print(json.dumps({"ok": False, "error": f"HTTP {e.code}", "detail": detail}))
        return 1
    except Exception as e:  # noqa: BLE001
        print(json.dumps({"ok": False, "error": str(e)}))
        return 1

    results = []
    for item in payload.get("results") or []:
        results.append(
            {
                "title": item.get("title"),
                "url": item.get("url"),
                "snippet": (item.get("content") or "")[:400],
            }
        )
    out = {
        "ok": True,
        "query": query,
        "answer": payload.get("answer"),
        "results": results,
    }
    print(json.dumps(out, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
