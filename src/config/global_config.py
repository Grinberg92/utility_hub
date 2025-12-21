"""
Глобальный конфиг Autoconform.
"""
  
GLOBAL_CONFIG = {
    "paths": {
        "root_projects_mac": r"/Volumes/share2/003_transcode_to_vfx/projects",
        "root_projects_win": r"J:/003_transcode_to_vfx/projects",
        "project_path": "003_transcode_to_vfx/projects/",
        "log_path": "003_transcode_to_vfx/projects/log.log",
        "init_project_root_win": "J:/",
        "init_project_root_mac": "/Volumes/share2/",
        "init_shots_root_win": "R:/",
        "init_shots_root_mac": "/Volumes/RAID/",
    },
    "patterns": {
        "frame_number": r'(\d+)(?:\.|_)\w+$',               # для кадров [1001.exr] или [1001_exr]
        "shot_name": r'(\.|_)\d+\.\w+$',                   # 015_3030_comp_v002.1004.exr и 015_3030_comp_v002_1004.exr
        "shot_name_split": r'(.+?)([\._])\[(\d+)-\d+\]\.\w+$', # Парсинг имени секвенции. Префикс, суффикс и стартовый фрэйм
        "compare_versions_shot_versions_mask": r'(?<!\d)(?:[a-zA-Z]+_)*\d{3,4}[a-zA-Z]?_\d{1,4}[a-zA-Z]?(?:_[a-zA-Z]+)*?(_[a-zA-Z]+)?_[vV]?\d+(?!\d)',  # Имя с версией 001_0010_comp_v001 или prk_001_0010_comp_v001
        "compare_versions_shot_no_versions_mask": r'(?<![A-Za-z0-9])(?:[A-Za-z]+_)?\d{3,4}[A-Za-z]?_\d{1,4}[A-Za-z]?(?![A-Za-z0-9/])', # Короткое имя только prk_001_0010, 001_0010, 001_001c
        "compare_versions_shot_soft_mask": r'(.+_)?\d{1,4}[a-zA-Z]?_\d{1,4}[a-zA-Z]?_.+', # Легкая маска, для отбрасывания .exr файлов которые не относятся к шотам. Например титры
        "compare_versions_shot_no_prefix_mask": r'\d{3,4}[a-zA-Z]?_\d{1,4}[a-zA-Z]?' # Чистый номер без префиксов, если таковые есть 001_0010
    },
    "output_folders": {
        "sequence_checker": "sequence_checker"
    }   
}