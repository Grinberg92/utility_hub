from collections import Counter
import sys
import re
import math
import time
from pprint import pformat
from pathlib import Path
from timecode import Timecode as tc
from PyQt5.QtWidgets import (
    QApplication, QWidget, QLabel, QLineEdit, QPushButton,
    QVBoxLayout, QHBoxLayout, QComboBox, QFileDialog, QMessageBox, QGroupBox, QCheckBox, QFrame
)
from PyQt5.QtCore import Qt, QThread, pyqtSignal, QEventLoop
from dvr_tools.logger_config import get_logger
from dvr_tools.css_style import apply_style
from dvr_tools.resolve_utils import ResolveObjects
from dvr_tools.resolve_utils import ResolveTimelineItemExtractor
from config.global_config import GLOBAL_CONFIG

logger = get_logger(__file__)

SETTINGS = {
    "colors": ("Orange", "Beige", "Brown", "Blue"),
    "extentions": (".mxf", ".braw", ".arri", ".r3d", ".dng", ".mov", ".mp4"),
    "reference_render_preset": "reference_preset_FD",
    "effects": ('RTS+', 'Counter'),
    "plate_prefix": 'bim_',
    "plate_suffix": '_src_v001_VT',
    "ref_prefix": '',
    "ref_suffix": ''
}

TRACK_POSTFIX = GLOBAL_CONFIG["scripts_settings"]["exr_delivery_fd"]["track_postfix"]
COLORS = GLOBAL_CONFIG["scripts_settings"]["exr_delivery_fd"]["colors"]
EXTENTIONS = GLOBAL_CONFIG["scripts_settings"]["exr_delivery_fd"]["extentions"]
FALSE_EXTENTIONS = GLOBAL_CONFIG["scripts_settings"]["exr_delivery_fd"]["false_extentions"]
PLATE_PROJECT_PRESETS = GLOBAL_CONFIG["scripts_settings"]["exr_delivery_fd"]["plate_project_presets"]
REF_PROJECT_PRESETS = GLOBAL_CONFIG["scripts_settings"]["exr_delivery_fd"]["ref_project_presets"]
COPTER_EXTENTIONS = GLOBAL_CONFIG["scripts_settings"]["exr_delivery_fd"]["copter_extentions"]
LUT_PATH = GLOBAL_CONFIG["scripts_settings"]["exr_delivery_fd"]["LUT_win"]

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

    def set_markers(self, item, clip_name) -> None:
        """
        Установка маркера посередине клипа на таймлайне.
        """
        clip_start = int((item.GetStart() + (item.GetStart() + item.GetDuration())) / 2) - self.timeline_start_tc
        self.timeline.AddMarker(clip_start, 'Blue', clip_name, "", 1, 'Renamed')

    def get_markers(self) -> list: 
        '''
        Получение маркеров для работы других методов.
        '''
        try:
            markers_list = []
            for timecode, name in self.timeline.GetMarkers().items():
                name = name[self.marker_from].strip()
                timecode_marker = tc(self.fps, frames=timecode + self.timeline_start_tc)   
                markers_list.append((name, timecode_marker))
            return markers_list
        except Exception as e:
            self.signals.error_signal.emit(f"Ошибка получения данных об объектах маркеров: {e}")
            return False

    def from_markers(self) -> None:
        """
        Присвоение имен из маркеров, согласно шаблону из gui.
        """
        markers = self.get_markers()

        for track_index in range(2, self.count_of_tracks + 1):
            clips_under = self.timeline.GetItemListInTrack('video', track_index)
            for clip_under in clips_under:
                applied = False  # было ли имя присвоено этому текущему clip_under
                for name, timecode in markers:
                    if clip_under.GetStart() <= timecode < (clip_under.GetStart() + clip_under.GetDuration()):
                        # Вычитаем - 1, чтобы отсчет плейтов был с первой дорожки, а не второй
                        name_new = self.prefix + name + self.postfix + ("", TRACK_POSTFIX + str(track_index - 1))[self.set_track_id]
                        clip_under.SetName(name_new)
                        clip_under.AddVersion(name, 0)
                        logger.info(f'Добавлено кастомное имя "{name_new}" в клип на треке {track_index}')
                        applied = True

                if not applied:
                    self.warnings.append(f"Для клипа {clip_under.GetName()} на треке {track_index} не было установлено имя")

    def from_offline(self, items) -> None:
        """
        Присвоение имен из оффлайн клипов, согласно шаблону из gui.
        """
        for track_index in range(2, self.count_of_tracks + 1):
            clips_under = self.timeline.GetItemListInTrack('video', track_index)
            for clip_under in clips_under:
                applied = False 
                for item in items:
                    if clip_under.GetStart() == item.GetStart():
                        # Вычитаем - 1 чтобы отсчет плейтов был с первой дорожки, а не второй
                        name = self.prefix + item.GetName() + self.postfix + ("", TRACK_POSTFIX + str(track_index - 1))[self.set_track_id]
                        clip_under.SetName(name)
                        clip_under.AddVersion(name, 0)
                        logger.info(f'Добавлено кастомное имя "{name}" в клип на треке {track_index}')
                        applied = True
                        break 

                if not applied:
                    self.warnings.append(
                        f"Для клипа {clip_under.GetName()} на треке {track_index} не было установлено имя")

    def set_name(self, items) -> bool:
        """
        Метод устанавливает имя полученное из маркеров или оффлайн клипов на таймлайне Resolve 
        и применяет его в имена клипов по двум принципам.
        В случае получения имен из оффлайн клипов - имена применяются на все итемы лежащие ниже оффлайн клипа.
        Стартовый таймкод оффлайн клипа должен пересекаться со стартовыми таймкодами итемов, лежащими под ним.
        В случае получения имен из маркеров - имена применяются на все клипы, которые лежат ниже маркера. 
        Таймкод маркера должен быть внутри таймкода такого клипа.
        """
        self.warnings = []

        try:
            if self.name_from_markers:
                self.from_markers()

            elif self.name_from_track:
                self.from_offline(items)

            if self.warnings:
                self.signals.warning_signal.emit("\n".join(self.warnings))
                return False
            else:
                logger.info("Имена успешно применены на клипы.")
            return True
        
        except Exception as e:
            self.signals.error_signal.emit(f"Ошибка копирования имен: {e}")
            return False 

    def is_connect_project(self) -> bool:
        """
        Проверяет все ли объекты резолв получены для дальнейшей работы.
        """
        if self.resolve is None:
            self.signals.error_signal.emit("Не найден Резолв")
            return False
        
        if self.media_pool is None:
            self.signals.error.emit("Не найден медиапул")
            return False
        
        if self.timeline is None:
            self.signals.error_signal.emit("Не найдена таймлиния")
            return False
        
        return True   

    def run(self) -> None:
        """
        Основная логика.
        """
        try:
            self.resolve_api = self.get_api_resolve()
        except Exception as e:
            self.signals.error_signal.emit(str(e))
            return False
        
        self.resolve = self.resolve_api.resolve
        self.media_pool = self.resolve_api.mediapool
        self.timeline = self.resolve_api.timeline

        if not self.is_connect_project():
            return False
        self.timeline_start_tc = self.timeline.GetStartFrame()

        self.track_number = int(self.user_config["track_number"])
        self.name_from_track = self.user_config["set_name_from_track"]
        self.name_from_markers = self.user_config["set_name_from_markers"]
        self.fps = int(self.user_config["fps"])
        self.marker_from = self.user_config["locator_from"]
        self.prefix = self.user_config["prefix_name"]
        self.postfix = self.user_config["postfix_name"]
        self.set_track_id = self.user_config["set_track_id"]

        self.count_of_tracks = self.timeline.GetTrackCount('video')

        items = self.timeline.GetItemListInTrack('video', self.track_number)

        if self.name_from_track:
            if items is None:
                self.signals.warning_signal.emit(f"Дорожка {self.track_number} не существует.")
                return
            if items == []:
                self.signals.warning_signal.emit(f"На дорожке {self.track_number} отсутствуют объекты.")
                return
        
        if not self.set_name(items):
            return

        self.signals.success_signal.emit("Имена успешно применены!")

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
    def __init__(self, mp_item, track_type_ind, clip_start_tmln, 
                 source_start, source_end, clip_dur, clip_color, timeline_item):
        self.mp_item = mp_item
        self.track_type_ind = track_type_ind
        self.clip_start = clip_start_tmln
        self.clip_duration = clip_dur
        self.clip_end = self.clip_start + (self.clip_duration - 1)
        self.source_start = source_start
        self.source_end = source_end
        self.clip_color = clip_color
        self.timeline_item = timeline_item

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

    def is_connect_project(self) -> bool:
        """
        Проверяет все ли объекты резолв получены для дальнейшей работы.
        """
        if self.resolve is None:
            self.signals.error_signal.emit("Не найден Резолв")
            return False
        
        if self.media_pool is None:
            self.signals.error.emit("Не найден медиапул")
            return False
        
        if self.timeline is None:
            self.signals.error_signal.emit("Не найдена таймлиния")
            return False
        
        if self.project is None:
            self.signals.error_signal.emit("Не найден проект")
            return False
        
        return True

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
                                item.GetClipColor(), item))
        return filtred_items
    
    def is_effect(self, track, track_type="video"):
        """
        Проверка на предмет наличия дорожки с эффектами.
        """
        for item in self.timeline.GetItemListInTrack(track_type, track):
            if item.GetMediaPoolItem() == None:
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
    
    def set_project_preset(self, track, item: DvrTimelineObject) -> bool:
        """
        Установка пресета проекта.
        """

        # Для референса
        if track == 1:
            preset =  REF_PROJECT_PRESETS[0]
            set_preset_var = self.project.SetPreset(preset)
            if set_preset_var is not None:
                logger.info(f"Применен пресет проекта: {preset}")
                return True
            else:
                self.signals.error_signal.emit(f"Пресет проекта не применен {preset}")
                return False
        
        # Для плейтов
        else:
            if self.palate_preset == PLATE_PROJECT_PRESETS[0]:
                if (item.mp_item.GetName().lower().endswith(COPTER_EXTENTIONS) or 
                    item.mp_item.GetName().lower().endswith(FALSE_EXTENTIONS) or 
                    item.mp_item.GetClipProperty("Input Color Space") == "S-Gamut3.Cine/S-Log3"):
                    preset = PLATE_PROJECT_PRESETS[1]
                    set_preset_var = self.project.SetPreset(preset)
                    #self.set_LUT(item)
                    if set_preset_var is not None:
                        logger.info(f"Применен пресет проекта: {preset}")
                        return True
                    else:
                        self.signals.error_signal.emit(f"Пресет проекта не применен {preset}")
                        return False
                else:
                    preset = PLATE_PROJECT_PRESETS[0]
                    set_preset_var = self.project.SetPreset(preset)
                    if set_preset_var is not None:
                        logger.info(f"Применен пресет проекта: {preset}")
                        return True
                    else:
                        self.signals.error_signal.emit(f"Пресет проекта не применен {preset}")
                        return False
                    
            # Только YRGB RCM пресет.
            else:
                preset = PLATE_PROJECT_PRESETS[1]
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
                    enabled = any(item.GetMediaPoolItem() == None for item in items)
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
        
    def standart_resolution(self, clip) -> str:
        """
        Пересчет разрешения исходника под стандартное разрешение для рендера(2к).
        Обрабатывает и сферическую и анаморфную линзу. 
        Для вычисления выходного разрешения ширины сферической линзы используется формула: 
        (ширина кадра текущего клипа * высота целевого разрешения) / (высота кадра такущего клипа / аспект текущего клипа).
        Для вычисления выходного разрешения высоты анаморфной линзы используется формула: 
        (высота кадра текущего клипа * ширина целевого разрешения) / (ширина кадра такущего клипа).
        Если полученное значение ширины или высоты кадра получается нечетным, то идет округление вверх до ближайшего четного значения.
        """
        width, height = clip.GetClipProperty('Resolution').split('x')
        ratio = int(width) / int(height)

        if clip.GetClipProperty('PAR') != 'Square' and clip.GetClipProperty('PAR') or ratio > 2.2:
            # Отлавливаем анаморфоты которые в исходнике уже имеют десквизный вид и PAR 'Square'
            if ratio > 2.2:
                aspect = clip.GetClipProperty('PAR')
                calculate_width = str((math.ceil(((int(width) * int(self.height_res_glob) / (int(height) ))) / 2) * 2))
                # Временный фикс
                if self.boe_fix:
                    if calculate_width == "2500":
                        calculate_width = "2498"
                resolution = "x".join([calculate_width, self.height_res_glob])
                return resolution
            else:
                aspect = clip.GetClipProperty('PAR')
                calculate_width = str((math.ceil(((int(width) * int(self.height_res_glob) / (int(height) / float(aspect)))) / 2) * 2))
                # Временный фикс
                if self.boe_fix:
                    if calculate_width == "2500":
                        calculate_width = "2498"
                resolution = "x".join([calculate_width, self.height_res_glob])
                return resolution
            
        else:
            aspect = clip.GetClipProperty('PAR')
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
        width, height = clip.GetClipProperty('Resolution').split('x')
        ratio = int(width) / int(height)

        if clip.GetClipProperty('PAR') != 'Square' and clip.GetClipProperty('PAR') or ratio > 2.2:
            # Отлавливаем анаморфоты которые в исходнике уже имеют десквизный вид и PAR 'Square'
            if ratio > 2.2:
                aspect = clip.GetClipProperty('PAR')
                calculate_width = str((math.ceil(((int(width) * int(self.height_res_glob) / (float(height) ))) / 2) * 2))
                # Временный фикс
                width_1_5 = str(int(math.ceil((float(calculate_width) * 1.5) / 2.0) * 2))
                if self.boe_fix:
                    if width_1_5 == "3750":
                            width_1_5 = "3748"
                resolution = "x".join([width_1_5, str(int(math.ceil(int(self.height_res_glob) * 1.5 / 2.0) * 2))])
                return resolution
            else:
                aspect = clip.GetClipProperty('PAR')
                calculate_width = str((math.ceil(((int(width) * int(self.height_res_glob) / (int(height) / float(aspect))) ) / 2) * 2))
                # Временный фикс
                width_1_5 = str(int(math.ceil((float(calculate_width) * 1.5) / 2.0) * 2))
                if self.boe_fix:
                    if width_1_5 == "3750":
                            width_1_5 = "3748"
                resolution = "x".join([width_1_5, str(int(math.ceil(int(self.height_res_glob) * 1.5 / 2.0) * 2))])
                return resolution
        else:
            aspect = clip.GetClipProperty('PAR')
            calculate_height = str((math.ceil((int(height) * int(self.width_res_glob) / int(width)) / 2) * 2))
            resolution = "x".join([str(int(math.ceil((int(self.width_res_glob) * 1.5) / 2) * 2)), str(int(math.ceil((int(calculate_height) * 1.5) / 2) * 2))])
            return resolution
        
    def scale_2_resolution(self, clip) -> str:
        """
        Пересчет разрешения исходника под стандартное разрешение для рендера,
        умноженное на 2 при зуме(скеиле) свыше 50%.
        Вычисление аналогично standart_resolution, но при этом и ширина и высота домножаются на коэффициент 2.
        """
        width, height = clip.GetClipProperty('Resolution').split('x')
        ratio = int(width) / int(height)

        if clip.GetClipProperty('PAR') != 'Square' and clip.GetClipProperty('PAR') or ratio > 2.2:
            # Отлавливаем анаморфоты которые в исходнике уже имеют десквизный вид и PAR 'Square'
            if ratio > 2.2:
                aspect = clip.GetClipProperty('PAR')
                calculate_width = str((math.ceil(((int(width) * int(self.height_res_glob) / (int(height))) ) / 2) * 2))
                resolution = "x".join([str(int(int(calculate_width) * 2)), str(int(math.ceil(int(self.height_res_glob) * 2 / 2.0) * 2))])
                return resolution
            else:
                aspect = clip.GetClipProperty('PAR')
                calculate_width = str((math.ceil(((int(width) * int(self.height_res_glob) / (int(height) / float(aspect))) ) / 2) * 2))
                resolution = "x".join([str(int(int(calculate_width) * 2)), str(int(math.ceil(int(self.height_res_glob) * 2 / 2.0) * 2))])
                return resolution      
        else:
            aspect = clip.GetClipProperty('PAR')
            calculate_height = str((math.ceil((int(height) * int(self.width_res_glob) / int(width)) / 2) * 2))
            resolution = "x".join([str(int(math.ceil((int(self.width_res_glob) * 2) / 2) * 2)), str(int(math.ceil((int(calculate_height) * 2) / 2) * 2))])
            return resolution
        
    def full_resolution(self, clip) -> str:
        """
        Полное разрешение исходника.
        Для вычисления выходного разрешения высоты анаморфной линзы используется формула: 
        (высота кадра текущего клипа / аспект текущего клипа).
        Если полученное значение высоты кадра получается нечетным, то идет округление вверх до ближайшего четного значения.
        """
        width, height = clip.GetClipProperty('Resolution').split('x')
        ratio = int(width) / int(height)

        if clip.GetClipProperty('PAR') != 'Square' and clip.GetClipProperty('PAR') or ratio > 2.2:
             # Отлавливаем анаморфоты которые в исходнике уже имеют десквизный вид и PAR 'Square'
            if ratio > 2.2:
                aspect = clip.GetClipProperty('PAR')
                calculate_height = str((math.ceil((int(height))  / 2) * 2))
                resolution = "x".join([width, calculate_height])
                return resolution
            else:
                aspect = clip.GetClipProperty('PAR')
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
            logger.info(f"Установлен пресет рендера: {preset_name}")
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
        render_settings.clear()

        if set_render is not None and render_job is not None:
            self.rj_to_clear.append(render_job)
            logger.info(f"Запустился рендер клипа {clip.mp_item.GetName()} с разрешением {width}x{height}")
            return True, render_job
        else:
            self.signals.error_signal.emit(f"Не удалось установить разрешение рендера {resolution}")
            return False, None 
        
    def is_question_items(self, warnings) -> bool:
        """
        Обрабатываем предупреждения через диалоговое окно потока gui.
        """
        text = "\n".join([f"• '{name}' на треке {track}" for name, track in warnings])
        message = f"Обнаружены клипы, требующие Davinci YRGB Color Management.\nПроверьте настройки цвета, прежде чем продолжить:\n\n{text}\n\nХотите продолжить?"

        loop = QEventLoop()
        user_choice = {}

        def callback(result):
            user_choice["answer"] = result
            loop.quit()

        self.signals.warning_question_signal.emit(message, callback)

        loop.exec_()  

        if user_choice["answer"] == QMessageBox.No:
            return True
        
    def validate(self, video_tracks) -> bool:
        """
        Валидирует итемы сразу на всей дорожке.
        """
        warnings = []
        warnings_question = []
        no_select = True
        try:
            for track_num, track in enumerate(video_tracks, start=1):
                
                if track_num > 1:
                    track_items = self.get_mediapoolitems(start_track=track, end_track=track)
                    for item in track_items:
                        clip = item.mp_item
                        # Проверка на расширения (".mov", ".mp4", ".jpg")
                        if (clip.GetName().lower().endswith(FALSE_EXTENTIONS) or 
                            clip.GetName().lower().endswith(COPTER_EXTENTIONS) or
                            clip.GetClipProperty("Input Color Space") == "S-Gamut3.Cine/S-Log3") and not item.clip_color == COLORS[3]:
                            warnings_question.append((clip.GetName(), track_num))    
                    
                        # Сбор статусов для проверки хотя бы одного ввыделенного клипа на таймлайне
                        if not item.clip_color == COLORS[3]:
                            no_select = False

                        # Проверка на клип, покрашенный в невалидный цвет
                        if item.clip_color not in COLORS:
                            warnings.append(f"• Не валидный цвет клипа {clip.GetName()} на треке {track_num}")

                        # Проверка на валидность расширения клипа
                        if not clip.GetName().lower().endswith(EXTENTIONS) and not clip.GetName().lower().endswith(FALSE_EXTENTIONS):
                            warnings.append(f"• Не валидное расширение клипа {clip.GetName()} на треке {track_num}")

                        # Проверка на валидный ФПС
                        if float(clip.GetClipProperty("FPS")) != float(self.fps):
                            warnings.append(f"• FPS клипа {clip.GetName()} на треке {track_num} не соответствует проектному")
                        
                        # Проверка на наличие трансформа на клипе
                        if self.detect_transform(item):
                            warnings.append(f"• Уберите трансфомы/скейлы с клипов на треке {track}")
                            break
                    
        except:
            warnings.append(f"На таймлайне обнаружен объект, который невозможно верифицировать.\nПроверьте нет ли на таймлайне эффектов перехода или других эффектов.")

        if no_select:
            warnings.append("Не выбран ни один клип на таймлайне")

        if warnings_question:
            if self.is_question_items(warnings_question):
                return False

        if warnings:
            self.signals.warning_signal.emit("\n".join(warnings))
            return False
        
        return True
        
    def skip_item(self, item: DvrTimelineObject) -> bool:
        """
        Пропускает итем, для последующей обработки вручную, при условии,
        что у клипа установлен дефолтный цвет 'Blue'.
        """
        return item.clip_color == COLORS[3]
    
    def detect_transform(self, item: DvrTimelineObject) -> bool:
        """
        Определяет есть ли трансформы и кроппинг на таймлайн итеме.
        """
        try:
            return not all((float(item.timeline_item.GetProperty("Pan")) == float(0.0),
                        float(item.timeline_item.GetProperty("Tilt")) == float(0.0),
                        float(item.timeline_item.GetProperty("ZoomX")) == float(1.0),
                        float(item.timeline_item.GetProperty("ZoomY")) == float(1.0),
                        float(item.timeline_item.GetProperty("Pitch")) == float(0.0),
                        float(item.timeline_item.GetProperty("Yaw")) == float(0.0),
                        float(item.timeline_item.GetProperty("RotationAngle")) == float(0.0),
                        float(item.timeline_item.GetProperty("CropLeft")) == float(0.0),
                        float(item.timeline_item.GetProperty("CropRight")) == float(0.0),
                        float(item.timeline_item.GetProperty("CropBottom")) == float(0.0),
                        float(item.timeline_item.GetProperty("Opacity")) == float(100.0),
                        float(item.timeline_item.GetProperty("CropSoftness")) == float(0.0)))

        except Exception as e:
            self.signals.warning_signal.emit(f"Ошибка получения значений трансформов: {e}")
        
    def is_multy_plates(self, timeline) -> dict:
        """
        Получаем словарь с количеством повторений шота на таймлайне.
        """
        extractor_obj = ResolveTimelineItemExtractor(timeline)
        timeline_items = [i.GetName() for i in extractor_obj.get_timeline_items(start_track=2, end_track=timeline.GetTrackCount("video")) if i != "" or i is not None]
        count_plate_tracks = Counter(timeline_items)
        return count_plate_tracks

    def burn_in_off(self) -> None:
        """
        Отключаем burn in.
        """
        self.project.LoadBurnInPreset("python_no_burn_in")

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
    
    def clear_render_jobs(self, render_jobs) -> None:
        """
        Очищаем render queue от всех созданных render jobs в процессе работы.
        """
        for job in render_jobs:
            self.project.DeleteRenderJob(job)
        logger.info(f"Очередь завершенных очередей рендера очищена")

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
        self.fps = self.user_config["fps"]

        self.rj_to_clear = []
        self.shots_tracks = {}

        try:
            self.resolve_api = self.get_api_resolve()
        except Exception as e:
            self.signals.error_signal.emit(str(e))
            return False

        self.resolve = self.resolve_api.resolve
        self.media_pool = self.resolve_api.mediapool
        self.timeline = self.resolve_api.timeline
        self.project = self.resolve_api.project

        if not self.is_connect_project():
            return False    

        self.timeline.DuplicateTimeline(self.timeline.GetName() + "_with_transform")
        self.project.SetCurrentTimeline(self.timeline)

        video_tracks = self.get_tracks()
        if video_tracks == []:
            self.signals.warning_signal.emit("Отсутствуют клипы для обработки.")
            return False

        self.count_plate_tracks = self.is_multy_plates(self.timeline)

        if not self.validate(video_tracks):
            return False

        self.burn_in_off()

        # Цикл по дорожкам(по основному и допплейтам, если таковые имеются).
        for track in video_tracks:

            track_items = self.get_mediapoolitems(start_track=track, end_track=track)

            self.set_disabled(track)

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

                project_preset_var = self.set_project_preset(track, item)
                if not project_preset_var:
                    return False

                item_resolution = self.get_resolution_settings(item)
                if not item_resolution:
                    return False

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
            self.timeline.ClearMarkInOut(type="all")
            self.resolve.OpenPage("edit")

        self.clear_render_jobs(self.rj_to_clear)
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
    warning_question_signal = pyqtSignal(str, object)

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
                "reference_preset": self.gui.reference_preset_combo.currentText().strip(),
                "handles": self.gui.handle_input.text().strip(),
                "linear_retime_handles": self.gui.retime_hndl_input.text().strip(),
                "non_linear_retime_handles": self.gui.nonlinear_hndl_input.text().strip(),
                "render_path": self.gui.render_path.text().strip(),
                "export_xml": self.gui.export_cb.isChecked(),
                "fps": self.gui.fps_entry.text(),
            }
        
        if self.mode == "names":
            return {"track_number": self.gui.from_track_qline.text().strip(),
                    "set_name_from_markers": self.gui.from_markers_cb.isChecked(),
                    "set_name_from_track": self.gui.from_track_cb.isChecked(),
                    "fps": self.gui.fps_entry.text(),
                    "locator_from": self.gui.locator_from_combo.currentText(),
                    "prefix_name": self.gui.prefix.text() + ("_", "")[self.gui.prefix.text() == ""],
                    "postfix_name": ("_", "")[self.gui.postfix.text() == ""] + self.gui.postfix.text(),
                    "set_track_id": self.gui.set_track_id.isChecked()
                    }
        
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

            if not any([user_config["set_name_from_markers"], user_config["set_name_from_track"]]):
                self.errors.append("Укажите метод установки имени")

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

        self.set_effects_btn = QPushButton("Set Burn-in")
        self.set_effects_btn.clicked.connect(lambda: self.run(EffectsAppender, mode="effects", button=self.set_effects_btn))

        self.fps_label = QLabel("FPS:")
        self.fps_entry = QLineEdit("24")
        self.fps_entry.setFixedWidth(50)

        self.locator_label = QLabel("from field:")
        self.locator_from_combo = QComboBox()
        self.locator_from_combo.setFixedWidth(70)
        self.locator_from_combo.addItems(["name", "note"])

        self.from_track_cb = QCheckBox("from track:")
        self.from_track_qline = QLineEdit("1")
        self.from_track_qline.setMaximumWidth(40)
        self.from_markers_cb = QCheckBox("from markers")
        self.set_names_btn = QPushButton("Start")
        self.set_names_btn.clicked.connect(lambda: self.run(NameSetter, mode="names", button=self.set_names_btn))

        self.res_group = QGroupBox("Film Resolution")
        self.res_group.setFixedHeight(70)
        self.res_group.setMinimumWidth(180)
        self.width_input = QLineEdit("2048")
        self.width_input.setFixedWidth(60)
        self.height_input = QLineEdit("858")
        self.height_input.setFixedWidth(60)

        self.preset_combo = QComboBox()
        self.preset_combo.addItems(PLATE_PROJECT_PRESETS)
        self.preset_combo.setCurrentText("aces1.2_smoother_preset")
        self.preset_combo.setMinimumWidth(180)

        self.reference_preset_combo = QComboBox()
        self.reference_preset_combo.addItems(REF_PROJECT_PRESETS)
        self.reference_preset_combo.setCurrentText("YRGB_ref_preset")
        self.reference_preset_combo.setMinimumWidth(180)

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

        self.prefix_label = QLabel("add prefix")
        self.postfix_label = QLabel("add postfix")
        self.prefix = QLineEdit("")
        self.prefix.setMaximumWidth(50)
        self.prefix.editingFinished.connect(lambda: self.get_shot_name())
        self.postfix = QLineEdit("")
        self.postfix.setMaximumWidth(50)
        self.postfix.editingFinished.connect(lambda: self.get_shot_name())
        self.shot_name_view = QLabel("###_####")
        self.set_track_id = QCheckBox("track id")
        self.set_track_id.stateChanged.connect(lambda: self.get_shot_name())
        self.set_track_id.setChecked(True)

        self.separator_set_name = QFrame()
        self.separator_set_name.setFrameShape(QFrame.HLine)
        self.separator_set_name.setStyleSheet("""
                                    QFrame {color: #555;
                                            background-color: #555}
                                        """)

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
        step2_group.setMinimumHeight(160)
        names_layout = QVBoxLayout()
        input_track_layout = QHBoxLayout()
        btn_layout = QHBoxLayout()
        shot_name_layout = QHBoxLayout()

        input_track_layout.addWidget(self.from_track_cb)
        input_track_layout.addWidget(self.from_track_qline)
        input_track_layout.addSpacing(40)
        input_track_layout.addWidget(self.from_markers_cb)
        input_track_layout.addSpacing(20)
        input_track_layout.addWidget(self.locator_label)
        input_track_layout.addWidget(self.locator_from_combo)
        input_track_layout.addSpacing(20)
        input_track_layout.addWidget(self.fps_label)
        input_track_layout.addWidget(self.fps_entry)
        input_track_layout.addStretch()

        shot_name_layout.addWidget(self.prefix_label)
        shot_name_layout.addWidget(self.prefix)
        shot_name_layout.addSpacing(20)
        shot_name_layout.addWidget(self.postfix_label)
        shot_name_layout.addWidget(self.postfix)
        shot_name_layout.addSpacing(20)
        shot_name_layout.addWidget(self.set_track_id)
        shot_name_layout.addSpacing(100)
        shot_name_layout.addWidget(self.shot_name_view)
        shot_name_layout.addStretch()

        btn_layout.addWidget(self.set_names_btn)
        
        names_layout.addSpacing(10)
        names_layout.addLayout(input_track_layout)
        names_layout.addWidget(self.separator_set_name)
        names_layout.addLayout(shot_name_layout)
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
        preset_layout.addWidget(self.reference_preset_combo)
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
        try:
            self.resolve = ResolveObjects()
            self.project = self.resolve.project
            return [preset["Name"] for ind, preset in self.project.GetPresets().items()]
        except RuntimeError as re:
            self.on_error_signal(str(re))
    
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
    
    def get_shot_name(self):
        self.base_shot_name = "###_####"
        result_shot_name = self.prefix.text() + ("_", "")[self.prefix.text() == ""] + self.base_shot_name + ("_", "")[self.postfix.text() == ""] + self.postfix.text() + ("", "_VT1")[self.set_track_id.isChecked()]
        self.shot_name_view.setText(result_shot_name)

    def on_success_signal(self, message):
        QMessageBox.information(self, "Успех", message)

    def on_warning_signal(self, message):
        QMessageBox.warning(self, "Предупреждение", message)
        logger.warning(message)

    def on_error_signal(self, message):
        QMessageBox.critical(self, "Ошибка", message)
        logger.exception(message)


    def on_question_signal(self, message, callback):
        reply = QMessageBox.question(
            self,
            "Подтверждение",
            message,
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No
        )
        logger.warning(message)
        callback(reply)

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
            self.on_error_signal("\n".join(self.validator.get_errors()))
            return
   
        logger.info(f"\n\n{pformat(self.user_config)}\n")
        thread = ThreadWorker(self, logic_class, self.user_config)
        thread.success_signal.connect(self.on_success_signal)
        thread.warning_signal.connect(self.on_warning_signal)
        thread.error_signal.connect(self.on_error_signal)
        thread.warning_question_signal.connect(self.on_question_signal)

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
