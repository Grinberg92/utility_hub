import os
import platform
from pathlib import Path

def get_davinci_scripts_dir():
    if platform.system() == "Windows":
        return Path("C:/ProgramData/Blackmagic Design/DaVinci Resolve/Fusion/Scripts/Utility")
    elif platform.system() == "Darwin":  # macOS
        return Path("/Library/Application Support/Blackmagic Design/DaVinci Resolve/Fusion/Scripts/Utility")
    else:
        raise RuntimeError("Unsupported OS")

def link_scripts():
    project_scripts_dir = Path(__file__).resolve().parent.parent / "src"
    davinci_scripts_dir = get_davinci_scripts_dir()
    davinci_scripts_dir.mkdir(parents=True, exist_ok=True)

    # Удаляем старые симлинки
    for existing in davinci_scripts_dir.glob("*.py"):
        if existing.is_symlink():
            existing.unlink()
            print(f"Удалён старый симлинк: {existing.name}")

    for script in project_scripts_dir.glob("*.py"):
        link_path = davinci_scripts_dir / script.name
        if link_path.exists():
            print(f"Уже существует: {link_path.name}")
            continue
        try:
            link_path.symlink_to(script)
            print(f"Симлинк создан: {link_path} → {script}")
        except Exception as e:
            print(f"Ошибка при создании ссылки {link_path}: {e}")

if __name__ == "__main__":
    link_scripts()