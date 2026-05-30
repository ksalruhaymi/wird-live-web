import os
import re

project_path = "."

arabic_pattern = re.compile(r'[\u0600-\u06FF][\u0600-\u06FF0-9\s\-\_\:\،\؛\؟\!\.\(\)\"\'/]*')

excluded_dirs = {
    "locale",
    ".git",
    "__pycache__",
    "node_modules",
    "venv",
    ".venv",
    "env",
    "site-packages",
    "migrations",
}

excluded_extensions = {".po", ".mo"}

results = {}

for root, dirs, files in os.walk(project_path):
    dirs[:] = [d for d in dirs if d not in excluded_dirs]

    for file in files:
        ext = os.path.splitext(file)[1].lower()
        if ext in excluded_extensions:
            continue

        if not file.endswith((".html", ".py", ".js")):
            continue

        path = os.path.join(root, file)

        try:
            with open(path, "r", encoding="utf-8", errors="ignore") as f:
                content = f.read()

            matches = arabic_pattern.findall(content)

            for match in matches:
                text = " ".join(match.strip().split())
                if len(text) < 2:
                    continue

                if text not in results:
                    results[text] = []

                results[text].append(path)

        except Exception:
            continue

with open("arabic_texts.txt", "w", encoding="utf-8") as f:
    for text, paths in sorted(results.items()):
        f.write(f"TEXT: {text}\n")
        for p in sorted(set(paths)):
            f.write(f"FILE: {p}\n")
        f.write("\n" + "-" * 60 + "\n\n")

print("Done. File saved as arabic_texts.txt")