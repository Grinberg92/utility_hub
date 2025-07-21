import DaVinciResolveScript as dvr
import re
from collections import Counter

class ResolveObjects:
    """
    Класс получает основные объекты резолв.

    """
    def __init__(self):
        self.resolve = dvr.scriptapp("Resolve")
        if self.resolve is None:
            raise RuntimeError("Ошибка подключения к Resolve")
        
        self.resolve_project_manager = self.resolve.GetProjectManager()
        self.resolve_project = self.resolve_project_manager.GetCurrentProject()
        self.resolve_mediapool = self.resolve_project.GetMediaPool()
        self.resolve_timeline = self.resolve_project.GetCurrentTimeline()
        self.resolve_mediapool_current_folder = self.resolve_mediapool.GetCurrentFolder()

    @property
    def timeline(self):
        return self.resolve_timeline
    
    @property
    def mediapool(self):
        return self.resolve_mediapool
    
    @property
    def project(self):
        return self.resolve_project
    
    @property
    def project_manager(self):
        return self.resolve_project_manager
    
    @property
    def mediapool_current_folder(self):
        return self.resolve_mediapool_current_folder

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

        timeline_shots = []
        for track in range(track_in, track_out + 1):
            timeline_shots += timeline.GetItemListInTrack('video', track)

        filtered = [
            item.GetName()
            for item in timeline_shots
            if item.GetName().lower().endswith(f".{extension.lower()}") and re.search(pattern, item.GetName())
        ]
        return Counter(filtered)
    except Exception as e:
        print(f"Ошибка подключения к API Resolve: {e}")
        return []

class ResolveTimelineItemExtractor():

    '''
    Класс получения resolve timelineitems и mediapoolitems
    '''
    def __init__(self, timeline):
        self.timeline = timeline

    def get_timeline_items(self, start_track: int, end_track: int, exceptions: tuple=None, mpitems: bool=False, track_type: str="video") -> list:
        '''
        Метод получает resolve timelineitems и mediapoolitems
        '''
        all_items = []
        for track in range(start_track, end_track + 1):
            clips = self.timeline.GetItemListInTrack(track_type, int(track))
            if exceptions is None:
                for clip in clips:
                    if mpitems:
                        all_items.append(clip.GetMediaPoolItem())
                    else:
                        all_items.append(clip)
            else:
                for clip in clips:
                    media_pool_item = clip.GetMediaPoolItem()
                    if not media_pool_item.GetName().lower().endswith(exceptions):
                        if mpitems:
                            all_items.append(clip.GetMediaPoolItem())
                        else:
                            all_items.append(clip)
        return all_items





