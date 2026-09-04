"""
Менеджер версий - отслеживание истории изменений команд и правил
"""

import json
from pathlib import Path
from typing import Dict, List, Optional, Any
from datetime import datetime


class Version:
    """Одна версия команды или правила"""
    
    def __init__(self, version_number: int, data: Dict, author: str = 'system',
                 change_description: str = ''):
        self.version_number = version_number
        self.data = data  # Полные данные этой версии
        self.author = author
        self.change_description = change_description
        self.created_at = datetime.now().isoformat()
    
    def to_dict(self) -> Dict:
        return {
            'version_number': self.version_number,
            'data': self.data,
            'author': self.author,
            'change_description': self.change_description,
            'created_at': self.created_at
        }


class VersionHistory:
    """История версий для одного элемента (команда/правило)"""
    
    def __init__(self, item_id: str, item_type: str):
        self.item_id = item_id
        self.item_type = item_type  # 'command' или 'rule'
        self.versions: List[Version] = []
        self.current_version = 0
    
    def add_version(self, data: Dict, author: str = 'system',
                   change_description: str = '') -> int:
        """Добавить новую версию"""
        version_number = len(self.versions) + 1
        version = Version(version_number, data, author, change_description)
        self.versions.append(version)
        self.current_version = version_number
        return version_number
    
    def get_version(self, version_number: int) -> Optional[Version]:
        """Получить конкретную версию"""
        for v in self.versions:
            if v.version_number == version_number:
                return v
        return None
    
    def get_latest_version(self) -> Optional[Version]:
        """Получить последнюю версию"""
        return self.versions[-1] if self.versions else None
    
    def get_all_versions(self) -> List[Dict]:
        """Получить все версии"""
        return [v.to_dict() for v in self.versions]
    
    def rollback_to_version(self, version_number: int) -> Dict:
        """Откатиться к конкретной версии"""
        version = self.get_version(version_number)
        if not version:
            return {'success': False, 'error': f'Версия {version_number} не найдена'}
        
        # Добавить текущее состояние как восстановленное
        self.add_version(
            version.data,
            author='system',
            change_description=f'Откачено к версии {version_number}'
        )
        
        return {
            'success': True,
            'message': f'Откачено к версии {version_number}',
            'current_version': self.current_version,
            'data': version.data
        }
    
    def get_changes_between_versions(self, v1: int, v2: int) -> Dict:
        """Получить различия между двумя версиями"""
        version1 = self.get_version(v1)
        version2 = self.get_version(v2)
        
        if not version1 or not version2:
            return {'success': False, 'error': 'Одна из версий не найдена'}
        
        changes = {
            'from_version': v1,
            'to_version': v2,
            'changes': {}
        }
        
        # Сравнить поля
        all_keys = set(version1.data.keys()) | set(version2.data.keys())
        
        for key in all_keys:
            old_value = version1.data.get(key)
            new_value = version2.data.get(key)
            
            if old_value != new_value:
                changes['changes'][key] = {
                    'old': old_value,
                    'new': new_value
                }
        
        return {'success': True, 'data': changes}
    
    def to_dict(self) -> Dict:
        return {
            'item_id': self.item_id,
            'item_type': self.item_type,
            'versions': self.get_all_versions(),
            'current_version': self.current_version
        }


class VersionManager:
    """Управляет версионированием всех элементов"""
    
    def __init__(self, db_path: str = 'data/versions.json'):
        self.db_path = Path(db_path)
        self.histories: Dict[str, VersionHistory] = {}
        self.version_history = self.histories  # Alias для совместимости с тестами
        self.data_dir = str(self.db_path.parent)  # Для совместимости с тестами
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.load_histories()
        print(f"✅ Менеджер версий инициализирован ({len(self.histories)} элементов)")
    
    def load_histories(self) -> None:
        """Загрузить историю версий"""
        if self.db_path.exists():
            try:
                with open(self.db_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    for item_id, history_data in data.items():
                        history = VersionHistory(
                            item_id=history_data['item_id'],
                            item_type=history_data['item_type']
                        )
                        
                        for version_data in history_data.get('versions', []):
                            version = Version(
                                version_number=version_data['version_number'],
                                data=version_data['data'],
                                author=version_data.get('author', 'system'),
                                change_description=version_data.get('change_description', '')
                            )
                            version.created_at = version_data.get('created_at', version.created_at)
                            history.versions.append(version)
                        
                        history.current_version = history_data.get('current_version', 0)
                        self.histories[item_id] = history
                    
                    print(f"📂 Загружено историй для {len(self.histories)} элементов")
            except Exception as e:
                print(f"❌ Ошибка загрузки версий: {e}")
    
    def save_histories(self) -> None:
        """Сохранить историю версий"""
        try:
            data = {item_id: history.to_dict() for item_id, history in self.histories.items()}
            with open(self.db_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            print(f"💾 Сохранено историй для {len(self.histories)} элементов")
        except Exception as e:
            print(f"❌ Ошибка сохранения: {e}")
    
    def track_change(self, item_id: str, item_type: str, data: Dict,
                    author: str = 'system', change_description: str = '') -> Dict:
        """Отследить изменение элемента"""
        if item_id not in self.histories:
            self.histories[item_id] = VersionHistory(item_id, item_type)
        
        history = self.histories[item_id]
        version_number = history.add_version(data, author, change_description)
        self.save_histories()
        
        return {
            'success': True,
            'message': f'Версия {version_number} сохранена',
            'version_number': version_number,
            'item_id': item_id
        }
    
    def get_history(self, item_id: str) -> Optional[Dict]:
        """Получить историю элемента"""
        history = self.histories.get(item_id)
        if not history:
            return None
        return history.to_dict()
    
    def get_current_version(self, item_id: str) -> Optional[Dict]:
        """Получить текущую версию"""
        history = self.histories.get(item_id)
        if not history:
            return None
        
        version = history.get_latest_version()
        if not version:
            return None
        
        return version.to_dict()
    
    def get_version(self, item_id: str, version_number: int) -> Optional[Dict]:
        """Получить конкретную версию"""
        history = self.histories.get(item_id)
        if not history:
            return None
        
        version = history.get_version(version_number)
        if not version:
            return None
        
        return version.to_dict()
    
    def rollback(self, item_id: str, version_number: int) -> Dict:
        """Откатиться к версии"""
        history = self.histories.get(item_id)
        if not history:
            return {'success': False, 'error': f'История для "{item_id}" не найдена'}
        
        result = history.rollback_to_version(version_number)
        if result['success']:
            self.save_histories()
        return result
    
    def compare_versions(self, item_id: str, v1: int, v2: int) -> Dict:
        """Сравнить две версии"""
        history = self.histories.get(item_id)
        if not history:
            return {'success': False, 'message': f'История для "{item_id}" не найдена', 'data': None}
        
        result = history.get_changes_between_versions(v1, v2)
        if result.get('success') == False:
            return {'success': False, 'message': result.get('error', 'Ошибка'), 'data': None}
        
        return {'success': True, 'message': 'Версии сравнены', 'data': result}
    
    def get_statistics(self) -> Dict:
        """Получить статистику версионирования"""
        total_items = len(self.histories)
        total_versions = sum(len(h.versions) for h in self.histories.values())
        
        items_by_type = {}
        for history in self.histories.values():
            item_type = history.item_type
            if item_type not in items_by_type:
                items_by_type[item_type] = 0
            items_by_type[item_type] += 1
        
        return {
            'total_items': total_items,
            'total_tracked_items': total_items,
            'total_versions': total_versions,
            'average_versions_per_item': round(total_versions / total_items, 2) if total_items > 0 else 0,
            'items': items_by_type,  # ← Added for compatibility
            'items_by_type': items_by_type
        }
    
    def __repr__(self):
        return f"VersionManager({len(self.histories)} элементов отслеживается)"


def get_version_manager(db_path: str = 'data/versions.json') -> VersionManager:
    """Factory функция"""
    return VersionManager(db_path)
