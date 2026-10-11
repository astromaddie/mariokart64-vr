# Changelog

## 2026-10-11 — PR0 readiness preparation

- Added experimental Steam Frame status, readiness evidence and a public ROM-free VR host-test workflow.
- Replaced the private RT64 pin with its public upstream base plus SHA-256-pinned RT64/Plume VR source overlays.
- No public build or release was made. Full native builds still require a locally supplied game ROM.

## 2026-10-11 — Current-source PR0 verification

- Updated readiness evidence to current source `ecd49d581b984ebd3e587572c5fbac58b94f8d1b`; ROM-free production-source CMake/CTest passed 8/8.
- Built and packaged the full Linux ARM64 application with `JOBS=4`; package and ABI checks passed, and the 30-second host launch smoke stayed open until timeout. The package contains no ROM files; generated outputs were removed after recording the artifact identity.
- The latest exact-source GitHub job did not start because of the account billing/spending-limit block; the earlier successful run is retained in PR0_METADATA.json.
