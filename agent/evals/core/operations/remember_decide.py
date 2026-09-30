"""Evals for remember's filing decision against the real model.

Calls the Anthropic API, so it's kept out of the pytest suite and run on
demand from agent/:

    ANTHROPIC_API_KEY=... uv run --group evals python evals/core/operations/remember_decide.py

Pass --case (repeatable) to run only some cases, and --repeat to change how
many times each one runs.
"""

import argparse
import os
from dataclasses import dataclass
from pathlib import Path

from pydantic import BaseModel
from pydantic_evals import Dataset
from pydantic_evals.evaluators import EvaluationReason, Evaluator, EvaluatorContext

from victoria.core.integrations import anthropic_client
from victoria.core.operations import remember
from victoria.core.operations.models import FileNoteDecision
from victoria.core.storage.models import PageContent

CASES_PATH = Path(__file__).resolve().with_suffix(".yaml")
CONVENTIONS_PATH = Path(__file__).resolve().parents[4] / "seed" / "CONVENTIONS.md"
DEFAULT_REPEATS = 3


class DecideInputs(BaseModel):
    text: str
    domains: list[str]
    related_pages: list[PageContent] = []


type DecideContext = EvaluatorContext[DecideInputs, FileNoteDecision, None]


@dataclass
class InDomain(Evaluator[DecideInputs, FileNoteDecision, None]):
    domain: str

    def evaluate(self, ctx: DecideContext) -> EvaluationReason:
        return _filed_under(ctx.output, _domain(ctx.output) == self.domain)


@dataclass
class NewDomain(Evaluator[DecideInputs, FileNoteDecision, None]):
    def evaluate(self, ctx: DecideContext) -> EvaluationReason:
        return _filed_under(ctx.output, _domain(ctx.output) not in ctx.inputs.domains)


@dataclass
class ContentIncludes(Evaluator[DecideInputs, FileNoteDecision, None]):
    """Case-insensitive, and checked against the page content alone — a
    phrase that only made it into the summary doesn't count."""

    phrases: list[str]

    def evaluate(self, ctx: DecideContext) -> EvaluationReason:
        content = ctx.output.full_content.lower()
        missing = [p for p in self.phrases if p.lower() not in content]
        return EvaluationReason(
            value=not missing, reason=f"missing: {missing}" if missing else None
        )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--case", action="append", dest="cases", metavar="NAME")
    parser.add_argument("--repeat", type=int, default=DEFAULT_REPEATS)
    args = parser.parse_args()

    dataset = Dataset[DecideInputs, FileNoteDecision, None].from_file(
        CASES_PATH, custom_evaluator_types=[InDomain, NewDomain, ContentIncludes]
    )
    if args.cases:
        _select_cases(dataset, args.cases)
    client = anthropic_client.get_client(os.environ["ANTHROPIC_API_KEY"])
    conventions = CONVENTIONS_PATH.read_text()

    def decide(inputs: DecideInputs) -> FileNoteDecision:
        return remember._decide(
            client, conventions, inputs.domains, inputs.related_pages, inputs.text
        )

    report = dataset.evaluate_sync(decide, repeat=args.repeat)
    report.print(include_reasons=True)


def _select_cases(dataset: Dataset, names: list[str]) -> None:
    known = {case.name for case in dataset.cases}
    if unknown := set(names) - known:
        raise SystemExit(f"unknown case(s): {sorted(unknown)}; known: {sorted(known)}")
    dataset.cases = [case for case in dataset.cases if case.name in names]


def _domain(decision: FileNoteDecision) -> str:
    return decision.page_path.split("/")[1]


def _filed_under(decision: FileNoteDecision, passed: bool) -> EvaluationReason:
    return EvaluationReason(value=passed, reason=None if passed else decision.page_path)


if __name__ == "__main__":
    main()
