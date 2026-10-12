import json
import re
import sys
from pathlib import Path
from tempfile import TemporaryDirectory
from urllib.request import HTTPRedirectHandler, Request, build_opener

REPO = "amordasiewi1/resume"
FILES = ("resume.html", "resume.pdf", "resume.json", "resume.yaml")
OUTPUT_NAMES = {"resume.html": "index.html"}
LIMIT = 10 * 1024 * 1024


class NoRedirects(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise ValueError("Unexpected redirect from GitHub")


def fetch(url):
    request = Request(url, headers={"User-Agent": "website-resume-sync", "Accept": "application/vnd.github+json"})
    with build_opener(NoRedirects).open(request, timeout=30) as response:
        content = response.read(LIMIT + 1)
    if not content or len(content) > LIMIT:
        raise ValueError("Download is empty or exceeds 10 MiB")
    return content


def validate(name, content):
    if name.endswith(".pdf"):
        if not content.startswith(b"%PDF-"):
            raise ValueError("Invalid PDF header")
        return
    text = content.decode("utf-8")
    if name.endswith(".json"):
        data = json.loads(text)
        if not isinstance(data, dict) or not isinstance(data.get("name"), str) or not isinstance(data.get("sections"), list):
            raise ValueError("Invalid resume JSON structure")
    elif name.endswith(".html"):
        if not text.lstrip().lower().startswith("<!doctype html>"):
            raise ValueError("Expected a standalone HTML document")
    elif name.endswith(".yaml"):
        if "\x00" in text or not re.search(r"^name:", text, re.MULTILINE):
            raise ValueError("Expected UTF-8 resume YAML with a name field")


def sync(destination):
    commit = json.loads(fetch(f"https://api.github.com/repos/{REPO}/commits/main"))["sha"]
    if not isinstance(commit, str) or not re.fullmatch(r"[0-9a-f]{40}", commit):
        raise ValueError("Invalid GitHub commit ID")
    with TemporaryDirectory(prefix="resume-sync-") as temporary:
        staged = Path(temporary)
        for name in FILES:
            content = fetch(f"https://raw.githubusercontent.com/{REPO}/{commit}/data/{name}")
            validate(name, content)
            (staged / name).write_bytes(content)
        destination.mkdir(parents=True, exist_ok=True)
        for name in FILES:
            output_name = OUTPUT_NAMES.get(name, name)
            pending = destination / (output_name + ".tmp")
            if pending.is_symlink() or (destination / output_name).is_symlink():
                raise ValueError("Refusing to overwrite a symbolic link")
        for name in FILES:
            output_name = OUTPUT_NAMES.get(name, name)
            pending = destination / (output_name + ".tmp")
            pending.write_bytes((staged / name).read_bytes())
            pending.replace(destination / output_name)
    print(f"Synced four resume files from {REPO}@{commit}")


def main():
    target = Path(__file__).resolve().parents[1] / "alessandromordasiewicz.com/public/resume"
    try:
        sync(target)
    except Exception as error:
        print(f"Resume sync failed: {error}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
