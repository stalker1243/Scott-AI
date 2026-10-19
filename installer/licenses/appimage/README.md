# AppImage runtime

ScottAI AppImage embeds the unmodified x86-64 type-2 runtime, release `20251108`.

- Source: https://github.com/AppImage/type2-runtime/tree/dd6cebedcbddde9c82f89b011e8e1d40b6e43868
- Build instructions and dependency source URLs: https://github.com/AppImage/type2-runtime/blob/dd6cebedcbddde9c82f89b011e8e1d40b6e43868/BUILD.md
- Binary: https://github.com/AppImage/type2-runtime/releases/download/20251108/runtime-x86_64
- SHA256: `2fca8b443c92510f1483a883f60061ad09b46b978b2631c807cd873a47ec260d`

`LICENSE.txt` is copied verbatim from that source revision. It describes the
runtime's MIT license and the licenses of its statically linked libraries.
The application payload retains its own licenses in the parent directory.

The build uses appimagetool 1.9.1, revision
`8c8c91f762b412a19f4e8d2c4b35afb98f2d7c81`; the tool is not included in ScottAI.
Its binary and runtime are pinned and checked by `installer/build_appimage.py`.
