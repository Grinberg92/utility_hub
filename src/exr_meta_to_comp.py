import DaVinciResolveScript as dvr
import csv

resolve = dvr.scriptapp("Resolve")
project_manager = resolve.GetProjectManager()
project = project_manager.GetCurrentProject()
media_pool = project.GetMediaPool()
timeline = project.GetCurrentTimeline()
root_folder = media_pool.GetRootFolder()

def get_mediapoolitems(start_track, end_track):
        # Получение списка кортежей с атрибутами timelineitems
        all_items = []
        for track in range(start_track, end_track + 1):
            clips = timeline.GetItemListInTrack('video', int(track))
            for clip in clips:
                all_items.append(clip.GetMediaPoolItem())
        return all_items

def get_camera_name(obj):
    if obj.GetClipProperty("Clip Name")[0:2] in ("A_", "B_", "C_", "D_", "X_"):
        return "Alexa 35" 
    if obj.GetClipProperty("Clip Name")[0:2] in ("H0", "S0"):
        return "DJI FC4280"
    if obj.GetClipProperty("Clip Name")[0:2] in ("BM", "bm"):
        return "Blackmagic Pocket Cinema Camera 6K G2"
    if obj.GetClipProperty("Clip Name")[0:2] in ("D0"):
        return "DJI Zemuse X7"
    if obj.GetClipProperty("Clip Name")[0:2] in ("F0", "f0"):
        return "F_camera"
    if obj.GetClipProperty("Clip Name")[0:2] in ("GX", "gx"):
        return "GoPro"
    

def export_csv(meta_tuple):
    with open('empire_meta.csv', "a", newline="", encoding="utf-8") as output:
        writer = csv.writer(output, quotechar='"', delimiter=";")
        writer.writerow(("Clip_name", "Camera_name", "Resolution", "PAR"))
        writer.writerows(meta_tuple)

def extract_meta(mp_items):
    property_list = []
    for obj in mp_items:
        property_list.append((obj.GetClipProperty("Clip Name")[0], get_camera_name(obj), obj.GetClipProperty("Resolution"), obj.GetClipProperty("PAR")))
    export_csv(property_list)

media_pool_items = get_mediapoolitems(1,5)
extract_meta(media_pool_items)
