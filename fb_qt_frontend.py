import os
import time
from multiprocessing.connection import Client, Connection
from PySide6 import QtCore, QtGui, QtWidgets

import fb_common
import fb_ui.simple


class FileBroClient(QtWidgets.QMainWindow):
    def __init__(self):
        super().__init__()
        self._path: str = ''
        self.backend = BackendConnection(self)
        self.backend.message_received.connect(self._handle_message)
        self.backend.link_up()

        self.ui = fb_ui.simple.FBSimpleUI(self)
        self.ui.dir_triggered.connect(self._navigate_dir)
        self.setCentralWidget(self.ui)
        self.ui.navigate.connect(self.navigate)
        self.backend.error.connect(self.ui.error)

    def closeEvent(self, event):
        self.backend.link_down()
        super().closeEvent(event)

    def showEvent(self, event):
        super().showEvent(event)

    def navigate(self, path: str = '') -> None:
        if not path.strip():
            return
        self._path = path
        message = {'nav': path}
        self.backend.message(message)

    def _navigate_dir(self, dir_name: str):
        self.navigate(os.path.join(self._path, dir_name))

    def _handle_message(self, message):
        if 'error' in message:
            print(f'message_received: {message}')
            self.ui.error(message['error'])
            return

        if 'nav' in message:
            self.ui.set_items(message)


class BackendConnection(QtCore.QObject):
    message_received = QtCore.Signal(dict)
    error = QtCore.Signal(str)

    def __init__(self, parent):
        super().__init__(parent)
        self._connection: None | Connection = None
        self._listener: None | BackendListener = None

    def link_up(self):
        """Connect to the filebro backend."""
        for port in range(fb_common.LISTEN_ON_PORT, fb_common.LISTEN_MAX_PORT):
            try:
                self._address = ('localhost', port)
                print(f'trying to connect ... {self._address}')
                self._connection = Client(self._address, authkey=fb_common.KEY)
                self.connected = True
                print(f'Connected to backend at {self._connection}')
                self._listener = BackendListener(self, self._connection)
                self._listener.message_received.connect(self.message_received.emit)
                self._listener.error.connect(self.error.emit)
                self._listener.finished.connect(self._listener.deleteLater)
                self._listener.start()

                return True
            except Exception as error:
                print(error)
                continue

        raise ConnectionError(
            f'Could not connect to backend on ports from {fb_common.LISTEN_ON_PORT} '
            f'to {fb_common.LISTEN_MAX_PORT}! Giving up!'
        )
        return False

    def link_down(self):
        """Disconnect from the filebro backend."""
        if self._listener is not None and not self._listener.isFinished():
            print('requestInterruption')
            self._listener.requestInterruption()

        if self._connection is not None:
            self._connection.send({'link_down': True})
            self._connection.close()

        self.connected = False
        print('Disconnected from backend')

    def message(self, content):
        if self._connection is None:
            return
        self._connection.send(content)
        # response = self._connection.recv()
        # print(f'✅ {response} ack received')


class BackendListener(QtCore.QThread):
    message_received = QtCore.Signal(dict)
    error = QtCore.Signal(str)

    def __init__(self, parent: QtCore.QObject, connection: Connection):
        super().__init__(parent)
        self._connection = connection

    def run(self):
        while not self.isInterruptionRequested():
            try:
                if self._connection.poll(timeout=1):
                    msg = self._connection.recv()
                    print(f'Received message! {msg}')
                    self.message_received.emit(msg)

            except (EOFError, Exception) as error:
                if self.isInterruptionRequested():
                    return

                print(f'BackendListener error: {error}')
                self.error.emit(str(error))
                break


def run():
    app = QtWidgets.QApplication([])
    win = FileBroClient()
    win.show()
    app.exec()


if __name__ == '__main__':
    run()
