import sys
from collections import Counter
import DaVinciResolveScript 
from datetime import date
import os
import openpyxl
import re
import bisect
import csv
from itertools import count
from PyQt5 import QtWidgets, QtCore
from PyQt5.QtWidgets import (QFileDialog, QLabel, QLineEdit, QPushButton, QRadioButton, 
                             QVBoxLayout, QHBoxLayout, QGroupBox, QTextEdit, QComboBox, 
                             QWidget, QMessageBox, QCheckBox, QButtonGroup)
from PyQt5.QtGui import QFont
from dvr_tools.logger_config import get_logger
from dvr_tools.css_style import apply_style

logger = get_logger(__file__)

class VersionCheckerGUI(QtWidgets.QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Check Shot Version")
        self.resize(550, 500)
        self.setWindowFlags(QtCore.Qt.WindowStaysOnTopHint)

        self.result_list = {}
        self.result_list_except = {}
        self.failed_paths = []
        self.failed_names = set()
        self.rows = 0

        self.file_path = QLineEdit()
        self.result_path = QLineEdit()
        self.start_track = QLineEdit("2")
        self.end_track = QLineEdit("10")
        self.sheet_name = QLineEdit("Sheet1")
        self.reel_name = QLineEdit("0")
        self.column_reel = QLineEdit("B")
        self.column_letter = QLineEdit("H")

        self.file_type_group_rb = QButtonGroup()
        self.file_type_xlsx = QRadioButton("excel")
        self.file_type_csv = QRadioButton(".csv from PL")
        self.file_type_group_rb.addButton(self.file_type_xlsx)
        self.file_type_group_rb.addButton(self.file_type_csv)
        self.file_type_xlsx.setChecked(True)

        self.mode_group_rb = QButtonGroup()
        self.global_mode =  QRadioButton('Global')
        self.local_mode =  QRadioButton('Local')
        self.mode_group_rb.addButton(self.file_type_xlsx)
        self.mode_group_rb.addButton(self.file_type_csv)
        self.local_mode.setChecked(True)

        self.failed_paths_text = QTextEdit()
        self.failed_paths_text.setPlaceholderText("Здесь будут показаны имена шотов, которые не удалось определить.")

        self.result_label = QLabel("Checked 0 from 0 shots")
        bold_font = QFont()
        bold_font.setBold(True)
        self.result_label.setFont(bold_font)

        self.init_ui()
        self.update_fields_state()

    def init_ui(self):
        layout = QVBoxLayout(self)

        layout.addWidget(self.failed_paths_text)

        # === Input file ===
        file_layout = QHBoxLayout()
        file_layout.addWidget(QLabel("Choose input file:"))
        file_layout.addSpacing(27)
        file_layout.addWidget(self.file_path)
        choose_file_btn = QPushButton("Choose")
        choose_file_btn.clicked.connect(self.select_file)
        file_layout.addWidget(choose_file_btn)
        layout.addLayout(file_layout)

        # === Output path ===
        output_layout = QHBoxLayout()
        output_layout.addWidget(QLabel("Choose output path:"))
        output_layout.addSpacing(10)
        output_layout.addWidget(self.result_path)
        choose_output_btn = QPushButton("Choose")
        choose_output_btn.clicked.connect(self.select_result_path)
        output_layout.addWidget(choose_output_btn)
        layout.addLayout(output_layout)

        # === File type radio buttons ===

        file_type_group = QGroupBox("Source")
        file_type_group.setFixedWidth(300)
        file_type_group.setFixedHeight(50)
        filetype_layout = QHBoxLayout()
        filetype_layout.addStretch()
        self.file_type_xlsx.toggled.connect(self.update_fields_state)
        filetype_layout.addWidget(self.file_type_xlsx)
        filetype_layout.addSpacing(80)
        filetype_layout.addWidget(self.file_type_csv)
        filetype_layout.addStretch()
        file_type_group.setLayout(filetype_layout)
        layout.addWidget(file_type_group, alignment=QtCore.Qt.AlignCenter)

        mode_group = QGroupBox("Mode")
        mode_group.setFixedWidth(300)
        mode_group.setFixedHeight(50)
        mode_layout = QHBoxLayout()
        mode_layout.addStretch()
        mode_layout.addWidget(self.global_mode)
        mode_layout.addSpacing(80)
        mode_layout.addWidget(self.local_mode)
        mode_layout.addStretch()
        mode_group.setLayout(mode_layout)
        layout.addWidget(mode_group, alignment=QtCore.Qt.AlignCenter)

        # === GroupBox Section ===
        groupbox_layout = QHBoxLayout()
    
        resolve_group = QGroupBox("Resolve Data")
        resolve_layout = QHBoxLayout()
        resolve_group.setFixedHeight(70)
        resolve_layout.addWidget(QLabel("Reel:"))
        resolve_layout.addWidget(self.reel_name)
        resolve_layout.addSpacing(10)
        resolve_layout.addWidget(QLabel("Track In:"))
        resolve_layout.addWidget(self.start_track)
        resolve_layout.addSpacing(10)
        resolve_layout.addWidget(QLabel("Out:"))
        resolve_layout.addWidget(self.end_track)
        resolve_group.setLayout(resolve_layout)

        excel_group = QGroupBox("Excel Data")
        excel_layout = QHBoxLayout()
        self.sheet_name.setFixedWidth(80)
        self.column_reel.setFixedWidth(40)
        self.column_letter.setFixedWidth(40)
        excel_layout.addWidget(QLabel("Sheet:"))
        excel_layout.addWidget(self.sheet_name)
        excel_layout.addSpacing(10)
        excel_layout.addWidget(QLabel("Reel:"))
        excel_layout.addWidget(self.column_reel)
        excel_layout.addSpacing(10)
        excel_layout.addWidget(QLabel("Shots:"))
        excel_layout.addWidget(self.column_letter)
        excel_group.setLayout(excel_layout)

        groupbox_layout.addWidget(resolve_group)
        groupbox_layout.addWidget(excel_group)
        layout.addLayout(groupbox_layout)

        # Result info
        label_layout = QHBoxLayout()
        label_layout.addStretch()
        label_layout.addWidget(self.result_label)
        label_layout.addStretch()
        layout.addLayout(label_layout)

        self.start_button = QPushButton("Start")
        self.start_button.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Fixed)
        self.start_button.setFixedHeight(30)
        self.start_button.clicked.connect(self.run_script)
        layout.addWidget(self.start_button)

    def select_file(self):
        path, _ = QFileDialog.getOpenFileName(self, "Choose File", "", "Excel or CSV Files (*.xlsx *.csv)")
        if path:
            self.file_path.setText(path)

    def select_result_path(self):
        folder = QFileDialog.getExistingDirectory(self, "Choose Output Folder")
        if folder:
            self.result_path.setText(folder)

    def update_fields_state(self):

        enable_excel = self.file_type_xlsx.isChecked()
        self.sheet_name.setEnabled(enable_excel)
        self.column_reel.setEnabled(enable_excel)
        self.column_letter.setEnabled(enable_excel)

    def update_result_label(self):
        len_res_list = len([j for i in self.result_list.values() for j in i])
        self.result_label.setText(f"Проверено {len_res_list + len(self.failed_names)} шотов из {self.rows or 0}")


    def update_failed_paths(self):
        integers = count(1)
        num_failed_paths = [f'{number}) {string_}' for number, string_ in zip(integers, self.failed_paths)]
        self.failed_paths_text.setPlainText("\n".join(num_failed_paths))

    def on_error(self, message):
        QMessageBox.critical(self, "Ошибка", message)
        logger.exception(message)

    def on_warning(self, message):
        QMessageBox.warning(self, "Предупреждение", message)
        logger.warning(message)

    def on_info(self, message):
        QMessageBox.information(self, "Инфо", message)
        logger.info(message)
    
    
    def run_script(self):
        
        # Проверка ввода для start_track и end_track
        try:
            start_track = int(self.start_track.text())
            end_track = int(self.end_track.text())
        except ValueError:
            self.on_warning("Диапазон треков должен быть числом!")
            return

        try:
            resolve_reel = int(self.reel_name.text())
        except ValueError:
            self.on_warning("Рил должен быть числом!")
            return

        # Инициализация Resolve
        try:
            resolve = DaVinciResolveScript.scriptapp("Resolve")
            project_manager = resolve.GetProjectManager()
            project = project_manager.GetCurrentProject()
            media_pool = project.GetMediaPool()
            cur_bin = media_pool.GetCurrentFolder()
            clip_list = cur_bin.GetClipList()
            timeline = project.GetCurrentTimeline()
        except Exception as e:
            self.on_error(f"Ошибка инициализации Resolve: {e}")
            return

        # Паттерны на поиск имен шотов
        pattern_short = r'(?<!\d)(?:..._)?\d{3,4}[a-zA-Z]?_\d{1,4}(?!\d)' # Короткое имя 001_0010 или prk_001_0010
        pattern_long = r'(?<!\d)(?:[a-zA-Z]+_)*\d{3,4}[a-zA-Z]?_\d{1,4}(?:_[a-zA-Z]+)*?_v?\d+\w*(?!\d)'  # Имя с версией 001_0010_comp_v001 или prk_001_0010_comp_v001
        pattern_shot_number = r'\d{3,4}[a-zA-Z]?_\d+' # Чистый номер без префиксов, если таковые есть 001_0010
        pattern_real_shot = r'(.+_)?\d{1,4}[a-zA-Z]?_\d{1,4}_.+' # Легкая маска, для отбрасывания .exr файлов которые не относятся к шотам. Например титры.

        logger.debug("\n".join(("SetUp:", f"Choose input file: {self.file_path.text()}", f"Choose output path: {self.result_path.text()}", 
                                f"Source-exel: {self.file_type_xlsx.isChecked()}",f"Source-csv: {self.file_type_csv.isChecked()}", 
                                f"Resolve-reel: {self.reel_name.text()}", f"Track in: {self.start_track.text()}", f"Track Out: {self.end_track.text()}", 
                                f"Sheet: {self.sheet_name.text()}", f"Excel-reel: {self.column_reel.text()}", f"Shots: {self.column_letter.text()}")))
        
        def get_timeline_items(start_track: int, end_track: int, timeline) -> list:
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

        def is_dublicate(check_list: list)-> None:

            """Функция проверяет входящий список на наличие дубликатов"""

            find_dublicates = dict(filter(lambda x: x[1] >= 2, Counter(check_list).items()))
            if find_dublicates:
                for shot, _ in find_dublicates.items():
                    self.rows -= 1
                    self.failed_paths.append(f"Найден дубликат шота {shot}")

        def read_column_from_excel()-> list: 

            '''Функция получает данные из .xlsx файла'''

            dublicate_shot = []
            try: 
                # Открываем файл Excel 
                workbook = openpyxl.load_workbook(self.file_path.text()) 
                sheet = workbook[self.sheet_name.text()]

                # Проверка по конкретному рилу из контрольного списка
                if int(self.reel_name.text()) != 0:
                    reel_shot = list(zip(sheet[self.column_reel.text()], sheet[self.column_letter.text()]))
                    column_data = {}
                    # Считываем данные из списка кортежей (рил, шот)
                    for reel, shot in reel_shot:
                        if reel.value is not None:
                            if re.search(self.reel_name.text(), reel.value):
                                if shot.value is not None and shot.value != '':
                                    self.rows += 1
                                    try:
                                        column_data[re.search(pattern_short, shot.value).group(0).lower()] = re.search(pattern_long, shot.value).group(0).lower()
                                        dublicate_shot.append(re.search(pattern_short, shot.value).group(0).lower())
                                    except AttributeError:
                                        self.failed_paths.append(f"Имя {shot.value} не опознано")
                                        self.failed_names.add(f"Имя {shot.value} не опознано")

                # Проверка всего контрольного списка
                else:
                    column_data = {}
                    # Считываем данные из указанного столбца 
                    for shot in sheet[self.column_letter.text()]:
                        if shot.value is not None and shot.value != '':
                            self.rows += 1
                            try:
                                column_data[re.search(pattern_short, shot.value).group(0).lower()] = re.search(pattern_long, shot.value).group(0).lower()
                                dublicate_shot.append(re.search(pattern_short, shot.value).group(0).lower())
                            except AttributeError:
                                self.failed_paths.append(f"Имя {shot.value} не опознано")
                                self.failed_names.add(f"Имя {shot.value} не опознано")

                is_dublicate(dublicate_shot)
                return column_data 
            except Exception as e: 
                self.on_error(f"Не удалось получить данные из Excel документа: {e}")
                return []

        def read_column_from_csv()-> list:

            '''Функция получает данные из .csv файла'''

            dublicate_shot = []
            try:
            # Открываем csv с данными по плейлисту из Шотгана и получаем словарь с парами ключ: значение. Имя шота с версией и имя шота без версии. {001_0010_comp_v001 : 001_0010, ...} 
                with open(self.file_path.text(), encoding='utf-8') as f:
                    file = csv.DictReader(f, delimiter=',')
                    
                    # Проверка всего контрольного списка
                    if int(self.reel_name.text()) != 0:
                        play_list = {}
                        for i in file:
                            self.rows += 1
                            if not i['Path to EXR'] and not i['Path to Frames'] and re.search(self.reel_name.text(), i['Reel']): # Если нет адресов
                                self.failed_paths.append(f"Отсутствуют данные о шоте {i['Entity']}")
                                self.failed_names.add(i['Entity'])
                                continue
                            if i['Path to EXR'] and re.search(self.reel_name.text(), i['Reel']): # Ищется в первую очередь
                                try:
                                    play_list[re.search(pattern_short, i['Path to EXR']).group(0)] = re.search(pattern_long, i['Path to EXR']).group(0)
                                    dublicate_shot.append(re.search(pattern_short, i['Path to EXR']).group(0))
                                except AttributeError:
                                    pass # Ничего не делать. Переходим к проверке Path to Frames
                            if not i['Path to EXR'] and re.search(self.reel_name.text(), i['Reel']):   # Если нет хайреза
                                try:
                                    play_list[re.search(pattern_short, i['Path to Frames']).group(0)] = re.search(pattern_long, i['Path to Frames']).group(0)
                                    dublicate_shot.append(re.search(pattern_short, i['Path to EXR']).group(0))
                                except AttributeError:
                                    self.failed_paths.append(f"Имя {i['Path to Frames']} не опознано")
                                    self.failed_names.add(i['Entity'])
                            
                    else:
                        play_list = {}
                        for i in file:
                            self.rows += 1
                            if not i['Path to EXR'] and not i['Path to Frames']: # Если нет адресов
                                self.failed_paths.append(f"Отсутствуют данные о шоте {i['Entity']}")
                                self.failed_names.add(i['Entity'])
                                continue
                            if i['Path to EXR']: # Ищется в первую очередь
                                try:
                                    play_list[re.search(pattern_short, i['Path to EXR']).group(0)] = re.search(pattern_long, i['Path to EXR']).group(0)
                                    dublicate_shot.append(re.search(pattern_short, i['Path to EXR']).group(0))
                                except AttributeError:
                                    pass # Ничего не делать. Переходим к проверке Path to Frames
                            if not i['Path to EXR']:   # Если нет хайреза
                                try:
                                    play_list[re.search(pattern_short, i['Path to Frames']).group(0)] = re.search(pattern_long, i['Path to Frames']).group(0)
                                    dublicate_shot.append(re.search(pattern_short, i['Path to Frames']).group(0))
                                except AttributeError:
                                    self.failed_paths.append(f"Имя {i['Path to Frames']} не опознано")
                                    self.failed_names.add(i['Entity'])
                is_dublicate(dublicate_shot)
                return play_list
            except Exception as e: 
                self.on_error(f"Не удалось получить данные из CSV документа: {e}")
                return []
            
        def export_result(result_path)-> bool:

            """Функция экспорта результата в .txt"""

            try:
                with open(result_path, 'a', encoding='utf-8') as o:
                    o.write(self.reel_name.text() + " РИЛ" + "\n")
                    full_result_list = self.result_list_except | self.result_list
                    for key, value in full_result_list.items():
                        o.write("\n" + key + "\n\n") 
                        for item in value:
                            o.write(item + "\n")
                    o.write("_"* 80 + '\n\n')
                return True
            except:
                return None

        def is_compare(all_cg_items, markers_list, result_path)-> None:

            """Функция с основной логикой"""

            # Если тип файла .xlsx данные берутся из функции read_column_from_excel, в противном случае данные берутся из csv из функции read_column_from_csv
            play_list = read_column_from_excel() if self.file_type_xlsx.isChecked() else read_column_from_csv()
            logger.debug(f"Данные плейлиста полученные из контрольного документа:\n{play_list}")

            if not play_list:
                return True

            # Проходимся циклом по списку шотов из таймлайна. Получаем (имя шота без версии: [имя шота(ов) c версией]).
            timeline_items = {}
            for item in all_cg_items:
                if item.GetName().endswith(('.exr', '.mov', '.jpg')) and re.search(pattern_real_shot, item.GetName()): # С таймлайна берутся только .exr которые являются шотами
                    name_item_long = re.search(pattern_long, item.GetName()).group(0).lower() 
                    name_item_short = re.search(pattern_short, item.GetName()).group(0).lower() 
                    timeline_items.setdefault(name_item_short, []).append(name_item_long)

            logger.debug(f"Данные собранные с таймлайна (имя шота без версии: [имя шота(ов) c версией]):\n{timeline_items}")
            # Сверяем данные из контрольного списк с данными из таймлайна
            for pl_shot in play_list:
                if pl_shot in timeline_items :
                    if play_list[pl_shot] in timeline_items[pl_shot]:
                        self.result_list.setdefault("Стоит актуальная версия шота:", []).append(play_list[pl_shot])
                    else:
                        self.result_list.setdefault("Текущая версия шота не актуальна:", []).append(f"Версия в сверке - {play_list[pl_shot]}. На таймлайне присутствуют версии: {timeline_items[pl_shot]}")
                else:
                    self.result_list.setdefault("Шот есть в контрольном списке, но нет на таймлайне:", []).append(play_list[pl_shot])

            # Используются только в случае выбора глобального режима
            if not self.local_mode:
                # Сверяем данные из таймлайна с данными из контрольного списка
                for tmln_shot in timeline_items:
                    if tmln_shot not in play_list and tmln_shot not in self.failed_names:
                        self.result_list_except.setdefault("Шот отсутствует в контрольном списке:", []).append(tmln_shot)

                ''' Проверка на отсутствие графики на таймлайне и в контрольном списке.
                Пересбор словаря с номерами шотов в ключах без префиксов для унификации. prk_001_0010 добавится как 001_0010. 
                Если изначально 001_0010 - то так и добавится.
                Список маркеров и словарь с шотами с таймлайна и контрольного списка приведены к одному значению - 001_0010'''       
                play_list_dict_for_markers = {re.search(pattern_shot_number, k).group(0).lower(): j for k, j in play_list.items()}
                timeline_dict_for_markers = {re.search(pattern_shot_number, k).group(0).lower(): j for k, j in timeline_items.items()}
                for marker in markers_list:          
                    if marker not in play_list_dict_for_markers and marker not in timeline_dict_for_markers: 
                        self.result_list_except.setdefault('Шот отсутствует на таймлайне и в контрольном списке:', []).append(marker)          
                
                print(f"Данные для сверки соответствия между списком маркеров и ключами в play_list_dict_for_markers:\n{[k for k, v in play_list_dict_for_markers.items()]}")
            
            export_result_var = export_result(result_path)
            if export_result_var is None:
                self.on_error("Ошибка создания документа с результатами сверки")
                return
            
        # Получение имен шотов из маркеров из поля 'note'
        # Приведение всех номеров в маркерах к чистым числовым значениям для унификации. prk_001_0010 добавится как 001_0010. Если изначально 001_0010 - то так и добавится
        markers_list = []
        for _, j in timeline.GetMarkers().items():
            j = j['note'].strip()
            if j != '' and re.search(pattern_short, j):
                markers_list.append(re.search(pattern_shot_number, j).group(0))
        
        logger.debug(f"Данные маркеров с таймлайна:\n{markers_list}")

        # Собираем в список шоты(Объекты Blackmagic) с таймлайнов 
        all_cg_items = get_timeline_items(int(self.start_track.text()), int(self.end_track.text()) + 1, timeline)
        
        # Формирования пути для финального .txt файла
        result_file_path = os.path.join(self.result_path.text(), f'result_{date.today()}.txt')

        # Передача в основную функцию списка таймлайн итемов, списка маркеров, файловых путей, листа и столбца из exel
        compare_logic = is_compare(all_cg_items, markers_list, result_file_path)
        if compare_logic:
            self.on_error(f"В контрольном документе отсутствуют данные")
        else:
            self.update_failed_paths() # Выводим в GUI данные о неопознанных именах шотов
            self.update_result_label() # Обновляем количество проверенных шотов
            self.rows = 0 # Обнуляем контрольное количество шотов 
            # Обнуляем все списки
            self.result_list = {}
            self.result_list_except = {} 
            self.failed_paths = [] 
            self.failed_names = [] 
            self.on_info("Проверка завершена!")

if __name__ == '__main__':
    app = QtWidgets.QApplication(sys.argv)
    apply_style(app)
    window = VersionCheckerGUI()
    window.show()
    sys.exit(app.exec_())

