import opentimelineio as otio
import opentimelineio.adapters.cmx_3600 as cmx_3600
def convert_otio_to_edl(input_otio_path, output_edl_path):
    # Загрузка OTIO файла
    timeline = otio.adapters.read_from_file(input_otio_path)

    # Проверка, что загружен именно timeline
    if not isinstance(timeline, otio.schema.Timeline):
        raise TypeError("Файл не содержит Timeline.")

    # Экспорт в EDL
    edl_str = cmx_3600.write_to_string(timeline)

    with open(output_edl_path, "w") as f:
        f.write(edl_str)

    print(f"EDL успешно сохранён в {output_edl_path}")


# Пример использования
if __name__ == "__main__":
    convert_otio_to_edl(r"J:\003_transcode_to_vfx\projects\gorynych\TEST_MOV\mov_tst.otio", r"J:\003_transcode_to_vfx\projects\gorynych\TEST_MOV\mov_tst.edl")