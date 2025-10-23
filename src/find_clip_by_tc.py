import sys
import re
from timecode import Timecode as tc
from pprint import pformat
from PyQt5 import QtWidgets, QtCore
from dvr_tools.resolve_utils import ResolveObjects
from PyQt5.QtWidgets import (
    QApplication, QWidget, QLabel, QPushButton, QVBoxLayout, QHBoxLayout,
    QLineEdit, QTextEdit, QComboBox, QScrollBar, QFileDialog, QCheckBox, QFrame, QSizePolicy, QMessageBox,
    QGroupBox, QRadioButton, QButtonGroup
)
from PyQt5.QtCore import Qt, QThread, pyqtSignal
from dvr_tools.css_style import apply_style

from dvr_tools.logger_config import get_logger


logger = get_logger(__file__)

class ResolveClipExtractor:

    def __init__(self, user_config, signals):
        self.user_config = user_config
        self.signals = signals

    def get_target_folder(self, root_folder, target_folder):
        """
        Ищем папку 'search bin'.
        """      
        target_source_folder = next((f for f in root_folder.GetSubFolderList() if f.GetName() == target_folder), None)
        if not target_source_folder:
            return None
        else:
            return target_source_folder

    def find_clips_by_name(self, folder, target_name):
        """
        Рекурсивно ищет клип по имени во всём медиапуле.

        :return item: Объект целевого клипа.
        """
        # Сначала обходим все подпапки в обратном порядке (снизу вверх)
        for subfolder in reversed(folder.GetSubFolderList()):
            item = self.find_clips_by_name(subfolder, target_name)
            if item:
                return item  # нашли в подпапке — возвращаем

        # Потом проверяем клипы в текущей папке
        for item in folder.GetClipList():
            if re.search(re.escape(target_name), item.GetName(), re.IGNORECASE):
                return item

        return False

    def get_frame(self, clip, timecode) -> int:
        """
        Высчитываем фрейм таймкода в Resolve используя метаданные клипа.
        Из входящего таймкода из инпута вычитаем стартовый таймкод клипа полученный из метаданных.
        """
        frame = tc(24, timecode).frames - tc(24, clip.GetClipProperty("Start TC")).frames
        return frame

    def get_last_rec_frame(self, timeline, track) -> int:
        """
        Получаем конечный таймкод последнего клипа на треке.
        """
        if len(timeline.GetItemListInTrack("video", track)) > 0:
            last_item = timeline.GetItemListInTrack("video", track)[-1]
            frame = last_item.GetEnd(False)
            return frame 
        else:
            return timeline.GetStartFrame() # Фрейм начала тайлайна Resovle

    def run(self):
        """
        Основная логика.
        """
        self.search_bin = self.user_config["search_bin"]
        self.target_name = self.user_config["target_name"]
        self.input_tc = self.user_config["input_tc"]
        self.output_tc = self.user_config["output_tc"]
        self.track = int(self.user_config["track_input"])
        self.append_mode = self.user_config["append_mode"]
        self.selected_range = self.user_config["selected_range"]

        resolve = ResolveObjects()
        media_pool = resolve.mediapool
        timeline = resolve.timeline
        root = media_pool.GetRootFolder()

        if timeline.GetTrackCount("video") < self.track:
            self.signals.error_signal.emit(f"Трек {self.track} отсутсвует на таймлайне")
            return       

        target_media_folder = self.get_target_folder(root, self.search_bin)

        trg_clip = self.find_clips_by_name(target_media_folder, self.target_name)
        if not trg_clip:
            self.signals.error_signal.emit(f"Клип {trg_clip.GetName()} отсутствует")
            return

        if self.append_mode:
            record_frame = self.get_last_rec_frame(timeline, self.track)
        else:
            # Берем фрейм по плейхеду на таймлайне
            record_frame = tc(24, timeline.GetCurrentTimecode()).frames - 1

        if record_frame is None:
            self.signals.error_signal.emit(f"Ошибка нахождения record frame на таймлайне")
            return

        if self.selected_range:
            start_frame = self.get_frame(trg_clip, self.input_tc)
            end_frame = self.get_frame(trg_clip, self.output_tc) + 1
        else:
            # Берем начальный и конечный фрейм из метаданных клипа
            start_frame = int(trg_clip.GetClipProperty("Start"))
            end_frame = int(trg_clip.GetClipProperty("End")) + 1

        if (start_frame is None or start_frame == '') or (end_frame is None or end_frame  == ''):
            self.signals.error_signal.emit(f"Не удалось получить начальный или конечный таймкод в клипе {trg_clip.GetName()}")
            return

        media_pool.AppendToTimeline([{
            "mediaPoolItem": trg_clip,
            "startFrame": start_frame,
            "endFrame": end_frame,
            "mediaType": 1,
            "trackIndex": self.track,
            "recordFrame": record_frame
        }])

        self.signals.log.emit(f"Клип {trg_clip.GetName()} добавлен на таймлайн")

class ResolveExtractorWorker(QThread):
    """
    Класс работы с логикой в отдельном потоке.
    """
    error_signal = pyqtSignal(str)
    success_signal = pyqtSignal(str)
    warning_signal = pyqtSignal(str)
    info_signal = pyqtSignal(str)
    log = pyqtSignal(str)

    def __init__(self, parent, user_config):
        super().__init__(parent)
        self.user_config = user_config

    def run(self):
        try:
            logic = ResolveClipExtractor(self.user_config, self)
            result = logic.run() 

        except Exception as e:
            self.error_signal.emit(f"Не удалось создать OTIO файл: {e}")

class ConfigValidator:
    """
    Класс собирает и валидирует пользовательские данные.
    """
    def __init__(self, gui):
        self.gui = gui
        self.errors = []

    def collect_config(self) -> dict:
        """
        Собирает пользовательские данные из GUI.
        """
        return {
                "search_bin": self.gui.search_bin_input.text().strip(),
                "target_name": self.gui.target_name_input.text().strip(),
                "input_tc": self.gui.input_tc.text().strip(),
                "output_tc": self.gui.output_tc.text().strip(),
                "track_input": self.gui.track_input.text().strip(),
                "append_mode": self.gui.mode_append_rb.isChecked(),
                "selected_range": self.gui.range_selected_rb.isChecked()
        }
    
    def validate(self, user_config: dict) -> bool:
        """
        Валидирует конфиг.
        """
        self.errors.clear()

        if not user_config["search_bin"]:
            self.errors.append("Укажите бин для поиска клипов")
        if not user_config["target_name"]:
            self.errors.append("Укажите имя целевого клипа")
        if not user_config["input_tc"] and user_config["selected_range"]:
            self.errors.append("Укажите стартовый таймкод")
        if not user_config["output_tc"] and user_config["selected_range"]:
            self.errors.append("Укажите конечный таймкод")

        try:
            int(user_config["track_input"])
        except ValueError:
            self.errors.append("Значения должны быть целыми числами")
        return not self.errors

    def get_errors(self) -> list:
        return self.errors

class ResolveClipExtractorUI(QWidget):
    def __init__(self):
        super().__init__()

        self.search_bin_input = QLineEdit("001_OCF")
        self.target_name_input = QLineEdit()
        self.input_tc = QLineEdit()
        self.output_tc = QLineEdit()
        self.track_input = QLineEdit("1")

        self.range_selected_rb = QRadioButton("Selected")
        self.range_full_rb = QRadioButton("Full Range")
        self.range_selected_rb.setChecked(True)

        self.range_group = QButtonGroup()
        self.range_group.addButton(self.range_selected_rb)
        self.range_group.addButton(self.range_full_rb)

        self.mode_append_rb = QRadioButton("Append")
        self.mode_playhead_rb = QRadioButton("Playhead")
        self.mode_append_rb.setChecked(True)

        self.mode_group = QButtonGroup()
        self.mode_group.addButton(self.mode_append_rb)
        self.mode_group.addButton(self.mode_playhead_rb)

        self.log = QTextEdit()
        self.log.setReadOnly(True)

        self.init_ui()

    def init_ui(self):
        self.setWindowTitle("Clip Extractor")
        self.resize(420, 480)
        self.setWindowFlag(Qt.WindowStaysOnTopHint)

        layout = QtWidgets.QFormLayout()

        range_layout = QHBoxLayout()
        range_label = QLabel("Frame Range:")
        range_layout.addWidget(range_label)
        range_layout.addSpacing(55)
        range_layout.addWidget(self.range_selected_rb)
        range_layout.addSpacing(30)
        range_layout.addWidget(self.range_full_rb)
        range_layout.addStretch()

        mode_layout = QHBoxLayout()
        mode_label = QLabel("Mode:")
        mode_layout.addWidget(mode_label)
        mode_layout.addSpacing(100)
        mode_layout.addWidget(self.mode_append_rb)
        mode_layout.addSpacing(30)
        mode_layout.addWidget(self.mode_playhead_rb)
        mode_layout.addStretch()

        self.run_button = QPushButton("Start")
        self.run_button.clicked.connect(self.run)

        layout.addRow(range_layout)
        layout.addRow("Search Bin:", self.search_bin_input)
        layout.addRow("Target Name:", self.target_name_input)
        layout.addRow("Input TC:", self.input_tc)
        layout.addRow("Output TC:", self.output_tc)
        layout.addRow("Track:", self.track_input)
        layout.addRow(mode_layout)
        layout.addRow(self.run_button)
        layout.addRow(self.log)
        
        self.setLayout(layout)

    def run(self):
        """
        Запуск основной логики.
        """
        self.validator = ConfigValidator(self)
        self.user_config = self.validator.collect_config()

        if not self.validator.validate(self.user_config):
            self.on_error_signal("\n".join(self.validator.get_errors()))
            return
        
        logger.info(f"\n\nSetUp:\n{pformat(self.user_config)}\n")

        self.main_process = ResolveExtractorWorker(self,self.user_config)
        self.run_button.setEnabled(False)
        self.main_process.finished.connect(lambda : self.run_button.setEnabled(True))
        self.main_process.error_signal.connect(self.on_error_signal)
        self.main_process.success_signal.connect(self.on_success_signal)
        self.main_process.warning_signal.connect(self.on_warning_signal)
        self.main_process.info_signal.connect(self.on_info_signal)
        self.main_process.log.connect(self.log_append)
        self.main_process.start()

    def on_error_signal(self, message):
        QMessageBox.critical(self, "Error", message)
        logger.exception(message)
        return

    def on_success_signal(self, message):
        QMessageBox.information(self, "Success", message)
        logger.info(message)

    def on_warning_signal(self, message):
        QMessageBox.warning(self, "Warning", message)
        logger.warning(message)

    def on_info_signal(self, message):
        QMessageBox.information(self, "Info", message)
        logger.info(message)

    def log_append(self, message):
        self.log.append(message)

if __name__ == "__main__":
    app = QApplication(sys.argv)
    apply_style(app)
    window = ResolveClipExtractorUI()
    window.show()
    sys.exit(app.exec_())
