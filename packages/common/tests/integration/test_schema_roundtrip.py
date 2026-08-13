"""Integration test proving the schema + async session plumbing works
end-to-end against a real Postgres (db_test): insert a project, a task
under it, and an audit log row for the write, then read every one back.
"""

from __future__ import annotations

import uuid

from devbrain_common.audit import record_audit_event
from devbrain_common.models import AuditLog, Project, Task
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession


async def test_insert_project_task_and_audit_log_roundtrip(db_session: AsyncSession) -> None:
    project = Project(
        name="DevBrain Demo",
        description="Portfolio project",
        status="active",
        priority="high",
        owner="nikunj",
    )
    db_session.add(project)
    await db_session.flush()  # assign project.id without committing

    task = Task(
        project_id=project.id,
        title="Write Phase 1 schema",
        status="in_progress",
        assignee="nikunj",
    )
    db_session.add(task)
    await db_session.flush()

    await record_audit_event(
        db_session,
        actor="nikunj",
        tool_name="create_task",
        arguments={
            "project_id": str(project.id),
            "title": task.title,
            "token": "should-not-be-stored",
        },
        status="success",
        duration_ms=12,
    )
    await db_session.commit()

    fetched_project = await db_session.get(Project, project.id)
    assert fetched_project is not None
    assert fetched_project.name == "DevBrain Demo"
    assert fetched_project.status == "active"
    assert fetched_project.created_at is not None
    assert fetched_project.created_at.tzinfo is not None  # timezone-aware

    fetched_task = await db_session.get(Task, task.id)
    assert fetched_task is not None
    assert fetched_task.project_id == project.id
    assert fetched_task.title == "Write Phase 1 schema"

    audit_rows = (
        (await db_session.execute(select(AuditLog).where(AuditLog.tool_name == "create_task")))
        .scalars()
        .all()
    )
    assert len(audit_rows) == 1
    audit_row = audit_rows[0]
    assert audit_row.actor == "nikunj"
    assert audit_row.status == "success"
    assert audit_row.duration_ms == 12
    assert audit_row.arguments["title"] == "Write Phase 1 schema"
    assert audit_row.arguments["token"] == "***redacted***"  # never stored verbatim

    # relationship navigation works both directions
    await db_session.refresh(fetched_project, attribute_names=["tasks"])
    assert len(fetched_project.tasks) == 1
    assert fetched_project.tasks[0].id == task.id


async def test_project_not_found_returns_none(db_session: AsyncSession) -> None:
    missing = await db_session.get(Project, uuid.uuid4())
    assert missing is None


async def test_task_project_id_foreign_key_is_enforced(db_session: AsyncSession) -> None:
    """Inserting a task with a project_id that doesn't exist must fail."""
    from sqlalchemy.exc import IntegrityError

    task = Task(project_id=uuid.uuid4(), title="orphan task", status="todo")
    db_session.add(task)
    try:
        await db_session.flush()
    except IntegrityError:
        await db_session.rollback()
    else:
        raise AssertionError("expected IntegrityError for a dangling project_id FK")
