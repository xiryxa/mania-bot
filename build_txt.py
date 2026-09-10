import os

# Папки и файлы, которые нужно исключить (только технические)
IGNORE_DIRS = {
    '__pycache__',
    '.venv',
    '.git',
    'downloads',    # если это загрузки, не исходники
    'files',        # аналогично
}
IGNORE_FILES = {
    '.env',
    'users.sqlite',
    'build_txt.py',
    'project_full.txt',
}
ALLOWED_EXTENSIONS = {
    '.py', '.txt', '.md', '.json', '.yml', '.yaml'
}

def collect_files(start_dir):
    result = {}
    for root, dirs, files in os.walk(start_dir):
        # Убираем из обхода игнорируемые папки
        dirs[:] = [d for d in dirs if d not in IGNORE_DIRS]
        for file in files:
            if file in IGNORE_FILES:
                continue
            ext = os.path.splitext(file)[1]
            if ext not in ALLOWED_EXTENSIONS:
                continue
            full_path = os.path.join(root, file)
            rel_path = os.path.relpath(full_path, start_dir)
            result[rel_path] = full_path
    return result

def main():
    base_dir = os.getcwd()
    print(f"📂 Сканируем: {base_dir}")
    files = collect_files(base_dir)
    if not files:
        print("❌ Нет файлов для сборки.")
        return

    output_path = os.path.join(base_dir, "project_full.txt")
    with open(output_path, "w", encoding="utf-8") as out:
        out.write("=== СТРУКТУРА ПРОЕКТА ===\n")
        for path in sorted(files.keys()):
            out.write(f"  {path}\n")
        out.write("\n\n")

        for path in sorted(files.keys()):
            out.write(f"=== ФАЙЛ: {path} ===\n")
            try:
                with open(files[path], "r", encoding="utf-8") as f:
                    content = f.read()
                out.write(content)
            except Exception as e:
                out.write(f"// Ошибка чтения: {e}\n")
            out.write("\n\n")

    print(f"✅ Готово! Файл создан: {output_path}")

if __name__ == "__main__":
    main()