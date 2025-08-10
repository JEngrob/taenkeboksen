from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Dict, Any, List


@dataclass
class Task:
    title: str
    url: str
    number: Optional[int]
    text: str


@dataclass
class ProposedSolution:
    presentation: Optional[str]
    structured: Optional[Dict[str, Any]]


@dataclass
class OfficialSolution:
    text: Optional[str]


@dataclass
class Evaluation:
    text: Optional[str]
    verdict: Optional[str]  # "MATCH" | "NO MATCH" | None
    score: Optional[float]


@dataclass
class TaskResult:
    task: Task
    proposed: ProposedSolution
    official: OfficialSolution
    evaluation: Evaluation


@dataclass
class RunResult:
    generated_at_iso: str
    items: List[TaskResult]


