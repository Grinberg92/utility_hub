import sys
from collections import Counter
import DaVinciResolveScript 
from datetime import date
from pprint import pformat
import os
import openpyxl
import re
import bisect
import csv
from pathlib import Path
from itertools import count
from PyQt5 import QtWidgets, QtCore
from PyQt5.QtWidgets import (QApplication, QFileDialog, QLabel, QLineEdit, QPushButton, QRadioButton, 
                             QVBoxLayout, QHBoxLayout, QGroupBox, QTextEdit, QComboBox, 
                             QWidget, QMessageBox, QSizePolicy, QButtonGroup)
from PyQt5.QtGui import QFont
from PyQt5.QtCore import Qt, QThread, pyqtSignal
from dvr_tools.logger_config import get_logger
from dvr_tools.css_style import apply_style
from config.config_loader import load_config
from config.config import get_config
from config.global_config import GLOBAL_CONFIG
from dvr_tools.resolve_utils import ResolveObjects

logger = get_logger(__file__)

EXTENTIONS = ('.exr', '.mov', '.jpg')

class VersionComparer:

    def __init__(self, user_config: dict, signals, gui):
        """"

        :param signals: Экземпляр класса CheckerWorker для проброса сигналов.
        :param gui: Экземпляр класса VersionCheckerGUI для проброса предупреждений в ГУИ.
        """
        self.user_config = user_config
        self.signals = signals
        self.gui = gui

    def get_timeline_items(self, start_track: int, end_track: int, timeline: ResolveObjects) -> list:
        """
        Метод получет самый верхний клип в склейке.
        Работает только если все клипы в стеке стоят ровно в склейке и не вылезают за границы склейки.
        При этом отдельные клипы в стеке могут находиться внутри границы склейки и так же будут обработаны.
        """
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
                if re.search(self.pattern_real_shot, clip.GetName()):
                    start = clip.GetStart()
                    end = start + clip.GetDuration()

                    if not intersects(start, end):
                        top_clips.append(clip)
                        add_interval(start, end)

        return top_clips

    def is_dublicate(self, check_list: list) -> None:
        """
        Метод проверяет контрольную таблицу на наличие дубликатов.
        """
        find_dublicates = dict(filter(lambda x: x[1] >= 2, Counter(check_list).items()))
        if find_dublicates:
            for shot, quantity in find_dublicates.items():
                self.gui.current_counter += quantity - 1
                self.signals.warnings.emit(f"🟡  Шот {shot} имеет дубликаты")

    def count_global_excel(self, sheet) -> None:
        """
        Метод подсчитывает общее количество строк(шотов) excel в документе.
        """
        if self.gui.global_counter == 0:
            shots =  sheet[self.column_shots]
            for shot in shots:
                if shot.value is not None and shot.value != '' and re.search(self.pattern_shot_number, shot.value):
                    self.gui.global_counter += 1

    def check_reel_excel(self, sheet) -> None:
        """
        Метод проверяет незаполненные поля рил в контрольной таблице.
        """  
        shots_column = sheet[self.column_shots]
        reels_column = sheet[self.column_reel]

        reel_shot = list(zip(reels_column, shots_column))

        if int(self.resolve_reel) != 0:
            for reel, shot in reel_shot:
                if shot.value is not None and shot.value != '' and reel.value is None:
                    self.signals.warnings.emit(f"🔴  Не указан рил в шоте {shot.value}")        
                    self.gui.current_counter += 1

    def count_global_csv(self) -> None:
        '''
        Метод подсчитывает общее количество строк(шотов) в csv документе.
        '''
        if self.gui.global_counter == 0:
            with open(self.control_table_path, encoding='utf-8') as f:
                file = csv.DictReader(f, delimiter=',')
                
                # Проверка всего контрольного списка
                for string in file:
                    self.gui.global_counter += 1

    def read_column_from_excel(self)-> list: 
        '''
        Получаем данные из .xlsx файла.
        '''
        dublicate_shot = []
        try: 
            workbook = openpyxl.load_workbook(self.control_table_path) 
            sheet = workbook[self.sheet_name]
            self.count_global_excel(sheet)

            if self.gui.current_counter == 0:
                self.check_reel_excel(sheet)
            
            # Проверка, указан ли номер рила или рил = 0
            is_reel = int(self.resolve_reel) != 0

            shots_column = sheet[self.column_shots]
            reels_column = sheet[self.column_reel]

            # Получаем кортж в соответствие с тем указан ли номер рила или рил = 0
            reel_shot = ([(None, shot) for shot in shots_column], list(zip(reels_column, shots_column)))[is_reel]
            
            column_data = {}
            # Считываем данные из списка кортежей (рил, шот)
            for reel, shot in reel_shot:
                if (not is_reel) or (reel.value is not None):
                    if (not is_reel) or re.search(self.resolve_reel, str(reel.value)):
                        if shot.value is not None and shot.value != '':
                            try:
                                column_data[re.search(self.pattern_short, shot.value).group(0).lower()] = re.search(self.pattern_long, shot.value).group(0).lower()
                                dublicate_shot.append(re.search(self.pattern_short, shot.value).group(0).lower())
                            except AttributeError:
                                self.signals.warnings.emit(f"🔴  Имя {shot.value} не опознано")
                                self.failed_names.add(f"🔴  Имя {shot.value} не опознано")
                                self.gui.current_counter += 1

            self.is_dublicate(dublicate_shot)
            return column_data 
        except Exception as e: 
            self.signals.error_signal.emit(f"Не удалось получить данные из Excel документа: {e}")
            return []

    def read_column_from_csv(self)-> list:
        '''
        Получаем данные из .csv файла.
        '''
        dublicate_shot = []
        self.count_global_csv()
        
        try:
        # Открываем csv с данными по плейлисту из Шотгана и получаем словарь с парами ключ: значение. Имя шота с версией и имя шота без версии. {001_0010_comp_v001 : 001_0010, ...} 
            with open(self.control_table_path, encoding='utf-8') as f:
                file = csv.DictReader(f, delimiter=',')
                
                # Проверка всего контрольного списка
                control_table = {}
                for shot in file:
                    
                    # Если не указан рил, выбран 0 рил и current_counter пуст
                    if int(self.resolve_reel) != 0 and self.gui.current_counter == 0 and (shot["Reel"] == "" or not shot["Reel"]):
                        self.signals.warnings.emit(f"🔴  Не указан номер рила в шоте {shot['Entity']}")
                        self.failed_names.add(shot['Entity'])
                        self.gui.current_counter += 1

                    if not shot['Path to EXR'] and not shot['Path to Frames'] and (re.search(self.resolve_reel, shot['Reel']), True)[int(self.resolve_reel) == 0]: # Если нет адресов
                        self.signals.warnings.emit(f"🔴  Отсутствуют данные о шоте {shot['Entity']}")
                        self.failed_names.add(shot['Entity'])
                        self.gui.current_counter += 1
                        continue

                    # Если есть путь к exr и рил в контрольном списке соответствует рилу резолв в гуи
                    if shot['Path to EXR'] and (re.search(self.resolve_reel, shot['Reel']), True)[int(self.resolve_reel) == 0]: 
                        try:
                            shot['Path to EXR']
                            try:
                                control_table[re.search(self.pattern_short, shot['Path to EXR']).group(0)] = re.search(self.pattern_long, shot['Path to EXR']).group(0).lower()
                                dublicate_shot.append(re.search(self.pattern_short, shot['Path to EXR']).group(0))
                            except:
                                self.signals.warnings.emit(f"🔴  Имя {shot['Path to EXR']} не опознано")
                                self.failed_names.add(shot['Entity'])
                                self.gui.current_counter += 1
                                continue
                        except AttributeError:
                            pass # Ничего не делать. Переходим к проверке Path to Frames
                    
                    # Если нет пути к exr и рил в контрольном списке соответствует рилу резолв в гуи
                    if not shot['Path to EXR'] and (re.search(self.resolve_reel, shot['Reel']), True)[int(self.resolve_reel) == 0]:
                        try:
                            control_table[re.search(self.pattern_short, shot['Path to Frames']).group(0)] = re.search(self.pattern_long, shot['Path to Frames']).group(0).lower()
                            dublicate_shot.append(re.search(self.pattern_short, shot['Path to Frames']).group(0))
                        except AttributeError:
                            self.signals.warnings.emit(f"🔴  Имя {shot['Path to Frames']} не опознано")
                            self.failed_names.add(shot['Entity'])
                            self.gui.current_counter += 1

            self.is_dublicate(dublicate_shot)
            return control_table
        except Exception as e: 
            self.signals.error_signal.emit(f"Не удалось получить данные из CSV документа: {e}")
            return []
        
    def export_result(self)-> bool:
        """
        Экспорт результатов проверки.
        """   
        try:
            output_path = os.path.join(self.output_path, f'result_{date.today()}.txt')
            with open(output_path, 'a', encoding='utf-8') as o:
                o.write(self.resolve_reel + " РИЛ" + "\n")      
                for key, value in self.result_list.items():
                    o.write("\n" + key + "\n\n") 
                    for item in value:
                        o.write(item + "\n")
                o.write("_"* 80 + '\n\n')
            return True
        except:
            return False
        
    def get_target_tmln_items(self, all_timeline_items:list) -> dict:
        '''
        Получаем только целевые таймлайн объекты для последующей работы.
        '''
        timeline_items = {}
        for item in all_timeline_items:

            if item.GetName().endswith(EXTENTIONS): 

                name_long_match = re.search(self.pattern_long, item.GetName())
                if name_long_match:
                    name_item_long = name_long_match.group(0).lower()
                else:
                    continue

                name_short_match = re.search(self.pattern_short, item.GetName())
                if name_short_match:
                    name_item_short = name_short_match.group(0).lower()
                else:
                    continue

                timeline_items.setdefault(name_item_short, []).append(name_item_long)  #(имя шота без версии: [имя шота(ов) c версией])

        logger.debug(f"Данные собранные с таймлайна (имя шота без версии: [имя шота(ов) c версией]):\n{timeline_items}")
        return timeline_items
    
    def check_actual(self, control_table: dict, timeline_items:dict) -> None:
        '''
        Проверка шотов из контрольного списк с данными из таймлайна. 
        Проверяется актуальность и наличие шота на таймлайне.
        '''
        for ct_shot in control_table:
            if ct_shot in timeline_items:
                if control_table[ct_shot] in timeline_items[ct_shot]:
                    self.result_list.setdefault("Стоит актуальная версия шота:", []).append(control_table[ct_shot])
                    self.gui.current_counter += 1
                else:
                    self.result_list.setdefault("Обнаружено расхождение версий:", []).append(f"Версия в контрольной таблице - {control_table[ct_shot]}. Версии на таймлайне: {timeline_items[ct_shot]}")
                    self.gui.current_counter += 1
            else:
                self.result_list.setdefault("Шот есть в контрольной таблице, но нет на таймлайне:", []).append(control_table[ct_shot])
                self.gui.current_counter += 1

    def check_in_control_table(self, timeline_items:dict, control_table:dict) -> None:
        '''
        Проверяем сценарий наличия шота на таймлайне и отсутствие его в контрольной таблице.
        Так же проверяется отстутсвие шота на таймлайне и в контрольной таблице при условии что на таймлайне есть маркер с шотом.
        '''
        if self.global_mode:
            for tmln_shot in timeline_items:
                if tmln_shot not in control_table and tmln_shot not in self.failed_names:
                    self.result_list.setdefault("Шот отсутствует в контрольной таблице:", []).append(tmln_shot)

    def total_miss(self, timeline_items:dict, control_table:dict) -> None:
        '''
        Проверка на отсутствие графики на таймлайне и в контрольном списке.
        Пересбор словаря с номерами шотов в ключах без префиксов для унификации. prk_001_0010 добавится как 001_0010. 
        Если изначально 001_0010 - то так и добавится.
        Список маркеров и словарь с шотами с таймлайна и контрольного списка приведены к одному значению - 001_0010.
        '''     

        markers_list = []
        '''
        for _, j in timeline.GetMarkers().items():
            j = j['note'].strip()
            if j != '' and re.search(self.pattern_short, j):
                markers_list.append(re.search(self.pattern_shot_number, j).group(0))
        
        logger.debug(f"Данные маркеров с таймлайна:\n{markers_list}")
        '''
        if self.global_mode:
            control_table_dict_for_markers = {re.search(self.pattern_shot_number, k).group(0).lower(): j for k, j in control_table.items()}
            timeline_dict_for_markers = {re.search(self.pattern_shot_number, k).group(0).lower(): j for k, j in timeline_items.items()}
            for marker in markers_list:          
                if marker not in control_table_dict_for_markers and marker not in timeline_dict_for_markers: 
                    self.result_list.setdefault('Шот отсутствует на таймлайне и в контрольной таблице:', []).append(marker)  
            print(f"Данные для проверки соответствия между списком маркеров и ключами в control_table_dict_for_markers:\n{[k for k, v in control_table_dict_for_markers.items()]}")

    def is_compare(self, timeline_items:dict, control_table:dict) -> bool:
        """
        Метод с методами сравнения данных в контрольной таблице и таймлайне.
        """
        self.check_actual(control_table, timeline_items)

        self.check_in_control_table(timeline_items, control_table)       

        #self.total_miss(timeline_items, control_table) 
        return True
    
    def is_valid_track(self, timeline:ResolveObjects) -> bool:
        '''
        Валидация и проверка существования трека.
        '''
        if timeline.GetTrackCount("video") < self.out_track or self.in_track == 0:
            self.signals.warning_signal.emit(f"Указан несущствующий трек")
            return False
        return True
    
    def run(self) -> bool:
        '''
        Основная бизнес-логика.
        '''
        self.control_table_path = self.user_config["control_table_path"]
        self.output_path = self.user_config["output_path"]
        self.in_track = int(self.user_config["in_track"])
        self.out_track = int(self.user_config["out_track"])
        self.resolve_reel = self.user_config["resolve_reel"]
        self.sheet_name = self.user_config["sheet_name"]
        self.column_reel = self.user_config["column_reel"]
        self.column_shots = self.user_config["column_shots"]
        self.local_mode = self.user_config["local_mode"]
        self.global_mode = self.user_config["global_mode"]
        self.xlsx_source = self.user_config["xlsx_source"]
        self.csv_source = self.user_config["csv_source"]
        self.project = self.user_config["project"]
        self.failed_names = set()
        self.result_list = {}

        load_config(self.project)
        self.config = get_config()
        self.pattern_short = self.config['patterns']["compare_versions_shot_no_versions_mask"]
        self.pattern_long = self.config['patterns']["compare_versions_shot_versions_mask"]
        self.pattern_shot_number = self.config['patterns']["compare_versions_shot_soft_mask"]
        self.pattern_real_shot = self.config['patterns']["compare_versions_shot_no_prefix_mask"]

        try:

            resolve = ResolveObjects()
            timeline = resolve.timeline
            if timeline is None:
                self.signals.error_signal.emit(f"Не найдена таймлиния")
                return False
            valid = self.is_valid_track(timeline)
            if not valid:
                return False 
            
        except Exception as e:
            self.signals.error_signal.emit(f"{e}")
            return False     
            
        all_timeline_items = self.get_timeline_items(self.in_track, self.out_track, timeline)

        timeline_items = self.get_target_tmln_items(all_timeline_items)

        control_table = self.read_column_from_excel() if self.xlsx_source else self.read_column_from_csv()
        logger.debug(f"Данные плейлиста полученные из контрольного документа:\n{control_table}")
        if not control_table:
            self.signals.warning_signal.emit(f"В контрольном документе отсутствуют данные")
            return False

        compare_logic = self.is_compare(timeline_items, control_table)
        if not compare_logic:
            return
        else:
            export_result_var = self.export_result()
            if export_result_var is None:
                self.signals.error_signal.emit("Ошибка создания документа с результатами проверки")
                return False
            
        return True

class CheckerWorker(QThread):
    """
    Класс работы с логикой в отдельном потоке.
    """
    error_signal = pyqtSignal(str)
    success_signal = pyqtSignal(str)
    warning_signal = pyqtSignal(str)
    info_signal = pyqtSignal(str)
    warnings = pyqtSignal(str)
    update_signal = pyqtSignal()

    def __init__(self, parent, user_config):
        super().__init__(parent)
        self.user_config = user_config
        self.parent = parent

    def run(self):
        try:
            logic = VersionComparer(self.user_config, self, self.parent)
            result = logic.run() 
            if result:
                self.update_signal.emit() # Обновляем количество проверенных шотов
                self.info_signal.emit("Проверка завершена!")

        except Exception as e:
            self.error_signal.emit(f"Не удалось завершить проверку: {e}")

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
            "control_table_path": self.gui.control_table_path.text().strip(),
            "output_path": self.gui.result_path.text().strip(),
            "in_track": self.gui.in_resolve_track.text().strip(),
            "out_track": self.gui.out_resolve_track.text().strip(),
            "resolve_reel": self.gui.resolve_reel.text().strip(),
            "project": self.gui.project_cb.currentText(),
            "sheet_name": self.gui.sheet_name.text().strip(),
            "column_reel": self.gui.column_reel.text().strip().upper(),
            "column_shots": self.gui.column_shots.text().strip().upper(),
            "local_mode": self.gui.local_mode.isChecked(),
            "global_mode": self.gui.global_mode.isChecked(),
            "xlsx_source": self.gui.xlsx_source.isChecked(),
            "csv_source": self.gui.csv_source.isChecked()
        }
    
    def validate(self, user_config: dict) -> bool:
        """
        Валидирует конфиг.
        """
        self.errors.clear()

        if not user_config["control_table_path"]:
            self.errors.append("Укажите путь к контрольной таблице")
        else:
            if not os.path.exists(user_config["control_table_path"]):
                self.errors.append("Указан несуществующий путь к контрольной таблице")
        if not user_config["output_path"]:
            self.errors.append("Укажите путь для документа с результатом проверки")
        else:
            if not os.path.exists(user_config["output_path"]):
                self.errors.append("Указан несуществующий путь к документу с результатом сверки")

        try:
            int(user_config["in_track"])
            int(user_config["out_track"])
            int(user_config["resolve_reel"])
        except ValueError:
            self.errors.append("Значения должны быть целыми числами")

        if any(list(map(lambda x: x == '', (user_config["sheet_name"], user_config["column_reel"], user_config["column_shots"])))) and user_config['xlsx_source']:
            self.errors.append("Указаны не все значения для блока Excel Data")

        return not self.errors

    def get_errors(self) -> list:
        return self.errors
    
class VersionCheckerGUI(QWidget):

    def __init__(self):
        super().__init__()
        self.setWindowTitle("Check Shot Version")
        self.resize(550, 500)
        self.setWindowFlags(Qt.WindowStaysOnTopHint)

        self.current_counter = 0
        self.global_counter = 0

        self.control_table_path = QLineEdit()
        self.result_path = QLineEdit()
        self.in_resolve_track = QLineEdit("2")
        self.out_resolve_track = QLineEdit("10")
        self.sheet_name = QLineEdit("Sheet1")
        self.resolve_reel = QLineEdit("0")
        self.resolve_reel.textChanged.connect(lambda: self.update_fields_state())
        self.column_reel = QLineEdit()
        self.column_shots = QLineEdit()

        self.project_cb = QComboBox()
        self.project_cb.addItems(self.get_project())
        self.project_cb.setMinimumWidth(250)

        self.source_group_rb = QButtonGroup()
        self.xlsx_source = QRadioButton("excel")
        self.csv_source = QRadioButton(".csv from PL")
        self.source_group_rb.addButton(self.xlsx_source)
        self.source_group_rb.addButton(self.csv_source)
        self.xlsx_source.setChecked(True)

        self.mode_group_rb = QButtonGroup()
        self.global_mode =  QRadioButton('Global')
        self.local_mode =  QRadioButton('Local')
        self.mode_group_rb.addButton(self.xlsx_source)
        self.mode_group_rb.addButton(self.csv_source)
        self.local_mode.setChecked(True)

        self.warning_field = QTextEdit()
        self.warning_field_ph_text = "Здесь будут показаны имена шотов, которые не удалось определить."
        self.warning_field.setPlaceholderText(self.warning_field_ph_text)
        self.warning_field.setReadOnly(True)
        self.warning_field.setMinimumHeight(200)

        self.result_label = QLabel("Processed 0 from 0 shots")
        bold_font = QFont()
        bold_font.setBold(True)
        self.result_label.setFont(bold_font)

        self.init_ui()
        self.update_fields_state()

    def init_ui(self):
        layout = QVBoxLayout(self)

        layout.addWidget(self.warning_field)

        # Input file
        file_layout = QHBoxLayout()
        file_layout.addWidget(QLabel("Choose input file:"))
        file_layout.addSpacing(27)
        file_layout.addWidget(self.control_table_path)
        choose_file_btn = QPushButton("Choose")
        choose_file_btn.clicked.connect(self.select_file)
        file_layout.addWidget(choose_file_btn)
        layout.addLayout(file_layout)

        # Output path
        output_layout = QHBoxLayout()
        output_layout.addWidget(QLabel("Choose output path:"))
        output_layout.addSpacing(10)
        output_layout.addWidget(self.result_path)
        choose_output_btn = QPushButton("Choose")
        choose_output_btn.clicked.connect(self.select_result_path)
        output_layout.addWidget(choose_output_btn)
        layout.addLayout(output_layout)

        layout.addSpacing(7)

        project_layout = QHBoxLayout()
        project_layout.addStretch()
        project_layout.addWidget(self.project_cb)
        layout.addLayout(project_layout)
        project_layout.addStretch()

        # File type radio buttons
        file_type_group = QGroupBox("Source")
        file_type_group.setFixedWidth(300)
        file_type_group.setFixedHeight(50)
        filetype_layout = QHBoxLayout()
        filetype_layout.addStretch()
        self.xlsx_source.toggled.connect(self.update_fields_state)
        filetype_layout.addWidget(self.xlsx_source)
        filetype_layout.addSpacing(80)
        filetype_layout.addWidget(self.csv_source)
        filetype_layout.addStretch()
        file_type_group.setLayout(filetype_layout)
        layout.addWidget(file_type_group, alignment=Qt.AlignCenter)

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
        layout.addWidget(mode_group, alignment=Qt.AlignCenter)

        # GroupBox Section
        groupbox_layout = QHBoxLayout()  
        resolve_group = QGroupBox("Resolve Data")
        resolve_layout = QHBoxLayout()
        resolve_group.setFixedHeight(70)
        resolve_layout.addWidget(QLabel("Reel:"))
        resolve_layout.addWidget(self.resolve_reel)
        resolve_layout.addSpacing(10)
        resolve_layout.addWidget(QLabel("Track In:"))
        resolve_layout.addWidget(self.in_resolve_track)
        resolve_layout.addSpacing(10)
        resolve_layout.addWidget(QLabel("Out:"))
        resolve_layout.addWidget(self.out_resolve_track)
        resolve_group.setLayout(resolve_layout)

        excel_group = QGroupBox("Excel Data")
        excel_layout = QHBoxLayout()
        self.sheet_name.setFixedWidth(80)
        self.column_reel.setFixedWidth(40)
        self.column_shots.setFixedWidth(40)
        excel_layout.addWidget(QLabel("Sheet:"))
        excel_layout.addWidget(self.sheet_name)
        excel_layout.addSpacing(10)
        excel_layout.addWidget(QLabel("Reel:"))
        excel_layout.addWidget(self.column_reel)
        excel_layout.addSpacing(10)
        excel_layout.addWidget(QLabel("Shots:"))
        excel_layout.addWidget(self.column_shots)
        excel_group.setLayout(excel_layout)

        groupbox_layout.addWidget(resolve_group)
        groupbox_layout.addWidget(excel_group)
        layout.addLayout(groupbox_layout)

        # Result info
        label_layout = QHBoxLayout()
        label_layout.addWidget(self.result_label)
        reset_result_button = QPushButton("Reset")
        reset_result_button.clicked.connect(self.reset_counter)
        label_layout.addWidget(reset_result_button)
        label_layout.addStretch()
        layout.addLayout(label_layout)

        self.start_button = QPushButton("Start")
        self.start_button.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.start_button.setFixedHeight(30)
        self.start_button.clicked.connect(self.start)
        layout.addWidget(self.start_button)

    def reset_counter(self):
        """
        Обнуляем данные из обработанных таймлайнов и окно предупреждений
        """
        self.update_result_label(forse_reset=True)
        self.warning_field.clear()

    def get_project(self):
        """
        Метод получает список проектов.
        """
        base_path = {"win32": GLOBAL_CONFIG["paths"]["root_projects_win"], 
                    "darwin": GLOBAL_CONFIG["paths"]["root_projects_mac"]}[sys.platform]
        project_list = sorted([i for i in os.listdir(Path(base_path)) if os.path.isdir(Path(base_path) / i)])
        project_list.insert(0, "Select Project")
        return project_list

    def select_file(self):
        path, _ = QFileDialog.getOpenFileName(self, "Choose File", "", "Excel or CSV Files (*.xlsx *.csv)")
        if path:
            self.control_table_path.setText(path)

    def select_result_path(self):
        folder = QFileDialog.getExistingDirectory(self, "Choose Output Folder")
        if folder:
            self.result_path.setText(folder)

    def update_fields_state(self):
        """
        Локирует блок Excel при выборе режима .csv.
        Так же локирует инпут колонки рила при resolve_reel = 0.
        """
        enable_excel = self.xlsx_source.isChecked()
        self.sheet_name.setEnabled(enable_excel)
        self.column_shots.setEnabled(enable_excel)

        if enable_excel:
            try:
                reel_num = int(self.resolve_reel.text().strip())
            except ValueError:
                reel_num = None 

            if reel_num == 0:
                self.column_reel.setEnabled(False)
                self.column_reel.clear()
            else:
                self.column_reel.setEnabled(True)

        else:
            self.column_reel.setEnabled(False)

    def update_result_label(self, forse_reset=False):
        """
        Обновление счетчиков.
        """
        if forse_reset:
            self.current_counter = 0
            self.global_counter = 0
        self.result_label.setText(f"Processed {self.current_counter} from {self.global_counter or 0} shots")

    def on_error(self, message):
        QMessageBox.critical(self, "Ошибка", message)
        logger.exception(message)

    def on_warning(self, message):
        QMessageBox.warning(self, "Предупреждение", message)
        logger.warning(message)

    def on_info(self, message):
        QMessageBox.information(self, "Инфо", message)
        logger.info(message)

    def append_warning_field(self, message):
        """
        Добавляет уведомления и ошибки в warning_field через сигналы.
        """
        if self.warning_field.toPlainText().strip().startswith(self.warning_field_ph_text):
            self.warning_field.clear()
        self.warning_field.append(message)
    
    def start(self):
        """
        Запуск основной логики.
        """
        self.validator = ConfigValidator(self)
        self.user_config = self.validator.collect_config()

        if not self.validator.validate(self.user_config):
            self.on_error("\n".join(self.validator.get_errors()))
            return
        
        logger.info(f"\n\nSetUp:\n{pformat(self.user_config)}\n")

        self.main_process = CheckerWorker(self,self.user_config)
        self.start_button.setEnabled(False)
        self.main_process.finished.connect(lambda : self.start_button.setEnabled(True))
        self.main_process.error_signal.connect(self.on_error)
        self.main_process.warning_signal.connect(self.on_warning)
        self.main_process.info_signal.connect(self.on_info)
        self.main_process.warnings.connect(self.append_warning_field)
        self.main_process.update_signal.connect(self.update_result_label)
        self.main_process.start()

if __name__ == '__main__':
    app = QApplication(sys.argv)
    apply_style(app)
    window = VersionCheckerGUI()
    window.show()
    sys.exit(app.exec_())