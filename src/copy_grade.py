from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QLineEdit, QComboBox, QPushButton, QMessageBox
)
from PyQt5.QtCore import pyqtSignal, QObject, QThread, Qt
import DaVinciResolveScript
import sys
import os
from dvr_tools.logger_config import get_logger
from dvr_tools.css_style import apply_style

logger = get_logger(__file__)

class TransferWorker(QThread):

    finished = pyqtSignal()
    error = pyqtSignal(str)
    success = pyqtSignal(str)

    def __init__(self, parent, source_track, target_track, lut_name):
        super().__init__()
        self.parent = parent
        self.source_track = source_track
        self.target_track = target_track
        self.lut_name = lut_name

    def run(self):
        try:
            project = self.parent.project_manager.GetCurrentProject()
            if not project:
                self.error.emit("Проект не найден.")
                return

            timeline = project.GetCurrentTimeline()
            if not timeline:
                self.error.emit("Таймлайн не найден.")
                return

            source_clips = timeline.GetItemListInTrack("video", self.source_track)
            target_clips = timeline.GetItemListInTrack("video", self.target_track)

            if not target_clips:
                self.error.emit("На целевой дорожке нет клипов.")
                return
            
            # Проверка на отсутствие ЦК в target_clips
            if (any(map(lambda x: x > 1, [clip.GetNumNodes() for clip in target_clips])) or 
                any(filter(lambda x: x is not None,  [clip.GetNodeGraph(1).GetToolsInNode(1) for clip in target_clips]))):

                self.error.emit("На выбранной дорожке присутствует ЦК.")
                return

            def find_clip_on_track(track_clips, start_timecode):
                for clip in track_clips:
                    if clip.GetStart() == start_timecode:
                        return clip
                return None

            for source_clip in source_clips:
                start_time = source_clip.GetStart()
                color_group = source_clip.GetColorGroup()
                matching_clip = find_clip_on_track(target_clips, start_time)

                if matching_clip:
                    matching_clip.AssignToColorGroup(color_group)
                    source_clip.CopyGrades(matching_clip)

                    lut_path = [
                        path for path, name in self.parent.lut_list.items()
                        if name == self.lut_name
                    ][0]

                    if lut_path is not None:
                        project.RefreshLUTList()
                        matching_clip.SetLUT(1, lut_path)
                        logger.debug(f"Применен LUT: {os.path.basename(lut_path)}")
                else:
                    logger.debug(f"Не перенесена ЦК с клипа {source_clip.GetName()}")

            self.success.emit("Цветокоррекция успешно перенесена.")
        except Exception as e:
            self.error.emit(str(e))


class ColorGradeApplyApp(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Copy Grade")
        self.resize(390, 200)
        self.setWindowFlags(Qt.WindowStaysOnTopHint)

        self.resolve = DaVinciResolveScript.scriptapp("Resolve")
        self.project_manager = self.resolve.GetProjectManager()
        self.project = None
        self.timeline = None

        self.lut_list = {
            None: "No LUT",
            "/Library/Application Support/Blackmagic Design/DaVinci Resolve/LUT/VFX IO/AP0_to_AlexaLogC_v2.cube": "AP0_to_AlexaLogC_v2",
            "/Library/Application Support/Blackmagic Design/DaVinci Resolve/LUT/CLF_TEST/cmp_0020_0050_pregrade.clf": "cmp_0020_0050_pregrade"
        }

        self.init_ui()
        self.refresh_timeline_data()

    def init_ui(self):
        central_widget = QWidget()
        layout = QVBoxLayout()

        # --- Дорожки ---
        track_layout = QHBoxLayout()
        track_layout.addStretch()
        track_layout.addWidget(QLabel("Source Track:"))
        self.source_track_input = QLineEdit()
        self.source_track_input.setFixedWidth(40)
        track_layout.addWidget(self.source_track_input)

        track_layout.addWidget(QLabel("Target Track:"))
        self.target_track_input = QLineEdit()
        self.target_track_input.setFixedWidth(40)
        track_layout.addWidget(self.target_track_input)
        track_layout.addStretch()
        layout.addLayout(track_layout)

        # --- LUT ---
        lut_layout = QHBoxLayout()
        lut_layout.addWidget(QLabel("Select LUT:"))
        self.lut_combobox = QComboBox()
        self.lut_combobox.addItems(list(self.lut_list.values()))
        self.lut_combobox.setFixedWidth(300)
        lut_layout.addWidget(self.lut_combobox)
        layout.addLayout(lut_layout)

        # --- Кнопки ---

        self.refresh_button = QPushButton("Refresh")
        self.refresh_button.clicked.connect(self.refresh_timeline_data)
        layout.addWidget(self.refresh_button)

        self.apply_button = QPushButton("Start")
        self.apply_button.clicked.connect(self.start_transfer)
        layout.addWidget(self.apply_button)

        central_widget.setLayout(layout)
        self.setCentralWidget(central_widget)

    def refresh_timeline_data(self):
        self.project = self.project_manager.GetCurrentProject()
        if not self.project:
            self.show_error("Ошибка", "Проект не найден.")
            return

        self.timeline = self.project.GetCurrentTimeline()
        if not self.timeline:
            self.show_error("Ошибка", "Таймлайн не найден.")
            return

    def start_transfer(self):

        logger.debug("Запуск скрипта")
        
        try:
            source_track = int(self.source_track_input.text())
            target_track = int(self.target_track_input.text())
        except ValueError:
            self.show_error("Ошибка", "Введите корректные номера дорожек.")
            return

        selected_lut = self.lut_combobox.currentText()

        logger.debug("\n".join(("SetUp:", f"Source Track: {source_track}", f"Target Track: {target_track}", f"Select LUT: {selected_lut}")))
        self.worker = TransferWorker(self, source_track, target_track, selected_lut)
        self.worker.error.connect(lambda msg: self.show_error("Ошибка", msg))
        self.worker.success.connect(lambda msg: self.show_info("Успех", msg))
        self.worker.start()

    def show_error(self, title, message):
        QMessageBox.critical(self, title, message)
        logger.exception(message)
        

    def show_info(self, title, message):
        QMessageBox.information(self, title, message)
        logger.debug(message)


if __name__ == "__main__":
    app = QApplication(sys.argv)
    apply_style(app)
    window = ColorGradeApplyApp()
    window.show()
    sys.exit(app.exec_())

