"""Tracked launcher runs. Cancelling stops future steps; completed actions remain."""
import asyncio
import copy
import uuid
from dataclasses import asdict

try:
    from .protocols import Protocol
except ImportError:
    from protocols import Protocol


class ProtocolJobs:
    def __init__(self):
        self._jobs = {}
        self._tasks = {}
        self._latest = ""

    def current(self):
        return copy.deepcopy(self._jobs.get(self._latest, {}))

    def get(self, job_id):
        return copy.deepcopy(self._jobs.get(job_id, {}))

    def start(self, protocol, runner):
        if any(not task.done() for task in self._tasks.values()):
            return {"success": False, "error": "Другой протокол ещё выполняется"}
        if not protocol.enabled:
            return {"success": False, "error": "Протокол отключён"}
        # Edits during a run cannot change the sequence already started.
        snapshot = Protocol.from_dict(protocol.to_dict())
        job_id = uuid.uuid4().hex
        job = dict(id=job_id, protocol_id=protocol.id, name=protocol.name, state="running", current=0,
                   total=sum(s.enabled for s in snapshot.steps) * snapshot.repeat_count, text="", iteration=1,
                   steps=[], message="Начинаю выполнение…", error="", stopped_at=None)
        self._jobs[job_id] = job
        self._latest = job_id
        self._tasks[job_id] = asyncio.create_task(self._run(job, snapshot, runner))
        self._tasks[job_id].add_done_callback(lambda task: job.update(
            state="cancelled", message="Выполнение остановлено. Завершённые действия сохранены.") if task.cancelled() else None)
        # Keep a bounded session history, including the latest terminal result.
        for old_id in list(self._jobs)[:-20]:
            self._jobs.pop(old_id, None)
            self._tasks.pop(old_id, None)
        return {"success": True, "job": copy.deepcopy(job)}

    async def _run(self, job, protocol, runner):
        def progress(event):
            job.update({key: value for key, value in event.items() if key != "step"})
            if "step" in event:
                job["steps"].append(event["step"])
        try:
            result = await runner(protocol, progress=progress)
            job.update(state="completed" if result.ok else "failed", message=result.summary(),
                       error=result.error, stopped_at=result.stopped_at,
                       steps=[asdict(step) for step in result.steps])
        except asyncio.CancelledError:
            job.update(state="cancelled", message="Выполнение остановлено. Завершённые действия сохранены.")
        except Exception as error:
            job.update(state="failed", message="Не удалось выполнить протокол", error=str(error))

    def cancel(self, job_id):
        task = self._tasks.get(job_id)
        job = self._jobs.get(job_id)
        if job is None:
            return {"success": False, "error": "Запуск не найден"}
        if task and not task.done():
            job.update(state="cancelling", message="Останавливаю дальнейшие шаги…")
            task.cancel()
        return {"success": True, "job": copy.deepcopy(job)}
