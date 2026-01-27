import os
from multiprocessing.connection import Client, Connection
from PySide6 import QtCore, QtGui, QtWidgets

import fb_common
import fb_config
import fb_ui.simple


class FileBroClient(QtWidgets.QMainWindow):
    def __init__(self):
        super().__init__()
        self._path: str = ''
        self._history: list[str] = []
        self._history_index: int = -1
        self._history_off: bool = False

        self.backend = BackendConnection(self)
        self.backend.message_received.connect(self._handle_message)
        self.backend.link_up()

        self.ui = fb_ui.simple.FBSimpleUI(self)
        self.ui.dir_triggered.connect(self._navigate_dir)
        self.setCentralWidget(self.ui)
        self.ui.navigate.connect(self.navigate)
        self.ui.navigate_back.connect(self.navigate_back)
        self.ui.navigate_forward.connect(self.navigate_forward)
        self.backend.error.connect(self.ui.error)

        self.navigate(get_startup_path())

        self._setup_shortcuts()

    def navigate(self, path: str = '') -> None:
        """Communicate path change to backend."""
        if not path.strip():
            return
        self._path = path
        message = {'nav': path}
        self.backend.message(message)

    def navigate_back(self):
        if abs(self._history_index) == len(self._history):
            return

        self._history_index -= 1
        self._history_off = True
        self.navigate(self._history[self._history_index])

    def navigate_forward(self):
        if self._history_index == -1:
            return

        self._history_index += 1
        self._history_off = True
        self.navigate(self._history[self._history_index])

    def _navigate_dir(self, dir_name: str):
        self.navigate(os.path.join(self._path, dir_name))

    def _handle_message(self, message):
        if 'error' in message:
            print(f'error message_received: {message}')
            self.ui.error(message['error'])
            return

        if 'nav' in message:
            self.ui.set_items(message)
            self._navigated(message['nav'])

    def _navigated(self, path):
        if isinstance(path, str) and path and not self._history_off:
            this_index = len(self._history) + self._history_index + 1
            self._history[:] = self._history[:this_index]
            self._history_index = -1
            self._history.append(path)

        self._history_off = False
        history_len = len(self._history)
        this_index = history_len + self._history_index
        self.ui.set_nav_buttons(this_index != 0, (this_index + 1) != history_len)

    def _setup_shortcuts(self):
        """TODO: Grab these from configuration."""
        shortcut = QtGui.QShortcut(self)
        shortcut.setKey(QtGui.QKeySequence(QtCore.Qt.Key.Key_Back))
        shortcut.activated.connect(self.navigate_back)
        shortcut.setContext(QtCore.Qt.ShortcutContext.WindowShortcut)

        shortcut = QtGui.QShortcut(self)
        shortcut.setKey(QtGui.QKeySequence('Alt+Left'))
        shortcut.activated.connect(self.navigate_back)

        shortcut = QtGui.QShortcut(self)
        shortcut.setKey(QtGui.QKeySequence(QtCore.Qt.Key.Key_Forward))
        shortcut.activated.connect(self.navigate_forward)
        shortcut.setContext(QtCore.Qt.ShortcutContext.WindowShortcut)

        shortcut = QtGui.QShortcut(self)
        shortcut.setKey(QtGui.QKeySequence('Alt+Right'))
        shortcut.activated.connect(self.navigate_forward)

    def mouseEvent(self, event):
        if event.button() == QtCore.Qt.MouseButton.BackButton:
            self.navigate_back()
        if event.button() == QtCore.Qt.MouseButton.ForwardButton:
            self.navigate_forward()
        return super().mouseEvent(event)

    def closeEvent(self, event):
        self.backend.link_down()
        super().closeEvent(event)

    def showEvent(self, event):
        super().showEvent(event)


class BackendConnection(QtCore.QObject):
    message_received = QtCore.Signal(dict)
    error = QtCore.Signal(str)

    def __init__(self, parent):
        super().__init__(parent)
        self._connection: None | Connection = None
        self._listener: None | BackendListener = None

    def link_up(self):
        """Connect to the filebro backend."""
        try:
            self._address = ('localhost', fb_config.general.port)
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

        raise ConnectionError(
            f'Could not connect to backend on port {fb_config.general.port} Giving up!'
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
                    # print(f'Received message! {msg}')
                    self.message_received.emit(msg)

            except (EOFError, Exception) as error:
                if self.isInterruptionRequested():
                    return

                print(f'BackendListener error: {error}')
                self.error.emit(str(error))
                break


def get_startup_path() -> str:
    """Find a path to start a FileBro ui from."""
    startup_path = ''
    if fb_config.navigation.start_up_from_last_directory:
        startup_path = fb_config.navigation._last_directory
    else:
        startup_path = fb_config.navigation.start_up_directory

    if not startup_path:
        if os.name == 'nt':
            startup_path = os.environ['USERPROFILE']
        elif os.name == 'posix':
            startup_path = os.environ['HOME']
    return startup_path


def run():
    app = QtWidgets.QApplication([])
    win = FileBroClient()
    win.show()
    app.exec()


if __name__ == '__main__':
    run()
