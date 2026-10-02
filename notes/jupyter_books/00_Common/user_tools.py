from pathlib import Path

from dotenv import load_dotenv


def load_project_env():
    """Load workspace .env by walking up from the current directory."""
    for parent in [Path.cwd().resolve(), *Path.cwd().resolve().parents]:
        env_file = parent / ".env"
        if env_file.exists():
            load_dotenv(env_file, override=True)
            return env_file
    return None

from pathlib import Path

from dotenv import load_dotenv


def load_project_env():
    """Load workspace .env by walking up from the current directory."""
    for parent in [Path.cwd().resolve(), *Path.cwd().resolve().parents]:
        env_file = parent / ".env"
        if env_file.exists():
            load_dotenv(env_file, override=True)
            return env_file
    return None


class SectionPrinter():
    def __init__(self, section_name):
        self.section_name = section_name

    def __enter__(self):
        print(self.section_name.center(60, "="))

    def __exit__(self, exc_type, exc_value, traceback):
        print("=" * 60)