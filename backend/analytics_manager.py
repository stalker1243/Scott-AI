"""
Расширенная аналитика с графиками и статистикой
"""

from typing import Dict, List, Any
from datetime import datetime, timedelta
from collections import defaultdict
import json
from pathlib import Path

class AnalyticsManager:
    """Менеджер для аналитики и статистики"""
    
    def __init__(self, extended_executor=None):
        self.extended_executor = extended_executor  # Для доступа к метрикам
        self.analytics_data = {
            'daily_commands': defaultdict(int),
            'hourly_commands': defaultdict(int),
            'command_types': defaultdict(int),
            'most_used_apps': defaultdict(int),
            'response_times': [],
            'error_rate': 0
        }
        print("✅ Менеджер аналитики инициализирован")
    
    def record_command(self, command_type: str, command: str, success: bool, response_time: float = 0):
        """Записать информацию о команде"""
        now = datetime.now()
        date_key = now.strftime('%Y-%m-%d')
        hour_key = now.strftime('%Y-%m-%d %H:00')
        
        # Статистика по дням
        self.analytics_data['daily_commands'][date_key] += 1
        
        # Статистика по часам
        self.analytics_data['hourly_commands'][hour_key] += 1
        
        # Статистика по типам команд
        self.analytics_data['command_types'][command_type] += 1
        
        # Извлечь приложение если это команда открытия
        if 'open_app' in command_type or 'открой' in command.lower():
            words = command.split()
            for i, word in enumerate(words):
                if word in ['открой', 'запусти'] and i + 1 < len(words):
                    app = words[i + 1]
                    self.analytics_data['most_used_apps'][app] += 1
                    break
        
        # Время отклика
        if response_time > 0:
            self.analytics_data['response_times'].append({
                'timestamp': now.isoformat(),
                'time': response_time,
                'type': command_type
            })
            # Оставить только последние 1000
            if len(self.analytics_data['response_times']) > 1000:
                self.analytics_data['response_times'] = self.analytics_data['response_times'][-1000:]
    
    def get_daily_statistics(self, days: int = 7) -> Dict[str, Any]:
        """Получить статистику по дням"""
        today = datetime.now().date()
        date_range = [(today - timedelta(days=i)).strftime('%Y-%m-%d') for i in range(days)]
        
        daily_data = {
            'dates': date_range,
            'commands': [self.analytics_data['daily_commands'].get(date, 0) for date in date_range],
            'total': sum(self.analytics_data['daily_commands'].values())
        }
        
        return daily_data
    
    def get_hourly_statistics(self, hours: int = 24) -> Dict[str, Any]:
        """Получить статистику по часам"""
        now = datetime.now()
        hour_range = [
            (now - timedelta(hours=i)).strftime('%Y-%m-%d %H:00')
            for i in range(hours)
        ]
        hour_range.reverse()
        
        hourly_data = {
            'hours': hour_range,
            'commands': [self.analytics_data['hourly_commands'].get(hour, 0) for hour in hour_range],
            'total': sum(self.analytics_data['hourly_commands'].values())
        }
        
        return hourly_data
    
    def get_command_type_distribution(self) -> Dict[str, Any]:
        """Получить распределение по типам команд"""
        types = dict(self.analytics_data['command_types'])
        total = sum(types.values()) or 1
        
        # Сортировать по количеству
        sorted_types = sorted(types.items(), key=lambda x: x[1], reverse=True)
        
        distribution = {
            'types': [t[0] for t in sorted_types],
            'counts': [t[1] for t in sorted_types],
            'percentages': [round(t[1] / total * 100, 1) for t in sorted_types],
            'total': total
        }
        
        return distribution
    
    def get_top_apps(self, limit: int = 10) -> Dict[str, Any]:
        """Получить самые используемые приложения"""
        apps = dict(self.analytics_data['most_used_apps'])
        sorted_apps = sorted(apps.items(), key=lambda x: x[1], reverse=True)[:limit]
        
        return {
            'apps': [app[0] for app in sorted_apps],
            'usage_count': [app[1] for app in sorted_apps],
            'total': sum(apps.values())
        }
    
    def get_average_response_time(self) -> Dict[str, Any]:
        """Получить среднее время отклика"""
        if not self.analytics_data['response_times']:
            return {'average': 0, 'min': 0, 'max': 0, 'count': 0}
        
        times = [r['time'] for r in self.analytics_data['response_times']]
        
        return {
            'average': round(sum(times) / len(times), 3),
            'min': round(min(times), 3),
            'max': round(max(times), 3),
            'count': len(times),
            'by_type': self._avg_response_time_by_type()
        }
    
    def _avg_response_time_by_type(self) -> Dict[str, float]:
        """Среднее время по типам команд"""
        by_type = defaultdict(list)
        
        for record in self.analytics_data['response_times']:
            by_type[record['type']].append(record['time'])
        
        return {
            cmd_type: round(sum(times) / len(times), 3)
            for cmd_type, times in by_type.items()
        }
    
    def get_comprehensive_analytics(self) -> Dict[str, Any]:
        """Получить полную аналитику"""
        return {
            'daily': self.get_daily_statistics(7),
            'hourly': self.get_hourly_statistics(24),
            'command_types': self.get_command_type_distribution(),
            'top_apps': self.get_top_apps(10),
            'response_time': self.get_average_response_time(),
            'total_commands': sum(self.analytics_data['daily_commands'].values())
        }
    
    def export_analytics(self, filepath: str = 'data/analytics.json') -> Dict:
        """Экспортировать аналитику в JSON"""
        try:
            analytics = self.get_comprehensive_analytics()
            path = Path(filepath)
            path.parent.mkdir(parents=True, exist_ok=True)
            
            # Преобразовать defaultdict в обычный dict для JSON
            data_to_export = {
                'generated_at': datetime.now().isoformat(),
                'analytics': analytics,
                'raw_data': {
                    'daily_commands': dict(self.analytics_data['daily_commands']),
                    'hourly_commands': dict(self.analytics_data['hourly_commands']),
                    'command_types': dict(self.analytics_data['command_types']),
                    'most_used_apps': dict(self.analytics_data['most_used_apps'])
                }
            }
            
            with open(path, 'w', encoding='utf-8') as f:
                json.dump(data_to_export, f, ensure_ascii=False, indent=2)
            
            return {'success': True, 'message': f'Аналитика экспортирована в {filepath}'}
        except Exception as e:
            return {'success': False, 'error': str(e)}
    
    def get_trend_analysis(self) -> Dict[str, Any]:
        """Анализ тренда использования"""
        daily = self.get_daily_statistics(7)
        commands = daily['commands']
        
        if len(commands) < 2:
            return {'trend': 'insufficient_data', 'trend_percentage': 0}
        
        # Простое сравнение: последние 3 дня vs предыдущие 3 дня
        recent = sum(commands[-3:]) if len(commands) >= 3 else commands[-1]
        previous = sum(commands[-6:-3]) if len(commands) >= 6 else sum(commands[:-1])
        
        if previous == 0:
            trend_percentage = 100 if recent > 0 else 0
        else:
            trend_percentage = round((recent - previous) / previous * 100, 1)
        
        trend = 'up' if trend_percentage > 0 else 'down' if trend_percentage < 0 else 'stable'
        
        return {
            'trend': trend,
            'trend_percentage': trend_percentage,
            'recent_total': recent,
            'previous_total': previous
        }
    
    def get_recommendations(self) -> List[Dict[str, str]]:
        """Получить рекомендации на основе аналитики"""
        recommendations = []
        
        # Рекомендация 1: Самые используемые приложения
        top_apps = self.get_top_apps(3)
        if top_apps['apps']:
            recommendations.append({
                'type': 'frequent_app',
                'title': 'Быстрый доступ',
                'message': f'Ты часто открываешь {top_apps["apps"][0]}. Добавить ярлык?'
            })
        
        # Рекомендация 2: Тренд использования
        trend = self.get_trend_analysis()
        if trend['trend'] == 'up' and trend['trend_percentage'] > 10:
            recommendations.append({
                'type': 'usage_trend',
                'title': 'Растущее использование',
                'message': f'Использование Scott растет на {trend["trend_percentage"]:.0f}% 📈'
            })
        
        # Рекомендация 3: Лучшее время использования
        hourly = self.get_hourly_statistics(24)
        max_hour_idx = hourly['commands'].index(max(hourly['commands'])) if hourly['commands'] else 0
        if max_hour_idx > 0:
            peak_hour = hourly['hours'][max_hour_idx].split()[1]
            recommendations.append({
                'type': 'peak_usage',
                'title': 'Пиковое время',
                'message': f'Ты чаще всего используешь Scott около {peak_hour}'
            })
        
        return recommendations
    
    def __repr__(self):
        total = sum(self.analytics_data['daily_commands'].values())
        return f"AnalyticsManager({total} команд записано)"


def get_analytics_manager(extended_executor=None) -> AnalyticsManager:
    """Factory функция"""
    return AnalyticsManager(extended_executor)
