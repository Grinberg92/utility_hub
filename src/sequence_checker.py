import os
import numpy as np
import OpenImageIO as oiio
from concurrent.futures import ThreadPoolExecutor
import argparse
import sys

# --- Функция чтения EXR-файлов ---
def read_exr(file_path):
    """Читает EXR-файл и возвращает numpy-массив или None при ошибке."""
    try:
        inp = oiio.ImageInput.open(file_path)
        if not inp:
            return None

        spec = inp.spec()
        pixels = inp.read_image(oiio.FLOAT)
        inp.close()

        if pixels is None or spec is None:
            return None

        return np.array(pixels)
    except Exception as e:
        return None

# --- Функция обработки пары кадров ---
def process_frame_pair(file_pair):
    """Обрабатывает пару кадров и возвращает информацию об артефактах."""
    prev_path, curr_path = file_pair
    tolerance = 0.0001
    try:
        prev_frame = read_exr(prev_path)
        curr_frame = read_exr(curr_path)

        if prev_frame is None or curr_frame is None:
            return (prev_path, curr_path, f"Ошибка: Не удалось открыть кадр {os.path.basename(prev_path)} или {os.path.basename(curr_path)}.")

        # Вычисляем разницу между кадрами
        diff_np = np.abs(curr_frame - prev_frame)
        mean_diff = np.mean(diff_np)

        # Проверка на фриз-фреймы
        if mean_diff < tolerance:
            return (prev_path, curr_path, f"Найдены фриз-фреймы между кадрами {os.path.basename(prev_path)} и {os.path.basename(curr_path)}.")

    except Exception as e:
        return (prev_path, curr_path, f"Ошибка при обработке кадров {os.path.basename(prev_path)}: {e}")
    
    return None


# --- Функция сканирования папок ---
def scan_folders(root_folder, output_path, extention):

    messages = []  # Список для хранения всех сообщений об ошибках иы фриз-фреймах

    if extention not in ["exr", "jpg"]:
        sys.exit(2)

    for folder, _, files in os.walk(root_folder):
        exr_files = sorted([f for f in files if f.endswith(f".{extention}")])
        if len(exr_files) < 2:
            continue

        file_pairs = [(os.path.join(folder, exr_files[i]),
                        os.path.join(folder, exr_files[i + 1])) for i in range(len(exr_files) - 1)]

        with ThreadPoolExecutor() as executor:
            results = executor.map(process_frame_pair, file_pairs)

        for result in results:
            if result:
                messages.append(result)
    if messages:
        with open(output_path, "w", encoding="utf-8") as o:
            o.write("\n".join(i[2] for i in messages))
        sys.exit(1)
    else:        
        sys.exit(0)

# --- Запуск приложения ---
if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="check EXR")
    parser.add_argument('exr_folder', type=str, help="Input exrs folder")
    parser.add_argument("output_path", type=str, help="result output to storage")
    parser.add_argument("extention", type=str, help="sequence extention (exr or jpg)")
    args = parser.parse_args()
    scan_folders(args.exr_folder, args.output_path, args.extention)
    
