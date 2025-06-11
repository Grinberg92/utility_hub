
class ResolveTimelineItemExtractor():

    '''
    Класс получения resolve timelineitems и mediapoolitems
    '''
    def __init__(self, timeline):
        self.timeline = timeline

    def get_timeline_items(self, start_track: int, end_track: int, exceptions: tuple=None, mpitems: bool=False) -> list:
        '''
        Метод получает resolve timelineitems и mediapoolitems
        '''
        all_items = []
        for track in range(start_track, end_track + 1):
            clips = self.timeline.GetItemListInTrack('video', int(track))
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

if __name__ == "__main":
    ResolveTimelineItemExtractor()