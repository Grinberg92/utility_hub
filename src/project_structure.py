import os
import re
import sys
import shutil
import DaVinciResolveScript as dvr
from datetime import date
from PyQt5.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QHBoxLayout, QRadioButton, QLabel,
    QComboBox, QLineEdit, QPushButton, QSpinBox, QGroupBox, QCheckBox,
    QMessageBox, QFileDialog
)
from PyQt5.QtCore import Qt
from dvr_tools.logger_config import get_logger
from dvr_tools.css_style import apply_style
from dvr_tools.resolve_utils import ResolveObjects

logger = get_logger(__file__)

REEL_PRESET = "reel_settings_preset"

FILE_COPY_SOURCE = r"\\stor-di-2\arch\000_FOR_EDITORS\Patterns\AVID\AVID_PROJ\bins_to_AVID_PROJ"

FILE_COPY_MAP = {
    "_edit_CURRENT.avb": "04_EDIT",
    "01_takes_for_VFX.avb": "02_CG",
    "02_Animatic.avb": "02_CG",
    "03_ANIMA.avb": "02_CG",
    "04_COMP.avb": "02_CG",
    "05_ALL_VFX_Conform.avb": "02_CG",
    "Preview_202508.avb": "07_PREVIEW_ROOM",
    "skv_Mclp.avb": os.path.join("01_DI", "002_SKV"),
    "skv_Sublclp.avb": os.path.join("01_DI", "002_SKV"),
    "T1_edit.avb": os.path.join("05_TRAILERS", "T1"),
    "T2_edit.avb": os.path.join("05_TRAILERS", "T2"),
}

J_SRTUCTURE = [
    "J:/001_sources",
    "J:/002_edits",
    "J:/003_transcode_to_vfx",
    "J:/004_masters"
]
R_STRUCTURE = "R:/"

STRUCTURE_001_FOLDER = {
    "01_ocf": {},
    "02_trims": {},
    "03_cc_trims": {},
    "04_shots": {},
    "05_restore": {}
}
STRUCTURE_004_MASTERS = {
    "01_tmp": {},
    "02_printmasters": {
        "Edit_name": {
            "1_DCP": {},
            "2_INET": {}, 
            "3_TV": {
                "24": {},
                "25": {}
            }, 
            "4_SOUND": {}, 
            "5_TXT": {}
        }
    },
    "03_add_masters": {
        "1_GFF": {}, 
        "2_STILLS": {}, 
        "3_TRIM": {}
    },
    "04_proj": {
        "1_Davinchi_proj": {},
          "2_AVID_proj": {}, 
          "3_LUTs": {}, 
          "4_Davinchi_base_backup": {}
    }
}
R_FOLDER_STRUCTURE = {
    "CC_OUT": {}, 
    "TO_CC": {}, 
    "TRIM": {}, 
    "VFX": {}
}

AVID_FOLDER_STRUCTURE = {
    "01_DI": {
        "001_OCF": {},
        "002_SKV": {}
    },
    "02_CG": {
        "06_RasShot": {}
    },
    "03_SOUND": {
        "001_Original_Stage_Sound": {},
        "002_MUSIC": {},
        "003_SFX": {},
        "004_ADR": {},
        "005_MIX": {}
    },
    "04_EDIT": {
        "001_SCENES": {},
        "002_Assistant_CUT": {},
        "003_Directors_CUT": {},
        "004_Editor_CUT": {},
        "005_Producer_CUT": {}
    },
    "05_TRAILERS": {
        "T1": {},
        "T2": {}
    },
    "06_MASTER": {},
    "07_PREVIEW_ROOM": {}
}

RESOLVE_OCF_FOLDER = {
    "001_OCF": {},
    "002_EDIT": {},
    "003_TO_VFX": {}, 
    "004_TO_CC": {}, 
    "005_SCREENING": {}, 
    "006_TMP": {}
    }

RESOLVE_REEL_FOLDER = {
    "001_SRC": {},
    "002_TIMELINES": {},
    "003_VFX": {
        "CURRENT_DAY": {}
    },
    "004_EDIT_REF": {
        "SOUND_MIX": {}
    },
    "005_TITLES": {},
    "006_MASKS": {},
    "007_TMP": {}
}

class MainWindow(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Project Structure Creator")
        self.setWindowFlag(Qt.WindowStaysOnTopHint)
        self.resize(460, 280)
        self.setup_ui()

    def setup_ui(self):
        layout = QVBoxLayout()

        # Mode selection
        mode_layout = QHBoxLayout()
        mode_layout.addStretch() 

        self.explorer_radio = QRadioButton("Explorer")
        self.resolve_radio = QRadioButton("Resolve")
        self.avid_radio = QRadioButton("Avid")
        self.explorer_radio.setChecked(True)

        mode_layout.addWidget(self.explorer_radio)
        mode_layout.addSpacing(60)  
        mode_layout.addWidget(self.resolve_radio)
        mode_layout.addSpacing(60)  
        mode_layout.addWidget(self.avid_radio)

        mode_layout.addStretch() 

        layout.addLayout(mode_layout)

        # Explorer group
        self.explorer_group = QGroupBox("Explorer Options")
        explorer_layout = QVBoxLayout()
        disk_row = QHBoxLayout()
        disk_row.addWidget(QLabel("Disk:"))
        disk_row.addSpacing(15)
        self.disk_selector = QComboBox()
        self.disk_selector.addItems(["J", "R"])
        self.disk_selector.setMinimumWidth(100)
        disk_row.addWidget(self.disk_selector)
        disk_row.addStretch()
        explorer_layout.addLayout(disk_row)

        name_row = QHBoxLayout()
        name_row.addWidget(QLabel("Project:"))
        self.explorer_project_name = QLineEdit()
        self.explorer_project_name.setPlaceholderText("Project name")
        self.explorer_project_name.setMinimumWidth(200)
        name_row.addWidget(self.explorer_project_name)
        explorer_layout.addLayout(name_row)
        self.explorer_group.setLayout(explorer_layout)
        layout.addWidget(self.explorer_group)

        # Resolve group
        self.resolve_group = QGroupBox("Resolve Options")
        resolve_layout = QVBoxLayout()

        type_row = QHBoxLayout()
        self.type_combo = QLabel("Type:")
        type_row.addWidget(self.type_combo)
        type_row.addSpacing(12)
        self.type_selector = QComboBox()
        self.type_selector.addItems(["OCF", "REEL"])
        self.type_selector.setMinimumWidth(100)
        type_row.addWidget(self.type_selector)
        type_row.addSpacing(30)
        self.add_proj_folder = QCheckBox("Add project folder")
        self.add_proj_folder.setChecked(True)
        type_row.addWidget(self.add_proj_folder)
        resolve_layout.addLayout(type_row)

        reels_row = QHBoxLayout()
        reels_row.addWidget(QLabel("Reels:"))
        reels_row.addSpacing(10)
        self.reels_input = QSpinBox()
        self.reels_input.setRange(1, 20)
        reels_row.addWidget(self.reels_input)
        resolve_layout.addLayout(reels_row)

        project_row = QHBoxLayout()
        project_row.addWidget(QLabel("Project:"))
        self.resolve_project_name = QLineEdit()
        self.resolve_project_name.setPlaceholderText("Project name")
        self.resolve_project_name.setMinimumWidth(200)
        project_row.addWidget(self.resolve_project_name)
        resolve_layout.addLayout(project_row)
        type_row.addStretch()
        reels_row.addStretch()

        self.resolve_group.setLayout(resolve_layout)
        layout.addWidget(self.resolve_group)

        # Avid group
        self.avid_group = QGroupBox("Avid Options")
        avid_layout = QHBoxLayout()
        self.avid_path_label = QLineEdit()
        self.avid_path_label.setMinimumWidth(200)

        self.avid_path_button = QPushButton("Choose")
        avid_layout.addWidget(QLabel("Path:"))
        avid_layout.addSpacing(15)
        avid_layout.addWidget(self.avid_path_label)
        avid_layout.addWidget(self.avid_path_button)

        self.avid_group.setLayout(avid_layout)
        layout.addWidget(self.avid_group)

        # Create button
        self.create_button = QPushButton("Start")
        layout.addWidget(self.create_button)

        self.setLayout(layout)
        self.setup_connections()
        self.update_ui()

    def select_avid_path(self):
        path = QFileDialog.getExistingDirectory(self, "Выберите папку для Avid проекта")
        if path:
            self.avid_selected_path = path
            self.avid_path_label.setText(path)
        else:
            self.avid_selected_path = None

    def setup_connections(self):
        self.explorer_radio.toggled.connect(self.update_ui)
        self.resolve_radio.toggled.connect(self.update_ui)
        self.avid_path_button.clicked.connect(self.select_avid_path)
        self.type_selector.currentTextChanged.connect(self.update_ui)
        self.create_button.clicked.connect(self.run)

    def update_ui(self):
        is_explorer = self.explorer_radio.isChecked()
        is_resolve = self.resolve_radio.isChecked()
        is_avid = self.avid_radio.isChecked()

        self.explorer_group.setEnabled(is_explorer)
        self.resolve_group.setEnabled(is_resolve)
        self.avid_group.setEnabled(is_avid)

        is_reel = self.type_selector.currentText() == "REEL"
        self.reels_input.setEnabled(is_reel)

    def on_error_signal(self, message):
        QMessageBox.critical(self, "Ошибка", message)
        logger.exception(message)
        return
    
    def on_warning_signal(self, message):
        QMessageBox.warning(self, "Предупреждение", message)
        logger.warning(message)
        return

    def on_success_signal(self, message):
        QMessageBox.information(self, "Успех", message)
        logger.info(message)

    def run(self):
        """
        Метод запуска целевой логики.
        """
        if self.explorer_radio.isChecked():
            disk = self.disk_selector.currentText()
            project_name = self.explorer_project_name.text().strip()
            if not project_name:
                self.on_warning_signal("Пожалуйста, укажите имя проекта для Explorer.")
                return

            if disk == "J":
                for folder in J_SRTUCTURE:
                    self.set_creation_logic(project_name, folder)
                self.on_success_signal("Структура папок на диске J:/ успешно создана")
            else:
                self.set_creation_logic(project_name, R_STRUCTURE)
                self.on_success_signal("Структура папок на диске R:/ успешно создана")

        elif self.resolve_radio.isChecked():

            type_proj = self.type_selector.currentText()
            project_name = self.resolve_project_name.text().strip()

            if not project_name:
                self.on_warning_signal("Пожалуйста, укажите имя проекта для Resolve.")
                return

            reels = self.reels_input.value()
            self.create_resolve_structure(project_name, type_proj, reels)
            self.on_success_signal("Структура папок в Resolve успешно создана")

        elif self.avid_radio.isChecked():
            if not hasattr(self, 'avid_selected_path') or not self.avid_selected_path:
                self.on_warning_signal("Пожалуйста, выберите путь для Avid структуры.")
                return

            self.create_avid_structure(self.avid_selected_path)
            self.on_success_signal("Структура папок в Avid успешно создана")

    # Методы исполняющие создание фолдеров
    def create_folder_structure(self, structure, base_path):
        """
        Метод рекурсивно создает папки из дерева structure в проекте Resolve.

        :param structure: Структура вложенных папок представленная в виде словаря. 
        """
        try:
            for folder, subfolders in structure.items():
                folder_path = os.path.join(base_path, folder)
                os.makedirs(folder_path, exist_ok=True)
                if subfolders:
                    self.create_folder_structure(subfolders, folder_path)
        except Exception as e:
            self.on_error_signal(f"Не удалось создать структуру папок {base_path}")

    def copy_files(self, mapping, base_path, source_path):
        """
        Копирует .avb файлы в целевые папки.
        
        :param mapping: словарь {имя .avb файла: относительный_путь_в_AVID_STRUCTURE}
        :param source_path: Корневая папка с копируемыми .avb
        """
        for filename, target_rel_path in mapping.items():
            src_file = os.path.join(source_path, filename)
            dst_dir = os.path.join(base_path, target_rel_path)
            
            if not os.path.exists(src_file):
                self.on_warning_signal(f"Файл {src_file} не найден. Пропуск...")
                continue

            os.makedirs(dst_dir, exist_ok=True)
            dst_file = os.path.join(dst_dir, os.path.basename(src_file))
            
            try:
                if os.path.isdir(src_file):
                    # копируем папку
                    if os.path.exists(dst_file):
                        shutil.rmtree(dst_file)
                    shutil.copytree(src_file, dst_file)
                else:
                    # копируем файл
                    shutil.copy2(src_file, dst_file)
            except Exception as e:
                self.on_error_signal(f"Ошибка при копировании {src_file} → {dst_dir}: {str(e)}")

    def create_avid_structure(self, base_path):
        """
        Создание структуры папок для Avid проекта.
        """
        os.makedirs(base_path, exist_ok=True)

        self.create_folder_structure(AVID_FOLDER_STRUCTURE, base_path)

        self.copy_files(FILE_COPY_MAP, base_path, FILE_COPY_SOURCE)

    def set_creation_logic(self, project_name, base_path):
        """
        Выбирает логику для создания структуры в проводнике/файндере.
        """
        try:
            project_path = os.path.join(base_path, f"CC_{project_name.upper()}" if base_path == "R:/" else project_name)
            os.makedirs(project_path, exist_ok=True)

            if "001_sources" in base_path:
                self.create_folder_structure(STRUCTURE_001_FOLDER, project_path)

            elif "004_masters" in base_path:
                self.create_folder_structure(STRUCTURE_004_MASTERS, project_path)

            if base_path == "R:/":
                self.create_folder_structure(R_FOLDER_STRUCTURE, project_path)

        except Exception as e:
            self.on_error_signal(f"Путь {base_path} не найден")

    def recursive_resolve(self, media_pool, parent_folder, structure):
        for name, subfolders in structure.items():
            new_folder = media_pool.AddSubFolder(parent_folder, name)
            if subfolders:
                self.recursive_resolve(media_pool, new_folder, subfolders)

    def set_resolve_preset(self, project):
        """
        Установка настроек для проектов Reel через пресет Resolve.
        """
        if project.SetPreset(REEL_PRESET):
            logger.info(f"Применен пресет проекта: {REEL_PRESET}")
        else:
            logger.critical(f"Ошибка: Не удалось применить пресет проекта {REEL_PRESET}")

    def create_resolve_structure(self, project_name, type_project_resolve, reels_number):
        """
        Создание структуры для проектов Resolve.
        """
        try:
            try:
                resolve = ResolveObjects()
                project_manager = resolve.project_manager
            except Exception:
                self.on_error_signal("Пожалуйста, откройте Resolve")

            # Логика создания OCF структуры
            if type_project_resolve == "OCF":

                if self.add_proj_folder.isChecked():
                    reels_folder = f"{project_name.upper()}"
                    project_manager.CreateFolder(reels_folder)
                    project_manager.OpenFolder(reels_folder)

                project_manager.CreateProject(f"{project_name.upper()}_OCF")
                resolve = ResolveObjects()
                media_pool = resolve.mediapool
                root_folder = resolve.root_folder
                self.recursive_resolve(media_pool, root_folder, RESOLVE_OCF_FOLDER)

            # Логика создания Reel структуры
            elif type_project_resolve == "REEL":

                if self.add_proj_folder.isChecked():
                    reels_folder = f"{project_name.upper()}_CC"
                    project_manager.CreateFolder(reels_folder)
                    project_manager.OpenFolder(reels_folder)

                for i in range(1, reels_number + 1):
                    project_manager.CreateProject(f"{project_name.upper()}_CC_REEL_0{i}_{date.today().strftime('%Y%m%d')}")
                    resolve = ResolveObjects()
                    project = resolve.project
                    media_pool = resolve.mediapool
                    root_folder = resolve.root_folder
                    self.recursive_resolve(media_pool, root_folder, RESOLVE_REEL_FOLDER)
                    self.set_resolve_preset(project)

        except Exception as e:
            self.on_error_signal(f"Не удалось создать структуру папок в Resolve: {e}")

if __name__ == "__main__":
    app = QApplication(sys.argv)
    apply_style(app)
    window = MainWindow()
    window.show()
    sys.exit(app.exec_())
