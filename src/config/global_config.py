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
    }
}