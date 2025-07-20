CONFIG = {}

def update_config(new_config: dict):
    """
    Загружает в CONFIG актуальный конфиг с учетом локальных настроек проекта.
    """
    global CONFIG
    CONFIG = new_config

def get_config():
    """
    Возвращает актуальный конфиг проекта.
    """
    return CONFIG