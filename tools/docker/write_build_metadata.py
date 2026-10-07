#!/usr/bin/env python3
"""Write package hashes plus the complete host-captured build provenance."""

import argparse
import hashlib
import json
import os
import re
import subprocess
from datetime import datetime, timezone
from pathlib import Path


def version(*command):
	result = subprocess.run(command, check=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
	return result.stdout.splitlines()[0]


def file_sha256(path):
	digest = hashlib.sha256()
	with path.open("rb") as stream:
		for block in iter(lambda: stream.read(1024 * 1024), b""):
			digest.update(block)
	return digest.hexdigest()


def tree_manifest(path):
	if path.is_file():
		return {"files": 1, "sha256": file_sha256(path)}
	if not path.is_dir():
		return {"files": 0, "sha256": None}
	entries = []
	for child in sorted(item for item in path.rglob("*") if item.is_file()):
		entries.append((child.relative_to(path).as_posix(), file_sha256(child)))
	digest = hashlib.sha256()
	for name, sha256 in entries:
		digest.update(name.encode("utf-8"))
		digest.update(b"\0")
		digest.update(sha256.encode("ascii"))
		digest.update(b"\n")
	return {"files": len(entries), "sha256": digest.hexdigest()}


def main():
	parser = argparse.ArgumentParser(description=__doc__)
	parser.add_argument("--source", type=Path, required=True)
	parser.add_argument("--package", type=Path, required=True)
	parser.add_argument("--build", type=Path, required=True)
	args = parser.parse_args()
	source = json.loads(args.source.read_text(encoding="utf-8"))
	if not re.fullmatch(r"[0-9a-f]{40}", source.get("source_revision", "")):
		raise RuntimeError("source metadata has no exact 40-character Git revision")
	for key in ("source_status", "source_untracked_files", "source_diff_sha256", "submodules", "tree_dirty", "rom_input"):
		if key not in source:
			raise RuntimeError(f"source metadata is incomplete: missing {key}")
	if source.get("release_ready", False) and not source.get("provenance_complete", False):
		raise RuntimeError("release-ready metadata requires a complete host source audit")
	expected_dirty = bool(source["source_status"] or source["source_untracked_files"]) or any(
		module.get("status") or module.get("untracked_files") or not module.get("revision_matches_parent")
		or module.get("tracked_worktree_audit") == "unknown"
		for module in source["submodules"]
	) or not source.get("provenance_complete", False)
	if source["tree_dirty"] != expected_dirty:
		raise RuntimeError("source dirty flag does not match captured status and submodule state")
	if not re.fullmatch(r"[0-9a-f]{40}", source["rom_input"].get("sha1", "")):
		raise RuntimeError("source metadata has no ROM input hash")
	if not re.fullmatch(r"[0-9a-f]{64}", source["rom_input"].get("sha256", "")):
		raise RuntimeError("source metadata has no ROM input SHA-256")

	package = args.package.resolve()
	build = args.build.resolve()
	root = Path(__file__).resolve().parents[2]
	generated = {
		"recompiled_funcs": tree_manifest(root / "RecompiledFuncs"),
		"recompiled_patches": tree_manifest(root / "RecompiledPatches"),
		"rsp_asp_main": tree_manifest(root / "rsp/aspMain.cpp"),
		"patch_elf": tree_manifest(root / "patches/patches.elf"),
	}
	files = {
		path.relative_to(package).as_posix(): file_sha256(path)
		for path in sorted(item for item in package.rglob("*") if item.is_file())
		if path.name != "BUILD-METADATA.json"
	}
	metadata = {
		"title": "MarioKart64Recompiled",
		"source_revision": source["source_revision"],
		"source_branch": source.get("source_branch", ""),
		"tree_dirty": source["tree_dirty"],
		"provenance_complete": source.get("provenance_complete", False),
		"release_ready": source.get("release_ready", False),
		"provenance_notes": source.get("provenance_notes", []),
		"source_status": source["source_status"],
		"source_diff_sha256": source["source_diff_sha256"],
		"source_untracked_files": source["source_untracked_files"],
		"submodules": source["submodules"],
		"rom_input": source["rom_input"],
		"built_at_utc": datetime.now(timezone.utc).isoformat(),
		"build": {
			"architecture": version("uname", "-m"),
			"compiler": version("clang-15", "--version"),
			"linker": version("ld.lld-15", "--version"),
			"cmake": version("cmake", "--version"),
			"ninja": version("ninja", "--version"),
			"flags": ["-fsigned-char", "-ffp-contract=off"],
			"image": os.environ.get("MK64_FRAME_IMAGE", ""),
			"image_id": os.environ.get("MK64_FRAME_IMAGE_ID", ""),
		},
		"generated_inputs": generated,
		"files": files,
	}
	(package / "BUILD-METADATA.json").write_text(json.dumps(metadata, indent=2) + "\n", encoding="utf-8")
	print(f"metadata: source {metadata['source_revision']} ({'dirty' if metadata['tree_dirty'] else 'clean'})")
	print(f"metadata: {len(source['submodules'])} submodules, {len(files)} package file hashes")
	print(f"metadata: ROM sha1 {source['rom_input']['sha1']}")


if __name__ == "__main__":
	main()
