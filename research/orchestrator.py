"""
Process Orchestration Framework
A framework for managing subprocesses with multiprocessing workers that execute custom code
and report progress back to the main orchestrator.
"""

import multiprocessing as mp
from multiprocessing import Queue, Process
import time
import importlib.util
from typing import Callable, Dict, Any, List, Optional
from dataclasses import dataclass
from enum import Enum
import traceback


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
    error: str | None = None


class Worker:
    """Worker process that executes tasks and reports progress"""

    def __init__(self, worker_id: int, task_queue: Queue, progress_queue: Queue):
        self.worker_id = worker_id
        self.task_queue = task_queue
        self.progress_queue = progress_queue

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


class ProcessOrchestrator:
    """Main orchestrator that manages workers and distributes tasks"""

    def __init__(self, num_workers: Optional[int] = None):
        self.num_workers = num_workers or mp.cpu_count()
        self.task_queue = Queue()
        self.progress_queue = Queue()
        self.workers: List[Process] = []
        self.task_registry: Dict[str, Dict] = {}
        self.running = False

    def start(self):
        """Start all worker processes"""
        if self.running:
            return

        self.running = True

        for i in range(self.num_workers):
            worker = Worker(i, self.task_queue, self.progress_queue)
            p = Process(target=worker.run)
            p.start()
            self.workers.append(p)

        print(f'Started {self.num_workers} worker processes')

    def submit_task(
        self,
        task_id: str,
        function: Callable,
        args: tuple = (),
        kwargs: Optional[dict] = None,
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
        }

        self.task_queue.put(task)
        print(f'Submitted task: {task_id}')
        return task_id

    def load_custom_code(self, filepath: str) -> Callable:
        """Load a custom Python function from a file"""
        spec = importlib.util.spec_from_file_location('custom_module', filepath)
        if spec is None or spec.loader is None:
            raise FileNotFoundError(f'Could not find {filepath} among custom_modules!')

        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)

        # Return the main function (assumes function is named 'main' or 'execute')
        if hasattr(module, 'main'):
            return getattr(module, 'main')
        elif hasattr(module, 'execute'):
            return getattr(module, 'execute')

        raise ValueError("Custom code must define 'main' or 'execute' function")

    def get_progress(self, timeout: float = 0.1) -> List[ProgressUpdate]:
        """Get all pending progress updates"""
        updates = []

        while not self.progress_queue.empty():
            try:
                update = self.progress_queue.get(timeout=timeout)
                updates.append(update)

                # Update task registry
                self.task_registry[update.task_id].update(
                    {
                        'status': update.status,
                        'progress': update.progress,
                        'result': update.result,
                        'error': update.error,
                    }
                )

            except:
                break

        return updates

    def wait_for_completion(self, poll_interval: float = 0.5):
        """Wait for all tasks to complete and print progress"""
        while True:
            updates = self.get_progress()

            for update in updates:
                print(
                    f'[Worker {update.worker_id}] Task {update.task_id}: '
                    f'{update.status.value} - {update.progress * 100:.1f}% - {update.message}'
                )

                if update.error:
                    print(f'  ERROR: {update.error}')

            # Check if all tasks are done
            all_done = all(
                task['status'] in [TaskStatus.COMPLETED, TaskStatus.FAILED]
                for task in self.task_registry.values()
            )

            if all_done and self.task_queue.empty():
                break

            time.sleep(poll_interval)

    def shutdown(self):
        """Shutdown all worker processes"""
        if not self.running:
            return

        # Send poison pills
        for _ in range(self.num_workers):
            self.task_queue.put(None)

        # Wait for workers to finish
        for worker in self.workers:
            worker.join()

        self.running = False
        print('All workers shut down')

    def get_results(self) -> Dict[str, Any]:
        """Get results of all completed tasks"""
        return {
            task_id: task['result']
            for task_id, task in self.task_registry.items()
            if task['status'] == TaskStatus.COMPLETED
        }


# Example usage and custom task functions
def heavy_computation(n: int, progress_callback: Optional[Callable] = None):
    """Example CPU-heavy task with progress reporting"""
    result = 0
    for i in range(n):
        # Simulate heavy computation
        result += sum(j**2 for j in range(1000))

        # Report progress
        if progress_callback and i % (n // 10) == 0:
            progress_callback(i / n, f'Processed {i}/{n} iterations')

    if progress_callback:
        progress_callback(1.0, 'Computation complete')

    return result


def data_processing(data: List[int], progress_callback: Optional[Callable] = None):
    """Example data processing task"""
    results = []
    total = len(data)

    for i, item in enumerate(data):
        # Simulate processing
        time.sleep(0.1)
        results.append(item * 2)

        if progress_callback:
            progress_callback((i + 1) / total, f'Processed item {i + 1}/{total}')

    return results


if __name__ == '__main__':
    # Create orchestrator with 4 workers
    orchestrator = ProcessOrchestrator(num_workers=4)
    orchestrator.start()

    # Submit various tasks
    orchestrator.submit_task('task1', heavy_computation, args=(100,))
    orchestrator.submit_task('task2', heavy_computation, args=(150,))
    orchestrator.submit_task('task3', data_processing, args=([1, 2, 3, 4, 5],))
    orchestrator.submit_task('task4', heavy_computation, args=(200,))

    # Wait for all tasks to complete
    orchestrator.wait_for_completion()

    # Get results
    results = orchestrator.get_results()
    print('\nFinal Results:')
    for task_id, result in results.items():
        print(f'{task_id}: {result}')

    # Shutdown
    orchestrator.shutdown()
