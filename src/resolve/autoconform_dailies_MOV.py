import tkinter as tk
from tkinter import filedialog, messagebox
import ffmpeg._probe
import opentimelineio as otio
from timecode import Timecode as tc
import re
import os
import platform
import OpenEXR
from threading import Thread
import logging
import time
import subprocess
from pathlib import Path
from collections import Counter
import DaVinciResolveScript as dvr
import OpenImageIO as oiio
import ffmpeg
from pymediainfo import MediaInfo


def is_OS(path):
    '''
    Функция составления корректного пути в зависимости от платформы
    '''
    platform = {"nt": "J:/", "posix": "/Volumes/share2/"}[os.name]
    result_path = Path(platform) / path
    return result_path

# Настройка логгера
log_path = r"003_transcode_to_vfx/projects/log_file.log"
logging.basicConfig(
    filename=is_OS(log_path),  # Имя файла для записи логов
    level=logging.DEBUG,    # Уровень логирования: DEBUG, INFO, WARNING, ERROR, CRITICAL
    format="- %(levelname)s - %(message)s"  # Формат записи
)
logger = logging.getLogger(__name__)

# Начало работы программы
logger.debug('-' * 50)  
logger.debug(f'Execution started at: {time.strftime("%Y-%m-%d %H:%M:%S")}')
logger.debug('-' * 50)  

# Глобальные переменные
warnings_dict = {} # Словарь с предупреждениями для отображения в GUI
projects_path = is_OS(r"003_transcode_to_vfx/projects/") # Путь к проектам

def is_crash_exr(mov_file):
    """
    Функция проверки EXR-секвенции на битые кадры.
    Возвращает только уведомление.
    """
    # Проверяем файлы на наличие веса ниже 10% от максимального
    file_size = os.path.getsize(mov_file)
    file_name = os.path.basename(mov_file)
    if file_size == 0:
        warning_messege = f"Предупреждение. Маленький размер файла в секвенции. Вес: {file_size} байт."
        warnings_dict[file_name] = warning_messege
        logger.warning(f"\n{warning_messege}")



def is_lenght(src_duration, timeline_duration, shot_name):
    """
    Функция сравнивает фактическую длину шота по данным из сорса и из таймлайн диапазона.
    Не возвращает объектов или переменных, только предупреждение.
    """
    if src_duration < timeline_duration:
        result = timeline_duration - src_duration
        warning_message = f"Предупреждение. Шот {shot_name.split('.')[0]} короче, чем его длина в EDL. "
        warnings_dict[shot_name.split('.')[0]] = warning_message
        logger.warning(f'\n{warning_message}')  # Логирование 

def is_first_gap(frame_rate, edl_timeline_start_tc, tmln_start_hour, end_tc_tracks, track_ind):
    """
    Функция определения продолжительности для первого GAP объекта и для всех остальных GAP объектов.
    """
    gap_dur = 0
    if end_tc_tracks[track_ind] is None:
        # Для первого клипа на любом из треков используем разность стартового таймкода клипа из EDL и начала таймлайна
        gap_dur = tc(frame_rate, edl_timeline_start_tc).frames - tmln_start_hour  
    else:
        gap_dur = tc(frame_rate, edl_timeline_start_tc).frames - tc(frame_rate, end_tc_tracks[track_ind]).frames
    return gap_dur

def is_edl_start_frame(src_duration, timeline_duration, start_frame):
    """Функция определяет есть ли захлесты у шота.
       Если длина исходника больше длины продолжительности шота на таймлайне и равна 6(3 + 3 захлеста), 8 и 10,
       то прибавляем к стартовому фрейму захлест.
       """  
    # Задаем None по дефолту на случай если искомый захлест не обнаружен
    otio_clip_start_frame = None
    if src_duration - timeline_duration == 6:
        otio_clip_start_frame = float(start_frame + 3)
    elif src_duration - timeline_duration == 8:
        otio_clip_start_frame = float(start_frame + 4)
    elif src_duration - timeline_duration == 10:
        otio_clip_start_frame = float(start_frame + 5)
    return otio_clip_start_frame

def format_timecode(timecode_str):
    """
    Форматирует таймкод в двухзначный формат для всех его компонентов (HH:MM:SS:FF).
    """
    formatted_parts = ':'.join([part.zfill(2) for part in timecode_str.split(':')])  # Каждый элемент приводит к двухзначному формату
    return formatted_parts

def normalize_folder_name(folder_name):
    """
    Нормализует имя папки:
    - Первое число (с буквами или без) → 3 знака (обрезает слева, если больше 3).
    - Второе число → 4 знака.
    - Всё остальное оставляет как есть.
    - Игнорирует префикс (3-4 буквы, например PRK_).

    Обрабатывает имена вида: prk_001_0010, 001_0010, 001a_0010
    """
    folder_name = folder_name.lower()
    
    # Проверяем наличие префикса (3-4 буквы + _ или -)
    prefix_match = re.match(r'^([a-z]{3,4}_)', folder_name)
    prefix = prefix_match.group(1) if prefix_match else ''
    
    # Убираем префикс временно для обработки
    if prefix:
        folder_name = folder_name[len(prefix):]

    parts = folder_name.split('_')
    normalized_parts = []
    
    for i, part in enumerate(parts):
        match = re.match(r'(\d+)([a-z]*)', part)  # Разделяем число и буквы
        if match:
            num, letters = match.groups()
            if i == 0:  # Первое число
                num = num[-3:].zfill(3)  # Оставляем только 3 последних цифры
            elif i == 1:  # Второе число
                num = num.zfill(4)  # 0060 → 0060
            normalized_parts.append(num + letters)  # Объединяем обратно
        else:
            normalized_parts.append(part)  # Оставляем текст без изменений

    return prefix + '_'.join(normalized_parts)

def extract_timecode_from_exr(file_path, frame_rate, exr_name):
    """
    Извлекает таймкод из .exr файла и форматирует его.
    Проверяет FPS шота на соответствие с FPS проекта.
    """
    try:
        exr_file = OpenEXR.InputFile(file_path)
        header = exr_file.header()
        timecode = header.get('timeCode', None) 
        clip_frame_rate = header.get('nuke/input/frame_rate')

        # Иногда информация о фрейм рейте хранится в байтовом представлении. Учитываем это.
        if clip_frame_rate is not None:
            clip_frame_rate = float(clip_frame_rate.decode()) if isinstance(clip_frame_rate, bytes) else float(clip_frame_rate)
            if int(frame_rate) != int(clip_frame_rate):
                warning_message = f"Предупреждение. FPS шота расходится с проектным. FPS - {round(clip_frame_rate, 2)}"
                warnings_dict[exr_name] = warning_message
                logger.warning(f'\n{warning_message}')

        if timecode:
            # Таймкод хранится в формате объекта. Преобразуем в строку и извлекаем время.
            timecode_str = str(timecode)
            time_match = timecode_str.split("time: ")[1].split(",")[0].strip()  # Извлекаем значение времени
            return format_timecode(time_match)  # Приводим к двухзначному формату
        else:
            return None
    except Exception as e:
        error_message = f"Ошибка при обработке таймкода или значения FPS {file_path}: {e}"
        logger.error(error_message, exc_info=True) # Логирование
        return None

def is_correct_sequence(real_exr_name, frames_list_int): 
    """
    Функция проверяет есть ли битые кадры в секвенции.
    Если есть то пропускает текущий шот и переходит к следующему выводя предупреждение.
    """
    
    if not all(frames_list_int[i] + 1 == frames_list_int[i + 1] for i in range(len(frames_list_int) - 1)):
        warning_message = f"Предупреждение. Секвенция имеет пропущенные фреймы. Необходимо добавить шот вручную."
        warnings_dict[real_exr_name.split('.')[0]] = warning_message
        logger.warning(f'\n{warning_message}') # Логирование
        return False
    return True


def is_dublicate(target_name, all_cg_items):
    '''
    Функция находит шоты, версии которых уже стоят на таймлайне и пропускает их.
    '''
    try:
        if target_name in all_cg_items:
            return True
        return False
    except:
        return False
    
def get_clip_duration_and_timecode(path, frame_rate):
    try:
        media_info = MediaInfo.parse(path)
        print(media_info)
        # Получаем длительность и начальный таймкод видео
        for track in media_info.tracks:
            if track.track_type == "Video":
                # Длительность видео в секундах
                duration_seconds = track.duration / 1000  # переводим из миллисекунд в секунды
                duration_frames = duration_seconds * frame_rate  # умножаем на частоту кадров
                duration_frames = int(duration_frames) - 1  # Переводим в целое количество кадров. -1 для корректного восприятия в ДВР
                print("TACK TYPE")
                # Извлекаем начальный таймкод
                if track.other_delay:
                    print("DELAY")
                    timecode = tc(frame_rate, track.other_delay[4]).frames - 1 # -1 для корректного восприятия в ДВР
                return duration_frames, timecode
        
    except Exception as e:
        print(f"Ошибка при получении длительности видео: {e}")
        return None, None



def get_shot_name_and_timecodes_from_folder(name, all_files_mov_list, frame_rate, no_dublicates, all_cg_items):
    """
    Ищет файл с именем, соответствующим шаблону шота, в дереве каталогов и извлекает EXR секвенцию.
    """
    try:
        target_list = []
        target_mov_file = None

        # Обход дерева каталогов
        for mov_clip_path in all_files_mov_list:

            mov_name = os.path.basename(mov_clip_path)        
            if mov_name.endswith(".mov") and re.search(name.lower(), mov_name):  # Фильтр по названию
                target_list.append(mov_clip_path)

        # Итерация по списку с версиями одного шота. Если таковые имеются
        target_list_dict = []
        for target_mov_file in target_list:
            if not target_mov_file:
                return []

            mov_clip_name = os.path.basename(target_mov_file)
            mov_clip_path = target_mov_file
            mov_clip_duration, mov_start_tc = get_clip_duration_and_timecode(mov_clip_path, frame_rate)

                        # Пропускаем шот, если нет
            print(name, mov_clip_duration, tc(frame_rate, frames=mov_start_tc))
            if mov_clip_duration is None or mov_start_tc is None:
                warnings_dict[mov_clip_name] = f'Ошибка при обработке шота. Необходимо добавить его вручную в Media Pool.'
                return []


            # Добавление шота с метой в словарь
            target_list_dict.append({
                "mov_clip_name": mov_clip_name,
                "mov_clip_path": mov_clip_path,
                "mov_clip_duration": mov_clip_duration,
                "mov_start_tc": mov_start_tc
            })
        return target_list_dict
    except Exception as e:
        error_message = f"Ошибка при обработке файла: {e}"
        logger.error(error_message, exc_info=True) # Логирование
        warnings_dict[name] = f'Ошибка при обработке шота. Необходимо добавить его вручную в Media Pool.'
        return []
    
def create_otio(meta_dict, frame_rate, timeline, otio_clip_start_frame):
    """
    Функция добавления треков и gap объектов на таймлайн.
    """
    try:
        # Получаем существующий видеотрек
        track_ind = meta_dict['track_ind']
        video_track = timeline.tracks[track_ind]


        # Распаковка метаданных шота и данных GAP
        clip_duration = meta_dict['mov_duration']
        gap_duration = meta_dict['gap_duration']
        clip_path = meta_dict['mov_path']
        clip_name = meta_dict['mov_name']
        clip_start_frame = meta_dict['start_frame']
        timeline_duration = meta_dict['timeline_duration']

        # Логирование
        debug_exr_info = f'Shot name: {clip_name}\nShot start timecode: {clip_start_frame}\nShot duration: {clip_duration}\nShot path: {clip_path}\nGap duration: {gap_duration}'
        logger.debug(f'\n{debug_exr_info}')

        # Проверка на наличине или отсутствие GAP между клипами
        if gap_duration > 0:
            # Создание GAP объекта
            gap = otio.schema.Gap(
                source_range=otio.opentime.TimeRange(
                    start_time=otio.opentime.RationalTime(0.0, frame_rate),
                    duration=otio.opentime.RationalTime(gap_duration, frame_rate),
                )
            )
            video_track.append(gap)

        # Создание ссылки на видеофайл
        media_reference = otio.schema.ExternalReference(
            target_url=clip_path,
            available_range=otio.opentime.TimeRange(
                start_time=otio.opentime.RationalTime(clip_start_frame, frame_rate),
                duration=otio.opentime.RationalTime(clip_duration, frame_rate),
            ),
        )

        # Создание клипа
        clip = otio.schema.Clip(
            name=clip_name,
            media_reference=media_reference,
            source_range=otio.opentime.TimeRange(
                start_time=otio.opentime.RationalTime(otio_clip_start_frame or 0, frame_rate),
                duration=otio.opentime.RationalTime(timeline_duration, frame_rate),
            ),
        )
        '''
                # Создание ссылки на аудиофайл
        audio_media_reference = otio.schema.ExternalReference(
            target_url=clip_path,  # Путь к аудиофайлу
            available_range=otio.opentime.TimeRange(
                start_time=otio.opentime.RationalTime(clip_start_frame, frame_rate),  # Начало аудио совпадает с видео
                duration=otio.opentime.RationalTime(clip_duration, frame_rate),  # Длительность аудио совпадает с видео
            ),
        )
        # Создание клипа для аудио
        audio_clip = otio.schema.Clip(
            name=clip_name + "audio",
            media_reference=audio_media_reference,
            source_range=otio.opentime.TimeRange(
                start_time=otio.opentime.RationalTime(otio_clip_start_frame, frame_rate),
                duration=otio.opentime.RationalTime(timeline_duration, frame_rate),
            ),
        )
        '''
        # Добавление клипа на трек
        video_track.append(clip)
        #audio_track.append(audio_clip)

    except Exception as e:
        error_messege = f"Ошибка. Не удалось добавить на таймлайн секвенцию {clip_name}."
        logger.error(error_messege, exc_info=True) # Логирование

def parse_edl_and_get_clip_data(edl_path, frame_rate, all_folders_list, no_dublicates, all_cg_items):
    """
    Основная функция
    """
    try:
        # Создание таймлайна и треков Video1, Video2 и т.д.
        timeline = otio.schema.Timeline(name="Timeline") 
        video_tracks = []  # Массив для треков
        #audio_track = otio.schema.Track(name=f'Audio1', kind=otio.schema.TrackKind.Audio)
        #timeline.tracks.append(audio_track)
        track_count = 10  # Количество треков

        # Создание нужного количества треков
        for i in range(track_count):
            video_tracks.append(otio.schema.Track(name=f'Video{i+1}', kind=otio.schema.TrackKind.Video))
            timeline.tracks.append(video_tracks[i])

        # Промежуточные значения для вычисления GAP на каждом треке
        end_tc_tracks = [None] * track_count  # Список для хранения edl timeline end timecode для каждого трека

        # Чтение EDL с шотами
        with open(edl_path, 'r') as edl_file:
            lines = edl_file.readlines()

        # Парсинг EDL-файла
        for line in lines:
            if re.search(r'^\d+\s', line.strip()):  # Паттерн ищет значения 001, 0001 и т.д. по началу строки
                parts = line.split()
                edl_timeline_start_tc = parts[6]
                edl_timeline_end_tc = parts[7]
                edl_start_hour = edl_timeline_start_tc.split(":")[0]
                tmln_start_hour = tc(frame_rate, edl_start_hour + ":00:00:00").frames
                current_name = parts[1]
                edl_src_start_tc = parts[4]
                edl_src_end_tc = parts[5]

                # Получаем данные из EXR-файлов. Если их нет, переходим к следующему шоту
                mov_clip_info = get_shot_name_and_timecodes_from_folder(current_name, all_folders_list, frame_rate, no_dublicates, all_cg_items)
                if not mov_clip_info:
                    continue

                for track_ind, mov_info in enumerate(mov_clip_info):

                    # Распаковка данных о EXR
                    mov_clip_name = mov_info["mov_clip_name"]
                    mov_clip_path = mov_info["mov_clip_path"]
                    mov_clip_duration = mov_info["mov_clip_duration"]
                    mov_start_tc = mov_info["mov_start_tc"]

                    is_crash_exr(mov_clip_path)
                    

                    # Вычисление таймлайн дюрэйшн
                    timeline_duration = tc(frame_rate, edl_timeline_end_tc).frames - tc(frame_rate, edl_timeline_start_tc).frames

                    # Смещение фазы на 1 фрейм для отрезания слейта по началу
                    otio_clip_start_frame = mov_start_tc + 1 


                    # Вычисление GAP для клипов
                    gap_dur = is_first_gap(frame_rate, edl_timeline_start_tc, tmln_start_hour, end_tc_tracks, track_ind)
                    
                    
                    # Проверка на длину
                    is_lenght(mov_clip_duration, timeline_duration, mov_clip_name)

                    # Словарь с данными GAP, EXR-секвенции и трек индекс
                    meta_dict = {
                        'mov_path': mov_clip_path,
                        'mov_name': mov_clip_name,
                        'gap_duration': gap_dur,
                        'start_frame': mov_start_tc,
                        'mov_duration': mov_clip_duration,
                        'timeline_duration': timeline_duration,
                        'track_ind': track_ind
                    }

                    # Логирование
                    logger.debug(f'\nTimeline start timecode: {edl_timeline_start_tc}\nTimeline end timecode: {edl_timeline_end_tc}')
                    logger.debug(f'\nEDL source start timecode: {edl_src_start_tc}\nEDL source end timecode: {edl_src_end_tc}\nTimeline duration: {timeline_duration}')
                    create_otio(meta_dict, frame_rate, timeline, otio_clip_start_frame)

                    # Обновление end_timecode для текущего трека
                    end_tc_tracks[track_ind] = edl_timeline_end_tc
                    
                    
        # Возврат сформированного таймлайна
        all_tracks_len = sum([len(track) for track in video_tracks]) # Получение количества объектов на таймлайне
        return timeline, all_tracks_len
    except Exception as e:
        error_message = f"Сбой в работе программы. Не удалось сформировать OTIO файл: {e}"
        logger.error(error_message, exc_info=True)  # Логирование

# Основной класс GUI
class OTIOConverterApp:
    def __init__(self, root):
        self.shots_count = 0
        self.shots_count_in_folder = 0
        self.root = root
        self.root.title("Autoconform Dailies")
        root.attributes('-topmost', True)

        window_width = 640
        window_height = 660

        screen_width = root.winfo_screenwidth()
        screen_height = root.winfo_screenheight()

        # Центрирование окна
        x = (screen_width // 2) - (window_width // 2)
        y = int((screen_height * 7 / 10) - (window_height / 2))
        root.geometry(f"{window_width}x{window_height}+{x}+{y}")

        def on_button_click(button, func):
            def task():
                button.config(state=tk.DISABLED)
                func()
                button.config(state=tk.NORMAL)
            Thread(target=task).start()

        # Рамка для текста и скроллбара
        warning_frame = tk.Frame(root)
        warning_frame.pack(anchor="c", fill=tk.BOTH)

        # Поле предупреждений с прокруткой

        def enable_copy(event):
            try:
                selected_text = self.warning_field.get("sel.first", "sel.last")
                self.root.clipboard_clear()
                self.root.clipboard_append(selected_text)
                self.root.update()
            except tk.TclError:
                pass  # Игнорируем ошибку, если нет выделенного текста
        self.warning_field = tk.Text(warning_frame, height=15, width=70, wrap=tk.WORD)
        self.warning_field.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        scrollbar = tk.Scrollbar(warning_frame, orient=tk.VERTICAL, command=self.warning_field.yview)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        self.warning_field.configure(yscrollcommand=scrollbar.set)
        self.warning_field.insert("1.0", "Здесь будут показаны предупреждения программы.\n")
        self.warning_field.config(state="normal")
        self.warning_field.bind("<Control-c>", enable_copy)
        self.warning_field.bind("<Command-c>", enable_copy)

        # Переменные для хранения путей
        self.edl_path = tk.StringVar()
        self.exr_folder = tk.StringVar()
        self.otio_path = tk.StringVar()
        self.selected_track_in = tk.StringVar(value=8)
        self.selected_track_out = tk.StringVar(value=8)

        self.projects = sorted([i for i in os.listdir(projects_path) if os.path.isdir(projects_path / i)])
        self.selected_project = tk.StringVar(root)
        self.selected_project.set(self.projects[0])  # Проект по умолчанию

        # Рамка для центрирования выбора проекта
        project_frame = tk.Frame(root)
        project_frame.pack(anchor="c", pady=10)

        # Метка "Выберите проект" (по центру)
        tk.Label(project_frame, text="Выберите проект:", font=("Arial", 12)).pack(anchor="c")

        # Меню выбора проекта (по центру)
        project_menu = tk.OptionMenu(project_frame, self.selected_project, *self.projects)
        project_menu.pack(anchor="c", pady=5)

        # Рамка для чекбокса и выбора трека (в одной строке)
        options_frame = tk.Frame(root)
        options_frame.pack(anchor="c", pady=10)

        # Чекбокс "Игнорировать дубликаты шотов"
        self.no_duplicates = tk.BooleanVar()
        tk.Checkbutton(options_frame, text="Игнорировать дубликаты шотов", variable=self.no_duplicates).pack(side=tk.LEFT, padx=10)

        # Поле ввода диапазона трека
        tk.Label(options_frame, text="Диапазон треков:").pack(side=tk.LEFT)
        tk.Entry(options_frame, textvariable=self.selected_track_in, width=3).pack(side=tk.LEFT, padx=5)

        tk.Label(options_frame, text='-').pack(side=tk.LEFT)
        tk.Entry(options_frame, textvariable=self.selected_track_out, width=3).pack(side=tk.LEFT, padx=5)

        # Поля для ввода
        tk.Label(root, text="Выберите EDL файл:").pack(anchor="c")
        tk.Entry(root, textvariable=self.edl_path, width=60).pack(anchor="c")
        tk.Button(root, text="Обзор", command=self.select_edl).pack(anchor="c")

        tk.Label(root, text="Выберите папку с EXR файлами:").pack(anchor="c")
        tk.Entry(root, textvariable=self.exr_folder, width=60).pack(anchor="c")
        tk.Button(root, text="Обзор", command=self.select_exr_folder).pack(anchor="c")

        tk.Label(root, text="Путь для сохранения OTIO файла:").pack(anchor="c")
        tk.Entry(root, textvariable=self.otio_path, width=60).pack(anchor="c")
        tk.Button(root, text="Обзор", command=self.save_otio).pack(anchor="c")

        # Кнопка "Создать OTIO"
        button_create = tk.Button(root, text="Создать OTIO", command=lambda: on_button_click(button_create, self.create_otio))
        button_create.pack(anchor="c")

        self.result_label = tk.Label(root, text="Обработано 0 шотов из 0", font=("Arial", 17, "bold"))
        self.result_label.pack()

        # Фрейм для кнопок внизу
        bottom_frame = tk.Frame(root)
        bottom_frame.pack(side=tk.BOTTOM, fill=tk.X, pady=10)

        # Залочен импорт otio в dvr до лучших времен
        '''
        # Кнопка "Импортировать OTIO" по центру
        button_import = tk.Button(root, text="Импортировать в Resolve", command=self.import_otio_to_resolve)
        button_import.pack(anchor="c")
        button_import.config(state=tk.DISABLED)
        '''

        # Кнопка "Logs" в левом углу
        button_logs = tk.Button(bottom_frame, text="Open logs", command=self.open_logs)
        button_logs.pack(anchor='w', padx=45)

    def select_edl(self):
        project_name = self.selected_project.get()
        init_dir = is_OS(f'003_transcode_to_vfx/projects/{project_name}/')
        path = filedialog.askopenfilename(initialdir=init_dir,
                                          filetypes=[("EDL files", "*.edl")])
        if path:
            self.edl_path.set(path)

    def select_exr_folder(self):

        path = filedialog.askdirectory(initialdir={"nt": "R:/", "posix": "/Volumes/RAID/"}[os.name])
        if path:
            self.exr_folder.set(path)

    def save_otio(self):
        project_name = self.selected_project.get()
        init_dir = is_OS(f'003_transcode_to_vfx/projects/{project_name}/')
        path = filedialog.asksaveasfilename(initialdir=init_dir, 
                                            defaultextension=".otio", filetypes=[("OTIO files", "*.otio")])
        if path:
            self.otio_path.set(path)

    def update_result_label(self):
        self.result_label.config(text=f'Обработано {self.shots_count} из {self.shots_count_in_folder} шотов')


    def resolve_shot_list(self):
        # Подключение API Resolve, если открыт проект + получение списка всех .exr секвенций с таймлайна 
        try:
            resolve = dvr.scriptapp("Resolve")
            project_manager = resolve.GetProjectManager()
            project = project_manager.GetCurrentProject()
            timeline = project.GetCurrentTimeline()
            pattern_shot_exr = r'(.+_)?\d{1,4}[a-zA-Z]?_\d{1,4}_.+'

            all_cg_items = []
            for track in range(int(self.selected_track_in.get()), int(self.selected_track_out.get()) + 1):
                all_cg_items += timeline.GetItemListInTrack('video', track)
            all_cg_items = Counter([item.GetName() for item in all_cg_items if item.GetName().endswith(('.exr')) and re.search(pattern_shot_exr, item.GetName())])
            return all_cg_items
        except:
            return []
        
    def sum_shots(self):
            timeline = otio.adapters.read_from_file(self.otio_path.get())
            # Проверяем, есть ли дорожки
            if not timeline.tracks:
                messagebox.showwarning("Предупреждение","Нет дорожек на таймлайне")
            else:
                total_clips = 0 
                # Проходим по всем дорожкам
                for _, track in enumerate(timeline.tracks):
                    clip_count = sum(1 for item in track if isinstance(item, otio.schema.Clip))
                    total_clips += clip_count  # Добавляем к общему количеству

            self.shots_count += total_clips

    def sum_shots_in_folder(self):

        count = 0 
        for dirpath, _, files in os.walk(self.exr_folder.get()):
            # Проверяем, есть ли хотя бы один .exr файл в текущей папке
            for file in files:
                if file.lower().endswith(".mov"): 
                    count += 1  # Плюсуем к счетчику

        self.shots_count_in_folder = count

    def create_otio(self):
        try:
            edl_path = self.edl_path.get()
            exr_folder = self.exr_folder.get()
            otio_path = self.otio_path.get()
            all_cg_items = self.resolve_shot_list()

            if not edl_path or not exr_folder or not otio_path:
                messagebox.showerror("Ошибка", "Заполните все пути перед созданием OTIO файла.")
                return

            frame_rate = 24  # Задайте вашу частоту кадров
            #warnings_dict.clear()  # Очистка предупреждений перед новой итерацией

            # Сбор всех фолдеров корневой папки(R:/) в список
            all_folders_list = [os.path.join(root, file) for root, folders, files in os.walk(exr_folder) for file in files]
            print(all_folders_list)
            # Передача в конвеер обработки
            timeline, is_clip_on_track = parse_edl_and_get_clip_data(edl_path, frame_rate, all_folders_list, self.no_duplicates.get(), all_cg_items)

            # Проверка на наличие объектов на таймлинии
            if is_clip_on_track == 0:
                messagebox.showinfo('Предупреждение', 'Нет EXR файлов для данной таймлинии')
            else:
                messagebox.showinfo("Успех", f"OTIO файл успешно создан: {otio_path}")

            # Запись таймлайна в файл OTIO
            otio.adapters.write_to_file(timeline, otio_path)

            # Проверка количества клипов на таймлайне и общего количества клипов в фолдере
            self.sum_shots()
            self.sum_shots_in_folder()
            
            # Апдейт данных счетчика
            self.update_result_label()           
                
            # Отображение предупреждений в текстовом поле
            self.warning_field.delete("1.0", tk.END) 
            for clip, warning in warnings_dict.items():
                self.warning_field.insert(tk.END, f"{clip}: {warning}\n")
        except Exception as e:
            messagebox.showerror("Ошибка", f"Не удалось создать OTIO файл: {e}")

    def import_otio_to_resolve(self):
        try:
            otio_path = self.otio_path.get()

            if not otio_path:
                messagebox.showerror("Ошибка", "Сначала создайте или выберите OTIO файл.")
                return

            resolve = dvr.scriptapp("Resolve")
            if not resolve:
                messagebox.showerror("Ошибка", "Не удалось подключиться к DaVinci Resolve.")
                return

            project_manager = resolve.GetProjectManager()
            project = project_manager.GetCurrentProject()
            if not project:
                messagebox.showerror("Ошибка", "Не удалось получить текущий проект DaVinci Resolve.")
                return

            timeline = project.ImportTimelineFromFile(otio_path)
            if timeline:
                messagebox.showinfo("Успех", f"OTIO файл успешно импортирован в DaVinci Resolve.")
            else:
                messagebox.showerror("Ошибка", "Импорт OTIO файла завершился неудачей.")
        except Exception as e:
            messagebox.showerror("Ошибка", f"Ошибка при импорте OTIO файла: {e}")

    def open_logs(self):
            log_file_path = is_OS(log_path)
            try:
                if platform.system() == 'Darwin':  # macOS
                    subprocess.Popen(['open', log_file_path])
                elif platform.system() == 'Windows':  # Windows
                    os.startfile(log_file_path)
                else:  # Linux и другие Unix-подобные системы
                    subprocess.Popen(['xdg-open', log_file_path])
            except Exception as e:
                messagebox.showerror("Ошибка", f"Ошибка при открытии файла логов: {e}")

# Запуск приложения
if __name__ == "__main__":
    root = tk.Tk()
    app = OTIOConverterApp(root)
    root.mainloop()






'''
Обрабатывается как оффлайн клип:
Если не верный фпс у EXR
Добавляются фриз фреймы если шот короче чем должен быть по рэнжу на таймлайне
Не обрабатывается:
Если не верный нейминг шота
Если есть пропущеные файлы в секвенции


Работает с 2 версиями имени секвенции
Работает с несколькими версиями одного шота(4 версии)
Уведомляет когда шот короче чем должен быть
Уведомляет если есть пропущеные фреймы
Уведомляет о битых EXR-файлах
Добавляются захлесты если о них есть информация в исходнике и edl
Обрабатываются имена если есть ошибки с нулями в номере? например 01_010
Уведомляет о несоответствии фпс проекта и шота
'''

"""
Добавить каунтер по количеству сформированных шотов?

Добавить корректную обработку ситуаций с шотами которые короче чем в монтаже
Дописать обработку закрытого проекта?
"""