import os 

def apply_style(app):
    font_family = "Segoe UI"  # Современный системный шрифт
    ICON_PATH = os.path.join(os.path.dirname(os.path.realpath(__file__)), "..", "..", "hub", "ui", "arrow_ico_white.png")
    app.setStyleSheet(f"""
        QWidget {{
            background-color: #2b2b2b;
            color: #dcdcdc;
            font-family: "{font_family}";
            font-size: 10.5pt;
        }}

        QLineEdit, QComboBox, QTextEdit {{
            background-color: #3c3f41;
            border: 1px solid #555;
            border-radius: 4px;
            padding: 4px;
            selection-background-color: #007acc;
            color: #ffffff;
        }}

        QLineEdit:disabled, QComboBox:disabled, QTextEdit:disabled {{
            background-color: #2a2a2a;
            color: #777;
            border: 1px solid #444;
        }}

        QComboBox::drop-down {{
            border: none;
            background-color: #3c3f41;
        }}

        QComboBox::down-arrow {{
            image: url("{ICON_PATH}");
            width: 12px;
            height: 12px;
            margin-right: 15px;
            background: transparent;
        }}

        QGroupBox {{
            border: 1px solid #444;
            border-radius: 5px;
            margin-top: 10px;
            font-weight: bold;
            font-size: 11pt;
        }}

        QGroupBox:disabled {{
            color: #777;
            border-color: #333;
        }}

        QGroupBox:title {{
            subcontrol-origin: margin;
            subcontrol-position: top center;
            padding: 0 3px;
        }}

        QPushButton {{
            background-color: #007acc;
            color: white;
            border: none;
            border-radius: 4px;
            padding: 6px 12px;
        }}

        QPushButton:hover {{
            background-color: #2899e0;
        }}

        QPushButton:pressed {{
            background-color: #005f99;
        }}

        QPushButton:disabled {{
            background-color: #3c3f41;
            color: #777;
            border: 1px solid #444;
        }}

        QCheckBox {{
            spacing: 6px;
        }}

        QCheckBox::indicator {{
            width: 14px;
            height: 14px;
            border-radius: 3px;
            border: 1px solid #666;
            background-color: #2b2b2b;
        }}

        QCheckBox::indicator:checked {{
            background-color: #007acc;
            border: 1px solid #007acc;
        }}

        QCheckBox::indicator:hover {{
            border: 1px solid #aaaaaa;
        }}

        QCheckBox::indicator:disabled {{
            background-color: #2a2a2a;
            border: 1px solid #444;
        }}

        QRadioButton {{
            spacing: 6px;
        }}

        QRadioButton::indicator {{
            width: 14px;
            height: 14px;
            border-radius: 7px;
            border: 1px solid #666;
            background-color: #2b2b2b;
        }}

        QRadioButton::indicator:checked {{
            background-color: #007acc;
            border: 1px solid #007acc;
        }}

        QRadioButton::indicator:hover {{
            border: 1px solid #aaaaaa;
        }}

        QRadioButton::indicator:disabled {{
            background-color: #2a2a2a;
            border: 1px solid #444;
        }}

        QListWidget {{
            background-color: #3c3f41;
            border: 1px solid #555;
            padding: 4px;
        }}

        QListWidget::item:selected {{
            background-color: #007acc;
            color: white;
        }}

        QLabel {{
            font-size: 10pt;
        }}

        QLabel:disabled {{
            color: #777;
        }}

        QScrollBar:vertical {{
            background: #2b2b2b;
            width: 12px;
            margin: 0px;
        }}

        QScrollBar::handle:vertical {{
            background: #5a5a5a;
            border-radius: 5px;
            min-height: 20px;
        }}

        QScrollBar::add-line:vertical,
        QScrollBar::sub-line:vertical {{
            height: 0px;a
        }}

        QProgressBar {{
            border: 1px solid #555;
            border-radius: 5px;
            background-color: #3c3f41;
            text-align: center;
            color: white;
        }}

        QProgressBar::chunk {{
            background-color: #007acc;
            width: 20px;
        }}

        QProgressBar:disabled {{
            background-color: #2a2a2a;
            color: #777;
            border: 1px solid #444;
        }}
    """)
