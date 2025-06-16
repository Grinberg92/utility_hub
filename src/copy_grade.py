from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QLineEdit, QComboBox, QPushButton, QMessageBox
)
from PyQt5.QtCore import pyqtSignal, QObject, QThread, Qt
import DaVinciResolveScript
import sys


class WorkerSignals(QObject):
    finished = pyqtSignal()
    error = pyqtSignal(str)
    success = pyqtSignal(str)


class TransferWorker(QThread):
    def __init__(self, parent, track_1, track_2, lut_name):
        super().__init__()
        self.parent = parent
        self.track_1 = track_1
        self.track_2 = track_2
        self.lut_name = lut_name
        self.signals = WorkerSignals()

    def run(self):
        try:
            project = self.parent.project_manager.GetCurrentProject()
            if not project:
                self.signals.error.emit("Проект не найден.")
                return

            timeline = project.GetCurrentTimeline()
            if not timeline:
                self.signals.error.emit("Таймлайн не найден.")
                return

            source_clips = timeline.GetItemListInTrack("video", self.track_1)
            target_clips = timeline.GetItemListInTrack("video", self.track_2)

            if not target_clips:
                self.signals.error.emit("На целевой дорожке нет клипов.")
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

                if matching_clip and matching_clip.GetNumNodes() <= 1:
                    matching_clip.AssignToColorGroup(color_group)
                    source_clip.CopyGrades(matching_clip)

                    lut_path = [
                        path for path, name in self.parent.lut_list.items()
                        if name == self.lut_name
                    ][0]

                    if lut_path is not None:
                        project.RefreshLUTList()
                        matching_clip.SetLUT(1, lut_path)

            self.signals.success.emit("Цветокоррекция успешно перенесена.")
        except Exception as e:
            self.signals.error.emit(str(e))


class ColorGradeApplyApp(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Copy Grade")
        self.resize(390, 150)
        self.setMinimumSize(320, 150)
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
        track_layout.addWidget(QLabel("Source track:"))
        self.track_1_input = QLineEdit()
        self.track_1_input.setFixedWidth(40)
        track_layout.addWidget(self.track_1_input)

        track_layout.addWidget(QLabel("Target track:"))
        self.track_2_input = QLineEdit()
        self.track_2_input.setFixedWidth(40)
        track_layout.addWidget(self.track_2_input)
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
        try:
            track_1 = int(self.track_1_input.text())
            track_2 = int(self.track_2_input.text())
        except ValueError:
            self.show_error("Ошибка", "Введите корректные номера дорожек.")
            return

        selected_lut = self.lut_combobox.currentText()

        self.worker = TransferWorker(self, track_1, track_2, selected_lut)
        self.worker.signals.error.connect(lambda msg: self.show_error("Ошибка", msg))
        self.worker.signals.success.connect(lambda msg: self.show_info("Успех", msg))
        self.worker.start()

    def show_error(self, title, message):
        QMessageBox.critical(self, title, message)

    def show_info(self, title, message):
        QMessageBox.information(self, title, message)


if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = ColorGradeApplyApp()
    window.show()
    sys.exit(app.exec_())

