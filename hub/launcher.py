import subprocess
import os
import sys
from PyQt5.QtWidgets import QApplication, QWidget, QPushButton, QVBoxLayout, QGroupBox, QLabel, QFrame, QHBoxLayout, QSizePolicy, QMessageBox
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QIcon
from ui.css_style import apply_style
from logger_config import get_logger

SCRIPT_DIR = os.path.join(os.path.dirname(os.path.realpath(__file__)), "..", "src")
ICON_PATH = os.path.join(os.path.dirname(os.path.realpath(__file__)), "ui", "icon.png")

logger = get_logger(__file__)

class HubApp(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Utility Hub")
        self.setWindowFlags(Qt.WindowStaysOnTopHint)
        if os.name != "posix":
            self.resize(1200, 350)
        else:
            self.resize(1450, 420)
        self.setWindowIcon(QIcon(ICON_PATH))

        #Главный горизонтальный слой
        mainlayout = QHBoxLayout()
        # Блок resolve
        resolve_box = QGroupBox("Resolve Utilities")
        # Вертикальный слой resolve
        resolve_layout = QVBoxLayout()
        resolve_layout.setAlignment(Qt.AlignTop)

        # Добавляем кнопки в resolve_layout
        row1 = self.create_button_description_row(
            button_name="Autoconfom",
            description_text="Автоматическая сборка дейлизов",
            script_name="autoconform_dailies.py"
        )
        row2 = self.create_button_description_row(
            button_name="Plate Delivery",
            description_text="Внутристудийный пайплайн выдачи плейтов из Resolve",
            script_name="exr_delivery.py"
        )
        row3 = self.create_button_description_row(
            button_name="Outsource Plate Delivery",
            description_text="Пайплайн выдачи для сторонних студий",
            script_name="exr_delivery_fd.py"
        )
        row4 = self.create_button_description_row(
            button_name="Copy Grade",
            description_text="Копирование грейда",
            script_name="copy_grade.py"
        )
        row5 = self.create_button_description_row(
            button_name="Check Shot Version",
            description_text="Сверка версий шотов",
            script_name="compare_versions.py"
        )
        row6 = self.create_button_description_row(
            button_name="Resolve Get Shot",
            description_text="Загрузка дейлизов из SG в Resolve",
            script_name="get_shot_in_dvr.py"
        )
        row7 = self.create_button_description_row(
            button_name="Render Proxy",
            description_text="Автоматический рендер прокси для монтажа",
            script_name="mxf_proxy_render.py"
        )
        row8 = self.create_button_description_row(
            button_name="OCF Color and FPS",
            description_text="Установка проектного FPS и цвета для исходников по их разрешению",
            script_name="ocf_set_source_color.py"
        )
        row10 = self.create_button_description_row(
            button_name="EDL Processor",
            description_text="Хаб для работы с маркерами и EDL",
            script_name="loc_offline_edl_utility.py"
        )
        row11 = self.create_button_description_row(
            button_name="Find Source",
            description_text="Поиск исходника и добавление его на таймлайн",
            script_name="find_clip_by_tc.py"
        )

        resolve_layout.addLayout(row1)
        resolve_layout.addLayout(row2)
        resolve_layout.addLayout(row3)
        resolve_layout.addLayout(row4)
        resolve_layout.addLayout(row5)
        resolve_layout.addLayout(row6)
        resolve_layout.addLayout(row7)
        resolve_layout.addLayout(row8)
        resolve_layout.addLayout(row10)
        resolve_layout.addLayout(row11)

        resolve_box.setLayout(resolve_layout)
        resolve_box.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Expanding)

        # Блок others
        other_box = QGroupBox("Other Utilities")
        # Вертикальный слой others
        other_layout = QVBoxLayout()
        resolve_layout.setAlignment(Qt.AlignTop)

        # Добавляем кнопки в others_layout
        other_box = QGroupBox("Other Utilities")
        other_layout = QVBoxLayout()
        other_layout.setAlignment(Qt.AlignTop)  # Тоже выравнивание по верху

        row20 = self.create_button_description_row(
            button_name="Project Folders Structure",
            description_text="Установка структуры папок в системных дисках, Resolve и Avid",
            script_name="project_structure.py"
        )
        row21 = self.create_button_description_row(
            button_name="Get Sequence N-frame",
            description_text="Получение каждого n-ного кадра в секвенции",
            script_name="get_every_n_frame.py"
        )
        row22 = self.create_button_description_row(
            button_name="Excel data to locators",
            description_text="Конвертация расшота из Excel в локаторы для Avid",
            script_name="excel_to_locs.py"
        )
        row23 = self.create_button_description_row(
            button_name="EDL Filter",
            description_text="Фильтрация EDL-файла по списку запрашиваемых номеров шотов",
            script_name="edl_filter.py"
        )
        row24 = self.create_button_description_row(
            button_name="Edit Database",
            description_text="База данных проектов + функционал работы с монтажами шотов",
            script_name="edit_database.py"
        )
        other_layout.addLayout(row20)
        other_layout.addLayout(row21)
        other_layout.addLayout(row22)
        other_layout.addLayout(row23)
        other_layout.addLayout(row24)

        other_box.setLayout(other_layout)
        other_box.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Expanding)

        # Добавляем обе колонки в горизонтальный layout
        mainlayout.addWidget(resolve_box)
        mainlayout.addWidget(other_box)

        self.setLayout(mainlayout)

    def create_button_description_row(self, button_name, description_text, script_name):
        row_layout = QHBoxLayout()

        #Кнопка
        button = QPushButton(button_name)
        button.clicked.connect(lambda: self.run_script(script_name))

        # Вертикальный разделитель
        vline = QFrame()
        vline.setFrameShape(QFrame.VLine)
        vline.setFrameShadow(QFrame.Sunken)

        # Описание
        description = QLabel(description_text)
        description.setWordWrap(True)

        # Добавляем всё в строку
        row_layout.addWidget(button)
        row_layout.addWidget(vline)
        row_layout.addWidget(description)

        return row_layout

    def run_script(self, script_name):
        script_path = os.path.join(SCRIPT_DIR, script_name)
        try:
            subprocess.Popen([sys.executable, script_path])
            logger.debug(f"Запускаю: {script_path}")
        except Exception as e:
            QMessageBox.critical(f"Ошибка запуска скрипта {script_name}: {e}")
            logger.exception(f"Ошибка запуска скрипта {script_name}: {e}")



if __name__ == "__main__":
    app = QApplication(sys.argv)
    apply_style(app)
    hub = HubApp()
    hub.show()
    sys.exit(app.exec_())



