"""
Глобальный конфиг Autoconform.
"""
  
GLOBAL_CONFIG = {
    
    "paths": {
        "root_projects_mac": r"/Volumes/share2/003_transcode_to_vfx/projects",
        "root_projects_win": r"J:/003_transcode_to_vfx/projects",
        "log_path_win": r"J:/003_transcode_to_vfx/projects/log.log",
        "log_path_mac": r"/Volumes/share2/003_transcode_to_vfx/projects/log.log",
        "editdatabase_path_mac": r"/Volumes/share2/003_transcode_to_vfx/projects/Others/projects_data.json",
        "editdatabase_path_win": r"J:\003_transcode_to_vfx\projects\Others\projects_data.json",
    },

    "patterns": {
        # для кадров [1001.exr] или [1001_exr]
        "frame_number": r'(\d+)(?:\.|_)\w+$',

        # 015_3030_comp_v002.1004.exr и 015_3030_comp_v002_1004.exr
        "shot_name": r'(\.|_)\d+\.\w+$',

        # Парсинг имени секвенции. Префикс, суффикс и стартовый фрэйм
        "shot_name_split": r'(.+?)([\._])\[(\d+)-\d+\]\.\w+$',

        # Имя с версией 001_0010_comp_v001; prk_001_0010_comp_v001; tst_0010_comp_v001; prk_001a_001a_comp_v001
        "compare_versions_shot_versions_mask": r'(?<!\d)(?:[a-zA-Z]+_)*(?:\d{3,4}[a-zA-Z]?|[a-zA-Z]{3,4})_\d{1,4}[a-zA-Z]?(?:_[a-zA-Z]+)*?(_[a-zA-Z]+)?_[vV]?\d+(?!\d)', 

        # Короткое имя только prk_001_0010, 001_0010, 001_001c, 001a_001c, tst_0010
        "compare_versions_shot_no_versions_mask": r'(?<![A-Za-z0-9])(?:[A-Za-z]+_)?(?:\d{3,4}[a-zA-Z]?|[a-zA-Z]{3,4})_\d{1,4}[A-Za-z]?(?![A-Za-z0-9/])', 

        # Легкая маска, для отбрасывания .exr файлов которые не относятся к шотам. Например титры
        "compare_versions_shot_soft_mask": r'(.+_)?(?:\d{3,4}[a-zA-Z]?|[a-zA-Z]{3,4})_\d{1,4}[a-zA-Z]?_.+', 

        # Чистый номер без префиксов, если таковые есть 001_0010
        "compare_versions_shot_no_prefix_mask": r'(?:\d{3,4}[a-zA-Z]?|[a-zA-Z]{3,4})_\d{1,4}[a-zA-Z]?', 
    },

    "output_folders": {

        "sequence_checker": "sequence_checker",
        "edit_database": "edit_database",
        "edl_processor": "edl_processor",
        "autoconform": "autoconform",
        "compare_versions": "compare_versions",
        "ocf_color_and_fps": "resolutions_table",
        "edl_filter": "edl_filter"  
    },

    "scripts_settings":{
        "autoconform": {"shots_path_win": r"R:/",
                        "shots_path_mac": r"/Volumes/RAID/"},
        "exr_delivery": {
                "track_postfix": '_VT',
                "colors": ["Orange", "Yellow", "Lime", "Violet", "Blue"],
                "extentions": (".mxf", ".braw", ".arri", ".r3d", ".dng", ".cine"),
                "false_extentions": (".mov", ".mp4", ".jpg"),
                "project_presets": ["aces1.2_smoother_preset", "yrgb_smoother_preset"],
                "copter_extentions": (".dng")
                    },
        "edl_processor": {
                "exceptions": ["RETIME WARNING"],
                "track_postfix": '_VT'
                    },
        "ocf_color_and_fps": {"clip_color": ['Orange', 'Yellow', 'Lime', 'Teal', 'Green', 'Purple', 'Navy',
                                'Apricot', 'Olive', 'Violet', 'Blue', 'Pink', 'Tan', 'Beige',
                                'Brown', 'Chocolate'],
                            "extentions": (".mxf", ".braw", ".arri", ".mov", ".r3d", ".mp4", ".dng", ".jpg", ".cine")
                    },
        "proxy_render": {
                "burn_in_win_path": r"J:\003_transcode_to_vfx\projects\Others\burn_in_presets",
                "burn_in_mac_path": r"/Volumes/share2/003_transcode_to_vfx/projects/Others/burn_in_presets",
                "lut_path_win": r'C:\ProgramData\Blackmagic Design\DaVinci Resolve\Support\LUT\LUTS_FOR_PROXY',
                "lut_path_mac": r'/Library/Application Support/Blackmagic Design/DaVinci Resolve/LUT/LUTS_FOR_PROXY/',
                "timeline_preset_path_win": r"J:\003_transcode_to_vfx\projects\Others\timeline_presets",
                "timeline_preset_path_mac": r"/Volumes/share2/003_transcode_to_vfx/projects/Others/timeline_presets/",
                "all_extentions": (".mxf", ".braw", ".arri", ".mov", ".r3d", ".mp4", ".dng", ".jpg", ".cine"),
                "standart_extentions": (".mxf", ".braw", ".arri", ".r3d", ".dng", ".cine"),
                "excepted_extentions": ('.mov', '.mp4', '.jpg')
            },
        "compare_versions": {"extentions": ('.exr', '.mov', '.jpg')},
        "get_shot": {"extentions": (".exr", ".jpg", ".tif", ".tiff", ".png")}
    }
}