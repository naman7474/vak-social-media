from vak_bot.workers.celery_app import celery_app


def test_video_tasks_are_routed_to_pipeline_queue() -> None:
    routes = celery_app.conf.task_routes or {}
    assert routes.get("vak_bot.workers.tasks.process_video_post_task") == {"queue": "pipeline"}
    assert routes.get("vak_bot.workers.tasks.extend_video_task") == {"queue": "pipeline"}
    assert routes.get("vak_bot.workers.tasks.reel_this_task") == {"queue": "pipeline"}
