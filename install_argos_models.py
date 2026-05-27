import sys
from pathlib import Path


def install_from_file(path: str) -> None:
    import argostranslate.package
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"Model file not found: {p}")
    argostranslate.package.install_from_path(str(p))
    print(f"Installed model: {p}")


def auto_install_pair(from_code: str, to_code: str) -> bool:
    import argostranslate.package
    print(f"Looking for model {from_code} -> {to_code} ...")
    available = argostranslate.package.get_available_packages()
    package = next((pkg for pkg in available if pkg.from_code == from_code and pkg.to_code == to_code), None)
    if package is None:
        print(f"Model not found in index: {from_code} -> {to_code}")
        return False
    print(f"Downloading {package} ...")
    path = package.download()
    argostranslate.package.install_from_path(path)
    print(f"Installed {from_code} -> {to_code}")
    return True


def main() -> int:
    try:
        import argostranslate.package
        import argostranslate.translate
    except Exception as e:
        print("Argos Translate is not installed.")
        print(e)
        return 1

    if len(sys.argv) > 1:
        install_from_file(sys.argv[1])
        return 0

    print("Updating Argos package index...")
    try:
        argostranslate.package.update_package_index()
        ok1 = auto_install_pair("en", "zh")
        ok2 = auto_install_pair("zh", "en")
        if ok1 or ok2:
            print("Done. You can now select 'Argos 本地离线翻译' in Settings.")
            return 0
        print("Could not find Chinese-English models automatically.")
        print("You can download .argosmodel files manually and drag them onto install_argos_model_file.bat.")
        return 2
    except Exception as e:
        print("Automatic model download failed:")
        print(e)
        print("You can manually download .argosmodel files and drag them onto install_argos_model_file.bat.")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
