import subprocess
import os
import sys
from PyQt5.QtWidgets import QApplication, QWidget, QPushButton, QVBoxLayout, QGroupBox, QLabel, QFrame, QHBoxLayout, QSizePolicy
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QIcon

SCRIPT_DIR = os.path.join(os.path.dirname(os.path.realpath(__file__)), "..", "src")
ICON_PATH = os.path.join(os.path.dirname(os.path.realpath(__file__)), "ui", "icon.png")

class HubApp(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Utility Hub")
        self.setGeometry(200, 200, 900, 350)
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
            description_text="Автоматическая сборка дейлизов (EXR, JPG)",
            script_name="autoconform_dailies_EXR_JPG.py"
        )
        row2 = self.create_button_description_row(
            button_name="Exr delivery",
            description_text="Автоматический рендер EXR",
            script_name="exr_delivery.py"
        )
        row3 = self.create_button_description_row(
            button_name="Copy Grade",
            description_text="Копирование грейда",
            script_name="copy_grade.py"
        )
        row4 = self.create_button_description_row(
            button_name="Shot Versions",
            description_text="Получение отчета об актуальности версий шотов",
            script_name="compare_versions.py"
        )
        row5 = self.create_button_description_row(
            button_name="Get Shot",
            description_text="Загрузка дейлизов в медиапул",
            script_name="get_shot_in_dvr.py"
        )
        row6 = self.create_button_description_row(
            button_name="Render MXF Proxy",
            description_text="Автоматический рендер MXF прокси для Avid",
            script_name="mxf_proxy_render.py"
        )
        row7 = self.create_button_description_row(
            button_name="OCF Color and FPS",
            description_text="Установка проектного FPS и цвета для исходников по их разрешению",
            script_name="ocf_set_source_color.py"
        )
        row8 = self.create_button_description_row(
            button_name="Name from Offline",
            description_text="Установка имени оффлайн клипа в атрибут клипа на таймлайне",
            script_name="set_name_from_offline.py"
        )
        row9 = self.create_button_description_row(
            button_name="Additional Programs",
            description_text="Хаб для работы с маркерами и созданием EDL",
            script_name="loc_offline_edl_utility.py"
        )

        resolve_layout.addLayout(row1)
        resolve_layout.addLayout(row2)
        resolve_layout.addLayout(row3)
        resolve_layout.addLayout(row4)
        resolve_layout.addLayout(row5)
        resolve_layout.addLayout(row6)
        resolve_layout.addLayout(row7)
        resolve_layout.addLayout(row8)
        resolve_layout.addLayout(row9)


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
            description_text="Установка структуры папок в системных дисках, resolve и avid",
            script_name="project_structure.py"
        )
        row21 = self.create_button_description_row(
            button_name="Get Sequence N-frame",
            description_text="Получение каждого n-ного кадра в секвенции",
            script_name="get_every_n_frame.py"
        )

        other_layout.addLayout(row20)
        other_layout.addLayout(row21)

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
        print(f"Запускаю: {script_path}")
        try:
            subprocess.Popen([sys.executable, script_path])
            print(sys.executable)
        except Exception as e:
            print(f"Ошибка запуска скрипта {script_name}: {e}")



if __name__ == "__main__":
    app = QApplication(sys.argv)
    hub = HubApp()
    hub.show()
    sys.exit(app.exec_())



