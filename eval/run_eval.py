from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.config import Settings
from src.evaluation import run_evaluation, save_results


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the labeled Feedback Copilot evaluation.")
    parser.add_argument("--use-gemini", action="store_true", help="Evaluate Gemini extraction when configured.")
    parser.add_argument("--output", default="eval/results.json")
    args = parser.parse_args()
    settings = Settings()
    if args.use_gemini and not settings.gemini_enabled:
        parser.error("--use-gemini requires GEMINI_API_KEY")
    result = run_evaluation(settings, use_gemini=args.use_gemini)
    save_results(result, args.output)
    print(json.dumps({key: value for key, value in result.items() if key != "extraction_details"}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
