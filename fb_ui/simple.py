from PySide6 import QtWidgets, QtCore


class FBSimpleUI(QtWidgets.QWidget):
    navigate = QtCore.Signal(str)
    file_triggered = QtCore.Signal(str)
    dir_triggered = QtCore.Signal(str)

    def __init__(self, parent):
        super().__init__(parent)
        self._setup_ui()

    def set_items(self, message):
        self.url_bar.setText(message.get('nav', ''))
        self._model.set_items(message.get('dirs', []), message.get('files', []))

    def _setup_ui(self):
        lyt = QtWidgets.QVBoxLayout(self)
        self.url_bar = QtWidgets.QLineEdit(self)
        lyt.addWidget(self.url_bar)

        self._model = SimpleDirItemModel(self)
        self._file_list = QtWidgets.QListView(self)
        self._file_list.setModel(self._model)
        self._file_list.activated.connect(self._activated)
        lyt.addWidget(self._file_list)

        self.url_bar.returnPressed.connect(self._navigate)

    def _navigate(self):
        url = self.url_bar.text().strip()
        if not url:
            return
        self.navigate.emit(url)

    def error(self, error_message):
        QtWidgets.QMessageBox.critical(self, 'ERROR', error_message)

    @QtCore.Slot(QtCore.QModelIndex)
    def _activated(self, index):
        name, is_dir = self._model.get_item(index)
        if is_dir:
            self.dir_triggered.emit(name)
        else:
            self.file_triggered.emit(name)


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

        if role == QtCore.Qt.ItemDataRole.DisplayRole:
            return item_name

        if role == QtCore.Qt.ItemDataRole.DecorationRole:
            if is_dir:
                return self._icon_provider.icon(QtWidgets.QFileIconProvider.IconType.Folder)
            return self._icon_provider.icon(QtWidgets.QFileIconProvider.IconType.File)

        return None

    def get_item(self, index):
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