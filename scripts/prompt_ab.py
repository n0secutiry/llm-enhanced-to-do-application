"""A/B comparison of two prioritisation prompts.

The idea: take a set of tasks you ranked by hand, let each prompt version
produce signals, compute the deterministic score from those signals, and see
which version's ordering agrees with yours more closely. Agreement is measured
with Spearman's rank correlation (1.0 = identical order, 0 = unrelated,
-1.0 = reversed).

Usage:
    uv run python scripts/prompt_ab.py                        # default dataset
    uv run python scripts/prompt_ab.py --dataset my.json \\
        --prompt-a app/prompts/priority_prompt.txt \\
        --prompt-b app/prompts/priority_prompt_v2.txt \\
        --runs 3

The dataset is a JSON list of objects:
    {"content": "...", "due_in_days": 2, "tags": ["work"], "manual_rank": 1}
`manual_rank` is your reference order, 1 being the most important task.
"""

import argparse
import asyncio
import datetime
import json
import statistics
from pathlib import Path

import ollama
from bson import ObjectId

from app.config import settings
from app.v1.llm.service import LLMService
from app.v1.todo.context import build_priority_context, render_prompt
from app.v1.todo.models import TodoModel
from app.v1.todo.scoring import days_left, priority_score

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DATASET = ROOT / "scripts" / "priority_dataset.json"


def spearman(first: list[float], second: list[float]) -> float:
    """Spearman correlation = Pearson correlation of the ranks."""
    first_ranks = _ranks(first)
    second_ranks = _ranks(second)

    mean_a = statistics.fmean(first_ranks)
    mean_b = statistics.fmean(second_ranks)

    covariance = sum(
        (a - mean_a) * (b - mean_b) for a, b in zip(first_ranks, second_ranks)
    )
    spread_a = sum((a - mean_a) ** 2 for a in first_ranks) ** 0.5
    spread_b = sum((b - mean_b) ** 2 for b in second_ranks) ** 0.5

    if spread_a == 0 or spread_b == 0:
        return 0.0

    return round(covariance / (spread_a * spread_b), 3)


def _ranks(values: list[float]) -> list[float]:
    """Ranks with ties averaged, which is what Spearman expects."""
    order = sorted(range(len(values)), key=lambda i: values[i])
    ranks = [0.0] * len(values)
    position = 0

    while position < len(order):
        end = position

        while (
            end + 1 < len(order) and values[order[end + 1]] == values[order[position]]
        ):
            end += 1

        shared = (position + end) / 2 + 1

        for index in range(position, end + 1):
            ranks[order[index]] = shared

        position = end + 1

    return ranks


def as_todo(task: dict, now: datetime.datetime) -> TodoModel:
    due_in_days = task.get("due_in_days")
    due_date = (
        now + datetime.timedelta(days=due_in_days) if due_in_days is not None else None
    )

    return TodoModel.model_validate(
        {
            "_id": ObjectId(),
            "title": task["content"][:40],
            "title_source": "user",
            "content": task["content"],
            "status": task.get("status", "open"),
            "tags": task.get("tags", []),
            "due_date": due_date,
        }
    )


async def score_dataset(
    service: LLMService,
    prompt_template: str,
    tasks: list[dict],
    now: datetime.datetime,
    runs: int,
) -> list[float]:
    """Average score per task over several runs, to smooth out model noise."""
    totals = [0.0] * len(tasks)

    for _ in range(runs):
        for index, task in enumerate(tasks):
            todo = as_todo(task, now)
            context = build_priority_context(todo, len(tasks), now)
            prompt = render_prompt(prompt_template, context)

            signals = await service.create_priority_signals(prompt)
            totals[index] += priority_score(signals, days_left(todo.due_date, now))

    return [round(total / runs, 2) for total in totals]


async def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", type=Path, default=DEFAULT_DATASET)
    parser.add_argument(
        "--prompt-a",
        type=Path,
        default=ROOT / "app" / "prompts" / "priority_prompt.txt",
    )
    parser.add_argument("--prompt-b", type=Path, default=None)
    parser.add_argument("--runs", type=int, default=1)
    args = parser.parse_args()

    tasks = json.loads(args.dataset.read_text(encoding="utf-8"))
    manual = [float(task["manual_rank"]) for task in tasks]
    now = datetime.datetime.now(datetime.timezone.utc)

    client = ollama.AsyncClient(host=settings.OLLAMA_URL, timeout=120.0)
    service = LLMService(client)

    versions = {"A": args.prompt_a}

    if args.prompt_b:
        versions["B"] = args.prompt_b

    print(f"model={settings.OLLAMA_MODEL} tasks={len(tasks)} runs={args.runs}\n")

    for name, path in versions.items():
        template = path.read_text(encoding="utf-8")
        scores = await score_dataset(service, template, tasks, now, args.runs)

        # Manual rank 1 means "most important", so a higher score should map to
        # a lower rank: the correlation is expected to be negative. Flip the
        # sign to make "bigger is better" readable.
        correlation = -spearman(manual, scores)

        print(f"prompt {name}: {path.name}")
        print(f"  spearman vs manual ranking: {correlation}")

        for task, score in sorted(zip(tasks, scores), key=lambda pair: -pair[1]):
            print(
                f"  {score:6.2f}  (manual #{task['manual_rank']})  {task['content'][:60]}"
            )

        print()

    await client.close()


if __name__ == "__main__":
    asyncio.run(main())
