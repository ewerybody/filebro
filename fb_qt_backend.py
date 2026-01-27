import os
import sys
import threading
import multiprocessing
from datetime import datetime
from multiprocessing.connection import Listener

from PySide6 import QtCore, QtGui, QtWidgets

import fb_drivers
import fb_common
import fb_config


class FileBroBackend(QtWidgets.QApplication):
    def __init__(self):
        super().__init__(sys.argv)
        self.navigation = Navigation(self)

        self.clients = ClientHandler(self)
        self.clients.message_received.connect(self._process_message)
        self.clients.navigate.connect(self.navigation.lookup)

        self.navigation.results.connect(self.clients.broadcast)
        self.navigation.error.connect(self.clients.broadcast)

        self.workers = WorkerHandler(self)
        self.workers.progress.connect(self._broadcast_progress)

    def _process_message(self, message):
        print(f'_process_message: {message}')

    def _broadcast_progress(self, progress):
        progress


class ClientHandler(QtCore.QObject):
    message_received = QtCore.Signal(dict)
    navigate = QtCore.Signal(dict)

    def __init__(self, parent):
        super().__init__(parent)

        self._clients: list[dict] = []
        self._client_lock = threading.Lock()

        self._client_listener = ClientListener(self)
        self._client_listener.new_client.connect(self._new_client)
        self._client_listener.finished.connect(self._client_listener.deleteLater)
        self._client_listener.start()

    def _new_client(self, client_data: dict):
        with self._client_lock:
            self._clients.append(client_data)

        print(f'self._clients: {len(self._clients)}')
        print(f'New client_data: {client_data}')
        print(f'client_data[connection].closed: {client_data["connection"].closed}')

        client_thread = ClientThread(self, client_data)
        client_thread.message_received.connect(self._handle_message)
        client_thread.finished.connect(self._cleanup_client)
        client_data['thread'] = client_thread
        client_thread.start()

    def _get_client_data(self, thread):
        client_data = next(
            (d for d in self._clients if d.get('thread') is thread), None
        )
        if client_data is None:
            print(f'Error! Could not get `client_data` from thread: {thread}')
            return None
        return client_data

    def _handle_message(self, message: dict):
        client_data = self._get_client_data(self.sender())
        if client_data is None:
            return

        if message.get('link_down', False):
            print(f'LINK_DOWN: {client_data}')
            self._cleanup_client(client_data)
            return

        print(f'client_data: {client_data}')
        print(f'message: {message}')
        if 'nav' in message:
            message['connection'] = client_data['connection']
            self.navigate.emit(message)
            return

        self.message_received.emit(message)

    def _cleanup_client(self, client_data=None):
        if client_data is None:
            client_data = self._get_client_data(self.sender())
        if client_data is None:
            return

        print(f'_cleanup_client client_thread: {client_data}')
        self._clients.remove(client_data)
        print(f'self._clients: {len(self._clients)}')

    def broadcast(self, message):
        connection = message.get('connection')
        if connection is None:
            return
        print(f'connection: {connection}')
        del message['connection']
        connection.send(message)


class ClientListener(QtCore.QThread):
    """Thread handling all incoming client connection requests."""

    new_client = QtCore.Signal(dict)

    def __init__(self, parent: QtCore.QObject):
        super().__init__(parent)
        self._listener: None | Listener = None

    def start_listening(self):
        if self._listener is not None:
            print(f"We're already listening!! {self._listener}")
            return

        from_port, to_port = (
            fb_config.general.port,
            fb_config.general.port + fb_config.general.port_range,
        )
        for port in range(from_port, to_port):
            try:
                self._listener = Listener(('localhost', port), authkey=fb_common.KEY)
                print(f'👂 Listening for UI connections on {self._listener.address}')
                fb_config.general.port = port
                return

            except OSError:
                continue

        raise ConnectionError(
            f'Could not start listening on ports from {from_port} '
            f'to {to_port}! Giving up!'
        )

    def run(self):
        self.start_listening()

        while self.isRunning() and self._listener is not None:
            try:
                print(f'listening ... {self._listener.address}')
                connection = self._listener.accept()
                print(f'🔌 UI client connected from {self._listener.last_accepted}')

                client_info = {
                    'connection': connection,
                    'active': True,
                    'connected_at': datetime.now(),
                }
                self.new_client.emit(client_info)
                print('New_client emitted')

            except Exception as error:
                if not self.isRunning():
                    continue
                print(f'Error accepting client connection: {error}')

        print('ended?')


class ClientThread(QtCore.QThread):
    """Thread listening for messages from one of the clients."""

    message_received = QtCore.Signal(dict)

    def __init__(self, parent, client_data):
        super().__init__(parent)
        self._connection = client_data['connection']

    def run(self):
        """Handle messages from a connected UI client"""
        try:
            while self.isRunning() and not self.isInterruptionRequested():
                if self._connection.poll(timeout=1.0):
                    self.message_received.emit(self._connection.recv())
                    # self._connection.send({'type': 'ack', 'task_id': '💩'})

        except (EOFError, ConnectionResetError, BrokenPipeError):
            print('🔌 UI client disconnected')
        except Exception as e:
            print(f'Error handling client: {e}')
        finally:
            print(f'Closing client connection: {self._connection}')
            self._connection.close()


class WorkerHandler(QtCore.QObject):
    progress = QtCore.Signal()

    def __init__(self, parent):
        super().__init__(parent)
        self.core_workers = fb_common.CORE_WORKERS
        self.max_workers = multiprocessing.cpu_count() * 2
        self.queue_threshold = fb_common.QUEUE_THRESHOLD


class Navigation(QtCore.QObject):
    results = QtCore.Signal(dict)
    request_auth = QtCore.Signal(dict)
    error = QtCore.Signal(dict)

    """Handles directory lookups & caching on different resources for requesting clients.

    Directory navigation always tries to get from cache first.
        If it misses, clients wait for fresh data.
        If cached data is delivered, fresh data follows asap. Clients handle updating views accordingly.

    If a client navigates somewhere it's also registered for changes in the directory.
        Local directories will use FileSystem-watchers whereas remote ones do low-frequent polling.
        There will be drivers handling these on their own.
    """

    def __init__(self, parent):
        super().__init__(parent)
        self._registry = {}

        self._drivers = fb_drivers.get_all()

    def lookup(self, message):
        path = message['nav']
        print(f'{self} looking up: {message} ...')
        for name, driver in self._drivers.items():
            if driver.matches(path):
                break
        else:
            message['nav error'] = 'Could not Resolve path!'
            self.error.emit(message)
            return

        try:
            files, dirs, details = driver.lookup(path)
            message['files'] = files
            message['dirs'] = dirs
            message['details'] = details
            self.results.emit(message)
            fb_config.navigation._last_directory = path

        except fb_drivers.NeedAuthentication:
            self.request_auth.emit(message)

        except Exception as error:
            message['nav error'] = str(error)
            self.error.emit(message)


def run():
    fb_app = FileBroBackend()

    if not QtWidgets.QSystemTrayIcon.isSystemTrayAvailable():
        QtWidgets.QMessageBox.critical(
            None,
            'No System Tray?!',
            "I couldn't detect any system tray on this system!",
        )
        sys.exit(1)

    fb_app.setQuitOnLastWindowClosed(False)
    sys.exit(fb_app.exec())
