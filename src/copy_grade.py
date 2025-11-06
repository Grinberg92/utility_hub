import DaVinciResolveScript
import sys
import os
import bisect
from dvr_tools.logger_config import get_logger
from dvr_tools.css_style import apply_style
from dvr_tools.resolve_utils import ResolveObjects
from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QLineEdit, QComboBox, QPushButton, QMessageBox
)
from PyQt5.QtCore import pyqtSignal, QObject, QThread, Qt

logger = get_logger(__file__)

class TransferWorker(QThread):

    finished = pyqtSignal()
    error = pyqtSignal(str)
    success = pyqtSignal(str)

    def __init__(self, parent, source_track_in, source_track_out, target_track, lut_name):
        super().__init__()
        self.parent = parent
        self.source_track_in = source_track_in
        self.source_track_out = source_track_out
        self.target_track = target_track
        self.lut_name = lut_name

    def get_source_clips(self, start_track: int, end_track: int, timeline) -> list:
        top_clips = []
        covered = []  # список интервалов (start, end), отсортированный по start

        def intersects(start, end):
            """Проверка пересечений через двоичный поиск."""
            i = bisect.bisect_left(covered, (start, end))
            # Проверяем интервал слева
            if i > 0 and covered[i-1][1] > start:
                return True
            # Проверяем интервал справа
            if i < len(covered) and covered[i][0] < end:
                return True
            return False

        def add_interval(start, end):
            """Вставка интервала с возможным слиянием."""
            i = bisect.bisect_left(covered, (start, end))
            
            # слияние с соседями
            while i < len(covered) and covered[i][0] <= end:
                start = min(start, covered[i][0])
                end = max(end, covered[i][1])
                covered.pop(i)
            
            if i > 0 and covered[i-1][1] >= start:
                start = min(start, covered[i-1][0])
                end = max(end, covered[i-1][1])
                covered.pop(i-1)
                i -= 1
            
            covered.insert(i, (start, end))

        # идем от верхних треков к нижним
        for track_index in range(end_track, start_track - 1, -1):
            for clip in timeline.GetItemListInTrack('video', track_index):
                start = clip.GetStart()
                end = start + clip.GetDuration()

                if not intersects(start, end):
                    top_clips.append(clip)
                    add_interval(start, end)

        return top_clips

    def run(self):
        """
        Основная логика.
        """
        try:
            project = self.parent.project
            if not project:
                self.error.emit("Проект не найден.")
                return

            timeline = self.parent.timeline
            if not timeline:
                self.error.emit("Таймлайн не найден.")
                return
            
            source_clips = self.get_source_clips(self.source_track_in, self.source_track_out, timeline)
            target_clips = timeline.GetItemListInTrack("video", self.target_track)

            if not target_clips:
                self.error.emit("На целевой дорожке нет клипов.")
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
        track_layout.addWidget(QLabel("Source tracks range:"))
        self.source_track_in_input = QLineEdit()
        self.source_track_out_input = QLineEdit()
        self.source_track_out_input.setFixedWidth(40)
        self.source_track_in_input.setFixedWidth(40)
        track_layout.addWidget(self.source_track_in_input)
        track_layout.addWidget(QLabel(" - "))
        track_layout.addWidget(self.source_track_out_input)
        track_layout.addSpacing(20)

        track_layout.addWidget(QLabel("Target track:"))
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

        self.refresh_button = QPushButton("Refresh timeline")
        self.refresh_button.clicked.connect(self.refresh_timeline_data)
        layout.addWidget(self.refresh_button)

        self.apply_button = QPushButton("Start")
        self.apply_button.clicked.connect(self.start_transfer)
        layout.addWidget(self.apply_button)

        central_widget.setLayout(layout)
        self.setCentralWidget(central_widget)

    def refresh_timeline_data(self):
        try:
            resolve = ResolveObjects()
        except RuntimeError:
            self.show_error("Нет подключения к API Resolve.")

        self.project = resolve.project
        self.timeline = resolve.timeline

        if not self.project:
            self.show_error("Ошибка", "Проект не найден.")
            return

        if not self.timeline:
            self.show_error("Ошибка", "Таймлайн не найден.")
            return
        
    def is_cc(self, target_track) -> bool:
        """
        Проверка на отсутствие ЦК в target_clips.
        """
        target_clips = self.timeline.GetItemListInTrack("video", target_track)
        # Больше одной ноды
        has_nodes = any(clip.GetNumNodes() > 1 for clip in target_clips)
        # Есть ЦК в ноде
        has_tools = any(bool(clip.GetNodeGraph(1).GetToolsInNode(1)) for clip in target_clips)

        return has_nodes or has_tools

    
    def start_transfer(self):

        logger.debug("Запуск скрипта")
        
        try:
            source_track_in = int(self.source_track_in_input.text())
            target_track = int(self.target_track_input.text())
            source_track_out = int(self.source_track_out_input.text())
        except ValueError:
            self.show_error("Ошибка", "Введите корректные номера дорожек.")
            return

        selected_lut = self.lut_combobox.currentText()

        if self.is_cc(target_track):
            reply = QMessageBox.question(
                self,
                "Подтверждение",
                "На выбранной дорожке присутствует ЦК.\nВы уверены, что хотите продолжить?",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No
            )

            if reply == QMessageBox.No:
                return  

        logger.debug("\n".join(("SetUp:", f"Source track in: {source_track_in}", f"Source track out: {source_track_in}", f"Target track: {target_track}", f"Select LUT: {selected_lut}")))
        self.worker = TransferWorker(self, source_track_in, source_track_out, target_track, selected_lut)
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

