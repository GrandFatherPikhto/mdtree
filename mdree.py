#!/usr/bin/env python3
import os
import json
import fnmatch
import argparse  # Добавили для создания хелпа
from datetime import datetime
from pathlib import Path

# Текст встроенной краткой справки по JSON для вывода в --help
CONFIG_HELP_TEXT = """
💡 Структура файла конфигурации (tree_config.json):
{
  "depth": null,               // Ограничение глубины (число или null)
  "only_dirs": false,          // Показывать только директории (true/false)
  "output_file": "docs/TREE.md",// Куда сохранять Markdown (строка или null)
  "ignore_names": [".git"],    // Глобальный черный список по имени
  "ignore_paths": [],          // Черный список по относительным путям
  "ignore_extensions": [],     // Скрывать по расширению (например, [".pyc"])
  "ignore_masks": ["RAISE*"],  // Скрывать по маске со звездочкой
  "allow_only": {              // Белый список (изоляция веток)
    "NAFNet/options": ["train"]
  },
  "descriptions": {            // Инлайн-комментарии через символ '#'
    "NAFNet": "Основной репозиторий архитектуры NAFNet"
  }
}
"""

def load_config(config_file="tree_config.json"):
    """Загружает параметры из JSON-файла или использует дефолтные."""
    defaults = {
        "depth": None,
        "only_dirs": False,
        "output_file": None,
        "ignore_names": [".git", "__pycache__", ".venv"],
        "ignore_paths": [],
        "ignore_extensions": [],
        "ignore_masks": [],
        "allow_only": {},
        "descriptions": {}
    }
    if os.path.exists(config_file):
        with open(config_file, "r", encoding="utf-8") as f:
            try:
                config = json.load(f)
                for key in defaults:
                    if key in config:
                        defaults[key] = config[key]
            except json.JSONDecodeError:
                print("⚠️ Ошибка чтения JSON. Используются дефолтные настройки.")
    
    defaults["ignore_names"] = set(defaults["ignore_names"])
    defaults["ignore_paths"] = set(defaults["ignore_paths"])
    defaults["ignore_extensions"] = set(defaults["ignore_extensions"])
    return defaults

def format_size(size_bytes):
    """Преобразует размер в байтах в человекочитаемый формат."""
    if size_bytes == 0:
        return "0 Б"
    size_name = ("Б", "КБ", "МБ", "ГБ")
    import math
    i = int(math.floor(math.log(size_bytes, 1024)))
    p = math.pow(1024, i)
    s = round(size_bytes / p, 1)
    return f"{s} {size_name[i]}"

def build_tree(dir_path, root_path=None, config=None, current_depth=1):
    """Рекурсивно строит дерево директорий на основе JSON-конфига."""
    if config is None:
        config = load_config()
    if root_path is None:
        root_path = Path(".").absolute()

    path = Path(dir_path).absolute()
    try:
        current_rel_path = str(path.relative_to(root_path)).replace("\\", "/")
    except ValueError:
        current_rel_path = ""

    if config["depth"] is not None and current_depth > config["depth"]:
        return {}

    tree = {}

    try:
        items = sorted(list(path.iterdir()), key=lambda x: x.name)
    except PermissionError:
        return tree

    cleaned_current_path = current_rel_path.lstrip("./")

    for item in items:
        rel_path = item.relative_to(root_path)
        rel_path_str = str(rel_path).replace("\\", "/") 

        config_allow = config["allow_only"].get(current_rel_path) or config["allow_only"].get(cleaned_current_path)
        if config_allow is not None:
            if item.name not in config_allow:
                continue
            
        if config["only_dirs"] and item.is_file():
            continue
        if item.name in config["ignore_names"]:
            continue
        if rel_path_str in config["ignore_paths"]:
            continue
        if item.is_file() and item.suffix in config["ignore_extensions"]:
            continue

        is_masked = False
        for mask in config["ignore_masks"]:
            if fnmatch.fnmatch(item.name, mask) or fnmatch.fnmatch(rel_path_str, mask):
                is_masked = True
                break
        if is_masked:
            continue

        desc = config["descriptions"].get(rel_path_str) or config["descriptions"].get(item.name, "")

        if item.is_dir():
            subtree = build_tree(item, root_path, config, current_depth + 1)
            tree[item.name] = {"type": "dir", "content": subtree, "desc": desc, "rel_path": rel_path_str}
        else:
            try:
                size = item.stat().st_size
                size_str = format_size(size)
            except FileNotFoundError:
                size_str = "0 Б"
            tree[item.name] = {"type": "file", "size": size_str, "desc": desc, "rel_path": rel_path_str}

    return tree

def render_tree(tree, prefix="", lines_list=None):
    """Рекурсивно собирает структуру дерева в список строк."""
    if lines_list is None:
        lines_list = []
        
    items = list(tree.keys())
    for i, name in enumerate(items):
        is_last = (i == len(items) - 1)
        connector = "└── " if is_last else "├── "
        
        node = tree[name]
        if node["type"] == "file":
            display_name = f"{name} ({node['size']})"
        else:
            display_name = name
            
        current_line = f"{prefix}{connector}{display_name}"
        
        if node["desc"]:
            current_line = f"{current_line:<50} # {node['desc']}"
            
        lines_list.append(current_line)
        
        if node["type"] == "dir":
            next_prefix = prefix + ("    " if is_last else "│   ")
            render_tree(node["content"], next_prefix, lines_list)
            
    return lines_list

if __name__ == "__main__":
    # Настраиваем красивый парсер аргументов командной строки
    parser = argparse.ArgumentParser(
        description="mdtree — Генератор структуры проекта в Markdown с фильтрами и комментариями.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=CONFIG_HELP_TEXT
    )
    parser.add_argument(
        "-c", "--config", 
        default="tree_config.json", 
        help="Путь к кастомному JSON-файлу конфигурации (по умолчанию: tree_config.json)"
    )
    
    args = parser.parse_args()
    
    # Загружаем конфиг, переданный через аргументы
    config = load_config(args.config)
    
    full_tree = build_tree(".")
    tree_lines = ["."] + render_tree(full_tree)
    
    for line in tree_lines:
        print(line)
        
    output_path_str = config.get("output_file")
    if output_path_str:
        output_file = Path(output_path_str)
        output_file.parent.mkdir(parents=True, exist_ok=True)
        
        now = datetime.now().strftime("%d.%m.%Y %H:%M")
        
        with open(output_file, "w", encoding="utf-8") as f:
            f.write("# Структура проекта\n\n")
            f.write(f"*Последнее обновление: {now}*\n\n")
            f.write("```text\n")
            f.write("\n".join(tree_lines) + "\n")
            f.write("```\n")
            
        print(f"\n✨ Файл успешно обновлен: {output_file.resolve()}")
