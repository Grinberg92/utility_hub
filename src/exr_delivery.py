import sys
import re
import math
import time
from pprint import pformat
from pathlib import Path

from PyQt5.QtWidgets import (
    QApplication, QWidget, QLabel, QLineEdit, QPushButton,
    QVBoxLayout, QHBoxLayout, QComboBox, QFileDialog, QMessageBox, QGroupBox, QCheckBox
)
from PyQt5.QtCore import Qt, QThread, pyqtSignal
from dvr_tools.logger_config import get_logger
from dvr_tools.css_style import apply_style
from dvr_tools.resolve_utils import ResolveObjects
from dvr_tools.resolve_utils import ResolveTimelineItemExtractor


logger = get_logger(__file__)

COLORS = ["Orange", "Yellow", "Lime", "Violet", "Blue"]
EXTENTIONS = (".mxf", ".braw", ".arri", ".r3d", ".dng")

class DvrTimelineObject():
    """
    Объект с атрибутами итема на таймлайне.
    """
    def __init__(self, mp_item, track_type_ind, clip_start_tmln, source_start, source_end, clip_dur, clip_color):
        self.mp_item = mp_item
        self.track_type_ind = track_type_ind
        self.clip_start = clip_start_tmln
        self.clip_duration = clip_dur
        self.clip_end = self.clip_start + (self.clip_duration - 1)
        self.source_start = source_start
        self.source_end = source_end
        self.clip_color = clip_color

class DeliveryPipline:
    """
    Конвеер создания render jobs и их последующего рендера.
    """
    def __init__(self, user_config, signals):
        self.user_config = user_config
        self.signals = signals

    def get_api_resolve(self) -> ResolveObjects:
        """
        Проверка подключения к API Resolve и получение основного объекта Resolve.
        """
        try:
            resolve = ResolveObjects().resolve
            return ResolveObjects()
        except RuntimeError as re:
            raise

    def get_mediapoolitems(self, start_track, end_track) -> list:
        """
        Получение списка с экземплярами DvrTimelineObject,
        содержащими необходимые данные о клипе. 
        """
        timeline_extractor = ResolveTimelineItemExtractor(self.timeline)
        timeline_items = timeline_extractor.get_timeline_items(start_track, end_track)
        filtred_items = []
        for item in timeline_items:
            filtred_items.append(DvrTimelineObject(item.GetMediaPoolItem(), item.GetTrackTypeAndIndex()[1],
                                item.GetStart(), item.GetSourceStartFrame(),
                                item.GetSourceEndFrame(), item.GetDuration(),
                                item.GetClipColor()))
        return filtred_items
    
    def get_tracks(self, start_track=2, track_type="video") -> list:
        """
        Получем индексы не пустых треков.
        """
        no_empty_tracks = []
        all_track = self.timeline.GetTrackCount(track_type)
        for track_num in range(start_track, all_track + 1):
            if self.timeline.GetItemListInTrack(track_type, track_num) != []:
                no_empty_tracks.append(track_num)

        return no_empty_tracks
    
    def set_project_preset(self) -> bool:
        """
        Установка пресета проекта.
        """
        set_preset_var = self.project.SetPreset(self.project_preset)
        if set_preset_var is not None:
            logger.info(f"Применен пресет проекта: {self.project_preset}")
            return True
        else:
            self.signals.error_signal.emit(f"Пресет проекта не применен {self.project_preset}")
            return False
    def set_disabled(self, current_track_number):
        '''
        Отключаем все дорожки кроме текущей.
        '''
        self.max_track = self.timeline.GetTrackCount("video")
        for track_number in range(1, self.max_track + 1):
            self.timeline.SetTrackEnable("video", track_number, track_number == current_track_number)
        logger.info(f"Начало работы с {current_track_number} треком")

    def get_handles(self, timeline_item) -> str:
        '''
        Получаем значения захлестов.
        '''
        start_frame = timeline_item.source_start
        end_frame = timeline_item.source_end
        duration = timeline_item.clip_duration
        source_duration = end_frame - start_frame
        
        # Если source duration врет на 1 фрейм то вычитаем его(баг Resolve).
        # Второе условие пропускает только ретаймы кратные 100(т.е 100, 200, 300 и тд)
        if source_duration % duration == 1 and (source_duration - 1 / duration * 100) % 100 == 0:
            source_duration = source_duration - 1 

        retime_speed = source_duration / duration * 100
        excess = max(0, retime_speed - 100)

        increment = math.ceil(excess / 33.34)
        handles = self.frame_handles + increment

        return f"EXR_{handles}hndl"
    
    def standart_resolution(self, clip) -> str:
        """
        Пересчет разрешения исходника под стандартное разрешение для рендера(2к).
        Обрабатывает и сферическую и анаморфную линзу. 
        Для вычисления выходного разрешения ширины сферической линзы используется формула: 
        (ширина кадра текущего клипа * высота целевого разрешения) / (высота кадра такущего клипа / аспект текущего клипа).
        Для вычисления выходного разрешения высоты анаморфной линзы используется формула: 
        (высота кадра текущего клипа * ширина целевого разрешения) / (ширина кадра такущего клипа).
        Если полученное значение ширины или высоты кадра получается нечетным, то идет округление вверх до ближайшего четного значения.
        """
        if clip.GetClipProperty('PAR') != 'Square' and clip.GetClipProperty('PAR'):
            aspect = clip.GetClipProperty('PAR')
            width, height = clip.GetClipProperty('Resolution').split('x')
            calculate_width = str((math.ceil(((int(width) * int(self.height_res_glob) / (int(height) / float(aspect))) ) / 2) * 2))
            resolution = "x".join([calculate_width, self.height_res_glob])
            return resolution
        
        else:
            aspect = clip.GetClipProperty('PAR')
            width, height = clip.GetClipProperty('Resolution').split('x')
            calculate_height = str((math.ceil((int(height) * int(self.width_res_glob) / int(width)) / 2) * 2))
            resolution = "x".join([self.width_res_glob, calculate_height])
            return resolution
        
    def scale_1_5_resolution(self, clip) -> str:
        """
        Пересчет разрешения исходника под стандартное разрешение для рендера,
        умноженное на 1.5 при зуме(скеиле) свыше 10%.
        Вычисление аналогично standart_resolution, но при этом и ширина и высота домножаются на коэффициент 1.5.
        """
        # Находит анаморф, вычисляет ширину по аспекту
        if clip.GetClipProperty('PAR') != 'Square' and clip.GetClipProperty('PAR'):
            aspect = clip.GetClipProperty('PAR')
            width, height = clip.GetClipProperty('Resolution').split('x')
            calculate_height = str((math.ceil(((int(width) * int(self.height_res_glob) / (int(height) / float(aspect))) ) / 2) * 2))
            resolution = "x".join([str(int(int(calculate_height) * 1.5)), str(int(math.ceil(int(self.height_res_glob) * 1.5 / 2.0) * 2))])
            return resolution
        else:
            aspect = clip.GetClipProperty('PAR')
            width, height = clip.GetClipProperty('Resolution').split('x')
            calculate_height = str((math.ceil((int(height) * int(self.width_res_glob) / int(width)) / 2) * 2))
            resolution = "x".join([str(int(math.ceil((int(self.width_res_glob) * 1.5) / 2) * 2)), str(int(math.ceil((int(calculate_height) * 1.5) / 2) * 2))])
            return resolution
        
    def scale_2_resolution(self, clip) -> str:
        """
        Пересчет разрешения исходника под стандартное разрешение для рендера,
        умноженное на 2 при зуме(скеиле) свыше 50%.
        Вычисление аналогично standart_resolution, но при этом и ширина и высота домножаются на коэффициент 2.
        """
        if clip.GetClipProperty('PAR') != 'Square' and clip.GetClipProperty('PAR'):
            aspect = clip.GetClipProperty('PAR')
            width, height = clip.GetClipProperty('Resolution').split('x')
            calculate_height = str((math.ceil(((int(width) * int(self.height_res_glob) / (int(height) / float(aspect))) ) / 2) * 2))
            resolution = "x".join([str(int(int(calculate_height) * 2)), str(int(math.ceil(int(self.height_res_glob) * 2 / 2.0) * 2))])
            return resolution
        else:
            aspect = clip.GetClipProperty('PAR')
            width, height = clip.GetClipProperty('Resolution').split('x')
            calculate_height = str((math.ceil((int(height) * int(self.width_res_glob) / int(width)) / 2) * 2))
            resolution = "x".join([str(int(math.ceil((int(self.width_res_glob) * 2) / 2) * 2)), str(int(math.ceil((int(calculate_height) * 2) / 2) * 2))])
            return resolution
        
    def full_resolution(self, clip) -> str:
        """
        Полное разрешение исходника.
        Для вычисления выходного разрешения высоты анаморфной линзы используется формула: 
        (высота кадра текущего клипа / аспект текущего клипа).
        Если полученное значение высоты кадра получается нечетным, то идет округление вверх до ближайшего четного значения.
        """
        if clip.GetClipProperty('PAR') != 'Square' and clip.GetClipProperty('PAR'):
            aspect = clip.GetClipProperty('PAR')
            width, height = clip.GetClipProperty('Resolution').split('x')
            calculate_height = str((math.ceil((int(height) / float(aspect))  / 2) * 2))
            resolution = "x".join([width, calculate_height])
            return resolution
        else:
            return clip.GetClipProperty('Resolution')
        
    def get_resolution_settings(self, timeline_item) -> str:
        """
        Метод логики вычисления разрешения для рендера.

        :return resolution: Разрешение в виде строки : '2500x858'.
        """
        
        clip = timeline_item.mp_item
        clip_color = timeline_item.clip_color

        if clip.GetName() != '' and clip.GetName().lower().endswith(EXTENTIONS) and clip_color == COLORS[0]:
            resolution = self.standart_resolution(clip)

        if clip.GetName() != '' and clip.GetName().lower().endswith(EXTENTIONS) and clip_color == COLORS[1]:
            resolution = self.scale_1_5_resolution(clip)
        
        # 2-кратное увеличение разрешение от стандартного(условный 4К)
        if clip.GetName() != '' and clip.GetName().lower().endswith(EXTENTIONS) and clip_color == COLORS[2]:
            resolution = self.scale_2_resolution(clip)
            
        # Полное съемочное разрешение
        if clip.GetName() != '' and clip.GetName().lower().endswith(EXTENTIONS) and clip_color == COLORS[3]:
            resolution = self.full_resolution(clip)

        return resolution
    
    def stop_process(self):
        """
        Приостановка конвеера, пока идет процесс рендера текущего итема.
        """
        def rendering_in_progress():
            return self.project.IsRenderingInProgress()
        while rendering_in_progress():
            time.sleep(1)

    def set_render_preset(self, handles_value) -> bool:
        '''
        Метод ищет полученное в get_retime значение захлеста через регулярное выражение 
        в списке всех пресетов рендера.
        '''
        preset_list = self.project.GetRenderPresetList()
        for preset in preset_list:
            if re.match(handles_value, preset):
                self.project.LoadRenderPreset(preset)
                logger.info(f"Установлен пресет рендера: {handles_value} ")
                return True
        self.signals.error_signal.emit(f"Не удалось применить пресет рендера {handles_value}")
        return False 
            
    def set_project_resolution(self, height_res, width_res):
        """
        Установка проектного разрешения перед рендером.
        """
        self.project.SetSetting("timelineResolutionHeight", height_res)
        self.project.SetSetting("timelineResolutionWidth", width_res)
            
    def set_render_settings(self, clip, clip_resolution):
        '''
        Метод задает настройки для  рендера текущего итема 
        и добавляет текущий render job в очередь.

        :return: Кортеж (Флаг ошибки, render job item)
        '''
        try:
            resolution = re.search(r'\d{4}x\d{3,4}', clip_resolution).group(0)
            width, height = resolution.split("x")
            logger.info(f"Установлено разрешение с настройках рендера: {width}x{height}")
        except Exception as e:
            self.signals.error_signal.emit(f"Не удалось вычислить разрешение {resolution}: {e}")
            return False
        
        self.set_project_resolution(height, width)

        render_settings = {
            "SelectAllFrames": False,
            "MarkIn": clip.clip_start,
            "MarkOut": clip.clip_end,
            "TargetDir": str(self.render_path),
            "FormatWidth": int(width),
            "FormatHeight": int(height)
            }
        
        set_render = self.project.SetRenderSettings(render_settings)
        render_job = self.project.AddRenderJob()

        if set_render is not None and render_job is not None:
            logger.info(f"Запустился рендер клипа {clip.mp_item.GetName()} с разрешением {width}x{height}")
            return True, render_job
        else:
            self.signals.error_signal.emit(f"Не удалось установить разрешение рендера {resolution}")
            return False, None 
        
    def skip_item(self, item) -> bool:
        """
        Пропускает итем, для последующей обработки вручную, при условии,
        что у клипа установлен дефолтный цвет 'Blue'.
        """
        if item.clip_color == COLORS[4]:
            return True

    def start_render(self, render_job) -> bool:
        """
        Запуск render job.
        """    
        start_render = self.project.StartRendering([render_job], isInteractiveMode=True)
        if not start_render:
            self.signals.error_signal.emit(f"Ошибка обработки рендера: {render_job}")
            return False
        return True
    
    def export_timeline(self):
        """
        Экспорт таймлайна после окончания рендера в формате xml.

        """
        xml_name = str(self.timeline.GetName())
        path = (Path(self.render_path) / ".." / f'{xml_name}.xml').resolve()  
        result = self.timeline.Export(str(path), self.resolve.EXPORT_FCP_7_XML)
        if result is None:
            self.signals.warning_signal.emit(f"Ошибка экспорта таймлайна {xml_name}")
        else:
            logger.info(f"Таймлайн {xml_name} успешно экспортирован")

    def set_enabled(self):

        for track_number in range(1, self.max_track + 1):
            
            self.timeline.SetTrackEnable("video", track_number, True)

    def run(self):
        """
        Логика конвеера рендера.
        """
        self.resolve_api = self.get_api_resolve()
        self.resolve = self.resolve_api.resolve
        self.media_pool = self.resolve_api.mediapool
        self.timeline = self.resolve_api.timeline
        self.project = self.resolve_api.project
        self.project_preset = self.user_config["project_preset"]
        self.frame_handles = int(self.user_config["handles"])
        self.height_res_glob = self.user_config["resolution_height"]
        self.width_res_glob = self.user_config["resolution_width"]
        self.render_path = self.user_config["render_path"]
        self.export_bool = self.user_config["export_xml"]

        video_tracks = self.get_tracks()
        if video_tracks == []:
            self.signals.warning_signal.emit("Отсутствуют клипы для обработки.")
            return False

        project_preset_var = self.set_project_preset()
        if not project_preset_var:
            return False

        # Цикл по дорожкам(по основному и допплейтам, если таковые имеются).
        for track in video_tracks:

            track_items = self.get_mediapoolitems(start_track=track, end_track=track)

            self.set_disabled(track)
            
            # Цикл по клипам на дорожке.
            for item in track_items:
                
                if self.skip_item(item):
                    continue

                logger.debug("\n".join(("\n", f"timline duration: {item.clip_duration}",
                             f"source duration: {item.source_end - item.source_start}",
                             f"timline start: {item.clip_start}",
                             f"timeline end: {item.clip_end}",
                             f"source start: {item.source_start}",
                             f"source end: {item.source_end}")))

                handles_value = self.get_handles(item)

                item_resolution = self.get_resolution_settings(item)

                # Ставится до установки render preset
                self.stop_process()

                render_preset_var = self.set_render_preset(handles_value)
                if not render_preset_var:
                    return False
                
                render_settings_var, render_job = self.set_render_settings(item, item_resolution)
                if not render_settings_var:
                    return False
                
                start_render_var = self.start_render(render_job)
                if not start_render_var:
                    return False

            # Ожидаем, переключаемся на вкладку edit и уходим на новый трек.
            self.stop_process()
            self.resolve.OpenPage("edit")

        self.set_enabled()
        if self.export_bool:    
            self.export_timeline()
        self.signals.success_signal.emit(f"Рендер успешно завершен!")

class RenderWorker(QThread):
    """
    Запуск логики из отдельного потока.
    """
    success_signal = pyqtSignal(str)
    warning_signal = pyqtSignal(str)
    error_signal = pyqtSignal(str)

    def __init__(self, parent, user_config):
        super().__init__(parent)
        self.user_config = user_config

    def run(self):
        try:
            logic = DeliveryPipline(self.user_config, self)
            success = logic.run()

        except Exception as e:
            print(f"Ошибка программы {e}")

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
            "resolution_height": self.gui.height_input.text().strip(),
            "resolution_width": self.gui.width_input.text().strip(),
            "project_preset": self.gui.preset_combo.currentText().strip(),
            "handles": self.gui.handle_input.text().strip(),
            "render_path": self.gui.render_path.text().strip(),
            "export_xml": self.gui.export_cb.isChecked()
        }
    
    def validate(self, user_config: dict) -> bool:
        """
        Валидирует конфиг.
        """
        self.errors.clear()

        if not user_config["render_path"]:
            self.errors.append("Укажите путь для рендера")

        try:
            int(user_config["resolution_height"])
            int(user_config["resolution_width"])
            int(user_config["handles"])
        except ValueError:
            self.errors.append("Значения должны быть целыми числами")
        return not self.errors

    def get_errors(self) -> list:
        return self.errors
        

class ExrDelivery(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("EXR Delivery")
        self.resize(600, 200)
        self.setWindowFlags(self.windowFlags() | Qt.WindowStaysOnTopHint)

        self.res_group = QGroupBox("Resolution")
        self.res_group.setFixedHeight(70)
        self.width_input = QLineEdit("2048")
        self.width_input.setFixedWidth(60)
        self.height_input = QLineEdit("858")
        self.height_input.setFixedWidth(60)

        self.preset_combo = QComboBox()
        self.preset_combo.addItems(["aces1.2_smoother_preset"])
        self.preset_combo.setCurrentText("aces1.2_smoother_preset")
        self.preset_combo.setMinimumWidth(180)
        self.export_cb = QCheckBox("Export .xml")
        self.handle_input = QLineEdit("3")
        self.handle_input.setFixedWidth(40)

        self.render_path = QLineEdit()
        self.browse_btn = QPushButton("Choose")
        self.browse_btn.clicked.connect(self.select_folder)

        self.init_ui()

    def init_ui(self):
        layout = QVBoxLayout()

        # --- Разрешение ---
        res_layout = QHBoxLayout()
        res_layout.addStretch()
        res_layout.addWidget(self.width_input)
        res_layout.addWidget(QLabel("x"))
        res_layout.addWidget(self.height_input)
        res_layout.addStretch()
        self.res_group.setLayout(res_layout)
        layout.addWidget(self.res_group, alignment=Qt.AlignHCenter)

        # --- Пресет + захлест ---
        preset_layout = QHBoxLayout()
        preset_layout.addWidget(QLabel("Project preset:"))
        preset_layout.addWidget(self.preset_combo)
        preset_layout.addSpacing(20)
        preset_layout.addWidget(QLabel("Handles:"))
        preset_layout.addWidget(self.handle_input)
        preset_layout.addSpacing(20)
        preset_layout.addWidget(self.export_cb)
        
        preset_layout.addStretch()
        layout.addLayout(preset_layout)

        # --- Путь рендера ---
        path_layout = QHBoxLayout()
        path_layout.addWidget(QLabel("Render path:"))
        path_layout.addSpacing(10)
        path_layout.addWidget(self.render_path)
        path_layout.addWidget(self.browse_btn)
        layout.addLayout(path_layout)

        # --- Кнопка запуска ---
        self.run_button = QPushButton("Start")
        self.run_button.clicked.connect(self.run_render)
        layout.addWidget(self.run_button)

        palette_widget = self.create_color_palette()
        layout.addWidget(palette_widget)

        self.setLayout(layout)

    def create_color_palette(self, labels=None):
        palette_group = QGroupBox("")

        main_layout = QVBoxLayout()
        label_layout = QHBoxLayout()
        color_layout = QHBoxLayout()

        labels = {
            "Orange": "Standart res",
            "Yellow": "1.5x res",
            "Lime": "2x res",
            "Violet": "Full res",
            "Blue": "Ignore"
        }
        color_map = {
            "Orange": "#FFA500",
            "Yellow": "#FFFF00",
            "Lime": "#00FF00",
            "Violet": "#8A2BE2",
            "Blue": "#1E90FF"
        }

        self.color_labels = {}

        for name, hex_color in color_map.items():
            # Если задан labels — берём из него, иначе "Label"
            label_text = labels.get(name, "Label") if labels else "Label"

            # Верхний лейбл
            label = QLabel(label_text)
            label.setAlignment(Qt.AlignCenter)
            self.color_labels[name] = label
            label_layout.addWidget(label)

            # Цветной блок с подписью внутри
            color_box = QLabel(name)
            color_box.setFixedSize(107, 25)
            color_box.setAlignment(Qt.AlignCenter)
            color_box.setStyleSheet(f"""
                background-color: {hex_color};
                color: black;
                border: 1px solid gray;
                border-radius: 4px;
            """)
            color_layout.addWidget(color_box)

        main_layout.addLayout(label_layout)
        main_layout.addLayout(color_layout)
        palette_group.setLayout(main_layout)
        return palette_group

    def on_success_signal(self):
        QMessageBox.information(self, "Успех", "Рендер успешно завершен")

    def on_warning_signal(self, message):
        QMessageBox.warning(self, "Предупреждение", message)
        logger.warning(message)

    def on_error_signal(self, message):
        QMessageBox.critical(self, "Ошибка", message)
        logger.exception(message)

    def select_folder(self):
        folder = QFileDialog.getExistingDirectory(self, "Выбор папки")
        if folder:
            self.render_path.setText(folder)

    def run_render(self):

        self.validator = ConfigValidator(self)
        self.user_config = self.validator.collect_config()

        if not self.validator.validate(self.user_config):
            QMessageBox.critical(self, "Ошибка валидации", "\n".join(self.validator.get_errors()))
            return
   
        logger.info(f"\n\n{pformat(self.user_config)}\n")
        self.render_thread = RenderWorker(self, self.user_config)
        self.run_button.setEnabled(False)
        self.render_thread.finished.connect(lambda: self.run_button.setEnabled(True))
        self.render_thread.success_signal.connect(self.on_success_signal)
        self.render_thread.warning_signal.connect(self.on_warning_signal)
        self.render_thread.error_signal.connect(self.on_error_signal)
        self.render_thread.start()

if __name__ == "__main__":
    app = QApplication(sys.argv)
    apply_style(app)
    window = ExrDelivery()
    window.show()
    sys.exit(app.exec_())
