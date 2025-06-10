import DaVinciResolveScript as dvr
import re
from threading import Thread
import math
import openpyxl
from openpyxl.styles import Font, Alignment, PatternFill, Border, Side
from openpyxl.utils import get_column_letter
import pandas as pd
from PyQt5 import QtWidgets, QtCore
from PyQt5.QtWidgets import QMessageBox
from threading import Thread
import sys

class GUI(QtWidgets.QWidget):

    finished_signal = QtCore.pyqtSignal(str, str)
    error_signal = QtCore.pyqtSignal(str, str)

    def __init__(self):
        super().__init__()
        self.setWindowTitle('Set Shot Colors')
        self.setFixedSize(270, 130)
        self.clip_color_list = ['Orange', 'Yellow', 'Lime', 'Teal', 'Green', 'Purple', 'Navy',
                                'Apricot', 'Olive', 'Violet', 'Blue', 'Pink', 'Tan', 'Beige',
                                'Brown', 'Chocolate']

        self.init_ui()
        self.finished_signal.connect(self.show_message_box)
        self.error_signal.connect(self.show_message_box)

    def init_ui(self):
        layout = QtWidgets.QVBoxLayout()

        # FPS row
        fps_layout = QtWidgets.QHBoxLayout()
        fps_label = QtWidgets.QLabel('FPS:')
        self.fps_entry = QtWidgets.QLineEdit()
        self.fps_entry.setText("24")
        fps_layout.addWidget(fps_label)
        fps_layout.addWidget(self.fps_entry)

        # Выбор режима запуска
        self.mode_combo = QtWidgets.QComboBox()
        self.mode_combo.addItems([
            "Запустить оба (цвет + Excel)", 
            "Присвоить цвета и проектный FPS", 
            "Создать таблицу Excel"
        ])

        # Checkbox остаётся, если вдруг понадобится позже
        self.excel_checkbox = QtWidgets.QCheckBox("Создать Excel таблицу")
        self.excel_checkbox.setChecked(True)
        self.excel_checkbox.hide()  # Скрываем, заменено на combo box

        # Run button
        self.run_button = QtWidgets.QPushButton("Run Script")
        self.run_button.clicked.connect(self.on_run_clicked)

        # Добавляем в основной layout
        layout.addLayout(fps_layout)
        layout.addWidget(self.mode_combo)
        layout.addWidget(self.excel_checkbox)
        layout.addWidget(self.run_button)

        self.setLayout(layout)

    def show_message_box(self, title, message):
        if title == "Ошибка":
            QMessageBox.critical(self, title, message)
        else:
            QMessageBox.information(self, title, message)

    def on_run_clicked(self):
        self.run_button.setEnabled(False)
        Thread(target=self.run_script_wrapper).start()

    def run_script_wrapper(self):
        try:
            fps_value = self.fps_entry.text()
            mode_text = self.mode_combo.currentText()
            # Определяем по выбору, какие флаги передать
            if mode_text == "Запустить оба (цвет + Excel)":
                run_color = True
                run_excel = True
            elif mode_text == "Присвоить цвета и проектный FPS":
                run_color = True
                run_excel = False
            elif mode_text == "Создать таблицу Excel":
                run_color = False
                run_excel = True
            else:
                run_color = True
                run_excel = True

            self.run_da_vinci_script(fps_value, create_exel=run_excel, run_coloring=run_color)
        finally:
            self.run_button.setEnabled(True)

    def run_script(self):
        # Старая реализация, если требуется
        fps_value = self.fps_entry.text()
        self.run_da_vinci_script(fps_value, create_exel=True)

    def run_da_vinci_script(self, fps_value, create_exel, run_coloring=True):
        """Основная логика скрипта для DaVinci Resolve"""

        def get_spreadsheet_data(data):
            '''
            Функция вычисляет/получает данные для экспорта в EXEL таблицу 
            '''
            def export_to_exel(table_data_list):
                '''
                Функция экспортирует данные в EXEL таблицу
                '''
                COLOR_HEX_MAP = {
                    'Orange': "FFA500",
                    'Yellow': "FFFF99",
                    'Lime': "BFFF00",
                    'Teal': "008080",
                    'Green': "66CC66",
                    'Purple': "9370DB",
                    'Navy': "000080",
                    'Apricot': "FBCEB1",
                    'Olive': "808000",
                    'Violet': "EE82EE",
                    'Blue': "87CEEB",
                    'Pink': "FFC0CB",
                    'Tan': "D2B48C",
                    'Beige': "F5F5DC",
                    'Brown': "A52A2A",
                    'Chocolate': "D2691E"
                }

                def style_excel_table(ws, table_start_row, num_columns):
                    fill = PatternFill(start_color="D9EAD3", end_color="D9EAD3", fill_type="solid")
                    thin_border = Border(
                        left=Side(style='thin'),
                        right=Side(style='thin'),
                        top=Side(style='thin'),
                        bottom=Side(style='thin')
                    )

                    for row in ws.iter_rows(min_row=table_start_row, max_row=ws.max_row, min_col=1, max_col=num_columns):
                        for cell in row:
                            cell.fill = fill
                            cell.border = thin_border
                            cell.alignment = Alignment(horizontal="center", vertical="center")

                    for cell in ws[table_start_row]:
                        cell.font = Font(bold=True)

                    for col_idx in range(1, num_columns + 1):
                        col_letter = get_column_letter(col_idx)
                        max_len = max(
                            len(str(ws.cell(row=row, column=col_idx).value)) for row in range(table_start_row, ws.max_row + 1)
                        )
                        ws.column_dimensions[col_letter].width = max(12, max_len + 2)

                def color_rows_by_color_column(ws, color_column_name="Цвет", start_row=4):
                    color_col_idx = None
                    for col in range(1, ws.max_column + 1):
                        if ws.cell(row=3, column=col).value == color_column_name:
                            color_col_idx = col
                            break

                    if color_col_idx is None:
                        print("Колонка 'Цвет' не найдена.")
                        return

                    for row in range(start_row, ws.max_row + 1):
                        color_name = ws.cell(row=row, column=color_col_idx).value
                        hex_color = COLOR_HEX_MAP.get(color_name)
                        if hex_color:
                            fill = PatternFill(start_color=hex_color, end_color=hex_color, fill_type="solid")
                            cell = ws.cell(row=row, column=color_col_idx)
                            cell.fill = fill

                headers = ["Цвет", "Камера", "Оптика", "Исходное разрешение", "Разрешение выдачи", "Разрешение 1.5x", "Разрешение 2x", "Mxf для AVID", "Доп информация"]
                table_data_list.insert(0, headers)

                expected_columns = len(headers)
                for row in table_data_list[1:]:
                    while len(row) < expected_columns:
                        row.append("")

                df = pd.DataFrame(table_data_list[1:], columns=table_data_list[0])
                df.to_excel("Exel_project_document.xlsx", index=False, startrow=2)

                wb = openpyxl.load_workbook("Exel_project_document.xlsx")
                ws = wb.active

                num_columns = len(headers)

                ws.merge_cells(start_row=1, start_column=1, end_row=2, end_column=num_columns)
                header_cell = ws.cell(row=1, column=1)
                header_cell.value = "PROJECT NAME HERE"
                header_cell.font = Font(bold=True, size=14)
                header_cell.alignment = Alignment(horizontal="center", vertical="center")

                style_excel_table(ws, table_start_row=3, num_columns=num_columns)

                color_rows_by_color_column(ws, color_column_name="Цвет", start_row=4)

                # >>> ОБЪЕДИНЕНИЕ колонки "Доп информация"
                for col_idx in range(1, num_columns + 1):
                    if ws.cell(row=3, column=col_idx).value == "Доп информация":
                        info_col = col_idx
                        break
                else:
                    info_col = None

                if info_col:
                    start_row = 4
                    end_row = ws.max_row
                    ws.merge_cells(start_row=start_row, start_column=info_col, end_row=end_row, end_column=info_col)

                    merged_cell = ws.cell(row=start_row, column=info_col)
                    merged_cell.value = ""  # или можно вставить любую строку
                    merged_cell.alignment = Alignment(horizontal="center", vertical="center")
                    merged_cell.fill = PatternFill(start_color="D9EAD3", end_color="D9EAD3", fill_type="solid")
                    merged_cell.border = Border(
                        left=Side(style='thin'),
                        right=Side(style='thin'),
                        top=Side(style='thin'),
                        bottom=Side(style='thin')
                    )

                wb.save("Exel_project_document.xlsx")

            def rescale_resolution(width, height, aspect):
                '''
                Функция получает разрешение для стандартной 2к выдачи
                '''
                if aspect == "Square":
                    calculate_height = int(math.ceil(((height * target_resolution_width / width) / 2) * 2))
                    return (target_resolution_width, calculate_height)
                else:
                    calculate_width = int(math.ceil(((width * target_resolution_height / height) / 2) * 2))
                    return (calculate_width, target_resolution_height)
                
            def rescale_1_5_and_2_x(width, height, mult=None):
                '''
                Функция пересчитывает стандартное 2к разрешение в 1.5 кратноме и 2 кратное разрешение
                '''
                result_width = int(math.ceil((width * mult) / 2) * 2)
                result_height = int(math.ceil((height * mult) / 2) * 2)
                return result_width, result_height
            
            def rescale_avid(width, height):

                avid_target_resolution_width = 1920
                avid_target_resolution_height = 1080

                calculate_height = int(math.ceil(((height * avid_target_resolution_width / width) / 2) * 2))
                return (avid_target_resolution_width, calculate_height)
                
            
            # Целевое финальное разрешение
            target_resolution_height = 858
            target_resolution_width = 2048

            # Получили сортировку и цвета такие же как для расцветовки OCF
            data_zip = list(zip(self.clip_color_list, sorted(data.items(), key=lambda x: len(x[1]), reverse=True)))

            # Сбор всех возможных разрешений и данных для экспорта в таблицу
            table_data_list = []
            for color, (resolution_aspect, clips) in data_zip:
                resolution, aspect = resolution_aspect
                camera_resolution_width, camera_resolution_heigth = list(map(int, resolution.split("x")))
                first_latter_clip_name = list(set([clip.GetName()[0].upper() for clip in clips]))
                avid_scale_resolution_width, avid_scale_resolution_height = rescale_avid(camera_resolution_width, camera_resolution_heigth)
                scale_2k_resolution_width, scale_2k_resolution_height = rescale_resolution(camera_resolution_width, camera_resolution_heigth, aspect)
                scale_1_5_resolution_width, scale_1_5_resolution_height = rescale_1_5_and_2_x(scale_2k_resolution_width, scale_2k_resolution_height, mult=1.5)
                scale_2_resolution_width, scale_2_resolution_height = rescale_1_5_and_2_x(scale_2k_resolution_width, scale_2k_resolution_height, mult=2)
                if aspect == "Square":
                    aspect = "Сферическая"
                else:
                    aspect = "Анаморф"
                table_data_list.append([color,
                      first_latter_clip_name, 
                      aspect,
                      f"{camera_resolution_width}x{camera_resolution_heigth}", 
                      f"{scale_2k_resolution_width}x{scale_2k_resolution_height}",
                      f"{scale_1_5_resolution_width}x{scale_1_5_resolution_height}", 
                      f"{scale_2_resolution_width}x{scale_2_resolution_height}",
                      f"{avid_scale_resolution_width}x{avid_scale_resolution_height}"
                      ])
            export_to_exel(table_data_list)

        try:
            resolve = dvr.scriptapp("Resolve")
            project = resolve.GetProjectManager().GetCurrentProject()
            media_pool = project.GetMediaPool()

            target_bin = self.find_target_bin(media_pool)  # Ищем папку OCF
            if not target_bin:
                self.show_message_signal.emit("Ошибка", "Папка OCF не найдена.")
                return

            clips_dict = {}  # Словарь с данными разрешение: список клипов с таким разрешением
            spreadsheet_info_dict = {} # Словарь с данными (разрешение, аспект): список клипов с таким разрешением
            clips = self.get_clips_from_bin(target_bin)

            for clip in clips:
                if clip.GetName() != '' and clip.GetName().lower().endswith((".mxf", ".braw", ".arri", ".mov", ".r3d", ".mp4", ".dng", ".jpg", ".cine")):
                    # Находит анаморф, вычисляет ширину по аспекту
                    if clip.GetClipProperty('PAR') != 'Square' and clip.GetClipProperty('PAR'):
                        # Меняем FPS если не соответствует проектному и не выбрано создание таблицы
                        if clip.GetClipProperty("FPS") != fps_value and not create_exel:
                            clip.SetClipProperty("FPS", "24")

                        aspect = clip.GetClipProperty('PAR')
                        width, height = clip.GetClipProperty('Resolution').split('x')
                        resolution = "x".join([str(width), str(int((int(height) / float(aspect)) + (int(height) / float(aspect)) % 2))])
                        clips_dict.setdefault(resolution, []).append(clip)
                        spreadsheet_info_dict.setdefault((resolution, aspect), []).append(clip) # Данные для таблицы
                    else:
                        # Меняем FPS если не соответствует проектному и не выбрано создание таблицы
                        if clip.GetClipProperty("FPS") != fps_value  and not create_exel:
                            clip.SetClipProperty("FPS", "24")

                        aspect = clip.GetClipProperty('PAR')
                        clips_dict.setdefault(clip.GetClipProperty('Resolution'), []).append(clip)
                        spreadsheet_info_dict.setdefault((clip.GetClipProperty('Resolution'), aspect), []).append(clip) # Данные для таблицы

            # Опционально получаем данные для таблицы
            if create_exel:
                get_spreadsheet_data(spreadsheet_info_dict)

            # Опционально запускаем присваивание цвета клипам в медиапуле и устанавливаем проектный FPS
            if run_coloring:
                # Сортировка по количеству клипов в группе разрешения
                sorted_clip_list = list(zip(self.clip_color_list, {res: clips for res, clips in sorted(clips_dict.items(), key=lambda x: len(x[1]), reverse=True) if res != ""}))

                # Установка отдельного цвета на каждую группу разрешений
                for color, res in sorted_clip_list:
                    if res in clips_dict:
                        for clip in clips_dict[res]:
                            clip.SetClipColor(color)

            self.finished_signal.emit("Успех", f"Обработка закончена. Найдено {len(clips)} клипов в OCF и её подпапках.")

        except Exception as e:
            self.error_signal.emit("Ошибка", f"Произошла ошибка: {str(e)}")

    def get_clips_from_bin(self, bin):
        """Рекурсивно получает все клипы из папки и её подпапок."""
        clips = list(bin.GetClipList())  # Получаем клипы из текущей папки
        for sub_bin in bin.GetSubFolderList():  # Рекурсивно проходим по подпапкам
            clips.extend(self.get_clips_from_bin(sub_bin))
        return clips

    def find_target_bin(self, media_pool, target_name="OCF"):
        """Ищет папку с именем target_name в Media Pool."""
        root_bin = media_pool.GetRootFolder()
        return self.search_bin_recursive(root_bin, target_name)

    def search_bin_recursive(self, bin, target_name):
        """Рекурсивный поиск папки в Media Pool."""
        if re.search(target_name.lower(), bin.GetName().lower()):
            return bin
        for sub_bin in bin.GetSubFolderList():
            result = self.search_bin_recursive(sub_bin, target_name)
            if result:
                return result
        return None

if __name__ == "__main__":
    app = QtWidgets.QApplication(sys.argv)
    window = GUI()
    window.show()
    sys.exit(app.exec_())



