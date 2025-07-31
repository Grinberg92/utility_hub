from PyQt5 import QtWidgets, QtCore
from PyQt5.QtWidgets import QMessageBox
import re
from timecode import Timecode as tc
import DaVinciResolveScript as dvr
import sys
from dvr_tools.css_style import apply_style
from dvr_tools.logger_config import get_logger
from dvr_tools.resolve_utils import ResolveObjects

logger = get_logger(__file__)

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

        # === FPS + Locator From (по центру, в одной строке) ===
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

        # === Блок 1: Locators / Track / Export Locators ===
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

        self.export_loc_checkbox = QtWidgets.QCheckBox("Export locators to AVID")
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

        # === Блок 2: Offline/Dailies + Input/Output paths ===
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

        # === Start Button ===
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

        logger.debug("Запуск скрипта")
        
        edl_path = self.input_entry.text()
        output_path = self.output_entry.text()
        export_loc = self.export_loc_checkbox.isChecked()
        set_markers = self.set_markers_checkbox.isChecked()
        fps = self.fps_entry.text()
        process_edl = self.edl_for_dailies_checkbox.isChecked() or self.offline_clips_checkbox.isChecked()
        locators_output_path = self.save_locators_path_entry.text()
        locator_from = self.locator_from_combo.currentText()
        resolve = ResolveObjects()
        track_number = self.track_entry.text()
        offline_checkbox = self.offline_clips_checkbox.isChecked()
        dailies_checkbox = self.edl_for_dailies_checkbox.isChecked()

        if process_edl and (not edl_path or not output_path):
            QMessageBox.warning(self,"Ошибка", "Выберите файлы EDL!")
            logger.warning("Выберите файлы EDL!")
            return
        if not locators_output_path and export_loc:
            QMessageBox.warning(self, "Ошибка", "Введите путь для сохранения локаторов")
            logger.warning("Введите путь для сохранения локаторов")
            return

        try:
            fps = int(fps)
        except ValueError:
            QMessageBox.warning(self,"Ошибка", "FPS должен быть числом!")
            logger.warning("FPS должен быть числом!")
            return
        
        try:
            track_number = int(track_number)
        except ValueError:
            QMessageBox.warning(self,"Ошибка", "Номер дорожки должен быть числом!")
            logger.warning("Номер дорожки должен быть числом!")
            return
        
        if int(track_number) > resolve.timeline.GetTrackCount("video"):
            QMessageBox.warning(self, "Ошибка", "Указан несуществующий трек")
            logger.warning("Указан несуществующий трек")
            return

        try:
            self.resolve = dvr.scriptapp("Resolve")
            self.project = self.resolve.GetProjectManager().GetCurrentProject()
            self.timeline = self.project.GetCurrentTimeline()
            self.timeline_start_tc = self.timeline.GetStartFrame()

            logger.debug("\n".join(("SetUp:", f"Project FPS: {fps}", f"Marker name from: {locator_from}", f"Set markers: {set_markers}",
                                    f"From track: {track_number}", f"Export locators to AVID: {export_loc}",
                                    f"Save created locators: {locators_output_path or None}", f"Offline EDL: {offline_checkbox}", 
                                    f"Dailies EDL: {dailies_checkbox}", f"Choose EDL-file: {edl_path or None}", 
                                    f"Save created EDL: {output_path or None}")))

            if process_edl:
                self.process_edl(self.timeline, edl_path, output_path, fps)

            if set_markers:
                self.set_markers(self.timeline, track_number)

            if export_loc:
                self.export_locators_to_avid(locators_output_path)

            QMessageBox.information(self, "Готово", "Обработка завершена!")
            logger.debug("Обработка завершена!")
        except Exception as e:
            QMessageBox.critical(self, "Ошибка", f"Ошибка подключения Resolve: {e}")
            logger.exception(f"Ошибка подключения Resolve: {e}")
            return

    def get_markers(self, timeline_start_timecode): 
        '''
        Получение маркеров для работы других функций
        '''
        try:
            marker_from = self.locator_from_combo.currentText()
            markers_list = []
            for timecode, name in self.timeline.GetMarkers().items():
                name = name[marker_from].strip()
                timecode_marker = tc(self.fps_entry.text(), frames=timecode + timeline_start_timecode) + 1  
                markers_list.append((name, timecode_marker))
            return markers_list
        except Exception as e:
            QMessageBox.critical(f"Ошибка получения данных об объектах маркеров: {e}")
            logger.exception(f"Ошибка получения данных об объектах маркеров: {e}")
            return

    def set_markers(self, timeline, track_number):
        '''
        Установка маркеров с номерами полученными из оффлайн клипов на текущем таймлайне 
        '''
        try:
            clips = timeline.GetItemListInTrack('video', track_number)
            for clip in clips:
                clip_name = clip.GetName()
                clip_start = int((clip.GetStart() + (clip.GetStart() + clip.GetDuration())) / 2) - timeline.GetStartFrame()
                timeline.AddMarker(clip_start, 'Blue', clip_name, "", 1, 'Renamed')
            logger.debug("Маркеры успешно созданы")
        except Exception as e:
            QMessageBox.critical(f"Ошибка создания маркеров: {e}")
            logger.exception(f"Ошибка создания маркеров: {e}")
            return

    def export_locators_to_avid(self, output_path):
        '''
        Формирование строк и экспорт локаторов для AVID в .txt
        '''
        try:
            markers_list = self.get_markers(self.timeline_start_tc)
            with open(output_path, "a", encoding='utf8') as output:
                for name, timecode in markers_list:
                    # Используется спец табуляция для корректного импорта в AVID
                    output_string = f'PGM	{str(timecode)}	V3	yellow	{name}'
                    output.write(output_string + "\n")
            logger.debug(f"Локаторы успешно экспортированы. Путь: {output_path}")
        except Exception as e:
            QMessageBox.critical(f"Ошибка формирования локаторов: {e}")
            logger.exception(f"Ошибка формирования локаторов: {e}")
            return

    def process_edl(self, timeline, edl_path, output_path, fps):
        """
        Выводит EDL для дейлизов и EDL с оффлайн клипами
        """
        offline_clips = self.offline_clips_checkbox.isChecked()
        edl_for_dailies = self.edl_for_dailies_checkbox.isChecked()

        def parse_edl():
            try:
                markers_list = self.get_markers(self.timeline_start_tc)
                with open(edl_path, "r", encoding='utf8') as edl_file:
                    title = [next(edl_file) for _ in range(2)]
                    lines = edl_file.readlines()

                with open(output_path, "w", encoding='utf8') as output:
                    output.write("".join(title) + "\n")
                    for line in lines:
                        if re.search(r'^\d+\s', line.strip()):  
                            parts = line.split()
                            edl_timeline_start_tc = parts[6]
                            edl_timeline_end_tc = parts[7]

                            # Логика для offline_clips
                            if offline_clips:
                                marker_name = None
                                for name, timecode in markers_list:
                                    if tc(fps, edl_timeline_start_tc).frames <= tc(fps, timecode).frames <= tc(fps, edl_timeline_end_tc).frames:
                                        marker_name = name
                                if marker_name is not None:
                                    output.write(" ".join(parts) + '\n')
                                    output.write(f'* FROM CLIP NAME: {marker_name}\n\n')

                            # Логика для edl_for_dailies
                            elif edl_for_dailies:
                                for name, timecode in markers_list:
                                    if tc(fps, edl_timeline_start_tc).frames <= tc(fps, timecode).frames <= tc(fps, edl_timeline_end_tc).frames:
                                        parts[1] = name
                                output.write(" ".join(parts) + '\n')
                    logger.debug(f"EDL для дейлизов успешно сформировано. Путь: {output_path}")
            except Exception as e:
                QMessageBox.critical(f"Ошибка формирования EDL: {e}")
                logger.exception(f"Ошибка формирования EDL: {e}")
                return

        parse_edl()

if __name__ == '__main__':
    app = QtWidgets.QApplication(sys.argv)
    apply_style(app)
    window = EDLProcessorGUI()
    window.show()
    sys.exit(app.exec_())
