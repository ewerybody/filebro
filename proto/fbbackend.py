import time
import hashlib
import threading
from multiprocessing.connection import Listener, Client

from fbcommon import NAME, KEY

class FileBackend:
    def __init__(self, command_port=6000, status_port=6001):
        self.command_listener = Listener(('localhost', command_port), authkey=KEY)
        self.status_conn = None
        self.running = True

    def start(self):
        # Connect to GUI's status listener
        self.status_conn = Client(('localhost', 6001), authkey=KEY)

        # Listen for commands
        command_conn = self.command_listener.accept()

        while self.running:
            try:
                command = command_conn.recv()
                self.handle_command(command)
            except EOFError:
                break

    def handle_command(self, command):
        cmd_type = command.get('type')

        if cmd_type == 'copy_files':
            self.copy_files_with_progress(command['files'], command['destination'])
        elif cmd_type == 'delete_files':
            self.delete_files_with_progress(command['files'])

    def copy_files_with_progress(self, files, destination):
        total = len(files)
        for i, file_path in enumerate(files):
            try:
                # Send progress update
                self.status_conn.send({
                    'type': 'progress',
                    'current': i + 1,
                    'total': total,
                    'file': file_path
                })

                # Simulate file operation
                time.sleep(0.1)  # Replace with actual copy logic

            except Exception as e:
                # Send error
                self.status_conn.send({
                    'type': 'error',
                    'message': str(e),
                    'file': file_path
                })

        # Send completion
        self.status_conn.send({'type': 'complete', 'operation': 'copy'})
