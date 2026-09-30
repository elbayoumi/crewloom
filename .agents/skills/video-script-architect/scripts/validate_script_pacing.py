#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Validate video script word count and speaking pacing against target duration."""
import argparse
import re
import sys
from pathlib import Path


def analyze_script(text: str, target_seconds: float) -> dict:
    # Clean markdown headers, table separators, etc.
    cleaned = re.sub(r"\|.*\|", lambda m: m.group(0), text)
    words = re.findall(r"[\w\u0621-\u064A]+", cleaned)
    count = len(words)
    wps = count / target_seconds if target_seconds > 0 else 0

    return {
        "word_count": count,
        "target_seconds": target_seconds,
        "words_per_second": round(wps, 2),
        "is_safe": 2.0 <= wps <= 3.2,
        "status": "PASS" if (2.0 <= wps <= 3.2) else "WARN"
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate video script pacing.")
    parser.add_argument("--file", help="Path to script markdown file")
    parser.add_argument("--text", help="Direct text of the script")
    parser.add_argument("--duration", type=float, default=30.0, help="Target duration in seconds (default: 30)")
    args = parser.parse_args()

    content = ""
    if args.file:
        p = Path(args.file)
        if not p.exists():
            print(f"Error: File {args.file} not found")
            return 1
        content = p.read_text(encoding="utf-8")
    elif args.text:
        content = args.text
    else:
        print("Please provide --file or --text")
        return 1

    res = analyze_script(content, args.duration)
    print(f"\n📊 Script Pacing Analysis:")
    print(f"  - Total Words:        {res['word_count']} words")
    print(f"  - Target Duration:    {res['target_seconds']} seconds")
    print(f"  - Pacing Rate:        {res['words_per_second']} words/second (Ideal: 2.5 - 3.0)")
    print(f"  - Status:             {res['status']}")

    if not res['is_safe']:
        if res['words_per_second'] > 3.2:
            print("  ⚠️ Script is too fast/crowded! Reduce word count to avoid rushed voiceover.")
        else:
            print("  ⚠️ Script is too slow! Add more substance or shorten target duration.")
        return 0

    print("  ✅ Perfect pacing for high-retention short-form video!")
    return 0


if __name__ == "__main__":
    sys.exit(main())
