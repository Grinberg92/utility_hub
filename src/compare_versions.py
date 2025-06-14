import tkinter as tk
from tkinter import filedialog, messagebox, scrolledtext
from collections import Counter
import DaVinciResolveScript 
from datetime import date
import os
import openpyxl
import re
import traceback
import csv
from itertools import count

class VersionCheckerApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Versions Check")
        root.attributes('-topmost', True)

        # Результирующий список в который добавляются все значения проверки, далее сортируются по номеру и печатаются в текстовый файл.
        self.result_list = {}
        self.result_list_except = {}  # Отчеты которые не идут в сверку общего количества шотов
        self.failed_paths = [] # Список с неопределенными путями. Идут в отчет GUI  
        self.failed_names = set() # Список номеров шотов неопределенных путей. Нужны для сверки данных из таймлайна с данными из контрольного списка
        self.rows = 0 # Количество шотов в контрольном списке

        window_width = 550
        window_height = 700

        screen_width = root.winfo_screenwidth()
        screen_height = root.winfo_screenheight()
        x = (screen_width // 2) - (window_width // 2)
        y = int((screen_height * 7 / 10) - (window_height / 2))
        root.geometry(f"{window_width}x{window_height}+{x}+{y}")

        self.file_path = tk.StringVar()
        self.result_path = tk.StringVar()
        self.start_track = tk.StringVar(value="2")
        self.end_track = tk.StringVar(value="10")
        self.sheet_name = tk.StringVar(value="Sheet2")
        self.reel_name = tk.StringVar(value='0')
        self.column_reel = tk.StringVar(value='B')
        self.column_letter = tk.StringVar(value="A")
        self.file_type = tk.StringVar(value="xlsx") 

        self.failed_paths_text = scrolledtext.ScrolledText(root, height=15)
        self.failed_paths_text.pack(side="top", fill="both", expand=True, padx=0, pady=0)
        self.failed_paths_text.insert("1.0", "Здесь будут показаны имена шотов, которые не удалось определить.\n")
        self.failed_paths_text.config(state="normal")

        tk.Label(root, text="Choose input file:", font=("Arial", 13, "bold")).pack()
        tk.Entry(root, textvariable=self.file_path, width=50).pack()
        tk.Button(root, text="Choose", command=self.select_file).pack()
        
        tk.Label(root, text="Choose output path:", font=("Arial", 13, "bold")).pack()
        tk.Entry(root, textvariable=self.result_path, width=50).pack()
        tk.Button(root, text="Choose", command=self.select_result_path).pack()

        tk.Label(root, text="Source:", font=("Arial", 13, "bold")).pack()
        file_type_frame = tk.Frame(root)
        file_type_frame.pack()
        tk.Radiobutton(file_type_frame, text="Excel (XLSX)", variable=self.file_type, value="xlsx").pack(side=tk.LEFT, padx=5)
        tk.Radiobutton(file_type_frame, text="CSV", variable=self.file_type, value="csv").pack(side=tk.LEFT, padx=5)       

        tk.Label(root, text="Reel number:", font=("Arial", 13, "bold")).pack(pady=3)
        reel_number = tk.Frame(root)
        reel_number.pack()
        tk.Entry(reel_number, textvariable=self.reel_name, width=5).pack(side=tk.LEFT)

        tk.Label(root, text="Resolve tracks range", font=("Arial", 13, "bold")).pack(pady=3)
        track_frame = tk.Frame(root)
        track_frame.pack()
        tk.Label(track_frame, text="in:").pack(side=tk.LEFT)
        tk.Entry(track_frame, textvariable=self.start_track, width=5).pack(side=tk.LEFT, padx=5)
        tk.Label(track_frame, text="out:").pack(side=tk.LEFT)
        tk.Entry(track_frame, textvariable=self.end_track, width=5).pack(side=tk.LEFT)

        tk.Label(root, text="Data from Excel", font=("Arial", 13, "bold")).pack(pady=3)
        sheet_frame = tk.Frame(root)
        sheet_frame.pack()
        tk.Label(sheet_frame, text="Sheet:").pack(side=tk.LEFT)
        self.sheet = tk.Entry(sheet_frame, textvariable=self.sheet_name, width=15)
        self.sheet.pack(side=tk.LEFT, padx=5)
        tk.Label(sheet_frame, text="Reel:").pack(side=tk.LEFT)
        self.reel = tk.Entry(sheet_frame, textvariable=self.column_reel, width=5)
        self.reel.pack(side=tk.LEFT, padx=5)
        tk.Label(sheet_frame, text="Shots:").pack(side=tk.LEFT)
        self.shots = tk.Entry(sheet_frame, textvariable=self.column_letter, width=5)
        self.shots.pack(side=tk.LEFT, padx=5)
        
        self.result_label = tk.Label(root, text="Checked 0 from 0 shots", font=("Arial", 17, "bold"))
        self.result_label.pack()
        tk.Button(root, text="Start", command=self.run_script,  width=30, height=1).pack(pady=5)

        # Привязываем функцию к изменениям состояний чекбоксов
        self.file_type.trace_add("write", lambda *args: self.update_fields_state())

    def update_fields_state(self):

        """ 
        Блокирует или разблокирует поля в зависимости от состояния радиобатн
        """
        if self.file_type.get() == "csv":
            # Если включен "Set locators", блокируем оба поля
            self.sheet.config(state="disabled")
            self.reel.config(state="disabled")
            self.shots.config(state="disabled")
        else:
            self.sheet.config(state="normal")
            self.reel.config(state="normal")
            self.shots.config(state="normal")

    def update_result_label(self):
        len_res_list = len([j for i in self.result_list.values() for j in i])
        self.result_label.config(text=f"Проверено {len_res_list + len(self.failed_names)} шотов из {self.rows or 0}")

    def select_file(self):
        file_types = [("Excel files", "*.xlsx"), ("CSV files", "*.csv")]
        file_path = filedialog.askopenfilename(filetypes=file_types)
        self.file_path.set(file_path)
    
    def select_result_path(self):
        folder_path = filedialog.askdirectory()
        self.result_path.set(folder_path)

    def update_failed_paths(self):
        integers = count(1)
        num_failed_paths = [f'{number}) {string_}' for number, string_ in zip(integers, self.failed_paths)]
        self.failed_paths_text.delete(1.0, tk.END)
        self.failed_paths_text.insert(tk.END, "\n".join(num_failed_paths))

    
    
    def run_script(self):
        
        # Проверка ввода для start_track и end_track
        try:
            start_track = int(self.start_track.get())
            end_track = int(self.end_track.get())
        except ValueError:
            messagebox.showwarning("Ошибка ввода", "Диапазон треков должен быть числом!")
            start_track, end_track = 2, 10
            self.start_track.set(str(start_track))
            self.end_track.set(str(end_track))

        # Инициализация Resolve
        resolve = DaVinciResolveScript.scriptapp("Resolve")
        project_manager = resolve.GetProjectManager()
        project = project_manager.GetCurrentProject()
        media_pool = project.GetMediaPool()
        cur_bin = media_pool.GetCurrentFolder()
        clip_list = cur_bin.GetClipList()
        timeline = project.GetCurrentTimeline()

        # Паттерны на поиск имен шотов
        pattern_short = r'(?<!\d)(?:..._)?\d{3,4}[a-zA-Z]?_\d{1,4}(?!\d)' # Короткое имя 001_0010 или prk_001_0010
        pattern_long = r'(?<!\d)(?:[a-zA-Z]+_)*\d{3,4}[a-zA-Z]?_\d{1,4}(?:_[a-zA-Z]+)*?_v?\d+\w*(?!\d)'  # Имя с версией 001_0010_comp_v001 или prk_001_0010_comp_v001
        pattern_shot_number = r'\d{3,4}[a-zA-Z]?_\d+' # Чистый номер без префиксов, если таковые есть 001_0010
        pattern_real_shot = r'(.+_)?\d{1,4}[a-zA-Z]?_\d{1,4}_.+' # Легкая маска, для отбрасывания .exr файлов которые не относятся к шотам. Например титры.

        # Получение имен шотов из маркеров из поля 'note'
        # Приведение всех номеров в маркерах к чистым числовым значениям для унификации. prk_001_0010 добавится как 001_0010. Если изначально 001_0010 - то так и добавится
        markers_list = []
        for _, j in timeline.GetMarkers().items():
            j = j['note'].strip()
            if j != '' and re.search(pattern_short, j):
                markers_list.append(re.search(pattern_shot_number, j).group(0))
        
        print("Данные маркеров:", markers_list, sep="\n") # Отладка

        def is_dublicate(check_list: list):
            # Обработка дубликатов
            find_dublicates = dict(filter(lambda x: x[1] >= 2, Counter(check_list).items()))
            if find_dublicates:
                for shot, _ in find_dublicates.items():
                    self.rows -= 1
                    self.failed_paths.append(f"Найден дубликат шота {shot}")

        def read_column_from_excel(): 
            dublicate_shot = []
            '''
            Получение данных из .xlsx файла
            '''
            try: 
                # Открываем файл Excel 
                workbook = openpyxl.load_workbook(self.file_path.get()) 
                sheet = workbook[self.sheet_name.get()]

                # Проверка по конкретному рилу из контрольного списка
                if int(self.reel_name.get()) != 0:
                    reel_shot = list(zip(sheet[self.column_reel.get()], sheet[self.column_letter.get()]))
                    column_data = {}
                    # Считываем данные из списка кортежей (рил, шот)
                    for reel, shot in reel_shot:
                        if reel.value is not None:
                            if re.search(self.reel_name.get(), reel.value):
                                if shot.value is not None and shot.value != '':
                                    self.rows += 1
                                    try:
                                        column_data[re.search(pattern_short, shot.value).group(0).lower()] = re.search(pattern_long, shot.value).group(0).lower()
                                        dublicate_shot.append(re.search(pattern_short, shot.value).group(0).lower())
                                    except AttributeError:
                                        self.failed_paths.append(f"Имя {shot.value} не опознано")
                                        self.failed_names.add(f"Имя {shot.value} не опознано")

                # Проверка всего контрольного списка
                else:
                    column_data = {}
                    # Считываем данные из указанного столбца 
                    for shot in sheet[self.column_letter.get()]:
                        if shot.value is not None and shot.value != '':
                            self.rows += 1
                            try:
                                column_data[re.search(pattern_short, shot.value).group(0).lower()] = re.search(pattern_long, shot.value).group(0).lower()
                                dublicate_shot.append(re.search(pattern_short, shot.value).group(0).lower())
                            except AttributeError:
                                self.failed_paths.append(f"Имя {shot.value} не опознано")
                                self.failed_names.add(f"Имя {shot.value} не опознано")

                is_dublicate(dublicate_shot)
                return column_data 
            except Exception as e: 
                traceback.print_exc()
                raise

        def read_column_from_csv():
            '''
            Получение данных из .csv файла
            '''
            dublicate_shot = []
            try:
            # Открываем csv с данными по плейлисту из Шотгана и получаем словарь с парами ключ: значение. Имя шота с версией и имя шота без версии. {001_0010_comp_v001 : 001_0010, ...} 
                with open(self.file_path.get(), encoding='utf-8') as f:
                    file = csv.DictReader(f, delimiter=',')
                    
                    # Проверка всего контрольного списка
                    if int(self.reel_name.get()) != 0:
                        play_list = {}
                        for i in file:
                            self.rows += 1
                            if not i['Path to EXR'] and not i['Path to Frames'] and re.search(self.reel_name.get(), i['Reel']): # Если нет адресов
                                self.failed_paths.append(f"Отсутствуют данные о шоте {i['Entity']}")
                                self.failed_names.add(i['Entity'])
                                continue
                            if i['Path to EXR'] and re.search(self.reel_name.get(), i['Reel']): # Ищется в первую очередь
                                try:
                                    play_list[re.search(pattern_short, i['Path to EXR']).group(0)] = re.search(pattern_long, i['Path to EXR']).group(0)
                                    dublicate_shot.append(re.search(pattern_short, i['Path to EXR']).group(0))
                                except AttributeError:
                                    pass # Ничего не делать. Переходим к проверке Path to Frames
                            if not i['Path to EXR'] and re.search(self.reel_name.get(), i['Reel']):   # Если нет хайреза
                                try:
                                    play_list[re.search(pattern_short, i['Path to Frames']).group(0)] = re.search(pattern_long, i['Path to Frames']).group(0)
                                    dublicate_shot.append(re.search(pattern_short, i['Path to EXR']).group(0))
                                except AttributeError:
                                    self.failed_paths.append(f"Имя {i['Path to Frames']} не опознано")
                                    self.failed_names.add(i['Entity'])
                            
                    else:
                        play_list = {}
                        for i in file:
                            self.rows += 1
                            if not i['Path to EXR'] and not i['Path to Frames']: # Если нет адресов
                                self.failed_paths.append(f"Отсутствуют данные о шоте {i['Entity']}")
                                self.failed_names.add(i['Entity'])
                                continue
                            if i['Path to EXR']: # Ищется в первую очередь
                                try:
                                    play_list[re.search(pattern_short, i['Path to EXR']).group(0)] = re.search(pattern_long, i['Path to EXR']).group(0)
                                    dublicate_shot.append(re.search(pattern_short, i['Path to EXR']).group(0))
                                except AttributeError:
                                    pass # Ничего не делать. Переходим к проверке Path to Frames
                            if not i['Path to EXR']:   # Если нет хайреза
                                try:
                                    play_list[re.search(pattern_short, i['Path to Frames']).group(0)] = re.search(pattern_long, i['Path to Frames']).group(0)
                                    dublicate_shot.append(re.search(pattern_short, i['Path to Frames']).group(0))
                                except AttributeError:
                                    self.failed_paths.append(f"Имя {i['Path to Frames']} не опознано")
                                    self.failed_names.add(i['Entity'])
                is_dublicate(dublicate_shot)
                return play_list
            except Exception as e: 
                traceback.print_exc()
                raise

        def is_compare(all_cg_items, markers_list, result_path):
            try:
                # Если тип файла .xlsx данные берутся из функции ead_column_from_excel, в противном случае данные берутся из csv из функции read_column_from_csv
                play_list = read_column_from_excel() if self.file_type.get() == "xlsx" else read_column_from_csv()
                print(play_list)

                # Проходимся циклом по списку шотов из таймлайна. Получаем имя шота с версией и имя шота без версии.
                timeline_items = {}
                for item in all_cg_items:
                    if item.GetName().endswith(('.exr', '.mov', '.jpg')) and re.search(pattern_real_shot, item.GetName()): # С таймлайна берутся только .exr которые являются шотами
                        name_item_long = re.search(pattern_long, item.GetName()).group(0).lower() 
                        name_item_short = re.search(pattern_short, item.GetName()).group(0).lower() 
                        print(name_item_short, name_item_long)  
                        timeline_items.setdefault(name_item_short, []).append(name_item_long)

                # Сверяем данные из контрольного списк с данными из таймлайна
                for pl_shot in play_list:
                    if pl_shot in timeline_items :
                        if play_list[pl_shot] in timeline_items[pl_shot]:
                            self.result_list.setdefault("Стоит актуальная версия шота:", []).append(play_list[pl_shot])
                        else:
                            self.result_list.setdefault("Текущая версия шота не актуальна:", []).append(f"Версия в сверке - {play_list[pl_shot]}. На таймлайне присутствуют версии: {timeline_items[pl_shot]}")
                    else:
                        self.result_list.setdefault("Шот есть в контрольном списке, но нет на таймлайне:", []).append(play_list[pl_shot])

                # Сверяем данные из таймлайна с данными из контрольного списка
                for tmln_shot in timeline_items:
                    if tmln_shot not in play_list and tmln_shot not in self.failed_names:
                        self.result_list_except.setdefault("Шот отсутствует в контрольном списке:", []).append(tmln_shot)

                ''' Проверка на отсутствие графики на таймлайне и в контрольном списке.
                Пересбор словаря с номерами шотов в ключах без префиксов для унификации. prk_001_0010 добавится как 001_0010. 
                Если изначально 001_0010 - то так и добавится.
                Список маркеров и словарь с шотами с таймлайна и контрольного списка приведены к одному значению - 001_0010'''       
                play_list_dict_for_markers = {re.search(pattern_shot_number, k).group(0).lower(): j for k, j in play_list.items()}
                timeline_dict_for_markers = {re.search(pattern_shot_number, k).group(0).lower(): j for k, j in timeline_items.items()}
                for marker in markers_list:          
                    if marker not in play_list_dict_for_markers and marker not in timeline_dict_for_markers: 
                        self.result_list_except.setdefault('Шот отсутствует на таймлайне и в контрольном списке:', []).append(marker)          
                
                print("Данные плейлиста:", *play_list_dict_for_markers, sep="\n") # Отладка
               
                with open(result_path, 'a', encoding='utf-8') as o:
                    o.write(self.reel_name.get() + " РИЛ" + "\n")
                    full_result_list = self.result_list_except | self.result_list
                    for key, value in full_result_list.items():
                        o.write("\n" + key + "\n\n") 
                        for item in value:
                            o.write(item + "\n")
                    o.write("_"* 80 + '\n\n')
            except Exception as e:
                traceback.print_exc()
                raise

        # Собираем в список шоты(Объекты Blackmagic) с таймлайнов 
        all_cg_items = []
        for i in range(int(self.start_track.get()), int(self.end_track.get()) + 1):
            all_cg_items += timeline.GetItemListInTrack('video', i)
        
        # Формирования пути для финального .txt файла
        result_file_path = os.path.join(self.result_path.get(), f'result_{date.today()}.txt')

        # Передача в основную функцию списка таймлайн итемов, списка маркеров, файловых путей, листа и столбца из exel
        try:
            is_compare(all_cg_items, markers_list, result_file_path)
            self.update_failed_paths() # Выводим в GUI данные о неопознанных именах шотов
            self.update_result_label() # Обновляем количество проверенных шотов
            self.rows = 0 # Обнуляем контрольное количество шотов 
            # Обнуляем все списки
            self.result_list = {}
            self.result_list_except = {} 
            self.failed_paths = [] 
            self.failed_names = [] 
            messagebox.showinfo("Готово", "Проверка завершена!")
        except Exception as e:
            traceback.print_exc()
            messagebox.showinfo("Ошибка", f"Ошибка {e}")

if __name__ == "__main__":
    root = tk.Tk()
    app = VersionCheckerApp(root)
    root.mainloop()

'''
Доработать паттерны
Прибрать вывод в функцию
'''