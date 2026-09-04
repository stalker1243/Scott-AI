"""
File System Manager для Scott AI
Управление файлами и запуск программ
"""

import os
import subprocess
import shutil
import sys
from pathlib import Path
from typing import List, Dict, Optional

class FileSystemManager:
    """Управление файлами и программами на Windows"""
    
    def __init__(self):
        self.desktop_path = os.path.expanduser("~\\Desktop")
        self.start_menu_path = os.path.expanduser("~\\AppData\\Roaming\\Microsoft\\Windows\\Start Menu\\Programs")
        self.quick_access_path = os.path.expanduser("~\\AppData\\Roaming\\Microsoft\\Windows\\Recent\\Quick access")
        
    def find_program(self, program_name: str) -> Optional[str]:
        """
        Найти программу по имени
        1. Рабочий стол
        2. Панель быстрого доступа
        3. Меню Пуск
        4. PATH / стандартные приложения Windows
        """
        program_lower = program_name.lower().strip()
        if not program_lower:
            return None

        # Поиск в PATH / стандартных местах Windows
        resolved = shutil.which(program_name)
        if resolved:
            return resolved

        for candidate in self._candidate_program_paths(program_lower):
            if os.path.exists(candidate):
                return candidate

        for directory in [self.desktop_path, self.quick_access_path, self.start_menu_path]:
            match = self._search_in_directory(directory, program_lower)
            if match:
                return match

        return None

    def _candidate_program_paths(self, program_name: str) -> List[str]:
        """Сформировать кандидаты для запуска по имени программы."""
        candidates = []
        env_path = os.environ.get('PATH', '')
        for entry in env_path.split(os.pathsep):
            if not entry:
                continue
            for suffix in ['.exe', '.bat', '.cmd', '.lnk']:
                candidates.append(os.path.join(entry, program_name + suffix))
        candidates.extend([
            os.path.join(os.path.expanduser('~'), 'AppData', 'Local', 'Programs', program_name),
            os.path.join(os.path.expanduser('~'), 'AppData', 'Local', 'Microsoft', 'WindowsApps', program_name),
            os.path.join('C:\\Windows\\System32', program_name),
            os.path.join('C:\\Windows', program_name),
        ])
        return candidates
    
    def _search_in_directory(self, directory: str, program_name: str) -> Optional[str]:
        """Поиск программы в директории"""
        if not os.path.exists(directory):
            return None
        
        try:
            for item in os.listdir(directory):
                item_lower = item.lower()
                
                # Проверка точного совпадения или частичного
                if program_name in item_lower:
                    full_path = os.path.join(directory, item)
                    
                    # Проверка расширения
                    if item.endswith(('.lnk', '.exe', '.bat', '.cmd', '.msi')):
                        return full_path
                    
                    # Для ярлыков на рабочем столе
                    if item.endswith('.lnk'):
                        target = self._get_shortcut_target(full_path)
                        if target:
                            return target
                    
                    # Если папка с нужным именем - может быть portable приложение
                    if os.path.isdir(full_path):
                        for subitem in os.listdir(full_path):
                            if subitem.endswith('.exe'):
                                return os.path.join(full_path, subitem)
        except Exception as e:
            print(f"Ошибка при поиске в {directory}: {e}")
        
        return None
    
    def _get_shortcut_target(self, shortcut_path: str) -> Optional[str]:
        """Получить целевой путь из ярлыка (.lnk)"""
        try:
            from pathlib import Path
            link = Path(shortcut_path)
            
            # Простой метод - для ярлыков можно использовать pyshortcuts
            # но для быстроты попробуем subprocess
            result = subprocess.run(
                f'powershell -Command "[System.IO.File]::ReadAllText(\\"{shortcut_path}\\")"',
                capture_output=True,
                text=True
            )
            # Это не будет работать так, нужна другая библиотека
            return None
        except:
            return None
    
    def open_program(self, program_path: str) -> Dict:
        """
        Открыть программу
        """
        try:
            if not os.path.exists(program_path):
                return {"success": False, "message": f"❌ Программа не найдена: {program_path}"}

            if os.name == 'nt':
                if program_path.endswith('.lnk'):
                    os.startfile(program_path)
                else:
                    subprocess.Popen([program_path], shell=False, creationflags=subprocess.CREATE_NEW_CONSOLE if hasattr(subprocess, 'CREATE_NEW_CONSOLE') else 0)
            else:
                subprocess.Popen([program_path])

            program_name = os.path.basename(program_path)
            return {"success": True, "message": f"✅ Программа открыта: {program_name}"}
        except Exception as e:
            return {"success": False, "message": f"❌ Ошибка при открытии программы: {str(e)}"}
    
    def find_file(self, file_path: str) -> Optional[str]:
        """
        Найти файл по полному пути или имени
        """
        # Если это полный путь
        if os.path.exists(file_path):
            return file_path
        
        # Если только имя файла - поискать на рабочем столе
        if os.path.exists(os.path.join(self.desktop_path, file_path)):
            return os.path.join(self.desktop_path, file_path)
        
        return None
    
    def open_file(self, file_path: str) -> Dict:
        """Открыть файл"""
        resolved_path = self.find_file(file_path)
        if not resolved_path:
            return {"success": False, "message": f"❌ Файл не найден: {file_path}"}
        
        try:
            os.startfile(resolved_path)
            return {"success": True, "message": f"✅ Файл открыт: {os.path.basename(resolved_path)}"}
        except Exception as e:
            return {"success": False, "message": f"❌ Ошибка при открытии файла: {str(e)}"}
    
    def delete_file(self, file_path: str) -> Dict:
        """Удалить файл"""
        resolved_path = self.find_file(file_path)
        if not resolved_path:
            return {"success": False, "message": f"❌ Файл не найден: {file_path}"}
        
        try:
            if os.path.isdir(resolved_path):
                shutil.rmtree(resolved_path)
                return {"success": True, "message": f"✅ Папка удалена: {os.path.basename(resolved_path)}"}
            else:
                os.remove(resolved_path)
                return {"success": True, "message": f"✅ Файл удалён: {os.path.basename(resolved_path)}"}
        except Exception as e:
            return {"success": False, "message": f"❌ Ошибка при удалении: {str(e)}"}
    
    def rename_file(self, file_path: str, new_name: str) -> Dict:
        """Переименовать файл"""
        resolved_path = self.find_file(file_path)
        if not resolved_path:
            return {"success": False, "message": f"❌ Файл не найден: {file_path}"}
        
        try:
            directory = os.path.dirname(resolved_path)
            new_path = os.path.join(directory, new_name)
            os.rename(resolved_path, new_path)
            return {"success": True, "message": f"✅ Файл переименован в: {new_name}"}
        except Exception as e:
            return {"success": False, "message": f"❌ Ошибка при переименовании: {str(e)}"}
    
    def move_file(self, file_path: str, destination: str) -> Dict:
        """Переместить файл"""
        resolved_path = self.find_file(file_path)
        if not resolved_path:
            return {"success": False, "message": f"❌ Файл не найден: {file_path}"}
        
        try:
            shutil.move(resolved_path, destination)
            return {"success": True, "message": f"✅ Файл перемещён в: {destination}"}
        except Exception as e:
            return {"success": False, "message": f"❌ Ошибка при перемещении: {str(e)}"}
    
    def list_desktop_files(self) -> List[str]:
        """Список файлов на рабочем столе"""
        try:
            return os.listdir(self.desktop_path)
        except:
            return []
    
    def search_files(self, pattern: str, folder: Optional[str] = None, max_depth: int = 3) -> List[Dict]:
        """
        Поиск файлов по паттерну
        pattern: имя или расширение файла (например "*.pdf" или "report")
        folder: папка для поиска (если None, ищет на рабочем столе и Documents)
        """
        results = []
        pattern_lower = pattern.lower()
        
        # Папки для поиска
        search_folders = []
        if folder:
            search_folders.append(folder)
        else:
            search_folders = [
                self.desktop_path,
                os.path.expanduser("~\\Documents"),
                os.path.expanduser("~\\Downloads")
            ]
        
        for base_folder in search_folders:
            if not os.path.exists(base_folder):
                continue
                
            try:
                for root, dirs, files in os.walk(base_folder):
                    # Ограничить глубину поиска
                    depth = root[len(base_folder):].count(os.sep)
                    if depth > max_depth:
                        continue
                    
                    for file in files:
                        file_lower = file.lower()
                        # Проверить по имени или расширению
                        if (pattern_lower in file_lower or 
                            file_lower.endswith(pattern_lower)):
                            full_path = os.path.join(root, file)
                            try:
                                size = os.path.getsize(full_path)
                                results.append({
                                    "name": file,
                                    "path": full_path,
                                    "size": size,
                                    "folder": root
                                })
                            except:
                                pass
            except:
                pass
        
        return results
    
    def find_in_file_content(self, search_text: str, folder: Optional[str] = None, 
                            extensions: List[str] = None) -> List[Dict]:
        """
        Поиск текста в содержимом файлов
        extensions: список расширений для поиска (например ['.txt', '.log', '.py'])
        """
        if not extensions:
            extensions = ['.txt', '.log', '.md', '.py', '.js']
        
        results = []
        search_lower = search_text.lower()
        
        search_folders = []
        if folder:
            search_folders.append(folder)
        else:
            search_folders = [
                self.desktop_path,
                os.path.expanduser("~\\Documents")
            ]
        
        for base_folder in search_folders:
            if not os.path.exists(base_folder):
                continue
            
            try:
                for root, dirs, files in os.walk(base_folder):
                    for file in files:
                        if any(file.lower().endswith(ext) for ext in extensions):
                            file_path = os.path.join(root, file)
                            try:
                                with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                                    for line_num, line in enumerate(f, 1):
                                        if search_lower in line.lower():
                                            results.append({
                                                "file": file,
                                                "path": file_path,
                                                "line": line_num,
                                                "content": line.strip()[:100]  # Первые 100 символов
                                            })
                            except:
                                pass
            except:
                pass
        
        return results[:50]  # Ограничить результаты


# Глобальный экземпляр
file_manager = FileSystemManager()
