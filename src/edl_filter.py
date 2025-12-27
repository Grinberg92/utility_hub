import sys
import os
from collections import Counter
from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QLineEdit, QTextEdit, QPushButton, QFileDialog, QMessageBox
)
from PyQt5.QtCore import Qt
from dvr_tools.css_style import apply_style
from dvr_tools.logger_config import get_logger
from common_tools.edl_parsers import detect_edl_parser, EDLParser

logger = get_logger(__file__)

def create_output_edl(shot: EDLParser, output) -> None:
    """
    Метод формирует аутпут файл в формате, пригодном для отображения оффлайн клипов в Resolve и AVID.

    :param output: Файловый объект.
    """
    str1 = (f"{shot.edl_record_id} {shot.edl_shot_name} "
            f"{shot.edl_track_type} {shot.edl_transition} "
            f"{shot.edl_source_in} {shot.edl_source_out} "
            f"{shot.edl_record_in} {shot.edl_record_out}")
    str2 = f'\n* FROM CLIP NAME: {shot.edl_shot_name}\n'
    output.write(str1)
    output.write(str2)

def filter_edl(self, edl_path: str, input_shots: list[str], fps: int) -> str:
    """
    Пересобирает шоты в EDL при нахождении их в списке input_shots.
    """
    logger.info("Start process")
    edl_parser = detect_edl_parser(fps, edl_path=edl_path)

    edl_shot_names = Counter([i.edl_shot_name for i in edl_parser]) # Словарь имен шотов из EDL

    edl_shot_data = [i for i in edl_parser] # Объекты EDL парсера в списке

    input_shots_data = Counter(input_shots) # Словарь имен шотов из инпута

    base, ext = os.path.splitext(self.edl_path)
    output_path = base + "_filtered" + ext
    logger.info(f"Output: {output_path}")

    # Поиск шота из EDL в списке input_shots
    with open(output_path, "w", encoding="utf-8") as _:
        pass

    for shot_data in edl_shot_data:
        with open(output_path, "a", encoding="utf-8") as f:
            if shot_data.edl_shot_name in input_shots_data: 
                create_output_edl(shot_data, f)
    
    # Поиск шотов отсутствующих в EDL
    not_found_shots = []
    for input_shot in input_shots_data:
        if input_shot not in edl_shot_names:
            not_found_shots.append(f"В EDL отсутствует шот {input_shot}")
    if not_found_shots:
        self.log.append("\n".join(not_found_shots))
        return True

    return True

class EDLFilterApp(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("EDL Filter")
        self.setWindowFlag(Qt.WindowStaysOnTopHint)
        self.resize(600, 200)

        self.fps = 24
        central = QWidget()
        self.setCentralWidget(central)
        layout = QVBoxLayout(central)

        # Choose EDL
        file_layout = QHBoxLayout()
        self.file_edit = QLineEdit()
        file_btn = QPushButton("Choose")
        file_btn.clicked.connect(self.choose_file)
        file_layout.addWidget(QLabel("EDL path:"))
        file_layout.addWidget(self.file_edit)
        file_layout.addWidget(file_btn)
        layout.addLayout(file_layout)

        # Exclude names
        self.ids_edit = QTextEdit()
        self.ids_edit.setPlaceholderText("Input shot name (separated by a space or from new string)")
        self.ids_edit.setFixedHeight(300)
        layout.addWidget(QLabel("Shot names to get:"))
        layout.addWidget(self.ids_edit)

        filter_btn = QPushButton("Start")
        filter_btn.clicked.connect(self.run_filter)
        layout.addWidget(filter_btn)

        self.log = QTextEdit()
        self.log.setPlaceholderText("Errors log")
        self.log.setReadOnly(True)
        layout.addWidget(self.log)

        self.edl_text = ""
        self.edl_path = ""

    def choose_file(self):
        path, _ = QFileDialog.getOpenFileName(self, "Choose EDL", "", "EDL Files (*.edl *.txt)")
        if path:
            self.file_edit.setText(path)
            self.edl_path = path

    def run_filter(self):
        if not self.edl_path:
            QMessageBox.warning(self, "Warning", "Не выбран EDL файл")
            logger.warning("Не выбран EDL файл")
            return
        
        else:
            if not os.path.exists(self.edl_path):
                QMessageBox.warning(self, "Warning", "Указан несуществующий путь к EDL файлу")
                logger.warning("Указан несуществующий путь к EDL файлу")
                return
        
        if not self.ids_edit.toPlainText().strip():
            QMessageBox.warning(self, "Warning", "Добавьте шоты в input shot names")
            logger.warning("Добавьте шоты в input shot names")
            return

        ids_raw = self.ids_edit.toPlainText().strip()
        input_ids = ids_raw.replace(",", " ").split()
        result = filter_edl(self, self.edl_path, input_ids, self.fps)
        if result:
            QMessageBox.information(self, "Success", f"Файл успешно создан")
            logger.info(f"Файл успешно создан")
        else:
            QMessageBox.critical(self, "Error", f"Ошибка создания файла")
            logger.error(f"Ошибка создания файла")

if __name__ == "__main__":
    app = QApplication(sys.argv)
    apply_style(app)
    win = EDLFilterApp()
    win.show()
    sys.exit(app.exec_())
