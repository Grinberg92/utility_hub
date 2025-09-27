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
        self.resolve_root_folder = self.resolve_mediapool.GetRootFolder()  
        self.resolve_mediapool_current_folder = self.resolve_mediapool.GetCurrentFolder()

    @property
    def resolve_obj(self):
        return self.resolve

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
    def root_folder(self):
        return self.resolve_root_folder
    
    @property
    def mediapool_current_folder(self):
        return self.resolve_mediapool_current_folder

import re
from collections import Counter
import DaVinciResolveScript as dvr

def get_resolve_shot_list(start_track: int, end_track: int, extension: str, pattern: str = None) -> Counter:
    """
    Возвращает список имён клипов с верхнего трека в указанном диапазоне.
    Если несколько клипов стоят в стеке, берётся тот, что выше по номеру трека.
    """
    try:
        resolve = dvr.scriptapp("Resolve")
        project = resolve.GetProjectManager().GetCurrentProject()
        timeline = project.GetCurrentTimeline()

        if not timeline:
            return Counter()

        if pattern is None:
            pattern = r'(.+_)?\d{1,4}[a-zA-Z]?_\d{1,4}_.+'
        regex = re.compile(pattern)

        top_items = {}
        # идём сверху вниз, чтобы нижние не перезаписывали верхние
        for track_index in range(end_track, start_track - 1, -1):
            clips = timeline.GetItemListInTrack('video', track_index)

            for clip in clips:
                start, end = clip.GetStart(), clip.GetStart() + clip.GetDuration()

                if not any(s <= start < e or start <= s < end for s, e in top_items.keys()):
                    top_items[(start, end)] = clip

        # Фильтрация по расширению и паттерну
        filtered = [
            clip.GetName()
            for clip in top_items.values()
            if clip.GetName().lower().endswith(f".{extension.lower()}") and regex.search(clip.GetName())
        ]

        return Counter(filtered)

    except Exception as e:
        print(f"Ошибка подключения к API Resolve: {e}")
        return Counter()

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





