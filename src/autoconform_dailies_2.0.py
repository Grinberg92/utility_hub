from PyQt5.QtWidgets import (
    QApplication, QWidget, QLabel, QPushButton, QVBoxLayout, QHBoxLayout,
    QLineEdit, QTextEdit, QComboBox, QScrollBar, QFileDialog, QCheckBox, QFrame, QSizePolicy, QMessageBox,
    QGroupBox, QRadioButton, QButtonGroup
)
from PyQt5.QtCore import Qt, QThread, pyqtSignal
import os
import sys
import re
import subprocess
from pathlib import Path
from timecode import Timecode as tc
import OpenEXR
from dataclasses import dataclass
import opentimelineio as otio
import DaVinciResolveScript as dvr
from collections import Counter
from pymediainfo import MediaInfo
from dvr_tools.logger_config import get_logger
from dvr_tools.resolve_timeline_shots_names import get_resolve_shot_list
from dvr_tools.css_style import apply_style


logger = get_logger(__file__)


class Constant:
    frame_pattern = r'(\d+)(?:\.|_)\w+$' # Паттерн на номера секвении [1001-...]
    main_shot_pattern = r'(\.|_)\d+\.\w+$'
    project_path = r"003_transcode_to_vfx/projects/"
    log_path = r"003_transcode_to_vfx/projects/log_file.log"
    

@dataclass
class EDLEntry:
    """
    Класс-контейнер для данных из строки EDL
    """
    edl_record_id: str
    edl_shot_name: str
    edl_track_type: str
    edl_transition: str
    edl_source_in: str
    edl_source_out: str
    edl_record_in: str
    edl_record_out: str 

class EDLParser:
    """
    Класс-итератор.
    Итерируется по EDL файлу
    """
    def __init__(self, edl_path):
        self.edl_path = edl_path
    def __iter__(self):

        with open(self.edl_path, 'r') as edl_file:
            lines = edl_file.readlines()

            for line in lines:
                if re.search(r'^\d+\s', line.strip()):
                    yield self.parse_line(line)  # Паттерн ищет значения 001, 0001 и т.д. по началу строки

    def parse_line(self, line):
        """
        Метод парсит строку на значения через класс EDLEntry
        """
        parts = line.split()
        return EDLEntry(
                    edl_record_id= parts[0],
                    edl_record_in= parts[6],
                    edl_record_out= parts[7],
                    edl_track_type= parts[2],
                    edl_transition= parts[3],
                    edl_shot_name= parts[1],
                    edl_source_out= parts[5],
                    edl_source_in= parts[4] )

class OTIOCreator:
    """
    Класс создания OTIO таймлайна
    """
    def __init__(self, user_config, resolve_shot_list):
        self.user_config = user_config
        self.resolve_shot_list = resolve_shot_list
        self.send_warning = lambda msg: None

        self.frame_pattern = r'(\d+)(?:\.|_)\w+$' # Паттерн на номера секвении [1001-...]
        self.main_shot_pattern = r'(\.|_)\d+\.\w+$'

    def get_shots_sequence_list(self, path):
        """
        Получем список путей к подпапкам секвенций EXR, JPG (они же имена шотов)
        :param path: Входящий путь из GUI 
        """
        return  [os.path.join(root, folder) for root, folders, _ in os.walk(path) for folder in folders]
    
    def get_shots_movie_list(self, path):
        """
        Получем список путей к видеофайлам MOV, MP4
        :param path: Входящий путь из GUI 
        """
        return [os.path.join(root, file) for root, _, files in os.walk(path) for file in files]
    
    def is_drop_frames(self, exr_files, target_folder):
        """
        Проверяет шот(секвенцию) на предмет битых кадров.
        Работает только с секвенциями.

        :return: Уведомление в GUI
        """
        # Проверяем файлы на наличие веса ниже 10% от максимального
        max_file_size = 0
        size_threshold = 0
        percent = 0.1
        for file in exr_files:
            file_path = os.path.join(target_folder, file)
            file_size = os.path.getsize(file_path)

            # Обновляем максимальный размер файла и порог
            if file_size > max_file_size:
                max_file_size = file_size
                size_threshold = max_file_size * percent

            # Проверяем текущий файл
            if file_size < size_threshold:
                warning_messege = f"Маленький размер файла в секвенции. Вес: {file_size} байт."
                self.send_warning(warning_messege)
                logger.warning(f"\n{warning_messege}")
                break

    def is_duplicate(self, shot_name, resolve_timeline_objects)-> bool:
        '''
        Находит шоты, версии которых уже стоят на таймлайне и пропускает их.
        '''
        try:
            if shot_name in resolve_timeline_objects:
                return True
            return False
        except:
            return False
        
    def get_gap_value(self, edl_record_in, timeline_in_tc, edl_start_timecodes, track_index):
        """
        Метод определения продолжительности для первого GAP объекта и для всех остальных GAP объектов.

        :param timeline_in_tc: Таймкод начала таймлайна
        """
        gap_dur = 0
        if edl_start_timecodes[track_index] is None:
            # Для первого клипа на любом из треков используем разность стартового таймкода клипа из EDL и начала таймлайна
            gap_dur = self.timecode_to_frame(edl_record_in) - timeline_in_tc  
        else:
            gap_dur = self.timecode_to_frame(edl_record_in) - self.timecode_to_frame(edl_start_timecodes[track_index])
        return gap_dur
    
    def is_miss_frames(self, shot_name, frames_list)-> bool: 
        """
        Функция проверяет есть ли битые кадры в секвенции.
        Работает только с секвенциями.
        """
        frames_numbers_list = [int(re.search(self.frame_pattern, i).group(0).split(".")[0]) for i in frames_list]  
        if not all(frames_numbers_list[i] + 1 == frames_numbers_list[i + 1] 
                   for i in range(len(frames_numbers_list) - 1)):
            message = f"Секвенция {shot_name} имеет пропущенные фреймы. Необходимо добавить шот вручную."
            self.send_warning(message)
            logger.warning(message)
            return False
        return True
    
    def timecode_to_frame(self, timecode)-> int:
        """
        Метод получает таймкод во фреймах
        """
        return tc(self.frame_rate, timecode).frames
    
    def frame_to_timecode(self, frames):
        """
        Метод получает таймкод из значений фреймов
        """
        return tc(self.frame_rate, frames=frames)
    
    def get_fixed_frame_handles(self, src_duration, timeline_duration, start_frame)-> int:
        """Функция определяет есть ли захлесты у шота.
        Если длина исходника больше длины продолжительности шота на таймлайне и равна 6(3 + 3 захлеста), 8 и 10,
        то прибавляем к стартовому фрейму захлест.

        :param edl_src_start_frame: None по дефолту на случай если пересечения таймкодов нет
        """  
        shot_start_frame = None
        if src_duration - timeline_duration == 6:
            shot_start_frame = float(start_frame + 3)
        elif src_duration - timeline_duration == 8:
            shot_start_frame = float(start_frame + 4)
        elif src_duration - timeline_duration == 10:
            shot_start_frame = float(start_frame + 5)
        return shot_start_frame
    
    def get_frame_handles_from_edl_in(self, edl_source_in, edl_source_out, source_in, source_out)-> int:
        """Функция определяет вхождение сорс диапазона шота в таймлайн диапазон из EDL.
        Если условие удовлетворяется - получаем стартовый таймкод из EDL и передаем в create_otio_timeline_object
        для выставления этого значения в качестве начального таймкода клипа.

        :param edl_src_start_frame: None по дефолту на случай если пересечения таймкодов нет
        """  

        edl_src_start_frame = None
        edl_src_start_tc_in_frames = self.timecode_to_frame(edl_source_in)
        edl_src_end_tc_in_frames = self.timecode_to_frame(edl_source_out)
        if edl_src_start_tc_in_frames >= source_in and edl_src_end_tc_in_frames <= source_out:  
            edl_src_start_frame = float(edl_src_start_tc_in_frames - 1)

        return edl_src_start_frame
    
    def get_filtred_shots_list_by_mask(self, shot_name):
            """
            Метод обходит папку с секвенциями или видеофайлами и отбирает только те, 
            которые пересекаются с именем шота из EDL

            :param shot_name: Имя шота из EDL

            :return: Список путей с фильтрованными по имени шота фолдерами(секвенциями) или видеофайлами.
            Если присутствует несколько версий шота, в аутпут списке будут несколько версий
            """
            target_list = []

            for folder_path in self.shots_paths:
                folder_name = os.path.basename(folder_path)
                if self.not_movie_bool:
                    if re.search(shot_name.lower(), folder_name): 
                        target_list.append(folder_path)
                else:
                    if folder_name.endswith(".mov") and re.search(shot_name.lower(), folder_name): 
                        target_list.append(folder_path)

            return target_list

    def split_name(self, clip_name)-> tuple:
        """
        Метод разбивает полное имя секвенции кадров на префикс, суффикс и стартовый фрэйм
        Обрабатывает только такие имена: 015_3030_comp_v002.1004.exr и 015_3030_comp_v002_1004.exr
        """

        match = re.search(fr'(.+?)([\._])\[(\d+)-\d+\]\.{self.clip_extension.lower()}$', clip_name)
        if not match:
            raise ValueError(f"Невозможно разобрать имя секвенции: {clip_name}")
        pref = match.group(1) + match.group(2)
        suff = f".{self.clip_extension.lower()}"
        start = match.group(3)

        return (pref, suff, start)

    def create_otio_gap_object(self, gap_duration, track_index):
        """
        Метод создает объект GAP в OTIO конструкторе
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

            logger.info(f'GAP duration: {gap_duration}')

    def create_otio_timeline_object_movie(self, shot_data, shot_start_frame, track_index):
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

            debug_exr_info = f'Shot name: {clip_name}\nShot start timecode: {clip_start_frame}\nShot duration: {clip_duration}\nShot path: {clip_path}'
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

    def create_otio_timeline_object(self, shot_data, shot_start_frame, track_index):
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

            logger.info(f'Shot name: {clip_name}\nShot start timecode: {clip_start_frame}\nShot duration: {clip_duration}\nShot path: {clip_path}\nParse name: {pref, suff, start}\n\n\n')

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
        Получение количества объектов на таймлайне
        """
        return sum([len(track) for track in self.video_tracks]) 

    def create_video_tracks(self):
        """
        Создание списка заданного количества объектов видео треков на OTIO таймлайне
        Метод ничего не возвращает
        """
        self.video_tracks = []
        self.track_count = 10
        for num in range(self.track_count):
            self.video_tracks.append(otio.schema.Track(name=f'Video{num+1}', kind=otio.schema.TrackKind.Video))
            self.otio_timeline.tracks.append(self.video_tracks[num])
    
    def is_correct_lenght(self, source_duration, timeline_duration, shot_name):
        """
        Функция сравнивает фактическую длину шота по данным из сорса и из таймлайн диапазона.
        Метод ничего не возвращает.
        """
        if source_duration < timeline_duration:
            result = timeline_duration - source_duration
            warning_message = f"Предупреждение. Шот {shot_name} короче, чем его длина в EDL."
            self.send_warning(warning_message)
            logger.warning(f'\n{warning_message}')

    def is_correct_fps(self, shot)->bool:
        """
        Сравнивает проектный fps и fps шота
        """
        try:
            frame = OpenEXR.InputFile(shot.first_frame_path)
            header = frame.header()
            frame_fps = header.get('nuke/input/frame_rate')

            if frame_fps is not None:
                # Иногда информация о фрейм рейте хранится в байтовом представлении. Учитываем это.
                frame_fps = float(frame_fps.decode()) if isinstance(frame_fps, bytes) else float(frame_fps)
                if int(self.frame_rate) != int(frame_fps):
                    warning_message = f"FPS шота {shot.name} расходится с проектным. FPS - {round(frame_fps, 2)}"
                    self.send_warning(warning_message)
                    logger.warning(warning_message)
                    return False
                return True
            return True
                
        except Exception as e:
            message = f"Ошибка при обработке значения FPS {shot.first_frame_path}: {e}"
            logger.exception(message)
            return True
        
    def validate_shot(self, shot)-> bool:
        """
        Метод-агрегатор валидаторов шота
        """
        if self.ignore_dublicates_bool:
            if self.is_duplicate(shot.name, self.resolve_shot_list):
                return False

        if not self.is_miss_frames(shot.name, shot.frames_list):
            return False
        if not self.is_correct_fps(shot):
            return False

        self.is_drop_frames(shot.frames_list, shot.path)

        return True


    def get_shot(self, edl_shot_name, shot_path=None):
        """
        Ищет шот в self.user_config["shots_folder"] и собирает данные о шоте
        Проверяет секвенцию на ошибки. Если в текущей версии шота есть ошибки - шот пропускается

        :return shots_versions: Список с версиями валидных шотов
        """
        try:
            filtred_shot_paths = self.get_filtred_shots_list_by_mask(edl_shot_name)
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
            self.send_warning(f'Ошибка при обработке шота {edl_shot_name}. Необходимо добавить его вручную в Media Pool.')
            return []

    def run(self):
        """
        Основной метод логики
        """
        self.edl_path = self.user_config["edl_path"]
        self.frame_rate = self.user_config["frame_rate"]
        self.ignore_dublicates_bool = self.user_config["ignore_dublicates"]
        self.clip_extension = self.user_config["extension"]
        self.handles_logic = self.user_config["handles_logic"]
        self.not_movie_bool = self.clip_extension not in ("mov", "mp4")
        if self.not_movie_bool: 
            self.shots_paths = self.get_shots_sequence_list(self.user_config["shots_folder"])
        else:
            self.shots_paths = self.get_shots_movie_list(self.user_config["shots_folder"]) 

        edl_data = EDLParser(self.edl_path)

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

                    # Вычисление таймлайн дюрэйшн
                    timeline_duration = self.timecode_to_frame(edl_record_out) - self.timecode_to_frame(edl_record_in)

                    # Нахождение страртового кадра для создания OTIO клипа и выставления захлеста
                    if self.handles_logic == "fixed":
                        shot_start_frame = self.get_fixed_frame_handles(source_duration, timeline_duration, source_in_tc)
                    elif self.handles_logic == "from_edl":
                        shot_start_frame = self.get_frame_handles_from_edl_in(edl_source_in, 
                                                                                   edl_source_out, source_in_tc, source_out_tc)
                    # Вычисление GAP для клипов
                    gap_duration = self.get_gap_value(edl_record_in, timeline_in_tc, edl_start_timecodes, track_index)

                    logger.info(f"Source start tc: {source_in_tc}\nSource end tc: {source_out_tc}")
                    logger.info(f'\nTimeline start timecode: {edl_record_in}\nTimeline end timecode: {edl_record_out}')
                    logger.info(f'\nEDL source start timecode: {edl_source_in}\nEDL source end timecode: {edl_source_out}\nTimeline duration: {timeline_duration}')

                    self.create_otio_gap_object(gap_duration, track_index)

                    self.is_correct_lenght(source_duration, timeline_duration, shot.name)

                    shot_data = {
                        'exr_path': shot.path,
                        'shot_name': shot.name,
                        'gap_duration': gap_duration,
                        'source_in_tc': source_in_tc,
                        'source duration': source_duration,
                        'timeline_duration': timeline_duration,
                        'track_index': track_index
                                            }
                    if self.not_movie_bool:
                        self.create_otio_timeline_object(shot_data, shot_start_frame, track_index)
                    else:
                        self.create_otio_timeline_object_movie(shot_data, shot_start_frame, track_index)

                    edl_start_timecodes[track_index] = edl_record_out

            timeline_objects = self.count_timeline_objects()
            return self.otio_timeline, timeline_objects

        except Exception as e:
            logger.exception(f"Сбой в работе программы. Не удалось сформировать OTIO файл: {e}") 

class MovieObject:
    """
    Класс-объект видеофайла .mov или .mp4
    """
    def __init__(self, path, frame_pattern=None):
        self.path = path
        self.frame_pattern = Constant.frame_pattern

    @property
    def name(self)-> str:
        """
        Получение имени клипа
        """
        return os.path.basename(self.path)
    
    def get_duration(self, frame_rate:int)-> int:
        """
        Получение длительности видеофайла
        """
        try:
            media_info = MediaInfo.parse(self.path)

            for track in media_info.tracks:
                if track.track_type == "Video":
                    duration_seconds = track.duration / 1000  # переводим из миллисекунд в секунды
                    duration_frames = duration_seconds * frame_rate  # умножаем на частоту кадров
                    # Переводим в целое количество кадров
                    duration = int(duration_frames) - 1 #-1 для корректного восприятия в Davinci Resolve
                    return duration
                
        except Exception as e:
            print(f"Ошибка при получении длительности видео: {e}")
            return None
        
    def extract_timecode(self, frame_rate)-> tuple:
        """
        Получение стартового таймкода, конечного таймкода и длительности видеофайла
        """
        try:
            media_info = MediaInfo.parse(self.path)
            # Получаем длительность и начальный таймкод видео
            for track in media_info.tracks:
                if track.track_type == "Video":
                    # Длительность видео в секундах
                    duration_seconds = track.duration / 1000  # переводим из миллисекунд в секунды
                    duration_frames = duration_seconds * frame_rate  # умножаем на частоту кадров
                    duration = int(duration_frames) - 1 # -1 для корректного восприятия в Davinci Resolve

                    # Извлекаем начальный таймкод
                    if track.other_delay:
                        start_timecode = tc(frame_rate, track.other_delay[4]).frames - 1 # -1 для корректного восприятия в Davinci Resolve
                        start_timecode += 1 # +1 - отрезаем первый кадр слейта

                    end_timecode = start_timecode + duration
                    return (start_timecode, end_timecode, duration)
            
        except Exception as e:
            print(f"Ошибка при получении длительности видео: {e}")
            return (None, None, None)

class SequenceFrames:
    """
    Класс-объект секвенции EXR или JPG
    """
    def __init__(self, path_to_sequence, extension, frame_pattern=None):
        self.path = path_to_sequence
        self.extension = extension
        self.frame_pattern = Constant.frame_pattern

    def __repr__(self):
        return F"Sequence'{self.name}'"
    
    def __str__(self):
        return f"{self.name}"
    
    def __getitem__(self, index):
        if not isinstance(index, int):
            raise ValueError("Некорректное значение индекса")
        return self.frames_list[index]

    @property
    def frames_list(self):
        """
        Получаем список кадров секвенции отсортированных по возрастанию
        """
        return sorted([f for f in os.listdir(self.path) if f.lower().endswith(f'.{self.extension.lower()}')])
    
    @property
    def first_frame_path(self):
        """
        Определяем путь к первому кадру секвенции
        """
        return os.path.join(self.path, self.frames_list[0])
    
    @property
    def last_frame_path(self)->str:
        """
        Определяем путь к последнему кадру секвенции
        """
        return os.path.join(self.path, self.frames_list[-1])
    
    @property
    def first_frame_number(self)->str:
        """
        Извлекаем номер кадра из имени первого кадра секвенции
        """
        match = re.search(self.frame_pattern, self.first_frame_path)
        if not match:
            raise ValueError(f"Невозможно извлечь номер кадра из кадра {self.first_frame_path}.")
        return match.group(1)
    
    @property
    def last_frame_number(self)->str:
        """
        Извлекаем номер кадра из имени последнего кадра секвенции
        """
        match = re.search(self.frame_pattern, self.last_frame_path)
        if not match:
            raise ValueError(f"Невозможно извлечь номер кадра из кадра {self.last_frame_number}.")
        return match.group(1)
    
    @property
    def name(self)->str:
        """
        Получаем имя секвенции
        Обрабатывает стандартный формат имени 015_3030_comp_v002.1004.exr
        и частый ошибочный формат имени 015_3030_comp_v002_1004.exr
        """
        base_name = re.sub(r'(\.|_)\d+\.\w+$', '', os.path.basename(self.first_frame_path))
        if '.' in os.path.splitext(self.first_frame_path)[0]:
            sequence_name = f"{base_name}.[{self.first_frame_number}-{self.last_frame_number}].{self.extension.lower()}"
        else:
            sequense_name = f"{base_name}_[{self.first_frame_number}-{self.last_frame_number}].{self.extension.lower()}"
        return sequence_name
    
    @staticmethod
    def format_timecode(timecode_str:str)->str:
        """
        Форматирует таймкод в двухзначный формат для всех его компонентов (HH:MM:SS:FF).
        """
        formatted_parts = ':'.join([part.zfill(2) for part in timecode_str.split(':')])  # Каждый элемент приводит к двухзначному формату
        return formatted_parts

    def extract_timecode(self, project_fps:int)->tuple:
        """
        Извлекает таймкод из кадра секвенции и форматирует его.
        Настроен на композы из Nuke
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
                start_timecode = float(tc(project_fps, "00:00:00:00").frames - 1)  # -1 что бы корректно воспринимал Resolve
                end_timecode = start_timecode + (len(self.frames_list))
                duration = (end_timecode - start_timecode) 
            else:
                start_timecode = float(tc(project_fps, start_timecode).frames - 1) # -1 что бы корректно воспринимал Resolve
                end_timecode = start_timecode + (len(self.frames_list))
                duration = (end_timecode - start_timecode) 
                          
            return (start_timecode, end_timecode, duration)

        except Exception as e:
            message = f"Ошибка при обработке таймкода {self.first_frame_path}: {e}"
            logger.exception(message)
            return (None, None, None)

class OTIOWorker(QThread):
    """
    Класс работы с логикой в отдельном потоке
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
    Методы примеси для класса Autoconform
    """
    def count_otio_clips(self, otio_path)-> int:
        """
        Читает OTIO и получает количество видео-объектов(шотов) на таймлайне(не учитывая версии шотов)
        """
        try:
            timeline = otio.adapters.read_from_file(otio_path)
            total_clips = 0 
            # Проходим по всем дорожкам
            for _, track in enumerate(timeline.tracks):
                clip_count = sum(1 for item in track if isinstance(item, otio.schema.Clip))
                total_clips += clip_count  # Добавляем к общему количеству

            return total_clips

        except Exception as e:
            logger.warning(f"Ошибка при чтении OTIO: {e}")
            return 0

    def count_clips_on_storage(self, shots_folder, extension)-> int:
        """
        Сканирует папку на хранилище с шотами (секвенциями или видеофайлами), 
        участвующими в сборке OTIO, и получает их количество
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

class ConfigValidator:
    """
    Класс собирает и валидирует пользовательские данные
    """
    def __init__(self, gui):
        self.gui = gui
        self.errors = []

    def collect_config(self) -> dict:
        """
        Собирает пользовательские данные из GUI
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
            "frame_rate": self.gui.frame_rate,
            "handles_logic": handles_logic
        }

    def validate(self, user_config: dict) -> bool:
        """
        Валидирует конфиг
        """
        self.errors.clear()

        if not user_config["edl_path"]:
            self.errors.append("Укажите путь к файлу EDL")
        if not user_config["shots_folder"]:
            self.errors.append("Укажите путь к папке с шотами")
        if not user_config["otio_path"]:
            self.errors.append("Укажите путь к папке для сохранения OTIO")

        try:
            int(user_config["track_in"])
            int(user_config["track_out"])
        except ValueError:
            self.errors.append("Значения должны быть целыми числами")
        return not self.errors

    def get_errors(self) -> list:
        return self.errors
        


class Autoconform(QWidget, ConformCheckerMixin):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Autoconform Dailies")
        self.resize(640, 720)
        self.setWindowFlag(Qt.WindowStaysOnTopHint)

        self.frame_rate = 24
        self.edl_path = ""
        self.shots_folder = ""
        self.otio_path = ""

        self.selected_track_in = "8"
        self.selected_track_out = "8"
        self.selected_format = "EXR"

        self.otio_counter = 0
        self.folder_counter = 0

        self.projects = self.get_project()
        self.selected_project = self.projects[0] if self.projects else ""

        self.logic_mode_fixed = QRadioButton()
        self.logic_mode_fixed.setChecked(True) 
        self.logic_mode_fixed.setProperty("mode", "fixed")

        self.logic_mode_from_edl_in = QRadioButton()
        self.logic_mode_from_edl_in.setProperty("mode", "from_edl")

        self.init_ui()

    def init_ui(self):
        main_layout = QVBoxLayout()

        # Поле предупреждений
        self.warning_field = QTextEdit()
        self.warning_field.setReadOnly(True)
        self.warning_field.setPlainText("Здесь будут показаны предупреждения программы.\n")
        main_layout.addWidget(self.warning_field)

        # Логика
        logic_group = QGroupBox("Handles logic")
        logic_group.setFixedHeight(70)
        logic_group.setFixedWidth(300)
        logic_layout = QHBoxLayout()

        self.logic_mode_group = QButtonGroup(self)
        self.logic_mode_group.addButton(self.logic_mode_fixed)
        self.logic_mode_group.addButton(self.logic_mode_from_edl_in)

        vbox1 = QVBoxLayout()
        fixed_label = QLabel("Fixed")
        fixed_label.setAlignment(Qt.AlignHCenter)
        vbox1.addWidget(self.logic_mode_fixed, alignment=Qt.AlignHCenter)
        vbox1.addWidget(fixed_label)

        vbox2 = QVBoxLayout()
        edl_in_label = QLabel("From EDL in")
        edl_in_label.setAlignment(Qt.AlignHCenter)
        vbox2.addWidget(self.logic_mode_from_edl_in, alignment=Qt.AlignHCenter)
        vbox2.addWidget(edl_in_label)

        logic_layout.addStretch()
        logic_layout.addLayout(vbox1)
        logic_layout.addSpacing(60)
        logic_layout.addLayout(vbox2)
        logic_layout.addStretch()

        logic_group.setLayout(logic_layout)
        main_layout.addWidget(logic_group, alignment=Qt.AlignHCenter)

        # 
        settings_group = QGroupBox("Settings")
        settings_layout = QVBoxLayout()

        # --- Project + Extension (горизонтальный слой с двумя вертикальными)
        top_row_layout = QHBoxLayout()

        # Левая вертикаль: проект
        project_vbox = QVBoxLayout()
        project_label = QLabel("Choose project:")
        self.project_menu = QComboBox()
        self.project_menu.addItems(self.projects)
        self.project_menu.setCurrentText(self.selected_project)
        project_vbox.addWidget(project_label)
        project_vbox.addWidget(self.project_menu)

        # Правая вертикаль: расширение
        format_vbox = QVBoxLayout()
        format_label = QLabel("Extension:")
        self.format_menu = QComboBox()
        self.format_menu.addItems(["EXR", "JPG", "MOV", "MP4"])
        self.format_menu.setCurrentText(self.selected_format)
        format_vbox.addWidget(format_label)
        format_vbox.addWidget(self.format_menu)

        # Объединяем в горизонтальный слой
        top_row_layout.addLayout(project_vbox)
        top_row_layout.addSpacing(40)
        top_row_layout.addLayout(format_vbox)

        # --- Нижняя строка: чекбокс и диапазон треков
        bottom_row_layout = QHBoxLayout()
        self.no_dublicates = QCheckBox("Ignore dublicates")
        bottom_row_layout.addWidget(self.no_dublicates)
        bottom_row_layout.addSpacing(30)

        bottom_row_layout.addWidget(QLabel("tracks range:"))

        self.track_in_input = QLineEdit(self.selected_track_in)
        self.track_in_input.setFixedWidth(30)
        bottom_row_layout.addWidget(self.track_in_input)

        bottom_row_layout.addWidget(QLabel("-"))

        self.track_out_input = QLineEdit(self.selected_track_out)
        self.track_out_input.setFixedWidth(30)
        bottom_row_layout.addWidget(self.track_out_input)
        bottom_row_layout.addStretch()

        # Финальная сборка
        settings_layout.addLayout(top_row_layout)
        settings_layout.addSpacing(10)
        settings_layout.addLayout(bottom_row_layout)
        settings_group.setLayout(settings_layout)

        main_layout.addWidget(settings_group)


        # Выбор EDL
        edl_path_layout = QHBoxLayout()
        edl_path_layout.addWidget(QLabel("EDL file:"))
        edl_path_layout.addSpacing(32)
        self.edl_input = QLineEdit()
        edl_path_layout.addWidget(self.edl_input)
        edl_button = QPushButton("Choose")
        edl_button.clicked.connect(self.select_edl)
        edl_path_layout.addWidget(edl_button)
        main_layout.addLayout(edl_path_layout)

        # Shots folder
        shots_path_layout = QHBoxLayout()
        shots_path_layout.addWidget(QLabel("Shots folder:"))
        shots_path_layout.addSpacing(10)
        self.shots_input = QLineEdit()
        shots_path_layout.addWidget(self.shots_input)
        shots_button = QPushButton("Choose")
        shots_button.clicked.connect(self.select_shots_folder)
        shots_path_layout.addWidget(shots_button)
        main_layout.addLayout(shots_path_layout)

        # OTIO
        otio_path_layout = QHBoxLayout()
        otio_path_layout.addWidget(QLabel("Save OTIO file:"))
        self.otio_input = QLineEdit()
        otio_path_layout.addWidget(self.otio_input)
        otio_button = QPushButton("Choose")
        otio_button.clicked.connect(self.save_otio)
        otio_path_layout.addWidget(otio_button)
        main_layout.addLayout(otio_path_layout)

        # Кнопка Start
        self.button_create = QPushButton("Start")
        self.button_create.clicked.connect(self.start)
        main_layout.addWidget(self.button_create)

        self.result_label = QLabel("Processed 0 from 0 shots")
        main_layout.addWidget(self.result_label)

        # Кнопка Logs
        bottom_layout = QHBoxLayout()
        self.button_logs = QPushButton("Open logs")
        self.button_logs.clicked.connect(self.open_logs)
        bottom_layout.addWidget(self.button_logs)
        bottom_layout.addStretch()
        main_layout.addLayout(bottom_layout)

        self.setLayout(main_layout)

    def is_OS(self, path):
        '''
        Метод конвертирует путь под платформу

        :return result_path: Конвертированный под платформу путь
        '''
        platform = {"windows": "J:/", 
                    "darwin": "/Volumes/share2/"}[sys.platform]
        result_path = Path(platform) / path
        return result_path

    def get_project(self):
        """
        Метод получает список проектов
        """
        base_path = self.is_OS(Constant.project_path)
        return sorted([i for i in os.listdir(base_path) if os.path.isdir(base_path / i)])

    def select_edl(self):
        init_dir = str(self.is_OS(f'003_transcode_to_vfx/projects/{self.project_menu.currentText()}/'))
        path, _ = QFileDialog.getOpenFileName(self, 
                                              "Choose EDL file", 
                                              init_dir, 
                                              "EDL files (*.edl)")
        if path:
            self.edl_input.setText(path)
            self.edl_path = path

    def select_shots_folder(self):
        init_dir = {"windows": "R:/", 
                    "darwin": "/Volumes/RAID/"}[sys.platform]
        path = QFileDialog.getExistingDirectory(self, 
                                                "Choose Shots Folder",
                                                init_dir)
        if path:
            self.shots_input.setText(path)
            self.shots_folder = path

    def save_otio(self):
        init_dir = str(self.is_OS(f'003_transcode_to_vfx/projects/{self.project_menu.currentText()}/'))
        path, _ = QFileDialog.getSaveFileName(self, 
                                              "Save OTIO file", 
                                              init_dir, 
                                              "OTIO files (*.otio)")
        if path:
            self.otio_input.setText(path)
            self.otio_path = path

    def start(self):
        """
        Запуск основной логики
        """
        self.validator = ConfigValidator(self)
        self.user_config = self.validator.collect_config()
        self.resolve_shots_list = get_resolve_shot_list(
            int(self.user_config["track_in"]),
            int(self.user_config["track_out"]),
            self.user_config["extension"]
        )

        if not self.validator.validate(self.user_config):
            QMessageBox.critical(self, "Validation error", "\n".join(self.validator.get_errors()))
            return
        
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
        Добавляет уведомления и ошибки в warning_field через сигналы
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
        Метод открывает лог-файл
        """
        log_file_path = self.is_OS(Constant.log_path)

        try:
            if sys.platform == 'Windows': 
                os.startfile(log_file_path)
            else: 
                subprocess.Popen(['open', log_file_path])
        except Exception as e:
            QMessageBox.warning(self, "Error", f"Ошибка при открытии файла логов: {e}")

    def update_result_label(self):
        """
        Метод создает и обновляет данные результата сборки
        """
        otio_path = self.otio_input.text().strip()
        shots_path = self.shots_input.text().strip()
        extension = self.format_menu.currentText()

        self.otio_counter += self.count_otio_clips(otio_path) # self.otio_counter: Количетсво шотов на таймлайне OTIO
        self.in_folder_counter = self.count_clips_on_storage(shots_path, extension) # self.folder_counter: Общее количество шотов в целевой папке shots_path

        self.result_label.setText(f'Обработано {self.otio_counter} из {self.in_folder_counter} шотов')


if __name__ == "__main__":
    app = QApplication(sys.argv)
    apply_style(app)
    window = Autoconform()
    window.show()
    sys.exit(app.exec_())