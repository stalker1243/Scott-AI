"""Packaging keeps license contents and Basic controls while removing unused styles."""
import importlib.util
from pathlib import Path
import zipfile

import pytest

pytestmark = pytest.mark.unit


@pytest.fixture
def builder():
    spec = importlib.util.spec_from_file_location('compact_builder', Path(__file__).resolve().parents[2] / 'installer/build.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_sbom_zip_retains_all_bytes_and_license_notice(builder, tmp_path, monkeypatch):
    installer = tmp_path / 'installer'
    (installer / 'licenses').mkdir(parents=True)
    (installer / 'licenses/NOTICE.md').write_text('License notice')
    sdk = tmp_path / 'qt'
    (sdk / 'sbom/nested').mkdir(parents=True)
    files = {'base.spdx': b'a' * 10000, 'nested/declarative.json': b'b' * 20000}
    for name, content in files.items():
        (sdk / 'sbom' / name).write_bytes(content)
    monkeypatch.setattr(builder, 'INSTALLER', installer)
    builder.copy_licenses(tmp_path / 'dist', sdk)
    assert (tmp_path / 'dist/licenses/NOTICE.md').read_text() == 'License notice'
    with zipfile.ZipFile(tmp_path / 'dist/licenses/qt-sbom.zip') as archive:
        assert set(archive.namelist()) == set(files)
        assert all(archive.read(name) == content for name, content in files.items())


def test_pruning_preserves_basic_and_software_renderer(builder, tmp_path, monkeypatch):
    monkeypatch.setattr(builder, 'ROOT', tmp_path)
    source = tmp_path / 'ScottAI_qt/src/main.cpp'
    source.parent.mkdir(parents=True)
    source.write_text('QQuickStyle::setStyle("Basic");')
    output = tmp_path / 'dist/launcher'
    for style in ('Basic', 'Material', 'Imagine'):
        directory = output / 'qml/QtQuick/Controls' / style
        directory.mkdir(parents=True)
        (directory / 'qmldir').write_text(style)
        (output / f'Qt6QuickControls2{style}.dll').write_bytes(style.encode())
    (output / 'opengl32sw.dll').write_bytes(b'fallback')
    builder.prune_qt_styles(output)
    assert (output / 'opengl32sw.dll').read_bytes() == b'fallback'
    assert (output / 'Qt6QuickControls2Basic.dll').exists()
    assert (output / 'qml/QtQuick/Controls/Basic/qmldir').exists()
    assert not (output / 'qml/QtQuick/Controls/Material').exists()
    assert not (output / 'Qt6QuickControls2Imagine.dll').exists()
    source.write_text('QQuickStyle::setStyle("Material");')
    (output / 'Qt6QuickControls2Material.dll').write_bytes(b'required')
    builder.prune_qt_styles(output)
    assert (output / 'Qt6QuickControls2Material.dll').exists()
