from pathlib import Path
import shutil


ROOT = Path(__file__).resolve().parent


def copy_static_assets(public_directory=None):
    destination = Path(public_directory) if public_directory else ROOT / "public"
    shutil.copytree(ROOT / "app" / "static", destination / "static", dirs_exist_ok=True)


if __name__ == "__main__":
    copy_static_assets()
