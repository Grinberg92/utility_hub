from copy import deepcopy
from config.global_config import GLOBAL_CONFIG
from config.local_configs import LOCAL_CONFIGS
from config.config import update_config

def merge_dicts(base: dict, override: dict) -> dict:
    """
    Объединяет глобальные и локальные конфиги проектов.
    """
    result = deepcopy(base)
    for key, value in override.items():
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            result[key] = merge_dicts(result[key], value)
        else:
            result[key] = value
    return result

def load_config(project_name: str = None):
    """
    Получает результирующий конфиг проекта.
    """
    local = LOCAL_CONFIGS.get(project_name, {})
    final = merge_dicts(GLOBAL_CONFIG, local)
    update_config(final)
