import sys
import os
import random
import re
import math
import time
from pathlib import Path
import DaVinciResolveScript as dvr
from PyQt5 import QtWidgets, QtCore
from PyQt5.QtWidgets import QComboBox, QListView
from PyQt5.QtGui import QStandardItemModel, QStandardItem
from PyQt5.QtCore import Qt
from dvr_tools.logger_config import get_logger
from dvr_tools.css_style import apply_style
from dvr_tools.timeline_exctractor import ResolveTimelineItemExtractor

logger = get_logger(__file__)

class CheckableComboBox(QComboBox):

    """Кастомный класс для создания выпадающего списка с чекбоксами"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setModel(QStandardItemModel(self))
        self.setView(QListView())
        self.setEditable(True)
        self.lineEdit().setReadOnly(True)
        self.lineEdit().setPlaceholderText("Select items")
        self.model().dataChanged.connect(self._update_display_text)
        self.lineEdit().installEventFilter(self)

    def eventFilter(self, source, event):
        if source == self.lineEdit() and event.type() == event.MouseButtonPress:
            self.showPopup()
            return True
        return super().eventFilter(source, event)

    def clear_items(self):
        self.model().clear()

    def add_checkable_item(self, text, data=None, checked=False):
        item = QStandardItem(text)
        item.setFlags(Qt.ItemIsEnabled | Qt.ItemIsUserCheckable)
        item.setData(Qt.Checked if checked else Qt.Unchecked, Qt.CheckStateRole)
        item.setData(data, Qt.UserRole)
        self.model().appendRow(item)

    def checked_items(self):

        """Возвращает список кортежей: (userData, текст)"""

        result = []
        for i in range(self.model().rowCount()):
            item = self.model().item(i)
            if item.checkState() == Qt.Checked:
                result.append((item.data(Qt.UserRole), item.text()))
        return result

    def _update_display_text(self):
        selected = [text for _, text in self.checked_items()]
        self.lineEdit().setText(", ".join(selected) if selected else "Select items")

class RenderThread(QtCore.QThread):

    """Класс пускает исполнение process_render через отдельный поток"""
    
    error_signal = QtCore.pyqtSignal(str)
    success_signal = QtCore.pyqtSignal()
    warning_signal = QtCore.pyqtSignal(str)
    info_signal = QtCore.pyqtSignal(str)

    def __init__(self, parent, glob_width, glob_height, output_folder, project_preset, render_preset):
        super().__init__(parent)
        self.parent = parent
        self.glob_width = glob_width
        self.glob_height = glob_height
        self.output_folder = output_folder
        self.project_preset = project_preset
        self.render_preset = render_preset

    def run(self):
        # Запускаем процесс рендера
        try:
            self.parent.process_render(self.glob_width, self.glob_height, self.output_folder, self.project_preset, self.render_preset)
        except Exception as e:
            self.error_signal.emit(f"Критическая ошибка: {e}")

class ResolveGUI(QtWidgets.QWidget):

    """Класс GUI"""

    def __init__(self):
        super().__init__()
        self.setWindowTitle("Proxy Render")
        self.resize(550, 500)
        self.setWindowFlag(QtCore.Qt.WindowStaysOnTopHint)

        # Глобальные переменные
        self.glob_width = QtWidgets.QLineEdit("1920")
        self.glob_width.setFixedWidth(50)
        self.glob_height = QtWidgets.QLineEdit("1080")
        self.glob_height.setFixedWidth(50)

        self.logic_mode_1080 = QtWidgets.QRadioButton()
        self.logic_mode_frame = QtWidgets.QRadioButton()

        self.output_folder = QtWidgets.QLineEdit("J:/003_transcode_to_vfx/kraken/tst")

        self.project_preset = QtWidgets.QComboBox()
        self.render_preset = QtWidgets.QComboBox()

        self.lut_project = QtWidgets.QComboBox()
        self.lut_file = QtWidgets.QComboBox()
        self.apply_arricdl_lut = QtWidgets.QCheckBox("Apply ARRI Camera LUT")

        self.set_fps_checkbox = QtWidgets.QCheckBox("Set Project FPS")
        self.project_fps_value = QtWidgets.QLineEdit("24")
        self.project_fps_value.setFixedWidth(50)

        self.set_burn_in_checkbox = QtWidgets.QCheckBox("Set Burn-in")
        self.add_mov_mp4 = QtWidgets.QCheckBox("Add .mov, .mp4, .jpg")
        self.auto_sync_checkbox = QtWidgets.QCheckBox("Sync Audio")

        self.burn_in_list = CheckableComboBox()

        self.ocf_folders_list = CheckableComboBox()
        self.ocf_folders_list.setFixedWidth(180)

        self.lut_path_nx = r'C:\ProgramData\Blackmagic Design\DaVinci Resolve\Support\LUT\LUTS_FOR_PROXY'
        self.lut_path_posix = '/Library/Application Support/Blackmagic Design/DaVinci Resolve/LUT/LUTS_FOR_PROXY/'
        self.lut_base_path = self.lut_path_posix if os.name == "posix" else self.lut_path_nx

        self.timeline_preset_path_nx = r"J:\003_transcode_to_vfx\projects\Others\timeline_presets\logc4_to_rec709.drt"
        self.timeline_preset_path_posix = "/Volumes/share2/003_transcode_to_vfx/projects/Others/timeline_presets/logc4_to_rec709.drt"
        self.timeline_preset_path = self.timeline_preset_path_posix if os.name == "posix" else self.timeline_preset_path_nx

        # Подключение к Resolve
        try:
            self.resolve = dvr.scriptapp("Resolve")
            self.project_manager = self.resolve.GetProjectManager()
            self.project = self.project_manager.GetCurrentProject()
            self.media_pool = self.project.GetMediaPool()
            self.timeline = self.project.GetCurrentTimeline()
        except Exception as e:
            QtWidgets.QMessageBox.critical(self, "Ошибка", f"Ошибка подключения к Resolve: {e}")
            logger.exception(f"Ошибка подключения к Resolve: {e}")
            sys.exit()

        self.init_ui()
        self.get_project_preset_list()
        self.get_render_preset_list()
        self.update_lut_projects()

    def init_ui(self):
        
        layout = QtWidgets.QVBoxLayout(self)

        # Resolution
        res_layout = QtWidgets.QHBoxLayout()
        res_layout.addStretch()
        res_layout.addWidget(QtWidgets.QLabel("Resolution:"))
        res_layout.addWidget(self.glob_width)
        res_layout.addWidget(QtWidgets.QLabel("x"))
        res_layout.addWidget(self.glob_height)
        res_layout.addStretch()
        layout.addLayout(res_layout)

        # Logic group
        logic_group = QtWidgets.QGroupBox("Logic")
        logic_group.setFixedHeight(70)
        logic_group.setFixedWidth(300)
        logic_layout = QtWidgets.QHBoxLayout()

        vbox1 = QtWidgets.QVBoxLayout()
        label_1080 = QtWidgets.QLabel("All into FullHD")
        label_1080.setAlignment(QtCore.Qt.AlignHCenter)
        vbox1.addWidget(self.logic_mode_1080, alignment=QtCore.Qt.AlignHCenter)
        vbox1.addWidget(label_1080)

        vbox2 = QtWidgets.QVBoxLayout()
        label_frame = QtWidgets.QLabel("Frame to horizontal")
        label_frame.setAlignment(QtCore.Qt.AlignHCenter)
        vbox2.addWidget(self.logic_mode_frame, alignment=QtCore.Qt.AlignHCenter)
        vbox2.addWidget(label_frame)

        self.logic_mode_frame.setChecked(True)

        logic_layout.addStretch()
        logic_layout.addLayout(vbox1)
        logic_layout.addSpacing(60)
        logic_layout.addLayout(vbox2)
        logic_layout.addStretch()

        logic_group.setLayout(logic_layout)
        layout.addWidget(logic_group, alignment=QtCore.Qt.AlignHCenter)

        # Presets group 
        presets_group = QtWidgets.QGroupBox("Presets")
        presets_layout = QtWidgets.QVBoxLayout()
        presets_layout.addWidget(QtWidgets.QLabel("Project Preset:"))
        presets_layout.addWidget(self.project_preset)
        presets_layout.addWidget(QtWidgets.QLabel("Render Preset:"))
        presets_layout.addWidget(self.render_preset)
        presets_layout.addWidget(QtWidgets.QLabel("Burn-in Preset:"))
        presets_layout.addWidget(self.burn_in_list)
        presets_group.setLayout(presets_layout)
        layout.addWidget(presets_group)

        # Color group 
        color_group = QtWidgets.QGroupBox("Color")
        color_layout = QtWidgets.QVBoxLayout()
        color_layout.addWidget(QtWidgets.QLabel("LUT Project:"))
        color_layout.addWidget(self.lut_project)
        self.lut_project.currentTextChanged.connect(self.update_lut_files)
        color_layout.addWidget(QtWidgets.QLabel("LUT File:"))
        color_layout.addWidget(self.lut_file)
        color_layout.addWidget(self.apply_arricdl_lut)
        color_group.setLayout(color_layout)
        layout.addWidget(color_group)

        # FPS group 
        fps_group = QtWidgets.QGroupBox("FPS")
        fps_layout = QtWidgets.QHBoxLayout()
        fps_layout.addWidget(self.set_fps_checkbox)
        fps_layout.addSpacing(10)
        fps_layout.addWidget(QtWidgets.QLabel("FPS:"))
        fps_layout.addWidget(self.project_fps_value)
        fps_layout.addStretch()
        fps_group.setLayout(fps_layout)
        layout.addWidget(fps_group)

        # Advanced
        adv_group = QtWidgets.QGroupBox("Advanced Group")
        adv_group.setFixedHeight(100)
        adv_main_layout = QtWidgets.QVBoxLayout()

        row1_layout = QtWidgets.QHBoxLayout()
        self.set_burn_in_checkbox.setChecked(True)
        row1_layout.addWidget(self.set_burn_in_checkbox)
        row1_layout.addSpacing(20)
        row1_layout.addWidget(self.add_mov_mp4)
        row1_layout.addSpacing(20)
        row1_layout.addWidget(self.ocf_folders_list)
        row1_layout.addStretch()

        row2_layout = QtWidgets.QHBoxLayout()
        self.auto_sync_checkbox.setChecked(False)
        row2_layout.addWidget(self.auto_sync_checkbox)
        row2_layout.addStretch()

        adv_main_layout.addLayout(row1_layout)
        adv_main_layout.addLayout(row2_layout)
        adv_group.setLayout(adv_main_layout)
        layout.addWidget(adv_group)

        # Render path
        path_layout = QtWidgets.QHBoxLayout()
        path_layout.addWidget(QtWidgets.QLabel("Render Path:"))
        path_layout.addWidget(self.output_folder)
        path_btn = QtWidgets.QPushButton("Choose")
        path_btn.clicked.connect(self.select_folder)
        path_layout.addWidget(path_btn)
        layout.addLayout(path_layout)

        # Start button
        self.start_button = QtWidgets.QPushButton("Start")
        self.start_button.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Fixed)
        self.start_button.clicked.connect(self.start_render)
        layout.addWidget(self.start_button)

        self.load_ocf_subfolders()
        self.load_burn_in()

    def update_lut_projects(self):

        """Метод сканирует подпапки в LUT-папке"""

        if os.path.isdir(self.lut_base_path):
            subfolders = [name for name in os.listdir(self.lut_base_path)
                        if os.path.isdir(os.path.join(self.lut_base_path, name))]
            self.lut_project.clear()
            self.lut_project.addItems(subfolders)
            if subfolders:
                self.lut_project.setCurrentIndex(0)
                self.update_lut_files()

    def update_lut_files(self):

        """Метод сканирует .cube файлы в выбранной папке LUT"""

        selected_project = self.lut_project.currentText()
        selected_path = os.path.join(self.lut_base_path, selected_project)
        if os.path.isdir(selected_path):
            cube_files = [f for f in os.listdir(selected_path)
                        if f.lower().endswith(".cube")]
            cube_files.insert(0, "No LUT")
            self.lut_file.clear()
            self.lut_file.addItems(cube_files)

    def get_project_preset_list(self):

        """Метод получения пресета проекта"""

        project_preset_list = [preset["Name"] for preset in self.project.GetPresetList()][3:] # Отрезаем системные пресеты
        self.project_preset.addItems(project_preset_list)

    def get_render_preset_list(self):

        """Метод получения пресета рендера"""

        render_presets_list = [preset for preset in self.project.GetRenderPresetList()][31:] # Отрезаем системные пресеты
        self.render_preset.addItems(render_presets_list)

    def select_folder(self):
        folder = QtWidgets.QFileDialog.getExistingDirectory(self, "Выбор папки")
        if folder:
            self.output_folder.setText(folder)

    def load_burn_in(self):

        "Метод получает данные о пресетах burn-in"

        win_path = r"J:\003_transcode_to_vfx\projects\Others\burn_in_presets"
        mac_path = "/Volumes/share2/003_transcode_to_vfx/projects/Others/burn_in_presets"
        base_path = mac_path if os.name == "posix" else win_path

        preset_list = os.listdir(base_path)
        preset_list_sorted = sorted(
                                    preset_list,
                                    key=lambda name: os.path.getmtime(os.path.join(base_path, name)))
        
        preset_list_sorted = [i.split(".")[0] for i in preset_list_sorted]
        for preset in preset_list_sorted:
            self.burn_in_list.add_checkable_item(preset)

        self.burn_in_list._update_display_text()


    def load_ocf_subfolders(self):

        """Метод загружает сабфолдеры из папки '001_OCF' в CheckableComboBox"""

        root_folder = self.media_pool.GetRootFolder()
        ocf_folder = next((f for f in root_folder.GetSubFolderList() if f.GetName() == "001_OCF"), None)

        if not ocf_folder:
            QtWidgets.QMessageBox.critical(self, "Ошибка", "Папка '001_OCF' не найдена")
            return

        self.ocf_folders_list.clear_items()
        self.ocf_folders_list.add_checkable_item("Current Folder", data=None, checked=True)

        for subfolder in ocf_folder.GetSubFolderList():
            self.ocf_folders_list.add_checkable_item(subfolder.GetName(), data=subfolder)

    def start_render(self):

        """Метод запускает исполняемый скрипт через отдельный поток"""

        glob_width = self.glob_width.text()
        glob_height = self.glob_height.text()
        output_folder = self.output_folder.text()
        project_preset = self.project_preset.currentText()
        render_preset = self.render_preset.currentText()

        if not glob_height or not glob_width:
            QtWidgets.QMessageBox.warning(self, "Предупреждение", "Значения ширины или высоты не указаны")
            logger.warning("Значения ширины или высоты не указаны")
            return
        
        if self.set_fps_checkbox.isChecked() and not self.project_fps_value.text():
            QtWidgets.QMessageBox.warning(self, "Предупреждение", "Укажите значение FPS")
            logger.warning("Укажите значение FPS")
            return      
        
        if not output_folder:
            QtWidgets.QMessageBox.warning(self, "Предупреждение", "Укажите путь для рендера")
            logger.warning("Укажите путь для рендера")
            return    

        if not self.burn_in_list.checked_items():
            QtWidgets.QMessageBox.warning(self, "Предупреждение", "Укажите хотя бы один пресет burn-in")
            logger.warning("Укажите хотя бы один пресет burn-in")
            return 


        if not self.ocf_folders_list.checked_items():
            QtWidgets.QMessageBox.warning(self, "Предупреждение", "Укажите хотя бы один фолдер")
            logger.warning("Укажите хотя бы один фолдер")
            return 

        if not os.path.exists(self.timeline_preset_path) and self.apply_arricdl_lut.isChecked():
            QtWidgets.QMessageBox.warning(self, "Предупреждение", f"Отсутстует програмный файл - {self.timeline_preset_path}")
            logger.warning("Укажите хотя бы один фолдер")
            return 

        logger.debug("\n".join(("SetUp:", f"Resolution: {glob_width}x{glob_height}", f"Logic fullhd: {self.logic_mode_1080.isChecked()}", 
                      f"Logic frame: {self.logic_mode_frame.isChecked()}",
                      f"Burn-in preset: {self.burn_in_list.checked_items()}",
                      f"Render path: {output_folder}",f"Project preset: {project_preset}", 
                      f"Render preset: {render_preset}", f"LUT Project: {self.lut_project.currentText()}", 
                      f"LUT file: {self.lut_file.currentText()}", f"ArriCDLandLUT: {self.apply_arricdl_lut.isChecked()}", 
                      f"Set FPS: {self.set_fps_checkbox.isChecked()}", f"FPS: {self.project_fps_value.text()}", 
                      f"Set Burn in: {self.set_burn_in_checkbox.isChecked()}", f"Add .mov, .mp4, .jpg: {self.add_mov_mp4.isChecked()}",
                      f"Folder: {self.ocf_folders_list.checked_items()}", f"Sync Audio: {self.auto_sync_checkbox.isChecked()}")))
        
        # Вызываем основной процесс рендера
        self.thread = RenderThread(
            self,
            glob_width,
            glob_height,
            output_folder,
            project_preset,
            render_preset
        )
        self.start_button.setEnabled(False)
        self.thread.finished.connect(lambda: self.start_button.setEnabled(True))
        self.thread.error_signal.connect(self.on_error_signal)
        self.thread.success_signal.connect(self.on_success_signal)
        self.thread.warning_signal.connect(self.on_warning_signal)
        self.thread.info_signal.connect(self.on_info_signal)
        self.thread.start()
    
    def on_error_signal(self, message):
        QtWidgets.QMessageBox.critical(self, "Ошибка", message)
        logger.exception(f"{message}")

    def on_success_signal(self):
        QtWidgets.QMessageBox.information(self, "Успех", "Рендер успешно завершен")
        logger.info("Рендер успешно завершен")

    def on_warning_signal(self, message):
        QtWidgets.QMessageBox.warning(self, "Предупреждение", message)
        logger.warning(f"Предупреждение: {message}")

    def on_info_signal(self, message):
        QtWidgets.QMessageBox.information(self, "Инфо", message)
        logger.info(f"{message}")

    def process_render(self, glob_width, glob_height, output_folder, project_preset, render_preset):

        """Метод основной исполняемой логики"""

        logger.debug("Запуск скрипта")

        def copy_filtered_clips_to_ocf_folder(current_source_folder):

            """
            Ищет .mov, .mp4, .jpg клипы в current_source_folder и перемещает их в
            001_OCF/Excepted clips/{current_source_folder}.
            """

            valid_extensions = ['.mov', '.mp4', '.jpg', '.MOV', '.MP4', '.JPG']
            root_folder = self.media_pool.GetRootFolder()

            # --- Найти или создать папку 001_OCF ---
            ocf_folder = next((f for f in root_folder.GetSubFolderList() if f.GetName() == "001_OCF"), None)
            if not ocf_folder:
                self.thread.error_signal.emit("Папка '001_OCF' не найдена")
                return None

            # --- Найти или создать папку mov_mp4_jpg ---
            base_folder = next((f for f in ocf_folder.GetSubFolderList() if f.GetName() == "Excepted clips"), None)
            if not base_folder:
                base_folder = self.media_pool.AddSubFolder(ocf_folder, "Excepted clips")
                if not base_folder:
                    self.thread.error_signal.emit("Не удалось создать папку 'Excepted clips'.")
                    return None

            # --- Сбор клипов с подходящими расширениями ---
            def collect_valid_clips(folder):

                "Функция формирует список 'отбракованных mov, mp4, jpg'"

                collected = []
                for clip in folder.GetClipList():
                    name = clip.GetName().lower()
                    if any(name.endswith(ext) for ext in valid_extensions):
                        if self.set_fps_checkbox.isChecked() and float(clip.GetClipProperty("FPS")) != float(self.project_fps_value.text()):
                            set_project_fps(clip)
                        collected.append(clip)
                for subfolder in folder.GetSubFolderList():
                    collected.extend(collect_valid_clips(subfolder))
                return collected

            clips_to_move = collect_valid_clips(current_source_folder)

            if not clips_to_move:
                logger.debug("Нет .mov, .jpg, .mp4 клипов для перемещения.")
                self.media_pool.SetCurrentFolder(current_source_folder) 
                return []
            else:
                # --- Создать вложенную подпапку с именем текущего исходного бин-фолдера ---
                source_folder_name = current_source_folder.GetName()
                target_folder = next((f for f in base_folder.GetSubFolderList() if f.GetName() == source_folder_name), None)
                if not target_folder:
                    target_folder = self.media_pool.AddSubFolder(base_folder, source_folder_name)
                    if not target_folder:
                        self.thread.error_signal.emit(f"Не удалось создать папку '{source_folder_name}' внутри 'Excepted clips'.")
                        return None
                    
            # Переключаемся в нужный подбин
            self.media_pool.SetCurrentFolder(target_folder)
            
            return clips_to_move
        
        def set_project_fps(clip)-> None:

            "Функция устанавливает проектный FPS"

            clip.SetClipProperty("FPS", self.project_fps_value.text())
            logger.debug(f"Установлен FPS {self.project_fps_value.text()} на клип {clip.GetName()}")

        def auto_sync_audio(curr_source_folder_clips_list):

            """Функция делает автосинхронизацию видео и звука по таймкоду в текущем фолдере"""

            result_sync = self.media_pool.AutoSyncAudio(curr_source_folder_clips_list, {self.resolve.AUDIO_SYNC_MODE: self.resolve.AUDIO_SYNC_TIMECODE})

            if result_sync:
                logger.debug("Синхронизация звука произведена успешно")
            else:
                self.thread.error_signal.emit("Синхронизация звука не произведена")

        def get_bin_items()-> list:

            """Функция получает mediapoolitems из текущего фолдера"""

            cur_bin_items_list = []
            curr_source_folder = self.media_pool.GetCurrentFolder()
            curr_source_folder_clips_list = curr_source_folder.GetClipList()
            if self.auto_sync_checkbox.isChecked():
                auto_sync_audio(curr_source_folder_clips_list)
            for clip in curr_source_folder_clips_list:
                name = clip.GetName().lower()
                if "." in name:
                    if self.add_mov_mp4.isChecked() or not name.endswith(('.mov', '.mp4', '.jpg')):
                        if self.set_fps_checkbox.isChecked() and float(clip.GetClipProperty("FPS")) != float(self.project_fps_value.text()):
                            set_project_fps(clip)
                        cur_bin_items_list.append(clip)

            logger.debug(f"Получен список mediapool объектов в фолдере {curr_source_folder.GetName()}")
            return cur_bin_items_list, curr_source_folder
        
        def turn_on_burn_in(aspect)-> None:

            "Функция устанавливает пресет burn in"

            try:
                preset_list = [preset[1] for preset in self.burn_in_list.checked_items()]

                if not self.set_burn_in_checkbox.isChecked():
                    if self.project.LoadBurnInPreset("python_no_burn_in"):
                        logger.debug("Применен пресет burn-in: python_no_burn_in") 
                    else:
                        logger.warning("Пресет 'python_no_burn_in' отсутствует") 
                else:
                    for preset in preset_list:
                        if re.search(aspect, preset):
                            self.project.LoadBurnInPreset(preset)
                            logger.debug(f"Применен пресет burn-in: {preset}") 
            except Exception as e:
                self.thread.error_signal.emit("Ошибка применения пресета burn-in")

        def set_project_preset()-> None:

            "Функция устанавливает пресет проекта"

            if self.project.SetPreset(project_preset):
                logger.debug(f"Применен пресет проекта: {project_preset}")
            else:
                logger.debug(f"Ошибка: Не удалось применить пресет проекта {project_preset}")

        def get_sep_resolution_list(cur_bin_items_list, extentions=None)-> dict:

            "Функция создает словать с парами ключ(разрешение): значение(список соответствующих клипов)"

            if extentions is None:
                extentions = (".mxf", ".braw", ".arri", ".r3d", ".dng")

            logger.debug(f"Используются расширения {extentions}")
            clips_dict = {}
            for clip in cur_bin_items_list:
                    if clip.GetName() != '' and clip.GetName().lower().endswith(extentions):
                        # Находит анаморф, вычисляет ширину по аспекту
                        if clip.GetClipProperty('PAR') != 'Square' and clip.GetClipProperty('PAR'):
                            aspect = clip.GetClipProperty('PAR')
                            width, height = clip.GetClipProperty('Resolution').split('x')
                            calculate_height = str((math.ceil(((int(height) / float(aspect)) * int(glob_width) / int(width) ) / 2) * 2))
                            resolution = "x".join([glob_width, calculate_height])
                            clips_dict.setdefault(resolution, []).append(clip)
                        else:
                            aspect = clip.GetClipProperty('PAR')
                            width, height = clip.GetClipProperty('Resolution').split('x')
                            calculate_height = str((math.ceil((int(height) * int(glob_width) / int(width)) / 2) * 2))
                            resolution = "x".join([glob_width, calculate_height])
                            clips_dict.setdefault(resolution, []).append(clip)
            return clips_dict
        
        def split_by_arri(clip_list)-> list:

            """Разделяет клипы на ARRI и не-ARRI"""

            arri_clips = []
            non_arri_clips = []
            for clip in clip_list:
                video_codec = clip.GetClipProperty("Video Codec").lower()
                ics = clip.GetClipProperty("Input Color Space").lower()
                if "arri" in video_codec or "arri" in ics:
                    arri_clips.append(clip)
                else:
                    non_arri_clips.append(clip)
            return arri_clips, non_arri_clips


        def get_timelines(clips_dict)-> list:

            """Функция создает таймлайны"""

            new_timelines = [] 

            for res, items in clips_dict.items():
                arri_clips, non_arri_clips = split_by_arri(items)

                def make_timeline(clips, is_arri):
                    random_number = random.randint(10000, 999999)
                    suffix = "arri" if is_arri else "mixed"
                    timeline_name = f"tmln_{res}_{suffix}_{random_number}"

                    if is_arri and self.apply_arricdl_lut.isChecked():
                        # Импорт шаблона таймлайна с loc4 to rec709 трансформом
                        timeline = self.media_pool.ImportTimelineFromFile(self.timeline_preset_path)
                            
                        if not timeline:
                            logger.critical(f"Отсутствует шаблон таймлайна для ARRI: {self.timeline_preset_path}")
                        
                        # Установка разрешения на таймлайн (таймлайн импортируется без привязки к проектному разрешению)
                        resolution = get_resolution(timeline_name)
                        width, height = resolution.split("x")
                        timeline.SetSetting("timelineResolutionHeight", height)
                        timeline.SetSetting("timelineResolutionWidth", width)

                        timeline.SetName(timeline_name)
                        self.media_pool.AppendToTimeline(clips)

                        # Удаляем заглушку присутсвующую при импорте шаблона(видео + аудио) в медиапуле и таймлайне
                        mp_obj = ResolveTimelineItemExtractor(timeline)
                        self.media_pool.DeleteClips([mp_obj.get_timeline_items(1, 1)[0].GetMediaPoolItem()])
                        timeline.DeleteClips([mp_obj.get_timeline_items(1, 1)[0],mp_obj.get_timeline_items(1, 1, track_type='audio')[0]], True)
                    else:
                        timeline = self.media_pool.CreateEmptyTimeline(timeline_name)
                        self.project.SetCurrentTimeline(timeline)
                        self.media_pool.AppendToTimeline(clips)

                    if timeline:
                        logger.debug(f"Создан таймлайн: {timeline_name}")
                        new_timelines.append(timeline)
                    else:
                        logger.critical(f"Ошибка при создании таймлайна: {timeline_name}")

                # Один общий ARRI таймлайн
                if arri_clips:
                    make_timeline(arri_clips, is_arri=True)
                    
                # Один таймлайн для прочих клипов
                if non_arri_clips:
                    make_timeline(non_arri_clips, is_arri=False)

            if not new_timelines:
                return None
            
            return new_timelines

        def set_lut()-> None:

            "Функция устанавливает заданный LUT(распаковывает AriiCDLLut) на все клипы на таймлайне"

            self.project.RefreshLUTList()
            if not self.apply_arricdl_lut.isChecked() and self.lut_file == "No LUT":
                logger.debug(f"LUT не применялся")
                return
            current_timeline = self.project.GetCurrentTimeline()
            for track in range(1, current_timeline.GetTrackCount("video") + 1):
                for tmln_item in current_timeline.GetItemListInTrack("video", track):
                    if self.apply_arricdl_lut.isChecked():
                        tmln_item.GetNodeGraph(1).ApplyArriCdlLut()  
                    if not self.lut_file == "No LUT":
                        lut_path = os.path.join(self.lut_base_path, self.lut_project.currentText(), self.lut_file.currentText())
                        tmln_item.SetLUT(1, lut_path)
            logger.debug(f"LUT установлен на все клипы на таймлайне {current_timeline.GetName()}")

        def get_render_list(new_timelines, folder_name)-> list:
            
            "Функция создает render job из всех собранных таймлайнов"

            try:
                if folder_name != "Current Folder":
                    folder = Path(output_folder) / folder_name
                else:
                    folder = output_folder
                
                logger.debug(f"Финальный путь: {folder}")

                render_list = []
                for timeline in new_timelines:
                    self.project.SetCurrentTimeline(timeline)  # Переключаемся на текущий таймлайн
                    set_lut()
                    timeline_name = timeline.GetName()
                    resolution = re.search(r'\d{3,4}x\d{3,4}', timeline_name).group(0)
                    width, height = resolution.split("x")
                    logger.debug(f"Добавляю в очередь рендеринга: {timeline_name}")

                    # Применяем пресет рендера
                    if self.project.LoadRenderPreset(render_preset):
                        logger.debug(f"Применен пресет рендера: {render_preset}")
                    else:
                        logger.critical(f"Ошибка: Не удалось загрузить пресет рендера {render_preset}")
                    
                    # Устанавливаем настройки рендера

                    render_settings = {
                        "TargetDir": str(folder),
                        "FormatWidth": int(width), 
                        "FormatHeight": int(height)
                    }
                    self.project.SetRenderSettings(render_settings)        

                    # Добавляем в очередь рендера
                    render_item = self.project.AddRenderJob()  
                    render_list.append((render_item, timeline_name))
                return render_list
            except Exception as e:
                self.thread.error_signal.emit(f"Ошибка создания списка с рендер задачами: {e}")
                return None

        def rendering_in_progress()-> bool:

            "Функция проверяеет есть ли активный рендер"

            return self.project.IsRenderingInProgress()
        
        def get_resolution(timeline_name)-> str:

            """Функция извлечения разрешения из переданного таймлайна"""

            return re.search(r'\d{3,4}x\d{3,4}', timeline_name).group(0)
        
        def start_render(render_queue)-> bool:

            "Функция запуска рендера"

            logger.debug("Запускаю рендер...")
            for render, timeline_name in render_queue:
                resolution = get_resolution(timeline_name)
                width, height = resolution.split("x")
                # Проверяем закончился ли предыдущий рендер
                while rendering_in_progress():
                    time.sleep(1)
                logger.debug(f"Разрешение {resolution}")
                self.project.SetSetting("timelineResolutionWidth", width)
                self.project.SetSetting("timelineResolutionHeight", height)
                if int(height) < 1000:
                    turn_on_burn_in("anam")
                else:
                    turn_on_burn_in("square")
                start_render_var = self.project.StartRendering(render)
                if not start_render_var:
                    return None      

            # Ожидаем завершения последнего активного рендера
            while rendering_in_progress():
                time.sleep(1)

            return True 

                
        # Основной блок 
        selected_folders = self.ocf_folders_list.checked_items()

        # Установка пресета проекта
        set_project_preset()

        # Цикл по выбранным в GUI фолдерам selected_folders
        for folder_obj, folder_name in selected_folders:
            
            if folder_obj is None: # None = Current Folder в интерфейсе
                ...
            else:
                logger.debug(f"Начало работы с фолдером {folder_obj.GetName()}")
                current_source_folder = self.media_pool.SetCurrentFolder(folder_obj)
            cur_bin_items_list, current_source_folder = get_bin_items()

            if self.add_mov_mp4.isChecked():
                # Если флаг активен — обрабатываем ВСЕ расширения в одном потоке
                all_exts = (".mxf", ".braw", ".arri", ".mov", ".r3d", ".mp4", ".dng", ".jpg", ".cine")
                clips_dict = get_sep_resolution_list(cur_bin_items_list, extentions=all_exts)
                new_timelines = get_timelines(clips_dict)
                if new_timelines is None:
                    self.thread.error_signal.emit("Не удалось создать ни одного таймлайна.")
                    logger.debug("Не удалось создать ни одного таймлайна.")
                    return
                render_queue = get_render_list(new_timelines, folder_name)
                start_render(render_queue)
                continue  # Пропускаем остальной блок

            # Если флаг НЕ активен — отдельно обрабатываем .mov, .mp4, .jpg
            filterd_clips = copy_filtered_clips_to_ocf_folder(current_source_folder)
            if filterd_clips is None:
                return

            if filterd_clips:
                filtred_clips_dict = get_sep_resolution_list(filterd_clips, extentions=('.mov', '.mp4', '.jpg'))
                get_timelines(filtred_clips_dict)
                self.media_pool.SetCurrentFolder(current_source_folder)

            # Логика для доработки
            if self.logic_mode_1080.isChecked():
                clips_dict = {"1920x1080": cur_bin_items_list}
            else:
                clips_dict = get_sep_resolution_list(cur_bin_items_list)

            new_timelines = get_timelines(clips_dict)

            if new_timelines is None:
                self.thread.error_signal.emit("Не удалось создать ни одного таймлайна.")
                return
            
            render_queue = get_render_list(new_timelines, folder_name)
            if render_queue is None:
                return

            start_render_var = start_render(render_queue)
            if not start_render_var:
                self.thread.error_signal.emit("Ошибка запуска рендера")
                return

        self.thread.success_signal.emit()

if __name__ == "__main__":
    app = QtWidgets.QApplication(sys.argv)
    apply_style(app)
    gui = ResolveGUI()
    gui.show()
    sys.exit(app.exec_())

