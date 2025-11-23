"""
Hybrid Process Orchestration Framework
Combines pre-spawned worker pool with on-demand process spawning for optimal performance.
"""

import multiprocessing as mp
from multiprocessing import Queue, Process, Manager
import time
import importlib.util
import sys
from typing import Callable, Dict, Any, List, Optional
from dataclasses import dataclass
from enum import Enum
import traceback
from datetime import datetime, timedelta


class TaskStatus(Enum):
    PENDING = 'pending'
    RUNNING = 'running'
    COMPLETED = 'completed'
    FAILED = 'failed'


@dataclass
class ProgressUpdate:
    worker_id: int
    task_id: str
    status: TaskStatus
    progress: float  # 0.0 to 1.0
    message: str = ''
    result: Any = None
    error: Optional[str] = None


class Worker:
    """Worker process that executes tasks and reports progress"""

    def __init__(
        self,
        worker_id: int,
        task_queue: Queue,
        progress_queue: Queue,
        ephemeral: bool = False,
    ):
        self.worker_id = worker_id
        self.task_queue = task_queue
        self.progress_queue = progress_queue
        self.ephemeral = ephemeral  # On-demand worker dies after one task

    def run(self):
        """Main worker loop"""
        while True:
            task = self.task_queue.get()

            if task is None:  # Poison pill
                break

            task_id = task['id']
            func = task['function']
            args = task.get('args', ())
            kwargs = task.get('kwargs', {})

            # Report task started
            self.report_progress(task_id, TaskStatus.RUNNING, 0.0, 'Task started')

            try:
                # Execute the task with progress callback
                def progress_callback(progress: float, message: str = ''):
                    self.report_progress(task_id, TaskStatus.RUNNING, progress, message)

                # Add progress callback to kwargs if the function accepts it
                kwargs['progress_callback'] = progress_callback

                result = func(*args, **kwargs)

                # Report completion
                self.report_progress(
                    task_id, TaskStatus.COMPLETED, 1.0, 'Task completed', result=result
                )

            except Exception as e:
                error_msg = f'{str(e)}\n{traceback.format_exc()}'
                self.report_progress(
                    task_id, TaskStatus.FAILED, 0.0, 'Task failed', error=error_msg
                )

            # If ephemeral, exit after completing one task
            if self.ephemeral:
                break

    def report_progress(
        self,
        task_id: str,
        status: TaskStatus,
        progress: float,
        message: str,
        result=None,
        error=None,
    ):
        """Send progress update to orchestrator"""
        update = ProgressUpdate(
            worker_id=self.worker_id,
            task_id=task_id,
            status=status,
            progress=progress,
            message=message,
            result=result,
            error=error,
        )
        self.progress_queue.put(update)


class HybridOrchestrator:
    """Hybrid orchestrator with core pool + on-demand workers"""

    def __init__(
        self,
        core_workers: int = 2,
        max_workers: int = None,
        idle_timeout: float = 30.0,
        queue_threshold: int = 5,
    ):
        """
        Args:
            core_workers: Number of always-running workers
            max_workers: Maximum total workers (core + on-demand)
            idle_timeout: Seconds before killing idle on-demand workers
            queue_threshold: Queue depth to trigger on-demand worker spawn
        """
        self.core_workers = core_workers
        self.max_workers = max_workers or mp.cpu_count() * 2
        self.idle_timeout = idle_timeout
        self.queue_threshold = queue_threshold

        self.task_queue = Queue()
        self.progress_queue = Queue()

        # Track all workers
        self.core_pool: List[Process] = []
        self.ondemand_pool: Dict[int, Dict] = {}  # worker_id -> {process, last_active}

        self.task_registry: Dict[str, Dict] = {}
        self.running = False
        self.next_worker_id = 0

    def start(self):
        """Start core worker processes"""
        if self.running:
            return

        self.running = True

        # Start core workers
        for i in range(self.core_workers):
            worker = Worker(self._get_worker_id(), self.task_queue, self.progress_queue)
            p = Process(target=worker.run)
            p.start()
            self.core_pool.append(p)

        print(f'Started {self.core_workers} core workers (max: {self.max_workers})')

    def _get_worker_id(self) -> int:
        """Generate unique worker ID"""
        worker_id = self.next_worker_id
        self.next_worker_id += 1
        return worker_id

    def _spawn_ondemand_worker(self):
        """Spawn an on-demand worker"""
        current_total = len(self.core_pool) + len(self.ondemand_pool)

        if current_total >= self.max_workers:
            return None

        worker_id = self._get_worker_id()
        worker = Worker(worker_id, self.task_queue, self.progress_queue, ephemeral=True)
        p = Process(target=worker.run)
        p.start()

        self.ondemand_pool[worker_id] = {'process': p, 'spawned': datetime.now()}

        print(f'🚀 Spawned on-demand worker {worker_id} (total: {current_total + 1})')
        return worker_id

    def _cleanup_finished_workers(self):
        """Remove finished on-demand workers"""
        finished = []

        for worker_id, info in self.ondemand_pool.items():
            if not info['process'].is_alive():
                info['process'].join(timeout=0.1)
                finished.append(worker_id)

        for worker_id in finished:
            del self.ondemand_pool[worker_id]
            print(f'💤 Cleaned up finished worker {worker_id}')

    def _check_and_scale(self):
        """Check if we need to spawn more workers based on queue depth"""
        queue_size = self.task_queue.qsize()

        # Spawn worker if queue is building up
        if queue_size >= self.queue_threshold:
            active_workers = len(self.core_pool) + sum(
                1 for info in self.ondemand_pool.values() if info['process'].is_alive()
            )

            if active_workers < self.max_workers:
                self._spawn_ondemand_worker()

    def submit_task(
        self, task_id: str, function: Callable, args: tuple = (), kwargs: dict = None
    ) -> str:
        """Submit a task to the worker pool"""
        if not self.running:
            raise RuntimeError('Orchestrator not started. Call start() first.')

        task = {
            'id': task_id,
            'function': function,
            'args': args,
            'kwargs': kwargs or {},
        }

        self.task_registry[task_id] = {
            'status': TaskStatus.PENDING,
            'progress': 0.0,
            'result': None,
            'error': None,
            'submitted': datetime.now(),
        }

        self.task_queue.put(task)
        print(f'📋 Submitted task: {task_id}')

        # Check if we should scale up
        self._check_and_scale()

        return task_id

    def load_custom_code(self, filepath: str) -> Callable:
        """Load a custom Python function from a file"""
        spec = importlib.util.spec_from_file_location('custom_module', filepath)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)

        # Return the main function (assumes function is named 'main' or 'execute')
        if hasattr(module, 'main'):
            return module.main
        elif hasattr(module, 'execute'):
            return module.execute
        raise ValueError("Custom code must define 'main' or 'execute' function")

    def get_progress(self, timeout: float = 0.1) -> List[ProgressUpdate]:
        """Get all pending progress updates"""
        updates = []

        while not self.progress_queue.empty():
            try:
                update = self.progress_queue.get(timeout=timeout)
                updates.append(update)

                # Update task registry
                self.task_registry[update.task_id].update({
                    'status': update.status,
                    'progress': update.progress,
                    'result': update.result,
                    'error': update.error,
                })

            except:
                break

        # Cleanup finished workers periodically
        self._cleanup_finished_workers()

        return updates

    def wait_for_completion(self, poll_interval: float = 0.5):
        """Wait for all tasks to complete and print progress"""
        while True:
            updates = self.get_progress()

            for update in updates:
                worker_type = '🔥' if update.worker_id < self.core_workers else '⚡'
                print(
                    f'{worker_type} [Worker {update.worker_id}] Task {update.task_id}: '
                    f'{update.status.value} - {update.progress * 100:.1f}% - {update.message}'
                )

                if update.error:
                    print(f'  ❌ ERROR: {update.error}')

            # Check if all tasks are done
            all_done = all(
                task['status'] in [TaskStatus.COMPLETED, TaskStatus.FAILED]
                for task in self.task_registry.values()
            )

            if all_done and self.task_queue.empty():
                break

            # Auto-scale check
            self._check_and_scale()

            time.sleep(poll_interval)

    def shutdown(self):
        """Shutdown all worker processes"""
        if not self.running:
            return

        # Send poison pills to core workers
        for _ in range(len(self.core_pool)):
            self.task_queue.put(None)

        # Wait for core workers to finish
        for worker in self.core_pool:
            worker.join()

        # Wait for on-demand workers to finish
        for info in self.ondemand_pool.values():
            if info['process'].is_alive():
                info['process'].join(timeout=2)
                if info['process'].is_alive():
                    info['process'].terminate()

        self.running = False
        print('✅ All workers shut down')

    def get_results(self) -> Dict[str, Any]:
        """Get results of all completed tasks"""
        return {
            task_id: task['result']
            for task_id, task in self.task_registry.items()
            if task['status'] == TaskStatus.COMPLETED
        }

    def get_stats(self) -> Dict[str, Any]:
        """Get orchestrator statistics"""
        return {
            'core_workers': len(self.core_pool),
            'ondemand_workers': len(self.ondemand_pool),
            'total_workers': len(self.core_pool) + len(self.ondemand_pool),
            'queue_size': self.task_queue.qsize(),
            'pending_tasks': sum(
                1
                for t in self.task_registry.values()
                if t['status'] == TaskStatus.PENDING
            ),
            'running_tasks': sum(
                1
                for t in self.task_registry.values()
                if t['status'] == TaskStatus.RUNNING
            ),
            'completed_tasks': sum(
                1
                for t in self.task_registry.values()
                if t['status'] == TaskStatus.COMPLETED
            ),
            'failed_tasks': sum(
                1
                for t in self.task_registry.values()
                if t['status'] == TaskStatus.FAILED
            ),
        }


# Example usage and custom task functions
def heavy_computation(n: int, delay: float = 0.01, progress_callback: Callable = None):
    """Example CPU-heavy task with progress reporting"""
    result = 0
    for i in range(n):
        # Simulate heavy computation
        result += sum(j**2 for j in range(1000))
        time.sleep(delay)

        # Report progress
        if progress_callback and i % max(1, n // 10) == 0:
            progress_callback(i / n, f'Processed {i}/{n} iterations')

    if progress_callback:
        progress_callback(1.0, 'Computation complete')

    return result


def quick_task(value: int, progress_callback: Callable = None):
    """Quick task for testing core workers"""
    time.sleep(0.5)
    if progress_callback:
        progress_callback(1.0, 'Quick task done')
    return value * 2


if __name__ == '__main__':
    # Create hybrid orchestrator: 2 core workers, up to 8 total
    orchestrator = HybridOrchestrator(
        core_workers=2,
        max_workers=8,
        queue_threshold=3,  # Spawn on-demand worker if 3+ tasks queued
    )
    orchestrator.start()

    print('\n🎯 Phase 1: Light load (should use core workers only)')
    orchestrator.submit_task('quick1', quick_task, args=(1,))
    orchestrator.submit_task('quick2', quick_task, args=(2,))
    time.sleep(2)

    print('\n🎯 Phase 2: Heavy load (should spawn on-demand workers)')
    # Submit many tasks at once to trigger on-demand spawning
    for i in range(10):
        orchestrator.submit_task(f'heavy{i}', heavy_computation, args=(50,))

    # Print stats
    print('\n📊 Stats after submission:')
    print(orchestrator.get_stats())

    # Wait for all tasks to complete
    orchestrator.wait_for_completion()

    # Final stats
    print('\n📊 Final stats:')
    print(orchestrator.get_stats())

    # Get results
    results = orchestrator.get_results()
    print(f'\n✨ Completed {len(results)} tasks')

    # Shutdown
    orchestrator.shutdown()
