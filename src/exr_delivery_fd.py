import sys
import re
import math
import time
from pprint import pformat
from pathlib import Path

from PyQt5.QtWidgets import (
    QApplication, QWidget, QLabel, QLineEdit, QPushButton,
    QVBoxLayout, QHBoxLayout, QComboBox, QFileDialog, QMessageBox, QGroupBox, QCheckBox
)
from PyQt5.QtCore import Qt, QThread, pyqtSignal
from dvr_tools.logger_config import get_logger
from dvr_tools.css_style import apply_style
from dvr_tools.resolve_utils import ResolveObjects
from dvr_tools.resolve_utils import ResolveTimelineItemExtractor

logger = get_logger(__file__)

SETTINGS = {
    "colors": ("Orange", "Beige", "Brown", "Blue"),
    "extentions": (".mxf", ".braw", ".arri", ".r3d", ".dng", ".mov", ".mp4"),
    "reference_render_preset": "reference_preset_FD",
    "effects": ('RTS+', 'Counter'),
    "plate_prefix": 'prk_',
    "plate_suffix": '_src_v001_VT',
    "ref_prefix": 'prm_prk_',
    "ref_suffix": '_rec709'
}

class NameSetter:
    """
    Класс логики, устанавливающий имена шотов из оффлайн клипов, на все итемы,
    находящиеся ниже по таймлайну. 
    """
    def __init__(self, user_config, signals):
        self.signals = signals
        self.user_config = user_config

    def get_api_resolve(self) -> ResolveObjects:
        """
        Проверка подключения к API Resolve и получение основного объекта Resolve.
        """
        try:
            resolve = ResolveObjects().resolve
            return ResolveObjects()
        except RuntimeError as re:
            raise

    def set_markers(self, item, clip_name):
        """
        Установка маркера посередине клипа на таймлайне.
        """
        clip_start = int((item.GetStart() + (item.GetStart() + item.GetDuration())) / 2) - self.timeline_start_tc
        self.timeline.AddMarker(clip_start, 'Blue', clip_name, "", 1, 'Renamed')

    def is_effect(self, track, track_type="video"):
        """
        Проверка на предмет наличия дорожки с эффектами.
        """
        for item in self.timeline.GetItemListInTrack(track_type, track):
            if item.GetName() == "Text+":
                return True

    def set_name(self, items):
        """
        Устанавливает имена на все итемы лежащие ниже дорожки с оффлайн клипами.
        """
        for item in items:
            clipName = item.GetName()

            for track_index in range(1, self.count_of_tracks):
                clips_under = self.timeline.GetItemListInTrack('video', track_index)
                if clips_under:
                    
                    for clip_under in clips_under:

                        if clip_under.GetStart() == item.GetStart():

                            if track_index == 1 or self.is_effect(track_index):
                                name = SETTINGS["ref_prefix"] + clipName + SETTINGS["ref_suffix"]
                                clip_under.AddVersion(name, 0)
                                logger.info(f'Добавлено кастомное имя "{name}" в клип на треке {track_index}')
                            else: 
                                # Вычитаем - 1 что бы отсчет плейтов был с первой дорожки, а не второй
                                name = SETTINGS["plate_prefix"] + clipName + SETTINGS["plate_suffix"] + str(track_index - 1)
                                clip_under.AddVersion(name, 0)
                                logger.info(f'Добавлено кастомное имя "{name}" в клип на треке {track_index}')

    def run(self):
        """
        Основная логика.
        """
        resolve = self.get_api_resolve()
        self.timeline = resolve.timeline
        self.media_pool = resolve.mediapool
        self.timeline_start_tc = self.timeline.GetStartFrame()

        self.track_number = int(self.user_config["track_number"])
        self.count_of_tracks = self.timeline.GetTrackCount('video')

        items = self.timeline.GetItemListInTrack('video', self.track_number)

        if items is None:
            self.signals.warning_signal.emit(f"Дорожка {self.track_number} не существует.")
            return
        if items == []:
            self.signals.warning_signal.emit(f"На дорожке {self.track_number} отсутствуют объекты.")
            return
        
        self.set_name(items)

        self.signals.success_signal.emit("Имена из оффлайн клипов успешно применены")

class EffectsAppender:
    """
    Класс добавляет эффект счетчика кадров и эффект 
    с информацией о позиционировании или ретайме на таймлайн Resolve.
    """
    def __init__(self, user_config, signals):
        self.signals = signals

    def get_api_resolve(self) -> ResolveObjects:
        """
        Проверка подключения к API Resolve и получение основного объекта Resolve.
        """
        try:
            resolve = ResolveObjects().resolve
            return ResolveObjects()
        except RuntimeError as re:
            raise

    def find_clips_by_name(self, folder, target_name):
        '''
        Рекурсивно ищет эффекты по имени во всём медиапуле.

        :return item: Объект целевого эффекта.
        '''
        # Сначала обходим все подпапки в обратном порядке (снизу вверх)
        for subfolder in reversed(folder.GetSubFolderList()):
            item = self.find_clips_by_name(subfolder, target_name)
            if item:
                return item  # нашли в подпапке — возвращаем

        # Потом проверяем клипы в текущей папке
        for item in folder.GetClipList():
            if re.fullmatch(re.escape(target_name), item.GetName(), re.IGNORECASE):
                logger.info(f"Найден эффект: {item.GetName()}")
                return item

        return False
    
    def get_effect_in_mediapool(self) -> list:
        """
        Получение целевых эффектов в качестве объектов медиапула.
        """
        target_effects = []
        for effect_name in SETTINGS["effects"]:

            found = self.find_clips_by_name(self.root_folder, effect_name)
            if found:
                target_effects.append(found)
            else:
                logger.info(f"Эффект '{effect_name}' не найден в медиапуле.")

        return target_effects

    def get_timeline_items(self) -> list:
        """
        Список таймлайн итемов кроме клипов с расширением .mov и итемов не являющихся видео объектами.
        """
        timeline_items = []
        for track in range(1, self.timeline.GetTrackCount("video") + 1):
            clips = self.timeline.GetItemListInTrack('video', int(track))
            for clip in clips:
                if not clip.GetName().lower().endswith(('.mov')) and clip.GetMediaPoolItem():
                    timeline_items.append((clip.GetMediaPoolItem(), 
                                    clip.GetStart(), 
                                    clip.GetSourceStartFrame(),
                                    clip.GetDuration(),  
                                    clip.GetTrackTypeAndIndex()[1]))
                    
        return timeline_items
                    
    def get_items_property(self, timeline_items) -> list:
        """
        Получает свойства из клипов, для их дальнейшего применения в эффекты.
        
        :return items_property: Список свойств таймлайн итемов.

        :return max(track_indecses): Индекс самой последней дорожки с хайрезом.
        """
        items_property = []
        track_indecses = []
        for clip_attribute in timeline_items:
            media_pool_item, tmln_strt, strt_frame, duration, index = clip_attribute
            track_indecses.append(index)
            if not media_pool_item.GetName().lower().endswith(('.mov')):
                clip_info = {
                    "mediaPoolItem": media_pool_item,
                    "startFrame": strt_frame,
                    "endFrame": duration,
                    "mediaType": 1,
                    "trackIndex": index,
                    "recordFrame": tmln_strt,
                }
                items_property.append(clip_info)    

        return items_property, max(track_indecses)
    
    def set_effects_property(self, effects, items_property, max_track_ind) -> list:
        """
        Устанавливает свойства, полученные из таймлайн итемов, на эффекты.
        """
        effects_property = []
        for item_property in items_property:
            for index, effect in enumerate(effects, start=1):
                end_frame = item_property["endFrame"]
                rec_frame = item_property["recordFrame"]

                effect_property = {'mediaPoolItem': effect,
                            "startFrame": 0,      
                            "endFrame": end_frame, 
                            "mediaType": 1, 
                            "trackIndex": max_track_ind + index,      
                            "recordFrame": rec_frame }
                
                effects_property.append(effect_property)

        return effects_property

    def append_effects(self, effects_property):
        """
        Добавление эффектов на таймлайн Resolve.
        """
        result = self.media_pool.AppendToTimeline(effects_property)

        if not result:
            self.signals.error_signal.emit("Ошибка добавления эффектов")

        else:
            self.signals.success_signal.emit(f"Эффекты успешно добавлены")

    def run(self):
        """
        Основная логика.
        """
        resolve = self.get_api_resolve()
        self.timeline = resolve.timeline
        self.media_pool = resolve.mediapool
        self.root_folder = self.media_pool.GetRootFolder()

        effects = self.get_effect_in_mediapool()

        timeline_items = self.get_timeline_items()

        items_property, max_track_ind = self.get_items_property(timeline_items)
         
        effects_property = self.set_effects_property(effects, items_property, max_track_ind)

        self.append_effects(effects_property)

class DvrTimelineObject():
    """
    Объект с атрибутами итема на таймлайне.
    """
    def __init__(self, mp_item, track_type_ind, clip_start_tmln, source_start, source_end, clip_dur, clip_color):
        self.mp_item = mp_item
        self.track_type_ind = track_type_ind
        self.clip_start = clip_start_tmln
        self.clip_duration = clip_dur
        self.clip_end = self.clip_start + (self.clip_duration - 1)
        self.source_start = source_start
        self.source_end = source_end
        self.clip_color = clip_color

class DeliveryPipline:
    """
    Конвеер создания render jobs и их последующего рендера.
    """
    def __init__(self, user_config, signals):
        self.user_config = user_config
        self.signals = signals

    def get_api_resolve(self) -> ResolveObjects:
        """
        Проверка подключения к API Resolve и получение основного объекта Resolve.
        """
        try:
            resolve = ResolveObjects().resolve
            return ResolveObjects()
        except RuntimeError as re:
            raise

    def get_mediapoolitems(self, start_track, end_track) -> list:
        """
        Получение списка с экземплярами DvrTimelineObject,
        содержащими необходимые данные о клипе. 
        """
        timeline_extractor = ResolveTimelineItemExtractor(self.timeline)
        timeline_items = timeline_extractor.get_timeline_items(start_track, end_track)
        filtred_items = []
        for item in timeline_items:
            filtred_items.append(DvrTimelineObject(item.GetMediaPoolItem(), item.GetTrackTypeAndIndex()[1],
                                item.GetStart(), item.GetSourceStartFrame(),
                                item.GetSourceEndFrame(), item.GetDuration(),
                                item.GetClipColor()))
        return filtred_items
    
    def is_effect(self, track, track_type="video"):
        """
        Проверка на предмет наличия дорожки с эффектами.
        """
        for item in self.timeline.GetItemListInTrack(track_type, track):
            if item.GetName() == "Text+":
                return True
            
    def get_tracks(self, start_track=1, track_type="video") -> list:
        """
        Получем индексы не пустых и не залоченых треков. Так же что бы треки не содержали на себе эффектов.
        """
        no_empty_tracks = []
        all_track = self.timeline.GetTrackCount(track_type)
        for track_num in range(start_track, all_track + 1):
            # Если трек не пустой
            if self.timeline.GetItemListInTrack(track_type, track_num) != []:
                # Если трек не залочен
                if not self.timeline.GetIsTrackLocked(track_type, track_num):
                    # Если трек не содержит эффекты
                    if not self.is_effect(track_num):
                        no_empty_tracks.append(track_num)

        return no_empty_tracks
    
    def set_project_preset(self, track) -> bool:
        """
        Установка пресета проекта.
        """
        preset = (self.palate_preset, self.reference_preset)[track == 1]

        set_preset_var = self.project.SetPreset(preset)
        if set_preset_var is not None:
            logger.info(f"Применен пресет проекта: {preset}")
            return True
        else:
            self.signals.error_signal.emit(f"Пресет проекта не применен {preset}")
            return False

    def set_disabled(self, current_track_number):
        '''
        Отключаем все дорожки кроме текущей.
        Для трека 1 — оставляем также треки с эффектами (с "Text+").
        Последнее нужно для того, что бы в последующий рендер пошли все слои.
        '''
        self.max_track = self.timeline.GetTrackCount("video")
        for track_number in range(1, self.max_track + 1):
            if current_track_number == 1:
                # Включаем track 1 и треки, содержащие "Text+"
                if track_number == 1:
                    enabled = True
                else:
                    items = self.timeline.GetItemListInTrack("video", track_number)
                    enabled = any(item.GetName() == "Text+" for item in items)
            else:
                enabled = (track_number == current_track_number)

            self.timeline.SetTrackEnable("video", track_number, enabled)

        logger.info(f"Начало работы с {current_track_number} треком")

    def set_enabled(self):

        for track_number in range(1, self.max_track + 1):
            
            self.timeline.SetTrackEnable("video", track_number, True)

    def get_handles(self, timeline_item) -> str:
        '''
        Получаем значения захлестов.
        '''
        handles = ""
        if timeline_item.clip_color == SETTINGS["colors"][1]: # Beige
            handles = self.lin_retime_hndls
        elif timeline_item.clip_color == SETTINGS["colors"][2]: # Brown
            handles = self.non_lin_retime_hndls
        else:
            handles = self.frame_handles

        return f"EXR_{handles}hndl_FD"
    
    def standart_resolution(self, clip) -> str:
        """
        Пересчет разрешения исходника под стандартное разрешение для рендера(2к).
        Обрабатывает и сферическую и анаморфную линзу. 
        Для вычисления выходного разрешения ширины сферической линзы используется формула: 
        (ширина кадра текущего клипа * высота целевого разрешения) / (высота кадра такущего клипа / аспект текущего клипа).
        Для вычисления выходного разрешения высоты анаморфной линзы используется формула: 
        (высота кадра текущего клипа * ширина целевого разрешения) / (ширина кадра такущего клипа).
        Если полученное значение ширины или высоты кадра получается нечетным, то идет округление до ближайшего четного значения.
        """
        if clip.GetClipProperty('PAR') != 'Square' and clip.GetClipProperty('PAR'):
            aspect = clip.GetClipProperty('PAR')
            width, height = clip.GetClipProperty('Resolution').split('x')
            calculate_width = str((math.ceil(((int(width) * int(self.height_res_glob) / (int(height) / float(aspect))) ) / 2) * 2))
            resolution = "x".join([calculate_width, self.height_res_glob])
            return resolution
        
        else:
            aspect = clip.GetClipProperty('PAR')
            width, height = clip.GetClipProperty('Resolution').split('x')
            calculate_height = str((math.ceil((int(height) * int(self.width_res_glob) / int(width)) / 2) * 2))
            resolution = "x".join([self.width_res_glob, calculate_height])
            return resolution
        
    def scale_1_5_resolution(self, clip) -> str:
        """
        Пересчет разрешения исходника под стандартное разрешение для рендера,
        умноженное на 1.5 при зуме(скеиле) свыше 10%.
        Вычисление аналогично standart_resolution, но при этом и ширина и высота домножаются на коэффициент 1.5.
        """
        # Находит анаморф, вычисляет ширину по аспекту
        if clip.GetClipProperty('PAR') != 'Square' and clip.GetClipProperty('PAR'):
            aspect = clip.GetClipProperty('PAR')
            width, height = clip.GetClipProperty('Resolution').split('x')
            calculate_height = str((math.ceil(((int(width) * int(self.height_res_glob) / (int(height) / float(aspect))) ) / 2) * 2))
            resolution = "x".join([str(int(int(calculate_height) * 1.5)), str(int(math.ceil(int(self.height_res_glob) * 1.5 / 2.0) * 2))])
            return resolution
        else:
            aspect = clip.GetClipProperty('PAR')
            width, height = clip.GetClipProperty('Resolution').split('x')
            calculate_height = str((math.ceil((int(height) * int(self.width_res_glob) / int(width)) / 2) * 2))
            resolution = "x".join([str(int(math.ceil((int(self.width_res_glob) * 1.5) / 2) * 2)), str(int(math.ceil((int(calculate_height) * 1.5) / 2) * 2))])
            return resolution
        
    def scale_2_resolution(self, clip) -> str:
        """
        Пересчет разрешения исходника под стандартное разрешение для рендера,
        умноженное на 2 при зуме(скеиле) свыше 50%.
        Вычисление аналогично standart_resolution, но при этом и ширина и высота домножаются на коэффициент 2.
        """
        if clip.GetClipProperty('PAR') != 'Square' and clip.GetClipProperty('PAR'):
            aspect = clip.GetClipProperty('PAR')
            width, height = clip.GetClipProperty('Resolution').split('x')
            calculate_height = str((math.ceil(((int(width) * int(self.height_res_glob) / (int(height) / float(aspect))) ) / 2) * 2))
            resolution = "x".join([str(int(int(calculate_height) * 2)), str(int(math.ceil(int(self.height_res_glob) * 2 / 2.0) * 2))])
            return resolution
        else:
            aspect = clip.GetClipProperty('PAR')
            width, height = clip.GetClipProperty('Resolution').split('x')
            calculate_height = str((math.ceil((int(height) * int(self.width_res_glob) / int(width)) / 2) * 2))
            resolution = "x".join([str(int(math.ceil((int(self.width_res_glob) * 2) / 2) * 2)), str(int(math.ceil((int(calculate_height) * 2) / 2) * 2))])
            return resolution
        
    def full_resolution(self, clip) -> str:
        """
        Полное разрешение исходника.
        Для вычисления выходного разрешения высоты анаморфной линзы используется формула: 
        (высота кадра текущего клипа / аспект текущего клипа).
        Если полученное значение высоты кадра получается нечетным, то идет округление до ближайшего четного значения.
        """
        if clip.GetClipProperty('PAR') != 'Square' and clip.GetClipProperty('PAR'):
            aspect = clip.GetClipProperty('PAR')
            width, height = clip.GetClipProperty('Resolution').split('x')
            calculate_height = str((math.ceil((int(height) / float(aspect))  / 2) * 2))
            resolution = "x".join([width, calculate_height])
            return resolution
        else:
            return clip.GetClipProperty('Resolution')
        
    def get_resolution_settings(self, timeline_item) -> str:
        """
        Метод логики вычисления разрешения для рендера.
        Реализовано full res разрешение для всех итемов и дорожек.

        :return resolution: Разрешение в виде строки : '2500x858'.
        """
        
        clip = timeline_item.mp_item
        clip_color = timeline_item.clip_color
        track_ind = timeline_item.track_type_ind

        # Плейты
        if clip.GetName() != '' and clip.GetName().lower().endswith(SETTINGS["extentions"]) and clip_color == SETTINGS["colors"][0]: # Orange
            resolution = self.full_resolution(clip)

        if clip.GetName() != '' and clip.GetName().lower().endswith(SETTINGS["extentions"]) and clip_color == SETTINGS["colors"][1]: # Beige
            resolution = self.full_resolution(clip)

        if clip.GetName() != '' and clip.GetName().lower().endswith(SETTINGS["extentions"]) and clip_color == SETTINGS["colors"][2]: # Brown
            resolution = self.full_resolution(clip)

        # Референс
        if clip.GetName() != '' and clip.GetName().lower().endswith(SETTINGS["extentions"]) and track_ind == 1:
            self.is_reference = True
            resolution = self.full_resolution(clip)

        return resolution
    
    def stop_process(self):
        """
        Приостановка конвеера, пока идет процесс рендера текущего итема.
        """
        def rendering_in_progress():
            return self.project.IsRenderingInProgress()
        while rendering_in_progress():
            time.sleep(1)

    def set_render_preset(self, handles_value) -> bool:
        '''
        Метод ищет полученное в get_retime значение захлеста через регулярное выражение 
        в списке всех пресетов рендера.
        '''
        preset_list = self.project.GetRenderPresetList()
        if not self.is_reference:
            for preset in preset_list:
                if re.match(handles_value, preset):
                    self.project.LoadRenderPreset(preset)
                    logger.info(f"Установлен пресет рендера: {handles_value}")
                    return True
            self.signals.error_signal.emit(f"Не удалось применить пресет рендера {handles_value}")
            return False 
        else:
            preset_name = SETTINGS["reference_render_preset"]
            self.project.LoadRenderPreset(preset_name)
            logger.info(f"Установлен пресет рендера: {handles_value}")
            return True
        
    def set_project_resolution(self, height_res, width_res):
        """
        Установка проектного разрешения перед рендером.
        """
        self.project.SetSetting("timelineResolutionHeight", height_res)
        self.project.SetSetting("timelineResolutionWidth", width_res)
            
    def set_render_settings(self, clip, clip_resolution):
        '''
        Метод задает настройки для рендера текущего итема 
        и добавляет текущий render job в очередь.

        :return: Кортеж (Флаг ошибки, render job item)
        '''
        try:
            resolution = re.search(r'\d{4}x\d{3,4}', clip_resolution).group(0)
            width, height = resolution.split("x")
            logger.info(f"Установлено разрешение с настройках рендера: {width}x{height}")
        except Exception as e:
            self.signals.error_signal.emit(f"Не удалось вычислить разрешение {resolution}: {e}")
            return False
        
        self.set_project_resolution(height, width)

        render_settings = {
            "SelectAllFrames": False,
            "MarkIn": clip.clip_start,
            "MarkOut": clip.clip_end,
            "TargetDir": str(self.render_path),
            "FormatWidth": int(width),
            "FormatHeight": int(height)
            }
        
        set_render = self.project.SetRenderSettings(render_settings)
        render_job = self.project.AddRenderJob()

        if set_render is not None and render_job is not None:
            logger.info(f"Запустился рендер клипа {clip.mp_item.GetName()} с разрешением {width}x{height}")
            return True, render_job
        else:
            self.signals.error_signal.emit(f"Не удалось установить разрешение рендера {resolution}")
            return False, None 
        
    def skip_item(self, item) -> bool:
        """
        Пропускает итем, для последующей обработки вручную, при условии,
        что у клипа установлен дефолтный цвет 'Blue'.
        """
        if item.clip_color == SETTINGS["colors"][3] and item.track_type_ind != 1:
            return True

    def start_render(self, render_job) -> bool:
        """
        Запуск render job.
        Обнуление флага референса.
        """    
        start_render = self.project.StartRendering([render_job], isInteractiveMode=True)
        if not start_render:
            self.signals.error_signal.emit(f"Ошибка обработки рендера: {render_job}")
            return False
        
        self.is_reference = False
        return True

    def export_timeline(self):
        """
        Экспорт таймлайна после окончания рендера в формате xml.

        """
        xml_name = str(self.timeline.GetName())
        path = (Path(self.render_path) / f'{xml_name}.xml').resolve()  
        result = self.timeline.Export(str(path), self.resolve.EXPORT_FCP_7_XML)
        if result is None:
            self.signals.warning_signal.emit(f"Ошибка экспорта таймлайна {xml_name}")
        else:
            logger.info(f"Таймлайн {xml_name} успешно экспортирован")

    def run(self):
        """
        Логика конвеера рендера.
        """
        self.resolve_api = self.get_api_resolve()
        self.resolve = self.resolve_api.resolve
        self.media_pool = self.resolve_api.mediapool
        self.timeline = self.resolve_api.timeline
        self.project = self.resolve_api.project
        self.palate_preset = self.user_config["plate_preset"]
        self.reference_preset = self.user_config["reference_preset"]
        self.frame_handles = int(self.user_config["handles"])
        self.height_res_glob = self.user_config["resolution_height"]
        self.width_res_glob = self.user_config["resolution_width"]
        self.render_path = self.user_config["render_path"]
        self.export_bool = self.user_config["export_xml"]
        self.lin_retime_hndls = int(self.user_config["linear_retime_handles"])
        self.non_lin_retime_hndls = int(self.user_config["non_linear_retime_handles"])
        self.is_reference = False

        video_tracks = self.get_tracks()

        if video_tracks == []:
            self.signals.warning_signal.emit("Отсутствуют клипы для обработки.")
            return False

        # Цикл по дорожкам(по основному и допплейтам, если таковые имеются).
        for track in video_tracks:

            track_items = self.get_mediapoolitems(start_track=track, end_track=track)

            self.set_disabled(track)
        
            project_preset_var = self.set_project_preset(track)
            if not project_preset_var:
                return False

            # Цикл по клипам на дорожке.
            for item in track_items:
                
                if self.skip_item(item):
                    continue

                logger.debug("\n".join(("\n", f"timline duration: {item.clip_duration}",
                             f"source duration: {item.source_end - item.source_start}",
                             f"timline start: {item.clip_start}",
                             f"timeline end: {item.clip_end}",
                             f"source start: {item.source_start}",
                             f"source end: {item.source_end}")))

                handles_value = self.get_handles(item)

                # Ставится до установки render preset что бы не перезатирать пресеты при цикле.
                self.stop_process()

                item_resolution = self.get_resolution_settings(item)

                render_preset_var = self.set_render_preset(handles_value)
                if not render_preset_var:
                    return False

                render_settings_var, render_job = self.set_render_settings(item, item_resolution)
                if not render_settings_var:
                    return False
                
                start_render_var = self.start_render(render_job)
                if not start_render_var:
                    return False

            # Ожидаем, переключаемся на вкладку edit и уходим на новый трек.
            self.stop_process()
            self.resolve.OpenPage("edit")

        self.set_enabled()
        if self.export_bool:    
            self.export_timeline()
        self.signals.success_signal.emit(f"Рендер успешно завершен!")

class ThreadWorker(QThread):
    """
    Запуск логики из отдельного потока.
    """
    success_signal = pyqtSignal(str)
    warning_signal = pyqtSignal(str)
    error_signal = pyqtSignal(str)

    def __init__(self, parent, logic_class, user_config):
        super().__init__(parent)
        self.user_config = user_config
        self.logic_class = logic_class

    def run(self):
        try:
            logic = self.logic_class(self.user_config, self)
            success = logic.run()

        except Exception as e:
            self.error_signal(f"Ошибка программы {e}")

class ConfigValidator:
    """
    Класс собирает и валидирует пользовательские данные.
    """
    def __init__(self, gui, mode="conform"):

        self.gui = gui
        self.mode = mode
        self.errors = []

    def collect_config(self) -> dict:
        """
        Собирает пользовательские данные из GUI.
        """

        if self.mode == "conform":
            return {
                "resolution_height": self.gui.height_input.text().strip(),
                "resolution_width": self.gui.width_input.text().strip(),
                "plate_preset": self.gui.preset_combo.currentText().strip(),
                "reference_preset": self.gui.render_preset_combo.currentText().strip(),
                "handles": self.gui.handle_input.text().strip(),
                "linear_retime_handles": self.gui.retime_hndl_input.text().strip(),
                "non_linear_retime_handles": self.gui.nonlinear_hndl_input.text().strip(),
                "render_path": self.gui.render_path.text().strip(),
                "export_xml": self.gui.export_cb.isChecked()
            }
        
        if self.mode == "names":
            return {"track_number": self.gui.from_track_qline.text().strip()}
        
        if self.mode == "effects":
            pass
    
    def validate(self, user_config: dict) -> bool:
        """
        Валидирует конфиг.
        """
        self.errors.clear()

        if self.mode == "conform":

            if not user_config["render_path"]:
                self.errors.append("Укажите путь для рендера")

            try:
                int(user_config["resolution_height"])
                int(user_config["resolution_width"])
                int(user_config["handles"])
                int(user_config["linear_retime_handles"])
                int(user_config["non_linear_retime_handles"])
            except ValueError:
                self.errors.append("Значения должны быть целыми числами")
            return not self.errors
        
        if self.mode == "names":
            try:
                int(user_config["track_number"])
            except ValueError:
                self.errors.append("Значения должны быть целыми числами")
            return not self.errors
        
        if self.mode == "effects":
            return True

    def get_errors(self) -> list:
        return self.errors   
    
class ExrDelivery(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("EXR Delivery")
        self.resize(600, 200)
        self.setWindowFlags(self.windowFlags() | Qt.WindowStaysOnTopHint)

        self.set_effects_btn = QPushButton("Set Effects")
        self.set_effects_btn.clicked.connect(lambda: self.run(EffectsAppender, mode="effects", button=self.set_effects_btn))

        self.from_track_label = QLabel("From Track:")
        self.from_track_qline = QLineEdit()
        self.from_track_qline.setMaximumWidth(40)
        self.set_names_btn = QPushButton("Set Names")
        self.set_names_btn.clicked.connect(lambda: self.run(NameSetter, mode="names", button=self.set_names_btn))

        self.res_group = QGroupBox("Resolution")
        self.res_group.setFixedHeight(70)
        self.res_group.setMinimumWidth(180)
        self.width_input = QLineEdit("2048")
        self.width_input.setFixedWidth(60)
        self.height_input = QLineEdit("858")
        self.height_input.setFixedWidth(60)

        self.preset_combo = QComboBox()
        self.preset_combo.addItems(self.get_project_preset())
        self.preset_combo.setCurrentText("aces1.2_smoother_preset")
        self.preset_combo.setMinimumWidth(180)

        self.render_preset_combo = QComboBox()
        self.render_preset_combo.addItems(self.get_project_preset())
        self.render_preset_combo.setCurrentText("YRGB_ref_preset")
        self.render_preset_combo.setMinimumWidth(180)

        self.export_cb = QCheckBox("Export .xml")

        self.handles_label = QLabel("Handles:")
        self.retime_label = QLabel("retime - ")
        self.handle_input = QLineEdit("0")
        self.handle_input.setMaximumWidth(40)
        self.nonlinear_label = QLabel("non-linear - ")
        self.retime_hndl_input = QLineEdit("0")
        self.retime_hndl_input.setMaximumWidth(40)
        self.nonlinear_hndl_input = QLineEdit("5")
        self.nonlinear_hndl_input.setMaximumWidth(40)

        self.render_path = QLineEdit()
        self.browse_btn = QPushButton("Choose")
        self.browse_btn.clicked.connect(self.select_folder)

        self.init_ui()

    def init_ui(self):
        layout = QVBoxLayout()

        # -- Группа установки эффектов
        step1_group = QGroupBox("Step 1")
        step1_group.setMinimumHeight(80)
        effects_layout = QHBoxLayout()
        effects_layout.addWidget(self.set_effects_btn)
        step1_group.setLayout(effects_layout)
        layout.addWidget(step1_group)

        # -- Группа установки имен клипов
        step2_group = QGroupBox("Step 2")
        step2_group.setMinimumHeight(120)
        names_layout = QVBoxLayout()
        input_track_layout = QHBoxLayout()
        btn_layout = QHBoxLayout()
        input_track_layout.addWidget(self.from_track_label)
        input_track_layout.addWidget(self.from_track_qline)
        input_track_layout.addStretch()
        btn_layout.addWidget(self.set_names_btn)
        names_layout.addLayout(input_track_layout)
        names_layout.addLayout(btn_layout)
        step2_group.setLayout(names_layout)
        layout.addWidget(step2_group)

        # -- Группа конформа монтажа
        step3_group = QGroupBox("Step 3")
        step3_group.setMinimumHeight(300)
        step3_layout = QVBoxLayout()

        # Разрешение
        res_layout = QHBoxLayout()
        res_layout.addStretch()
        res_layout.addWidget(self.width_input)
        res_layout.addWidget(QLabel("x"))
        res_layout.addWidget(self.height_input)
        res_layout.addStretch()
        self.res_group.setLayout(res_layout)
        step3_layout.addWidget(self.res_group, alignment=Qt.AlignHCenter)

        # Пресеты
        preset_layout = QHBoxLayout()
        preset_layout.addWidget(QLabel("Plate preset:"))
        preset_layout.addWidget(self.preset_combo)
        preset_layout.addSpacing(20)
        preset_layout.addWidget(QLabel("Reference preset"))
        preset_layout.addWidget(self.render_preset_combo)
        preset_layout.addSpacing(20)
        preset_layout.addStretch()
        step3_layout.addLayout(preset_layout)

        # Захлесты
        handles_layout = QHBoxLayout()
        handles_layout.addWidget(self.handles_label)
        handles_layout.addSpacing(40)
        handles_layout.addWidget(QLabel("standart - "))
        handles_layout.addWidget(self.handle_input)
        handles_layout.addSpacing(20)
        handles_layout.addWidget(self.retime_label)
        handles_layout.addWidget(self.retime_hndl_input)
        handles_layout.addSpacing(20)
        handles_layout.addWidget(self.nonlinear_label)
        handles_layout.addWidget(self.nonlinear_hndl_input)
        handles_layout.addStretch()
        step3_layout.addLayout(handles_layout)

        # Путь рендера 
        path_layout = QHBoxLayout()
        path_layout.addWidget(QLabel("Render path:"))
        path_layout.addSpacing(10)
        path_layout.addWidget(self.render_path)
        path_layout.addWidget(self.browse_btn)
        step3_layout.addLayout(path_layout)

        # Кнопка запуска
        self.run_button = QPushButton("Render Conform")
        self.run_button.clicked.connect(lambda: self.run(DeliveryPipline, mode="conform", button=self.run_button))
        step3_layout.addWidget(self.run_button)

        step3_group.setLayout(step3_layout)
        layout.addWidget(step3_group)

        # Цветовая палетка
        palette_widget = self.create_color_palette()
        layout.addWidget(palette_widget)

        self.setLayout(layout)

    def get_project_preset(self):
        """
        Получаем список пресетов проекта Resolve.
        """
        self.resolve = ResolveObjects()
        self.project = self.resolve.project
        return [preset["Name"] for ind, preset in self.project.GetPresets().items()]
    
    def get_render_preset(self):
        """
        Получаем список пресетов рендера Resolve.
        """
        self.resolve = ResolveObjects()
        self.project = self.resolve.project
        return [preset for ind, preset in self.project.GetRenderPresets().items()][31:]

    def create_color_palette(self, labels=None):
        palette_group = QGroupBox("")

        main_layout = QVBoxLayout()
        label_layout = QHBoxLayout()
        color_layout = QHBoxLayout()

        labels = {
            "Orange": "No retime",
            "Beige": "Linear retime",
            "Brown": "Non-linear retime",

        }
        color_map = {
            "Orange": "#FFA500",
            "Beige": "#F5F5DC",
            "Brown": "#8B4513",

        }
        self.color_labels = {}

        for name, hex_color in color_map.items():
            # Если задан labels — берём из него, иначе "Label"
            label_text = labels.get(name, "Label") if labels else "Label"

            # Верхний лейбл
            label = QLabel(label_text)
            label.setAlignment(Qt.AlignCenter)
            self.color_labels[name] = label
            label_layout.addWidget(label)

            # Цветной блок с подписью внутри
            color_box = QLabel(name)
            color_box.setFixedSize(160, 25)
            color_box.setAlignment(Qt.AlignCenter)
            color_box.setStyleSheet(f"""
                background-color: {hex_color};
                color: black;
                border: 1px solid gray;
                border-radius: 4px;
            """)
            color_layout.addWidget(color_box)

        main_layout.addLayout(label_layout)
        main_layout.addLayout(color_layout)
        palette_group.setLayout(main_layout)
        return palette_group

    def on_success_signal(self, message):
        QMessageBox.information(self, "Успех", message)

    def on_warning_signal(self, message):
        QMessageBox.warning(self, "Успех", message)
        logger.warning(message)

    def on_error_signal(self, message):
        QMessageBox.warning(self, "Успех", message)
        logger.exception(message)

    def select_folder(self):
        folder = QFileDialog.getExistingDirectory(self, "Выбор папки")
        if folder:
            self.render_path.setText(folder)

    def run(self, logic_class, mode, button=None):
        """
        :param logic_class: Класс логики, который будет запущен.

        :param mode: Мод логики. Используется при валидации.

        :param button: Кнопка, которая была запущена в GUI.
        """

        self.validator = ConfigValidator(self, mode=mode)
        self.user_config = self.validator.collect_config()

        if not self.validator.validate(self.user_config):
            QMessageBox.critical(self, "Ошибка валидации", "\n".join(self.validator.get_errors()))
            return
   
        logger.info(f"\n\n{pformat(self.user_config)}\n")
        thread = ThreadWorker(self, logic_class, self.user_config)
        thread.success_signal.connect(self.on_success_signal)
        thread.warning_signal.connect(self.on_warning_signal)
        thread.error_signal.connect(self.on_error_signal)

        if button:
            button.setEnabled(False)
            thread.finished.connect(lambda: button.setEnabled(True))
        thread.start()

if __name__ == "__main__":
    app = QApplication(sys.argv)
    apply_style(app)
    window = ExrDelivery()
    window.show()
    sys.exit(app.exec_())
