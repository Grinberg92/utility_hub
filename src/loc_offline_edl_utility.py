from PyQt5 import QtWidgets, QtCore
from PyQt5.QtWidgets import QMessageBox
import re
from timecode import Timecode as tc
import DaVinciResolveScript as dvr
import sys


class EDLProcessorGUI(QtWidgets.QWidget):
    def __init__(self):
        super().__init__()

        self.pattern_short = r'(?<!\d)(?:..._)?\d{3,4}[a-zA-Z]?_\d{1,4}(?!\d)'
        self.setWindowTitle("EDL&Markers Creator")
        self.resize(620, 220)
        self.setMinimumSize(400, 200)

        self.init_ui()

    def init_ui(self):
        layout = QtWidgets.QVBoxLayout()
        self.setLayout(layout)

        # === Input file ===
        layout.addWidget(QtWidgets.QLabel("Choose EDL-file:"))
        input_layout = QtWidgets.QHBoxLayout()
        self.input_entry = QtWidgets.QLineEdit()
        input_btn = QtWidgets.QPushButton("Choose")
        input_btn.clicked.connect(self.select_input_file)
        input_layout.addWidget(self.input_entry)
        input_layout.addWidget(input_btn)
        layout.addLayout(input_layout)

        # === Output file ===
        layout.addWidget(QtWidgets.QLabel("Save created EDL:"))
        output_layout = QtWidgets.QHBoxLayout()
        self.output_entry = QtWidgets.QLineEdit()
        output_btn = QtWidgets.QPushButton("Choose")
        output_btn.clicked.connect(self.select_output_file)
        output_layout.addWidget(self.output_entry)
        output_layout.addWidget(output_btn)
        layout.addLayout(output_layout)

        # === Checkboxes ===
        checkboxes_layout = QtWidgets.QGridLayout()

        self.set_markers_checkbox = QtWidgets.QCheckBox("Set locators")
        self.set_markers_checkbox.stateChanged.connect(self.update_fields_state)
        checkboxes_layout.addWidget(self.set_markers_checkbox, 0, 0)

        # Track label + input combined
        track_widget = QtWidgets.QWidget()
        track_layout = QtWidgets.QHBoxLayout()
        track_layout.setContentsMargins(0, 0, 0, 0)
        track_layout.setSpacing(4)  # чуть-чуть отступа
        track_label = QtWidgets.QLabel("Track:")
        track_label.setSizePolicy(QtWidgets.QSizePolicy.Fixed, QtWidgets.QSizePolicy.Fixed)

        self.track_entry = QtWidgets.QLineEdit("1")
        self.track_entry.setMaximumWidth(50)
        self.track_entry.setSizePolicy(QtWidgets.QSizePolicy.Fixed, QtWidgets.QSizePolicy.Fixed)

        track_layout.addWidget(track_label)
        track_layout.addWidget(self.track_entry)
        track_widget.setLayout(track_layout)
        track_widget.setSizePolicy(QtWidgets.QSizePolicy.Fixed, QtWidgets.QSizePolicy.Fixed)

        checkboxes_layout.addWidget(track_widget, 0, 1, alignment=QtCore.Qt.AlignLeft)


        self.export_loc_checkbox = QtWidgets.QCheckBox("Export locators")
        self.export_loc_checkbox.stateChanged.connect(self.update_fields_state)
        checkboxes_layout.addWidget(self.export_loc_checkbox, 0, 2)

        self.offline_clips_checkbox = QtWidgets.QCheckBox("Offline EDL")
        self.offline_clips_checkbox.stateChanged.connect(self.update_fields_state)
        checkboxes_layout.addWidget(self.offline_clips_checkbox, 0, 3)

        self.edl_for_dailies_checkbox = QtWidgets.QCheckBox("Dailies EDL")
        self.edl_for_dailies_checkbox.stateChanged.connect(self.update_fields_state)
        checkboxes_layout.addWidget(self.edl_for_dailies_checkbox, 0, 4)

        layout.addLayout(checkboxes_layout)

        # === FPS ===
        fps_widget = QtWidgets.QWidget()
        fps_layout = QtWidgets.QHBoxLayout()
        fps_layout.setContentsMargins(0, 0, 0, 0)
        fps_layout.setSpacing(4)
        fps_label = QtWidgets.QLabel("FPS:")
        fps_label.setSizePolicy(QtWidgets.QSizePolicy.Fixed, QtWidgets.QSizePolicy.Fixed)

        self.fps_entry = QtWidgets.QLineEdit("24")
        self.fps_entry.setMaximumWidth(50)
        self.fps_entry.setSizePolicy(QtWidgets.QSizePolicy.Fixed, QtWidgets.QSizePolicy.Fixed)

        fps_layout.addWidget(fps_label)
        fps_layout.addWidget(self.fps_entry)
        fps_widget.setLayout(fps_layout)
        fps_widget.setSizePolicy(QtWidgets.QSizePolicy.Fixed, QtWidgets.QSizePolicy.Fixed)

        fps_center_layout = QtWidgets.QHBoxLayout()
        fps_center_layout.addStretch()
        fps_center_layout.addWidget(fps_widget)
        fps_center_layout.addStretch()

        layout.addLayout(fps_center_layout)

        # === Start button ===
        self.run_button = QtWidgets.QPushButton("Start")
        self.run_button.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Fixed)
        self.run_button.clicked.connect(self.run_script)
        layout.addWidget(self.run_button)



    def select_input_file(self):
        file_path, _ = QtWidgets.QFileDialog.getOpenFileName(self, "Select EDL file", "", "EDL files (*.edl)")
        if file_path:
            self.input_entry.setText(file_path)

    def select_output_file(self):
        if self.export_loc_checkbox.isChecked():
            ext = ".txt"
            filter = "Text files (*.txt)"
        else:
            ext = ".edl"
            filter = "EDL files (*.edl)"

        file_path, _ = QtWidgets.QFileDialog.getSaveFileName(self, "Save As", "", filter)
        if file_path:
            self.output_entry.setText(file_path)

    def update_fields_state(self):
        self.track_entry.setEnabled(self.set_markers_checkbox.isChecked())

        if self.set_markers_checkbox.isChecked():
            self.input_entry.setEnabled(False)
            self.output_entry.setEnabled(False)
        elif self.export_loc_checkbox.isChecked():
            self.input_entry.setEnabled(False)
            self.output_entry.setEnabled(True)
        else:
            self.input_entry.setEnabled(True)
            self.output_entry.setEnabled(True)


    def run_script(self):
        edl_path = self.input_entry.text()
        output_path = self.output_entry.text()
        export_loc = self.export_loc_checkbox.isChecked()
        set_markers = self.set_markers_checkbox.isChecked()
        fps = self.fps_entry.text()
        process_edl = self.edl_for_dailies_checkbox.isChecked() or self.offline_clips_checkbox.isChecked()

        if process_edl and (not edl_path or not output_path):
            QMessageBox.critical(self,"Ошибка", "Выберите файлы EDL!")
            return

        try:
            fps = int(fps)
        except ValueError:
            QMessageBox.critical(self,"Ошибка", "FPS должен быть числом!")
            return

        track_number = self.track_entry.text()
        try:
            track_number = int(track_number)
        except ValueError:
            QMessageBox.critical(self,"Ошибка", "Номер дорожки должен быть числом!")
            return

        try:
            self.resolve = dvr.scriptapp("Resolve")
            self.project = self.resolve.GetProjectManager().GetCurrentProject()
            self.timeline = self.project.GetCurrentTimeline()
            self.timeline_start_tc = self.timeline.GetStartFrame()

            if process_edl:
                self.process_edl(self.timeline, edl_path, output_path, fps)

            if set_markers:
                self.set_markers(self.timeline, track_number)

            if export_loc:
                self.export_locators_to_avid(output_path)

            QMessageBox.information(self, "Готово", "Обработка завершена!")
        except Exception as e:
            QMessageBox.critical(self, "Ошибка", f"Произошла ошибка: {e}")

    def get_markers(self, timeline_start_timecode): 
        '''
        Получение маркеров для работы других функций
        '''
        markers_list = []
        for timecode, name in self.timeline.GetMarkers().items():
            name = name['note'].strip()
            if name and re.search(self.pattern_short, name):
                timecode_marker = tc(self.fps_entry.text(), frames=timecode + timeline_start_timecode) + 1  
                markers_list.append((name, timecode_marker))
        return markers_list

    def set_markers(self, timeline, track_number):
        '''
        Установка маркеров с номерами полученными из оффлайн клипов на текущем таймлайне 
        '''
        clips = timeline.GetItemListInTrack('video', track_number)
        for clip in clips:
            if re.search(self.pattern_short, clip.GetName()):
                clip_name = clip.GetName()
                clip_start = int((clip.GetStart() + (clip.GetStart() + clip.GetDuration())) / 2) - timeline.GetStartFrame()
                timeline.AddMarker(clip_start, 'Blue', clip_name, "", 1, 'Renamed')


    def export_locators_to_avid(self, output_path):
        '''
        Формирование строк и экспорт локаторов для AVID в .txt
        '''
        markers_list = self.get_markers(self.timeline_start_tc)
        with open(output_path, "a", encoding='utf8') as output:
            for name, timecode in markers_list:
                # Используется спец табуляция для корректного импорта в AVID
                output_string = f'PGM	{str(timecode)}	V3	yellow	{name}'
                output.write(output_string + "\n")

    def process_edl(self, timeline, edl_path, output_path, fps):
        """
        Выводит EDL для дейлизов и EDL с оффлайн клипами
        """
        offline_clips = self.offline_clips_checkbox.isChecked()
        edl_for_dailies = self.edl_for_dailies_checkbox.isChecked()

        def parse_edl():
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

        parse_edl()

if __name__ == '__main__':
    app = QtWidgets.QApplication(sys.argv)
    window = EDLProcessorGUI()
    window.show()
    sys.exit(app.exec_())
