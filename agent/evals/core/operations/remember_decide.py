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
from victoria.core.pages import edits, frontmatter
from victoria.core.pages.models import PageAction
from victoria.core.storage.models import PageContent, PageVersion

CASES_PATH = Path(__file__).resolve().with_suffix(".yaml")
CONVENTIONS_PATH = Path(__file__).resolve().parents[4] / "seed" / "CONVENTIONS.md"
DEFAULT_REPEATS = 3


class DecideInputs(BaseModel):
    text: str
    domains: list[str]
    related_pages: list[PageContent] = []


class DecideOutput(BaseModel):
    """The page after the model's edits were applied to the pages it was
    shown, or the reason they couldn't be."""

    page_path: str = ""
    action: PageAction | None = None
    content: str = ""
    error: str | None = None


type DecideContext = EvaluatorContext[DecideInputs, DecideOutput, None]


@dataclass
class InDomain(Evaluator[DecideInputs, DecideOutput, None]):
    domain: str

    def evaluate(self, ctx: DecideContext) -> EvaluationReason:
        return _filed_under(ctx.output, _domain(ctx.output) == self.domain)


@dataclass
class NewDomain(Evaluator[DecideInputs, DecideOutput, None]):
    def evaluate(self, ctx: DecideContext) -> EvaluationReason:
        return _filed_under(ctx.output, _domain(ctx.output) not in ctx.inputs.domains)


@dataclass
class ContentIncludes(Evaluator[DecideInputs, DecideOutput, None]):
    """Case-insensitive, and checked against the page content alone — a
    phrase that only made it into the summary doesn't count."""

    phrases: list[str]

    def evaluate(self, ctx: DecideContext) -> EvaluationReason:
        content = " ".join(ctx.output.content.split()).lower()
        missing = [p for p in self.phrases if " ".join(p.split()).lower() not in content]
        return EvaluationReason(
            value=not missing, reason=f"missing: {missing}" if missing else None
        )


@dataclass
class EditsApply(Evaluator[DecideInputs, DecideOutput, None]):
    """The model's tool calls parse and apply cleanly on the first attempt."""

    def evaluate(self, ctx: DecideContext) -> EvaluationReason:
        return EvaluationReason(value=ctx.output.error is None, reason=ctx.output.error)


@dataclass
class MaxWords(Evaluator[DecideInputs, DecideOutput, None]):
    """Counts the whole page, frontmatter included. The count is reported on
    pass as well as fail, so a baseline run shows how far over or under it is."""

    limit: int

    def evaluate(self, ctx: DecideContext) -> EvaluationReason:
        words = len(ctx.output.content.split())
        return EvaluationReason(
            value=words <= self.limit, reason=f"{words} words (limit {self.limit})"
        )


@dataclass
class ExcludesPhrases(Evaluator[DecideInputs, DecideOutput, None]):
    """Case-insensitive, checked against the page content alone."""

    phrases: list[str]

    def evaluate(self, ctx: DecideContext) -> EvaluationReason:
        lines = ctx.output.content.splitlines()
        found = {
            phrase: next(line.strip() for line in lines if phrase.lower() in line.lower())
            for phrase in self.phrases
            if any(phrase.lower() in line.lower() for line in lines)
        }
        return EvaluationReason(value=not found, reason=f"found: {found}" if found else None)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--case", action="append", dest="cases", metavar="NAME")
    parser.add_argument("--repeat", type=int, default=DEFAULT_REPEATS)
    args = parser.parse_args()

    dataset = Dataset[DecideInputs, DecideOutput, None].from_file(
        CASES_PATH,
        custom_evaluator_types=[
            InDomain,
            NewDomain,
            ContentIncludes,
            MaxWords,
            ExcludesPhrases,
            EditsApply,
        ],
    )
    if args.cases:
        _select_cases(dataset, args.cases)
    client = anthropic_client.get_client(os.environ["ANTHROPIC_API_KEY"])
    conventions = CONVENTIONS_PATH.read_text()

    def decide(inputs: DecideInputs) -> DecideOutput:
        shown = [PageVersion(**page.model_dump(), etag="eval") for page in inputs.related_pages]
        try:
            page_edits = remember._decide(client, conventions, inputs.domains, shown, inputs.text)
            edited = edits.apply_edits(shown, page_edits.commands, today=frontmatter.today())
        except edits.EditError as e:
            return DecideOutput(error=str(e))
        return DecideOutput(page_path=edited.path, action=edited.action, content=edited.content)

    report = dataset.evaluate_sync(decide, repeat=args.repeat)
    report.print(include_reasons=True)


def _select_cases(dataset: Dataset, names: list[str]) -> None:
    known = {case.name for case in dataset.cases}
    if unknown := set(names) - known:
        raise SystemExit(f"unknown case(s): {sorted(unknown)}; known: {sorted(known)}")
    dataset.cases = [case for case in dataset.cases if case.name in names]


def _domain(decision: DecideOutput) -> str:
    parts = decision.page_path.split("/")
    return parts[1] if len(parts) > 1 else ""


def _filed_under(decision: DecideOutput, passed: bool) -> EvaluationReason:
    return EvaluationReason(value=passed, reason=None if passed else decision.page_path)


if __name__ == "__main__":
    main()
