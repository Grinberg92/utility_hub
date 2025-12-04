"""
Локальный конфиг для проектов Autoconfom.
"""

LOCAL_CONFIGS = {
    "gorynych": {  # ГОРЫНЫЧ
        "paths": {
            "init_shots_root_win": "R:/CC_GORYNYCH/VFX",
            "init_shots_root_mac": "/Volumes/RAID/CC_GORYNYCH/VFX",
                }
            },
    'BOI': {  # Рождение империи
        'paths': {
            "init_shots_root_win": "R:\CC_BOE\VFX",
            "init_shots_root_mac": "/Volumes/RAID/CC_BOE/VFX",
                }
            },
    'cheburashka_2': { # Чебурашка
        'patterns': {
            "compare_versions_shot_versions_mask": r'(?<!\d)(?:[A-Za-z]\d{1,2})_[A-Za-z]+_\d{1,4}_[vV]?\d+(?!\d)',  # Имя с версией 001_0010_comp_v001 или prk_001_0010_comp_v001
            "compare_versions_shot_no_versions_mask": r'(?<![A-Za-z0-9])(?:[A-Za-z]\d{1,2})_[A-Za-z]+_\d{1,4}(?![A-Za-z0-9/])', # Короткое имя только prk_001_0010, 001_0010, 001_001c
            "compare_versions_shot_soft_mask": r'(?:[A-Za-z]\d{1,2})_[A-Za-z]+_\d{1,4}', # Легкая маска, для отбрасывания .exr файлов которые не относятся к шотам. Например титры
            "compare_versions_shot_no_prefix_mask": r'(?:[A-Za-z]\d{1,2})_[A-Za-z]+_\d{1,4}' # Чистый номер без префиксов, если таковые есть 001_0010
                }
            }
}