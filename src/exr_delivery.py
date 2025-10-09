import sys
import re
import math
import time
from pprint import pformat
from pathlib import Path
from timecode import Timecode as tc
from PyQt5.QtWidgets import (
    QApplication, QWidget, QLabel, QLineEdit, QPushButton,
    QVBoxLayout, QHBoxLayout, QComboBox, QFileDialog, QMessageBox, QGroupBox, QCheckBox, QTextEdit
)
from PyQt5.QtCore import Qt, QThread, pyqtSignal, QEventLoop
from dvr_tools.logger_config import get_logger
from dvr_tools.css_style import apply_style
from dvr_tools.resolve_utils import ResolveObjects
from dvr_tools.resolve_utils import ResolveTimelineItemExtractor


logger = get_logger(__file__)

SETTINGS = {
    "plate_suffix": '_VT',
    "colors": ["Orange", "Yellow", "Lime", "Violet", "Blue"],
    "extentions": (".mxf", ".braw", ".arri", ".r3d", ".dng", ".cine"),
    "false_extentions": (".mov", ".mp4", ".jpg")
}

class DvrTimelineObject():
    """
    Объект с атрибутами итема на таймлайне.
    """
    def __init__(self, mp_item, track_type_ind, clip_start_tmln, source_start, source_end, clip_dur, clip_color, timeline_item):
        self.mp_item = mp_item
        self.track_type_ind = track_type_ind
        self.clip_start = clip_start_tmln
        self.clip_duration = clip_dur
        self.clip_end = self.clip_start + (self.clip_duration - 1)
        self.source_start = source_start
        self.source_end = source_end
        self.clip_color = clip_color
        self.timeline_item = timeline_item

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
        Присвоение имен из маркеров.
        """
        markers = self.get_markers()

        for track_index in range(2, self.count_of_tracks + 1):
            clips_under = self.timeline.GetItemListInTrack('video', track_index)
            for clip_under in clips_under:
                applied = False  # было ли имя присвоено этому текущему clip_under
                for name, timecode in markers:
                    if clip_under.GetStart() <= timecode < (clip_under.GetStart() + clip_under.GetDuration()):
                        # Вычитаем - 1, чтобы отсчет плейтов был с первой дорожки, а не второй
                        name_new = name + SETTINGS["plate_suffix"] + str(track_index - 1)
                        clip_under.SetName(name_new)
                        logger.info(f'Добавлено кастомное имя "{name_new}" в клип на треке {track_index}')
                        applied = True

                if not applied:
                    self.warnings.append(f"Для клипа {clip_under.GetName()} на треке {track_index} не было установлено имя")

    def from_offline(self, items) -> None:
        """
        Присвоение имен из оффлайн клипов.
        """
        for track_index in range(2, self.count_of_tracks + 1):
            clips_under = self.timeline.GetItemListInTrack('video', track_index)
            for clip_under in clips_under:
                applied = False 

                for item in items:
                    if clip_under.GetStart() == item.GetStart():
                        # Вычитаем - 1 чтобы отсчет плейтов был с первой дорожки, а не второй
                        name = item.GetName() + SETTINGS["plate_suffix"] + str(track_index - 1)
                        clip_under.SetName(name)
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

    def run(self) -> None:
        """
        Основная логика.
        """
        resolve = self.get_api_resolve()
        self.timeline = resolve.timeline
        self.media_pool = resolve.mediapool
        self.timeline_start_tc = self.timeline.GetStartFrame()

        self.track_number = int(self.user_config["track_number"])
        self.name_from_track = self.user_config["set_name_from_track"]
        self.name_from_markers = self.user_config["set_name_from_markers"]
        self.fps = int(self.user_config["fps"])
        self.marker_from = self.user_config["locator_from"]

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
                                item.GetClipColor(), item))
        return filtred_items
    
    def get_tracks(self, start_track=2, track_type="video") -> list:
        """
        Получем индексы не пустых треков.
        """
        no_empty_tracks = []
        all_track = self.timeline.GetTrackCount(track_type)
        for track_num in range(start_track, all_track + 1):
            if self.timeline.GetItemListInTrack(track_type, track_num) != []:
                no_empty_tracks.append(track_num)

        return no_empty_tracks
    
    def set_project_preset(self) -> bool:
        """
        Установка пресета проекта.
        """
        set_preset_var = self.project.SetPreset(self.project_preset)
        if set_preset_var is not None:
            logger.info(f"Применен пресет проекта: {self.project_preset}")
            return True
        else:
            self.signals.error_signal.emit(f"Пресет проекта не применен {self.project_preset}")
            return False
    def set_disabled(self, current_track_number):
        '''
        Отключаем все дорожки кроме текущей.
        '''
        self.max_track = self.timeline.GetTrackCount("video")
        for track_number in range(1, self.max_track + 1):
            self.timeline.SetTrackEnable("video", track_number, track_number == current_track_number)
        logger.info(f"Начало работы с {current_track_number} треком")

    def get_handles(self, timeline_item, hide_log=True) -> str:
        '''
        Получаем значения захлестов.
        '''
        start_frame = timeline_item.source_start
        end_frame = timeline_item.source_end
        duration = timeline_item.clip_duration
        source_duration = end_frame - start_frame

        if self.frame_handles == 0:
            return f"EXR_{self.frame_handles}hndl"
        
        # Если source duration врет на 1 фрейм то вычитаем или прибавляем его(баг Resolve).
        # Второе условие пропускает только ретаймы кратные 100(т.е 100, 200, 300 и тд)

        if source_duration % duration == 1 and ((source_duration - 1) / duration * 100) % 100 == 0.0:
            source_duration = source_duration - 1 
        elif duration % source_duration == 1 and ((source_duration + 1) / duration * 100) % 100 == 0.0:
            source_duration = source_duration + 1 

        retime_speed = source_duration / duration * 100

        if retime_speed > 1000:
            raise ValueError
        
        abs_speed = abs(retime_speed)
        excess = max(0, abs_speed - 100)

        if hide_log:
            logger.info(f"Retime speed - {abs_speed}")

        increment = math.ceil(excess / 33.34)
        handles = self.frame_handles + increment

        return f"EXR_{handles}hndl"
    
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

        :return resolution: Разрешение в виде строки : '2500x858'.
        """
        
        clip = timeline_item.mp_item
        clip_color = timeline_item.clip_color

        # Стандартное разрешение от final delivery res
        if clip.GetName() != '' and clip.GetName().lower().endswith(SETTINGS["extentions"]) and clip_color == SETTINGS["colors"][0]:
            resolution = self.standart_resolution(clip)
        # 1.5-кратное увеличение разрешение от стандартного
        elif clip.GetName() != '' and clip.GetName().lower().endswith(SETTINGS["extentions"]) and clip_color == SETTINGS["colors"][1]:
            resolution = self.scale_1_5_resolution(clip)
        
        # 2-кратное увеличение разрешение от стандартного(условный 4К)
        elif clip.GetName() != '' and clip.GetName().lower().endswith(SETTINGS["extentions"]) and clip_color == SETTINGS["colors"][2]:
            resolution = self.scale_2_resolution(clip)
            
        # Полное съемочное разрешение
        elif clip.GetName() != '' and clip.GetName().lower().endswith(SETTINGS["extentions"]) and clip_color == SETTINGS["colors"][3]:
            resolution = self.full_resolution(clip)

        return resolution
    
    def stop_process(self) -> None:
        """
        Приостановка конвеера, пока идет процесс рендера текущего итема.
        """
        def rendering_in_progress():
            return self.project.IsRenderingInProgress()
        while rendering_in_progress():
            time.sleep(0.1)

    def set_render_preset(self, handles_value) -> bool:
        '''
        Метод ищет полученное в get_retime значение захлеста через регулярное выражение 
        в списке всех пресетов рендера.
        '''
        preset_list = self.project.GetRenderPresetList()
        if self._last_render_preset != handles_value:
            for preset in preset_list:
                if re.match(handles_value, preset):
                    self.project.LoadRenderPreset(preset)
                    self._last_render_preset = handles_value
                    logger.info(f"Установлен пресет рендера: {handles_value} ")
                    return True
            self.signals.error_signal.emit(f"Не удалось применить пресет рендера {handles_value}")
            return False 
        else:
            return True
            
    def set_project_resolution(self, height_res, width_res) -> None:
        """
        Установка проектного разрешения перед рендером.
        """
        self.project.SetSetting("timelineResolutionHeight", height_res)
        self.project.SetSetting("timelineResolutionWidth", width_res)
            
    def set_render_settings(self, clip, clip_resolution) -> tuple:
        '''
        Метод задает настройки для  рендера текущего итема 
        и добавляет текущий render job в очередь.

        :return: Кортеж (Флаг ошибки, render job item)
        '''
        try:
            resolution = re.search(r'\d{4}x\d{3,4}', clip_resolution).group(0)
            width, height = resolution.split("x")
            logger.info(f"Установлено разрешение с настройках рендера: {width}x{height}")
        except Exception as e:
            self.signals.error_signal.emit(f"Не удалось вычислить разрешение {resolution}: {e}")
            return False, None
        
        if resolution != self._last_resolution:
            self.set_project_resolution(height, width)

        self._last_resolution = resolution

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
            self.rj_to_clear.append(render_job)
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
        if item.clip_color == SETTINGS["colors"][4]:
            return True

    def start_render(self, render_job) -> bool:
        """
        Запуск render job.
        """    
        start_render = self.project.StartRendering([render_job], isInteractiveMode=True)
        if not start_render:
            self.signals.error_signal.emit(f"Ошибка обработки рендера: {render_job}")
            return False
        return True
    
    def export_timeline(self) -> None:
        """
        Экспорт таймлайна после окончания рендера в формате xml.

        """
        xml_name = str(self.timeline.GetName())
        path = (Path(self.render_path) /  f'{xml_name}.xml').resolve()  
        result = self.timeline.Export(str(path), self.resolve.EXPORT_FCP_7_XML)
        if result is None:
            self.signals.warning_signal.emit(f"Ошибка экспорта таймлайна {xml_name}")
        else:
            logger.info(f"Таймлайн {xml_name} успешно экспортирован")

    def set_enabled(self) -> None:

        for track_number in range(1, self.max_track + 1):
            
            self.timeline.SetTrackEnable("video", track_number, True)

    def remove_transform(self, item) -> None:
        """
        Удаляет трансформы и кроппинг с таймлайн итема.

        Не используется.
        """
        item.timeline_item.SetProperty("Tilt", 0.000)
        item.timeline_item.SetProperty("ZoomX", 1.000)
        item.timeline_item.SetProperty("ZoomY", 1.000)
        item.timeline_item.SetProperty("Pitch", 0.000)
        item.timeline_item.SetProperty("Yaw", 0.000)
        item.timeline_item.SetProperty("RotationAngle", 0.000)
        item.timeline_item.SetProperty("CropLeft", 0.000)
        item.timeline_item.SetProperty("CropRight", 0.000)
        item.timeline_item.SetProperty("CropTop", 0.000)
        item.timeline_item.SetProperty("CropBottom", 0.000)
        item.timeline_item.SetProperty("Opacity", 100)
        item.timeline_item.SetProperty("CropSoftness", 0.000)

    def detect_transform(self, item) -> bool:
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

    def is_question_items(self, warnings) -> bool:
        """
        Обрабатываем false_extentions через диалоговое окно потока gui.
        """
        text = "\n".join([f"• '{name}' на треке {track}" for name, track in warnings])
        message = f"Обнаружены проблемные клипы:\n{text}\n\nХотите продолжить?"

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
            for track_num, track in enumerate(video_tracks, start=2):

                track_items = self.get_mediapoolitems(start_track=track, end_track=track)
                for item in track_items:

                    clip = item.mp_item

                    if clip.GetName().lower().endswith(SETTINGS["false_extentions"]) and not item.clip_color == SETTINGS["colors"][4]:
                        warnings_question.append((clip.GetName(), track_num))    

                    if not item.clip_color == SETTINGS["colors"][4]:
                        no_select = False

                    if not clip.GetName().lower().endswith(SETTINGS["extentions"]) and not clip.GetName().lower().endswith(SETTINGS["false_extentions"]):
                        warnings.append(f"• Не валидное расширение клипа {clip.GetName()} на треке {track_num}")

                    if float(clip.GetClipProperty("FPS")) != float(self.fps):
                        warnings.append(f"• FPS клипа {clip.GetName()} на треке {track_num} не соответствует проектному")
                    
                    if self.detect_transform(item):
                        warnings.append(f"• Уберите трансфомы/скейлы с клипов на треке {track}")
                        break

                    try:
                        if not item.clip_color == SETTINGS["colors"][4]:
                            self.get_handles(item, hide_log=False)
                    except ZeroDivisionError:
                        warnings.append(f"• Фриз-фрейм или однокадровый клип '{clip.GetName()}' на треке {track_num} должен рендериться без захлестов")
                    except ValueError:
                        warnings.append(f"• У клипа '{clip.GetName()}' на треке {track_num} ретайм свыше 1000%")
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
    
    def clear_render_jobs(self, render_jobs) -> None:
        """
        Очищаем render queue от всех созданных render jobs в процессе работы.
        """
        for job in render_jobs:
            self.project.DeleteRenderJob(job)

    def run(self) -> None:
        """
        Логика конвеера рендера.
        """
        self.resolve_api = self.get_api_resolve()
        self.resolve = self.resolve_api.resolve
        self.media_pool = self.resolve_api.mediapool
        self.timeline = self.resolve_api.timeline
        self.project = self.resolve_api.project
        self.project_preset = self.user_config["project_preset"]
        self.frame_handles = int(self.user_config["handles"])
        self.height_res_glob = self.user_config["resolution_height"]
        self.width_res_glob = self.user_config["resolution_width"]
        self.render_path = self.user_config["render_path"]
        self.export_bool = self.user_config["export_xml"]
        self.boe_fix = self.user_config["boe_fix"]
        self.fps = self.user_config["fps"]

        self.rj_to_clear = []
        self._last_render_preset = None
        self._last_resolution = None

        self.timeline.DuplicateTimeline(self.timeline.GetName() + "_with_transform")
        self.project.SetCurrentTimeline(self.timeline)

        video_tracks = self.get_tracks()
        if video_tracks == []:
            self.signals.warning_signal.emit("Отсутствуют клипы для обработки")
            return False

        project_preset_var = self.set_project_preset()
        if not project_preset_var:
            return False
        
        if not self.validate(video_tracks):
            return False

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

                item_resolution = self.get_resolution_settings(item)
                if not item_resolution:
                    return False

                # Ставится до установки render preset
                self.stop_process()

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
                "project_preset": self.gui.preset_combo.currentText().strip(),
                "handles": self.gui.handle_input.text().strip(),
                "render_path": self.gui.render_path.text().strip(),
                "export_xml": self.gui.export_cb.isChecked(),
                "boe_fix": self.gui.boe_fix_cb.isChecked(),
                "fps": self.gui.fps_entry.text(),
            }
        if self.mode == "names":
            return {"track_number": self.gui.from_track_qline.text().strip(),
                    "set_name_from_markers": self.gui.from_markers_cb.isChecked(),
                    "set_name_from_track": self.gui.from_track_cb.isChecked(),
                    "fps": self.gui.fps_entry.text(),
                    "locator_from": self.gui.locator_from_combo.currentText()}
    
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
            except ValueError:
                self.errors.append("Значения должны быть целыми числами")
            return not self.errors

        if self.mode == "names":
            try:
                int(user_config["track_number"])
                int(user_config["fps"])
            except ValueError:
                self.errors.append("Значения должны быть целыми числами")

            if not any([user_config["set_name_from_markers"], user_config["set_name_from_track"]]):
                self.errors.append("Укажите метод установки имени")
            return not self.errors    

    def get_errors(self) -> list:
        return self.errors

class ExrDelivery(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Plate Delivery")
        self.resize(650, 200)
        self.setWindowFlags(self.windowFlags() | Qt.WindowStaysOnTopHint)

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
        self.width_input = QLineEdit("2048")
        self.width_input.setFixedWidth(60)
        self.height_input = QLineEdit("858")
        self.height_input.setFixedWidth(60)

        self.preset_combo = QComboBox()
        self.preset_combo.addItems(["aces1.2_smoother_preset", "yrgb_smoother_preset"])
        self.preset_combo.setCurrentText("aces1.2_smoother_preset")
        self.preset_combo.setMinimumWidth(180)
        self.export_cb = QCheckBox("Export .xml")
        self.handle_input = QLineEdit("3")
        self.handle_input.setFixedWidth(40)
        self.boe_fix_cb = QCheckBox("BOE Fix")

        self.render_path = QLineEdit()
        self.browse_btn = QPushButton("Choose")
        self.browse_btn.clicked.connect(self.select_folder)

        self.init_ui()

    def init_ui(self):
        layout = QVBoxLayout()

        # -- Группа установки имен клипов
        step2_group = QGroupBox("Set Shot name")
        step2_group.setMinimumHeight(120)
        names_layout = QVBoxLayout()
        input_track_layout = QHBoxLayout()
        btn_layout = QHBoxLayout()
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
        btn_layout.addWidget(self.set_names_btn)
        names_layout.addLayout(input_track_layout)
        names_layout.addLayout(btn_layout)
        step2_group.setLayout(names_layout)
        layout.addWidget(step2_group)

        # --- Разрешение ---
        res_layout = QHBoxLayout()
        res_layout.addStretch()
        res_layout.addWidget(self.width_input)
        res_layout.addWidget(QLabel("x"))
        res_layout.addWidget(self.height_input)
        res_layout.addStretch()
        self.res_group.setLayout(res_layout)
        layout.addWidget(self.res_group, alignment=Qt.AlignHCenter)

        # --- Пресет + захлест ---
        preset_layout = QHBoxLayout()
        preset_layout.addWidget(QLabel("Project preset:"))
        preset_layout.addWidget(self.preset_combo)
        preset_layout.addSpacing(20)
        preset_layout.addWidget(QLabel("Handles:"))
        preset_layout.addWidget(self.handle_input)
        preset_layout.addSpacing(20)
        preset_layout.addWidget(self.export_cb)
        preset_layout.addSpacing(20)
        preset_layout.addWidget(self.boe_fix_cb)
        
        preset_layout.addStretch()
        layout.addLayout(preset_layout)

        # --- Путь рендера ---
        path_layout = QHBoxLayout()
        path_layout.addWidget(QLabel("Render path:"))
        path_layout.addSpacing(10)
        path_layout.addWidget(self.render_path)
        path_layout.addWidget(self.browse_btn)
        layout.addLayout(path_layout)

        # --- Кнопка запуска ---
        self.run_button = QPushButton("Start")
        self.run_button.clicked.connect(lambda: self.run(DeliveryPipline, mode="conform", button=self.run_button))
        layout.addWidget(self.run_button)

        palette_widget = self.create_color_palette()
        layout.addWidget(palette_widget)

        self.setLayout(layout)

    def create_color_palette(self, labels=None):
        palette_group = QGroupBox("")

        main_layout = QVBoxLayout()
        label_layout = QHBoxLayout()
        color_layout = QHBoxLayout()

        labels = {
            "Orange": "Standart res",
            "Yellow": "1.5x res",
            "Lime": "2x res",
            "Violet": "Full res",
            "Blue": "Ignore"
        }
        color_map = {
            "Orange": "#FFA500",
            "Yellow": "#FFFF00",
            "Lime": "#00FF00",
            "Violet": "#8A2BE2",
            "Blue": "#1E90FF"
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
            color_box.setFixedSize(107, 25)
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
        logger.info(message)

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
