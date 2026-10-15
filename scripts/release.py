"""Shared version, deterministic archives, and complete-release validation."""
import argparse
import gzip
import hashlib
import io
import json
from pathlib import Path
import plistlib
import re
import shutil
import stat
import subprocess
import tarfile
import zipfile

ROOT = Path(__file__).resolve().parents[1]


def version(root=ROOT):
    value = (root / "VERSION").read_text().strip()
    if not re.fullmatch(r"(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)", value):
        raise ValueError("VERSION must contain a stable major.minor.patch version")
    return value


def build_number(value):
    major, minor, patch = map(int, value.split("."))
    if minor >= 100 or patch >= 100:
        raise ValueError("Minor and patch versions must be below 100 for the macOS build number")
    return str(major * 10000 + minor * 100 + patch)


def metadata(platform, root=ROOT):
    try:
        revision = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=root, text=True,
                                           stderr=subprocess.DEVNULL).strip()
    except (OSError, subprocess.CalledProcessError):
        revision = "source-archive"
    return {"version": version(root), "platform": platform, "revision": revision,
            "python_minimum": "3.9", "bundle_id": "org.coindex.desktop"}


def archive_files(directory):
    files = []
    for item in sorted(directory.rglob("*")):
        if item.is_symlink():
            raise ValueError("Release archives cannot contain symlinks: " + item.name)
        if item.is_file():
            files.append(item)
    if not files:
        raise ValueError("Cannot package an empty directory")
    return files


def write_zip(output, files, root, prefix):
    """Stable timestamps/order/modes; original executable permissions are retained."""
    output.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for item in sorted(files):
            if item.is_symlink() or not item.is_file():
                raise ValueError("Missing or symlinked archive input: " + item.name)
            name = prefix + "/" + item.relative_to(root).as_posix()
            info = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
            info.create_system = 3
            info.compress_type = zipfile.ZIP_DEFLATED
            mode = 0o755 if item.stat().st_mode & 0o111 else 0o644
            info.external_attr = (stat.S_IFREG | mode) << 16
            archive.writestr(info, item.read_bytes())


def write_tar(output, directory):
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("wb") as raw, gzip.GzipFile(filename="", mode="wb", fileobj=raw, mtime=0) as compressed:
        with tarfile.open(fileobj=compressed, mode="w", format=tarfile.USTAR_FORMAT) as archive:
            for item in archive_files(directory):
                data = item.read_bytes()
                info = tarfile.TarInfo(directory.name + "/" + item.relative_to(directory).as_posix())
                info.size = len(data)
                info.mode = 0o755 if item.stat().st_mode & 0o111 else 0o644
                info.mtime = 0
                archive.addfile(info, io.BytesIO(data))


def package(platform, root=ROOT):
    value = version(root)
    app = root / "dist" / ("coindex.app" if platform == "macos" else "coindex-linux")
    resource = app / "Contents/Resources" if platform == "macos" else app
    release = json.loads((resource / "release.json").read_text())
    if release.get("version") != value or release.get("platform") != platform:
        raise ValueError("Rebuild application: bundled release metadata does not match VERSION/platform")
    required = [resource / "backend/service.py", resource / "backend/summaries.py", resource / "backend/updates.py", resource / "demo.json"]
    if platform == "macos":
        info = plistlib.loads((app / "Contents/Info.plist").read_bytes())
        if info.get("CFBundleShortVersionString") != value or info.get("CFBundleVersion") != build_number(value):
            raise ValueError("Application Info.plist version does not match VERSION")
        subprocess.run(["lipo", "-verify_arch", "arm64", "x86_64", str(app / "Contents/MacOS/coindex")], check=True)
        subprocess.run(["codesign", "--verify", "--deep", "--strict", str(app)], check=True)
        required += [app / "Contents/MacOS/coindex", resource / "AppIcon.icns"]
        output = root / "dist" / ("coindex-" + value + "-macos-universal.zip")
    else:
        required += [app / "coindex", app / "linux/app.py", app / "linux/summaries.py", app / "scripts/install-linux.sh",
                     app / "scripts/install-linux.py", app / "VERSION"]
        output = root / "dist" / ("coindex-" + value + "-linux.tar.gz")
    if not all(item.is_file() for item in required):
        raise ValueError("Application bundle is incomplete; rebuild before packaging")
    subprocess.run(["python3", str(root / "scripts/check-public-release.py"), "--app", str(app)], check=True)
    if platform == "macos":
        write_zip(output, archive_files(app), app, app.name)
    else:
        write_tar(output, app)
    return output


def install_build(platform, stage, destination):
    """Replace only a recognized build output, keeping the previous bundle on failure."""
    if destination.is_symlink():
        raise ValueError("Refusing to replace a symlinked build output")
    if destination.exists():
        if platform == "macos":
            try:
                recognized = plistlib.loads((destination / "Contents/Info.plist").read_bytes()).get("CFBundleIdentifier") == "org.coindex.desktop"
            except (OSError, ValueError, plistlib.InvalidFileException):
                recognized = False
        else:
            launcher = destination / "coindex"
            recognized = launcher.is_file() and not launcher.is_symlink() and "# Managed by coindex build-linux.sh" in launcher.read_text()
        if not recognized:
            raise ValueError("Refusing to replace an unrecognized build output")
    backup = stage.parent / "previous-build"
    if destination.exists():
        destination.rename(backup)
    try:
        stage.rename(destination)
    except BaseException:
        if backup.exists():
            backup.rename(destination)
        raise
    if backup.exists():
        shutil.rmtree(backup)


def artifact_names(value):
    return ["coindex-" + value + suffix for suffix in ("-macos-universal.zip", "-linux.tar.gz", "-source.zip")]


def checksum_lines(directory, value):
    lines = []
    for name in artifact_names(value):
        path = directory / name
        if path.is_symlink() or not path.is_file():
            raise ValueError("Missing release artifact: " + name)
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        lines.append(digest + "  " + name)
    return "\n".join(lines) + "\n"


def validate_archives(directory, value):
    """Check embedded versions and required files without extracting untrusted paths."""
    names = artifact_names(value)
    with zipfile.ZipFile(directory / names[0]) as archive:
        info = plistlib.loads(archive.read("coindex.app/Contents/Info.plist"))
        meta = json.loads(archive.read("coindex.app/Contents/Resources/release.json"))
        if info.get("CFBundleShortVersionString") != value or meta.get("version") != value or meta.get("platform") != "macos":
            raise ValueError("macOS archive version/platform mismatch")
        archive.getinfo("coindex.app/Contents/Resources/backend/summaries.py")
        archive.getinfo("coindex.app/Contents/Resources/backend/updates.py")
    with tarfile.open(directory / names[1], "r:gz") as archive:
        meta = json.loads(archive.extractfile("coindex-linux/release.json").read())
        if meta.get("version") != value or meta.get("platform") != "linux":
            raise ValueError("Linux archive version/platform mismatch")
        archive.getmember("coindex-linux/backend/summaries.py")
        archive.getmember("coindex-linux/backend/updates.py")
        archive.getmember("coindex-linux/linux/summaries.py")
        archive.getmember("coindex-linux/scripts/install-linux.sh")
    with zipfile.ZipFile(directory / names[2]) as archive:
        if archive.read("coindex/VERSION").decode().strip() != value:
            raise ValueError("Source archive version mismatch")
        for required in ("Sources/SummaryViews.swift", "Sources/UpdateViews.swift", "backend/summaries.py", "backend/updates.py", "linux/app.py", "linux/summaries.py", "scripts/build.sh"):
            archive.getinfo("coindex/" + required)


def release_notes(root=ROOT):
    value = version(root)
    sections = re.split(r"(?m)^## ", (root / "CHANGELOG.md").read_text())
    section = next((part for part in sections[1:] if part.startswith(value + " ") or part.startswith(value + "\n")), None)
    if not section:
        raise ValueError("CHANGELOG.md needs a section for " + value)
    return "## " + section.strip() + "\n"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    for command in ("version", "build-number", "notes"):
        sub.add_parser(command)
    check = sub.add_parser("check-tag")
    check.add_argument("tag")
    meta = sub.add_parser("metadata")
    meta.add_argument("platform", choices=("macos", "linux"))
    meta.add_argument("output", type=Path)
    install = sub.add_parser("install-build")
    install.add_argument("platform", choices=("macos", "linux"))
    install.add_argument("stage", type=Path)
    install.add_argument("destination", type=Path)
    bundle = sub.add_parser("package")
    bundle.add_argument("platform", choices=("macos", "linux"))
    for command in ("checksums", "verify"):
        command_parser = sub.add_parser(command)
        command_parser.add_argument("--directory", type=Path, default=ROOT / "dist")
    args = parser.parse_args()
    value = version()
    if args.command == "version":
        print(value)
    elif args.command == "build-number":
        print(build_number(value))
    elif args.command == "check-tag":
        if args.tag != "v" + value:
            parser.error("Tag must match VERSION: v" + value)
        release_notes()
    elif args.command == "metadata":
        args.output.write_text(json.dumps(metadata(args.platform), indent=2) + "\n")
    elif args.command == "install-build":
        install_build(args.platform, args.stage, args.destination)
    elif args.command == "package":
        print(package(args.platform))
    elif args.command == "notes":
        print(release_notes(), end="")
    else:
        validate_archives(args.directory, value)
        checksums = checksum_lines(args.directory, value)
        target = args.directory / ("coindex-" + value + "-SHA256SUMS.txt")
        if args.command == "checksums":
            target.write_text(checksums)
        elif target.read_text() != checksums:
            raise ValueError("Release checksums do not match artifacts")
        print(target)


if __name__ == "__main__":
    main()
