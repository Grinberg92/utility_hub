import DaVinciResolveScript as dvr
import os
import re
import shutil
from pathlib import Path
from datetime import datetime
from PyQt5.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QLabel, QPushButton,
    QComboBox, QTextEdit, QCheckBox, QMessageBox, QProgressBar
)
from PyQt5.QtCore import Qt, QThread, pyqtSignal
from dvr_tools.logger_config import get_logger
from dvr_tools.css_style import apply_style

logger = get_logger(__file__)


class WorkerThread(QThread):
    finished_signal = pyqtSignal()
    error_signal = pyqtSignal(str)
    progress_signal = pyqtSignal(int)
    shot_signal = pyqtSignal(str)

    def __init__(self, parent, shot_paths):
        super().__init__(parent)
        self.shot_paths = shot_paths
        self.parent = parent

    def run(self):
        try:
            for shot_path in self.shot_paths:
                shot_name = os.path.basename(shot_path)
                self.shot_signal.emit(shot_name)
                self.parent.process_shot(shot_path, self.progress_signal)
            self.finished_signal.emit()
        except Exception as e:
            self.error_signal.emit(str(e))


class GetShotDvr(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Get Shot")
        self.setWindowFlag(Qt.WindowStaysOnTopHint)

        layout = QVBoxLayout()

        # Выбор проекта
        try:
            self.projects = os.listdir(self.cross_platform_name('R:/'))
        except Exception as e:
            QMessageBox.critical(self, "Ошибка", "Ошибка запуска. Не подключен диск RAID")
            logger.exception("Ошибка запуска. Не подключен диск RAID")
            
        self.selected_project = QComboBox()
        self.selected_project.addItems(self.projects)
        self.selected_project.setCurrentIndex(10)
        layout.addWidget(QLabel("Choose Project:"))
        layout.addWidget(self.selected_project)

        # Чекбоксы
        self.is_append = QCheckBox("Add to timeline")
        self.is_normalize = QCheckBox("Set normalize")
        layout.addWidget(self.is_append)
        layout.addWidget(self.is_normalize)

        # Поле для ввода путей
        self.text_widget = QTextEdit()
        layout.addWidget(self.text_widget)

        # Прогрессбар и метка текущего шота
        self.current_shot_label = QLabel("Downloading: ")
        self.progress_bar = QProgressBar()
        self.progress_bar.setValue(0)
        layout.addWidget(self.current_shot_label)
        layout.addWidget(self.progress_bar)

        # Кнопка обработки
        self.process_button = QPushButton("Start")
        self.process_button.clicked.connect(self.run)
        layout.addWidget(self.process_button)

        self.setLayout(layout)
        self.set_window_position()

    def set_window_position(self):
        screen = QApplication.primaryScreen().geometry()
        window_width, window_height = 530, 350
        x = (screen.width() // 2) - (window_width // 2)
        y = int((screen.height() * 7 / 10) - (window_height / 2))
        self.setGeometry(x, y, window_width, window_height)

    def toggle_button(self, locked):
        self.process_button.setEnabled(not locked)

    def show_message(self, title, message, is_error=False):
        QMessageBox.critical(self, title, message) if is_error else QMessageBox.information(self, title, message)

    def cross_platform_name(self, data):
        if os.name == 'nt':
            path_T = 'T:/'
            path_R = 'R:/'
        else:
            path_T = '/Volumes/transfer/'
            path_R = '/Volumes/RAID/'

        if data.startswith('T:/'):
            data = data.replace('T:/', '', 1)
            result_path = Path(path_T) / data
        elif data.startswith("/mnt"):
            data = data.replace('/mnt/', '', 1)
            result_path = Path(path_T) / os.path.dirname(data)
        elif data.startswith('R:/'):
            data = data.replace('R:/', '', 1)
            result_path = Path(path_R) / data
        else:
            result_path = Path(data)

        return result_path

    def run(self):

        logger.debug("Запуск скрипта")
        
        # Проверка открытого Resolve
        try:
            self.resolve = dvr.scriptapp("Resolve")
            self.project_manager = self.resolve.GetProjectManager()
            self.project = self.project_manager.GetCurrentProject()
            self.media_pool = self.project.GetMediaPool()
            self.cur_bin = self.media_pool.GetCurrentFolder()
            self.timeline = self.project.GetCurrentTimeline()
        except:
            logger.exception('Откройте проект Davinci Resolve')
            QMessageBox.critical(None, 'Ошибка', 'Откройте проект Davinci Resolve')
            return
        # Проверка на наличие хотя бы одного путя в text_widget
        self.toggle_button(True)
        shot_paths = [shot.strip() for shot in self.text_widget.toPlainText().split('\n') if shot.strip()]

        if not shot_paths:
            self.show_message('Ошибка', 'Отсутствуют данные для обработки', True)
            logger.exception('Отсутствуют данные для обработки')
            self.toggle_button(False)
            return
        
        # Проверка существования путей
        invalid_paths = []
        for path in shot_paths:
            resolved_path = self.cross_platform_name(path)
            if not resolved_path.exists():
                invalid_paths.append(str(resolved_path))

        if invalid_paths:
            msg = "Указанные пути не существуют:\n" + "\n".join(invalid_paths)
            self.show_message('Ошибка', msg, True)
            logger.warning("Указаны несуществующие пути:\n" + "\n".join(invalid_paths))
            self.toggle_button(False)
            return

        logger.debug("\n".join((f"SetUp:", f"Choose Project: {self.selected_project.currentText()}", f"Add to timeline: {self.is_append.isChecked()}",
                                f"Set Normalize: {self.is_normalize.isChecked()}", f"Shot Paths: {shot_paths}")))
        logger.debug(f"Начата обработка {len(shot_paths)} шотов")
        self.worker = WorkerThread(self, shot_paths)
        self.worker.finished_signal.connect(self.on_task_completed)
        self.worker.error_signal.connect(self.on_task_failed)
        self.worker.progress_signal.connect(self.update_progress)
        self.worker.shot_signal.connect(self.update_shot_label)
        self.worker.start()

    def update_progress(self, value):
        self.progress_bar.setValue(value)

    def update_shot_label(self, name):
        self.current_shot_label.setText(f"Downloading: {name}")
        self.progress_bar.setValue(0)

    def on_task_completed(self):
        self.show_message('Успех', 'Все файлы скопированы')
        logger.debug('Все файлы скопированы')
        self.toggle_button(False)

    def on_task_failed(self, message):
        self.show_message('Ошибка', f'Ошибка обработки: {message}', True)
        logger.exception(f'Ошибка обработки: {message}')
        self.toggle_button(False)

    def process_shot(self, shot_path, progress_signal):
        shot_path = self.cross_platform_name(shot_path)
        shot_name = os.path.basename(shot_path)

        frames_list = self.copy_sequence_files(shot_path, progress_signal)
        if frames_list:
            logger.debug(f"Шот {os.path.basename(frames_list[0])} скопирован и импортирован")
            self.media_pool.ImportMedia(frames_list)

        if self.is_append.isChecked():
            for item in self.cur_bin.GetClipList():
                if re.search(shot_name, item.GetName()):
                    self.append_to_timeline(item)
                    logger.debug(f"Шот {item.GetName()} добавлен на таймлайн")

    def get_timeline_item(self, mediapool_item):
        for tmln_item in self.timeline.GetItemListInTrack("video", 1):
            if mediapool_item.GetName() == tmln_item.GetName():
                return tmln_item

    def set_normalize_lut(self, item):
        try:
            normalize_lut = r"/Library/Application Support/Blackmagic Design/DaVinci Resolve/LUT/'VFX IO/AP0_to_P3D65.cube"
            timeline_item = self.get_timeline_item(item)
            timeline_item.SetLUT(1, normalize_lut)
            logger.debug(f"Применен LUT к шоту {item.GetName()}")
        except Exception as e:
            logger.exception("Не удалось установить LUT")
            self.show_message("Ошибка", f"Не удалось установить LUT {e}", True)

    def append_to_timeline(self, item):
        # Проверка на активный таймлайн
        if self.is_append.isChecked() and not self.timeline:
            self.show_message('Ошибка', 'Добавление на таймлайн невозможно — ни один таймлайн не открыт.', True)
            logger.warning('Попытка добавления на таймлайн без активного таймлайна.')
            self.toggle_button(False)
            return
        try:
            self.media_pool.AppendToTimeline(item)
            if self.is_normalize.isChecked():
                self.set_normalize_lut(item)
        except Exception as e:
            logger.exception('Не удалось добавить клип на таймлайн')
            self.show_message('Ошибка', f'Не удалось добавить клип на таймлайн: {e}', True)

    def copy_sequence_files(self, seq_path, progress_signal):
        target_list = []
        try:
            current_date = datetime.now().strftime('%Y%m%d')
            destination_dir = os.path.join(self.cross_platform_name(f'R:/{self.selected_project.currentText()}/VFX'), current_date)
            os.makedirs(destination_dir, exist_ok=True)

            shot_name = os.path.basename(seq_path)
            shot_target_dir = os.path.join(destination_dir, shot_name)
            os.makedirs(shot_target_dir, exist_ok=True)

            all_files = []
            for root, _, files in os.walk(seq_path):
                for file in files:
                    if file.endswith((".exr", ".jpg")):
                        all_files.append((root, file))

            total = len(all_files)
            for i, (root, file) in enumerate(all_files):
                full_path = os.path.join(root, file)
                target_file = os.path.join(shot_target_dir, file)

                if not os.path.exists(target_file):
                    shutil.copy2(full_path, target_file)

                target_list.append(target_file)
                percent = int((i + 1) / total * 100)
                progress_signal.emit(percent)

        except Exception as e:
            self.show_message('Ошибка', f'Ошибка копирования файлов: {e}', True)
            logger.exception(f'Ошибка копирования файлов')

        return target_list
    

if __name__ == "__main__":
    app = QApplication([])
    apply_style(app)
    window = GetShotDvr()
    window.show()
    app.exec_()