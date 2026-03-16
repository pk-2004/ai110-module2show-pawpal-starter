from __future__ import annotations
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from enum import Enum
from typing import Optional


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

class TaskType(Enum):
    WALK = "walk"
    FEEDING = "feeding"
    MEDICATION = "medication"
    ENRICHMENT = "enrichment"
    GROOMING = "grooming"


class Recurrence(Enum):
    ONCE = "once"
    DAILY = "daily"
    WEEKLY = "weekly"


class TimeOfDay(Enum):
    MORNING = "morning"      # 06:00–12:00
    AFTERNOON = "afternoon"  # 12:00–17:00
    EVENING = "evening"      # 17:00–21:00
    ANYTIME = "anytime"


# ---------------------------------------------------------------------------
# Task
# ---------------------------------------------------------------------------

@dataclass
class Task:
    task_id: str
    type: TaskType
    duration_minutes: int
    priority: int                              # validated: 1 (low) – 5 (high)
    pet_name: str                              # back-reference for readable output
    recurrence: Recurrence = Recurrence.DAILY
    preferred_time: TimeOfDay = TimeOfDay.ANYTIME
    is_completed: bool = False
    scheduled_time: Optional[datetime] = None

    def __post_init__(self) -> None:
        if not 1 <= self.priority <= 5:
            raise ValueError(f"priority must be 1–5, got {self.priority}")
        if self.duration_minutes <= 0:
            raise ValueError("duration_minutes must be positive")

    def mark_complete(self) -> None:
        self.is_completed = True

    def reschedule(self, time: datetime) -> None:
        self.scheduled_time = time

    def get_priority(self) -> int:
        return self.priority

    def is_overdue(self) -> bool:
        if self.scheduled_time is None or self.is_completed:
            return False
        return datetime.now() > self.scheduled_time

    def next_occurrence(self, after: date) -> Optional[date]:
        """Return the next date this task should appear, or None if ONCE."""
        if self.recurrence == Recurrence.ONCE:
            return None
        if self.recurrence == Recurrence.DAILY:
            return after + timedelta(days=1)
        if self.recurrence == Recurrence.WEEKLY:
            return after + timedelta(weeks=1)

    def clone_for_date(self, target_date: date) -> Task:
        """Return a fresh, incomplete copy of this task for a new day."""
        return Task(
            task_id=f"{self.task_id}_{target_date.isoformat()}",
            type=self.type,
            duration_minutes=self.duration_minutes,
            priority=self.priority,
            pet_name=self.pet_name,
            recurrence=self.recurrence,
            preferred_time=self.preferred_time,
        )


# ---------------------------------------------------------------------------
# Pet
# ---------------------------------------------------------------------------

@dataclass
class Pet:
    pet_id: str
    name: str
    species: str
    age: int
    tasks: list[Task] = field(default_factory=list)

    def add_task(self, task: Task) -> None:
        task.pet_name = self.name          # keep back-reference in sync
        self.tasks.append(task)

    def remove_task(self, task_id: str) -> None:
        self.tasks = [t for t in self.tasks if t.task_id != task_id]

    def get_tasks(self) -> list[Task]:
        return list(self.tasks)

    def get_pending_tasks(self) -> list[Task]:
        return [t for t in self.tasks if not t.is_completed]

    def get_overdue_tasks(self) -> list[Task]:
        return [t for t in self.tasks if t.is_overdue()]

    def tasks_for_time_of_day(self, slot: TimeOfDay) -> list[Task]:
        return [
            t for t in self.get_pending_tasks()
            if t.preferred_time in (slot, TimeOfDay.ANYTIME)
        ]

    def rollover_recurring_tasks(self, target_date: date) -> list[Task]:
        """
        Clone each recurring task for target_date and add it to the pet.
        Call once at the start of a new day.
        """
        new_tasks: list[Task] = []
        for task in self.tasks:
            next_date = task.next_occurrence(target_date - timedelta(days=1))
            if next_date == target_date:
                clone = task.clone_for_date(target_date)
                new_tasks.append(clone)
        for t in new_tasks:
            self.add_task(t)
        return new_tasks


# ---------------------------------------------------------------------------
# Owner
# ---------------------------------------------------------------------------

@dataclass
class TimeWindow:
    slot: TimeOfDay
    available_minutes: int

    def __post_init__(self) -> None:
        if self.available_minutes < 0:
            raise ValueError("available_minutes cannot be negative")


@dataclass
class Owner:
    owner_id: str
    name: str
    time_windows: list[TimeWindow] = field(default_factory=list)
    preferences: dict[str, str] = field(default_factory=dict)
    pets: list[Pet] = field(default_factory=list)

    # ------------------------------------------------------------------
    # Pet management
    # ------------------------------------------------------------------

    def add_pet(self, pet: Pet) -> None:
        self.pets.append(pet)

    def get_pet(self, name: str) -> Optional[Pet]:
        return next((p for p in self.pets if p.name == name), None)

    # ------------------------------------------------------------------
    # Time budget
    # ------------------------------------------------------------------

    def set_time_window(self, slot: TimeOfDay, minutes: int) -> None:
        for w in self.time_windows:
            if w.slot == slot:
                w.available_minutes = minutes
                return
        self.time_windows.append(TimeWindow(slot, minutes))

    def total_available_minutes(self) -> int:
        return sum(w.available_minutes for w in self.time_windows)

    def minutes_for_slot(self, slot: TimeOfDay) -> int:
        for w in self.time_windows:
            if w.slot == slot:
                return w.available_minutes
        return 0

    # ------------------------------------------------------------------
    # Preferences
    # ------------------------------------------------------------------

    def get_preferences(self) -> dict[str, str]:
        return dict(self.preferences)

    def update_preference(self, key: str, value: str) -> None:
        self.preferences[key] = value

    # ------------------------------------------------------------------
    # Task helpers
    # ------------------------------------------------------------------

    def all_pending_tasks(self) -> list[tuple[Task, Pet]]:
        """Return (task, pet) pairs for every pending task across all pets."""
        return [
            (task, pet)
            for pet in self.pets
            for task in pet.get_pending_tasks()
        ]


# ---------------------------------------------------------------------------
# DailyPlan
# ---------------------------------------------------------------------------

@dataclass
class ScheduledItem:
    task: Task
    pet: Pet
    slot: TimeOfDay


@dataclass
class DailyPlan:
    plan_id: str
    date: date
    owner: Owner
    scheduled_items: list[ScheduledItem] = field(default_factory=list)
    skipped_items: list[tuple[Task, Pet]] = field(default_factory=list)
    explanation: str = ""

    # ------------------------------------------------------------------
    # Core generation
    # ------------------------------------------------------------------

    def generate(self) -> None:
        """
        Build the day's plan respecting per-slot time budgets.
        Uses 0/1 knapsack within each slot so a single long task
        doesn't block shorter ones that would otherwise fit.
        Unused slot budget rolls into the ANYTIME pool.
        """
        self.scheduled_items = []
        self.skipped_items = []
        all_pairs = self.owner.all_pending_tasks()

        slot_order = [TimeOfDay.MORNING, TimeOfDay.AFTERNOON, TimeOfDay.EVENING, TimeOfDay.ANYTIME]
        buckets: dict[TimeOfDay, list[tuple[Task, Pet]]] = {s: [] for s in slot_order}
        for task, pet in all_pairs:
            buckets[task.preferred_time].append((task, pet))

        chosen: list[ScheduledItem] = []
        skipped: list[tuple[Task, Pet]] = []
        leftover_minutes = 0

        for slot in [TimeOfDay.MORNING, TimeOfDay.AFTERNOON, TimeOfDay.EVENING]:
            budget = self.owner.minutes_for_slot(slot)
            slot_chosen, slot_skipped = self._knapsack(buckets[slot], budget)
            used = sum(t.duration_minutes for t, _ in slot_chosen)
            leftover_minutes += max(0, budget - used)
            for task, pet in slot_chosen:
                chosen.append(ScheduledItem(task=task, pet=pet, slot=slot))
            skipped.extend(slot_skipped)

        # ANYTIME tasks + leftover budget from fixed slots
        anytime_budget = self.owner.minutes_for_slot(TimeOfDay.ANYTIME) + leftover_minutes
        anytime_chosen, anytime_skipped = self._knapsack(buckets[TimeOfDay.ANYTIME], anytime_budget)
        for task, pet in anytime_chosen:
            chosen.append(ScheduledItem(task=task, pet=pet, slot=TimeOfDay.ANYTIME))
        skipped.extend(anytime_skipped)

        self.scheduled_items = chosen
        self.skipped_items = skipped
        self._build_explanation(chosen, skipped)

    # ------------------------------------------------------------------
    # Manual overrides
    # ------------------------------------------------------------------

    def add_task(self, task: Task, pet: Pet, slot: TimeOfDay = TimeOfDay.ANYTIME) -> None:
        self.scheduled_items.append(ScheduledItem(task=task, pet=pet, slot=slot))

    def remove_task(self, task_id: str) -> bool:
        before = len(self.scheduled_items)
        self.scheduled_items = [i for i in self.scheduled_items if i.task.task_id != task_id]
        return len(self.scheduled_items) < before

    # ------------------------------------------------------------------
    # Queries
    # ------------------------------------------------------------------

    def get_explanation(self) -> str:
        return self.explanation

    def get_total_duration(self) -> int:
        return sum(i.task.duration_minutes for i in self.scheduled_items)

    def items_for_slot(self, slot: TimeOfDay) -> list[ScheduledItem]:
        return [i for i in self.scheduled_items if i.slot == slot]

    def mark_task_complete(self, task_id: str) -> bool:
        for item in self.scheduled_items:
            if item.task.task_id == task_id:
                item.task.mark_complete()
                return True
        return False

    def completion_rate(self) -> float:
        if not self.scheduled_items:
            return 0.0
        done = sum(1 for i in self.scheduled_items if i.task.is_completed)
        return done / len(self.scheduled_items)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _knapsack(
        pairs: list[tuple[Task, Pet]],
        budget: int,
    ) -> tuple[list[tuple[Task, Pet]], list[tuple[Task, Pet]]]:
        """
        0/1 knapsack: maximise total priority score within budget.
        Falls back to priority/duration ratio greedy for n > 20.
        """
        n = len(pairs)
        if n == 0:
            return [], []

        if n <= 20:
            dp = [[0] * (budget + 1) for _ in range(n + 1)]
            for i, (task, _) in enumerate(pairs, 1):
                d = task.duration_minutes
                p = task.priority
                for w in range(budget + 1):
                    dp[i][w] = dp[i - 1][w]
                    if d <= w:
                        dp[i][w] = max(dp[i][w], dp[i - 1][w - d] + p)
            chosen_idx: set[int] = set()
            w = budget
            for i in range(n, 0, -1):
                if dp[i][w] != dp[i - 1][w]:
                    chosen_idx.add(i - 1)
                    w -= pairs[i - 1][0].duration_minutes
        else:
            ranked = sorted(
                range(n),
                key=lambda i: pairs[i][0].priority / pairs[i][0].duration_minutes,
                reverse=True,
            )
            chosen_idx = set()
            remaining = budget
            for i in ranked:
                if pairs[i][0].duration_minutes <= remaining:
                    chosen_idx.add(i)
                    remaining -= pairs[i][0].duration_minutes

        chosen = [pairs[i] for i in range(n) if i in chosen_idx]
        skipped = [pairs[i] for i in range(n) if i not in chosen_idx]
        return chosen, skipped

    def _build_explanation(
        self,
        chosen: list[ScheduledItem],
        skipped: list[tuple[Task, Pet]],
    ) -> None:
        budget = self.owner.total_available_minutes()
        used = self.get_total_duration()
        lines = [
            f"=== PawPal Daily Plan — {self.date} ===",
            f"Time budget: {budget} min | Scheduled: {used} min | Tasks: {len(chosen)}",
            "",
        ]

        for slot in [TimeOfDay.MORNING, TimeOfDay.AFTERNOON, TimeOfDay.EVENING, TimeOfDay.ANYTIME]:
            items = self.items_for_slot(slot)
            if not items:
                continue
            lines.append(f"[{slot.value.upper()}]")
            for item in sorted(items, key=lambda i: i.task.priority, reverse=True):
                t = item.task
                lines.append(
                    f"  • {t.pet_name}: {t.type.value} "
                    f"({t.duration_minutes} min, priority {t.priority}/5)"
                )

        if skipped:
            lines += ["", f"Skipped {len(skipped)} task(s) — insufficient time:"]
            for task, pet in skipped:
                lines.append(
                    f"  ✗ {pet.name}: {task.type.value} "
                    f"({task.duration_minutes} min, priority {task.priority}/5)"
                )

        pref_note = self.owner.get_preferences().get("note")
        if pref_note:
            lines += ["", f"Owner note: {pref_note}"]

        self.explanation = "\n".join(lines)
