import re
from dataclasses import dataclass


class EDLParser_v23:
    """
    Класс-итератор. Итерируется по EDL файлу.
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

    def __init__(self, edl_path, lines=None):
        self.edl_path = edl_path
        self._lines = lines

    def __iter__(self):
        if self._lines is not None:
            lines = self._lines
        else:    
            with open(self.edl_path, 'r') as edl_file:
                lines = edl_file.readlines()

            for line in lines:
                if re.search(r'^\d+\s', line.strip()):
                    yield self.parse_line(line)  # Паттерн ищет значения 001, 0001 и т.д. по началу строки

    def parse_line(self, line):
        """
        Метод парсит строку на значения через класс EDLEntry.
        """
        parts = line.split()
        return self.EDLEntry(
                    edl_record_id=parts[0],
                    edl_record_in=parts[6],
                    edl_record_out=parts[7],
                    edl_track_type=parts[2],
                    edl_transition=parts[3],
                    edl_shot_name=parts[1],
                    edl_source_out=parts[5],
                    edl_source_in=parts[4],
                    retime=False 
                    )

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

    def __init__(self, edl_path=None, lines=None):
        self.edl_path = edl_path
        self._lines = lines

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
