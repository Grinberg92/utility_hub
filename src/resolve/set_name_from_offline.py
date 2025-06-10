import DaVinciResolveScript as dvrs
import tkinter as tk
from tkinter import messagebox

class GUI:
    def __init__(self, root):
        self.root = root
        self.root.title('Set shots name')
        root.attributes("-topmost", True)

        # Позиция окна
        window_width = 230
        window_height = 100

        screen_width = root.winfo_screenwidth()
        screen_height = root.winfo_screenheight()

        x = (screen_width // 2) - (window_width // 2)
        y = ((screen_height // 2) - (window_height // 2))

        root.geometry(f"{window_width}x{window_height}+{x}+{y}")

        # Создание виджетов
        self.create_widgets()

    def create_widgets(self):
        # Строка с label и полем ввода на одной строке
        label = tk.Label(self.root, text='Offline track number:')
        label.grid(row=0, column=0, padx=10, pady=10, sticky='e')  # Выравнивание по правому краю

        self.track_entry = tk.Entry(self.root, width=5)  # Настроена ширина поля ввода
        self.track_entry.grid(row=0, column=1, padx=10, pady=10, sticky='w')  # Выравнивание по левому краю

        # Кнопка
        btn = tk.Button(self.root, text='Set names', command=self.func, width=20)
        btn.grid(row=1, column=0, columnspan=2, pady=10)  # Настроена ширина кнопки

    def func(self):
        try:
            resolve = dvrs.scriptapp('Resolve')
            projectManager = resolve.GetProjectManager()
            project = projectManager.GetCurrentProject()
            mediaPool = project.GetMediaPool()
            timeline = project.GetCurrentTimeline()
            tlStart = timeline.GetStartFrame()

            count_of_tracks = timeline.GetTrackCount('video')
            track_number = int(self.track_entry.get())
            clips = timeline.GetItemListInTrack('video', track_number)

            for clip in clips:
                clipName = clip.GetName()
                clip_start = int((clip.GetStart() + (clip.GetStart() + clip.GetDuration())) / 2) - tlStart
                timeline.AddMarker(clip_start, 'Blue', clipName, "", 1, 'Renamed')

                for track_index in range(1, count_of_tracks):
                    clips_under = timeline.GetItemListInTrack('video', track_index)
                    if clips_under:
                        for clip_under in clips_under:
                            if clip_under.GetStart() == clip.GetStart():
                                clip_under.AddVersion(clipName, 0)
                                print(f'Добавлено кастомное имя "{clipName}" в клип на треке {track_index}')

            messagebox.showinfo("Success", "Кастомные имена применены на все клипы")
        except ValueError:
            messagebox.showerror('Error', 'Введите корректный номер дорожки')
        except Exception as e:
            messagebox.showerror('Error', f'Произошла ошибка: {str(e)}')


if __name__ == "__main__":
    root = tk.Tk()
    app = GUI(root)
    root.mainloop()
