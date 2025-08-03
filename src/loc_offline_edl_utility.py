from pprint import pformat
import re
from timecode import Timecode as tc
import DaVinciResolveScript as dvr
import sys
from PyQt5 import QtWidgets, QtCore
from PyQt5.QtCore import Qt, QThread, pyqtSignal
from PyQt5.QtWidgets import QMessageBox
from dataclasses import dataclass
from dvr_tools.css_style import apply_style
from dvr_tools.logger_config import get_logger
from dvr_tools.resolve_utils import ResolveObjects

logger = get_logger(__file__)


class LogicProcessor:
    """
    Класс работы с логикой.
    """
    def __init__(self, user_config, signals):
        self.user_config = user_config
        self.signals = signals

    def get_markers(self): 
        '''
        Получение маркеров для работы других функций
        '''
        try:
            markers_list = []
            for timecode, name in self.timeline.GetMarkers().items():
                name = name[self.marker_from].strip()
                timecode_marker = tc(self.fps, frames=timecode + self.timeline_start_tc) + 1  
                markers_list.append((name, timecode_marker))
            return markers_list
        except Exception as e:
            self.signals.error_signal.emit(f"Ошибка получения данных об объектах маркеров")
            return False

    def set_markers(self):
        '''
        Установка маркеров с номерами полученными из оффлайн клипов на текущем таймлайне 
        '''
        try:
            clips = self.timeline.GetItemListInTrack('video', self.track_number)
            for clip in clips:
                clip_name = clip.GetName()
                clip_start = int((clip.GetStart() + (clip.GetStart() + clip.GetDuration())) / 2) - self.timeline_start_tc
                self.timeline.AddMarker(clip_start, 'Blue', clip_name, "", 1, 'Renamed')
            logger.debug("Маркеры успешно созданы")
        except Exception as e:
            self.signals.error_signal.emit(f"Ошибка создания маркеров")
            return False

    def export_locators_to_avid(self):
        '''
        Формирование строк и экспорт локаторов для AVID в .txt.
        '''
        print(self.output_path)
        try:
            markers_list = self.get_markers()
            with open(self.locators_output_path, "a", encoding='utf8') as output:
                for name, timecode in markers_list:
                    # Используется спец табуляция для корректного импорта в AVID
                    output_string = f'PGM	{str(timecode)}	V3	yellow	{name}'
                    output.write(output_string + "\n")
            logger.debug(f"Локаторы успешно экспортированы. Путь: {self.locators_output_path}")
        except Exception as e:
            self.signals.error_signal.emit(f"Ошибка формирования локаторов")
            return False
        
    def process_edl(self):
        """
        Выводит EDL для дейлизов и EDL с оффлайн клипами.
        """
        try:
            markers_list = self.get_markers()
            with open(self.edl_path, "r", encoding='utf8') as edl_file:
                title = [next(edl_file) for _ in range(2)]
                lines = edl_file.readlines()

            with open(self.output_path, "w", encoding='utf8') as output:
                output.write("".join(title) + "\n")
                for line in lines:
                    if re.search(r'^\d+\s', line.strip()):  
                        parts = line.split()
                        edl_timeline_start_tc = parts[6]
                        edl_timeline_end_tc = parts[7]

                        # Логика для offline_clips
                        if self.offline_edl:
                            marker_name = None
                            for name, timecode in markers_list:
                                if tc(self.fps, edl_timeline_start_tc).frames <= tc(self.fps, timecode).frames <= tc(self.fps, edl_timeline_end_tc).frames:
                                    marker_name = name
                            if marker_name is not None:
                                output.write(" ".join(parts) + '\n')
                                output.write(f'* FROM CLIP NAME: {marker_name}\n\n')

                        # Логика для edl_for_dailies
                        elif self.dailies_edl:
                            for name, timecode in markers_list:
                                if tc(self.fps, edl_timeline_start_tc).frames <= tc(self.fps, timecode).frames <= tc(self.fps, edl_timeline_end_tc).frames:
                                    parts[1] = name
                            output.write(" ".join(parts) + '\n')
                logger.debug(f"EDL для дейлизов успешно сформировано. Путь: {self.output_path}")
        except Exception as e:
            self.signals.error_signal.emit(f"Ошибка формирования EDL")
            return False

    def run(self):
        self.timeline = ResolveObjects().timeline
        self.process_edl_logic = self.user_config["process_edl"]
        self.edl_path = self.user_config["edl_path"]
        self.output_path = self.user_config["output_path"]
        self.locators_output_path = self.user_config["locators_output_path"]
        self.export_loc_cb = self.user_config["export_loc"]
        self.fps = int(self.user_config["fps"])
        self.track_number = int(self.user_config["track_number"])
        self.set_markers_cb = self.user_config["set_markers"]
        self.marker_from = self.user_config["locator_from"]
        self.timeline_start_tc = self.timeline.GetStartFrame()
        self.offline_edl = self.user_config["offline_checkbox"]
        self.dailies_edl = self.user_config["dailies_checkbox"]


        if self.process_edl_logic:
            process_edl_var = self.process_edl()
            if not process_edl_var:
                return

        if self.set_markers_cb:
            set_markers_var = self.set_markers()
            if not set_markers_var:
                return

        if self.export_loc_cb:
            export_loc_var = self.export_locators_to_avid()
            if not export_loc_var:
                return

class LogicWorker(QThread):
    """
    Класс работы с логикой в отдельном потоке.
    """
    error_signal = pyqtSignal(str)
    success_signal = pyqtSignal(str)
    warning_signal = pyqtSignal(str)
    info_signal = pyqtSignal(str)

    def __init__(self, parent, user_config):
        super().__init__(parent)
        self.user_config = user_config

    def run(self):
        logic = LogicProcessor(self.user_config, self)
        logic.run()
        self.success_signal.emit("Обработка успешно завершена!")

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
        "edl_path": self.gui.input_entry.text(),
        "output_path": self.gui.output_entry.text(),
        "export_loc": self.gui.export_loc_checkbox.isChecked(),
        "set_markers": self.gui.set_markers_checkbox.isChecked(),
        "process_edl": (self.gui.offline_clips_checkbox.isChecked() 
                        or self.gui.edl_for_dailies_checkbox.isChecked()),
        "fps": self.gui.fps_entry.text(),
        "locators_output_path": self.gui.save_locators_path_entry.text(),
        "locator_from": self.gui.locator_from_combo.currentText(),
        "track_number": self.gui.track_entry.text(),
        "offline_checkbox": self.gui.offline_clips_checkbox.isChecked(),
        "dailies_checkbox": self.gui.edl_for_dailies_checkbox.isChecked()
        }
    
    def validate(self, user_config: dict) -> bool:
        """
        Валидирует конфиг.
        """
        self.errors.clear()

        process_edl = user_config["process_edl"]
        edl_path = user_config["edl_path"]
        output_path = user_config["output_path"]
        locators_output_path = user_config["locators_output_path"]
        export_loc = user_config["export_loc"]
        fps = user_config["fps"]
        track_number = user_config["track_number"]

        try:
            resolve = ResolveObjects()
        except RuntimeError as re:
            self.errors.append(re)

        if process_edl and (not edl_path or not output_path):
            self.errors.append("Выберите файлы EDL!")
            return
        
        if not locators_output_path and export_loc:
            self.errors.append("Введите путь для сохранения локаторов")
            return

        try:
            fps = int(fps)
        except ValueError:
            self.errors.append("FPS должен быть числом!")
            return
        
        try:
            track_number = int(track_number)
        except ValueError:
            self.errors.append("Номер дорожки должен быть числом!")
            return
        
        if  resolve.timeline is None:
            self.errors.append("Неудалось получить таймлайн")
            return

        if int(track_number) > resolve.timeline.GetTrackCount("video"):
            self.errors.append("Указан несуществующий трек")
            return
        
        return not self.errors

    def get_errors(self) -> list:
        return self.errors

class EDLProcessorGUI(QtWidgets.QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("EDL&Markers Creator")
        self.resize(620, 300)
        self.setWindowFlags(QtCore.Qt.WindowStaysOnTopHint)
        self.init_ui()

    def init_ui(self):
        main_layout = QtWidgets.QVBoxLayout()
        self.setLayout(main_layout)

        # FPS + Locator From (по центру, в одной строке)
        fps_layout = QtWidgets.QHBoxLayout()
        fps_layout.addStretch()
        fps_layout.setAlignment(QtCore.Qt.AlignCenter)

        fps_label = QtWidgets.QLabel("Project FPS:")
        self.fps_entry = QtWidgets.QLineEdit("24")
        self.fps_entry.setFixedWidth(50)

        locator_label = QtWidgets.QLabel("Marker name from:")
        self.locator_from_combo = QtWidgets.QComboBox()
        self.locator_from_combo.setFixedWidth(70)
        self.locator_from_combo.addItems(["name", "note"])

        fps_layout.addWidget(fps_label)
        fps_layout.addWidget(self.fps_entry)
        fps_layout.addSpacing(20)
        fps_layout.addWidget(locator_label)
        fps_layout.addWidget(self.locator_from_combo)
        fps_layout.addStretch()
        main_layout.addLayout(fps_layout)

        # Locators / Track / Export Locators
        block1_group = QtWidgets.QGroupBox("Markers Options")
        block1_group_layout = QtWidgets.QVBoxLayout()

        # Checkboxes and track field
        options_layout = QtWidgets.QHBoxLayout()
        options_layout.setAlignment(QtCore.Qt.AlignLeft)

        self.set_markers_checkbox = QtWidgets.QCheckBox("Set markers")
        self.set_markers_checkbox.stateChanged.connect(self.update_fields_state)
        options_layout.addWidget(self.set_markers_checkbox)
        options_layout.addSpacing(20)

        self.track_label = QtWidgets.QLabel("from track:")
        self.track_entry = QtWidgets.QLineEdit("1")
        self.track_entry.setFixedWidth(40)
        options_layout.addWidget(self.track_label)
        options_layout.addWidget(self.track_entry)
        options_layout.addSpacing(20)

        self.export_loc_checkbox = QtWidgets.QCheckBox("Export locators to Avid")
        self.export_loc_checkbox.stateChanged.connect(self.update_fields_state)
        options_layout.addWidget(self.export_loc_checkbox)
        options_layout.addStretch()
        block1_group_layout.addLayout(options_layout)

        # Save locators path
        save_path_label = QtWidgets.QLabel("Save created locators:")
        save_path_layout = QtWidgets.QHBoxLayout()
        self.save_locators_path_entry = QtWidgets.QLineEdit()
        self.save_path_btn = QtWidgets.QPushButton("Choose")
        self.save_path_btn.clicked.connect(self.select_save_markers_file)
        save_path_layout.addWidget(self.save_locators_path_entry)
        save_path_layout.addWidget(self.save_path_btn)
        self.save_locators_path_entry.setEnabled(False)
        self.save_path_btn.setEnabled(False)

        block1_group_layout.addWidget(save_path_label)
        block1_group_layout.addLayout(save_path_layout)
        block1_group.setLayout(block1_group_layout)
        main_layout.addWidget(block1_group)

        # Offline/Dailies + Input/Output paths 
        block2_group = QtWidgets.QGroupBox("EDL Options")
        block2_group_layout = QtWidgets.QVBoxLayout()

        # Checkboxes
        checks_layout = QtWidgets.QHBoxLayout()
        checks_layout.setAlignment(QtCore.Qt.AlignLeft)
        self.offline_clips_checkbox = QtWidgets.QCheckBox("Offline EDL")
        self.offline_clips_checkbox.stateChanged.connect(self.update_fields_state)
        self.edl_for_dailies_checkbox = QtWidgets.QCheckBox("Dailies EDL")
        self.edl_for_dailies_checkbox.stateChanged.connect(self.update_fields_state)
        checks_layout.addWidget(self.offline_clips_checkbox)
        checks_layout.addSpacing(60)
        checks_layout.addWidget(self.edl_for_dailies_checkbox)
        block2_group_layout.addLayout(checks_layout)

        # Input path
        input_label = QtWidgets.QLabel("Choose EDL-file:")
        input_layout = QtWidgets.QHBoxLayout()
        self.input_entry = QtWidgets.QLineEdit()
        input_btn = QtWidgets.QPushButton("Choose")
        input_btn.clicked.connect(self.select_input_file)
        input_layout.addWidget(self.input_entry)
        input_layout.addWidget(input_btn)
        block2_group_layout.addWidget(input_label)
        block2_group_layout.addLayout(input_layout)

        # Output path
        output_label = QtWidgets.QLabel("Save created EDL:")
        output_layout = QtWidgets.QHBoxLayout()
        self.output_entry = QtWidgets.QLineEdit()
        output_btn = QtWidgets.QPushButton("Choose")
        output_btn.clicked.connect(self.select_output_file)
        output_layout.addWidget(self.output_entry)
        output_layout.addWidget(output_btn)
        block2_group_layout.addWidget(output_label)
        block2_group_layout.addLayout(output_layout)

        block2_group.setLayout(block2_group_layout)
        main_layout.addWidget(block2_group)

        # Start Button
        self.run_button = QtWidgets.QPushButton("Start")
        self.run_button.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Fixed)
        self.run_button.clicked.connect(self.run_script)
        main_layout.addWidget(self.run_button)

    def select_input_file(self):
        file_path, _ = QtWidgets.QFileDialog.getOpenFileName(self, "Select EDL file", "", "EDL files (*.edl)")
        if file_path:
            self.input_entry.setText(file_path)

    def select_save_markers_file(self):
        file_path, _ = QtWidgets.QFileDialog.getSaveFileName(self, "Save Markers File", "", "Text Files (*.txt);;All Files (*)")
        if file_path:
            self.save_locators_path_entry.setText(file_path)

    def select_output_file(self):
        file_path, _ = QtWidgets.QFileDialog.getSaveFileName(self, "Save As", "", "EDL files (*.edl));;All Files (*)")
        if file_path:
            self.output_entry.setText(file_path)

    def update_fields_state(self):
        self.track_entry.setEnabled(self.set_markers_checkbox.isChecked())

        if not self.export_loc_checkbox.isChecked():
            self.save_locators_path_entry.setEnabled(False)
            self.save_path_btn.setEnabled(False)
        else:
            self.save_locators_path_entry.setEnabled(True)
            self.save_path_btn.setEnabled(True)

    def run_script(self):
        self.validator = ConfigValidator(self)
        self.user_config = self.validator.collect_config()

        if not self.validator.validate(self.user_config):
            QMessageBox.critical(self, "Ошибка", "\n".join(self.validator.get_errors()))
            return

        logger.info(f"\n\nSetUp:\n{pformat(self.user_config)}\n") 

        self.main_process = LogicWorker(self, self.user_config)
        self.run_button.setEnabled(False)
        self.main_process.finished.connect(lambda : self.run_button.setEnabled(True))
        self.main_process.error_signal.connect(self.on_error_signal)
        self.main_process.success_signal.connect(self.on_success_signal)
        self.main_process.warning_signal.connect(self.on_warning_signal)
        self.main_process.info_signal.connect(self.on_info_signal)
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

if __name__ == '__main__':
    app = QtWidgets.QApplication(sys.argv)
    apply_style(app)
    window = EDLProcessorGUI()
    window.show()
    sys.exit(app.exec_())
