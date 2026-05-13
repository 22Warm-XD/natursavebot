from __future__ import annotations

from src.services.task_extractor import extract_tasks_heuristic


def test_extracts_task_from_russian_message() -> None:
    tasks = extract_tasks_heuristic(["Я обещал завтра в 18:00 позвонить Олегу"])

    assert len(tasks) == 1
    assert "позвонить Олегу" in tasks[0].title
    assert tasks[0].actor == "я"
    assert tasks[0].deadline_at is not None
