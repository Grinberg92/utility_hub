import sys
import os
import random
import re
import math
import time
import DaVinciResolveScript as dvr
import tkinter as tk
from tkinter import ttk, filedialog

class ResolveGUI:
    def __init__(self, root):
        self.root = root
        self.root.title("Proxy Render")

        window_width = 670 
        window_height = 215 
 
        screen_width = root.winfo_screenwidth() 
        screen_height = root.winfo_screenheight() 
 
        # Вычисляем координаты x и y 
        x = (screen_width // 2) - (window_width // 2) 
        y = int((screen_height * 7 / 10) - (window_height / 2)) 
        root.geometry(f"{window_width}x{window_height}+{x}+{y}") 

        # --- Глобальные настройки ---
        self.glob_width = tk.StringVar(value="1920")
        self.glob_height = tk.StringVar(value="1080")
        self.output_folder = tk.StringVar(value="J:/003_transcode_to_vfx/kraken/tst")
        self.project_preset = tk.StringVar(value="for_conform_1920x1080")
        self.render_preset = tk.StringVar(value="MXF_AVID_HD_Render")
        self.lut_project = tk.StringVar()
        self.lut_file = tk.StringVar()
        self.set_fps_enabled = tk.BooleanVar(value=False)
        self.project_fps_value = tk.StringVar(value="24")
        self.set_arri_cdl_and_lut = tk.BooleanVar(value=False)
        self.lut_path_nx = r'C:\ProgramData\Blackmagic Design\DaVinci Resolve\Support\LUT\LUTS_FOR_PROXY'
        self.lut_path_posix = '/Library/Application Support/Blackmagic Design/DaVinci Resolve/LUT/LUTS_FOR_PROXY/'
        self.lut_base_path = (self.lut_path_nx, self.lut_path_posix)[os.name == "posix"]

        # Подключение к Resolve
        self.resolve = dvr.scriptapp("Resolve")
        self.project_manager = self.resolve.GetProjectManager()
        self.project = self.project_manager.GetCurrentProject()
        self.media_pool = self.project.GetMediaPool()
        self.timeline = self.project.GetCurrentTimeline()

        # Создание интерфейса
        self.create_widgets()

        if not self.project:
            print("Ошибка: нет активного проекта.")
            sys.exit()

    def create_widgets(self):
        def get_project_preset_list():
            return [preset["Name"] for preset in self.project.GetPresetList()]
        
        def get_render_preset_list():
            return [preset for preset in self.project.GetRenderPresetList()]
        
        # Поля для ширины и высоты (в одной строке)
        frame_size = tk.Frame(self.root)
        frame_size.pack(pady=5)

        tk.Label(frame_size, text="Width:").pack(side=tk.LEFT, padx=5)
        tk.Entry(frame_size, textvariable=self.glob_width, width=6).pack(side=tk.LEFT)

        tk.Label(frame_size, text="Height:").pack(side=tk.LEFT, padx=5)
        tk.Entry(frame_size, textvariable=self.glob_height, width=6).pack(side=tk.LEFT)

        # Поле выбора папки
        frame_folder = tk.Frame(self.root)
        frame_folder.pack(pady=5, fill="x")

        tk.Label(frame_folder, text="Render path:").pack(side=tk.LEFT, padx=5)
        self.folder_entry = tk.Entry(frame_folder, textvariable=self.output_folder, width=30)
        self.folder_entry.pack(side=tk.LEFT, padx=5, expand=True, fill="x")
        tk.Button(frame_folder, text="Choose", command=self.select_folder).pack(side=tk.LEFT, padx=5)

        # Поля выбора пресетов
        frame_presets = tk.Frame(self.root)
        frame_presets.pack(pady=5)
        n = get_project_preset_list()
        tk.Label(frame_presets, text="Project preset:").pack(side=tk.LEFT, padx=5)
        self.project_preset_combo = ttk.Combobox(frame_presets, textvariable=self.project_preset, values=get_project_preset_list())
        self.project_preset_combo.pack(side=tk.LEFT, padx=5)

        tk.Label(frame_presets, text="Render preset:").pack(side=tk.LEFT, padx=5)
        self.render_preset_combo = ttk.Combobox(frame_presets, textvariable=self.render_preset, values=get_render_preset_list())
        self.render_preset_combo.pack(side=tk.LEFT, padx=5)

        # Поля выбора LUT-папок и LUT-файлов
        frame_lut = tk.Frame(self.root)
        frame_lut.pack(pady=5)

        tk.Label(frame_lut, text="Project:").pack(side=tk.LEFT, padx=5)

        self.lut_project_combo = ttk.Combobox(frame_lut, textvariable=self.lut_project, state="readonly", width=20)
        self.lut_project_combo.pack(side=tk.LEFT, padx=5)

        tk.Label(frame_lut, text="LUT file:").pack(side=tk.LEFT, padx=5)

        self.lut_file_combo = ttk.Combobox(frame_lut, textvariable=self.lut_file, state="readonly", width=30)
        self.lut_file_combo.pack(side=tk.LEFT, padx=5)

        self.fps_checkbox = tk.Checkbutton(frame_lut, text="ApplyArriCDLandLUT", variable=self.set_arri_cdl_and_lut)
        self.fps_checkbox.pack(side=tk.LEFT, padx=5)

        # Установка проектного FPS
        frame_fps = tk.Frame(self.root)
        frame_fps.pack(pady=5)

        self.fps_checkbox = tk.Checkbutton(frame_fps, text="Set project FPS", variable=self.set_fps_enabled)
        self.fps_checkbox.pack(side=tk.LEFT, padx=5)

        tk.Label(frame_fps, text="FPS:").pack(side=tk.LEFT, padx=(10, 2))
        self.fps_entry = tk.Entry(frame_fps, textvariable=self.project_fps_value, width=5)
        self.fps_entry.pack(side=tk.LEFT)

        def update_lut_projects():
            """Сканирует подпапки в LUT-папке"""
            if os.path.isdir(self.lut_base_path):
                subfolders = [name for name in os.listdir(self.lut_base_path)
                              if os.path.isdir(os.path.join(self.lut_base_path, name))]
                self.lut_project_combo["values"] = subfolders
                if subfolders:
                    self.lut_project.set(subfolders[0])
                    update_lut_files()

        def update_lut_files(*args):
            """Сканирует .cube файлы в выбранной папке LUT"""
            selected_project = self.lut_project.get()
            if not selected_project:
                return
            selected_path = os.path.join(self.lut_base_path, selected_project)
            if os.path.isdir(selected_path):
                cube_files = [f for f in os.listdir(selected_path)
                              if f.lower().endswith(".cube")]
                cube_files.insert(0, "No LUT")
                self.lut_file_combo["values"] = cube_files
                if cube_files:
                    self.lut_file.set(cube_files[0])
                else:
                    self.lut_file.set("")

        self.lut_project.trace_add("write", update_lut_files)

        update_lut_projects()

        # Кнопка старта рендера
        tk.Button(self.root, text="Start", command=self.start_render).pack(pady=10)

    def select_folder(self):
        folder = filedialog.askdirectory()
        if folder:
            self.output_folder.set(folder)

    def start_render(self):
        glob_width = self.glob_width.get()
        glob_height = self.glob_height.get()
        output_folder = self.output_folder.get()
        project_preset = self.project_preset.get()
        render_preset = self.render_preset.get()

        print(f"Рендер с параметрами: {glob_width}x{glob_height}, Папка: {output_folder}, Проектный пресет: {project_preset}, Рендер-пресет: {render_preset}")
        
        # Вызываем основной процесс рендера
        self.process_render(glob_width, glob_height, output_folder, project_preset, render_preset)

    def process_render(self, glob_width, glob_height, output_folder, project_preset, render_preset):

        def copy_filtered_clips_to_ocf_folder(current_source_folder):
            """
            Ищет .mov, .mp4, .jpg клипы в current_source_folder и перемещает их в
            001_OCF/mov_mp4_jpg/{current_source_folder}.
            """

            valid_extensions = ['.mov', '.mp4', '.jpg', '.MOV', '.MP4', '.JPG']
            root_folder = self.media_pool.GetRootFolder()

            # --- Найти или создать папку 001_OCF ---
            ocf_folder = next((f for f in root_folder.GetSubFolderList() if f.GetName() == "001_OCF"), None)
            if not ocf_folder:
                print("Папка '001_OCF' не найдена.")
                return

            # --- Найти или создать папку mov_mp4_jpg ---
            base_folder = next((f for f in ocf_folder.GetSubFolderList() if f.GetName() == "mov_mp4_jpg"), None)
            if not base_folder:
                base_folder = self.media_pool.AddSubFolder(ocf_folder, "mov_mp4_jpg")
                if not base_folder:
                    print("Не удалось создать папку 'mov_mp4_jpg'.")
                    return

            # --- Сбор клипов с подходящими расширениями ---
            def collect_valid_clips(folder):

                "Функция формирует список 'отбракованных mov, mp4, jpg'"
                collected = []
                for clip in folder.GetClipList():
                    name = clip.GetName().lower()
                    if any(name.endswith(ext) for ext in valid_extensions):
                        if self.set_fps_enabled.get():
                            set_project_fps(clip)
                        collected.append(clip)
                for subfolder in folder.GetSubFolderList():
                    collected.extend(collect_valid_clips(subfolder))
                return collected

            clips_to_move = collect_valid_clips(current_source_folder)

            if not clips_to_move:
                print(f"Нет .mov, .jpg, .mp4 клипов для перемещения.")
                self.media_pool.SetCurrentFolder(current_source_folder) 
                return  
            else:
                # --- Создать вложенную подпапку с именем текущего исходного бин-фолдера ---
                source_folder_name = current_source_folder.GetName()
                target_folder = next((f for f in base_folder.GetSubFolderList() if f.GetName() == source_folder_name), None)
                if not target_folder:
                    target_folder = self.media_pool.AddSubFolder(base_folder, source_folder_name)
                    if not target_folder:
                        print(f"Не удалось создать папку '{source_folder_name}' внутри 'mov_mp4_jpg'.")
                        return
                    
            # Переключаемся в нужный подбин
            self.media_pool.SetCurrentFolder(target_folder)
            
            return clips_to_move
        
        def set_project_fps(clip):

            "Функция устанавливает проектный FPS"
            clip.SetClipProperty("FPS", self.project_fps_value.get())

        def get_bin_items():

            "Функция получения списка медиапул итемов в текущем фолдере"
            cur_bin_items_list = []
            curr_source_folder = self.media_pool.GetCurrentFolder()
            for clip in curr_source_folder.GetClipList():
                if "." in clip.GetName() and not clip.GetName().lower().endswith(('.mov', '.mp4', '.jpg')):
                    if self.set_fps_enabled.get():
                        set_project_fps(clip)
                    cur_bin_items_list.append(clip)
            return cur_bin_items_list, curr_source_folder
        
        def turn_on_burn_in():

            "Функция устанавливает пресет burn in"
            self.project.LoadBurnInPreset("python_proxy_preset") 

        def set_project_preset():

            "Функция устанавливает пресет проекта"

            if self.project.SetPreset(project_preset):
                print(f"Применен пресет проекта: {project_preset}")
            else:
                print(f"Ошибка: Не удалось применить пресет проекта {project_preset}")

        def get_sep_resolution_list(cur_bin_items_list, extentions=None):

            "Функция создает словать с парами ключ(разрешение): значение(список соответствующих клипов)"
            clips_dict = {}
            for clip in cur_bin_items_list:
                    if clip.GetName() != '' and clip.GetName().lower().endswith(extentions):
                        # Находит анаморф, вычисляет ширину по аспекту
                        if clip.GetClipProperty('PAR') != 'Square' and clip.GetClipProperty('PAR'):
                            aspect = clip.GetClipProperty('PAR')
                            width, height = clip.GetClipProperty('Resolution').split('x')
                            calculate_height = str((math.ceil(((int(height) / float(aspect)) * int(glob_width) / int(width) ) / 2) * 2))
                            resolution = "x".join([glob_width, calculate_height])
                            clips_dict.setdefault(resolution, []).append(clip)
                        else:
                            aspect = clip.GetClipProperty('PAR')
                            width, height = clip.GetClipProperty('Resolution').split('x')
                            calculate_height = str((math.ceil((int(height) * int(glob_width) / int(width)) / 2) * 2))
                            resolution = "x".join([glob_width, calculate_height])
                            clips_dict.setdefault(resolution, []).append(clip)
            return clips_dict
        
        def get_timelines(clips_dict):

            "Функция создает таймлайны"
            new_timelines = []
            for res, items in clips_dict.items():
                random_number = random.randint(10000, 999999)  # Генерируем случайное число
                timeline_name = f"tmln_{res}_{random_number}"  # Пример: tmln_1920x660_212066
                timeline = self.media_pool.CreateEmptyTimeline(timeline_name)
                self.project.SetCurrentTimeline(timeline)
                self.media_pool.AppendToTimeline(items)
                
                if timeline:
                    print(f"Создан таймлайн: {timeline_name}")
                    new_timelines.append(timeline)
                else:
                    print(f"Ошибка при создании таймлайна: {timeline_name}")

            if not new_timelines:
                print("Не удалось создать ни одного таймлайна.")
                exit()
            return new_timelines
        
        def set_lut():

            "Функция устанавливает заданный LUT(распаковывает AriiCDLLut) на все клипы на таймлайне"
            self.project.RefreshLUTList()
            if not self.set_arri_cdl_and_lut.get() and self.lut_file == "No LUT":
                return
            current_timeline = self.project.GetCurrentTimeline()
            for track in range(1, current_timeline.GetTrackCount("video") + 1):
                for tmln_item in current_timeline.GetItemListInTrack("video", track):
                    if self.set_arri_cdl_and_lut.get():
                        tmln_item.GetNodeGraph(1).ApplyArriCdlLut()  
                    if not self.lut_file == "No LUT":
                        lut_path = os.path.join(self.lut_base_path, self.lut_project.get(), self.lut_file.get())
                        tmln_item.SetLUT(1, lut_path)
        
        def get_render_list(new_timelines):

            "Функция создает рендер джобы из всех собранных таймлайнов"
            render_list = []
            for timeline in new_timelines:
                self.project.SetCurrentTimeline(timeline)  # Переключаемся на текущий таймлайн
                set_lut()
                timeline_name = timeline.GetName()
                resolution = re.search(r'\d{3,4}x\d{3,4}', timeline_name).group(0)
                width, height = resolution.split("x")
                print(f"Добавляю в очередь рендеринга: {timeline_name}")

                # Применяем пресет рендера
                if self.project.LoadRenderPreset(render_preset):
                    print(f"Применен пресет рендера: {render_preset}")
                else:
                    print(f"Ошибка: Не удалось загрузить пресет рендера {render_preset}")
                
                # Устанавливаем настройки рендера
                render_settings = {
                    "TargetDir": output_folder,
                    "FormatWidth": int(width), 
                    "FormatHeight": int(height)
                }
                self.project.SetRenderSettings(render_settings)
                

                # Добавляем в очередь рендера
                render_item = self.project.AddRenderJob()  
                render_list.append((render_item, timeline_name))
            return render_list
        
        def rendering_in_progress():

            "Функция проверяеет есть ли активный рендер"
            return self.project.IsRenderingInProgress()
        
        def start_render(render_queue):

            "Функция запуска рендера"
            print("Запускаю рендер...")
            for render, timeline_name in render_queue:
                resolution = re.search(r'\d{3,4}x\d{3,4}', timeline_name).group(0)
                width, height = resolution.split("x")
                # Проверяем закончился ли предыдущий рендер
                while rendering_in_progress():
                    print("Ожидание")
                    time.sleep(1)
                print("Разрешение",resolution)
                self.project.SetSetting("timelineResolutionWidth", width)
                self.project.SetSetting("timelineResolutionHeight", height)

                self.project.StartRendering(render)

        # Основной блок

        # Получаем список с целевыми клипами( не включая расширения mov, mp4, jpg), основной фолдер с целевыми клипами
        # Устанавливаем пресет для burn in и проекта
        cur_bin_items_list, current_source_folder = get_bin_items()
        filterd_clips = copy_filtered_clips_to_ocf_folder(current_source_folder)
        turn_on_burn_in()
        set_project_preset()

        # Формирование таймлайнов для фильтрованных клипов(mov, mp4, jpg)
        if filterd_clips:
            filtred_clips_dict = get_sep_resolution_list(filterd_clips, extentions=('.mov', '.mp4', '.jpg'))
            get_timelines(filtred_clips_dict)
            # Возвращаемся в основной фолдер с рабочими клипами
            self.media_pool.SetCurrentFolder(current_source_folder)

        # Получаем данные по целевым клипам
        # 2 сценария:
        # 1 - рендер прокси в DNxHD и вписывание любых разрешений в 1920x1080
        if self.render_preset.get() == "MXF_AVID_HD_Render":
            clips_dict = {"1920x1080": cur_bin_items_list}
        # 2 - рендер прокси в DNxHR и пересчет аспекта каждого разрешения под ширину 1920
        else:
            clips_dict = get_sep_resolution_list(cur_bin_items_list, extentions=(".mxf", ".braw", ".arri", ".r3d", ".dng"))

        # Формирование таймлайнов для целевых клипов и запуск рендера
        new_timelines = get_timelines(clips_dict)       
        render_queue = get_render_list(new_timelines)
        start_render(render_queue)

if __name__ == "__main__":
    root = tk.Tk()
    app = ResolveGUI(root)
    root.mainloop()

