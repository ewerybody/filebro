# qt_client.py - Qt UI that talks to the server
import sys
import requests
from PySide6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout,
                              QHBoxLayout, QPushButton, QListWidget, QLabel,
                              QLineEdit, QTextEdit, QSplitter, QListWidgetItem)
from PySide6.QtCore import QTimer, Qt

SERVER_URL = 'http://127.0.0.1:5000'

class FileBrowser(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle('File Browser')
        self.setGeometry(100, 100, 1000, 600)

        # Main widget
        main_widget = QWidget()
        self.setCentralWidget(main_widget)
        layout = QHBoxLayout(main_widget)

        # Create splitter for resizable panels
        splitter = QSplitter(Qt.Orientation.Horizontal)
        layout.addWidget(splitter)

        # Left panel - File browser
        left_panel = QWidget()
        left_layout = QVBoxLayout(left_panel)

        # Path input
        path_layout = QHBoxLayout()
        self.path_input = QLineEdit('.')
        path_layout.addWidget(QLabel('Path:'))
        path_layout.addWidget(self.path_input)
        browse_btn = QPushButton('Browse')
        browse_btn.clicked.connect(self.browse_path)
        path_layout.addWidget(browse_btn)
        left_layout.addLayout(path_layout)

        # File list
        self.file_list = QListWidget()
        self.file_list.itemDoubleClicked.connect(self.on_file_double_click)
        left_layout.addWidget(self.file_list)

        # Action buttons
        btn_layout = QHBoxLayout()
        resize_btn = QPushButton('Resize Image')
        resize_btn.clicked.connect(self.resize_image)
        encode_btn = QPushButton('Encode Video')
        encode_btn.clicked.connect(self.encode_video)
        ftp_btn = QPushButton('Upload via FTP')
        ftp_btn.clicked.connect(self.upload_ftp)

        btn_layout.addWidget(resize_btn)
        btn_layout.addWidget(encode_btn)
        btn_layout.addWidget(ftp_btn)
        left_layout.addLayout(btn_layout)

        splitter.addWidget(left_panel)

        # Right panel - Job status
        right_panel = QWidget()
        right_layout = QVBoxLayout(right_panel)

        right_layout.addWidget(QLabel('Active Jobs:'))
        self.job_list = QTextEdit()
        self.job_list.setReadOnly(True)
        right_layout.addWidget(self.job_list)

        refresh_btn = QPushButton('Refresh Jobs')
        refresh_btn.clicked.connect(self.refresh_jobs)
        right_layout.addWidget(refresh_btn)

        splitter.addWidget(right_panel)
        splitter.setStretchFactor(0, 2)
        splitter.setStretchFactor(1, 1)

        # Auto-refresh timer
        self.timer = QTimer()
        self.timer.timeout.connect(self.refresh_jobs)
        self.timer.start(2000)  # Refresh every 2 seconds

        # Load initial directory
        self.browse_path()

    def browse_path(self):
        path = self.path_input.text()
        try:
            response = requests.get(f'{SERVER_URL}/files/browse', params={'path': path})
            data = response.json()

            self.file_list.clear()
            for item in data['items']:
                icon = '📁' if item['is_dir'] else '📄'
                size = f" ({item['size']} bytes)" if item['size'] else ''
                list_item = QListWidgetItem(f"{icon} {item['name']}{size}")
                list_item.setData(Qt.ItemDataRole.UserRole, item)
                self.file_list.addItem(list_item)
        except Exception as e:
            self.job_list.append(f"Error browsing: {e}")

    def on_file_double_click(self, item):
        file_data = item.data(Qt.ItemDataRole.UserRole)
        if file_data['is_dir']:
            self.path_input.setText(file_data['path'])
            self.browse_path()

    def get_selected_file(self):
        current = self.file_list.currentItem()
        if current:
            return current.data(Qt.ItemDataRole.UserRole)
        return None

    def resize_image(self):
        file_data = self.get_selected_file()
        if not file_data or file_data['is_dir']:
            self.job_list.append("Please select an image file")
            return

        try:
            response = requests.post(f'{SERVER_URL}/jobs/resize', json={
                'input_path': file_data['path'],
                'output_path': file_data['path'].replace('.', '_resized.'),
                'width': 800,
                'height': 600
            })
            job = response.json()
            self.job_list.append(f"✓ Resize job started: {job['job_id']}")
        except Exception as e:
            self.job_list.append(f"✗ Error: {e}")

    def encode_video(self):
        file_data = self.get_selected_file()
        if not file_data or file_data['is_dir']:
            self.job_list.append("Please select a video file")
            return

        try:
            response = requests.post(f'{SERVER_URL}/jobs/encode', json={
                'input_path': file_data['path'],
                'output_path': file_data['path'].replace('.', '_encoded.'),
                'codec': 'libx264'
            })
            job = response.json()
            self.job_list.append(f"✓ Encode job started: {job['job_id']}")
        except Exception as e:
            self.job_list.append(f"✗ Error: {e}")

    def upload_ftp(self):
        file_data = self.get_selected_file()
        if not file_data or file_data['is_dir']:
            self.job_list.append("Please select a file")
            return

        try:
            response = requests.post(f'{SERVER_URL}/jobs/ftp', json={
                'local_path': file_data['path'],
                'remote_host': 'ftp.example.com',
                'remote_path': f'/upload/{file_data["name"]}',
                'username': 'user',
                'password': 'pass'
            })
            job = response.json()
            self.job_list.append(f"✓ FTP job started: {job['job_id']}")
        except Exception as e:
            self.job_list.append(f"✗ Error: {e}")

    def refresh_jobs(self):
        try:
            response = requests.get(f'{SERVER_URL}/jobs')
            jobs = response.json()

            status_text = ""
            for job in jobs[-10:]:  # Show last 10 jobs
                status_icon = {'pending': '⏳', 'completed': '✅', 'failed': '❌'}.get(job['status'], '❓')
                status_text += f"{status_icon} {job['type']} - {job['status']}\n"

            if status_text:
                self.job_list.setPlainText(status_text)
        except Exception as e:
            pass  # Silently fail on refresh

if __name__ == '__main__':
    app = QApplication(sys.argv)
    window = FileBrowser()
    window.show()
    sys.exit(app.exec())