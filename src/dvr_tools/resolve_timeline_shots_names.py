import re
from collections import Counter
import DaVinciResolveScript as dvr

def get_resolve_shot_list(track_in, track_out, extension, pattern=None):
    """
    Получает список шотов из таймлайна DaVinci Resolve.
    
    :param track_in: начальный трек (int)
    :param track_out: конечный трек (int)
    :param extension: формат, например 'exr'
    :param pattern: кастомный regex фильтр по имени
    :return: Counter с именами шотов
    """
    try:
        resolve = dvr.scriptapp("Resolve")
        project = resolve.GetProjectManager().GetCurrentProject()
        timeline = project.GetCurrentTimeline()

        if pattern is None:
            pattern = r'(.+_)?\d{1,4}[a-zA-Z]?_\d{1,4}_.+'

        all_cg_items = []
        for track in range(track_in, track_out + 1):
            all_cg_items += timeline.GetItemListInTrack('video', track)

        filtered = [
            item.GetName()
            for item in all_cg_items
            if item.GetName().lower().endswith(f".{extension.lower()}") and re.search(pattern, item.GetName())
        ]
        return Counter(filtered)
    except Exception as e:
        print(f"Ошибка подключения к API Resolve: {e}")
        return []
