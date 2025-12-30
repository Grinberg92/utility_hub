from pathlib import Path
import openpyxl
from timecode import Timecode as tc
from datetime import datetime as dt, date as d
import sys
import os
from itertools import count
from PyQt5.QtWidgets import QHBoxLayout, QWidget
from PyQt5.QtWidgets import (
    QApplication, QWidget,  QPushButton, QVBoxLayout, QButtonGroup, QComboBox,
    QFileDialog, QLineEdit, QMessageBox, QFormLayout, QHBoxLayout, QRadioButton, QGroupBox, QLabel
)
from PyQt5.QtCore import Qt
from config.global_config import GLOBAL_CONFIG
from dvr_tools.css_style import apply_style

class ExcelDataerror(Exception):
    pass

def get_output_path(project: str, ext: str, report_name: str) -> str:
    """
    Получение пути к бекапу результата.
    """
    date = dt.now().strftime("%Y%m%d")

    output_path = (
        Path(
            {"win32": GLOBAL_CONFIG["paths"]["root_projects_win"],
            "darwin": GLOBAL_CONFIG["paths"]["root_projects_mac"]}[sys.platform]
        )
        / project
        / GLOBAL_CONFIG["output_folders"]["excel_to_locs"] / date
        / f"{report_name}_{date}.{ext}"
    )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    return output_path

class LocatorCreator:
    def __init__(self, excel_path, shift_timecode, sheet_name, 
                 shot_column, src_start_tc, rec_start_tc, duration, start_row, base_mode, project):
        self.excel_path = excel_path
        self.shift_timecode = shift_timecode
        self.sheet_name = sheet_name
        self.shot_column = shot_column
        self.src_start_tc = src_start_tc
        self.rec_start_tc = rec_start_tc
        self.duration = duration
        self.start_row = start_row
        self.base_mode = base_mode
        self.project = project

    def change_timecode(self, rec_in_tc: str) -> tc:
        """
        Делает сдвиг таймкода на указанное в GUI значение.
        """
        timecode = tc(24, rec_in_tc).frames
        return tc(24, frames=timecode + self.shift_timecode)
    
    def timecode_to_frame(self, fps: int, timecode: str) -> int:
        """
        Переводит таймкоды в значения фреймов.
        """
        return tc(fps, timecode).frames

    def frame_to_timecode(self, fps: int, frames: int) -> str:
        """
        Переводит фреймы в значения таймкодов.
        """
        return str(tc(fps, frames=frames))

    def create_output_edl(self, shot: dict, output) -> None:
        """
        Метод формирует аутпут файл в формате, пригодном для отображения оффлайн клипов в Resolve и AVID.

        :param output: Файловый объект.
        """
        str1 = (f"{shot['id']:05} {shot['shot_name']} "
                f"{'V'} {'C'} "
                f"{shot['src_in']} {shot['src_out']} "
                f"{shot['rec_in']} {shot['rec_out']}")
        str2 = f"\n* FROM CLIP NAME: {shot['shot_name']}\n"
        output.write(str1)
        output.write(str2)
    
    def create_loc(self, sheet) -> bool:
        """
        Парсинг данных из EDL для формирования маркеров.
        """
        try:
            raw_data = zip(sheet[self.rec_start_tc][self.start_row - 1:], 
                        sheet[self.shot_column][self.start_row -1:])
            # Фильтр на пустые строки
            shot_data = [(tc, sh) for tc, sh in raw_data if tc.value and sh.value]
        
            output_path = Path(self.excel_path).parent / f"{self.project}_AVID_LOCS_{dt.now().strftime('%Y%m%d')}.txt"
            backup_output_path = get_output_path(self.project, "txt", f"{self.project}_AVID_LOCS")

            with open(output_path, "w", encoding='utf8') as o, open(backup_output_path, "w", encoding='utf8') as ob:
                for timecode_data, shot_name_data in shot_data:
                    rec_in = timecode_data.value
                    shot_name = shot_name_data.value
                    timecode = self.change_timecode(rec_in)
                    # Используется спец табуляция для корректного импорта в AVID
                    output_string = f'PGM	{str(timecode)}	V3	yellow	{shot_name}'
                    o.write(output_string + "\n")
                    ob.write(output_string + "\n")

        except Exception as e:
            raise ExcelDataerror("Некорректные данные в Excel файле.\n" \
            "Проверьте, не попадает ли шапка таблицы в сборку данных.")

        return True

    def create_edl(self, sheet) -> bool:
        """
        Парсинг данных из EDL для формирования оффлайн клипов.
        """
        try:
            raw_data = zip(count(1), sheet[self.src_start_tc][self.start_row - 1:], sheet[self.rec_start_tc][self.start_row - 1:], 
                        sheet[self.duration][self.start_row - 1:], sheet[self.shot_column][self.start_row -1:])
            
            shot_data = [(id, src_tc, rec_tc, dur, shot) for id, src_tc, rec_tc, dur, shot in raw_data if src_tc.value and rec_tc.value and dur.value and shot.value]
        
            output_path = Path(self.excel_path).parent / f"{self.project}_offline_EDL_{dt.now().strftime('%Y%m%d')}.edl"
            backup_output_path = get_output_path(self.project, "edl", f"{self.project}_offline_EDL")

            tmp = {}

            with open(output_path, "w", encoding='utf8') as o, open(backup_output_path, "w", encoding='utf8') as ob:
                for data in shot_data:
                    id, src_in, rec_in, duration, shot_name = data
                    src_out = tc(24, src_in.value) + tc(24, frames=duration.value)
                    rec_out = tc(24, rec_in.value) + tc(24, frames=duration.value)

                    tmp["src_in"] = src_in.value
                    tmp["src_out"] = src_out
                    tmp["rec_in"] = rec_in.value
                    tmp["rec_out"] = rec_out
                    tmp["id"] = id
                    tmp["shot_name"] = shot_name.value

                    self.create_output_edl(tmp, o)
                    self.create_output_edl(tmp, ob)

        except Exception as e:
            raise ExcelDataerror("Некорректные данные в Excel файле.\n" \
            "Проверьте, не попадает ли шапка таблицы в сборку данных.")
        
        return True
    
    def run(self) -> bool:
        """
        Получение данных о столбцах с таймкодами и шотами и дальнейшая конвертация в локаторы для Avid.
        """
        workbook = openpyxl.load_workbook(self.excel_path)
        sheet = workbook[self.sheet_name]

        create_loc_success = self.create_loc(sheet)
        if not create_loc_success:
            return False
        
        if not self.base_mode:
            create_edl_success = self.create_edl(sheet)
            if not create_edl_success:
                return False
            
        return True
            
class LocatorGUI(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Locators&EDL from EXCEL")
        self.resize(500, 280)
        self.setWindowFlag(Qt.WindowStaysOnTopHint)

        # UI elements
        self.fps_lbl = QLabel("FPS:")
        self.fps = QLineEdit("24")
        self.fps.setMaximumWidth(40)
        
        self.base_mode = QRadioButton("")
        self.base_mode.setChecked(True)
        self.base_mode.toggled.connect(self.update_fields_state)
        self.adv_mode = QRadioButton("")
        self.adv_mode.toggled.connect(self.update_fields_state)

        self.excel_input = QLineEdit()
        self.output_input = QLineEdit()
        self.shift_input = QLineEdit("15")

        self.sheet_name_col = QLineEdit("Sheet1")
        self.shot_column_col = QLineEdit("")
        self.src_start_tc_col = QLineEdit("")
        self.rec_start_tc_col = QLineEdit("")
        self.duration_col = QLineEdit("")
        self.start_row_input = QLineEdit("1")
        self.empty = QLabel()

        # Buttons
        self.browse_excel_btn = QPushButton("Browse")
        self.browse_output_btn = QPushButton("Browse")
        self.create_btn = QPushButton("Create Locators")

        self.setup_ui()

    def setup_ui(self):
        layout = QVBoxLayout()

        # Project
        project_layout = QHBoxLayout()
        self.project_menu = QComboBox()
        self.project_menu.setMinimumWidth(200)
        self.project_menu.addItems(self.get_project())
        project_layout.addStretch()
        project_layout.addWidget(self.fps_lbl)
        project_layout.addWidget(self.fps)
        project_layout.addWidget(self.project_menu)
        project_layout.addStretch()
        layout.addLayout(project_layout)

        # Mode group
        mode_group = QGroupBox("Breakdown")
        mode_group.setMinimumHeight(70)
        mode_layout = QHBoxLayout()

        self.mode_group = QButtonGroup(self)
        self.mode_group.addButton(self.base_mode)
        self.mode_group.addButton(self.adv_mode)

        base_mode_layout = QVBoxLayout()
        base_mode_label =QLabel("Base type")
        base_mode_label.setAlignment(Qt.AlignHCenter)
        base_mode_layout.addWidget(self.base_mode, alignment=Qt.AlignHCenter)
        base_mode_layout.addWidget(base_mode_label)

        adv_mode_layout = QVBoxLayout()
        adv_mode_label =QLabel("Advanced type")
        adv_mode_label.setAlignment(Qt.AlignHCenter)
        adv_mode_layout.addWidget(self.adv_mode, alignment=Qt.AlignHCenter)
        adv_mode_layout.addWidget(adv_mode_label)

        mode_layout.addStretch()
        mode_layout.addLayout(base_mode_layout)
        mode_layout.addSpacing(100)
        mode_layout.addLayout(adv_mode_layout)
        mode_layout.addStretch()

        mode_group.setLayout(mode_layout)
        layout.addWidget(mode_group)

        # Excel group
        excel_data_group = QGroupBox("Excel Data")
        excel_data_layout = QFormLayout()
        excel_data_layout.setLabelAlignment(Qt.AlignLeft)
        excel_data_layout.setFormAlignment(Qt.AlignTop)

        # Settings group
        settings_group = QGroupBox("Settings")
        settings_layout = QFormLayout()
        settings_layout.setLabelAlignment(Qt.AlignLeft)
        settings_layout.setFormAlignment(Qt.AlignTop)

        # Width fields
        for line_edit in [
            self.excel_input, self.output_input, self.shift_input,
            self.sheet_name_col, self.shot_column_col,
            self.src_start_tc_col, self.rec_start_tc_col, self.duration_col, self.start_row_input
        ]:
            line_edit.setFixedWidth(250)

        # Add 
        excel_data_layout.addRow("Excel file:", self._with_button(self.excel_input, self.browse_excel_btn))
        excel_data_layout.addRow("Sheet name:", self.sheet_name_col)
        excel_data_layout.addRow("Shot:", self.shot_column_col)
        excel_data_layout.addRow("Rec start timecode:", self.rec_start_tc_col)
        excel_data_layout.addRow("Src start timecode:", self.src_start_tc_col)
        excel_data_layout.addRow("Duration:", self.duration_col)

        settings_layout.addRow("Shift timecode:      ", self.shift_input),
        settings_layout.addRow("Start row:      ", self.start_row_input)

        excel_data_group.setLayout(excel_data_layout)
        layout.addWidget(excel_data_group)
        settings_group.setLayout(settings_layout)
        layout.addWidget(settings_group)

        # Start
        layout.addWidget(self.create_btn)

        self.setLayout(layout)

        # Signals
        self.browse_excel_btn.clicked.connect(self.select_excel_file)
        self.create_btn.clicked.connect(self.run_logic)

        self.update_fields_state()

    def _with_button(self, line_edit, button):
        """
        Обертка для LineEdit + Browse Button
        """
        container = QWidget()
        hbox = QHBoxLayout(container)
        hbox.setContentsMargins(0, 0, 0, 0)
        hbox.addWidget(line_edit)
        hbox.addWidget(button)
        return container
    
    def get_project(self):
        """
        Метод получает список проектов из корневого каталога.
        """
        project_path = {"win32": GLOBAL_CONFIG["paths"]["root_projects_win"], 
            "darwin": GLOBAL_CONFIG["paths"]["root_projects_mac"]}[sys.platform] 
        if os.path.exists(project_path):
            projects_list = sorted([i for i in os.listdir(Path(project_path)) if os.path.isdir(Path(project_path) / i)])
            projects_list.insert(0, "Select Project")
            return projects_list
        else:
            QMessageBox.critical(self, "Error", "Путь к папке проекта не обнаружен")
            return
                
    def update_fields_state(self):
        """
        Изменение статуса состояния полей.
        """
        self.src_start_tc_col.setEnabled(not self.base_mode.isChecked())
        self.duration_col.setEnabled(not self.base_mode.isChecked())

    def select_excel_file(self):
        file, _ = QFileDialog.getOpenFileName(self, "Select Excel File", "", "Excel Files (*.xlsx *.xls)")
        if file:
            self.excel_input.setText(file)

    def run_logic(self):
        excel_path = self.excel_input.text().strip()
        sheet_name = self.sheet_name_col.text().strip()
        shot_column = self.shot_column_col.text().strip().upper()
        rec_start_tc = self.rec_start_tc_col.text().strip().upper()
        base_mode = self.base_mode.isChecked()
        project = self.project_menu.currentText() 
        src_start_tc = None
        duration = None

        if not base_mode:
            src_start_tc = self.src_start_tc_col.text().strip().upper()
            duration = self.duration_col.text().strip().upper()

        if project == "Select Project":
            QMessageBox.warning(self, "Warning", "Выберите проект.")
            return

        try:
            shift = int(self.shift_input.text())
            start_row = int(self.start_row_input.text().strip())

        except ValueError:
            QMessageBox.critical(self, "Error", "Значения должны быть положительными числами.")
            return

        if not excel_path:
            QMessageBox.warning(self, "Warning", "Укажите Excel файл для чтения.")
            return

        if not os.path.exists(excel_path):
            QMessageBox.warning(self, "Warning", "Некорректный путь к Excel файлу.")
            return

        if not sheet_name:
            QMessageBox.warning(self, "Warning", "Не указан лист Excel файла.")
            return                

        if not shot_column:
            QMessageBox.warning(self, "Warning", "Не указана колонка с именами шотов.")
            return                

        if not rec_start_tc:
            QMessageBox.warning(self, "Warning", "Не указан рекорд таймкод.")
            return                
        
        if not base_mode:

            if not src_start_tc:
                QMessageBox.warning(self, "Warning", "Не указан стартовый таймкод исходника.")
                return                
            if not duration:
                QMessageBox.warning(self, "Warning", "Не указан дюрейшн исходника.")
                return

        try:
            logic = LocatorCreator(excel_path, shift, sheet_name, shot_column, 
                                   src_start_tc, rec_start_tc, duration, 
                                   start_row, base_mode, project)
            
            success = logic.run()
            if success:
                QMessageBox.information(self, "Success", "Процесс успешно завершен.")  

        except ExcelDataerror as e:
            QMessageBox.critical(self, "Error", f"{e}")

        
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Ошибка:\n{e}")

if __name__ == "__main__":
    app = QApplication(sys.argv)
    apply_style(app)
    window = LocatorGUI()
    window.show()
    sys.exit(app.exec_())
