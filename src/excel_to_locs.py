import openpyxl
from timecode import Timecode as tc
import sys
from PyQt5.QtWidgets import (
    QApplication, QWidget,  QPushButton, QVBoxLayout,
    QFileDialog, QLineEdit, QMessageBox, QFormLayout
)
from PyQt5.QtCore import Qt
from dvr_tools.css_style import apply_style

class LocatorCreator:
    def __init__(self, excel_path, output_path, shift_timecode, sheet_name, shot_column, timecode_column, start_row):
        self.excel_path = excel_path
        self.output_path = output_path
        self.shift_timecode = shift_timecode
        self.sheet_name = sheet_name
        self.shot_column = shot_column
        self.timecode_column = timecode_column
        self.start_row = start_row

    def change_timecode(self, excel_timecode):
        """
        Делает сдвиг таймкода на указанное в GUI значение.
        """
        timecode = tc(24, excel_timecode).frames
        return tc(24, frames=timecode + self.shift_timecode)
    
    def run(self):
        """
        Получение данных о столбцах с таймкодами и шотами и дальнейшая конвертация в локаторы для Avid.
        """
        workbook = openpyxl.load_workbook(self.excel_path)
        sheet = workbook[self.sheet_name]

        raw_data = zip(sheet[self.timecode_column][self.start_row:], 
                    sheet[self.shot_column][self.start_row:])
        
        # Фильтр на пустые строки
        shot_data = [(tc, sh) for tc, sh in raw_data if tc.value and sh.value]

        with open(self.output_path, "a", encoding='utf8') as output:
            for timecode_data, shot_name_data in shot_data:
                timecode = timecode_data.value
                shot_name = shot_name_data.value
                if self.shift_timecode > 0:
                    timecode = self.change_timecode(timecode)
                # Используется спец табуляция для корректного импорта в AVID
                output_string = f'PGM	{str(timecode)}	V3	yellow	{shot_name}'
                output.write(output_string + "\n")

class LocatorGUI(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Locators from EXCEL")
        self.setFixedSize(500, 280)
        self.setWindowFlag(Qt.WindowStaysOnTopHint)

        # UI elements
        self.excel_input = QLineEdit()
        self.output_input = QLineEdit()
        self.shift_input = QLineEdit("15")

        self.sheet_name_input = QLineEdit("")
        self.shot_column_input = QLineEdit("")
        self.timecode_column_input = QLineEdit("")
        self.start_row_input = QLineEdit("0")

        # Кнопки
        self.browse_excel_btn = QPushButton("Browse")
        self.browse_output_btn = QPushButton("Browse")
        self.create_btn = QPushButton("Create Locators")

        self.setup_ui()

    def setup_ui(self):
        layout = QVBoxLayout()

        # Используем FormLayout для аккуратной сетки
        form_layout = QFormLayout()
        form_layout.setLabelAlignment(Qt.AlignRight)
        form_layout.setFormAlignment(Qt.AlignTop)

        # Ширина для всех полей
        for line_edit in [
            self.excel_input, self.output_input, self.shift_input,
            self.sheet_name_input, self.shot_column_input,
            self.timecode_column_input, self.start_row_input
        ]:
            line_edit.setFixedWidth(250)

        # Добавляем поля в форму
        form_layout.addRow("Excel file:", self._with_button(self.excel_input, self.browse_excel_btn))
        form_layout.addRow("Output path:", self._with_button(self.output_input, self.browse_output_btn))
        form_layout.addRow("Shift timecode:", self.shift_input)
        form_layout.addRow("Sheet name:", self.sheet_name_input)
        form_layout.addRow("Shot column:", self.shot_column_input)
        form_layout.addRow("Timecode column:", self.timecode_column_input)
        form_layout.addRow("Start row:", self.start_row_input)

        layout.addLayout(form_layout)

        # Кнопка запуска по центру
        layout.addWidget(self.create_btn)

        self.setLayout(layout)

        # Signals
        self.browse_excel_btn.clicked.connect(self.select_excel_file)
        self.browse_output_btn.clicked.connect(self.select_output_file)
        self.create_btn.clicked.connect(self.run_logic)

    def _with_button(self, line_edit, button):
        """
        Обертка для LineEdit + Browse Button
        """
        from PyQt5.QtWidgets import QHBoxLayout, QWidget
        container = QWidget()
        hbox = QHBoxLayout(container)
        hbox.setContentsMargins(0, 0, 0, 0)
        hbox.addWidget(line_edit)
        hbox.addWidget(button)
        return container

    def select_excel_file(self):
        file, _ = QFileDialog.getOpenFileName(self, "Select Excel File", "", "Excel Files (*.xlsx *.xls)")
        if file:
            self.excel_input.setText(file)

    def select_output_file(self):
        file, _ = QFileDialog.getSaveFileName(self, "Select Output File", "", "Text Files (*.txt)")
        if file:
            self.output_input.setText(file)

    def run_logic(self):
        excel_path = self.excel_input.text().strip()
        output_path = self.output_input.text().strip()
        sheet_name = self.sheet_name_input.text().strip()
        shot_column = self.shot_column_input.text().strip().upper()
        timecode_column = self.timecode_column_input.text().strip().upper()

        try:
            start_row = int(self.start_row_input.text().strip())
            shift = int(self.shift_input.text())

        except ValueError:
            QMessageBox.critical(self, "Error", "Shift timecode and Start row must be integers.")
            return

        if not excel_path or not output_path:
            QMessageBox.warning(self, "Missing Info", "Please select both input and output files.")
            return

        try:
            logic = LocatorCreator(excel_path, output_path, shift, sheet_name, shot_column, timecode_column, start_row)
            
            logic.run()
            QMessageBox.information(self, "Success", "Locators created successfully.")
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to create locators:\n{str(e)}")

if __name__ == "__main__":
    app = QApplication(sys.argv)
    apply_style(app)
    window = LocatorGUI()
    window.show()
    sys.exit(app.exec_())
