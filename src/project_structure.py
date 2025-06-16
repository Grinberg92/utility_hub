import os
import re
import sys
import DaVinciResolveScript as dvr
from PyQt5.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QHBoxLayout, QRadioButton, QLabel,
    QComboBox, QLineEdit, QPushButton, QSpinBox, QGroupBox, QFormLayout,
    QMessageBox, QFileDialog 
)

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
    "05_TRAILERS": {},
    "06_MASTER": {}
}

RESOLVE_OCF_FOLDER = {
    "001_OCF": {},
    "002_EDIT": {},
    "003_TO_VFX": {}, 
    "004_TO_CC": {}, 
    "005_SCREENING": {}, 
    "006_TMP": {}
    }

RESOLVE_REEL_FOLDER = RESOLVE_REEL_FOLDER = {
    "001_SRC": {},
    "002_TIMELINES": {},
    "003_VFX": {
        "CURRENT_DAY": {}
    },
    "004_REEDIT": {},
    "005_TITLES": {},
    "006_MASKS": {},
    "007_MASTERS": {},
    "008_TMP": {}
}


def create_folder_structure(structure, base_path):
    for folder, subfolders in structure.items():
        folder_path = os.path.join(base_path, folder)
        os.makedirs(folder_path, exist_ok=True)
        if subfolders:
            create_folder_structure(subfolders, folder_path)

def create_avid_structure(base_path):
    os.makedirs(base_path, exist_ok=True)
    create_folder_structure(AVID_FOLDER_STRUCTURE, base_path)

def create_project(project_name, base_path):
    project_path = os.path.join(base_path, f"CC_{project_name.upper()}" if base_path == "R:/" else project_name)
    os.makedirs(project_path, exist_ok=True)
    if "001_sources" in base_path:
        create_folder_structure(STRUCTURE_001_FOLDER, project_path)
    elif "004_masters" in base_path:
        create_folder_structure(STRUCTURE_004_MASTERS, project_path)
    if base_path == "R:/":
        create_folder_structure(R_FOLDER_STRUCTURE, project_path)

def recursive_resolve(media_pool, parent_folder, structure):
    for name, subfolders in structure.items():
        new_folder = media_pool.AddSubFolder(parent_folder, name)
        if subfolders:
            recursive_resolve(media_pool, new_folder, subfolders)


def create_resolve_structure(project_name, type_project_resolve, reels_number):
    resolve = dvr.scriptapp("Resolve")
    project = resolve.GetProjectManager()

    if type_project_resolve == "OCF":
        reels_folder = f"{project_name.upper()}"
        project.CreateFolder(reels_folder)
        project.OpenFolder(reels_folder)

        new_project = project.CreateProject(f"{project_name.upper()}_OCF")
        current_project = resolve.GetProjectManager().GetCurrentProject()
        media_pool = current_project.GetMediaPool()
        root_folder = media_pool.GetRootFolder()
        recursive_resolve(media_pool, root_folder, RESOLVE_OCF_FOLDER)

    elif type_project_resolve == "REEL":
        reels_folder = f"{project_name.upper()}_CC"
        project.CreateFolder(reels_folder)
        project.OpenFolder(reels_folder)

        for i in range(1, reels_number + 1):
            new_project = project.CreateProject(f"{project_name.upper()}_CC_REEL_0{i}")
            current_project = resolve.GetProjectManager().GetCurrentProject()
            media_pool = current_project.GetMediaPool()
            root_folder = media_pool.GetRootFolder()
            recursive_resolve(media_pool, root_folder, RESOLVE_REEL_FOLDER)


class MainWindow(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Project Structure Creator")
        self.setup_ui()

    def setup_ui(self):
        layout = QVBoxLayout()

        # Mode selection
        mode_layout = QHBoxLayout()
        self.explorer_radio = QRadioButton("Explorer")
        self.resolve_radio = QRadioButton("Resolve")
        self.avid_radio = QRadioButton("Avid")
        self.explorer_radio.setChecked(True)
        mode_layout.addWidget(self.explorer_radio)
        mode_layout.addWidget(self.resolve_radio)
        mode_layout.addWidget(self.avid_radio)
        layout.addLayout(mode_layout)

        # Explorer group
        self.explorer_group = QGroupBox("Explorer Options")
        explorer_form = QFormLayout()
        self.disk_selector = QComboBox()
        self.disk_selector.addItems(["J", "R"])
        self.explorer_project_name = QLineEdit()
        self.explorer_project_name.setPlaceholderText("Project name")
        explorer_form.addRow(QLabel("Disk:"), self.disk_selector)
        explorer_form.addRow(QLabel("Project:"), self.explorer_project_name)
        self.explorer_group.setLayout(explorer_form)
        layout.addWidget(self.explorer_group)

        # Resolve group
        self.resolve_group = QGroupBox("Resolve Options")
        resolve_form = QFormLayout()
        self.type_selector = QComboBox()
        self.type_selector.addItems(["OCF", "REEL"])
        self.reels_input = QSpinBox()
        self.reels_input.setRange(1, 20)
        self.resolve_project_name = QLineEdit()
        self.resolve_project_name.setPlaceholderText("Project name")
        resolve_form.addRow(QLabel("Type:"), self.type_selector)
        resolve_form.addRow(QLabel("Reels:"), self.reels_input)
        resolve_form.addRow(QLabel("Project:"), self.resolve_project_name)
        self.resolve_group.setLayout(resolve_form)
        layout.addWidget(self.resolve_group)

        # Avid group 
        self.avid_group = QGroupBox("Avid Options")
        avid_form = QFormLayout()
        self.avid_path_label = QLabel()
        self.avid_path_button = QPushButton("Choose")
        avid_form.addRow(QLabel("Path:"), self.avid_path_button)
        avid_form.addRow(QLabel("Chosen Path:"), self.avid_path_label)
        self.avid_group.setLayout(avid_form)
        layout.addWidget(self.avid_group)

        # Create button
        self.create_button = QPushButton("Create")
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
            self.avid_path_label.setText("Не выбран")

    def setup_connections(self):
        self.explorer_radio.toggled.connect(self.update_ui)
        self.resolve_radio.toggled.connect(self.update_ui)
        self.avid_path_button.clicked.connect(self.select_avid_path)
        self.type_selector.currentTextChanged.connect(self.update_reel_input)
        self.create_button.clicked.connect(self.run_logic)

    def update_ui(self):
        is_explorer = self.explorer_radio.isChecked()
        is_resolve = self.resolve_radio.isChecked()
        is_avid = self.avid_radio.isChecked()

        self.explorer_group.setEnabled(is_explorer)
        self.resolve_group.setEnabled(is_resolve)
        self.avid_group.setEnabled(is_avid)
        self.update_reel_input()

    def update_reel_input(self):
        is_reel = self.type_selector.currentText() == "REEL"
        self.reels_input.setEnabled(is_reel)

    def run_logic(self):
        if self.explorer_radio.isChecked():
            disk = self.disk_selector.currentText()
            project_name = self.explorer_project_name.text().strip()
            if not project_name:
                QMessageBox.warning(self, "Ошибка", "Пожалуйста, укажите имя проекта для Explorer.")
                return
            if disk == "J":
                for folder in J_SRTUCTURE:
                    create_project(project_name, folder)
            else:
                create_project(project_name, R_STRUCTURE)

        elif self.resolve_radio.isChecked():
            type_proj = self.type_selector.currentText()
            project_name = self.resolve_project_name.text().strip()
            if not project_name:
                QMessageBox.warning(self, "Ошибка", "Пожалуйста, укажите имя проекта для Resolve.")
                return
            reels = self.reels_input.value()
            create_resolve_structure(project_name, type_proj, reels)

        elif self.avid_radio.isChecked():
            if not hasattr(self, 'avid_selected_path') or not self.avid_selected_path:
                QMessageBox.warning(self, "Ошибка", "Пожалуйста, выберите путь для Avid структуры.")
                return
            create_avid_structure(self.avid_selected_path)


if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = MainWindow()
    window.resize(300, 200)
    window.show()
    sys.exit(app.exec_())
