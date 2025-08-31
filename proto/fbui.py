from PySide6 import QtCore, QtWidgets
from multiprocessing.connection import Listener, Client

class BackendCommunicator(QtCore.QThread):
    progress_update = QtCore.Signal(dict)
    error_occurred = QtCore.Signal(dict)
    operation_complete = QtCore.Signal(dict)

    def __init__(self):
        super().__init__()
        self.command_conn = None
        self.status_listener = None
        self.running = True

    def run(self):
        # Set up connections
        self.command_conn = Client(('localhost', 6000))
        self.status_listener = Listener(('localhost', 6001))

        # Listen for status updates
        status_conn = self.status_listener.accept()

        while self.running:
            try:
                status = status_conn.recv()
                self.handle_status(status)
            except EOFError:
                break

    def handle_status(self, status):
        status_type = status.get('type')

        if status_type == 'progress':
            self.progress_update.emit(status)
        elif status_type == 'error':
            self.error_occurred.emit(status)
        elif status_type == 'complete':
            self.operation_complete.emit(status)

    def send_command(self, command):
        if self.command_conn:
            self.command_conn.send(command)

class FileBrowserGUI(QtWidgets.QMainWindow):
    def __init__(self):
        super().__init__()
        self.communicator = BackendCommunicator()
        self.communicator.progress_update.connect(self.update_progress)
        self.communicator.error_occurred.connect(self.show_error)
        self.communicator.operation_complete.connect(self.operation_finished)
        self.communicator.start()

    def copy_files(self, files, destination):
        command = {
            'type': 'copy_files',
            'files': files,
            'destination': destination
        }
        self.communicator.send_command(command)

    @QtCore.Slot(dict)
    def update_progress(self, status):
        # Update progress bar
        progress = (status['current'] / status['total']) * 100
        self.progress_bar.setValue(progress)
        self.status_label.setText(f"Processing: {status['file']}")

    @QtCore.Slot(dict)
    def show_error(self, error):
        # Show error in GUI
        self.error_list.addItem(f"Error with {error['file']}: {error['message']}")

    @QtCore.Slot(dict)
    def operation_finished(self, result):
        self.status_label.setText(f"Operation '{result['operation']}' completed!")


def show():
    app = QtWidgets.QApplication.instance()
    if app is None:
        app = QtWidgets.QApplication([])
    win = FileBrowserGUI()
    win.show()
    app.exec()
