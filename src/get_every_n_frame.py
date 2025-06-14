import sys
import os
import shutil
from PyQt5.QtWidgets import (
    QApplication, QWidget, QLabel, QLineEdit, QPushButton,
    QVBoxLayout, QHBoxLayout, QFileDialog, QMessageBox, QProgressBar
)
from PyQt5.QtCore import Qt, QThread, pyqtSignal


class CopyWorker(QThread):
    progress_changed = pyqtSignal(int)
    copy_finished = pyqtSignal()

    def __init__(self, current_path, target_path, step):
        super().__init__()
        self.current_path = current_path
        self.target_path = target_path
        self.step = step

    def run(self):
        all_tasks = []

        # Считаем сколько всего файлов будет скопировано
        for tmp_path in os.listdir(self.current_path):
            path = os.path.join(self.current_path, tmp_path)
            if len([i[0] for i in os.walk(self.current_path)]) > 1:
                if os.path.isdir(path):
                    files = [file for file in os.listdir(path) if file.lower().endswith(('.dng', '.exr', '.jpg'))]
                    all_tasks.append((path, os.path.basename(path), files, True))
            else:
                files = [file for file in os.listdir(self.current_path) if file.lower().endswith(('.dng', '.exr', '.jpg'))]
                all_tasks.append((self.current_path, os.path.basename(self.current_path), files, False))
                break

        total_files = sum(len(files) // self.step + (1 if len(files) % self.step else 0) for _, _, files, _ in all_tasks)
        copied = 0

        for base_path, file_name, files, recurse in all_tasks:
            for i in range(0, len(files), self.step):
                file = os.path.basename(files[i])
                if recurse:
                    old_path = os.path.join(self.current_path, file_name, file)
                    new_path = os.path.join(self.target_path, file_name, file)
                else:
                    old_path = os.path.join(self.current_path, file)
                    new_path = os.path.join(self.target_path, os.path.basename(self.current_path), file)

                try:
                    shutil.copy(old_path, new_path)
                except:
                    seq_folder = os.path.dirname(new_path)
                    os.makedirs(seq_folder, exist_ok=True)
                    shutil.copy(old_path, new_path)

                copied += 1
                percent = int((copied / total_files) * 100)
                self.progress_changed.emit(percent)

        self.copy_finished.emit()


class CopyApp(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Copy Files n-step")
        self.init_ui()

    def init_ui(self):
        layout = QVBoxLayout()

        self.current_input = QLineEdit()
        self.current_btn = QPushButton("Choose")
        self.current_btn.clicked.connect(self.choose_current)

        current_layout = QHBoxLayout()
        current_layout.addWidget(QLabel("Current Path:"))
        current_layout.addWidget(self.current_input)
        current_layout.addWidget(self.current_btn)

        self.target_input = QLineEdit()
        self.target_btn = QPushButton("Choose")
        self.target_btn.clicked.connect(self.choose_target)

        target_layout = QHBoxLayout()
        target_layout.addWidget(QLabel("Target Path:"))
        target_layout.addWidget(self.target_input)
        target_layout.addWidget(self.target_btn)

        self.step_input = QLineEdit()
        self.step_input.setText("100")

        step_layout = QHBoxLayout()
        step_layout.addWidget(QLabel("Step:"))
        step_layout.addWidget(self.step_input)

        self.progress_bar = QProgressBar()
        self.progress_bar.setAlignment(Qt.AlignCenter)

        self.start_btn = QPushButton("Start")
        self.start_btn.clicked.connect(self.start_copying)

        layout.addLayout(current_layout)
        layout.addLayout(target_layout)
        layout.addLayout(step_layout)
        layout.addWidget(self.progress_bar)
        layout.addWidget(self.start_btn)

        self.setLayout(layout)

    def choose_current(self):
        path = QFileDialog.getExistingDirectory(self, "Выбрать исходную папку")
        if path:
            self.current_input.setText(path)

    def choose_target(self):
        path = QFileDialog.getExistingDirectory(self, "Выбрать папку назначения")
        if path:
            self.target_input.setText(path)

    def start_copying(self):
        current = self.current_input.text()
        target = self.target_input.text()
        try:
            step = int(self.step_input.text())
        except ValueError:
            QMessageBox.warning(self, "Ошибка", "Step должен быть числом")
            return

        if not current or not target:
            QMessageBox.warning(self, "Ошибка", "Пожалуйста, заполните все поля.")
            return

        self.worker = CopyWorker(current, target, step)
        self.worker.progress_changed.connect(self.progress_bar.setValue)
        self.worker.copy_finished.connect(self.on_copy_finished)
        self.worker.start()

    def on_copy_finished(self):
        QMessageBox.information(self, "Готово", "Копирование завершено!")


if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = CopyApp()
    window.resize(600, 200)
    window.show()
    sys.exit(app.exec_())
