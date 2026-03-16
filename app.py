import streamlit as st
from datetime import date
from pawpal_system import (
    DailyPlan, Owner, Pet, Task, TaskType,
    TimeOfDay, Recurrence,
)

st.set_page_config(page_title="PawPal+", page_icon="🐾", layout="centered")
st.title("🐾 PawPal+")
st.caption("Pet care planning assistant")

# ---------------------------------------------------------------------------
# Session state — persists across reruns
# ---------------------------------------------------------------------------
if "owner" not in st.session_state:
    st.session_state.owner = None
if "pets" not in st.session_state:
    st.session_state.pets: dict[str, Pet] = {}   # name → Pet
if "plan" not in st.session_state:
    st.session_state.plan = None

# ---------------------------------------------------------------------------
# Section 1 — Owner setup
# ---------------------------------------------------------------------------
st.header("1. Owner")

col1, col2 = st.columns(2)
with col1:
    owner_name = st.text_input("Owner name", value="Alex")
with col2:
    morning_budget = st.number_input("Morning budget (min)", min_value=0, max_value=240, value=45)

col3, col4 = st.columns(2)
with col3:
    evening_budget = st.number_input("Evening budget (min)", min_value=0, max_value=240, value=30)
with col4:
    anytime_budget = st.number_input("Anytime budget (min)", min_value=0, max_value=240, value=15)

if st.button("Save owner"):
    owner = Owner(owner_id="owner_001", name=owner_name)
    owner.set_time_window(TimeOfDay.MORNING,   minutes=int(morning_budget))
    owner.set_time_window(TimeOfDay.EVENING,   minutes=int(evening_budget))
    owner.set_time_window(TimeOfDay.ANYTIME,   minutes=int(anytime_budget))
    st.session_state.owner = owner
    st.session_state.pets = {}
    st.session_state.plan = None
    st.success(f"Owner **{owner_name}** saved — total budget: {owner.total_available_minutes()} min")

# ---------------------------------------------------------------------------
# Section 2 — Add a pet
# ---------------------------------------------------------------------------
st.divider()
st.header("2. Add a Pet")

if st.session_state.owner is None:
    st.info("Save an owner first.")
else:
    col5, col6, col7 = st.columns(3)
    with col5:
        pet_name = st.text_input("Pet name", value="Buddy")
    with col6:
        species = st.selectbox("Species", ["Dog", "Cat", "Rabbit", "Other"])
    with col7:
        age = st.number_input("Age (years)", min_value=0, max_value=30, value=3)

    if st.button("Add pet"):
        if pet_name in st.session_state.pets:
            st.warning(f"A pet named **{pet_name}** already exists.")
        else:
            pet_id = f"pet_{len(st.session_state.pets) + 1:03d}"
            pet = Pet(pet_id=pet_id, name=pet_name, species=species, age=int(age))
            st.session_state.pets[pet_name] = pet
            st.session_state.owner.add_pet(pet)
            st.success(f"Added **{pet_name}** ({species}, age {age})")

    if st.session_state.pets:
        st.write("**Pets:**", ", ".join(
            f"{p.name} ({p.species})" for p in st.session_state.pets.values()
        ))

# ---------------------------------------------------------------------------
# Section 3 — Add a task
# ---------------------------------------------------------------------------
st.divider()
st.header("3. Add a Task")

TASK_TYPE_MAP = {t.value.capitalize(): t for t in TaskType}
PRIORITY_MAP  = {"1 – Low": 1, "2": 2, "3 – Medium": 3, "4": 4, "5 – High": 5}
TIME_MAP      = {t.value.capitalize(): t for t in TimeOfDay}
RECUR_MAP     = {r.value.capitalize(): r for r in Recurrence}

if not st.session_state.pets:
    st.info("Add at least one pet first.")
else:
    col8, col9 = st.columns(2)
    with col8:
        task_pet = st.selectbox("For pet", list(st.session_state.pets.keys()))
    with col9:
        task_type = st.selectbox("Task type", list(TASK_TYPE_MAP.keys()))

    col10, col11, col12 = st.columns(3)
    with col10:
        task_duration = st.number_input("Duration (min)", min_value=1, max_value=240, value=20)
    with col11:
        task_priority = st.selectbox("Priority", list(PRIORITY_MAP.keys()), index=2)
    with col12:
        task_time = st.selectbox("Time of day", list(TIME_MAP.keys()), index=3)

    task_recurrence = st.selectbox("Recurrence", list(RECUR_MAP.keys()), index=1)

    if st.button("Add task"):
        pet = st.session_state.pets[task_pet]
        new_type = TASK_TYPE_MAP[task_type]

        # --- Conflict detection: duplicate task type for same pet ---
        duplicate = next(
            (t for t in pet.get_tasks() if t.type == new_type and not t.is_completed),
            None,
        )
        if duplicate:
            st.warning(
                f"Conflict: **{task_pet}** already has a pending "
                f"**{task_type.lower()}** task ({duplicate.duration_minutes} min, "
                f"priority {duplicate.priority}/5). Add anyway or remove the existing one first."
            )
        else:
            task_id = f"t_{task_pet[:3].lower()}_{len(pet.tasks) + 1:03d}"
            task = Task(
                task_id=task_id,
                type=new_type,
                duration_minutes=int(task_duration),
                priority=PRIORITY_MAP[task_priority],
                pet_name=task_pet,
                preferred_time=TIME_MAP[task_time],
                recurrence=RECUR_MAP[task_recurrence],
            )
            pet.add_task(task)
            st.session_state.plan = None   # invalidate stale plan
            st.success(
                f"Added **{task_type.lower()}** for {task_pet} "
                f"({task_duration} min, priority {PRIORITY_MAP[task_priority]}/5, {task_time.lower()})"
            )

    # --- Sorting & Filtering ---
    all_tasks_raw = [
        {"Pet": p.name, "Type": t.type.value, "Duration": t.duration_minutes,
         "Priority": t.priority, "Time": t.preferred_time.value}
        for p in st.session_state.pets.values()
        for t in p.get_tasks()
    ]

    if all_tasks_raw:
        st.write("**All tasks:**")
        fc1, fc2, fc3 = st.columns(3)
        with fc1:
            filter_pets = st.multiselect(
                "Filter by pet",
                options=list(st.session_state.pets.keys()),
                default=list(st.session_state.pets.keys()),
                key="filter_pets",
            )
        with fc2:
            filter_types = st.multiselect(
                "Filter by type",
                options=list(TASK_TYPE_MAP.keys()),
                default=list(TASK_TYPE_MAP.keys()),
                key="filter_types",
            )
        with fc3:
            sort_by = st.selectbox(
                "Sort by",
                ["Priority (high→low)", "Priority (low→high)", "Duration (long→short)", "Duration (short→long)"],
                key="sort_by",
            )

        filtered = [
            r for r in all_tasks_raw
            if r["Pet"] in filter_pets and r["Type"].capitalize() in filter_types
        ]

        sort_key_map = {
            "Priority (high→low)":    (lambda r: r["Priority"], True),
            "Priority (low→high)":    (lambda r: r["Priority"], False),
            "Duration (long→short)":  (lambda r: r["Duration"], True),
            "Duration (short→long)":  (lambda r: r["Duration"], False),
        }
        key_fn, reverse = sort_key_map[sort_by]
        filtered.sort(key=key_fn, reverse=reverse)

        if filtered:
            st.table(filtered)
        else:
            st.info("No tasks match the current filters.")
    else:
        st.info("No tasks yet.")

# ---------------------------------------------------------------------------
# Section 4 — Generate schedule
# ---------------------------------------------------------------------------
st.divider()
st.header("4. Generate Schedule")

owner = st.session_state.owner
has_tasks = owner is not None and any(
    p.get_pending_tasks() for p in st.session_state.pets.values()
)

if not has_tasks:
    st.info("Add an owner, at least one pet, and at least one task first.")
else:
    if st.button("Generate schedule", type="primary"):
        plan = DailyPlan(
            plan_id="plan_001",
            date=date.today(),
            owner=owner,
        )
        plan.generate()
        st.session_state.plan = plan

    if st.session_state.plan:
        plan = st.session_state.plan
        st.success(
            f"Scheduled **{len(plan.scheduled_items)} task(s)** "
            f"using **{plan.get_total_duration()} min** "
            f"of {owner.total_available_minutes()} min budget"
        )

        # Display by slot
        for slot in [TimeOfDay.MORNING, TimeOfDay.AFTERNOON, TimeOfDay.EVENING, TimeOfDay.ANYTIME]:
            items = plan.items_for_slot(slot)
            if not items:
                continue
            st.subheader(f"{slot.value.capitalize()}")
            for item in sorted(items, key=lambda i: i.task.priority, reverse=True):
                t = item.task
                done = t.is_completed
                label = f"~~{t.pet_name}: {t.type.value} ({t.duration_minutes} min, priority {t.priority}/5)~~" \
                    if done else \
                    f"**{t.pet_name}**: {t.type.value} — {t.duration_minutes} min  ·  priority {t.priority}/5"
                checked = st.checkbox(label, value=done, key=t.task_id)
                if checked and not done:
                    plan.mark_task_complete(t.task_id)

        # Completion progress
        rate = plan.completion_rate()
        st.progress(rate, text=f"Completion: {rate:.0%}")

        # --- Conflict detection: per-slot budget overrun check ---
        st.subheader("Slot Budget Check")
        for slot in [TimeOfDay.MORNING, TimeOfDay.AFTERNOON, TimeOfDay.EVENING, TimeOfDay.ANYTIME]:
            budget = owner.minutes_for_slot(slot)
            if budget == 0:
                continue
            used = sum(
                i.task.duration_minutes
                for i in plan.items_for_slot(slot)
            )
            if used > budget:
                st.error(f"**{slot.value.capitalize()}**: {used} min used > {budget} min budget — overrun!")
            else:
                st.success(f"**{slot.value.capitalize()}**: {used}/{budget} min used")

        # --- Skipped tasks (couldn't fit in budget) ---
        if plan.skipped_items:
            st.subheader("Skipped Tasks (time conflicts)")
            skipped_rows = [
                {
                    "Pet": pet.name,
                    "Type": task.type.value,
                    "Duration": task.duration_minutes,
                    "Priority": task.priority,
                    "Reason": "Insufficient time remaining in slot",
                }
                for task, pet in plan.skipped_items
            ]
            st.warning(f"{len(skipped_rows)} task(s) could not be scheduled within the time budget.")
            st.table(skipped_rows)
        else:
            st.success("All tasks fit within the budget — no conflicts.")

        # Explanation
        with st.expander("Why this plan?"):
            st.text(plan.get_explanation())
