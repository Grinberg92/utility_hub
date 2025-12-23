from pprint import pformat
import re
import math
from timecode import Timecode as tc
import DaVinciResolveScript as dvr
import sys
import os
from pathlib import Path
from PyQt5 import QtWidgets, QtCore
from PyQt5.QtCore import Qt, QThread, pyqtSignal
from PyQt5.QtWidgets import (QMessageBox, QVBoxLayout, QHBoxLayout, QLabel, QRadioButton,
    QLineEdit, QComboBox, QGroupBox, QCheckBox, QPushButton, QSizePolicy, QApplication, QFileDialog, QFrame)
from dvr_tools.css_style import apply_style
from dvr_tools.logger_config import get_logger
from dvr_tools.resolve_utils import ResolveObjects
from common_tools.edl_parsers import detect_edl_parser, EDLParser

logger = get_logger(__file__)

SETTINGS = {
    "shot_name": r"^(?:[A-Za-z]{3,4}_)?[A-Za-z0-9]{3,4}_[A-Za-z0-9]{3,4}$",
    "exceptions": ["RETIME WARNING"],
    "track_postfix": '_VT',
}

class LogicProcessor:
    """
    Класс работы с логикой.
    """
    def __init__(self, user_config, signals):
        self.user_config = user_config
        self.signals = signals

    def timecode_to_frame(self, timecode)-> int:
        """
        Метод получает таймкод во фреймах.
        """
        return tc(self.fps, timecode).frames

    def frame_to_timecode(self, frames) -> tc:
        """
        Метод получает таймкод из значений фреймов.
        """
        return tc(self.fps, frames=frames)

    def get_markers(self, mode="external") -> list: 
        '''
        Получение маркеров для работы других методов.

        :param mode: При 'external' - будет прибавляться 1 фрейм для корректной работы с внешними монтажными документами. 
        При 'internal' для работы с маркерами внутри резолв ничего не добавляем.
        '''
        try:
            markers_list = []
            for timecode, name in self.timeline.GetMarkers().items():
                name = name[self.marker_from].strip()
                if timecode == 0:
                    self.signals.error_signal.emit(f"Таймкод первого маркера равен 0\nУдалите или переместите его.")
                    return False
                timecode_marker = tc(self.fps, frames=timecode + self.timeline_start_tc) + (0,1)[mode == "external"]  
                markers_list.append((name, timecode_marker))
            return markers_list
        except Exception as e:
            self.signals.error_signal.emit(f"Ошибка получения данных об объектах маркеров: {e}")
            return False

    def set_markers(self) -> bool:
        '''
        Установка маркеров с номерами полученными из оффлайн клипов на текущем таймлайне.
        Поддерживает опциональную фильтрацию по паттерну имени шота при создании маркера.
        В зависимости от self.center_marker устанавливается по старту клипа или середине клипа.
        '''
        try:
            clips = self.timeline.GetItemListInTrack('video', self.track_number)
            no_markers = True
            for clip in clips:
                clip_name = clip.GetName()

                if self.shot_filter:
                    if re.search(SETTINGS["shot_name"], clip_name):
                        if self.center_marker:
                            clip_start = int((clip.GetStart() + (clip.GetStart() + clip.GetDuration())) / 2) - self.timeline_start_tc
                        else:
                            clip_start = int(clip.GetStart()) - self.timeline_start_tc
                        if self.timeline.AddMarker(clip_start, 'Blue', clip_name, "", 1, 'Renamed'):
                            no_markers = False
                else:
                    if self.center_marker:
                        clip_start = int((clip.GetStart() + (clip.GetStart() + clip.GetDuration())) / 2) - self.timeline_start_tc
                    else:
                        clip_start = int(clip.GetStart()) - self.timeline_start_tc
                    if self.timeline.AddMarker(clip_start, 'Blue', clip_name, "", 1, 'Renamed'):
                        no_markers = False

            if no_markers:
                self.signals.warning_signal.emit(f"Маркеры не были созданы.")
                return False 
            logger.info("Маркеры успешно установлены.")
            return True
        except Exception as e:
            self.signals.error_signal.emit(f"Ошибка создания маркеров: {e}")
            return False

    def export_locators_to_avid(self) -> bool:
        '''
        Формирование строк и экспорт локаторов для AVID в .txt.
        Поддерживает опциональную фильтрацию по паттерну имени шота при конвертации в локаторы.
        '''
        try:
            markers_list = self.get_markers()
            if not markers_list:
                return
            
            path = Path(self.locator_output_path) / f"{self.timeline.GetName()}.txt"
            with open(path, "a", encoding='utf8') as output:

                for name, timecode in markers_list:
                    if self.shot_filter:
                        if re.match(SETTINGS["shot_name"], name, re.IGNORECASE) or name in SETTINGS["exceptions"]:
                            # Используется спец табуляция для корректного импорта в AVID
                            output_string = f'PGM	{str(timecode)}	V3	yellow	{name}'
                            output.write(output_string + "\n")
                    else:
                        # Используется спец табуляция для корректного импорта в AVID
                        output_string = f'PGM	{str(timecode)}	V3	yellow	{name}'
                        output.write(output_string + "\n")
            logger.info("Локаторы успешно созданы.")
            return True
        
        except Exception as e:
            self.signals.error_signal.emit(f"Ошибка создания локаторов: {e}")
            return False
        
    def convert_timecode(self, timecode) -> str:
        """
        Метод изменяет формат таймкода под стандарт SRT. Извлекает фрейм из стандартного таймкода и конвертирует в милисекунды.
        Пример: 01:08:43:18 --> 01:08:43,750.

        :return: Таймкод в конвертированом формате 00:00:00,000
        """
        base = ":".join(str(timecode).split(":")[:3])
        frames = str(timecode).split(":")[3]
        frames_to_mmm = f'{math.ceil(int(frames) * (1000 / 24)):03d}'
        return ",".join([base, frames_to_mmm])
    
    def get_edl_data(self) -> list:
        """
        Получение и конвертация данных из EDL файла.

        :return names: Список с данными по каждому шоту из EDL.
        """
        parser = detect_edl_parser(self.fps, self.edl_path)
        items_data = []
        for shot in parser:
            name = shot.edl_shot_name
            start_tc_frames = tc(self.fps, shot.edl_record_in).frames - 1 # Вычитание 1 - компенсация лишней единицы при конвертации из таймода во фреймы 
            end_tc_frames = tc(self.fps, shot.edl_record_out).frames - 1 # Вычитание 1 - компенсация лишней единицы при конвертации из таймода во фреймы 
            duration = (end_tc_frames - start_tc_frames) + 1 # +1 - компенсация для корректных значений
            start_tc = self.convert_timecode(tc(self.fps, frames=start_tc_frames + 1)) # +1 - компенсация для корректных значений
            end_tc = self.convert_timecode(tc(self.fps, frames=start_tc_frames + duration)) 
            items_data.append((name, start_tc, end_tc))
        
        return items_data
            
    def srt_from_edl(self, edl_path) -> bool:
        """
        Создание SRT файла из данных, извлеченных из EDL файла.
        """
        try:
            result_path = Path(str(edl_path).replace(".edl", "_converted.srt"))
            items_data = self.get_edl_data()
            with open(result_path, "a" ,encoding="utf-8") as o:
                for index, data in enumerate(items_data, start=1):
                    name, start_tc, end_tc = data
                    index_str = index
                    timecode_str = f"{start_tc} --> {end_tc}"
                    name_str = name

                    o.write(f"{index_str}\n{timecode_str}\n{name_str}\n\n")
            logger.info(f"SRT файл успешно создан: {result_path}")
            return True
        except Exception as e:
            self.signals.error_signal.emit(f"Ошибка создания SRT файла {e}")
            return False
        
    def convert_timecode_srt(self, timecode: str) -> str:
        """
        Конвертирует таймкод из формата SRT (HH:MM:SS,mmm)
        в формат видеотаймкода (HH:MM:SS:FF), где FF — кадры.
        
        Пример: 01:08:43,750 --> 01:08:43:18 (при 24 fps)
        """
        base, ms = timecode.split(',')
        frames = math.ceil(int(ms) * self.fps / 1000)
        return f"{base}:{frames:02d}"
        
    def edl_from_srt(self, srt_path: str) -> None:
        """
        Создание EDL файла оффлайн клипов с номерами шотов, из данных полученных из SRT файла.
        """
        try:
            result_path = Path(str(srt_path).replace(".srt", "_converted.edl"))

            with open(srt_path, 'r', encoding='utf-8') as input:
                srt = input.read().strip().split('\n\n')

                for i in srt:
                    number, timecode_raw, shot_name = i.split('\n')
                    number = number.strip('\ufeff') # Удаление символа по началу самой первой строки
                    record_in_raw, record_out_raw = timecode_raw.split('-->')
                    record_in = self.convert_timecode_srt(record_in_raw)
                    record_out = self.convert_timecode_srt(record_out_raw)
                    rec_duration = self.timecode_to_frame(record_out) - self.timecode_to_frame(record_in) 
                    src_in = "00:00:00:00"
                    src_out = self.frame_to_timecode(self.timecode_to_frame(src_in) + rec_duration)
                    shot_name = shot_name.strip("<b>").strip("</b>")
                    with open(result_path, 'a', encoding='utf-8') as o:
                        # Жестко придерживаться табуляции, что бы корректно принимал AVID
                        o.write(f"000{number}  {shot_name} V     C        {src_in} {src_out} {record_in} {record_out}\n")
                        o.write(f"* FROM CLIP NAME: {shot_name}\n")

            logger.info("EDL файл из SRT успешно создан: {result_path}")
            return True
        except Exception as e:
            self.signals.error_signal.emit(f"Ошибка создания EDL файлов из SRT {e}")
            return False
        
    def create_temp_edl(self) -> None:
        """
        Создает промежуточный EDL для offline edl.
        """
        tmp_path = str(Path(__file__).resolve().parent.parent / "temp_edl.edl")
        result = self.timeline.Export(tmp_path, self.resolve.EXPORT_EDL)
        if result:
            return tmp_path
        else:
            self.signals.error_signal.emit(f"Ошибка создания промежуточного EDL файла.")
            return False
        
    def kill_tmp_edl(self, edl_file):
        """
        Удаляет промежуточный EDL для offline edl.
        """
        os.remove(edl_file)

    def create_output_edl(self, shot: EDLParser, output, marker_name:list=None) -> None:
        """
        Метод формирует аутпут файл в формате, пригодном для отображения оффлайн клипов в Resolve и AVID.
        """
        shot_name = marker_name if marker_name is not None else shot.edl_shot_name

        output.write(f"{shot.edl_record_id} {shot_name} "
                f"{shot.edl_track_type} {shot.edl_transition} "
                f"{shot.edl_source_in} {shot.edl_source_out} "
                f"{shot.edl_record_in} {shot.edl_record_out}")
        output.write(f'\n* FROM CLIP NAME: {shot_name}\n\n')

    def process_edl(self) -> bool:
        """
        Выводит EDL для дейлизов и EDL с оффлайн клипами.
        """
        try:
            markers = self.get_markers()
            
            tmp_edl = self.create_temp_edl()
            if tmp_edl:

                parser = detect_edl_parser(fps=self.fps, edl_path=tmp_edl)
                with open(self.output_path, "w", encoding='utf8') as output:

                    for shot in parser:
                        if self.offline_edl:
                            marker_name = None
                            for name, timecode in markers:
                                if tc(self.fps, shot.edl_record_in).frames <= tc(self.fps, timecode).frames <= tc(self.fps, shot.edl_record_out).frames:
                                    marker_name = name
                            if marker_name is not None:
                                self.create_output_edl(shot, output, marker_name)

                logger.info("EDL файл успешно создан.")
                self.kill_tmp_edl(tmp_edl)
                return True
            else:
                return False
            
        except Exception as e:
            self.signals.error_signal.emit(f"Ошибка формирования EDL: {e}")
            return False
        
    def from_markers(self) -> None:
        """
        Присвоение имен из маркеров.
        """
        markers = self.get_markers(mode="internal")

        for track_index in range(2, self.count_of_tracks + 1):
            clips_under = self.timeline.GetItemListInTrack('video', track_index)
            for clip_under in clips_under:
                applied = False  # было ли имя присвоено этому текущему clip_under
                for name, timecode in markers:
                    if clip_under.GetStart() <= timecode < (clip_under.GetStart() + clip_under.GetDuration()):
                        # Вычитаем - 1, чтобы отсчет плейтов был с первой дорожки, а не второй
                        name_new = self.prefix + name + self.postfix + ("", SETTINGS["track_postfix"] + str(track_index - 1))[self.set_track_id]
                        clip_under.SetName(name_new)
                        logger.info(f'Добавлено кастомное имя "{name_new}" в клип на треке {track_index}')
                        applied = True

                if not applied:
                    self.warnings.append(f"Для клипа {clip_under.GetName()} на треке {track_index} не было установлено имя")

    def from_offline(self, items: list) -> None:
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
                        name = self.prefix + item.GetName() + self.postfix + ("", SETTINGS["track_postfix"] + str(track_index - 1))[self.set_track_id]
                        clip_under.SetName(name)
                        logger.info(f'Добавлено кастомное имя "{name}" в клип на треке {track_index}')
                        applied = True
                        break 

                if not applied:
                    self.warnings.append(
                        f"Для клипа {clip_under.GetName()} на треке {track_index} не было установлено имя")

    def set_name(self, items: list) -> bool:
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

    def convert_v3_to_v23(self, edl_path: str) -> None:
        """
        Конвертация EDLv3 с маркерами в EDLv23 с оффлайн клипами (для AVID).
        """
        output_path = Path(str(edl_path).replace(".edl", "_converted_to_v23.edl"))
        try:
            parser = detect_edl_parser(fps=self.fps, edl_path=edl_path)

            with open(output_path, 'a', encoding="utf-8") as output:
                for shot in parser:
                    self.create_output_edl(shot, output)
            logger.info("EDL файл успешно создан.")
            return True

        except Exception as e:
            self.signals.error_signal.emit(f"Ошибка конвертации EDL: {e}")
            return False
            
    def run(self) -> bool:
        self.timeline = ResolveObjects().timeline
        self.resolve = ResolveObjects().resolve
        self.process_edl_logic = self.user_config["process_edl"]
        self.output_path = self.user_config["output_path"]
        self.edl_path = self.user_config["edl_path"]
        self.locator_output_path = self.user_config["locator_output_path"]
        self.export_loc_cb = self.user_config["export_loc"]
        self.fps = int(self.user_config["fps"])
        self.track_number = int(self.user_config["track_number"])
        self.set_markers_cb = self.user_config["set_markers"]
        self.marker_from = self.user_config["locator_from"]
        self.timeline_start_tc = self.timeline.GetStartFrame()
        self.offline_edl = self.user_config["offline_checkbox"]
        self.srt_create_bool = self.user_config["create_srt_checkbox"]
        self.name_from_track = self.user_config["set_name_from_track"]
        self.name_from_markers = self.user_config["set_name_from_markers"]
        self.offline_track = int(self.user_config["offline_track_number"])
        self.shot_filter = self.user_config["shot_filter"]
        self.center_marker = self.user_config["is_center_marker"]
        self.edl_from_srt_bool = self.user_config["create_edl_from_srt"]
        self.prefix = self.user_config["prefix_name"]
        self.postfix = self.user_config["postfix_name"]
        self.set_track_id = self.user_config["set_track_id"]
        self.convert_edl = self.user_config["convert_edl"]

        self.count_of_tracks = self.timeline.GetTrackCount('video')
        items = self.timeline.GetItemListInTrack('video', self.offline_track)
        self.warnings = []

        if self.process_edl_logic:
            process_edl_var = self.process_edl()
            if not process_edl_var:
                return False

        if self.set_markers_cb:
            set_markers_var = self.set_markers()
            if not set_markers_var:
                return False

        if self.export_loc_cb:
            export_loc_var = self.export_locators_to_avid()
            if not export_loc_var:
                return False
            
        if self.srt_create_bool:
            srt_create_var = self.srt_from_edl(self.edl_path)
            if not srt_create_var:
                return False
            
        if self.edl_from_srt_bool:
            edl_from_srt_var = self.edl_from_srt(self.edl_path)
            if not edl_from_srt_var:
                return False
            
        if self.convert_edl:
            convert_edl_var = self.convert_v3_to_v23(self.edl_path)
            if not convert_edl_var:
                return False
            
        if self.name_from_markers or self.name_from_track:
            set_name_var = self.set_name(items)
            if not set_name_var:
                return False
            
        return True
    
class LogicWorker(QThread):
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
        logic = LogicProcessor(self.user_config, self)
        success = logic.run()
        if success:
            self.success_signal.emit("Процесс успешно завершен!")

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
        "edl_path": self.gui.input_entry.text(),
        "output_path": self.gui.output_entry.text(),
        "export_loc": self.gui.export_loc_checkbox.isChecked(),
        "set_markers": self.gui.set_markers_checkbox.isChecked(),
        "process_edl": (self.gui.offline_clips_checkbox.isChecked()),
        "fps": self.gui.fps_entry.text(),
        "locator_output_path": self.gui.save_locators_path_entry.text(),
        "locator_from": self.gui.locator_from_combo.currentText(),
        "track_number": self.gui.track_entry.text().strip(),
        "offline_checkbox": self.gui.offline_clips_checkbox.isChecked(),
        "create_srt_checkbox": self.gui.create_srt_cb.isChecked(),
        "set_name_from_track": self.gui.from_track_cb.isChecked(),
        "set_name_from_markers": self.gui.from_markers_cb.isChecked(),
        "offline_track_number": self.gui.from_track_edit.text().strip(),
        "shot_filter": self.gui.filter_shot.isChecked(),
        "is_center_marker": self.gui.to_center_rb.isChecked(),
        "create_edl_from_srt": self.gui.srt_to_edl_cb.isChecked(),
        "prefix_name": self.gui.prefix.text() + ("_", "")[self.gui.prefix.text() == ""],
        "postfix_name": ("_", "")[self.gui.postfix.text() == ""] + self.gui.postfix.text(),
        "set_track_id": self.gui.set_track_id.isChecked(),
        "convert_edl": self.gui.convert_edl.isChecked()
        }
    
    def validate(self, user_config: dict) -> bool:
        """
        Валидирует конфиг.
        """
        self.errors.clear()

        process_edl = user_config["process_edl"]
        edl_path = user_config["edl_path"]
        output_path = user_config["output_path"]
        locator_output_path = user_config["locator_output_path"]
        export_loc_cb = user_config["export_loc"]
        fps = user_config["fps"]
        track_number = user_config["track_number"]
        offline_track_number = user_config["offline_track_number"]
        name_from_track = user_config["set_name_from_track"]
        name_from_markers = user_config["set_name_from_markers"]
        offline_edl_cb = user_config["offline_checkbox"]
        create_srt_cb = user_config["create_srt_checkbox"]
        set_markers_cb = user_config["set_markers"]
        edl_from_srt = user_config["create_edl_from_srt"]
        convert_edl = user_config["convert_edl"]

        if not any([name_from_track, name_from_markers, offline_edl_cb, 
                    create_srt_cb, export_loc_cb, set_markers_cb, edl_from_srt, convert_edl]):
            self.errors.append("Не выбрана ни одна опция!")
            return

        try:
            resolve = ResolveObjects()
        except RuntimeError as re:
            self.errors.append(str(re))
            return

        if process_edl and not output_path:
            self.errors.append("Выберите путь для сохранения EDL!")

        if create_srt_cb and not edl_path:
            self.errors.append("Укажите входной для EDL!")

        if create_srt_cb and not os.path.exists(edl_path):
            self.errors.append("Указан несуществующий путь к EDL!")

        if edl_from_srt and not edl_path:
            self.errors.append("Укажите входной путь для EDL!")

        if edl_from_srt and not os.path.exists(edl_path):
            self.errors.append("Указан несуществующий путь к EDL!")
        
        if not locator_output_path and export_loc_cb:
            self.errors.append("Введите путь для сохранения локаторов!")

        if convert_edl and not edl_path:
            self.errors.append("Укажите входной путь для EDL!")

        if convert_edl and not os.path.exists(edl_path):
            self.errors.append("Указан несуществующий путь к EDL!")

        try:
            fps = int(fps)
        except ValueError:
            self.errors.append("FPS должен быть числом!")
        
        if  resolve.timeline is None:
            self.errors.append("Неудалось получить таймлайн!")
            return
        
        if set_markers_cb:
            try:
                track_number = int(track_number)
                if track_number > resolve.timeline.GetTrackCount("video"):
                    self.errors.append("Указан несуществующий трек")
            except ValueError:
                self.errors.append("Номер дорожки должен быть числом!")

        if name_from_track:
            try:
                offline_track_number = int(offline_track_number)
                if offline_track_number > resolve.timeline.GetTrackCount("video"):
                    self.errors.append("Указан несуществующий трек")
            except ValueError:
                self.errors.append("Номер дорожки должен быть числом!")       

        return not self.errors

    def get_errors(self) -> list:
        return self.errors

class EDLProcessorGUI(QtWidgets.QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("EDL Processor")
        self.resize(670, 300)
        self.setWindowFlags(QtCore.Qt.WindowStaysOnTopHint)

        self.separator_set_name = QFrame()
        self.separator_set_name.setFrameShape(QFrame.HLine)
        self.separator_set_name.setStyleSheet("""
                                    QFrame {color: #555;
                                            background-color: #555}
                                        """)
        
        self.init_ui()

    def init_ui(self):
        main_layout = QVBoxLayout()
        self.setLayout(main_layout)

        # FPS + Locator From
        fps_layout = QHBoxLayout()
        fps_layout.addStretch()
        fps_layout.setAlignment(QtCore.Qt.AlignCenter)

        fps_label = QLabel("FPS:")
        self.fps_entry = QLineEdit("24")
        self.fps_entry.setFixedWidth(50)

        locator_label = QLabel("Marker from field:")
        self.locator_from_combo = QComboBox()
        self.locator_from_combo.setFixedWidth(70)
        self.locator_from_combo.addItems(["name", "note"])

        fps_layout.addWidget(fps_label)
        fps_layout.addWidget(self.fps_entry)
        fps_layout.addSpacing(20)
        fps_layout.addWidget(locator_label)
        fps_layout.addWidget(self.locator_from_combo)
        fps_layout.addStretch()
        main_layout.addLayout(fps_layout)

        # Locators / Track / Export Locators
        block1_group = QGroupBox("Resolve to markers")
        block1_group_layout = QVBoxLayout()
        block1_group_layout.addSpacing(15)


        # Set name 
        set_marker_layout = QHBoxLayout()
        self.set_markers_checkbox = QCheckBox("Set markers")
        self.set_markers_checkbox.stateChanged.connect(self.update_fields_state)
        set_marker_layout.addWidget(self.set_markers_checkbox)
        self.track_label = QLabel("from track:")
        self.track_entry = QLineEdit("1")
        self.track_entry.setEnabled(False)
        self.track_entry.setFixedWidth(40)
        set_marker_layout.addWidget(self.track_label)
        set_marker_layout.addWidget(self.track_entry)

        set_marker_label = QLabel("and place at:")
        self.to_start_rb = QRadioButton("start")
        self.to_start_rb.setEnabled(False)
        self.to_center_rb = QRadioButton("center")
        self.to_center_rb.setEnabled(False)
        self.to_center_rb.setChecked(True)
        set_marker_layout.addWidget(set_marker_label)
        set_marker_layout.addSpacing(15)
        set_marker_layout.addWidget(self.to_start_rb)
        set_marker_layout.addSpacing(15)
        set_marker_layout.addWidget(self.to_center_rb)
        set_marker_layout.addStretch()
        block1_group_layout.addLayout(set_marker_layout)

        # Locator & Shot filter
        options_layout = QHBoxLayout()
        options_layout.setAlignment(Qt.AlignLeft)

        self.export_loc_checkbox = QCheckBox("Export locators to Avid")
        self.export_loc_checkbox.stateChanged.connect(self.update_fields_state)
        options_layout.addWidget(self.export_loc_checkbox)
        options_layout.addSpacing(290)

        self.filter_shot = QCheckBox("Shot filter")
        options_layout.addWidget(self.filter_shot)
        options_layout.addStretch()
        block1_group_layout.addLayout(options_layout)

        # Save locators path
        save_path_label = QLabel("Save locators:")
        save_path_layout = QHBoxLayout()
        self.save_locators_path_entry = QLineEdit()
        self.save_path_btn = QPushButton("Choose")
        self.save_path_btn.clicked.connect(self.select_save_markers_file)
        save_path_layout.addWidget(self.save_locators_path_entry)
        save_path_layout.addWidget(self.save_path_btn)
        self.save_locators_path_entry.setEnabled(False)
        self.save_path_btn.setEnabled(False)

        block1_group_layout.addWidget(save_path_label)
        block1_group_layout.addLayout(save_path_layout)
        block1_group.setLayout(block1_group_layout)
        main_layout.addWidget(block1_group)

        # Converter
        block2_group = QGroupBox("Converter")
        block2_group_layout = QVBoxLayout()
        block2_group_layout.addSpacing(20)

        # Checkboxes
        checks_layout = QHBoxLayout()
        checks_layout.setAlignment(Qt.AlignLeft)
        self.offline_clips_checkbox = QCheckBox("Resolve markers to EDL_v23")
        self.create_srt_cb = QCheckBox("EDL to SRT")
        self.srt_to_edl_cb = QCheckBox("SRT to EDL")
        self.convert_edl = QCheckBox("EDL_v3 to EDL_v23")
        self.create_srt_cb.stateChanged.connect(self.update_fields_state)
        self.srt_to_edl_cb.stateChanged.connect(self.update_fields_state)
        self.convert_edl.stateChanged.connect(self.update_fields_state)
        checks_layout.addWidget(self.offline_clips_checkbox)
        checks_layout.addSpacing(30)
        checks_layout.addWidget(self.create_srt_cb)
        checks_layout.addSpacing(30)
        checks_layout.addWidget(self.srt_to_edl_cb)
        checks_layout.addSpacing(30)
        checks_layout.addWidget(self.convert_edl)
        block2_group_layout.addLayout(checks_layout)

        # Input path
        input_label = QLabel("Choose input file:")
        input_layout = QHBoxLayout()
        self.input_entry = QLineEdit()
        self.input_entry.setEnabled(False)
        self.input_btn = QPushButton("Choose")
        self.input_btn.setEnabled(False)
        self.input_btn.clicked.connect(self.select_input_file)
        input_layout.addWidget(self.input_entry)
        input_layout.addWidget(self.input_btn)
        block2_group_layout.addWidget(input_label)
        block2_group_layout.addLayout(input_layout)

        # Output path
        output_label = QLabel("Save result:")
        output_layout = QHBoxLayout()
        self.output_entry = QLineEdit()
        self.output_btn = QPushButton("Choose")
        self.output_btn.clicked.connect(self.select_output_file)
        output_layout.addWidget(self.output_entry)
        output_layout.addWidget(self.output_btn)
        block2_group_layout.addWidget(output_label)
        block2_group_layout.addLayout(output_layout)

        block2_group.setLayout(block2_group_layout)
        main_layout.addWidget(block2_group)

        # Set Name group
        set_name_group = QGroupBox("Resolve to clip names")
        set_name_group.setMinimumHeight(130)
        name_layout = QVBoxLayout()
        set_name_layout = QHBoxLayout()
        set_name_layout.addSpacing(20)
        self.from_track_label = QLabel("")
        self.from_track_cb = QCheckBox("from track:")
        self.from_track_edit = QLineEdit("1")
        self.from_track_edit.setMaximumWidth(40)
        self.from_markers_cb = QCheckBox("from timeline markers")
        set_name_layout.addWidget(self.from_track_cb)
        set_name_layout.addWidget(self.from_track_edit)
        set_name_layout.addSpacing(60)
        set_name_layout.addWidget(self.from_markers_cb)
        set_name_layout.addStretch()

        shot_name_layout =QHBoxLayout()

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
        
        name_layout.addSpacing(10)
        name_layout.addLayout(set_name_layout)
        name_layout.addWidget(self.separator_set_name)
        name_layout.addLayout(shot_name_layout)
        set_name_group.setLayout(name_layout)
        main_layout.addWidget(set_name_group)

        # Start Button
        self.run_button = QPushButton("Start")
        self.run_button.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.run_button.clicked.connect(self.run_script)
        main_layout.addWidget(self.run_button)

    def get_shot_name(self):
        self.base_shot_name = "###_####"
        result_shot_name = self.prefix.text() + ("_", "")[self.prefix.text() == ""] + self.base_shot_name + ("_", "")[self.postfix.text() == ""] + self.postfix.text() + ("", "_VT1")[self.set_track_id.isChecked()]
        self.shot_name_view.setText(result_shot_name)


    def select_input_file(self):
        file_path, _ = QFileDialog.getOpenFileName(self, "Select EDL file", "", "SRT files (*.srt);; EDL files (*.edl)")
        if file_path:
            self.input_entry.setText(file_path)

    def select_save_markers_file(self):
        file_path = QFileDialog.getExistingDirectory(self, 
                                                "Choose Shots Folder",
                                                )
        if file_path:
            self.save_locators_path_entry.setText(file_path)

    def select_output_file(self):
        file_path, _ = QFileDialog.getSaveFileName(self, "Save As", "", "SRT files (*.srt);;EDL files (*.edl));;All Files (*)")
        if file_path:
            self.output_entry.setText(file_path)

    def update_fields_state(self):
        """
        Лок/анлок полей в UI.
        """
        self.track_entry.setEnabled(self.set_markers_checkbox.isChecked())
        self.to_start_rb.setEnabled(self.set_markers_checkbox.isChecked())
        self.to_center_rb.setEnabled(self.set_markers_checkbox.isChecked())

        self.save_locators_path_entry.setEnabled(self.export_loc_checkbox.isChecked())
        self.save_path_btn.setEnabled(self.export_loc_checkbox.isChecked())

        self.input_entry.setEnabled(self.create_srt_cb.isChecked())
        self.input_btn.setEnabled(self.create_srt_cb.isChecked())

        input_enabled = self.create_srt_cb.isChecked() or self.srt_to_edl_cb.isChecked() or self.convert_edl.isChecked()
        self.input_entry.setEnabled(input_enabled)
        self.input_btn.setEnabled(input_enabled)

        self.output_entry.setEnabled(not any((self.srt_to_edl_cb.isChecked(), self.create_srt_cb.isChecked(), self.convert_edl.isChecked())))
        self.output_btn.setEnabled(not any((self.srt_to_edl_cb.isChecked(), self.create_srt_cb.isChecked(), self.convert_edl.isChecked())))

    def run_script(self):
        self.validator = ConfigValidator(self)
        self.user_config = self.validator.collect_config()

        if not self.validator.validate(self.user_config):
            self.on_error_signal("\n".join(self.validator.get_errors()))
            return

        logger.info(f"\n\nSetUp:\n{pformat(self.user_config)}\n") 

        self.main_process = LogicWorker(self, self.user_config)
        self.run_button.setEnabled(False)
        self.main_process.finished.connect(lambda : self.run_button.setEnabled(True))
        self.main_process.error_signal.connect(self.on_error_signal)
        self.main_process.success_signal.connect(self.on_success_signal)
        self.main_process.warning_signal.connect(self.on_warning_signal)
        self.main_process.info_signal.connect(self.on_info_signal)
        self.main_process.start() 

    def on_error_signal(self, message):
        QMessageBox.critical(self, "Error", message)
        logger.exception(message)
        return

    def on_success_signal(self, message):
        QMessageBox.information(self, "Success", message)
        logger.info(message)

    def on_warning_signal(self, message):
        QMessageBox.warning(self, "Warning", message)
        logger.warning(message)

    def on_info_signal(self, message):
        QMessageBox.information(self, "Info", message)
        logger.info(message)

if __name__ == '__main__':
    app = QApplication(sys.argv)
    apply_style(app)
    window = EDLProcessorGUI()
    window.show()
    sys.exit(app.exec_())
