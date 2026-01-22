import os

# какие расширения оставляем
ALLOWED_EXT = {".py", ".js", ".css", ".html"}

# какие папки игнорируем
IGNORE_DIRS = {"build", ".gradle", ".idea", "out", "__pycache__"}

def should_show(file):
    if os.path.isdir(file):
        return os.path.basename(file) not in IGNORE_DIRS
    _, ext = os.path.splitext(file)
    return ext in ALLOWED_EXT or os.path.basename(file) in {"settings.gradle", "build.gradle"}

def print_tree(startpath, prefix=""):
    items = sorted([i for i in os.listdir(startpath) if should_show(os.path.join(startpath, i))])
    for index, item in enumerate(items):
        path = os.path.join(startpath, item)
        connector = "└── " if index == len(items) - 1 else "├── "
        print(prefix + connector + item)
        if os.path.isdir(path):
            extension = "    " if index == len(items) - 1 else "│   "
            print_tree(path, prefix + extension)

if __name__ == "__main__":
    print(".")
    print_tree(".")
    input()