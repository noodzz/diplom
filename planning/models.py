from dataclasses import dataclass
from typing import List, Dict, Optional


@dataclass
class Task:
    """Модель задачи."""
    id: int
    name: str
    duration: int
    position: str
    predecessors: List[int] = None

    # Параметры сетевой модели
    early_start: Optional[int] = None
    early_finish: Optional[int] = None
    late_start: Optional[int] = None
    late_finish: Optional[int] = None
    is_critical: bool = False
    reserve: int = 0


@dataclass
class Employee:
    """Модель сотрудника."""
    id: int
    name: str
    position: str
    days_off: List[str]


@dataclass
class Project:
    """Модель проекта."""
    id: int
    name: str
    tasks: List[Task]
    employees: List[Employee]