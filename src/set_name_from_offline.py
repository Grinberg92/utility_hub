import DaVinciResolveScript as dvrs
from PyQt5 import QtWidgets, QtCore
import sys
from dvr_tools.logger_config import get_logger

logger = get_logger(__file__)

class GUI(QtWidgets.QWidget):
    def __init__(self):
        super().__init__()
        self.init_ui()

    def init_ui(self):
        self.setWindowTitle('Names from Offline')
        self.setWindowFlag(QtCore.Qt.WindowStaysOnTopHint)

        # Размеры окна
        window_width = 230
        window_height = 100
        self.setFixedSize(window_width, window_height)

        # Центрирование окна
        screen = QtWidgets.QDesktopWidget().screenGeometry()
        x = (screen.width() - window_width) // 2
        y = (screen.height() - window_height) // 2
        self.move(x, y)

        # Главный вертикальный layout
        main_layout = QtWidgets.QVBoxLayout()

        # Горизонтальный layout для ввода номера трека
        input_layout = QtWidgets.QHBoxLayout()
        label = QtWidgets.QLabel('Offline Track Number:')
        self.track_entry = QtWidgets.QLineEdit()
        self.track_entry.setFixedWidth(50)

        input_layout.addWidget(label)
        input_layout.addWidget(self.track_entry)
        input_layout.addStretch()

        # Центрированный layout для кнопки
        button = QtWidgets.QPushButton('Start')
        button.setFixedWidth(180)
        button.clicked.connect(self.func)

        button_layout = QtWidgets.QHBoxLayout()
        button_layout.addStretch()
        button_layout.addWidget(button)
        button_layout.addStretch()

        # Добавление всех layout'ов в основной
        main_layout.addLayout(input_layout)
        main_layout.addLayout(button_layout)

        self.setLayout(main_layout)

    def func(self):
        try:
            resolve = dvrs.scriptapp('Resolve')
            projectManager = resolve.GetProjectManager()
            project = projectManager.GetCurrentProject()
            mediaPool = project.GetMediaPool()
            timeline = project.GetCurrentTimeline()
            tlStart = timeline.GetStartFrame()

            count_of_tracks = timeline.GetTrackCount('video')

            # Проверка и преобразование номера дорожки
            try:
                track_number = int(self.track_entry.text())
            except ValueError:
                logger.exception('Введите корректный номер дорожки')
                raise ValueError('Введите корректный номер дорожки')

            clips = timeline.GetItemListInTrack('video', track_number)
            if clips is None:
                logger.warning(f"Дорожка {track_number} не существует.")
                QtWidgets.QMessageBox.warning(self, "Внимание", f"Дорожка {track_number} не существует.")
                return
            if clips == []:
                logger.warning(f"На дорожке {track_number} отсутствуют объекты.")
                QtWidgets.QMessageBox.warning(self, "Внимание", f"На дорожке {track_number} отсутствуют объекты.")
                return

            for clip in clips:
                clipName = clip.GetName()
                # Расчёт средней точки клипа (примерно центр)   (заморозил)
                #clip_start = int((clip.GetStart() + (clip.GetStart() + clip.GetDuration())) / 2) - tlStart
                #timeline.AddMarker(clip_start, 'Blue', clipName, "", 1, 'Renamed')

                # Применение кастомного имени на другие клипы, совпадающие по старту
                for track_index in range(1, count_of_tracks):
                    clips_under = timeline.GetItemListInTrack('video', track_index)
                    if clips_under:
                        for clip_under in clips_under:
                            if clip_under.GetStart() == clip.GetStart():
                                clip_under.AddVersion(clipName, 0)
                                print(f'Добавлено кастомное имя "{clipName}" в клип на треке {track_index}')
            logger.info("Имена из оффлайн клипов применены на все клипы")
            QtWidgets.QMessageBox.information(self, "Success", "Имена из оффлайн клипов применены на все клипы")
        except ValueError as ve:
            QtWidgets.QMessageBox.critical(self, 'Ошибка', str(ve))
        except Exception as e:
            logger.exception(f'Произошла ошибка: {str(e)}')
            QtWidgets.QMessageBox.critical(self, 'Ошибка', f'Произошла ошибка: {str(e)}')

if __name__ == "__main__":
    app = QtWidgets.QApplication(sys.argv)
    window = GUI()
    window.show()
    sys.exit(app.exec_())
