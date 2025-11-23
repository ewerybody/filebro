"""
Process Orchestration Framework with Listener/Client IPC
Backend orchestrator that UI processes can connect/disconnect/reconnect to freely.
"""

import multiprocessing as mp
from multiprocessing import Queue, Process
from multiprocessing.connection import Listener, Client
import time
import importlib.util
import threading
from typing import Callable, Dict, Any, List, Optional
from dataclasses import dataclass, asdict
from enum import Enum
import traceback
from datetime import datetime
import json


class TaskStatus(Enum):
    PENDING = 'pending'
    RUNNING = 'running'
    COMPLETED = 'completed'
    FAILED = 'failed'


@dataclass
class ProgressUpdate:
    worker_id: int
    task_id: str
    status: str  # Use string for easier serialization
    progress: float
    message: str = ''
    result: Any = None
    error: str = None
    timestamp: str = None

    def __post_init__(self):
        if self.timestamp is None:
            self.timestamp = datetime.now().isoformat()

    def to_dict(self):
        return asdict(self)


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
        self.ephemeral = ephemeral

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
            status=status.value,
            progress=progress,
            message=message,
            result=result,
            error=error,
        )
        self.progress_queue.put(update)


class OrchestratorBackend:
    """Backend orchestrator that accepts UI connections via Listener"""

    def __init__(
        self,
        address=('localhost', 6000),
        authkey=b'orchestrator_secret',
        core_workers: int = 2,
        max_workers: int = None,
        queue_threshold: int = 5,
    ):
        self.address = address
        self.authkey = authkey
        self.core_workers = core_workers
        self.max_workers = max_workers or mp.cpu_count() * 2
        self.queue_threshold = queue_threshold

        self.task_queue = Queue()
        self.progress_queue = Queue()

        self.core_pool: List[Process] = []
        self.ondemand_pool: Dict[int, Dict] = {}
        self.task_registry: Dict[str, Dict] = {}

        self.next_worker_id = 0
        self.running = False
        self.listener = None

        # Track connected UI clients
        self.clients: List[Dict] = []  # {conn, thread, active}
        self.client_lock = threading.Lock()

    def start(self):
        """Start the backend orchestrator"""
        if self.running:
            return

        self.running = True

        # Start core workers
        for i in range(self.core_workers):
            worker = Worker(self._get_worker_id(), self.task_queue, self.progress_queue)
            p = Process(target=worker.run)
            p.start()
            self.core_pool.append(p)

        print(f'🚀 Backend started with {self.core_workers} core workers')

        # Start listener for UI connections
        self.listener = Listener(self.address, authkey=self.authkey)
        print(f'👂 Listening for UI connections on {self.address}')

        # Start progress broadcaster thread
        broadcast_thread = threading.Thread(
            target=self._broadcast_progress, daemon=True
        )
        broadcast_thread.start()

        # Start connection acceptor thread
        acceptor_thread = threading.Thread(target=self._accept_connections, daemon=True)
        acceptor_thread.start()

    def _get_worker_id(self) -> int:
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

        print(f'⚡ Spawned on-demand worker {worker_id}')
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

    def _check_and_scale(self):
        """Check if we need to spawn more workers"""
        queue_size = self.task_queue.qsize()

        if queue_size >= self.queue_threshold:
            active_workers = len(self.core_pool) + sum(
                1 for info in self.ondemand_pool.values() if info['process'].is_alive()
            )

            if active_workers < self.max_workers:
                self._spawn_ondemand_worker()

    def _accept_connections(self):
        """Accept incoming UI connections"""
        while self.running:
            try:
                conn = self.listener.accept()
                print(f'🔌 UI client connected from {self.listener.last_accepted}')

                # Spawn thread to handle this client
                client_info = {
                    'conn': conn,
                    'active': True,
                    'connected_at': datetime.now(),
                }

                with self.client_lock:
                    self.clients.append(client_info)

                client_thread = threading.Thread(
                    target=self._handle_client, args=(client_info,), daemon=True
                )
                client_thread.start()
                client_info['thread'] = client_thread

            except Exception as e:
                if self.running:
                    print(f'Error accepting connection: {e}')

    def _handle_client(self, client_info: Dict):
        """Handle messages from a connected UI client"""
        conn = client_info['conn']

        try:
            while client_info['active'] and self.running:
                if conn.poll(timeout=1.0):
                    msg = conn.recv()
                    self._process_client_message(msg, conn)
        except EOFError:
            print('🔌 UI client disconnected')
        except Exception as e:
            print(f'Error handling client: {e}')
        finally:
            client_info['active'] = False
            with self.client_lock:
                if client_info in self.clients:
                    self.clients.remove(client_info)
            try:
                conn.close()
            except:
                pass

    def _process_client_message(self, msg: Dict, conn):
        """Process a message from UI client"""
        msg_type = msg.get('type')

        if msg_type == 'submit_task':
            task_id = msg['task_id']
            function = msg['function']
            args = msg.get('args', ())
            kwargs = msg.get('kwargs', {})

            self._submit_task(task_id, function, args, kwargs)
            conn.send({'type': 'ack', 'task_id': task_id})

        elif msg_type == 'get_status':
            task_id = msg.get('task_id')
            if task_id:
                status = self.task_registry.get(task_id, {})
                conn.send({'type': 'status', 'task_id': task_id, 'data': status})
            else:
                conn.send({'type': 'status', 'data': self.task_registry})

        elif msg_type == 'get_stats':
            stats = self._get_stats()
            conn.send({'type': 'stats', 'data': stats})

        elif msg_type == 'shutdown':
            print('🛑 Shutdown requested by UI')
            self.shutdown()

    def _submit_task(
        self, task_id: str, function: Callable, args: tuple = (), kwargs: dict = None
    ):
        """Submit a task to the worker pool"""
        task = {
            'id': task_id,
            'function': function,
            'args': args,
            'kwargs': kwargs or {},
        }

        self.task_registry[task_id] = {
            'status': TaskStatus.PENDING.value,
            'progress': 0.0,
            'result': None,
            'error': None,
            'submitted': datetime.now().isoformat(),
        }

        self.task_queue.put(task)
        print(f'📋 Task submitted: {task_id}')

        self._check_and_scale()

    def _broadcast_progress(self):
        """Continuously broadcast progress updates to all connected UIs"""
        while self.running:
            try:
                # Get progress updates
                updates = []
                while not self.progress_queue.empty():
                    try:
                        update = self.progress_queue.get_nowait()
                        updates.append(update)

                        # Update task registry
                        self.task_registry[update.task_id].update(
                            {
                                'status': update.status,
                                'progress': update.progress,
                                'result': update.result,
                                'error': update.error,
                                'updated': update.timestamp,
                            }
                        )
                    except:
                        break

                # Broadcast to all connected clients
                if updates:
                    with self.client_lock:
                        for client_info in self.clients[:]:  # Copy list
                            if client_info['active']:
                                try:
                                    for update in updates:
                                        client_info['conn'].send(
                                            {
                                                'type': 'progress',
                                                'data': update.to_dict(),
                                            }
                                        )
                                except Exception as e:
                                    print(f'Error sending to client: {e}')
                                    client_info['active'] = False

                # Cleanup
                self._cleanup_finished_workers()
                self._check_and_scale()

                time.sleep(0.1)

            except Exception as e:
                print(f'Error in broadcast loop: {e}')

    def _get_stats(self) -> Dict[str, Any]:
        """Get orchestrator statistics"""
        return {
            'core_workers': len(self.core_pool),
            'ondemand_workers': len(self.ondemand_pool),
            'total_workers': len(self.core_pool) + len(self.ondemand_pool),
            'queue_size': self.task_queue.qsize(),
            'connected_clients': len([c for c in self.clients if c['active']]),
            'total_tasks': len(self.task_registry),
            'pending_tasks': sum(
                1
                for t in self.task_registry.values()
                if t['status'] == TaskStatus.PENDING.value
            ),
            'running_tasks': sum(
                1
                for t in self.task_registry.values()
                if t['status'] == TaskStatus.RUNNING.value
            ),
            'completed_tasks': sum(
                1
                for t in self.task_registry.values()
                if t['status'] == TaskStatus.COMPLETED.value
            ),
            'failed_tasks': sum(
                1
                for t in self.task_registry.values()
                if t['status'] == TaskStatus.FAILED.value
            ),
        }

    def shutdown(self):
        """Shutdown the backend"""
        if not self.running:
            return

        self.running = False

        # Close all client connections
        with self.client_lock:
            for client_info in self.clients:
                try:
                    client_info['conn'].send({'type': 'shutdown'})
                    client_info['conn'].close()
                except:
                    pass

        # Shutdown workers
        for _ in range(len(self.core_pool)):
            self.task_queue.put(None)

        for worker in self.core_pool:
            worker.join(timeout=2)

        for info in self.ondemand_pool.values():
            if info['process'].is_alive():
                info['process'].terminate()

        if self.listener:
            self.listener.close()

        print('✅ Backend shut down')

    def run_forever(self):
        """Run the backend indefinitely"""
        try:
            while self.running:
                time.sleep(1)
        except KeyboardInterrupt:
            print('\n⚠️  Keyboard interrupt received')
            self.shutdown()


class OrchestratorUI:
    """UI client that connects to the backend orchestrator"""

    def __init__(self, address=('localhost', 6000), authkey=b'orchestrator_secret'):
        self.address = address
        self.authkey = authkey
        self.conn = None
        self.connected = False
        self.progress_callback = None

    def connect(self):
        """Connect to the backend"""
        try:
            self.conn = Client(self.address, authkey=self.authkey)
            self.connected = True
            print(f'✅ Connected to backend at {self.address}')
            return True
        except Exception as e:
            print(f'❌ Failed to connect: {e}')
            self.connected = False
            return False

    def disconnect(self):
        """Disconnect from backend"""
        if self.conn is not None:
            self.conn.close()

        self.connected = False
        print('🔌 Disconnected from backend')

    def submit_task(self, task_id: str, function: Callable, *args, **kwargs) -> bool:
        """Submit a task to the backend"""
        if not self.connected:
            print('❌ Not connected to backend')
            return False

        try:
            self.conn.send({
                'type': 'submit_task',
                'task_id': task_id,
                'function': function,
                'args': args,
                'kwargs': kwargs or {},
            })

            # Wait for acknowledgment
            response = self.conn.recv()
            if response.get('type') == 'ack':
                print(f'✅ Task {task_id} submitted')
                return True

        except Exception as e:
            print(f'❌ Error submitting task: {e}')
            self.connected = False

        return False

    def get_status(self, task_id: str = None) -> Dict:
        """Get status of a specific task or all tasks"""
        if not self.connected:
            return {}

        try:
            self.conn.send({'type': 'get_status', 'task_id': task_id})

            response = self.conn.recv()
            return response.get('data', {})

        except Exception as e:
            print(f'❌ Error getting status: {e}')
            self.connected = False
            return {}

    def get_stats(self) -> Dict:
        """Get backend statistics"""
        if not self.connected:
            return {}

        try:
            self.conn.send({'type': 'get_stats'})
            response = self.conn.recv()
            return response.get('data', {})

        except Exception as e:
            print(f'❌ Error getting stats: {e}')
            self.connected = False
            return {}

    def listen_for_progress(
        self, callback: Callable | None = None, timeout: float = 1.0
    ):
        """Listen for progress updates (blocking)"""
        if not self.connected:
            return

        callback = callback or self._default_progress_handler

        while self.connected:
            try:
                if self.conn.poll(timeout=timeout):
                    msg = self.conn.recv()

                    if msg.get('type') == 'progress':
                        callback(msg['data'])
                    elif msg.get('type') == 'shutdown':
                        print('🛑 Backend is shutting down')
                        self.connected = False
                        break

            except EOFError:
                print('🔌 Connection closed by backend')
                self.connected = False
                break
            except Exception as e:
                print(f'❌ Error receiving progress: {e}')
                self.connected = False
                break

    def _default_progress_handler(self, progress_data: Dict):
        """Default progress handler"""
        worker_id = progress_data['worker_id']
        task_id = progress_data['task_id']
        status = progress_data['status']
        progress = progress_data['progress']
        message = progress_data['message']

        print(
            f'[Worker {worker_id}] {task_id}: {status} - {progress * 100:.1f}% - {message}'
        )

    def request_shutdown(self):
        """Request backend shutdown"""
        if not self.connected:
            return

        try:
            self.conn.send({'type': 'shutdown'})
        except:
            pass


# Example task functions
def heavy_computation(n: int, delay: float = 0.01, progress_callback: Callable = None):
    """Example CPU-heavy task"""
    result = 0
    for i in range(n):
        result += sum(j**2 for j in range(1000))
        time.sleep(delay)

        if progress_callback and i % max(1, n // 10) == 0:
            progress_callback(i / n, f'Processed {i}/{n} iterations')

    if progress_callback:
        progress_callback(1.0, 'Computation complete')

    return result


# Example usage
if __name__ == '__main__':
    import sys

    if len(sys.argv) > 1 and sys.argv[1] == 'backend':
        # Run as backend
        print('=' * 50)
        print('BACKEND MODE')
        print('=' * 50)

        backend = OrchestratorBackend(core_workers=2, max_workers=6, queue_threshold=3)
        backend.start()
        backend.run_forever()

    else:
        # Run as UI client
        print('=' * 50)
        print('UI CLIENT MODE')
        print('=' * 50)
        print('Start backend first: python script.py backend')
        print()

        ui = OrchestratorUI()

        if ui.connect():
            # Submit some tasks
            for i in range(5):
                ui.submit_task(f'task_{i}', heavy_computation, args=(50,))

            # Get stats
            print('\n📊 Backend stats:')
            print(ui.get_stats())

            # Listen for progress
            print('\n👂 Listening for progress updates...')
            print('(Press Ctrl+C to stop)\n')

            try:
                ui.listen_for_progress()
            except KeyboardInterrupt:
                print('\n⚠️  Stopping UI...')

            ui.disconnect()
