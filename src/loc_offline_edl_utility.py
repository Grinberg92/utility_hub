import tkinter as tk
from tkinter import filedialog, messagebox
import re
from timecode import Timecode as tc
import DaVinciResolveScript as dvr


class EDLProcessorGUI:
    def __init__(self, root):

        self.pattern_short = r'(?<!\d)(?:..._)?\d{3,4}[a-zA-Z]?_\d{1,4}(?!\d)' 
        self.root = root
        self.root.title("EDL&Markers Creator")
        root.attributes('-topmost', True)

        window_width = 620  
        window_height = 250  
        screen_width = root.winfo_screenwidth()
        screen_height = root.winfo_screenheight()

        x = (screen_width // 2) - (window_width // 2)
        y = int((screen_height * 7 / 10) - (window_height / 2))
        root.geometry(f"{window_width}x{window_height}+{x}+{y}")

        self.input_file_var = tk.StringVar()
        self.output_file_var = tk.StringVar()
        self.fps_var = tk.StringVar(value="24")
        self.track_number_var = tk.StringVar(value="1")

        # Флаги чекбоксов
        self.set_markers_var = tk.BooleanVar()
        self.export_loc_var = tk.BooleanVar()
        self.offline_clips_var = tk.BooleanVar()
        self.edl_for_dailies_var = tk.BooleanVar()

        # Поля ввода
        tk.Label(self.root, text="Choose EDL-file:").pack(pady=5)
        input_frame = tk.Frame(self.root)
        input_frame.pack()
        self.input_entry = tk.Entry(input_frame, textvariable=self.input_file_var, width=45)
        self.input_entry.pack(side=tk.LEFT, padx=5)
        tk.Button(input_frame, text="Choose", command=self.select_input_file).pack(side=tk.RIGHT)

        tk.Label(self.root, text="Save created EDL:").pack(pady=5)
        output_frame = tk.Frame(self.root)
        output_frame.pack()
        self.output_entry = tk.Entry(output_frame, textvariable=self.output_file_var, width=45)
        self.output_entry.pack(side=tk.LEFT, padx=5)
        tk.Button(output_frame, text="Choose", command=self.select_output_file).pack(side=tk.RIGHT)

        # Чекбоксы + поле ввода номера дорожки
        checkbox_frame = tk.Frame(self.root)
        checkbox_frame.pack(pady=7)
        # Чекбоксы
        set_locators_frame = tk.Frame(checkbox_frame)
        set_locators_frame.pack(side=tk.LEFT, padx=5)
        tk.Checkbutton(set_locators_frame, text="Set locators", variable=self.set_markers_var).pack(side=tk.LEFT)
        tk.Label(set_locators_frame, text="Track:").pack(side=tk.LEFT, padx=5)
        self.track_number_entry = tk.Entry(set_locators_frame, textvariable=self.track_number_var, width=3)
        self.track_number_entry.pack(side=tk.LEFT)
        self.track_number_entry.config(state="disabled")

        # Остальные чекбоксы
        tk.Checkbutton(checkbox_frame, text="Export locators", variable=self.export_loc_var).pack(side=tk.LEFT, padx=5)
        tk.Checkbutton(checkbox_frame, text="Offline EDL", variable=self.offline_clips_var).pack(side=tk.LEFT, padx=5)
        tk.Checkbutton(checkbox_frame, text="Dailies EDL", variable=self.edl_for_dailies_var).pack(side=tk.LEFT, padx=5)

        fps_frame = tk.Frame(self.root)
        fps_frame.pack(pady=3)
        tk.Label(fps_frame, text="FPS:").pack(side=tk.LEFT, padx=5)
        tk.Entry(fps_frame, textvariable=self.fps_var, width=3).pack(side=tk.LEFT, padx=5)

        tk.Button(self.root, text="Start", command=self.run_script, width=15).pack(pady=5)

        # Привязываем функцию к изменениям состояний чекбоксов
        self.set_markers_var.trace_add("write", lambda *args: self.update_fields_state())
        self.export_loc_var.trace_add("write", lambda *args: self.update_fields_state())
        self.offline_clips_var.trace_add("write", lambda *args: self.update_fields_state())
        self.edl_for_dailies_var.trace_add("write", lambda *args: self.update_fields_state())

    def select_input_file(self):
        file_path = filedialog.askopenfilename(filetypes=[("EDL файлы", "*.edl")])
        if file_path:
            self.input_file_var.set(file_path)

    def select_output_file(self):
        default_extension = ".txt" if self.export_loc_var.get() else ".edl"
        filetypes = [("Текстовые файлы", "*.txt")] if self.export_loc_var.get() else [("EDL файлы", "*.edl")]
        
        file_path = filedialog.asksaveasfilename(defaultextension=default_extension, filetypes=filetypes)
        if file_path:
            self.output_file_var.set(file_path)

    def update_fields_state(self):
        """ 
        Блокирует или разблокирует поля в зависимости от состояния чекбоксов
        """
        if self.set_markers_var.get():
            # Если включен "Set locators", разблокируем поле ввода номера дорожки
            self.track_number_entry.config(state="normal")
        else:
            self.track_number_entry.config(state="disabled")

        if self.set_markers_var.get():
            # Если включен "Set locators", блокируем оба поля
            self.input_entry.config(state="disabled")
            self.output_entry.config(state="disabled")
        elif self.export_loc_var.get():
            # Если включен "Export locators", блокируем только input
            self.input_entry.config(state="disabled")
            self.output_entry.config(state="normal")
        else:
            # Если включен "Offline EDL" или "Dailies EDL", разблокируем оба
            self.input_entry.config(state="normal")
            self.output_entry.config(state="normal")


    def run_script(self):
        edl_path = self.input_file_var.get()
        output_path = self.output_file_var.get()
        export_loc = self.export_loc_var.get()
        set_markers = self.set_markers_var.get()
        fps = self.fps_var.get()
        process_edl = self.edl_for_dailies_var.get() or self.offline_clips_var.get()

        if process_edl and (not edl_path or not output_path):
            messagebox.showerror("Ошибка", "Выберите файлы EDL!")
            return

        try:
            fps = int(fps)
        except ValueError:
            messagebox.showerror("Ошибка", "FPS должен быть числом!")
            return

        track_number = self.track_number_var.get()
        try:
            track_number = int(track_number)
        except ValueError:
            messagebox.showerror("Ошибка", "Номер дорожки должен быть числом!")
            return

        try:
            self.resolve = dvr.scriptapp("Resolve")
            self.project = self.resolve.GetProjectManager().GetCurrentProject()
            self.timeline = self.project.GetCurrentTimeline()
            self.timeline_start_tc = self.timeline.GetStartFrame()

            if process_edl:
                self.process_edl(self.timeline, edl_path, output_path, fps)

            if set_markers:
                self.set_markers(self.timeline, track_number)

            if export_loc:
                self.export_locators_to_avid(output_path)

            messagebox.showinfo("Готово", "Обработка завершена!")
        except Exception as e:
            messagebox.showerror("Ошибка", f"Произошла ошибка: {e}")

    def get_markers(self, timeline_start_timecode): 
        '''
        Получение маркеров для работы других функций
        '''
        markers_list = []
        for timecode, name in self.timeline.GetMarkers().items():
            name = name['name'].strip()
            if name and re.search(self.pattern_short, name):
                timecode_marker = tc(self.fps_var.get(), frames=timecode + timeline_start_timecode) + 1  
                markers_list.append((name, timecode_marker))
        return markers_list

    def set_markers(self, timeline, track_number):
        '''
        Установка маркеров с номерами полученными из оффлайн клипов на текущем таймлайне 
        '''
        clips = timeline.GetItemListInTrack('video', track_number)
        for clip in clips:
            if re.search(self.pattern_short, clip.GetName()):
                clip_name = clip.GetName()
                clip_start = int((clip.GetStart() + (clip.GetStart() + clip.GetDuration())) / 2) - timeline.GetStartFrame()
                timeline.AddMarker(clip_start, 'Blue', clip_name, "", 1, 'Renamed')


    def export_locators_to_avid(self, output_path):
        '''
        Формирование строк и экспорт локаторов для AVID в .txt
        '''
        markers_list = self.get_markers(self.timeline_start_tc)
        with open(output_path, "a", encoding='utf8') as output:
            for name, timecode in markers_list:
                # Используется спец табуляция для корректного импорта в AVID
                output_string = f'PGM	{str(timecode)}	V3	yellow	{name}'
                output.write(output_string + "\n")

    def process_edl(self, timeline, edl_path, output_path, fps):
        """
        Выводит EDL для дейлизов и EDL с оффлайн клипами
        """
        offline_clips = self.offline_clips_var.get()
        edl_for_dailies = self.edl_for_dailies_var.get()

        def parse_edl():
            markers_list = self.get_markers(self.timeline_start_tc)
            with open(edl_path, "r", encoding='utf8') as edl_file:
                title = [next(edl_file) for _ in range(2)]
                lines = edl_file.readlines()

            with open(output_path, "w", encoding='utf8') as output:
                output.write("".join(title) + "\n")
                for line in lines:
                    if re.search(r'^\d+\s', line.strip()):  
                        parts = line.split()
                        edl_timeline_start_tc = parts[6]
                        edl_timeline_end_tc = parts[7]

                        # Логика для offline_clips
                        if offline_clips:
                            marker_name = None
                            for name, timecode in markers_list:
                                if tc(fps, edl_timeline_start_tc).frames <= tc(fps, timecode).frames <= tc(fps, edl_timeline_end_tc).frames:
                                    marker_name = name
                            if marker_name is not None:
                                output.write(" ".join(parts) + '\n')
                                output.write(f'* FROM CLIP NAME: {marker_name}\n\n')

                        # Логика для edl_for_dailies
                        elif edl_for_dailies:
                            for name, timecode in markers_list:
                                if tc(fps, edl_timeline_start_tc).frames <= tc(fps, timecode).frames <= tc(fps, edl_timeline_end_tc).frames:
                                    parts[1] = name
                            output.write(" ".join(parts) + '\n')

        parse_edl()

if __name__ == "__main__":
    root = tk.Tk()
    app = EDLProcessorGUI(root)
    root.mainloop()


