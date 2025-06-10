# Импорт API DaVinci Resolve
import DaVinciResolveScript  

# Инициализация Resolve
resolve = DaVinciResolveScript.scriptapp("Resolve")
project_manager = resolve.GetProjectManager()
project = project_manager.GetCurrentProject()
media_pool = project.GetMediaPool()
cur_bin = media_pool.GetCurrentFolder()
clip_list = cur_bin.GetClipList()
timeline = project.GetCurrentTimeline()
markers = timeline.GetMarkers()

print(f'Количество клипов в текущем бине: {len(clip_list)}')
print(f'Количество клипов в текущем таймлайне: {len(timeline.GetItemListInTrack("video", 1))}')