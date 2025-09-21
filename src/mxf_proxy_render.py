import sys
import os
import random
import re
import math
import time
from pprint import pformat
from pathlib import Path
import DaVinciResolveScript as dvr
from PyQt5 import QtWidgets, QtCore
from PyQt5.QtWidgets import (QComboBox, QListView, QLineEdit, QRadioButton,
                             QCheckBox, QLabel, QMessageBox, QWidget, QVBoxLayout,
                             QGroupBox, QHBoxLayout, QPushButton, QSizePolicy, QFileDialog)
from PyQt5.QtGui import QStandardItemModel, QStandardItem
from PyQt5.QtCore import Qt, QThread, pyqtSignal
from dvr_tools.logger_config import get_logger
from dvr_tools.css_style import apply_style
from dvr_tools.resolve_utils import ResolveTimelineItemExtractor, ResolveObjects

logger = get_logger(__file__)

SETTINGS = {
    "burn_in_win_path": r"J:\003_transcode_to_vfx\projects\Others\burn_in_presets",
    "burn_in_mac_path": r"/Volumes/share2/003_transcode_to_vfx/projects/Others/burn_in_presets",
    "lut_path_win": r'C:\ProgramData\Blackmagic Design\DaVinci Resolve\Support\LUT\LUTS_FOR_PROXY',
    "lut_path_mac": r'/Library/Application Support/Blackmagic Design/DaVinci Resolve/LUT/LUTS_FOR_PROXY/',
    "timeline_preset_path_win": r"J:\003_transcode_to_vfx\projects\Others\timeline_presets\logc4_to_rec709.drt",
    "timeline_preset_path_mac": r"/Volumes/share2/003_transcode_to_vfx/projects/Others/timeline_presets/logc4_to_rec709.drt",
    "all_extensions": (".mxf", ".braw", ".arri", ".mov", ".r3d", ".mp4", ".dng", ".jpg", ".cine"),
    "standart_extensions": (".mxf", ".braw", ".arri", ".r3d", ".dng", ".cine"),
    "excepted_extensions": ('.mov', '.mp4', '.jpg')
}

class RenderPipline:
    """
    Класс создания OTIO таймлайна.
    """
    def __init__(self, user_config, signals):
        self.user_config = user_config
        self.signals = signals

    def set_project_preset(self) -> None:
        """
        Метод устанавливает пресет проекта.
        """
        if self.project.SetPreset(self.project_preset):
            logger.info(f"Применен пресет проекта: {self.project_preset}")
        else:
            logger.info(f"Ошибка: Не удалось применить пресет проекта {self.project_preset}")

    def auto_sync_audio(self, source_items) -> None:
        """
        Функция делает автосинхронизацию видео и звука по таймкоду в текущем фолдере.
        """
        result_sync = self.media_pool.AutoSyncAudio(source_items, {self.resolve.AUDIO_SYNC_MODE: self.resolve.AUDIO_SYNC_TIMECODE})

        if result_sync:
            logger.info("Синхронизация звука произведена успешно")
        else:
            self.signals.error_signal.emit("Синхронизация звука не произведена")

    def set_project_fps(self, clip) -> None:
        """
        Функция устанавливает проектный FPS.
        """
        clip.SetClipProperty("FPS", self.project_fps)
        logger.info(f"Установлен FPS {self.project_fps} на клип {clip.GetName()}")

    def get_resolution(self, timeline_name)-> str:
        """
        Метод извлечения разрешения из входящего имени таймлайна.
        """
        return re.search(r'\d{3,4}x\d{3,4}', timeline_name).group(0)
    
    def extract_resolution_value(self, timeline) -> tuple:
        """
        Извлекает и возвращает значения ширины и высоты разрешения.
        """
        timeline_name = timeline.GetName()
        resolution = self.get_resolution(timeline_name)
        width, height = resolution.split("x")

        logger.info(f"Добавляю в очередь рендеринга: {timeline_name}")

        return timeline_name, width, height
    
    def set_import_timeline_resolution(self, timeline_name, timeline) -> None:
        """
        Установка разрешения на таймлайн (таймлайн импортируется без привязки к проектному разрешению).
        """
        resolution = self.get_resolution(timeline_name)
        width, height = resolution.split("x")
        timeline.SetSetting("timelineResolutionHeight", height)
        timeline.SetSetting("timelineResolutionWidth", width)

    def remove_import_items(self, timeline):
        """
        Удаляет клип-заглушку присутсвующую при импорте шаблона(видео + аудио) в медиапуле и таймлайне.
        """
        mp_obj = ResolveTimelineItemExtractor(timeline)
        self.media_pool.DeleteClips([mp_obj.get_timeline_items(1, 1)[0].GetMediaPoolItem()])
        timeline.DeleteClips([mp_obj.get_timeline_items(1, 1)[0],mp_obj.get_timeline_items(1, 1, track_type='audio')[0]], True)

    def set_render_preset(self) -> None:
        """
        Применяем пресет рендера.
        """
        if self.project.LoadRenderPreset(self.render_preset):
            logger.info(f"Применен пресет рендера: {self.render_preset}")
        else:
            logger.critical(f"Ошибка: Не удалось загрузить пресет рендера {self.render_preset}")

    def set_render_settings(self, folder, width, height) -> None:
        """
        Устанавливаем настройки рендера.
        """
        render_settings = {
            "TargetDir": str(folder),
            "FormatWidth": int(width), 
            "FormatHeight": int(height)
        }
        self.project.SetRenderSettings(render_settings) 

    def rendering_in_progress(self)-> bool:
        """
        Метод проверяеет есть ли текущий активный рендер.
        """
        return self.project.IsRenderingInProgress()
    
    def choose_burnin_type(self, height):
        """
        Выбор пресета burn in.
        """

        if int(height) < 1000:
            self.turn_on_burn_in("anam")
        else:
            self.turn_on_burn_in("square")

    def get_bin_items(self) -> list:
        """
        Функция получает mediapoolitems из текущего фолдера.
        Опционально синхрит звук в текущем фолдере и устанавливает fps.
        """
        source_items = []
        current_source_folder = self.media_pool.GetCurrentFolder()
        items_list = current_source_folder.GetClipList()

        if self.auto_sync:
            self.auto_sync_audio(items_list)

        for clip in items_list:
            name = clip.GetName().lower()
            if clip.GetClipProperty("Type") == "Video" or "." in name:
                if self.add_all_extensions or not name.endswith(SETTINGS["excepted_extensions"]):
                    if self.set_fps and float(clip.GetClipProperty("FPS")) != float(self.project_fps):
                        self.set_project_fps(clip)
                    source_items.append(clip)

        logger.info(f"Получен список mediapool объектов в фолдере {current_source_folder.GetName()}")
        return source_items, current_source_folder

    def get_filtered_clips(self, current_source_folder) -> list:
        """
        Ищет .mov, .mp4, .jpg клипы в current_source_folder и перемещает их в
        source_folder/Excepted clips/{current_source_folder}.
        """
        valid_extensions = SETTINGS["excepted_extensions"]
        root_folder = self.media_pool.GetRootFolder()

        # Находим папку source_root_folder
        target_source_folder = next((f for f in root_folder.GetSubFolderList() if f.GetName() == self.source_root_folder), None)
        if not target_source_folder:
            self.signals.error_signal.emit(f"Папка '{self.source_root_folder}' не найдена")
            return None

        # Находим или создаем папку Excepted clips
        target_excepted_folder = next((f for f in target_source_folder.GetSubFolderList() if f.GetName() == "Excepted clips"), None)
        if not target_excepted_folder:
            target_excepted_folder = self.media_pool.AddSubFolder(target_source_folder, "Excepted clips")
            if not target_excepted_folder:
                self.signals.error_signal.emit("Не удалось создать папку 'Excepted clips'.")
                return None
            
        def collect_valid_clips(folder) -> list:
            """
            Функция формирует список 'отбракованных' mov, mp4, jpg.
            """
            collected = []

            for clip in folder.GetClipList():
                name = clip.GetName().lower()
                if any(name.endswith(ext.lower()) for ext in valid_extensions):
                    if self.set_fps and float(clip.GetClipProperty("FPS")) != float(self.project_fps):
                        self.set_project_fps(clip)
                    collected.append(clip)

            for subfolder in folder.GetSubFolderList():
                collected.extend(collect_valid_clips(subfolder))
            return collected

        clips_to_move = collect_valid_clips(current_source_folder)

        if not clips_to_move:
            logger.info("Нет .mov, .jpg, .mp4 клипов для перемещения.")
            self.media_pool.SetCurrentFolder(current_source_folder) 
            return []
        else:
            # Создать вложенную подпапку с именем текущего исходного бин-фолдера
            source_folder_name = current_source_folder.GetName()
            target_folder = next((f for f in target_excepted_folder.GetSubFolderList() if f.GetName() == source_folder_name), None)
            if not target_folder:
                target_folder = self.media_pool.AddSubFolder(target_excepted_folder, source_folder_name)
                if not target_folder:
                    self.signals.error_signal.emit(f"Не удалось создать папку '{source_folder_name}' внутри 'Excepted clips'.")
                    return None
                
        # Переключаемся в нужный подбин
        self.media_pool.SetCurrentFolder(target_folder)
        
        return clips_to_move
        
    def get_resolutions_dict(self, source_items, extensions=None) -> dict:
        """
        Метод создает словать с парами ключ(разрешение): значение(список соответствующих клипов).
        Каждому ключу-разрешению соответствует значение в виде списка клипов с соответствующим разрешением.
        """
        logger.info(f"Используются расширения {extensions}")
        sorted_resolutions = {}
        for clip in source_items:
                if clip.GetName() != '' and clip.GetName().lower().endswith(extensions):
                    # Находит анаморф, вычисляет ширину по аспекту
                    if clip.GetClipProperty('PAR') != 'Square' and clip.GetClipProperty('PAR'):
                        aspect = clip.GetClipProperty('PAR')
                        width, height = clip.GetClipProperty('Resolution').split('x')
                        calculate_height = str((math.ceil(((int(height) / float(aspect)) * int(self.glob_width) / int(width) ) / 2) * 2))
                        resolution = "x".join([self.glob_width, calculate_height])
                        sorted_resolutions.setdefault(resolution, []).append(clip)
                    else:
                        aspect = clip.GetClipProperty('PAR')
                        width, height = clip.GetClipProperty('Resolution').split('x')
                        calculate_height = str((math.ceil((int(height) * int(self.glob_width) / int(width)) / 2) * 2))
                        resolution = "x".join([self.glob_width, calculate_height])
                        sorted_resolutions.setdefault(resolution, []).append(clip)

        return sorted_resolutions
    
    def main_cam_detect(self, clip_list):
        """
        Разделяет клипы на клипы основной камеры и остальных.
        """
        main_cam_clips = []
        other_clips = []

        for clip in clip_list:
            video_codec = clip.GetClipProperty("Video Codec").lower()
            ics = clip.GetClipProperty("Input Color Space").lower()
            if "arri" in video_codec or "arri" in ics:
                main_cam_clips.append(clip)
            else:
                other_clips.append(clip)

        return main_cam_clips, other_clips

    def get_timelines(self, sorted_resolutions) -> list:
        """
        Метод формирует таймлайны на основе данных из sorted_resolutions.
        """
        timelines = []  

        for res, items in sorted_resolutions.items():
            main_cam_clips, other_clips = self.main_cam_detect(items)

            def make_timeline(clips, is_main):
                random_number = random.randint(10000, 999999)
                suffix = "main_cam" if is_main else "mixed"
                timeline_name = f"tmln_{res}_{suffix}_{random_number}"

                if is_main and self.apply_arri_cdl and self.lut_to_log:

                    timeline = self.media_pool.ImportTimelineFromFile(self.timeline_preset_path) # Импорт шаблона таймлайна с loc4 to rec709 трансформом
                        
                    if not timeline:
                        logger.critical(f"Отсутствует шаблон таймлайна для ARRI: {self.timeline_preset_path_posix}")
                        return None

                    self.set_import_timeline_resolution(timeline_name, timeline)

                    timeline.SetName(timeline_name)

                    self.remove_import_items(timeline)

                    self.media_pool.AppendToTimeline(clips)
                else:
                    timeline = self.media_pool.CreateEmptyTimeline(timeline_name)
                    self.project.SetCurrentTimeline(timeline)
                    self.media_pool.AppendToTimeline(clips)
                    if not self.lut_to_log and is_main:
                        timeline.SetSetting('useCustomSettings', '1')
                        timeline.SetSetting("colorScienceMode", "davinciYRGB")
                        self.set_import_timeline_resolution(timeline_name, timeline)
                        

                if timeline:
                    logger.info(f"Создан таймлайн: {timeline_name}")
                    timelines.append(timeline)
                else:
                    logger.critical(f"Ошибка при создании таймлайна: {timeline_name}")

            # Таймлайн для основной камеры
            if main_cam_clips:
                make_timeline(main_cam_clips, is_main=True)

            # Таймлайн для прочих камер
            if other_clips:
                make_timeline(other_clips, is_main=False)

        if not timelines:
            logger.info("Не удалось создать ни одного таймлайна.")
        return timelines

    def extension_filter(self, current_source_folder, source_items) -> tuple:
        """
        Определяет с какими расширениями работать.
        Возвращает кортеж (расширения, список исходников для рендера).
        При self.add_all_extensions берём все расширения,
        иначе вручную обрабатываем mov/mp4/jpg, а в основной поток идёт только source_items.
        """
        if self.add_all_extensions:
            extensions = SETTINGS["all_extensions"]
            return extensions, source_items
        else:
            filtred_clips = self.get_filtered_clips(current_source_folder)

            if filtred_clips is None:
                return None, None
            
            if filtred_clips:
                filtred_sorted_resolutions = self.get_resolutions_dict(filtred_clips, extensions=SETTINGS["excepted_extensions"])
                self.get_timelines(filtred_sorted_resolutions)
                self.media_pool.SetCurrentFolder(current_source_folder)

            extensions = SETTINGS["standart_extensions"]
            return extensions, source_items
        
    def set_sound_folder(self, current_folder_list, current_folder)-> None:
        """
        Метод создает фолдер 'SOUND' в корне текущего фолдера и переносит в него звук из текущего фолдера.
        """
        sound_list = [i for i in current_folder_list if i.GetClipProperty("Type") == "Audio"]

        base_folder = next((f for f in current_folder.GetSubFolderList() if f.GetName() == "SOUND"), None)
        if not base_folder:
            base_folder = self.media_pool.AddSubFolder(current_folder, "SOUND")
            if not base_folder:
                self.signals.error_signal.emit("Не удалось создать папку 'SOUND'.")
                return None

        logger.info("Звук перенесен в папку 'SOUND'")
        self.media_pool.MoveClips(sound_list, base_folder)
        self.media_pool.SetCurrentFolder(current_folder) 

    def set_lut(self) -> None:
        """
        Метод устанавливает заданный LUT(распаковывает AriiCDLLut) на все клипы на таймлайне.
        """
        self.project.RefreshLUTList()

        if not self.apply_arri_cdl and self.lut_file == "No LUT":
            logger.info(f"LUT не применялся")
            return
        
        current_timeline = self.project.GetCurrentTimeline()

        for track in range(1, current_timeline.GetTrackCount("video") + 1):
            for tmln_item in current_timeline.GetItemListInTrack("video", track):

                if self.apply_arri_cdl:
                    tmln_item.GetNodeGraph(1).ApplyArriCdlLut()  

                if self.lut_file != "No LUT":
                    lut_path = os.path.join(self.lut_path, self.lut_project_folder, self.lut_file)
                    tmln_item.SetLUT(1, lut_path)

        logger.info(f"LUT установлен на все клипы на таймлайне {current_timeline.GetName()}")

    def get_render_list(self, timelines, folder_name)-> list:
        """
        Метод создает render job из всех собранных таймлайнов.
        """
        try:
            folder = Path(self.output_folder) / folder_name
            
            logger.info(f"Путь рендера: {folder}")

            render_list = []
            for timeline in timelines:

                self.project.SetCurrentTimeline(timeline)  # Переключаемся на текущий таймлайн

                self.set_lut()

                timeline_name, width, height = self.extract_resolution_value(timeline)

                self.set_render_preset()
                
                self.set_render_settings(folder, width, height)     

                # Добавляем в очередь рендера
                render_item = self.project.AddRenderJob()  
                render_list.append((render_item, timeline_name))

            return render_list
        except Exception as e:
            self.signals.error_signal.emit(f"Ошибка создания списка с рендер задачами: {e}")
            return None
        
    def turn_on_burn_in(self, aspect):
        """
        Метод устанавливает пресет burn in.
        """
        try:
            preset_list = [preset[1] for preset in self.burnin_list]

            if not self.set_burnin:
                self.project.LoadBurnInPreset("python_no_burn_in")
                logger.info("Применен пресет burn in: python_no_burn_in")    
            else:
                for preset in preset_list:
                    if re.search(aspect, preset):
                        self.project.LoadBurnInPreset(preset)
                        logger.info(f"Применен пресет burn in: {preset}") 
        except Exception as e:
            self.signals.error_signal.emit("Ошибка применения пресета burn in")
        
    def start_render(self, render_queue)-> bool:
        """
        Метод запуска рендера.
        """
        logger.info("Запускаю рендер...")

        for render, timeline_name in render_queue:
            resolution = self.get_resolution(timeline_name)
            width, height = resolution.split("x")

            # Проверяем закончился ли предыдущий рендер
            while self.rendering_in_progress():
                time.sleep(1)

            logger.info(f"Разрешение {resolution}")

            # Установка разрешения в настройки проекта
            self.project.SetSetting("timelineResolutionWidth", width)
            self.project.SetSetting("timelineResolutionHeight", height)

            self.choose_burnin_type(height)

            start_render_var = self.project.StartRendering(render)
            if not start_render_var:
                return None      

        # Ожидаем завершения последнего активного рендера
        while self.rendering_in_progress():
            time.sleep(1)
        return True 

    def run(self):
        """
        Основная логика.
        """
        self.glob_width = self.user_config["glob_width"]
        self.glob_height = self.user_config["glob_height"]
        self.subfolders_list = self.user_config["subfolders_list"]
        self.project_preset = self.user_config["project_preset"]
        self.auto_sync = self.user_config["auto_sync"]
        self.add_all_extensions = self.user_config["add_all_extensions"]
        self.set_fps = self.user_config["set_fps"]
        self.project_fps = self.user_config["project_fps"]
        self.create_sound_folder = self.user_config["create_sound_folder"]
        self.source_root_folder = self.user_config["source_root_folder"]
        self.apply_arri_cdl = self.user_config["apply_arri_cdl"]
        self.output_folder = self.user_config["output_folder"]
        self.render_preset = self.user_config["render_preset"]
        self.lut_file = self.user_config["lut_file"]
        self.lut_path = self.user_config["lut_path"]
        self.lut_project_folder = self.user_config["lut_project_folder"]
        self.logic_fullhd = self.user_config["logic_fullhd"]
        self.set_burnin = self.user_config["set_burnin"]
        self.burnin_list = self.user_config["burnin_list"]
        self.timeline_preset_path = self.user_config["timeline_preset_path"]
        self.media_pool = self.user_config["media_pool"] # Тянем медиапул который использовался в GUI
        self.project = self.user_config["project_resolve"]
        self.lut_to_log = self.user_config["LUT_to_log"]

        self.obj = ResolveObjects()
        self.resolve = self.obj.resolve_obj

        # Установка пресета проекта
        self.set_project_preset()

        # Цикл по выбранным в GUI фолдерам selected_folders
        for folder_obj, folder_name in self.subfolders_list:
            
            # Определяем и переключаемся на фолдер с которым будем работать
            if folder_obj is not None:  # None = Current Folder в интерфейсе
                logger.info(f"Начало работы с фолдером {folder_obj.GetName()}")
                self.media_pool.SetCurrentFolder(folder_obj)
            else:
                folder_name = self.media_pool.GetCurrentFolder().GetName()

            # Получаем клипы в текущем фолдере
            source_items, current_source_folder = self.get_bin_items()

            # Опционально создаем папку 'SOUND'
            if self.create_sound_folder:
                self.set_sound_folder(source_items, current_source_folder)

            # Формируем таймлайны с extension clips(если есть) и получаем расширения и список видеоматериала для дальнейшей работы  
            extensions, filtred_source_items = self.extension_filter(current_source_folder, source_items)
            if extensions is None:
                return

            # Выбор логики обработки
            if self.logic_fullhd:
                sorted_resolutions = {"1920x1080": filtred_source_items}
            else:
                sorted_resolutions = self.get_resolutions_dict(filtred_source_items, extensions=extensions)

            # Получаем таймлайны разделенные по выходному разрешению рендера
            timelines = self.get_timelines(sorted_resolutions)
            if timelines is None:
                self.signals.error_signal.emit("Не удалось создать ни одного таймлайна.")
                return

            # Получаем список render job объектов
            render_queue = self.get_render_list(timelines, folder_name)
            if render_queue is None:
                return

            # Запускаем рендер
            start_render_var = self.start_render(render_queue)
            if not start_render_var:
                self.signals.error_signal.emit("Ошибка запуска рендера")
                return

        self.signals.success_signal.emit("Рендер успешно завершен")

class CheckableComboBox(QComboBox):
    """
    Кастомный класс для создания выпадающего списка с чекбоксами.
    """
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
        """
        Возвращает список кортежей: (userData, текст).
        """
        result = []
        for i in range(self.model().rowCount()):
            item = self.model().item(i)
            if item.checkState() == Qt.Checked:
                result.append((item.data(Qt.UserRole), item.text()))
        return result

    def _update_display_text(self):
        selected = [text for _, text in self.checked_items()]
        self.lineEdit().setText(", ".join(selected) if selected else "Select items")

class RenderWorker(QThread):
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
        try:
            logic = RenderPipline(self.user_config, self)
            success = logic.run()
        except Exception as e:
            self.error_signal.emit(f"Ошибка программы {e}")

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
            "glob_width": self.gui.glob_width.text().strip(),
            "glob_height": self.gui.glob_height.text().strip(),
            "logic_fullhd": self.gui.logic_mode_fullhd.isChecked(),
            "logic_frame": self.gui.logic_mode_frame.isChecked(),
            "output_folder": self.gui.output_folder.text().strip(),
            "project_preset": self.gui.project_preset.currentText(),
            "render_preset": self.gui.render_preset.currentText(),
            "lut_project_folder": self.gui.lut_project.currentText(),
            "lut_file": self.gui.lut_file.currentText(),
            "apply_arri_cdl": self.gui.apply_arricdl_lut.isChecked(),
            "set_fps": self.gui.set_fps_checkbox.isChecked(),
            "project_fps": self.gui.project_fps_value.text().strip(),
            "set_burnin": self.gui.set_burn_in_checkbox.isChecked(),
            "add_all_extensions": self.gui.add_all_extensions.isChecked(),
            "auto_sync": self.gui.auto_sync_checkbox.isChecked(),
            "create_sound_folder": self.gui.create_sound_folder.isChecked(),
            "source_root_folder": self.gui.source_root_folder.text().strip(),
            "burnin_list": self.gui.burn_in_list.checked_items(),
            "subfolders_list": self.gui.subfolders_list.checked_items(),
            "lut_path": self.gui.lut_base_path, 
            "timeline_preset_path": self.gui.timeline_preset_path, 
            "burnin_path": self.gui.burn_in_base_path,
            "media_pool": self.gui.media_pool,
            "project_resolve": self.gui.project,
            "LUT_to_log": self.gui.log_rb.isChecked()
        }
        
    def validate(self, user_config: dict) -> bool:
        """
        Валидирует конфиг.
        """
        self.errors.clear()

        if not user_config["glob_height"] or not user_config["glob_width"]:
            self.errors.append("Значения ширины или высоты не указаны")
        
        if user_config["set_fps"] and not user_config["project_fps"]:
            self.errors.append("Укажите значение FPS")
        
        if not user_config["output_folder"]:
            self.errors.append("Укажите путь для рендера")

        if user_config["set_burnin"]:
            if not user_config["burnin_list"]:
                self.errors.append("Укажите хотя бы один пресет burn-in")

        if not user_config["subfolders_list"]:
            self.errors.append("Укажите хотя бы один фолдер")

        if not os.path.exists(user_config["timeline_preset_path"]) and user_config["apply_arri_cdl"]:
            self.errors.append(f"Отсутстует програмный файл - {user_config['timeline_preset_path']}")

        if user_config["lut_file"] != "No LUT" and user_config["apply_arri_cdl"]:
            self.errors.append("Выберете либо LUT либо Apply Arri Camera LUT")
        return not self.errors

    def get_errors(self) -> list:
        return self.errors


class ResolveGUI(QWidget):
    """
    Класс GUI.
    """
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Proxy Render")
        self.resize(550, 500)
        self.setWindowFlag(Qt.WindowStaysOnTopHint)

        # Глобальные переменные
        self.glob_width = QLineEdit("1920")
        self.glob_width.setFixedWidth(50)
        self.glob_height = QLineEdit("1080")
        self.glob_height.setFixedWidth(50)

        self.logic_mode_fullhd = QRadioButton()
        self.logic_mode_frame = QRadioButton()

        self.output_folder = QLineEdit()

        self.project_preset = QComboBox()
        self.render_preset = QComboBox()

        self.lut_project = QComboBox()
        self.lut_file = QComboBox()
        self.apply_arricdl_lut = QCheckBox("Apply ARRI Camera LUT")

        self.set_fps_checkbox = QCheckBox("Set Project FPS")
        self.project_fps_value = QLineEdit("24")
        self.project_fps_value.setFixedWidth(50)

        self.label_ocf = QLabel("Choose Shoot Date:")
        self.label_root = QLabel("Choose Root Folder:")
        self.set_burn_in_checkbox = QCheckBox("Set Burn-in")
        self.add_all_extensions = QCheckBox("Use All Extensions")
        self.auto_sync_checkbox = QCheckBox("Sync Audio")
        self.create_sound_folder = QCheckBox("Create 'SOUND' Folder")
        self.source_root_folder = QLineEdit("001_OCF")
        self.lut_to_label = QLabel("LUT to:")
        self.log_rb = QRadioButton("log")
        self.rec709_rb = QRadioButton("rec709")
        self.log_rb.setChecked(True)

        self.burn_in_list = CheckableComboBox()

        self.subfolders_list = CheckableComboBox()
        self.subfolders_list.setFixedWidth(180)

        self.lut_base_path = SETTINGS["lut_path_win"] if sys.platform == "win32" else SETTINGS["lut_path_mac"]
        self.timeline_preset_path = SETTINGS["timeline_preset_path_win"] if sys.platform == "win32" else SETTINGS["timeline_preset_path_mac"]
        self.burn_in_base_path = SETTINGS["burn_in_win_path"] if sys.platform == "win32" else SETTINGS["burn_in_mac_path"]

        self.resolve = self.is_connect_resolve()

        self.init_ui()
        self.get_project_preset_list()
        self.get_render_preset_list()
        self.update_lut_projects()

    def init_ui(self):
        
        layout = QVBoxLayout(self)

        # Resolution
        res_group = QGroupBox("Resolution")
        res_group.setFixedWidth(150)
        res_group.setFixedHeight(70)
        res_layout = QHBoxLayout()
        res_layout.addStretch()
        res_layout.addWidget(self.glob_width)
        res_layout.addWidget(QLabel("x"))
        res_layout.addWidget(self.glob_height)
        res_layout.addStretch()
        res_group.setLayout(res_layout)
        layout.addWidget(res_group, alignment=Qt.AlignHCenter)

        # Logic group
        logic_group = QGroupBox("Logic")
        logic_group.setFixedHeight(70)
        logic_group.setFixedWidth(300)
        logic_layout = QHBoxLayout()

        vbox1 = QVBoxLayout()
        label_1080 = QLabel("All into FullHD")
        label_1080.setAlignment(Qt.AlignHCenter)
        vbox1.addWidget(self.logic_mode_fullhd, alignment=Qt.AlignHCenter)
        vbox1.addWidget(label_1080)

        vbox2 = QVBoxLayout()
        label_frame = QLabel("Frame to horizontal")
        label_frame.setAlignment(Qt.AlignHCenter)
        vbox2.addWidget(self.logic_mode_frame, alignment=Qt.AlignHCenter)
        vbox2.addWidget(label_frame)

        self.logic_mode_frame.setChecked(True)

        logic_layout.addStretch()
        logic_layout.addLayout(vbox1)
        logic_layout.addSpacing(60)
        logic_layout.addLayout(vbox2)
        logic_layout.addStretch()

        logic_group.setLayout(logic_layout)
        layout.addWidget(logic_group, alignment=Qt.AlignHCenter)

        # Presets group 
        presets_group = QGroupBox("Presets")
        presets_layout = QVBoxLayout()
        presets_layout.addWidget(QLabel("Project Preset:"))
        presets_layout.addWidget(self.project_preset)
        presets_layout.addWidget(QLabel("Render Preset:"))
        presets_layout.addWidget(self.render_preset)
        presets_layout.addWidget(QLabel("Burn-in Preset:"))
        presets_layout.addWidget(self.burn_in_list)
        presets_group.setLayout(presets_layout)
        layout.addWidget(presets_group)

        # Color group 
        color_group = QGroupBox("Color")
        color_layout = QVBoxLayout()
        color_layout.addWidget(QLabel("LUT Project:"))
        color_layout.addWidget(self.lut_project)
        self.lut_project.currentTextChanged.connect(self.update_lut_files)
        color_layout.addWidget(QLabel("LUT File:"))
        color_layout.addWidget(self.lut_file)
        self.apply_cdl_layout = QHBoxLayout()
        self.apply_cdl_layout.addWidget(self.apply_arricdl_lut)
        self.apply_cdl_layout.addSpacing(60)
        self.apply_cdl_layout.addWidget(self.lut_to_label)
        self.apply_cdl_layout.addWidget(self.log_rb)
        self.apply_cdl_layout.addWidget(self.rec709_rb)
        color_layout.addLayout(self.apply_cdl_layout) 
        color_group.setLayout(color_layout)
        layout.addWidget(color_group)

        # FPS group 
        fps_group = QGroupBox("FPS")
        fps_layout = QHBoxLayout()
        fps_layout.addWidget(self.set_fps_checkbox)
        fps_layout.addSpacing(10)
        fps_layout.addWidget(QLabel("FPS:"))
        fps_layout.addWidget(self.project_fps_value)
        fps_layout.addStretch()
        fps_group.setLayout(fps_layout)
        layout.addWidget(fps_group)

        # Advanced
        adv_group = QGroupBox("Advanced Settings")
        adv_main_layout = QHBoxLayout() 

        # Left column
        left_layout = QVBoxLayout()
        left_layout.setAlignment(Qt.AlignLeft)
        left_layout.addWidget(self.label_ocf)
        left_layout.addWidget(self.subfolders_list)
        self.set_burn_in_checkbox.setChecked(True)
        left_layout.addWidget(self.set_burn_in_checkbox)
        left_layout.addSpacing(10)
        self.auto_sync_checkbox.setChecked(False)
        left_layout.addWidget(self.auto_sync_checkbox)
        left_layout.addStretch()

        # Right column
        right_layout = QVBoxLayout()
        right_layout.setAlignment(Qt.AlignRight)
        right_layout.addWidget(self.label_root)
        self.source_root_folder.setFixedWidth(180)
        self.source_root_folder.editingFinished.connect(self.load_subfolders_list)
        right_layout.addWidget(self.source_root_folder)
        right_layout.addWidget(self.add_all_extensions)
        right_layout.addSpacing(10)
        right_layout.addWidget(self.create_sound_folder)
        right_layout.addStretch()

        adv_main_layout.addLayout(left_layout)
        adv_main_layout.addLayout(right_layout)

        adv_group.setLayout(adv_main_layout)
        layout.addWidget(adv_group)

        # Render path
        path_layout = QHBoxLayout()
        path_layout.addWidget(QLabel("Render Path:"))
        path_layout.addWidget(self.output_folder)
        path_btn = QPushButton("Choose")
        path_btn.clicked.connect(self.select_folder)
        path_layout.addWidget(path_btn)
        layout.addLayout(path_layout)

        # Start button
        self.start_button = QPushButton("Start")
        self.start_button.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.start_button.clicked.connect(self.start)
        layout.addWidget(self.start_button)

        self.load_subfolders_list()
        self.load_burn_in()

    def is_connect_resolve(self):
        """
        Проверка подключения к Resolve и получение базовых объектов.
        """
        try:
            self.resolve = ResolveObjects()
            self.project = self.resolve.project
            self.media_pool = self.resolve.mediapool
            self.timeline = self.resolve.timeline

        except RuntimeError as re:
            self.on_error_signal(str(re))
            sys.exit()
            return

    def on_error_signal(self, message):
        QMessageBox.critical(self, "Error", message)
        logger.exception(message)

    def on_success_signal(self, message):
        QMessageBox.information(self, "Success", message)
        logger.info(message)

    def on_warning_signal(self, message):
        QMessageBox.warning(self, "Warning", message)
        logger.warning(message)

    def on_info_signal(self, message):
        QMessageBox.information(self, "Info", message)
        logger.info(message)

    def select_folder(self):
        folder = QFileDialog.getExistingDirectory(self, "Выбор папки")
        if folder:
            self.output_folder.setText(folder)

    def update_lut_projects(self):
        """
        Метод получает подпапки в LUT-папке.
        """
        if os.path.isdir(self.lut_base_path):
            subfolders = [name for name in os.listdir(self.lut_base_path)
                        if os.path.isdir(os.path.join(self.lut_base_path, name))]
            self.lut_project.clear()
            self.lut_project.addItems(subfolders)
            if subfolders:
                self.lut_project.setCurrentIndex(0)
                self.update_lut_files()

    def update_lut_files(self):
        """
        Метод получает .cube файлы в выбранной папке LUT.
        """
        selected_project = self.lut_project.currentText()
        selected_path = os.path.join(self.lut_base_path, selected_project)
        if os.path.isdir(selected_path):
            cube_files = [f for f in os.listdir(selected_path)
                        if f.lower().endswith(".cube")]
            cube_files.insert(0, "No LUT")
            self.lut_file.clear()
            self.lut_file.addItems(cube_files)

    def load_burn_in(self):

        """
        Метод получает данные о пресетах burn-in.
        """
        preset_list = os.listdir(self.burn_in_base_path)
        preset_list_sorted = sorted(
                                    preset_list,
                                    key=lambda name: os.path.getmtime(os.path.join(self.burn_in_base_path, name)))
        
        preset_list_sorted = [i.split(".")[0] for i in preset_list_sorted]
        for preset in preset_list_sorted:
            self.burn_in_list.add_checkable_item(preset)

        self.burn_in_list._update_display_text()

    def load_subfolders_list(self):
        """
        Метод загружает сабфолдеры из папки 'source_root_folder' в CheckableComboBox.
        """
        root_folder = self.media_pool.GetRootFolder()
        source_root_folder = self.source_root_folder.text()
        ocf_folder = next((f for f in root_folder.GetSubFolderList() if f.GetName() == source_root_folder), None)

        if not ocf_folder:
            self.on_error_signal(f"Папка '{source_root_folder}' не найдена")
            return

        self.subfolders_list.clear_items()
        self.subfolders_list.add_checkable_item("Current Folder", data=None, checked=True)

        for subfolder in ocf_folder.GetSubFolderList():
            self.subfolders_list.add_checkable_item(subfolder.GetName(), data=subfolder)

    def get_project_preset_list(self):
        """
        Метод получения пресета проекта.
        """
        project_preset_list = [preset["Name"] for preset in self.project.GetPresetList()][3:] # Отрезаем системные пресеты
        self.project_preset.addItems(project_preset_list)

    def get_render_preset_list(self):
        """
        Метод получения пресета рендера.
        """     
        render_presets_list = [preset for preset in self.project.GetRenderPresetList()][31:] # Отрезаем системные пресеты
        self.render_preset.addItems(render_presets_list)

    def start(self):
        """
        Запуск основной логики.
        """
        self.validator = ConfigValidator(self)
        self.user_config = self.validator.collect_config()

        if not self.validator.validate(self.user_config):
            self.on_error_signal("\n".join(self.validator.get_errors()))
            return
        
        logger.info(f"\n\nUser Config:\n{pformat(self.user_config)}\n")

        self.main_process = RenderWorker(self, self.user_config)
        self.start_button.setEnabled(False)
        self.main_process.finished.connect(lambda : self.start_button.setEnabled(True))
        self.main_process.error_signal.connect(self.on_error_signal)
        self.main_process.success_signal.connect(self.on_success_signal)
        self.main_process.warning_signal.connect(self.on_warning_signal)
        self.main_process.info_signal.connect(self.on_info_signal)
        self.main_process.start()

if __name__ == "__main__":
    app = QtWidgets.QApplication(sys.argv)
    apply_style(app)
    gui = ResolveGUI()
    gui.show()
    sys.exit(app.exec_())