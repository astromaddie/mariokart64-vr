#!/usr/bin/env python3
"""Capture complete host-side source and ROM provenance for a Linux package build."""

import argparse
import hashlib
import json
import re
import subprocess
from pathlib import Path


def run(root, *args):
	return subprocess.run(
		["git", *args], cwd=root, check=True, stdout=subprocess.PIPE,
		stderr=subprocess.PIPE,
	).stdout


def gitlink_entries(root):
	"""Return committed submodule paths and revisions without refreshing the index."""
	data = run(root, "ls-tree", "-r", "-z", "HEAD")
	entries = []
	for record in data.split(b"\0"):
		if not record:
			continue
		metadata, raw_path = record.split(b"\t", 1)
		mode, kind, revision = metadata.decode("ascii").split()
		if mode == "160000":
			entries.append((raw_path.decode("utf-8", "strict"), revision))
	return entries


def diff_scope(root, gitlinks):
	"""Exclude gitlinks so Git does not recursively reopen every submodule per file."""
	pathspecs = ["."]
	pathspecs.extend(f":(exclude,literal){path}" for path, _ in gitlinks)
	return ["--", *pathspecs]


def tracked_changes(root, gitlinks):
	data = run(
		root, "diff", "--name-status", "-z", "--no-renames",
		"--ignore-submodules=all", "HEAD", *diff_scope(root, gitlinks),
	)
	fields = [field.decode("utf-8", "strict") for field in data.split(b"\0") if field]
	if len(fields) % 2:
		raise RuntimeError(f"cannot parse tracked change manifest in {root}")
	return [{"status": fields[index], "path": fields[index + 1]} for index in range(0, len(fields), 2)]


def diff_hash(root):
	gitlinks = gitlink_entries(root)
	return hashlib.sha256(run(
		root, "diff", "--binary", "--no-renames", "--ignore-submodules=all",
		"HEAD", *diff_scope(root, gitlinks),
	)).hexdigest()


def untracked_manifest(root):
	paths = run(root, "ls-files", "--others", "--exclude-standard", "-z").split(b"\0")
	entries = []
	for raw_path in paths:
		if not raw_path:
			continue
		path = Path(raw_path.decode("utf-8", "strict"))
		full_path = root / path
		if not full_path.is_file():
			raise RuntimeError(f"untracked source is missing or not a file: {path}")
		entries.append({"path": path.as_posix(), "sha256": file_sha256(full_path), "size_bytes": full_path.stat().st_size})
	return entries


def file_sha256(path):
	digest = hashlib.sha256()
	with path.open("rb") as stream:
		for block in iter(lambda: stream.read(1024 * 1024), b""):
			digest.update(block)
	return digest.hexdigest()


def submodule_entries(root, prefix=""):
	entries = []
	for relative_path, expected in gitlink_entries(root):
		path = f"{prefix}/{relative_path}" if prefix else relative_path
		module_root = root / relative_path
		try:
			actual = run(module_root, "rev-parse", "--verify", "HEAD").decode().strip()
		except (subprocess.CalledProcessError, FileNotFoundError) as error:
			raise RuntimeError(f"submodule is not initialized or readable: {path}") from error
		module_gitlinks = gitlink_entries(module_root)
		module_status = tracked_changes(module_root, module_gitlinks)
		module_untracked = untracked_manifest(module_root)
		entries.append({
			"path": path,
			"expected_revision": expected,
			"revision": actual,
			"revision_matches_parent": actual == expected,
			"status": module_status,
			"diff_sha256": diff_hash(module_root),
			"untracked_files": module_untracked,
		})
		entries.extend(submodule_entries(module_root, path))
	return entries


def main():
	parser = argparse.ArgumentParser(description=__doc__)
	parser.add_argument("--root", required=True, type=Path)
	parser.add_argument("--rom", required=True, type=Path)
	parser.add_argument("--output", required=True, type=Path)
	args = parser.parse_args()
	root = args.root.resolve()
	rom = args.rom.resolve(strict=True)

	revision = run(root, "rev-parse", "--verify", "HEAD").decode().strip()
	if not re.fullmatch(r"[0-9a-f]{40}", revision):
		raise RuntimeError(f"invalid source revision: {revision!r}")
	root_gitlinks = gitlink_entries(root)
	root_status = tracked_changes(root, root_gitlinks)
	root_untracked = untracked_manifest(root)
	submodules = submodule_entries(root)
	rom_hashes = hashlib.sha256(), hashlib.sha1()
	with rom.open("rb") as stream:
		for block in iter(lambda: stream.read(1024 * 1024), b""):
			for digest in rom_hashes:
				digest.update(block)

	metadata = {
		"source_revision": revision,
		"source_branch": run(root, "branch", "--show-current").decode().strip(),
		"provenance_complete": True,
		"release_ready": False,
		"provenance_notes": ["Host source and ROM provenance is complete; game stereo and headset validation remain pending."],
		"source_status": root_status,
		"source_diff_sha256": hashlib.sha256(run(
			root, "diff", "--binary", "--no-renames", "--ignore-submodules=all",
			"HEAD", *diff_scope(root, root_gitlinks),
		)).hexdigest(),
		"source_untracked_files": root_untracked,
		"submodules": submodules,
		"tree_dirty": bool(root_status or root_untracked) or any(
			module["status"] or module["untracked_files"] or not module["revision_matches_parent"]
			for module in submodules
		),
		"rom_input": {
			"filename": rom.name,
			"size_bytes": rom.stat().st_size,
			"sha1": rom_hashes[1].hexdigest(),
			"sha256": rom_hashes[0].hexdigest(),
		},
	}
	args.output.parent.mkdir(parents=True, exist_ok=True)
	args.output.write_text(json.dumps(metadata, indent=2) + "\n", encoding="utf-8")
	print(f"source revision {revision}; tree {'dirty' if metadata['tree_dirty'] else 'clean'}")
	print(f"captured {len(root_status)} root status entries, {len(root_untracked)} untracked files and {len(submodules)} submodules")
	print(f"ROM sha1 {metadata['rom_input']['sha1']} ({metadata['rom_input']['size_bytes']} bytes)")


if __name__ == "__main__":
	main()
