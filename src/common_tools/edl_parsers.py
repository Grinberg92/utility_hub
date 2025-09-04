import re
from dataclasses import dataclass
from timecode import Timecode as tc

class EDLParser_v23:
    """
    Класс-итератор. Итерируется по EDL файлу, обрабатывая строки с ретаймом (M2).
    """
    @dataclass
    class EDLEntry:
        """
        Класс-контейнер для данных из строки EDL.
        """
        edl_record_id: str
        edl_shot_name: str
        edl_track_type: str
        edl_transition: str
        edl_source_in: str
        edl_source_out: str
        edl_record_in: str
        edl_record_out: str 
        retime: bool

    def __init__(self, fps, edl_path=None, lines=None):
        self.edl_path = edl_path
        self._lines = lines
        self.fps = fps

    def convert(self, source_in, record_in, record_out) -> str:
        """
        Высчитывает на основе входящих таймкодов end source timecode для шотов с ретаймом.
        """
        record_duration = tc(self.fps, record_out).frames - tc(self.fps, record_in).frames 
        end_source_tc_frames = (tc(self.fps, source_in).frames) + record_duration
        end_source_tc_timecode = tc(self.fps, frames=end_source_tc_frames)

        return str(end_source_tc_timecode)
    
    def is_retime(self, data) -> bool:
        """
        Метод определения ретайма.
        На случай, если в EDL нет маркера ретайма "M2".
        """
        edl_source_in=tc(self.fps, data[4]).frames
        edl_source_out=tc(self.fps, data[5]).frames
        edl_record_in=tc(self.fps, data[6]).frames
        edl_record_out=tc(self.fps, data[7]).frames

        if edl_record_out - edl_record_in != edl_source_out - edl_source_in:
            return True

    def __iter__(self):
        if self._lines is not None:
            lines = self._lines
        else:    
            with open(self.edl_path, 'r') as edl_file:
                lines = edl_file.readlines()

        i = 0
        while i < len(lines):
            line = lines[i].strip()

            if re.match(r'^\d+\s', line):
                parts = line.split()
                if len(parts) < 8:
                    i += 1
                    continue

                retime_val = False
                j = i + 1

                while j < len(lines):
                    next_line = lines[j].strip()
                    if re.match(r'^\d+\s', next_line): 
                        break
                    if next_line.startswith("M2"):
                        retime_val = True
                    j += 1

                if retime_val or self.is_retime(parts):
                    parts[5] = self.convert(parts[4], parts[6], parts[7])
                    retime_val = True

                yield self.EDLEntry(
                    edl_record_id=parts[0],
                    edl_shot_name=parts[1],
                    edl_track_type=parts[2],
                    edl_transition=parts[3],
                    edl_source_in=parts[4],
                    edl_source_out=parts[5],
                    edl_record_in=parts[6],
                    edl_record_out=parts[7],
                    retime=retime_val
                )
                i = j
            else:
                i += 1


class EDLParser_v3:
    """
    Класс-итератор. Итерирует EDL-файл, возвращая только те пары,
    где есть строка данных (000xxx) и соответствующая *LOC строка.
    """

    @dataclass
    class EDLEntry:
        """
        Класс-контейнер для данных из двух строк EDL
        """
        edl_record_id: str
        edl_shot_name: str
        edl_track_type: str
        edl_transition: str
        edl_source_in: str
        edl_source_out: str
        edl_record_in: str
        edl_record_out: str
        retime: bool  

    def __init__(self, fps, edl_path=None, lines=None):
        self.edl_path = edl_path
        self._lines = lines
        self.fps = fps

    def convert(self, source_in, record_in, record_out) -> str:
        """
        Высчитывает на основе входящих таймкодов end source timecode для шотов с ретаймом.
        """
        record_duration = tc(self.fps, record_out).frames - tc(self.fps, record_in).frames 
        end_source_tc_frames = (tc(self.fps, source_in).frames) + record_duration
        end_source_tc_timecode = tc(self.fps, frames=end_source_tc_frames)

        return str(end_source_tc_timecode)
    
    def is_retime(self, data) -> bool:
        """
        Метод определения ретайма.
        На случай, если в EDL нет маркера ретайма "M2".
        """
        edl_source_in=tc(self.fps, data[4]).frames
        edl_source_out=tc(self.fps, data[5]).frames
        edl_record_in=tc(self.fps, data[6]).frames
        edl_record_out=tc(self.fps, data[7]).frames

        if edl_record_out - edl_record_in != edl_source_out - edl_source_in:
            return True

    def __iter__(self):
        if self._lines is not None:
            lines = self._lines
        else:    
            with open(self.edl_path, 'r') as edl_file:
                lines = edl_file.readlines()

        i = 0
        while i < len(lines):
            line = lines[i].strip()

            if re.match(r'^\d+\s', line):  # Найдена основная запись
                parts = line.split()
                if len(parts) < 8:
                    i += 1
                    continue

                # Ищем LOC и M2 между текущей и следующей основной строкой
                shot_name = None
                retime_val = False
                j = i + 1
                while j < len(lines):
                    next_line = lines[j].strip()

                    if re.match(r'^\d+\s', next_line):  # Следующий блок
                        break

                    if next_line.startswith("M2"):
                        retime_val = True

                    loc_match = re.search(r'^\*LOC.*\s+(\S+)$', next_line)
                    if loc_match:
                        shot_name = loc_match.group(1)

                    j += 1

                if shot_name:
                    if retime_val or self.is_retime(parts):
                        parts[5] = self.convert(parts[4], parts[6], parts[7])
                        retime_val = True

                    yield self.EDLEntry(
                        edl_record_id=parts[0],
                        edl_shot_name=shot_name,
                        edl_track_type=parts[2],
                        edl_transition=parts[3],
                        edl_source_in=parts[4],
                        edl_source_out=parts[5],
                        edl_record_in=parts[6],
                        edl_record_out=parts[7],
                        retime=retime_val,
                    )
                i = j  # Продвигаемся к следующему блоку
            else:
                i += 1

class EDLParser_Hiero:
    """
    Итерирует EDL, возвращая пары:
    - основная строка с таймкодами
    - строка '*FROM CLIP NAME:' с именем шота
    """

    @dataclass
    class EDLEntry:
        edl_record_id: str
        edl_shot_name: str
        edl_track_type: str
        edl_transition: str
        edl_source_in: str
        edl_source_out: str
        edl_record_in: str
        edl_record_out: str
        retime: bool

    def __init__(self, fps, edl_path=None, lines=None):
        self.edl_path = edl_path
        self._lines = lines
        self.fps = fps

    def convert(self, source_in, record_in, record_out) -> str:
        """
        Высчитывает на основе входящих таймкодов end source timecode для шотов с ретаймом.
        """
        record_duration = tc(self.fps, record_out).frames - tc(self.fps, record_in).frames
        end_source_tc_frames = tc(self.fps, source_in).frames + record_duration
        end_source_tc_timecode = tc(self.fps, frames=end_source_tc_frames)
        return str(end_source_tc_timecode)

    def is_retime(self, data) -> bool:
        """
        Метод определения ретайма.
        На случай, если в EDL нет маркера ретайма "M2".
        """
        edl_source_in = tc(self.fps, data[4]).frames
        edl_source_out = tc(self.fps, data[5]).frames
        edl_record_in = tc(self.fps, data[6]).frames
        edl_record_out = tc(self.fps, data[7]).frames
        return (edl_record_out - edl_record_in) != (edl_source_out - edl_source_in)

    def __iter__(self):
        if self._lines is not None:
            lines = self._lines
        else:
            with open(self.edl_path, 'r', encoding="utf-8") as edl_file:
                lines = edl_file.readlines()

        i = 0
        while i < len(lines):
            line = lines[i].strip()

            if re.match(r'^\d+\s', line):
                parts = line.split()
                if len(parts) < 8:
                    i += 1
                    continue

                shot_name = None
                retime_val = False
                j = i + 1
                while j < len(lines):
                    next_line = lines[j].strip()

                    if re.match(r'^\d+\s', next_line):
                        break

                    if next_line.startswith("M2"):
                        retime_val = True

                    clip_match = re.search(r'^\*FROM CLIP NAME:\s+(\S+)$', next_line, re.IGNORECASE)
                    if clip_match:
                        shot_name = clip_match.group(1)

                    j += 1

                if shot_name:
                    if retime_val or self.is_retime(parts):
                        parts[5] = self.convert(parts[4], parts[6], parts[7])
                        retime_val = True

                    yield self.EDLEntry(
                        edl_record_id=parts[0],
                        edl_shot_name=shot_name,
                        edl_track_type=parts[2],
                        edl_transition=parts[3],
                        edl_source_in=parts[4],
                        edl_source_out=parts[5],
                        edl_record_in=parts[6],
                        edl_record_out=parts[7],
                        retime=retime_val,
                    )
                i = j
            else:
                i += 1

class EDLParser_Resolve:
    """
    Итерирует EDL, возвращая пары:
    - основная строка с таймкодами
    - строка '*FROM CLIP NAME:' с именем шота
    """

    @dataclass
    class EDLEntry:
        edl_record_id: str
        edl_source_name: str
        edl_shot_name: str
        edl_track_type: str
        edl_transition: str
        edl_source_in: str
        edl_source_out: str
        edl_record_in: str
        edl_record_out: str
        retime: bool
        edl_edit_name: str

    def __init__(self, fps, edl_path=None, lines=None):
        self.edl_path = edl_path
        self._lines = lines
        self.fps = fps

    def is_retime(self, data) -> bool:
        """
        Метод определения ретайма.
        На случай, если в EDL нет маркера ретайма "M2".
        """
        edl_source_in = tc(self.fps, data[4]).frames
        edl_source_out = tc(self.fps, data[5]).frames
        edl_record_in = tc(self.fps, data[6]).frames
        edl_record_out = tc(self.fps, data[7]).frames
        return (edl_record_out - edl_record_in) != (edl_source_out - edl_source_in)

    def __iter__(self):
        if self._lines is not None:
            lines = self._lines
        else:
            with open(self.edl_path, 'r', encoding="utf-8") as edl_file:
                lines = edl_file.readlines()

        edit_name = lines[0].strip().split(":")[1].strip() # Отрезаем слово 'TITLE'

        i = 0
        while i < len(lines):
            line = lines[i].strip()

            if re.match(r'^\d+\s', line):
                parts = line.split()
                if len(parts) < 8:
                    i += 1
                    continue

                shot_name = None
                retime_val = False
                j = i + 1
                # проходим все дополнительные строки блока
                while j < len(lines):
                    next_line = lines[j].strip()

                    if re.match(r'^\d+\s', next_line):
                        break  # новая основная строка → конец блока

                    if next_line.startswith("M2"):
                        retime_val = True

                    clip_match = re.search(r'^\*\s*FROM CLIP NAME:\s*(.+)$', next_line, re.IGNORECASE)
                    if clip_match:
                        shot_name = clip_match.group(1).strip()

                    j += 1

                # проверяем ретайм после обработки всего блока
                if retime_val or self.is_retime(parts):
                    retime_val = True

                yield self.EDLEntry(
                    edl_record_id=parts[0],
                    edl_source_name=parts[1],
                    edl_shot_name=shot_name,
                    edl_track_type=parts[2],
                    edl_transition=parts[3],
                    edl_source_in=parts[4].strip(),
                    edl_source_out=parts[5].strip(),
                    edl_record_in=parts[6].strip(),
                    edl_record_out=parts[7].strip(),
                    retime=retime_val,
                    edl_edit_name=edit_name,
                )

                i = j  # переходим к следующей основной строке
            else:
                i += 1

def detect_edl_parser(fps, edl_path=None, lines=None):
    """
    Определяем тип EDL файла по содержимому файла.

    :param lines: Список со строками из EDL.
    :return: Класс EDL парсера
    """
    if lines is not None:
        for string in lines:
            if "*loc" in string.lower():
                return EDLParser_v3(fps, lines=lines)
            if "*from clip name" in string.lower():
                return EDLParser_Hiero(fps, lines=lines)
        return EDLParser_v23(fps, lines=lines)
        
    elif edl_path is not None:
        with open(edl_path, "r", encoding="utf-8") as f:
            for string in f:
                if "*loc" in string.lower():
                    return EDLParser_v3(fps, edl_path=edl_path)
                if "*from clip name" in string.lower():
                    return EDLParser_Hiero(fps, edl_path=edl_path)
            return EDLParser_v23(fps, edl_path=edl_path)