"""
orchestrator/master.py
-----------------------
Orchestration loop. Executes tasks across all 5 specialist agents
in dependency order with a 4-minute per-task timeout.

Key behaviours:
- Executes ALL pending tasks whose dependencies are satisfied each loop tick.
- Cascade-fails tasks whose dependencies permanently failed/blocked.
- Exponential backoff only when truly idle.
- Hard 240s timeout per task via run_with_timeout.
- Passes task_id, stage, project_id to every agent call.
"""

import time
from database import crud
from database.db import SessionLocal
from orchestrator.tasks import decompose_with_fallback, topological_sort
from agents import get_agent
from utils.logger import get_logger
from utils.executor import run_with_timeout

logger = get_logger(__name__)

STAGES = ["idea", "validation", "build", "gtm", "scale"]

_BASE_SLEEP   = 1.0
_MAX_SLEEP    = 15.0
_BACKOFF_MULT = 1.5


def _update_progress(db, project_id: int) -> int:
    try:
        return crud.update_project_progress(db, project_id)
    except Exception as e:
        logger.warning("Progress update failed for project=%d: %s", project_id, e)
        return 0


def orchestrate_project(project_id: int) -> None:
    logger.info("Orchestration started for project_id=%d", project_id)
    sleep_time = _BASE_SLEEP

    db = SessionLocal()
    try:
        project = crud.get_project(db, project_id)
        if not project:
            logger.error("Project %d not found -- aborting.", project_id)
            return

        while project.status == "active":
            stage = project.current_stage

            if stage not in STAGES:
                logger.error("Project %d has unknown stage '%s' -- stopping.", project_id, stage)
                break

            # 1. Generate tasks for this stage if none exist
            stage_tasks = crud.get_tasks_for_stage(db, project_id, stage)

            if not stage_tasks:
                logger.info("Generating tasks for project=%d stage=%s", project_id, stage)
                try:
                    specs        = decompose_with_fallback(project.goal, stage)
                    sorted_specs = topological_sort(specs)
                    for spec in sorted_specs:
                        crud.create_task(db, project_id, spec.to_db_dict(stage))
                    db.commit()
                    stage_tasks = crud.get_tasks_for_stage(db, project_id, stage)
                    logger.info("Created %d tasks for project=%d stage=%s",
                                len(stage_tasks), project_id, stage)
                    sleep_time = _BASE_SLEEP
                except Exception as exc:
                    logger.error("Task generation failed: %s", exc, exc_info=True)
                    sleep_time = min(sleep_time * _BACKOFF_MULT, _MAX_SLEEP)
                    time.sleep(sleep_time)
                    db.refresh(project)
                    continue

            # 2. Classify tasks
            completed_ids = {t.task_id for t in stage_tasks if t.status == "completed"}
            failed_ids    = {t.task_id for t in stage_tasks if t.status in ("failed", "blocked")}
            pending       = [t for t in stage_tasks if t.status == "pending"]
            in_progress   = [t for t in stage_tasks if t.status == "in_progress"]
            awaiting      = [t for t in stage_tasks if t.status == "awaiting_approval"]

            logger.info(
                "project=%d stage=%s | total=%d pending=%d in_progress=%d "
                "awaiting=%d failed=%d completed=%d",
                project_id, stage, len(stage_tasks), len(pending), len(in_progress),
                len(awaiting), len(failed_ids), len(completed_ids),
            )

            # 3. Find runnable tasks, cascade-fail unresolvable ones
            did_work = False
            runnable = []

            for task in pending:
                deps = set(task.dependencies or [])
                if deps.issubset(completed_ids):
                    runnable.append(task)
                    continue
                unresolvable = deps & failed_ids
                if unresolvable:
                    crud.update_task_status(
                        db, task.id, "failed",
                        result=f"Skipped: dependency failed: {sorted(unresolvable)}"
                    )
                    db.commit()
                    logger.warning("Task '%s' cascade-failed (blocked deps: %s)",
                                   task.task_id, unresolvable)
                    did_work = True

            # 4. Execute runnable tasks
            for task in runnable:
                # Risk gate
                if task.risk == "critical":
                    crud.update_task_status(db, task.id, "blocked",
                                            result="Blocked: critical risk -- requires manual review.")
                    db.commit()
                    logger.warning("Task '%s' BLOCKED (critical risk).", task.task_id)
                    did_work = True
                    continue

                if task.risk == "high" and task.requires_approval == "true":
                    crud.update_task_status(db, task.id, "awaiting_approval",
                                            result="Paused: awaiting founder approval.")
                    db.commit()
                    logger.info("Task '%s' PAUSED (awaiting approval).", task.task_id)
                    did_work = True
                    continue

                # Mark in-progress
                crud.update_task_status(db, task.id, "in_progress")
                db.commit()

                agent = get_agent(task.assigned_agent)
                if agent is None:
                    crud.update_task_status(db, task.id, "failed",
                                            result=f"No agent for '{task.assigned_agent}'")
                    db.commit()
                    logger.error("No agent for '%s'.", task.assigned_agent)
                    did_work = True
                    continue

                logger.info("Executing '%s' -> agent=%s (project=%d stage=%s)",
                            task.task_id, task.assigned_agent, project_id, stage)

                try:
                    result = run_with_timeout(
                        agent.execute,
                        timeout=240,
                        description=task.description,
                        task_id=task.task_id,
                        stage=task.stage,
                        project_id=project_id,
                    )
                    output = (result.get("output", "")
                              if isinstance(result, dict) else str(result))
                    crud.update_task_status(db, task.id, "completed", result=output)
                    db.commit()
                    _update_progress(db, project_id)
                    db.commit()
                    logger.info("Task '%s' COMPLETED (project=%d)", task.task_id, project_id)

                except TimeoutError:
                    crud.update_task_status(db, task.id, "failed",
                                            result="Timed out after 240 seconds.")
                    db.commit()
                    logger.error("Task '%s' timed out.", task.task_id)

                except Exception as exc:
                    crud.update_task_status(db, task.id, "failed", result=str(exc))
                    db.commit()
                    logger.error("Task '%s' FAILED: %s", task.task_id, exc, exc_info=True)

                did_work = True

            # 5. Check stage completion
            stage_tasks   = crud.get_tasks_for_stage(db, project_id, stage)
            terminal      = {"completed", "blocked", "failed", "awaiting_approval"}
            all_terminal  = all(t.status in terminal for t in stage_tasks)
            has_completed = any(t.status == "completed" for t in stage_tasks)

            if all_terminal and stage_tasks and has_completed:
                completed_count = sum(1 for t in stage_tasks if t.status == "completed")
                logger.info("Stage '%s' complete: %d/%d tasks completed.",
                            stage, completed_count, len(stage_tasks))
                idx = STAGES.index(stage)
                if idx + 1 < len(STAGES):
                    next_stage = STAGES[idx + 1]
                    crud.update_project_stage(db, project_id, next_stage)
                    db.commit()
                    logger.info("Project %d: %s -> %s", project_id, stage, next_stage)
                    sleep_time = _BASE_SLEEP
                else:
                    crud.update_project_status(db, project_id, "completed")
                    _update_progress(db, project_id)
                    db.commit()
                    logger.info("Project %d FULLY COMPLETED.", project_id)
                    break

            # 6. Backoff when idle
            if did_work:
                sleep_time = _BASE_SLEEP
            else:
                sleep_time = min(sleep_time * _BACKOFF_MULT, _MAX_SLEEP)

            time.sleep(sleep_time)
            db.refresh(project)

    except Exception as exc:
        logger.critical("Unhandled orchestration error for project=%d: %s",
                        project_id, exc, exc_info=True)
    finally:
        db.close()
        logger.info("Orchestration thread exiting for project_id=%d", project_id)