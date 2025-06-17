import logging
import os
import platform
import getpass
import socket

def get_logger(name: str) -> logging.Logger:
    logger = logging.getLogger(name)
    logger.setLevel(logging.DEBUG)  # Уровень логирования

    if logger.handlers:
        return logger

    # Пути под Windows и macOS
    mac_log_path = "/Volumes/share2/003_transcode_to_vfx/projects"
    win_log_path = r"J:\003_transcode_to_vfx\projects"
    base_path = mac_log_path if platform.system() != "Windows" else win_log_path
    os.makedirs(base_path, exist_ok=True)
    log_file = os.path.join(base_path, "log.log")

    # Получение имени пользователя и хоста
    user = getpass.getuser()
    hostname = socket.gethostname()

    # Создание хендлера
    file_handler = logging.FileHandler(log_file, encoding='utf-8')
    stream_handler = logging.StreamHandler()

    # Форматтер с уже подставленными user и hostname
    log_format = f"%(asctime)s | %(levelname)s | {user}@{hostname} | %(name)s | %(message)s"
    formatter = logging.Formatter(log_format, datefmt="%Y-%m-%d %H:%M:%S")

    file_handler.setFormatter(formatter)
    stream_handler.setFormatter(formatter)

    logger.addHandler(file_handler)
    logger.addHandler(stream_handler)

    return logger
