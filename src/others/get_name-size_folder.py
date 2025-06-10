import os

def get_clip_info(target_path):
    for clip in os.listdir(target_path):
        clip_path = os.path.join(target_path, clip)
        if os.path.isdir(clip_path):
            total_file_size = 0
            for seq_frame_path in os.listdir(clip_path):
                total_file_size += os.path.getsize(os.path.join(clip_path, seq_frame_path))
            print(os.path.basename(seq_frame_path), total_file_size)
        if os.path.isfile(clip_path):
            print(os.path.basename(clip_path), os.path.getsize(clip_path))

if __name__ == "__main__":
    target_path = r"R:\CC_PROROK\TRIM\REEL_08_20240828"
    get_clip_info(target_path)