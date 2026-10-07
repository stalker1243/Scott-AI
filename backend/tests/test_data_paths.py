"""Changing the launch directory must not change saved chats or model credentials."""
import json
from pathlib import Path
from backend import chat_store, intelligent_answerer as ia


def test_default_paths_are_anchored_to_backend():
    root = Path(chat_store.__file__).resolve().parent
    assert chat_store.DEFAULT_CHAT_DIR == root/'data/chats'
    assert ia.AI_CONFIG_PATH == root/'data/ai_config.json'


def test_default_chat_survives_different_cwd(tmp_path, monkeypatch):
    first, second = tmp_path/'first', tmp_path/'second'
    first.mkdir(); second.mkdir()
    monkeypatch.setattr(chat_store,'DEFAULT_CHAT_DIR',tmp_path/'saved-chats')
    monkeypatch.chdir(first)
    original = chat_store.ChatStore()
    ident = original.create()['id']
    original.commit_turn(ident,'Вопрос','Вопрос','Ответ','demo',[])
    monkeypatch.chdir(second)
    reopened = chat_store.ChatStore()
    assert reopened.path == original.path
    assert [row['text'] for row in reopened.get(ident)['messages']] == ['Вопрос','Ответ']
    assert not (second/'data').exists()


def test_explicit_relative_chat_path_remains_valid_after_chdir(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    original = chat_store.ChatStore('saved')
    ident = original.create()['id']
    elsewhere = tmp_path/'elsewhere'; elsewhere.mkdir()
    monkeypatch.chdir(elsewhere)
    assert original.get(ident)['id'] == ident


def test_model_settings_survive_different_cwd(tmp_path, monkeypatch):
    monkeypatch.setattr(ia,'AI_CONFIG_PATH',tmp_path/'settings/ai_config.json')
    model = ia.IntelligentAnswerer.__new__(ia.IntelligentAnswerer)
    model.custom_keys = {'Groq':'synthetic-token'}
    model._save_config('Groq','demo-model','synthetic-token')
    elsewhere = tmp_path/'elsewhere'; elsewhere.mkdir()
    monkeypatch.chdir(elsewhere)
    assert model._load_saved_config() == json.loads(ia.AI_CONFIG_PATH.read_text(encoding='utf-8'))
    assert model._load_saved_config()['keys']['Groq'] == 'synthetic-token'
