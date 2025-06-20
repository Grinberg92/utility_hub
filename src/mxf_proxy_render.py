import sys
import os
import random
import re
import math
import time
import DaVinciResolveScript as dvr
from PyQt5 import QtWidgets, QtCore
from dvr_tools.logger_config import get_logger
from dvr_tools.css_style import apply_style

logger = get_logger(__file__)

class RenderThread(QtCore.QThread):

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
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Proxy Render")
        self.resize(470, 500)
        self.setWindowFlag(QtCore.Qt.WindowStaysOnTopHint)

        # === Глобальные переменные ===
        self.glob_width = QtWidgets.QLineEdit("1920")
        self.glob_width.setFixedWidth(50)
        self.glob_height = QtWidgets.QLineEdit("1080")
        self.glob_height.setFixedWidth(50)
        self.output_folder = QtWidgets.QLineEdit("J:/003_transcode_to_vfx/kraken/tst")

        self.project_preset = QtWidgets.QComboBox()
        self.render_preset = QtWidgets.QComboBox()

        self.lut_project = QtWidgets.QComboBox()
        self.lut_file = QtWidgets.QComboBox()
        self.apply_arricdl_lut = QtWidgets.QCheckBox("Apply ARRI CDL LUT")

        self.set_fps_checkbox = QtWidgets.QCheckBox("Set Project FPS")
        self.project_fps_value = QtWidgets.QLineEdit("24")
        self.project_fps_value.setFixedWidth(50)

        self.set_burn_in_checkbox = QtWidgets.QCheckBox("Set Burn in")
        self.add_mov_mp4 = QtWidgets.QCheckBox("Add .mov, .mp4, .jpg")

        self.ocf_folders_list = QtWidgets.QListWidget()
        self.ocf_folders_list.setSelectionMode(QtWidgets.QAbstractItemView.MultiSelection)

        self.lut_path_nx = r'C:\ProgramData\Blackmagic Design\DaVinci Resolve\Support\LUT\LUTS_FOR_PROXY'
        self.lut_path_posix = '/Library/Application Support/Blackmagic Design/DaVinci Resolve/LUT/LUTS_FOR_PROXY/'
        self.lut_base_path = self.lut_path_posix if os.name == "posix" else self.lut_path_nx

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

        # === Presets group ===
        presets_group = QtWidgets.QGroupBox("Presets")
        presets_layout = QtWidgets.QVBoxLayout()
        presets_layout.addWidget(QtWidgets.QLabel("Project Preset:"))
        presets_layout.addWidget(self.project_preset)
        presets_layout.addWidget(QtWidgets.QLabel("Render Preset:"))
        presets_layout.addWidget(self.render_preset)
        presets_group.setLayout(presets_layout)
        layout.addWidget(presets_group)

        # === Color group ===
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

        # === FPS group ===
        fps_group = QtWidgets.QGroupBox("FPS")
        fps_layout = QtWidgets.QHBoxLayout()
        fps_layout.addWidget(self.set_fps_checkbox)
        fps_layout.addSpacing(10)
        fps_layout.addWidget(QtWidgets.QLabel("FPS:"))
        fps_layout.addWidget(self.project_fps_value)
        fps_layout.addStretch()
        fps_group.setLayout(fps_layout)
        layout.addWidget(fps_group)

        # === Advanced Group ===

        adv_group = QtWidgets.QGroupBox("Advanced Group")
        adv_layout = QtWidgets.QHBoxLayout()
        adv_layout.addWidget(self.set_burn_in_checkbox)
        self.set_burn_in_checkbox.setChecked(True)
        adv_layout.addSpacing(20)
        adv_layout.addWidget(self.add_mov_mp4)
        self.ocf_folders_list = QtWidgets.QListWidget()
        self.ocf_folders_list.setSelectionMode(QtWidgets.QAbstractItemView.MultiSelection)
        self.ocf_folders_list.setVerticalScrollBarPolicy(QtCore.Qt.ScrollBarAsNeeded)
        self.ocf_folders_list.setFixedHeight(100) 
        adv_layout.addSpacing(20)
        adv_layout.addWidget(self.ocf_folders_list)
        adv_group.setLayout(adv_layout)
        layout.addWidget(adv_group)
        adv_layout.addStretch()

        # === Render path ===
        path_layout = QtWidgets.QHBoxLayout()
        path_layout.addWidget(QtWidgets.QLabel("Render Path:"))
        path_layout.addWidget(self.output_folder)
        path_btn = QtWidgets.QPushButton("Choose")
        path_btn.clicked.connect(self.select_folder)
        path_layout.addWidget(path_btn)
        layout.addLayout(path_layout)

        # === Start button ===
        self.start_button = QtWidgets.QPushButton("Start")
        self.start_button.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Fixed)
        self.start_button.clicked.connect(self.start_render)
        layout.addWidget(self.start_button)

        self.load_ocf_subfolders()

    # === Функции LUT ===
    def update_lut_projects(self):
        """ Сканирует подпапки в LUT-папке """
        if os.path.isdir(self.lut_base_path):
            subfolders = [name for name in os.listdir(self.lut_base_path)
                        if os.path.isdir(os.path.join(self.lut_base_path, name))]
            self.lut_project.clear()
            self.lut_project.addItems(subfolders)
            if subfolders:
                self.lut_project.setCurrentIndex(0)
                self.update_lut_files()

    def update_lut_files(self):
        """ Сканирует .cube файлы в выбранной папке LUT """
        selected_project = self.lut_project.currentText()
        selected_path = os.path.join(self.lut_base_path, selected_project)
        if os.path.isdir(selected_path):
            cube_files = [f for f in os.listdir(selected_path)
                        if f.lower().endswith(".cube")]
            cube_files.insert(0, "No LUT")
            self.lut_file.clear()
            self.lut_file.addItems(cube_files)

    def get_project_preset_list(self):
        project_preset_list = [preset["Name"] for preset in self.project.GetPresetList()]
        self.project_preset.addItems(project_preset_list)

    def get_render_preset_list(self):
        render_presets_list = [preset for preset in self.project.GetRenderPresetList()]
        self.render_preset.addItems(render_presets_list)

    # === Выбор папки ===
    def select_folder(self):
        folder = QtWidgets.QFileDialog.getExistingDirectory(self, "Выбор папки")
        if folder:
            self.output_folder.setText(folder)

    def load_ocf_subfolders(self):
        root_folder = self.media_pool.GetRootFolder()
        ocf_folder = next((f for f in root_folder.GetSubFolderList() if f.GetName() == "001_OCF"), None)
        
        if not ocf_folder:
            self.thread.error_signal.emit("Папка '001_OCF' не найдена")
            return
        
        self.ocf_folders_list.clear()
        self.ocf_folders_list.addItem("Current Folder")
        for subfolder in ocf_folder.GetSubFolderList():
            item = QtWidgets.QListWidgetItem(subfolder.GetName())
            item.setData(QtCore.Qt.UserRole, subfolder)  # Привязываем MediaPoolFolder
            self.ocf_folders_list.addItem(item)

        # Установка Current Folder по умолчанию
        self.ocf_folders_list.setCurrentRow(0)
        self.ocf_folders_list.item(0).setSelected(True)


    def start_render(self):
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

        if not self.ocf_folders_list.selectedItems():
            QtWidgets.QMessageBox.warning(self, "Предупреждение", "Укажите хотя бы один фолдер")
            logger.warning("Укажите хотя бы один фолдер")
            return 

        logger.debug("\n".join(("SetUp:", f"Рендер с параметрами: {glob_width}x{glob_height}",
                      f"Папка: {output_folder}",f"Проектный пресет: {project_preset}", 
                      f"Рендер-пресет: {render_preset}", f"LUT Project: {self.lut_project.currentText()}", 
                      f"LUT file: {self.lut_file.currentText()}", f"ArriCDLandLUT: {self.apply_arricdl_lut.isChecked()}", 
                      f"Set FPS: {self.set_fps_checkbox.isChecked()}", f"FPS: {self.project_fps_value.text()}", 
                      f"Set Burn in: {self.set_burn_in_checkbox.isChecked()}", f"Add .mov, .mp4, .jpg: {self.add_mov_mp4.isChecked()}",
                      f"Folder: {[item.data(QtCore.Qt.UserRole) for item in self.ocf_folders_list.selectedItems()]}")))
        
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
        logger.critical(f"{message}")

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
                        self.thread.error_signal.emit(f"Не удалось создать папку '{source_folder_name}' внутри 'mov_mp4_jpg'.")
                        return None
                    
            # Переключаемся в нужный подбин
            self.media_pool.SetCurrentFolder(target_folder)
            
            return clips_to_move
        
        def set_project_fps(clip):

            "Функция устанавливает проектный FPS"
            clip.SetClipProperty("FPS", self.project_fps_value.text())
            logger.debug(f"Установлен FPS {self.project_fps_value.text()} на клип {clip.GetName()}")

        def get_bin_items():
            cur_bin_items_list = []
            curr_source_folder = self.media_pool.GetCurrentFolder()
            for clip in curr_source_folder.GetClipList():
                name = clip.GetName().lower()
                if "." in name:
                    if self.add_mov_mp4.isChecked() or not name.endswith(('.mov', '.mp4', '.jpg')):
                        if self.set_fps_checkbox.isChecked() and float(clip.GetClipProperty("FPS")) != float(self.project_fps_value.text()):
                            set_project_fps(clip)
                        cur_bin_items_list.append(clip)

            logger.debug(f"Получен список таймлайн объектов в фолдере {curr_source_folder.GetName()}")
            return cur_bin_items_list, curr_source_folder
        
        def turn_on_burn_in(aspect):

            "Функция устанавливает пресет burn in"

            if not self.set_burn_in_checkbox.isChecked():
                self.project.LoadBurnInPreset("python_no_burn_in")
                logger.debug("Применен пресет burn in: python_no_burn_in")    
            else:
                if aspect == "anam":
                    self.project.LoadBurnInPreset("python_proxy_preset_anam")
                    logger.debug("Применен пресет burn in: python_proxy_preset_anam") 

                elif aspect == "square":
                    self.project.LoadBurnInPreset("python_proxy_preset_square") 
                    logger.debug("Применен пресет burn in: python_proxy_preset_square")

        def set_project_preset():

            "Функция устанавливает пресет проекта"

            if self.project.SetPreset(project_preset):
                logger.debug(f"Применен пресет проекта: {project_preset}")
            else:
                logger.debug(f"Ошибка: Не удалось применить пресет проекта {project_preset}")

        def get_sep_resolution_list(cur_bin_items_list, extentions=None):

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
        
        def get_timelines(clips_dict):

            "Функция создает таймлайны"
            new_timelines = []
            for res, items in clips_dict.items():
                random_number = random.randint(10000, 999999)  # Генерируем случайное число
                timeline_name = f"tmln_{res}_{random_number}"  # Пример: tmln_1920x660_212066
                timeline = self.media_pool.CreateEmptyTimeline(timeline_name)
                self.project.SetCurrentTimeline(timeline)
                self.media_pool.AppendToTimeline(items)
                
                if timeline:
                    logger.debug(f"Создан таймлайн: {timeline_name}")
                    new_timelines.append(timeline)
                else:
                    logger.critical(f"Ошибка при создании таймлайна: {timeline_name}")

            if not new_timelines:
                logger.debug("Не удалось создать ни одного таймлайна.")
            return new_timelines
        
        def set_lut():

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

        def get_render_list(new_timelines):

            "Функция создает рендер джобы из всех собранных таймлайнов"
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
                    "TargetDir": output_folder,
                    "FormatWidth": int(width), 
                    "FormatHeight": int(height)
                }
                self.project.SetRenderSettings(render_settings)        

                # Добавляем в очередь рендера
                render_item = self.project.AddRenderJob()  
                render_list.append((render_item, timeline_name))
            return render_list
        
        def rendering_in_progress():

            "Функция проверяеет есть ли активный рендер"
            return self.project.IsRenderingInProgress()
        
        def start_render(render_queue):

            "Функция запуска рендера"
            logger.debug("Запускаю рендер...")
            for render, timeline_name in render_queue:
                resolution = re.search(r'\d{3,4}x\d{3,4}', timeline_name).group(0)
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
                self.project.StartRendering(render)

            # Ожидаем завершения последнего активного рендера
            while rendering_in_progress():
                time.sleep(1)


        # Основной блок
        
        selected_folders = [item.data(QtCore.Qt.UserRole) for item in self.ocf_folders_list.selectedItems()]

        # Установка пресета проекта
        set_project_preset()

        # Цикл по выбранным в GUI фолдерам selected_folders
        for folder in selected_folders:

            if folder is None: # None = Current Folder в интерфейсе
                ...
            else:
                logger.debug(f"Начало работы с фолдером {folder.GetName()}")
                current_source_folder = self.media_pool.SetCurrentFolder(folder)
            cur_bin_items_list, current_source_folder = get_bin_items()

            if self.add_mov_mp4.isChecked():
                # Если флаг активен — обрабатываем ВСЕ расширения в одном потоке
                all_exts = (".mxf", ".braw", ".arri", ".mov", ".r3d", ".mp4", ".dng", ".jpg", ".cine")
                clips_dict = get_sep_resolution_list(cur_bin_items_list, extentions=all_exts)
                new_timelines = get_timelines(clips_dict)
                render_queue = get_render_list(new_timelines)
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

            # Основные целевые клипы
            if self.render_preset.currentText() == "MXF_AVID_HD_Render":
                clips_dict = {"1920x1080": cur_bin_items_list}
            else:
                clips_dict = get_sep_resolution_list(cur_bin_items_list)

            new_timelines = get_timelines(clips_dict)
            render_queue = get_render_list(new_timelines)
            start_render(render_queue)

        self.thread.success_signal.emit()

if __name__ == "__main__":
    app = QtWidgets.QApplication(sys.argv)
    apply_style(app)
    gui = ResolveGUI()
    gui.show()
    sys.exit(app.exec_())

