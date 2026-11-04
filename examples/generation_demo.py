"""Controlled scenario suggestions and review, without a key or network access."""

import argparse
from pathlib import Path

from thadam.generation import GenerationResult, suggest_cases, write_draft
from thadam.reporting import write_json_artifact


class ControlledProvider:
    """A scripted provider fixture; these are demonstration proposals, not model output."""

    def generate(self, request: dict) -> GenerationResult:
        candidates = []
        for identifier, category, days, eligible, rationale in (
            (
                "within-window",
                "normal",
                7,
                True,
                "An unopened item is eligible within the stated window.",
            ),
            (
                "last-eligible-day",
                "boundary",
                30,
                True,
                "The stated 30-day policy includes the last eligible day.",
            ),
            ("past-window", "failure", 31, False, "A request past the window must be declined."),
        ):
            candidates.append(
                {
                    "category": category,
                    "rationale": rationale,
                    "uncertainty": "",
                    "case": {
                        "id": identifier,
                        "input": {"days": days, "unopened": True},
                        "assertions": [
                            {
                                "id": "eligibility",
                                "type": "output_equals",
                                "expected": {"eligible": eligible},
                            }
                        ],
                    },
                }
            )
        return GenerationResult(candidates, "controlled_demo", "scripted fixture — no AI request")


def create_demo(destination: Path) -> None:
    """Create new demo evidence; refuse an existing destination."""
    destination.mkdir(parents=True, exist_ok=False)
    context = {
        "description": "Controlled demo: a refund eligibility agent",
        "behavior": "Return {eligible: true} exactly when an item is unopened and days is between 0 and 30 inclusive; otherwise return {eligible: false}.",
        "examples": [{"input": {"days": 3, "unopened": True}, "output": {"eligible": True}}],
        "count": 3,
    }
    write_json_artifact(context, destination / "context.json")
    write_draft(suggest_cases(ControlledProvider(), context), destination / "suggestions.json")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=Path("artifacts/generation-demo"))
    args = parser.parse_args()
    create_demo(args.output)
    print(f"Controlled drafts saved to {args.output}. No model or agent was executed.")
    print(f"Open: thadam dashboard {args.output}")


if __name__ == "__main__":
    main()
