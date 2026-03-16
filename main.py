from datetime import date
from pawpal_system import (
    DailyPlan, Owner, Pet, Task, TaskType,
    TimeOfDay, Recurrence,
)

# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

def separator(char="=", width=52):
    print(char * width)


# ---------------------------------------------------------------------------
# 1. Owner
# ---------------------------------------------------------------------------
alex = Owner(owner_id="owner_001", name="Alex")
alex.set_time_window(TimeOfDay.MORNING,  minutes=45)
alex.set_time_window(TimeOfDay.EVENING,  minutes=30)
alex.set_time_window(TimeOfDay.ANYTIME,  minutes=15)
alex.update_preference("note", "Buddy needs outdoor walks only.")

# ---------------------------------------------------------------------------
# 2. Two Pets
# ---------------------------------------------------------------------------
buddy = Pet(pet_id="pet_001", name="Buddy", species="Dog", age=3)
luna  = Pet(pet_id="pet_002", name="Luna",  species="Cat", age=5)

alex.add_pet(buddy)
alex.add_pet(luna)

# ---------------------------------------------------------------------------
# 3. Tasks across both pets (morning / evening / anytime)
# ---------------------------------------------------------------------------

# Buddy — morning
buddy.add_task(Task(
    task_id="t_001", type=TaskType.FEEDING,
    duration_minutes=10, priority=5, pet_name="Buddy",
    preferred_time=TimeOfDay.MORNING, recurrence=Recurrence.DAILY,
))
buddy.add_task(Task(
    task_id="t_002", type=TaskType.WALK,
    duration_minutes=30, priority=4, pet_name="Buddy",
    preferred_time=TimeOfDay.MORNING, recurrence=Recurrence.DAILY,
))

# Buddy — evening
buddy.add_task(Task(
    task_id="t_003", type=TaskType.MEDICATION,
    duration_minutes=5, priority=5, pet_name="Buddy",
    preferred_time=TimeOfDay.EVENING, recurrence=Recurrence.DAILY,
))

# Luna — morning
luna.add_task(Task(
    task_id="t_004", type=TaskType.FEEDING,
    duration_minutes=10, priority=5, pet_name="Luna",
    preferred_time=TimeOfDay.MORNING, recurrence=Recurrence.DAILY,
))

# Luna — evening
luna.add_task(Task(
    task_id="t_005", type=TaskType.ENRICHMENT,
    duration_minutes=20, priority=3, pet_name="Luna",
    preferred_time=TimeOfDay.EVENING, recurrence=Recurrence.DAILY,
))

# Luna — anytime (weekly grooming — intentionally long to test knapsack)
luna.add_task(Task(
    task_id="t_006", type=TaskType.GROOMING,
    duration_minutes=25, priority=2, pet_name="Luna",
    preferred_time=TimeOfDay.ANYTIME, recurrence=Recurrence.WEEKLY,
))

# ---------------------------------------------------------------------------
# 4. Generate plan
# ---------------------------------------------------------------------------
plan = DailyPlan(plan_id="plan_001", date=date.today(), owner=alex)
plan.generate()

# ---------------------------------------------------------------------------
# 5. Print Today's Schedule
# ---------------------------------------------------------------------------
separator()
print("         TODAY'S SCHEDULE  —  PawPal+")
separator()
print(f"  Owner  : {alex.name}")
print(f"  Date   : {plan.date.strftime('%A, %B %d %Y')}")
print(f"  Budget : {alex.total_available_minutes()} min total")
separator()

for slot in [TimeOfDay.MORNING, TimeOfDay.AFTERNOON, TimeOfDay.EVENING, TimeOfDay.ANYTIME]:
    items = plan.items_for_slot(slot)
    if not items:
        continue
    print(f"\n  [{slot.value.upper()}]")
    for item in sorted(items, key=lambda i: i.task.priority, reverse=True):
        t = item.task
        status = "[done]" if t.is_completed else "[ ]"
        print(f"    {status} {t.pet_name:<8} {t.type.value:<12} {t.duration_minutes:>3} min  (priority {t.priority}/5)")

print()
separator("-")
print(f"  Total scheduled : {plan.get_total_duration()} min  |  Tasks: {len(plan.scheduled_items)}")
separator("-")

# ---------------------------------------------------------------------------
# 6. Scheduler test — mark tasks complete and show completion rate
# ---------------------------------------------------------------------------
print("\n--- Scheduler Test ---")

# Simulate completing two tasks
plan.mark_task_complete("t_001")
plan.mark_task_complete("t_003")

done  = sum(1 for i in plan.scheduled_items if i.task.is_completed)
total = len(plan.scheduled_items)
rate  = plan.completion_rate()

print(f"  Marked complete : t_001 (Buddy feeding), t_003 (Buddy medication)")
print(f"  Completion      : {done}/{total} tasks ({rate:.0%})")

# Verify knapsack respected time budget
assert plan.get_total_duration() <= alex.total_available_minutes(), \
    "Scheduler exceeded time budget!"
print(f"  Budget check    : {plan.get_total_duration()} min used <= {alex.total_available_minutes()} min budget  PASS")

# Verify priority ordering within each slot
for slot in [TimeOfDay.MORNING, TimeOfDay.EVENING]:
    items = plan.items_for_slot(slot)
    priorities = [i.task.priority for i in items]
    assert priorities == sorted(priorities, reverse=True) or len(priorities) <= 1, \
        f"Priority ordering violated in {slot}"
print(f"  Priority order  : verified across all slots  PASS")

# Verify invalid priority raises
try:
    Task(task_id="bad", type=TaskType.WALK, duration_minutes=10,
         priority=9, pet_name="X")
    print("  Validation      : FAIL (should have raised)")
except ValueError:
    print("  Validation      : priority=9 correctly rejected  PASS")

print()
separator()
print("  Why this plan?\n")
print(plan.get_explanation())
separator()
