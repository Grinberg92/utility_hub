import sys
import os
import re
from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QLineEdit, QTextEdit, QPushButton, QFileDialog, QMessageBox
)
from dvr_tools.css_style import apply_style
from dvr_tools.logger_config import get_logger

logger = get_logger(__file__)

def filter_edl(edl_text: str, exclude_ids: list[str]) -> str:
    """
    Убирает из EDL блоки, в которых *LOC содержит один из exclude_ids.
    """
    lines = edl_text.splitlines()
    blocks = []
    current_block = []

    for line in lines:
        if re.match(r"^\d{6}", line):  
            if current_block:
                blocks.append(current_block)
            current_block = [line]
        elif line.startswith("*LOC"):
            current_block.append(line)
            blocks.append(current_block)
            current_block = []
        else:
            if current_block is not None:
                current_block.append(line)

    if current_block:
        blocks.append(current_block)

    filtered_blocks = []
    for block in blocks:
        loc_line = next((l for l in block if l.startswith("*LOC")), None)
        if loc_line:
            shot_id = loc_line.strip().split()[-1]
            if shot_id in exclude_ids:
                filtered_blocks.append(block)
        else:
            filtered_blocks.append(block)

    return "\n".join("\n".join(b) for b in filtered_blocks)


class EDLFilterApp(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("EDL Filter")
        self.resize(600, 200)

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
        layout.addWidget(QLabel("Shot names to exclude:"))
        layout.addWidget(self.ids_edit)

        filter_btn = QPushButton("Start")
        filter_btn.clicked.connect(self.run_filter)
        layout.addWidget(filter_btn)

        self.edl_text = ""
        self.edl_path = ""

    def choose_file(self):
        path, _ = QFileDialog.getOpenFileName(self, "Choose EDL", "", "EDL Files (*.edl *.txt)")
        if path:
            self.file_edit.setText(path)
            self.edl_path = path
            with open(path, "r", encoding="utf-8") as f:
                self.edl_text = f.read()

    def run_filter(self):
        if not self.edl_text or not self.edl_path:
            QMessageBox.warning(self, "Error", "Сначала выберите файл EDL")
            return

        ids_raw = self.ids_edit.toPlainText().strip()
        exclude_ids = ids_raw.replace(",", " ").split()
        result = filter_edl(self.edl_text, exclude_ids)

        base, ext = os.path.splitext(self.edl_path)
        new_path = base + "_filtered" + ext

        with open(new_path, "w", encoding="utf-8") as f:
            f.write(result)

        QMessageBox.information(self, "Success", f"Файл сохранён:\n{new_path}")


if __name__ == "__main__":
    app = QApplication(sys.argv)
    apply_style(app)
    win = EDLFilterApp()
    win.show()
    sys.exit(app.exec_())
