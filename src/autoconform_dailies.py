import os
import sys
import re
import subprocess
from pprint import pformat
from pathlib import Path
from timecode import Timecode as tc
import OpenEXR
import opentimelineio as otio
from PyQt5.QtWidgets import (
    QApplication, QWidget, QLabel, QPushButton, QVBoxLayout, QHBoxLayout,
    QLineEdit, QTextEdit, QComboBox, QScrollBar, QFileDialog, QCheckBox, QFrame, QSizePolicy, QMessageBox,
    QGroupBox, QRadioButton, QButtonGroup
)
from PyQt5.QtCore import Qt, QThread, pyqtSignal
from pymediainfo import MediaInfo
from functools import cached_property
from dvr_tools.logger_config import get_logger
from dvr_tools.css_style import apply_style
from dvr_tools.resolve_utils import ResolveObjects, get_resolve_shot_list
from config.config_loader import load_config
from config.config import get_config
from config.global_config import GLOBAL_CONFIG
from common_tools.edl_parsers import EDLParser_v3, EDLParser_v23, detect_edl_parser

logger = get_logger(__file__)

class OTIOCreator:
    """
    Класс создания OTIO таймлайна.
    """
    def __init__(self, user_config, resolve_shot_list):
        self.user_config = user_config
        self.resolve_shot_list = resolve_shot_list
        self.send_warning = lambda msg: None
        self.frame_mask = get_config()["patterns"]["frame_number"]

    def get_shots_paths(self, path):
        """
        Получем список путей к подпапкам секвенций EXR, JPG (они же имена шотов)
        или к видеофайлам MOV, MP4.

        :param path: Путь к шотам из GUI.
        """
        paths = []
        for root, folders, files in os.walk(path):
            if self.not_movie_bool:
                for folder in folders:
                    paths.append(os.path.join(root, folder))
            else:
                for file in files:
                    paths.append(os.path.join(root, file))
        
        return paths
    
    def is_drop_frames(self, shot_frames, shot_path, shot_name):
        """
        Проверяет шот(секвенцию) на предмет битых кадров.
        Работает только с секвенциями.

        :return: Уведомление в GUI.
        """
        # Проверяем файлы на наличие веса ниже 10% от максимального
        max_frame_size = 0
        size_threshold = 0
        percent = 0.1
        for frame in shot_frames:
            frame_path = os.path.join(shot_path, frame)
            frame_size = os.path.getsize(frame_path)

            # Обновляем максимальный размер файла и порог
            if frame_size > max_frame_size:
                max_frame_size = frame_size
                size_threshold = max_frame_size * percent

            # Проверяем текущий файл
            if frame_size < size_threshold:
                warning_messege = f"🟡  Маленький размер файла {frame} в секвенции {shot_name}. Вес: {frame_size} байт."
                self.send_warning(warning_messege)
                logger.warning(f"\n{warning_messege}")
                break

    def is_duplicate(self, shot_name, resolve_timeline_objects) -> bool:
        '''
        Находит шоты, версии которых уже стоят на таймлайне и пропускает их.
        '''
        try:
            if shot_name in resolve_timeline_objects:
                return True
            return False
        except:
            return False
        
    def get_gap_value(self, edl_record_in, timeline_in_tc, edl_start_timecodes, track_index) -> int:
        """
        Метод определения продолжительности для первого GAP объекта и для всех остальных GAP объектов.

        :param timeline_in_tc: Таймкод начала таймлайна.
        :param edl_start_timecodes: Список конечных таймкодов предыдущего клипа для вычисления GAP на каждом треке.
        """
        gap_dur = 0
        if edl_start_timecodes[track_index] is None:
            gap_dur = self.timecode_to_frame(edl_record_in) - timeline_in_tc  # Разность стартового таймкода клипа из EDL и начала таймлайна для первого вхождения
        else:
            gap_dur = self.timecode_to_frame(edl_record_in) - self.timecode_to_frame(edl_start_timecodes[track_index])
        return gap_dur
    
    def is_miss_frames(self, shot_name, frames_list) -> bool: 
        """
        Функция проверяет есть ли битые кадры в секвенции.
        Работает только с секвенциями.
        """
        frames_numbers_list = [int(re.search(self.frame_mask, i).group(0).split(".")[0]) for i in frames_list]  
        if not all(frames_numbers_list[i] + 1 == frames_numbers_list[i + 1] 
                   for i in range(len(frames_numbers_list) - 1)):
            message = f"🔴  Шот {shot_name} имеет пропущенные фреймы. Необходимо добавить шот вручную."
            self.send_warning(message)
            logger.warning(message)
            return False
        return True
    
    def timecode_to_frame(self, timecode)-> int:
        """
        Метод получает таймкод во фреймах.
        """
        return tc(self.frame_rate, timecode).frames
    
    def frame_to_timecode(self, frames):
        """
        Метод получает таймкод из значений фреймов.
        """
        return tc(self.frame_rate, frames=frames)
    
    def get_filtred_shots(self, shot_name):
            """
            Метод обходит папку с секвенциями или видеофайлами и отбирает только те, 
            которые пересекаются с именем шота из EDL.

            :param shot_name: Имя шота из EDL.

            :return: Список путей с фильтрованными по имени шота фолдерами(секвенциями) или видеофайлами.
            Если присутствует несколько версий шота, в аутпут списке будут несколько версий.
            """
            target_list = []

            for folder_path in self.shots_paths:
                folder_name = os.path.basename(folder_path)
                if self.not_movie_bool:
                    if re.search(shot_name.lower(), folder_name): 
                        target_list.append(folder_path)
                else:
                    if folder_name.endswith((".mov", ".mp4")) and re.search(shot_name.lower(), folder_name): 
                        target_list.append(folder_path)

            return target_list

    def split_name(self, clip_name) -> tuple:
        """
        Метод разбивает полное имя секвенции кадров на префикс, суффикс и стартовый фрэйм.
        Обрабатывает только такие имена: 015_3030_comp_v002.1004.exr и 015_3030_comp_v002_1004.exr.
        """

        match = re.search(fr'(.+?)([\._])\[(\d+)-\d+\]\.{self.clip_extension.lower()}$', clip_name)
        if not match:
            raise ValueError(f"Невозможно разобрать имя секвенции: {clip_name}")
        pref = match.group(1) + match.group(2)
        suff = f".{self.clip_extension.lower()}"
        start = match.group(3)

        return (pref, suff, start)

    def set_gap_obj(self, gap_duration, track_index):
        """
        Метод создает объект GAP в OTIO конструкторе.
        """
        # Получаем существующий видеотрек
        video_track = self.otio_timeline.tracks[track_index]

        # Проверка на наличине или отсутствие GAP между клипами
        if gap_duration > 0:

            gap = otio.schema.Gap(
                source_range=otio.opentime.TimeRange(
                    start_time=otio.opentime.RationalTime(0.0, self.frame_rate),
                    duration=otio.opentime.RationalTime(gap_duration, self.frame_rate),
                )
            )
            video_track.append(gap)

            logger.info(f'\nGAP duration: {gap_duration}')

    def set_timeline_obj_clip(self, shot_data, shot_start_frame, track_index):
        """
        Функция добавления треков и gap объектов на таймлайн для видеофайлов.
        """
        try:
            video_track = self.otio_timeline.tracks[track_index]

            clip_duration = shot_data['source duration']
            clip_path = shot_data['exr_path']
            clip_name = shot_data['shot_name']
            clip_start_frame = shot_data['source_in_tc']
            timeline_duration = shot_data['timeline_duration']

            debug_exr_info = f'\nShot name: {clip_name}\nShot start timecode: {clip_start_frame}\nShot duration: {clip_duration}\nShot path: {clip_path}'
            logger.debug(f'\n{debug_exr_info}')

            # Создание ссылки на видеофайл
            media_reference = otio.schema.ExternalReference(
                target_url=clip_path,
                available_range=otio.opentime.TimeRange(
                    start_time=otio.opentime.RationalTime(clip_start_frame, self.frame_rate),
                    duration=otio.opentime.RationalTime(clip_duration, self.frame_rate),
                ),
            )

            # Создание клипа
            clip = otio.schema.Clip(
                name=clip_name,
                media_reference=media_reference,
                source_range=otio.opentime.TimeRange(
                    start_time=otio.opentime.RationalTime(shot_start_frame or 0, self.frame_rate),
                    duration=otio.opentime.RationalTime(timeline_duration, self.frame_rate),
                ),
            )
            # Добавление на трек
            video_track.append(clip)

        except Exception as e:
            logger.exception(f"Не удалось добавить на таймлайн секвенцию {clip_name}.") 

    def set_timeline_obj_seq(self, shot_data, shot_start_frame, track_index):
        """
        Функция добавления треков и gap объектов на таймлайн для секвенций.
        """
        try:
            video_track = self.otio_timeline.tracks[track_index]

            clip_duration = shot_data['source duration']
            clip_path = shot_data['exr_path']
            clip_name = shot_data['shot_name']
            clip_start_frame = shot_data['source_in_tc']
            timeline_duration = shot_data['timeline_duration']

            pref, suff, start = self.split_name(clip_name)

            logger.info(f'\nShot name: {clip_name}\nShot start timecode: {clip_start_frame}\nShot duration: {clip_duration}\nShot path: {clip_path}\nParse name: {pref, suff, start}')

            # Создание ссылки на клип
            media_reference = otio.schema.ImageSequenceReference(
                target_url_base=clip_path,
                name_prefix=pref,
                name_suffix=suff,
                start_frame=int(start),
                frame_step=1,
                rate=self.frame_rate,
                frame_zero_padding=len(start),
                missing_frame_policy=otio.schema.ImageSequenceReference.MissingFramePolicy.error,
                available_range=otio.opentime.TimeRange(
                    start_time=otio.opentime.RationalTime(clip_start_frame, self.frame_rate),
                    duration=otio.opentime.RationalTime(clip_duration, self.frame_rate),
                ),
            )

            # Создание клипа
            clip = otio.schema.Clip(
                name=clip_name,
                media_reference=media_reference,
                source_range=otio.opentime.TimeRange(
                    start_time=otio.opentime.RationalTime(shot_start_frame or 0, self.frame_rate),
                    duration=otio.opentime.RationalTime(timeline_duration, self.frame_rate),
                ),
            )

            # Добавление на трек
            video_track.append(clip)

        except Exception as e:
            logger.exception(f"Не удалось добавить на таймлайн секвенцию {clip_name}.") 

    def count_timeline_objects(self):
        """
        Получение количества объектов на таймлайне.
        """
        return sum([len(track) for track in self.video_tracks]) 

    def create_video_tracks(self):
        """
        Создание списка заданного количества объектов видео треков на OTIO таймлайне.

        :return: Метод ничего не возвращает.
        """
        self.video_tracks = []
        self.track_count = 10
        for num in range(self.track_count):
            self.video_tracks.append(otio.schema.Track(name=f'Video{num+1}', kind=otio.schema.TrackKind.Video))
            self.otio_timeline.tracks.append(self.video_tracks[num])
    
    def is_correct_lenght(self, source_duration, timeline_duration, shot_name, message=""):
        """
        Метод вычисляет фактическую длину шота по данным, полученным, из логики и сравнивает с таймлайн диапазоном полученным из EDL.

        :return: Метод ничего не возвращает.
        """
        if source_duration < timeline_duration:
            result = timeline_duration - source_duration
            warning_message = f"🟡  Шот {shot_name} короче, чем его длина в EDL{message}."
            self.send_warning(warning_message)
            logger.warning(f'\n{warning_message}')

    def is_correct_fps(self, shot) -> bool:
        """
        Сравнивает проектный fps и fps шота.
        """
        try:
            frame = OpenEXR.InputFile(shot.first_frame_path)
            header = frame.header()
            frame_fps = header.get('nuke/input/frame_rate')

            if frame_fps is not None:
                # Иногда информация о фрейм рейте хранится в байтовом представлении. Учитываем это.
                frame_fps = float(frame_fps.decode()) if isinstance(frame_fps, bytes) else float(frame_fps)
                if int(self.frame_rate) != int(frame_fps):
                    warning_message = f"🔴  FPS шота {shot.name} расходится с проектным. FPS - {round(frame_fps, 2)}. Необходимо добавить шот вручную."
                    self.send_warning(warning_message)
                    logger.warning(warning_message)
                    return  False
                return True
            return True
                
        except Exception as e:
            message = f"Ошибка при обработке значения FPS {shot.first_frame_path}: {e}"
            logger.exception(message)
            return True
        
    def validate_shot(self, shot) -> bool:
        """
        Метод-агрегатор валидаторов шота.
        """
        if self.ignore_dublicates_bool:
            if self.is_duplicate(shot.name, self.resolve_shot_list):
                return False

        if not self.is_miss_frames(shot.name, shot.frames_list):
            return False
        if not self.is_correct_fps(shot):
            return False

        self.is_drop_frames(shot.frames_list, shot.path, shot.name)

        return True


    def get_shot(self, edl_shot_name, shot_path=None):
        """
        Ищет шот в self.user_config["shots_folder"] и собирает данные о шоте.
        Проверяет секвенцию на ошибки. Если в текущей версии шота есть ошибки - шот пропускается.

        :return shots_versions: Список с версиями валидных шотов.
        """
        try:
            filtred_shot_paths = self.get_filtred_shots(edl_shot_name)
            shots_versions = []
            for shot_path in filtred_shot_paths:
                if not shot_path:
                    return []
                
                if self.not_movie_bool:
                    shot = SequenceFrames(shot_path, self.clip_extension)
                    if not shot:
                        continue

                    validate_bool = self.validate_shot(shot)
                    if not validate_bool:
                        continue

                    shots_versions.append(shot)         
                else:
                    shot = MovieObject(shot_path)
                    if not shot:
                        continue

                    shots_versions.append(shot)

            return shots_versions
        
        except Exception as e:
            error_message = f"Ошибка при обработке секвенции: {e}"
            logger.exception(error_message) 
            self.send_warning(f'🔴  Ошибка при обработке шота {edl_shot_name}. Необходимо добавить его вручную в Media Pool.')
            return []
        
    def cut_slate(self, source_in_tc) -> int:
        """
        Метод отрезает 1 кадр слейта в .mov дейлизах, оставляя его в захлесте
        """
        return source_in_tc + 1
    
    def resolve_compensation_tc(self, frame) -> int:
        """
        Вычитает -1 фрейм для корректной интерпретации в Resolve.
        """
        return frame - 1
    
    def resolve_compensation_edl(self, frame) -> int:
        """
        Вычитает -1 фрейм. 
        В EDL изначально edl_source_out + 1 для правильной машинной интерпретации, 
        но для логики сравнения в программе это не корректно.
        """
        return frame - 1

    def start_frame_logic(self, data):
        """
        Логика конформа шотов которая устанавливает с какого фрейма будет начинаться шот на таймлайне.
        Значение получено из ui.

        :return: Метод ничего не возвращает.
        """  
        source_in = data["source_in_tc"]
        shot_name = data["shot_name"]
        gap_duration = data["gap_duration"]
        track_index = data["track_index"]
        source_duration = data["source_duration"]
        timeline_duration = data["timeline_duration"]

        shot_start_frame = self.resolve_compensation_tc(source_in) + self.start_frame_ui

        self.is_correct_lenght(source_duration, timeline_duration, shot_name)

        self.set_gap_obj(gap_duration, track_index)  

        if self.not_movie_bool:
            self.set_timeline_obj_seq(data, shot_start_frame, track_index)
        else:
            self.set_timeline_obj_clip(data, shot_start_frame, track_index)
    
    def edl_start_logic(self, data):
        """
        Логика конформа шотов определяет вхождение сорс диапазона шота в таймлайн диапазон из EDL.
        Если условие удовлетворяется - получаем стартовый таймкод из EDL и передаем в set_timeline_obj_seq/clip
        для выставления этого значения в качестве начального таймкода клипа.

        :return: Метод ничего не возвращает.
        """  
        source_in = data["source_in_tc"]
        source_out = data["source_out_tc"]
        shot_name = data["shot_name"]
        edl_source_in = self.timecode_to_frame(data["edl_source_in"])
        edl_source_out = self.resolve_compensation_edl(self.timecode_to_frame(data["edl_source_out"]))
        gap_duration = data["gap_duration"]
        track_index = data["track_index"]
        source_duration = data["source_duration"]
        timeline_duration = data["timeline_duration"]
        edl_record_in = data["edl_record_in"]
        edl_record_out = data["edl_record_out"]

        shot_start_frame = None  # None по дефолту на случай, если пересечения таймкодов нет.

        self.is_correct_lenght(source_duration, timeline_duration, shot_name)

        if edl_source_in >= source_in and edl_source_out <= source_out:  
            shot_start_frame = edl_source_in - 1
            data["source_in_tc"] = source_in - 1 

        self.set_gap_obj(gap_duration, track_index)  

        if self.not_movie_bool:
            self.set_timeline_obj_seq(data, shot_start_frame, track_index)
        else:
            self.set_timeline_obj_clip(data, shot_start_frame, track_index)

        logger.info("\n".join(( "\n",
                                f'Source in (frame): {data["source_in_tc"]}', f'Source out (frame): {source_out}', 
                                f'Shot start frame: {shot_start_frame}'
                                f'EDL record in: {edl_record_in}', f'EDL record out: {edl_record_out}',
                                f'EDL source in (frame): {edl_source_in}', f'EDL source out (frame): {edl_source_out}', 
                                f'Timeline duration: {timeline_duration}', "\n\n\n")))

    def full_conform_logic(self, data):
        """
        Логика конформа шотов, учитывающая все сценарии пересечения тайкодов исходника,
        полученных из EDL и данных таймкодов, полученных непосредственно из шота.
        В случае полного отсутствия пересечения таймкодов используется значение из ui, которое устанавливает
        с какого фрейма будет начинаться шот на таймлайне.

        :return: Метод ничего не возвращает.
        """
        source_in = data["source_in_tc"]
        source_out = data["source_out_tc"]
        shot_name = data["shot_name"]
        edl_source_in = self.timecode_to_frame(data["edl_source_in"])
        edl_source_out = self.resolve_compensation_edl(self.timecode_to_frame(data["edl_source_out"]))
        gap_duration = data["gap_duration"]
        track_index = data["track_index"]
        timeline_duration = data["timeline_duration"]
        edl_record_in = data["edl_record_in"]
        edl_record_out = data["edl_record_out"]
        retime_bool = data["retime_bool"]

        shot_start_frame = None

        # Полное отсутствие пересечения
        if source_out < edl_source_in or source_in > edl_source_out:

            self.start_frame_logic(data)
    
            self.send_warning(f"🟡  Шот {shot_name}. Нет пересечения диапазона.")
            logger.info(f"Шот {shot_name}. Нет пересечения диапазона.")


        # Полное пересечение (EDL внутри исходника)
        elif edl_source_in >= source_in and edl_source_out <= source_out:  

            data["source_in_tc"] = self.resolve_compensation_tc(source_in) 
            shot_start_frame = self.resolve_compensation_tc(edl_source_in)
            logger.debug("Полное пересечение (EDL внутри исходника)")

            self.set_gap_obj(gap_duration, track_index)

            if self.not_movie_bool:
                self.set_timeline_obj_seq(data, shot_start_frame, track_index)
            else:
                self.set_timeline_obj_clip(data, shot_start_frame, track_index)
        
        # Часть исходника ДО EDL, часть внутри
        elif edl_source_in >= source_in and edl_source_out > source_out:

            if retime_bool:
                logger.info(f"Шот {shot_name} имеет ретайм")

            shot_start_frame = self.resolve_compensation_tc(edl_source_in)
            cutted_duration = edl_source_out - source_out
            data["timeline_duration"] = data["timeline_duration"] - cutted_duration
            data["source_in_tc"] = self.resolve_compensation_tc(source_in)
            logger.debug("Часть исходника ДО EDL, часть внутри")

            # Рабочий диапазон исходника на таймлайне
            working_source_range = source_out - edl_source_in
            self.is_correct_lenght(working_source_range, timeline_duration, shot_name, " по концу")

            self.set_gap_obj(gap_duration, track_index)  

            if self.not_movie_bool:
                self.set_timeline_obj_seq(data, shot_start_frame, track_index)
            else:
                self.set_timeline_obj_clip(data, shot_start_frame, track_index)

            self.set_gap_obj(cutted_duration, track_index)

        # Часть исходника ПОСЛЕ EDL, часть внутри         
        elif edl_source_in < source_in and edl_source_out <= source_out:

            shot_start_frame = self.resolve_compensation_tc(source_in)
            cutted_duration = source_in - edl_source_in
            data["timeline_duration"] = data["timeline_duration"] - cutted_duration
            data["source_in_tc"] = self.resolve_compensation_tc(source_in)
            new_gap_duration = gap_duration + cutted_duration
            logger.debug("Часть исходника ПОСЛЕ EDL, часть внутри")
            
            # Рабочий диапазон исходника на таймлайне
            working_source_range = edl_source_out - source_in
            self.is_correct_lenght(working_source_range, timeline_duration, shot_name, " по началу")

            self.set_gap_obj(new_gap_duration, track_index)  

            if self.not_movie_bool:
                self.set_timeline_obj_seq(data, shot_start_frame, track_index)
            else:
                self.set_timeline_obj_clip(data, shot_start_frame, track_index)

        # Исходник полностью внутри EDL 
        elif edl_source_in < source_in and edl_source_out > source_out:

            if retime_bool:
                logger.info(f"Шот {shot_name} имеет ретайм")

            shot_start_frame = self.resolve_compensation_tc(source_in) 
            cutted_duration_start = source_in - edl_source_in
            cutted_duration_end = edl_source_out - source_out
            data["timeline_duration"] = data["timeline_duration"] - (cutted_duration_start + cutted_duration_end)
            data["source_in_tc"] = self.resolve_compensation_tc(source_in)
            gap_duration_start = gap_duration + cutted_duration_start
            logger.debug(f"Исходник полностью внутри EDL ")

            # Рабочий диапазон исходника на таймлайне
            working_source_range = source_out - source_in
            self.is_correct_lenght(working_source_range, timeline_duration, shot_name, " по началу и концу")

            self.set_gap_obj(gap_duration_start, track_index)  

            if self.not_movie_bool:
                self.set_timeline_obj_seq(data, shot_start_frame, track_index)
            else:
                self.set_timeline_obj_clip(data, shot_start_frame, track_index)

            self.set_gap_obj(cutted_duration_end, track_index)

        logger.info("\n".join(( "\n",
                                f'Source in (frame): {data["source_in_tc"]}', f'Source out (frame): {source_out}', 
                                f'Shot start frame: {shot_start_frame}'
                                f'EDL record in: {edl_record_in}', f'EDL record out: {edl_record_out}',
                                f'EDL source in (frame): {edl_source_in}', f'EDL source out (frame): {edl_source_out}', 
                                f'Timeline duration: {data["timeline_duration"]}', "\n\n\n")))

    def run(self):
        """
        Основная логика создания OTIO таймлайна.
        """
        self.edl_path = self.user_config["edl_path"]
        self.frame_rate = self.user_config["frame_rate"]
        self.ignore_dublicates_bool = self.user_config["ignore_dublicates"]
        self.clip_extension = self.user_config["extension"]
        self.handles_logic = self.user_config["handles_logic"]
        self.start_frame_ui = self.user_config["start_frame_ui"]
        self.not_movie_bool = self.clip_extension not in ("mov", "mp4")
        self.shots_paths = self.get_shots_paths(self.user_config["shots_folder"])
        self.include_slate = self.user_config["include_slate"]

        edl_data = detect_edl_parser(self.frame_rate, self.edl_path)

        try:
            self.otio_timeline = otio.schema.Timeline(name="Timeline") 
            self.create_video_tracks()
            # edl_start_timecodes: - Список промежуточных значений edl_record_out для вычисления GAP на каждом треке
            edl_start_timecodes = [None] * self.track_count 

            for data in edl_data:
                edl_shot_name = data.edl_shot_name
                edl_source_in = data.edl_source_in
                edl_source_out = data.edl_source_out
                edl_record_in = data.edl_record_in
                edl_record_out = data.edl_record_out
                timeline_in_tc = self.timecode_to_frame(edl_record_in.split(":")[0] + ":00:00:00")
                
                shot_versions = self.get_shot(edl_shot_name)

                if not shot_versions:
                    continue    

                for track_index, shot in enumerate(shot_versions):
                    
                    source_in_tc, source_out_tc, source_duration = shot.extract_timecode(self.frame_rate)

                    if self.include_slate:
                        source_in_tc = self.cut_slate(source_in_tc)

                    timeline_duration = self.timecode_to_frame(edl_record_out) - self.timecode_to_frame(edl_record_in)

                    gap_duration = self.get_gap_value(edl_record_in, timeline_in_tc, edl_start_timecodes, track_index)

                    shot_data = {
                        'exr_path': shot.path,
                        'shot_name': shot.name,
                        'source_in_tc': source_in_tc,
                        'source_out_tc': source_out_tc,
                        'source duration': source_duration,
                        'timeline_duration': timeline_duration,
                        'track_index': track_index,
                        'gap_duration': gap_duration,
                        'source_duration': source_duration,
                        "edl_source_in": edl_source_in,
                        "edl_source_out": edl_source_out,
                        "edl_record_in": edl_record_in,
                        "edl_record_out": edl_record_out,
                        "retime_bool": data.retime
                    }

                    # Выбор логики конформа
                    if self.handles_logic == "from_start_frame":
                        self.start_frame_logic(shot_data)
                    elif self.handles_logic == "from_edl_start":
                        self.edl_start_logic(shot_data)
                    elif self.handles_logic == "full_logic":
                        self.full_conform_logic(shot_data)

                    edl_start_timecodes[track_index] = edl_record_out

            timeline_objects = self.count_timeline_objects()
            return self.otio_timeline, timeline_objects

        except Exception as e:
            logger.exception(f"Сбой в работе программы. Не удалось сформировать OTIO файл: {e}") 

class MovieObject:
    
    """
    Класс-объект видеофайла .MOV или .MP4.
    """
    def __init__(self, path, frame_pattern=None):
        self.path = path

    @property
    def name(self)-> str:
        """
        Получение имени клипа.
        """
        return os.path.basename(self.path)
    
    def get_duration(self, frame_rate:int)-> int:
        """
        Получение длительности видеофайла.
        """
        try:
            media_info = MediaInfo.parse(self.path)

            for track in media_info.tracks:
                if track.track_type == "Video":
                    duration_seconds = track.duration / 1000  # переводим из миллисекунд в секунды
                    duration_frames = duration_seconds * frame_rate  # умножаем на частоту кадров

                    # Переводим в целое количество кадров
                    duration = int(duration_frames) - 1  # -1 для корректного восприятия в Davinci Resolve
                    return duration
                
        except Exception as e:
            print(f"Ошибка при получении длительности видео: {e}")
            return None
        
    def extract_timecode(self, frame_rate) -> tuple:
        """
        Получение стартового таймкода, конечного таймкода и длительности видеофайла.
        """
        try:
            media_info = MediaInfo.parse(self.path)
            # Получаем длительность и начальный таймкод видео
            for track in media_info.tracks:
                if track.track_type == "Video":

                    # Длительность видео в секундах
                    duration_seconds = track.duration / 1000  # переводим из миллисекунд в секунды
                    duration_frames = duration_seconds * frame_rate  # умножаем на частоту кадров
                    duration = int(duration_frames) - 1  # -1 для корректного восприятия в Davinci Resolve

                    # Извлекаем начальный таймкод
                    if track.other_delay:
                        start_timecode = tc(frame_rate, track.other_delay[4]).frames - 1  # -1 для корректного восприятия в Davinci Resolve

                    end_timecode = start_timecode + duration
                    return (start_timecode, end_timecode, duration)
            
        except Exception as e:
            print(f"Ошибка при получении длительности видео: {e}")
            return (None, None, None)

class SequenceFrames:
    """
    Класс-объект секвенций EXR или JPG.
    """
    def __init__(self, path_to_sequence, extension, frame_pattern=None):
        self.path = path_to_sequence
        self.extension = extension
        self.frame_mask = get_config()["patterns"]["frame_number"]
        self.shot_name_mask = get_config()["patterns"]["shot_name"]

    def __repr__(self):
        return F"Sequence'{self.name}'"
    
    def __str__(self):
        return f"{self.name}"
    
    def __getitem__(self, index):
        if not isinstance(index, int):
            raise ValueError("Некорректное значение индекса")
        return self.frames_list[index]

    @cached_property
    def frames_list(self):
        """
        Получаем список кадров секвенции отсортированных по возрастанию.
        """
        return sorted([f for f in os.listdir(self.path) if f.lower().endswith(f'.{self.extension.lower()}')])
    
    @cached_property
    def first_frame_path(self):
        """
        Определяем путь к первому кадру секвенции.
        """
        return os.path.join(self.path, self.frames_list[0])
    
    @property
    def last_frame_path(self) -> str:
        """
        Определяем путь к последнему кадру секвенции.
        """
        return os.path.join(self.path, self.frames_list[-1])
    
    @property
    def first_frame_number(self) -> str:
        """
        Извлекаем номер кадра из имени первого кадра секвенции.
        """
        match = re.search(self.frame_mask, self.first_frame_path)
        if not match:
            raise ValueError(f"Невозможно извлечь номер кадра из кадра {self.first_frame_path}.")
        return match.group(1)
    
    @property
    def last_frame_number(self) -> str:
        """
        Извлекаем номер кадра из имени последнего кадра секвенции.
        """
        match = re.search(self.frame_mask, self.last_frame_path)
        if not match:
            raise ValueError(f"Невозможно извлечь номер кадра из кадра {self.last_frame_number}.")
        return match.group(1)
    
    @property
    def name(self) -> str:
        """
        Получаем имя секвенции.
        Обрабатывает стандартный формат имени 015_3030_comp_v002.1004.exr
        и частый ошибочный формат имени 015_3030_comp_v002_1004.exr.
        """
        base_name = re.sub(self.shot_name_mask, '', os.path.basename(self.first_frame_path))
        frame_range = f"[{self.first_frame_number}-{self.last_frame_number}]"
        sep = '.' if '.' in os.path.splitext(self.first_frame_path)[0] else '_'
        return f"{base_name}{sep}{frame_range}.{self.extension.lower()}"
    
    @staticmethod
    def format_timecode(timecode_str: str) -> str:
        """
        Форматирует таймкод в двухзначный формат для всех его компонентов (HH:MM:SS:FF).
        """
        formatted_parts = ':'.join([part.zfill(2) for part in timecode_str.split(':')])  # Каждый элемент приводит к двухзначному формату
        return formatted_parts

    def extract_timecode(self, project_fps: int) -> tuple:
        """
        Извлекает таймкод из кадра секвенции и форматирует его.
        Настроен на композы из Nuke.
        """
        try:
            frame = OpenEXR.InputFile(self.first_frame_path)
            header = frame.header()
            timecode = header.get('timeCode', None) 
            start_timecode = None

            if timecode:

                # Таймкод хранится в формате объекта. Преобразуем в строку и извлекаем время.
                timecode_str = str(timecode)
                time_match = timecode_str.split("time: ")[1].split(",")[0].strip()  # Извлекаем значение времени

                start_timecode = self.format_timecode(time_match)  # Приводим к двухзначному формату
                 
            if start_timecode is None:
                start_timecode = tc(project_fps, "00:00:00:00").frames - 1  # компенсация некорректной конвертации таймкода во фреймы
                end_timecode = start_timecode + (len(self.frames_list))
                duration = (end_timecode - start_timecode)
            else:
                start_timecode = tc(project_fps, start_timecode).frames - 1  # компенсация некорректной конвертации таймкода во фреймы
                end_timecode = start_timecode + (len(self.frames_list))
                duration = (end_timecode - start_timecode)
                          
            return (start_timecode, end_timecode, duration)

        except Exception as e:
            message = f"Ошибка при обработке таймкода {self.first_frame_path}: {e}"
            logger.exception(message)
            return (None, None, None)

class OTIOWorker(QThread):
    """
    Класс работы с логикой в отдельном потоке.
    """
    error_signal = pyqtSignal(str)
    success_signal = pyqtSignal(str)
    warning_signal = pyqtSignal(str)
    info_signal = pyqtSignal(str)
    warnings = pyqtSignal(str)

    def __init__(self, parent, user_config, resolve_shot_list):
        super().__init__(parent)
        self.user_config = user_config
        self.otio_path = user_config["otio_path"]
        self.resolve_shot_list = resolve_shot_list

    def run(self):
        try:
            logic = OTIOCreator(self.user_config, self.resolve_shot_list)
            logic.send_warning = lambda msg: self.warnings.emit(msg)
            otio_timeline, timeline_objects = logic.run() #timeline_objects: Количество объектов на OTIO таймлайне
            if not timeline_objects:
                self.warning_signal.emit('Отсутствуют шоты для данной таймлинии')
                return

            otio.adapters.write_to_file(otio_timeline, self.otio_path)
            self.success_signal.emit(f"OTIO файл успешно создан: {self.otio_path}")

        except Exception as e:
            self.error_signal.emit(f"Не удалось создать OTIO файл: {e}")

class ConformCheckerMixin:
    """
    Методы примеси для класса Autoconform.
    """
    def count_otio_clips(self, otio_path) -> int:
        """
        Читает OTIO и получает количество видео-объектов(шотов) на таймлайне(не учитывая версии шотов)
        """
        try:
            timeline = otio.adapters.read_from_file(otio_path)
            total_clips = 0 

            for _, track in enumerate(timeline.tracks):
                clip_count = sum(1 for item in track if isinstance(item, otio.schema.Clip))
                total_clips += clip_count

            return total_clips

        except Exception as e:
            logger.warning(f"Ошибка при чтении OTIO: {e}")
            return 0

    def count_clips_on_storage(self, shots_folder, extension) -> int:
        """
        Сканирует папку на хранилище с шотами (секвенциями или видеофайлами), 
        участвующими в сборке OTIO, и получает их количество.
        """
        count = 0 
        for dirpath, _, files in os.walk(shots_folder):
            # Проверяем секвенцию. Если есть хотя бы 1 фрейм - плюсуем счетчик
            if extension.lower() not in ("mov", "mp4") and any(file.lower().endswith(f'.{extension.lower()}') for file in files):
                    count += 1  
                    continue
            # Проверяем видеофайлы
            else:  
                for file in files:
                    if file.lower().endswith(f'.{extension.lower()}'):
                        count += 1  
        return count
    
    def set_attributes(self):
        """
        Устанавливает цвет для шота, если к шоту не был применен цвет ранее.
        Устанавливает альфу на None.
        """
        resolve = ResolveObjects()
        current_folder = resolve.mediapool_current_folder.GetClipList()
        items = [item for item in current_folder if "Video" in item.GetClipProperty("Type")]
        for item in items:
            if item.GetClipProperty("Alpha mode") != "None":
                item.SetClipProperty("Alpha mode", "None") 
            if item.GetClipColor() == "":
                item.SetClipColor("Lime") 
    
    def resolve_import_timeline(self):
        """
        Импорт OTIO таймлайна в Davinci Resolve
        """
        try:
            resolve = ResolveObjects()
            media_pool = resolve.mediapool

            timeline = media_pool.ImportTimelineFromFile(self.otio_input.text(), {
                "timelineName": f"{os.path.basename(str(self.otio_input.text()))}",
                "importSourceClips": True,   
            })

            if timeline is None:
                QMessageBox.warning(self, "Ошибка", "Ошибка импорта таймлайна")
            
                    
        except Exception as e:
            QMessageBox.warning(self, "Ошибка", str(e))

    def get_shots_paths(self, path, extension) -> list:
        """
        Получем имена папок секвенций EXR, JPG (они же имена шотов)
        или имена видеофайлов MOV, MP4.

        :param path: Путь к шотам из GUI.

        :param extension: Расширение из GUI.
        """
        paths = []
        for root, folders, files in os.walk(path):
                for folder in folders:
                    for item in os.listdir(os.path.join(root, folder)):
                        if item.endswith(f".{extension}".lower()):
                            paths.append(folder)
                            break
        
        return paths

    def is_missing_shot(self, fps, shots_root_path, edits_path, extension):
        """
        Проверяет есть ли каждый из шотов в shots_folder во всех монтажах из edits_path.

        :param shots_root_path: Путь к шотам из GUI.

        :param edits_path: Путь к .edl монтажам(или монтажу).

        :return flag: 
        """
        shots_list = self.get_shots_paths(shots_root_path, extension)

        united_edls = [line.strip() for file in edits_path.glob("*edl")
        for line in file.read_text(encoding="utf-8", errors="ignore").splitlines()
        if line.strip()
        ]

        check_flag = False
        triger_flag = False

        parser = EDLParser_v3(fps, lines=united_edls)
        for shot_name in shots_list:
            
            for edl_line in parser:
                if edl_line.edl_shot_name in shot_name:
                    triger_flag = True
            
            if not triger_flag:
                self.warning_signal.emit(f"🔴  Шот {shot_name} отсутствует в монтаже")
                check_flag = True
            triger_flag = False

        if not check_flag:
            self.warning_signal.emit("🟢  Проверка пройдена успешно!")

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
        selected_radio = self.gui.logic_mode_group.checkedButton()
        handles_logic = selected_radio.property("mode")
        return {
            "edl_path": self.gui.edl_input.text().strip(),
            "shots_folder": self.gui.shots_input.text().strip(),
            "otio_path": self.gui.otio_input.text().strip(),
            "track_in": self.gui.track_in_input.text().strip(),
            "track_out": self.gui.track_out_input.text().strip(),
            "extension": self.gui.format_menu.currentText().lower(),
            "project": self.gui.project_menu.currentText(),
            "ignore_dublicates": self.gui.no_dublicates.isChecked(),
            "frame_rate": int(self.gui.frame_rate.text().strip()),
            "handles_logic": handles_logic,
            "start_frame_ui": int(self.gui.start_frame.text().strip()),
            "include_slate": self.gui.include_slate.isChecked()
        }
    
    def validate(self, user_config: dict) -> bool:
        """
        Валидирует конфиг.
        """
        self.errors.clear()

        if not user_config["edl_path"]:
            self.errors.append("Укажите путь к файлу EDL")
        if not os.path.exists(user_config["edl_path"]):
            self.errors.append("Указан несуществующий путь к EDL")
        if not user_config["shots_folder"]:
            self.errors.append("Укажите путь к папке с шотами")
        if not os.path.exists(user_config["shots_folder"]):
            self.errors.append("Указан несуществующий путь к шотам")
        if not user_config["otio_path"]:
            self.errors.append("Укажите путь к папке для сохранения OTIO")

        try:
            int(user_config["track_in"])
            int(user_config["track_out"])
            int(user_config["start_frame_ui"])
        except ValueError:
            self.errors.append("Значения должны быть целыми числами")
        return not self.errors

    def get_errors(self) -> list:
        return self.errors

class Autoconform(QWidget, ConformCheckerMixin):
    warning_signal = pyqtSignal(str)

    def __init__(self):
        super().__init__()
        self.setWindowTitle("Autoconform Dailies")
        self.resize(710, 820)
        self.setWindowFlag(Qt.WindowStaysOnTopHint)

        self.warning_signal.connect(self.appent_warning_field)

        self.frame_rate = 24
        self.frame_rate_label = QLabel("FPS:")
        self.frame_rate = QLineEdit("24")
        self.frame_rate.setMaximumWidth(30)

        self.selected_track_in = "8"
        self.selected_track_out = "8"
        self.selected_format = "EXR"
        self.select_frame = "3"

        self.otio_counter = 0
        self.folder_counter = 0

        self.projects = self.get_project()
        self.selected_project = self.projects[0] if self.projects else ""

        self.result_label = QLabel()

        self.from_start_frame_mode = QRadioButton()
        self.from_start_frame_mode.setChecked(True) 
        self.from_start_frame_mode.setProperty("mode", "from_start_frame")

        self.from_edl_start_mode = QRadioButton()
        self.from_edl_start_mode.setProperty("mode", "from_edl_start")

        self.full_conform_mode = QRadioButton()
        self.full_conform_mode.setProperty("mode","full_logic")

        self.init_ui()

    def init_ui(self):
        main_layout = QVBoxLayout()

        # Поле предупреждений
        self.warning_field = QTextEdit()
        self.warning_field.setReadOnly(True)
        self.warning_field.setMinimumHeight(250)
        self.warning_field.setPlainText("Здесь будут показаны предупреждения программы.\n")
        main_layout.addWidget(self.warning_field)

        # Логика
        logic_group = QGroupBox("Conform logic")
        logic_group.setMinimumHeight(90)
        logic_group.setMinimumWidth(400)
        logic_layout = QHBoxLayout()

        self.logic_mode_group = QButtonGroup(self)
        self.logic_mode_group.addButton(self.from_start_frame_mode)
        self.logic_mode_group.addButton(self.from_edl_start_mode)
        self.logic_mode_group.addButton(self.full_conform_mode)

        vbox1 = QVBoxLayout()
        from_start_label = QLabel("From start frame")
        from_start_label.setAlignment(Qt.AlignHCenter)
        vbox1.addWidget(self.from_start_frame_mode, alignment=Qt.AlignHCenter)
        vbox1.addWidget(from_start_label)

        vbox2 = QVBoxLayout()
        from_edl_label = QLabel("From EDL start")
        from_edl_label.setAlignment(Qt.AlignHCenter)
        vbox2.addWidget(self.from_edl_start_mode, alignment=Qt.AlignHCenter)
        vbox2.addWidget(from_edl_label)

        vbox3 = QVBoxLayout()
        full_logic_label = QLabel("Full conform")
        full_logic_label.setAlignment(Qt.AlignHCenter)
        vbox3.addWidget(self.full_conform_mode, alignment=Qt.AlignHCenter)
        vbox3.addWidget(full_logic_label)

        logic_layout.addStretch()
        logic_layout.addLayout(vbox1)
        logic_layout.addSpacing(25)
        logic_layout.addLayout(vbox2)
        logic_layout.addStretch()
        logic_layout.addLayout(vbox3)
        logic_layout.addStretch()

        outer_layout = QVBoxLayout()
        outer_layout.addStretch()
        outer_layout.addLayout(logic_layout)
        outer_layout.addStretch()

        logic_group.setLayout(outer_layout)
        main_layout.addWidget(logic_group, alignment=Qt.AlignHCenter)

        # Группа Settings
        settings_group = QGroupBox("Settings")
        settings_layout = QHBoxLayout()

        # Левая колонка: проект + расширение
        left_vbox = QVBoxLayout()

        project_label = QLabel("Project:")
        self.project_menu = QComboBox()
        self.project_menu.addItems(self.projects)
        self.project_menu.setCurrentText(self.selected_project)
        self.project_menu.currentTextChanged.connect(self.get_project_settings)
        self.project_menu.currentTextChanged.connect(self.project_ui_state)
        left_vbox.addWidget(project_label)
        left_vbox.addWidget(self.project_menu)

        format_label = QLabel("Extension:")
        self.format_menu = QComboBox()
        self.format_menu.addItems(["EXR", "JPG", "MOV", "MP4"])
        self.format_menu.setCurrentText(self.selected_format)
        self.format_menu.currentTextChanged.connect(self.update_ui_state)
        self.format_menu.setMinimumWidth(270)
        left_vbox.addWidget(format_label)
        left_vbox.addWidget(self.format_menu)

        separator = QFrame()
        separator.setFrameShape(QFrame.VLine)
        separator.setFrameShadow(QFrame.Sunken)

        # Правая колонка
        right_vbox = QVBoxLayout()

        # Первая строка: Ignore dubl + tracks range
        tracks_hbox = QHBoxLayout()
        self.no_dublicates = QCheckBox("Ignore dubl")
        tracks_hbox.addWidget(self.no_dublicates)

        tracks_hbox.addSpacing(5)
        tracks_hbox.addWidget(QLabel("from tracks:"))

        self.track_in_input = QLineEdit(self.selected_track_in)
        self.track_in_input.setFixedWidth(30)
        tracks_hbox.addWidget(self.track_in_input)

        tracks_hbox.addWidget(QLabel("-"))

        self.track_out_input = QLineEdit(self.selected_track_out)
        self.track_out_input.setFixedWidth(30)
        tracks_hbox.addWidget(self.track_out_input)
        tracks_hbox.addStretch()
        right_vbox.addLayout(tracks_hbox)

        # Вторая строка: Start frame + Include slate
        frame_hbox = QHBoxLayout()

        self.include_slate = QCheckBox("Include slate")
        self.include_slate.setChecked(True)
        frame_hbox.addWidget(self.include_slate)
        frame_hbox.addSpacing(20)
        frame_hbox.addWidget(self.frame_rate_label)
        frame_hbox.addWidget(self.frame_rate)
        frame_hbox.addSpacing(15)
        frame_hbox.addWidget(QLabel("Start frame:"))
        self.start_frame = QLineEdit(self.select_frame)
        self.start_frame.setMaximumWidth(30)
        frame_hbox.addWidget(self.start_frame)

        frame_hbox.addStretch()
        right_vbox.addLayout(frame_hbox)

        settings_layout.addLayout(left_vbox)
        settings_layout.addSpacing(20)
        settings_layout.addWidget(separator)
        settings_layout.addSpacing(20)
        settings_layout.addLayout(right_vbox)

        settings_group.setLayout(settings_layout)
        main_layout.addWidget(settings_group)

        # Выбор EDL
        edl_path_layout = QHBoxLayout()
        edl_path_layout.addWidget(QLabel("EDL file:"))
        edl_path_layout.addSpacing(32)
        self.edl_input = QLineEdit()
        edl_path_layout.addWidget(self.edl_input)
        self.edl_button = QPushButton("Choose")
        self.edl_button.clicked.connect(self.select_edl)
        edl_path_layout.addWidget(self.edl_button)
        main_layout.addLayout(edl_path_layout)

        # Выбор фолдера с шотами
        shots_path_layout = QHBoxLayout()
        shots_path_layout.addWidget(QLabel("Shots folder:"))
        shots_path_layout.addSpacing(10)
        self.shots_input = QLineEdit()
        shots_path_layout.addWidget(self.shots_input)
        self.shots_button = QPushButton("Choose")
        self.shots_button.clicked.connect(self.select_shots_folder)
        self.shots_button.clicked.connect(self.update_result_label)
        shots_path_layout.addWidget(self.shots_button)
        main_layout.addLayout(shots_path_layout)

        # Выбор OTIO
        otio_path_layout = QHBoxLayout()
        otio_path_layout.addWidget(QLabel("Save OTIO file:"))
        self.otio_input = QLineEdit()
        otio_path_layout.addWidget(self.otio_input)
        self.otio_button = QPushButton("Choose")
        self.otio_button.clicked.connect(self.save_otio)
        otio_path_layout.addWidget(self.otio_button)
        main_layout.addLayout(otio_path_layout)

        # Кнопка Check
        self.button_check = QPushButton("PreCheck")
        self.button_check.clicked.connect(self.precheck_shots)
        main_layout.addWidget(self.button_check)

        # Кнопка Start
        self.button_create = QPushButton("Start")
        self.button_create.clicked.connect(self.start)
        main_layout.addWidget(self.button_create)

        # Кнопка Import
        self.button_import = QPushButton("Import OTIO")
        self.button_import.clicked.connect(self.resolve_import_timeline)
        main_layout.addWidget(self.button_import)

        # Статус обрабортки шотов
        result_label_layout = QHBoxLayout()
        result_label_layout.addWidget(self.result_label)
        reset_result_button = QPushButton("Reset")
        reset_result_button.clicked.connect(self.reset_counter)
        result_label_layout.addWidget(reset_result_button)
        result_label_layout.addStretch()
        main_layout.addLayout(result_label_layout)

        # Кнопка Logs
        bottom_layout = QHBoxLayout()
        self.button_logs = QPushButton("Open logs")
        self.button_logs.clicked.connect(self.open_logs)
        bottom_layout.addWidget(self.button_logs)
        bottom_layout.addStretch()
        main_layout.addLayout(bottom_layout)

        self.setLayout(main_layout)

        # Связь сигналов с обновлением UI
        self.no_dublicates.stateChanged.connect(self.update_ui_state)
        self.logic_mode_group.buttonClicked.connect(self.update_ui_state)
        self.include_slate.stateChanged.connect(self.update_ui_state)

        # Вызов для установки начального состояния
        self.update_ui_state()
        self.update_result_label()
        self.project_ui_state()

    def precheck_shots(self):
        """
        Проверяем все ли шоты присутствуют в .edl монтажах.
        """
        shots_root_path = Path(self.shots_input.text().strip())
        edits_path = Path(os.path.dirname(self.edl_input.text().strip()))

        if str(edits_path) == ".":
            self.on_warning_signal("Не указан путь к монтажам")
            return 
        if not os.path.exists(Path(self.edl_input.text().strip())):
            self.on_warning_signal("Указан несуществующий путь к монтажам")
            return
        if str(shots_root_path) == ".":
            self.on_warning_signal("Не указан путь к шотам")
            return 
        if not os.path.exists(shots_root_path):
            self.on_warning_signal("Указан несуществующий путь к шотам")
            return
        try:
            fps = int(self.frame_rate.text())
        except:
            self.on_warning_signal("Значение дожно быть целым числом")
            return
        
        extension = self.format_menu.currentText()

        self.button_check.setEnabled(False)
        self.is_missing_shot(fps, shots_root_path, edits_path, extension)
        self.button_check.setEnabled(True)

    def get_project_settings(self):
        """
        Получаем проектный конфиг
        """
        project_name = self.project_menu.currentText()
        load_config(project_name)
        self.config = get_config()

    def update_ui_state(self):
        """
        Блокировка и активация полей ui.
        """
        track_inputs_enabled = self.no_dublicates.isChecked()
        self.track_in_input.setEnabled(track_inputs_enabled)
        self.track_out_input.setEnabled(track_inputs_enabled)

        selected_button = self.logic_mode_group.checkedButton()
        selected_mode = selected_button.property("mode") if selected_button else None

        start_frame_enabled = selected_mode in ("from_start_frame", "full_logic")
        self.start_frame.setEnabled(start_frame_enabled)

        self.include_slate.setEnabled(self.format_menu.currentText() in ("MOV", "MP4"))

    def project_ui_state(self):
        """
        Блокирует все инпуты, если не выбран проект.
        """
        if self.project_menu.currentText() == "Select Project":
            self.otio_input.setEnabled(False)
            self.edl_input.setEnabled(False)
            self.shots_input.setEnabled(False)
            self.edl_button.setEnabled(False)
            self.shots_button.setEnabled(False)
            self.otio_button.setEnabled(False)
            self.button_logs.setEnabled(False)
        else:
            self.otio_input.setEnabled(True)
            self.edl_input.setEnabled(True)
            self.shots_input.setEnabled(True)
            self.edl_button.setEnabled(True)
            self.shots_button.setEnabled(True)
            self.otio_button.setEnabled(True)
            self.button_logs.setEnabled(True)

    def is_OS(self, path):
        '''
        Метод конвертирует путь под платформу.

        :return result_path: Конвертированный под платформу путь.
        '''
        platform = {"win32": self.config["paths"]["init_project_root_win"], 
                    "darwin": self.config["paths"]["init_project_root_mac"]}[sys.platform]
        result_path = Path(platform) / path
        return result_path

    def get_project(self):
        """
        Метод получает список проектов.
        """
        base_path = {"win32": GLOBAL_CONFIG["paths"]["root_projects_win"], 
                    "darwin": GLOBAL_CONFIG["paths"]["root_projects_mac"]}[sys.platform]
        project_list = sorted([i for i in os.listdir(Path(base_path)) if os.path.isdir(Path(base_path) / i)])
        project_list.insert(0, "Select Project")
        return project_list

    def select_edl(self):
        init_dir = str(self.is_OS(f'{self.config["paths"]["project_path"]}/{self.project_menu.currentText()}/'))
        path, _ = QFileDialog.getOpenFileName(self, 
                                              "Choose EDL file", 
                                              init_dir, 
                                              "EDL files (*.edl)")
        if path:
            self.edl_input.setText(path)

    def select_shots_folder(self):
        init_dir = {"win32": self.config["paths"]["init_shots_root_win"], 
                    "darwin": self.config["paths"]["init_shots_root_mac"]}[sys.platform]
        path = QFileDialog.getExistingDirectory(self, 
                                                "Choose Shots Folder",
                                                init_dir)
        if path:
            self.shots_input.setText(path)

    def save_otio(self):

        init_dir = str(self.is_OS(f'{self.config["paths"]["project_path"]}/{self.project_menu.currentText()}/'))
        path, _ = QFileDialog.getSaveFileName(self, 
                                              "Save OTIO file", 
                                              init_dir, 
                                              "OTIO files (*.otio)")
        if path:
            self.otio_input.setText(path)

    def start(self):
        """
        Запуск основной логики.
        """
        self.validator = ConfigValidator(self)
        self.user_config = self.validator.collect_config()

        self.warning_signal.emit(f"\nМонтаж: {Path(os.path.basename(self.edl_input.text())).stem}\n")

        if self.no_dublicates.isChecked():
            self.resolve_shots_list = get_resolve_shot_list(
                int(self.user_config["track_in"]),
                int(self.user_config["track_out"]),
                self.user_config["extension"]
            )
        else:
            self.resolve_shots_list = None

        if not self.validator.validate(self.user_config):
            self.on_error_signal("\n".join(self.validator.get_errors()))
            return
        
        logger.info(f"\n\nSetUp:\n{pformat(self.user_config)}\n")

        self.main_process = OTIOWorker(self,self.user_config, self.resolve_shots_list)
        self.button_create.setEnabled(False)
        self.main_process.finished.connect(lambda : self.button_create.setEnabled(True))
        self.main_process.error_signal.connect(self.on_error_signal)
        self.main_process.success_signal.connect(self.on_success_signal)
        self.main_process.warning_signal.connect(self.on_warning_signal)
        self.main_process.info_signal.connect(self.on_info_signal)
        self.main_process.warnings.connect(self.appent_warning_field)
        self.main_process.start()

    def appent_warning_field(self, message):
        """
        Добавляет уведомления и ошибки в warning_field через сигналы.
        """
        if self.warning_field.toPlainText().strip().startswith("Здесь будут показаны предупреждения программы."):
            self.warning_field.clear()
        self.warning_field.append(message)

    def on_error_signal(self, message):
        QMessageBox.critical(self, "Error", message)
        logger.exception(message)
        return

    def on_success_signal(self, message):
        QMessageBox.information(self, "Success", message)
        logger.info(message)
        self.update_result_label()

    def on_warning_signal(self, message):
        QMessageBox.warning(self, "Warning", message)
        logger.warning(message)

    def on_info_signal(self, message):
        QMessageBox.information(self, "Info", message)
        logger.info(message)

    def open_logs(self):
        """
        Метод открывает лог-файл.
        """
        log_file_path = self.is_OS(self.config["paths"]["log_path"])

        try:
            if sys.platform == 'win32': 
                os.startfile(log_file_path)
            else: 
                subprocess.Popen(['open', log_file_path])
        except Exception as e:
            self.on_error_signal(self, "Error", f"Ошибка при открытии файла логов: {e}")

    def reset_counter(self):
        """
        Обнуляем данные из обработанных таймлайнов и окно предупреждений
        """
        self.update_result_label(forse_reset=True)
        self.warning_field.clear()

    def update_result_label(self, forse_reset=False):
        """
        Метод обновляет данные результата сборки в self.result_label.
        """
        otio_path = self.otio_input.text().strip()
        shots_path = self.shots_input.text().strip()
        extension = self.format_menu.currentText()
        if forse_reset:
            self.otio_counter = 0
        else:
            self.otio_counter += self.count_otio_clips(otio_path) # self.otio_counter: Количетсво шотов на таймлайне OTIO
        self.in_folder_counter = self.count_clips_on_storage(shots_path, extension) # self.folder_counter: Общее количество шотов в целевой папке shots_path

        self.result_label.setText(f'Processed  {self.otio_counter}  from  {self.in_folder_counter}  shots')


if __name__ == "__main__":
    app = QApplication(sys.argv)
    apply_style(app)
    window = Autoconform()
    window.show()
    sys.exit(app.exec_())