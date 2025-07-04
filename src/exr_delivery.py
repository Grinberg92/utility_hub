import sys
import os
import re
import math
import time
import DaVinciResolveScript as dvr

from PyQt5.QtWidgets import (
    QApplication, QWidget, QLabel, QLineEdit, QPushButton,
    QVBoxLayout, QHBoxLayout, QComboBox, QFileDialog, QMessageBox
)
from PyQt5.QtCore import Qt, QThread, pyqtSignal
from dvr_tools.logger_config import get_logger

logger = get_logger(__file__)

class DvrRenderApp(QWidget):

    render_preset_error = pyqtSignal()
    project_preset_error = pyqtSignal()
    success_message = pyqtSignal()
    empty_track_warning = pyqtSignal()
    render_settings_error = pyqtSignal()
    resolve_connect_error = pyqtSignal()

    class RenderThread(QThread):
        def __init__(self, parent):
            super().__init__()
            self.parent = parent

        def run(self):
            self.parent.render_logic()

    def __init__(self):
        super().__init__()
        self.setWindowTitle("EXR Delivery")
        self.setMinimumWidth(450)
        self.setWindowFlags(self.windowFlags() | Qt.WindowStaysOnTopHint)
        self.init_ui()
        self.render_preset_error.connect(self.on_render_preset_error)
        self.project_preset_error.connect(self.on_project_preset_error)
        self.success_message.connect(self.on_success_message)
        self.empty_track_warning.connect(self.on_empty_track_warning)
        self.render_settings_error.connect(self.on_render_settings_error)
        self.resolve_connect_error.connect(self.on_resolve_connect_error)

    def init_ui(self):
        layout = QVBoxLayout()

        # --- Разрешение ---
        res_layout = QHBoxLayout()
        res_layout.addStretch()
        self.width_input = QLineEdit("1998")
        self.width_input.setFixedWidth(60)
        self.height_input = QLineEdit("1080")
        self.height_input.setFixedWidth(60)
        res_layout.addWidget(QLabel("Resolution:"))
        res_layout.addWidget(self.width_input)
        res_layout.addWidget(QLabel("x"))
        res_layout.addWidget(self.height_input)
        res_layout.addStretch()
        layout.addLayout(res_layout)

        # --- Пресет + захлест ---
        preset_layout = QHBoxLayout()
        self.preset_combo = QComboBox()
        self.preset_combo.addItems(["GRN_EXR_1998x1054", "PRESET_A", "PRESET_B"])
        self.preset_combo.setCurrentText("GRN_EXR_1998x1054")
        self.handle_input = QLineEdit("3")
        self.handle_input.setFixedWidth(40)
        preset_layout.addWidget(QLabel("Project preset:"))
        preset_layout.addWidget(self.preset_combo)
        preset_layout.addSpacing(40)
        preset_layout.addWidget(QLabel("Handles:"))
        preset_layout.addWidget(self.handle_input)
        preset_layout.addStretch()
        layout.addLayout(preset_layout)

        # --- Путь рендера ---
        path_layout = QHBoxLayout()
        self.path_input = QLineEdit()
        browse_btn = QPushButton("Choose")
        browse_btn.clicked.connect(self.select_folder)
        path_layout.addWidget(QLabel("Render path:"))
        path_layout.addWidget(self.path_input)
        path_layout.addWidget(browse_btn)
        layout.addLayout(path_layout)

        # --- Кнопка запуска ---
        self.run_button = QPushButton("Start")
        self.run_button.clicked.connect(self.run_render)
        layout.addWidget(self.run_button)

        self.setLayout(layout)

    def on_render_preset_error(self, message):
        QMessageBox.critical(self, "Ошибка установки пресета рендера", message)

    def on_project_preset_error(self, message):
        QMessageBox.critical(self, "Ошибка установки пресета проекта", message)

    def on_success_message(self):
        QMessageBox.information(self, "Успех", "Рендер успешно завершен")

    def on_empty_track_warning(self):
        QMessageBox.warning(self, "Предупреждение","На дорожках 2-5 отсутствуют клипы")

    def on_render_settings_error(self, message):
        QMessageBox.critical(self, "Ошибка установки разрешения в настройки рендера", message)

    def on_resolve_connect_error(self):
        QMessageBox.critical(self, "Ошибка", "Ошибка запуска. Откройте Resolve")

    def select_folder(self):
        folder = QFileDialog.getExistingDirectory(self, "Выбор папки")
        if folder:
            self.path_input.setText(folder)

    def run_render(self):
        self.output_folder = self.path_input.text()
        if not self.output_folder:
            QMessageBox.warning(self, "Ошибка", "Укажите путь для рендера")
            logger.warning("Укажите путь для рендера")
            return
        
        self.width_res_glob = self.width_input.text()
        self.height_res_glob = self.height_input.text()
        if not self.width_res_glob or not self.height_res_glob:
            QMessageBox.warning(self, "Ошибка", "Укажите значение ширины или высоты кадра")
            logger.warning("Укажите ширину или высоту кадра")
            return
        
        self.frame_handles = int(self.handle_input.text())
        if not self.frame_handles:
            QMessageBox.warning(self, "Ошибка", "Укажите значение захлеста")
            logger.warning("Укажите значение захлеста")
            return
        
        logger.info(f"SetUp: Resolution - {self.width_res_glob}x{self.height_res_glob}, Handles - {self.frame_handles}, Path - {self.output_folder}")
        self.render_thread = self.RenderThread(self)
        self.render_thread.start()

    def render_logic(self):
        project_preset_name = self.preset_combo.currentText()

        class DvrTimelineObject():
            "Пользовательский класс для удобного получения атрибутов объекта на таймлайне"
            def __init__(self, mp_item, track_type_ind, clip_start_tmln, source_start, source_end, clip_dur):
                self.mp_item = mp_item
                self.track_type_ind = track_type_ind
                self.clip_start_tmln = clip_start_tmln
                self.clip_dur = clip_dur
                self.clip_end = self.clip_start_tmln + (self.clip_dur - 1)
                self.source_start = source_start
                self.source_end = source_end
        
        resolve = dvr.scriptapp("Resolve")

        if resolve is None:
            self.resolve_connect_error.emit()
            return
        
        project_manager = resolve.GetProjectManager()
        project = project_manager.GetCurrentProject()
        media_pool = project.GetMediaPool()
        timeline = project.GetCurrentTimeline()
        root_folder = media_pool.GetRootFolder()

        def get_mediapoolitems(end_track, start_track):
            # Получение списка кортежей с атрибутами timelineitems
            all_items = []
            for track in range(start_track, end_track + 1):
                clips = timeline.GetItemListInTrack('video', int(track))
                for clip in clips:
                    all_items.append((clip.GetMediaPoolItem(), clip.GetTrackTypeAndIndex()[1],
                                      clip.GetStart(), clip.GetSourceStartFrame(),
                                      clip.GetSourceEndFrame(), clip.GetDuration()))
            return [DvrTimelineObject(*item) for item in all_items]

        def set_project_preset():
            # Устанавливаем пресет проекта
            try:
                project.SetPreset(project_preset_name)
                logger.info(f"Применен пресет проекта: {project_preset_name}")
                return True
            except Exception as e:
                self.project_preset_error.emit(f"Не удалось применить пресет проекта {project_preset_name}: {e}")
                logger.error(f"Не удалось применить пресет проекта {project_preset_name}: {e}")
                return False

        def get_resolution_settings(clip, track_number):
            """
            Функция получения разрешения клипа
            """
            extentions = (".mxf", ".braw", ".arri", ".r3d", ".dng", 
                        ".MXF", ".BRAW", ".R3D", ".ARRI", ".DNG")

            # Стандартный пересчет аспекта под 2К
            if clip.GetName() != '' and clip.GetName().lower().endswith(extentions) and track_number == 2:
                # Находит анаморф, вычисляет ширину по аспекту
                if clip.GetClipProperty('PAR') != 'Square' and clip.GetClipProperty('PAR'):
                    aspect = clip.GetClipProperty('PAR')
                    width, height = clip.GetClipProperty('Resolution').split('x')
                    calculate_width = str((math.ceil(((int(width) * int(self.height_res_glob) / (int(height) / float(aspect))) ) / 2) * 2))
                    if calculate_width == "2500": # Временная правка для выдачи BOI
                        calculate_width = "2498"
                    resolution = "x".join([calculate_width, self.height_res_glob])
                    return resolution
                else:
                    aspect = clip.GetClipProperty('PAR')
                    width, height = clip.GetClipProperty('Resolution').split('x')
                    calculate_height = str((math.ceil((int(height) * int(self.width_res_glob) / int(width)) / 2) * 2))
                    resolution = "x".join([self.width_res_glob, calculate_height])
                    return resolution

            # 1.5-кратное увеличение разрешение от стандартного
            if clip.GetName() != '' and clip.GetName().lower().endswith(extentions) and track_number == 3:
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
            
            # 2-кратное увеличение разрешение от стандартного(условный 4К)
            if clip.GetName() != '' and clip.GetName().lower().endswith(extentions) and track_number == 4:
                # Находит анаморф, вычисляет ширину по аспекту
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
                
            # Полное съемочное разрешение
            if clip.GetName() != '' and clip.GetName().lower().endswith(extentions) and track_number == 5:
                # Находит анаморф, вычисляет ширину по аспекту
                if clip.GetClipProperty('PAR') != 'Square' and clip.GetClipProperty('PAR'):
                    aspect = clip.GetClipProperty('PAR')
                    width, height = clip.GetClipProperty('Resolution').split('x')
                    calculate_height = str((math.ceil((int(height) / float(aspect))  / 2) * 2))
                    resolution = "x".join([width, calculate_height])
                    return resolution
                else:
                    return clip.GetClipProperty('Resolution')

        def rendering_in_progress():
            return project.IsRenderingInProgress()

        def set_enable_for_track(current_track_number):
            '''
            Функция отключает все дорожки кроме текущей
            '''
            max_track = timeline.GetTrackCount("video")
            for track_number in range(1, max_track + 1):
                timeline.SetTrackEnable("video", track_number, track_number == current_track_number)

        def get_retime(strt_frame, end_frame, duration) -> str:

            '''
            Функция получения значения захлестов
            '''
            if duration == 0:
                raise ValueError("Деление на ноль")
            retime_speed = (end_frame - strt_frame) / duration * 100
            excess = max(0, retime_speed - 100)
            if retime_speed <= 133:
                # Округляем вниз только в этом диапазоне. Что бы сгладить баг давинчи с  определением in/out.
                # Будет отсутствовать 4 захлеста
                increment = int(excess // 33.34)
            else:
                # Выше 133 — округляем вверх
                increment = math.ceil(excess / 33.34)
            handles = self.frame_handles + increment
            return f"EXR_{handles}hndl"

        def set_render_preset(calc_handl):
            '''
            Функция ищет полученное в get_retime значение захлеста через регулярное выражение в списке всех пресетов рендера
            '''
            try:
                preset_list = project.GetRenderPresetList()
                for preset in preset_list:
                    if re.match(calc_handl, preset):
                        project.LoadRenderPreset(preset)
                        logger.info(f"Установлен пресет рендера: {calc_handl} ")
                        return True
            except Exception as e:
                self.render_preset_error.emit(f"Не удалось применить пресет рендера {calc_handl}: {e}")
                logger.error(f"Не удалось применить пресет рендера {calc_handl}: {e}")
                return False 

        def set_render_settings(mark_in, mark_out, clip_resolution):
            '''
            Функция задает настройки для последующего рендера клипа
            '''
            try:
                resolution = re.search(r'\d{4}x\d{3,4}', clip_resolution).group(0)
                width, height = resolution.split("x")
                render_settings = {
                    "SelectAllFrames": False,
                    "MarkIn": mark_in,
                    "MarkOut": mark_out,
                    "TargetDir": self.output_folder,
                    "FormatWidth": int(width),
                    "FormatHeight": int(height)
                }
                project.SetRenderSettings(render_settings)
                render_item = project.AddRenderJob()
                return render_item, width, height
            
            except Exception as e:
                self.render_preset_error.emit(f"Не удалось установить разрешение рендера {resolution}: {e}")
                logger.error(f"Не удалось применить пресет рендера {resolution}: {e}")
                return False 
            
        def create_empty_tracks(current_traks_value):
            "Функция создает дополнительные дорожки при значении < 5 на таймлайне"
            for _ in range(5 - current_traks_value):
                timeline.AddTrack("video")

        # Проверка на наличие 5 обязательных дорожек
        if timeline.GetTrackCount("video") < 5:
            create_empty_tracks(timeline.GetTrackCount("video"))

        # Получение объектов таймлайна с дорожек 2-5, представленных в виде пользовательского класса DvrTimelineObject
        pipeline_scale_track_2 = get_mediapoolitems(end_track=2, start_track=2) 
        scale_1_5x_track_3 = get_mediapoolitems(end_track=3, start_track=3)
        scale_2x_track_4 = get_mediapoolitems(end_track=4, start_track=4)
        full_res_track_5 = get_mediapoolitems(end_track=5, start_track=5)
        all_tracks = (pipeline_scale_track_2, scale_1_5x_track_3, scale_2x_track_4, full_res_track_5)
        logger.info("Собраны списки медиапул объектов со всех дорожек")

        # Установка пресета проекта
        set_project_preset_var = set_project_preset()
        if not set_project_preset_var:
            return

        if all(not track for track in all_tracks):
            self.empty_track_warning.emit()
            logger.warning("На дорожках 2-5 отсутствют клипы")
            return

        # Основной цикл идущий по дорожкам 2-5
        for track in all_tracks:

            try:
                set_enable_for_track(track[0].track_type_ind)
                logger.info(f"Начало работы с {track[0].track_type_ind} треком")
            except IndexError:
                continue

            # Цикл фнутри одной из дорожек
            for clip in track:

                current_track_number = clip.track_type_ind
                calc_handl = get_retime(clip.source_start, clip.source_end, clip.clip_dur)
                clip_resolution = get_resolution_settings(clip.mp_item, current_track_number)

                # Последующий цикл не проходит пока идет рендер
                while rendering_in_progress():
                    time.sleep(1)

                # Установка пресета рендера и настроек рендера
                set_render_preset_var = set_render_preset(calc_handl)
                if not set_render_preset_var:
                    return
                
                render_item, width_res, height_res = set_render_settings(clip.clip_start_tmln, clip.clip_end, clip_resolution)
                if not render_item or not width_res or not height_res:
                    return
                
                logger.info(f"Установлено разрешение с настройках рендера: {width_res}x{height_res}")

                # Установка разрешение проекта
                project.SetSetting("timelineResolutionWidth", width_res)
                project.SetSetting("timelineResolutionHeight", height_res)
                logger.info(f"Запустился рендер клипа {clip.mp_item.GetName()} с разрешением {width_res}x{height_res}")

                # Запуск текущего render job
                project.StartRendering(render_item)

            # Ожидает пока закончиться рендер последнего клипа на дорожке n, переключает на вкладку edit и цикл уходит на новый трек
            while rendering_in_progress():
                time.sleep(1)
            resolve.OpenPage("edit")
        self.success_message.emit()
        
if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = DvrRenderApp()
    window.show()
    sys.exit(app.exec_())
