"""Equivalent SDK package inference; only synthetic metadata and local files."""
import contextlib
import csv
import importlib.metadata as metadata
import io
from pathlib import Path
import runpy
import sys
from types import SimpleNamespace

import pytest

pytestmark=pytest.mark.unit


@pytest.fixture
def namespace():
    path=Path(__file__).resolve().parents[2]/'voice/runtime/voice_worker.py'
    original_path=list(sys.path)
    try:
        with contextlib.redirect_stdout(io.StringIO()):
            return runpy.run_path(str(path),run_name='test_metadata_worker')
    finally:
        sys.path[:]=original_path


def distribution(root,name,rows,existing=(),declared=None):
    info=root/(name+'-1.dist-info')
    info.mkdir(parents=True)
    (info/'METADATA').write_text('Metadata-Version: 2.1\nName: '+name+'\nVersion: 1\n',encoding='utf-8')
    with (info/'RECORD').open('w',encoding='utf-8',newline='') as stream:
        csv.writer(stream).writerows(rows)
    if declared is not None:(info/'top_level.txt').write_text(declared,encoding='utf-8')
    for name in existing:
        path=root/name
        path.parent.mkdir(parents=True,exist_ok=True)
        path.write_text('synthetic',encoding='utf-8')
    return metadata.PathDistribution(info)


def check(namespace,monkeypatch,distributions):
    monkeypatch.setattr(metadata,'distributions',lambda:iter(distributions))
    original=metadata.packages_distributions
    expected=original()
    actual=namespace['_fast_packages_distributions'](original)
    assert actual==expected
    return actual


@pytest.mark.parametrize('rows,existing,expected',[
    ([['pkg/__init__.py','','1'],['pkg/extra.py','','1']],['pkg/__init__.py','pkg/extra.py'],{'pkg':['Example']}),
    ([['missing/first.py','','1'],['missing/second.py','','1']],[],{}),
    ([['pkg/missing.py','','1'],['pkg/present.py','','1']],['pkg/present.py'],{'pkg':['Example']}),
    ([['standalone.py','','1'],['bytecode.pyc','','1']],['standalone.py','bytecode.pyc'],{'standalone':['Example'],'bytecode':['Example']}),
    ([['ignored.pth','','1'],['other.dist-info/METADATA','','1']],['ignored.pth','other.dist-info/METADATA'],{}),
    ([['space package/данные,часть.py','','1']],['space package/данные,часть.py'],{'space package':['Example']}),
    ([['pkg/a.py','','1'],['pkg/a.py','','1']],['pkg/a.py'],{'pkg':['Example']}),
    ([['without_suffix','','1']],['without_suffix'],{'without_suffix':['Example']}),
])
def test_real_record_matches_standard_inference(namespace,monkeypatch,tmp_path,rows,existing,expected):
    item=distribution(tmp_path,'Example',rows,existing)
    assert check(namespace,monkeypatch,[item])==expected


def test_declared_names_keep_duplicates_and_skip_inference(namespace,monkeypatch,tmp_path):
    item=distribution(tmp_path,'Example',[['broken','','not-an-int']],declared='alias alias\nsecond\n')
    assert check(namespace,monkeypatch,[item])=={'alias':['Example','Example'],'second':['Example']}


def test_shared_namespace_preserves_distribution_order(namespace,monkeypatch,tmp_path):
    first=distribution(tmp_path/'first','One',[['shared/a.py','','1']],['shared/a.py'])
    second=distribution(tmp_path/'second','Two',[['shared/b.py','','1']],['shared/b.py'])
    assert check(namespace,monkeypatch,[second,first])=={'shared':['Two','One']}


def test_whitespace_declaration_uses_inference(namespace,monkeypatch,tmp_path):
    item=distribution(tmp_path,'Example',[['pkg/a.py','','1']],['pkg/a.py'],declared=' \n\t')
    assert check(namespace,monkeypatch,[item])=={'pkg':['Example']}


def test_empty_record_and_egg_sources_keep_standard_fallback(namespace,monkeypatch,tmp_path):
    item=distribution(tmp_path,'Example',[],['pkg/a.py'])
    (item._path/'SOURCES.txt').write_text('pkg/a.py\n',encoding='utf-8')
    assert check(namespace,monkeypatch,[item])=={'pkg':['Example']}


def test_custom_distribution_uses_its_files_property(namespace,monkeypatch):
    class Provider(metadata.Distribution):
        def read_text(self,name):
            return {'METADATA':'Name: Custom\nVersion: 1\n','RECORD':'misleading/entry.py,,1\n'}.get(name)
        def locate_file(self,path):raise AssertionError('Custom provider owns its files property')
        @property
        def files(self):return [metadata.PackagePath('virtual/module.py')]
    assert check(namespace,monkeypatch,[Provider()])=={'virtual':['Custom']}


def test_provider_error_is_not_retried_or_hidden(namespace,monkeypatch):
    error=RuntimeError('controlled provider error')
    calls=[]
    class Provider(metadata.Distribution):
        def read_text(self,name):
            calls.append(name)
            raise error
        def locate_file(self,path):raise AssertionError('No file access expected')
    monkeypatch.setattr(metadata,'distributions',lambda:iter([Provider()]))
    with pytest.raises(RuntimeError) as raised:
        namespace['_fast_packages_distributions'](metadata.packages_distributions)
    assert raised.value is error and calls==['top_level.txt']


def test_native_extension_name_uses_platform_suffix_rules(namespace,monkeypatch,tmp_path):
    from importlib.machinery import EXTENSION_SUFFIXES
    name='extension'+EXTENSION_SUFFIXES[0]
    item=distribution(tmp_path,'Native',[[name,'','1']],[name])
    assert check(namespace,monkeypatch,[item])=={'extension':['Native']}


@pytest.mark.parametrize('rows',[
    [['pkg/a.py','','invalid']],
    [['pkg/a.py','','1','extra']],
    [[]],
    [['','','1']],
    [['pkg/a.py','','1'],['pkg/later.py','','invalid']],
])
def test_malformed_metadata_keeps_original_exception(namespace,monkeypatch,tmp_path,rows):
    item=distribution(tmp_path,'Example',rows,['pkg/a.py'])
    monkeypatch.setattr(metadata,'distributions',lambda:iter([item]))
    original=metadata.packages_distributions
    with pytest.raises(Exception) as expected:original()
    with pytest.raises(type(expected.value)) as actual:namespace['_fast_packages_distributions'](original)
    assert str(actual.value)==str(expected.value)


def test_only_successful_namespace_needs_one_existing_file(namespace,monkeypatch,tmp_path):
    rows=[['pkg/missing.py','','1']]+[[f'pkg/file-{i}.py','','1'] for i in range(1000)]
    item=distribution(tmp_path,'Example',rows,[f'pkg/file-{i}.py' for i in range(1000)])
    monkeypatch.setattr(metadata,'distributions',lambda:iter([item]))
    original_locate=metadata.PathDistribution.locate_file
    count=[0]
    def counted(owner,path):
        if owner is item:count[0]+=1
        return original_locate(owner,path)
    monkeypatch.setattr(metadata.PathDistribution,'locate_file',counted)
    original=metadata.packages_distributions
    expected=original()
    assert count[0]==1001
    count[0]=0
    assert namespace['_fast_packages_distributions'](original)==expected
    assert count[0]==2


@pytest.mark.parametrize('fail',[False,True])
def test_scope_restores_public_function_and_keeps_version_checks(namespace,monkeypatch,fail):
    original=metadata.packages_distributions
    version=metadata.version
    lookup=metadata.distribution
    monkeypatch.setattr(metadata,'distributions',lambda:iter(()))
    error=RuntimeError('controlled import error')
    try:
        with namespace['_metadata_catalog']():
            assert metadata.packages_distributions is not original
            assert metadata.packages_distributions()=={}
            assert metadata.version is version and metadata.distribution is lookup
            if fail:raise error
    except RuntimeError as raised:
        assert fail and raised is error
    assert metadata.packages_distributions is original


def test_scope_preserves_a_later_replacement(namespace,monkeypatch):
    replacement=lambda:{'new':['provider']}
    original=metadata.packages_distributions
    with namespace['_metadata_catalog']():
        monkeypatch.setattr(metadata,'packages_distributions',replacement)
    assert metadata.packages_distributions is replacement
    monkeypatch.setattr(metadata,'packages_distributions',original)


@pytest.mark.parametrize('version,implementation',[
    ((3,12),'cpython'),((3,14),'cpython'),((3,13),'pypy'),
])
def test_other_interpreters_keep_the_standard_catalog(namespace,monkeypatch,version,implementation):
    scope=namespace['_metadata_catalog']
    monkeypatch.setitem(scope.__wrapped__.__globals__,'sys',SimpleNamespace(
        version_info=version,implementation=SimpleNamespace(name=implementation)))
    original=metadata.packages_distributions
    with scope():assert metadata.packages_distributions is original
