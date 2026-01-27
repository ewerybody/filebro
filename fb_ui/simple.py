from PySide6 import QtWidgets, QtCore


class FBSimpleUI(QtWidgets.QWidget):
    navigate = QtCore.Signal(str)
    navigate_back = QtCore.Signal()
    navigate_forward = QtCore.Signal()
    file_triggered = QtCore.Signal(str)
    dir_triggered = QtCore.Signal(str)

    def __init__(self, parent):
        super().__init__(parent)
        self._setup_ui()

    def set_items(self, message):
        self.url_bar.setText(message.get('nav', ''))
        self._file_list.set_items(message.get('dirs', []), message.get('files', []))

    def _setup_ui(self):
        main_layout = QtWidgets.QVBoxLayout(self)
        bar_layout = QtWidgets.QHBoxLayout()
        self.nav_button_back = QtWidgets.QPushButton('<')
        self.nav_button_back.setMaximumWidth(40)
        self.nav_button_back.clicked.connect(self.navigate_back.emit)
        self.nav_button_forward = QtWidgets.QPushButton('>')
        self.nav_button_forward.setMaximumWidth(40)
        self.nav_button_forward.clicked.connect(self.navigate_forward.emit)
        self.url_bar = QtWidgets.QLineEdit(self)
        bar_layout.addWidget(self.nav_button_back)
        bar_layout.addWidget(self.nav_button_forward)
        bar_layout.addWidget(self.url_bar)

        # bar_layout.setStretch(0, 0)
        # bar_layout.setStretch(1, 0)
        # bar_layout.setStretch(2, 3)
        main_layout.addLayout(bar_layout)

        self._file_list = FileListView(self)
        self._file_list.activated.connect(self._activated)
        self._file_list.navigate_back.connect(self.navigate_back.emit)
        self._file_list.navigate_forward.connect(self.navigate_forward.emit)
        main_layout.addWidget(self._file_list)

        self.url_bar.returnPressed.connect(self._navigate)

    def set_nav_buttons(self, back: bool, forward: bool) -> None:
        self.nav_button_back.setEnabled(back)
        self.nav_button_forward.setEnabled(forward)

    def _navigate(self):
        url = self.url_bar.text().strip()
        if not url:
            return
        self.navigate.emit(url)

    def error(self, error_message):
        QtWidgets.QMessageBox.critical(self, 'ERROR', error_message)

    @QtCore.Slot(QtCore.QModelIndex)
    def _activated(self, index):
        name, is_dir = self._file_list.get_item(index)
        if is_dir:
            self.dir_triggered.emit(name)
        else:
            self.file_triggered.emit(name)

    def mousePressEvent(self, event):
        if event.button() == QtCore.Qt.MouseButton.BackButton:
            self.navigate_back.emit()
        if event.button() == QtCore.Qt.MouseButton.ForwardButton:
            self.navigate_forward.emit()
        return super().mousePressEvent(event)


class FileListView(QtWidgets.QListView):
    navigate_back = QtCore.Signal()
    navigate_forward = QtCore.Signal()

    def __init__(self, parent):
        super().__init__(parent)
        self.setModel(SimpleDirItemModel(self))

    def set_items(self, dirs: list[str], files: list[str]):
        model = self.model()
        if isinstance(model, SimpleDirItemModel):
            model.set_items(dirs, files)

    def get_item(self, index: QtCore.QModelIndex) -> tuple[str, bool]:
        model = self.model()
        if isinstance(model, SimpleDirItemModel):
            return model.get_item(index)
        return '', False

    def mousePressEvent(self, event):
        if event.button() == QtCore.Qt.MouseButton.BackButton:
            self.navigate_back.emit()
        if event.button() == QtCore.Qt.MouseButton.ForwardButton:
            self.navigate_forward.emit()
        return super().mousePressEvent(event)


class SimpleDirItemModel(QtCore.QAbstractListModel):
    def __init__(self, parent=None):
        super().__init__(parent)

        self._item_count = 0
        self._dir_list: list[str] = []
        self._file_list: list[str] = []
        self._icon_provider = QtWidgets.QFileIconProvider()

    def rowCount(self, parent=QtCore.QModelIndex()):
        return self._item_count

    def data(self, index, role=QtCore.Qt.ItemDataRole.DisplayRole):
        if not index.isValid():
            return None

        row = index.row()
        if row >= self._item_count or row < 0:
            return None

        item_name, is_dir = self.get_item(index)
        if not item_name:
            return None

        if role == QtCore.Qt.ItemDataRole.DisplayRole:
            return item_name

        if role == QtCore.Qt.ItemDataRole.DecorationRole:
            if is_dir:
                return self._icon_provider.icon(
                    QtWidgets.QFileIconProvider.IconType.Folder
                )
            return self._icon_provider.icon(QtWidgets.QFileIconProvider.IconType.File)

        return None

    def get_item(self, index: QtCore.QModelIndex) -> tuple[str, bool]:
        row = index.row()
        len_dirs = len(self._dir_list)
        if row < len_dirs:
            return self._dir_list[row], True
        return self._file_list[row - len_dirs], False

    def set_items(self, dirs: list[str], files: list[str]) -> None:
        self.beginResetModel()
        self._dir_list[:] = dirs
        self._file_list[:] = files
        self._item_count = len(self._dir_list) + len(self._file_list)
        self.endResetModel()

    # def canFetchMore(self, index):
    #     return self._file_count < len(self._file_list)

    # def fetchMore(self, index):
    #     start = self._file_count
    #     total = len(self._file_list)
    #     remainder = total - start
    #     items_to_fetch = min(BATCH_SIZE, remainder)

    #     self.beginInsertRows(QModelIndex(), start, start + items_to_fetch)

    #     self._file_count += items_to_fetch

    #     self.endInsertRows()

    #     self.number_populated.emit(self._path, start, items_to_fetch, total)
