"""
Веб-скрейпер для получения информации с интернета
Курсы валют, новости, погода, и т.д.
"""

import requests
from bs4 import BeautifulSoup
import re
from typing import Dict, Optional, List
import json
from datetime import datetime


class WebScraper:
    """Получает информацию с веб-сайтов и анализирует её"""
    
    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        })
        print("✅ Веб-скрейпер инициализирован")
    
    def search_google(self, query: str) -> Dict:
        """Поиск информации через Google"""
        try:
            search_url = f"https://www.google.com/search?q={query}"
            response = self.session.get(search_url, timeout=10)
            response.encoding = 'utf-8'
            
            soup = BeautifulSoup(response.content, 'html.parser')
            
            # Извлекаем результаты поиска
            results = []
            for g in soup.find_all('div', class_='g'):
                try:
                    title = g.find('h3', class_='r')
                    link = g.find('a')
                    desc = g.find('span', class_='st')
                    
                    if title and link and desc:
                        results.append({
                            'title': title.text,
                            'link': link.get('href'),
                            'description': desc.text
                        })
                except:
                    continue
            
            return {
                'status': 'success',
                'query': query,
                'results': results[:5],  # Первые 5 результатов
                'timestamp': datetime.now().isoformat()
            }
        except Exception as e:
            return {'status': 'error', 'message': str(e)}
    
    def get_dollar_rate(self) -> Dict:
        """Получить курс доллара"""
        try:
            # Используем API курсов
            url = "https://api.exchangerate-api.com/v4/latest/USD"
            response = self.session.get(url, timeout=10)
            data = response.json()
            
            usd_to_rub = data.get('rates', {}).get('RUB', 'N/A')
            
            return {
                'status': 'success',
                'currency': 'USD',
                'rate': usd_to_rub,
                'timestamp': datetime.now().isoformat(),
                'source': 'exchangerate-api.com'
            }
        except Exception as e:
            # Fallback: используем CBR курсы
            try:
                url = "https://www.cbr.ru/scripts/XML_daily.asp"
                response = self.session.get(url, timeout=10)
                
                # Парсим XML
                soup = BeautifulSoup(response.content, 'xml')
                usd_elem = soup.find('Valute', Nominal='1')
                
                if usd_elem:
                    rate = float(usd_elem.Value.text.replace(',', '.'))
                    return {
                        'status': 'success',
                        'currency': 'USD',
                        'rate': rate,
                        'timestamp': datetime.now().isoformat(),
                        'source': 'CBR'
                    }
            except:
                pass
            
            return {'status': 'error', 'message': f"Не смог получить курс доллара: {str(e)}"}
    
    def get_euro_rate(self) -> Dict:
        """Получить курс евро"""
        try:
            url = "https://api.exchangerate-api.com/v4/latest/EUR"
            response = self.session.get(url, timeout=10)
            data = response.json()
            
            eur_to_rub = data.get('rates', {}).get('RUB', 'N/A')
            
            return {
                'status': 'success',
                'currency': 'EUR',
                'rate': eur_to_rub,
                'timestamp': datetime.now().isoformat(),
                'source': 'exchangerate-api.com'
            }
        except Exception as e:
            return {'status': 'error', 'message': str(e)}
    
    def get_bitcoin_price(self) -> Dict:
        """Получить цену Bitcoin"""
        try:
            url = "https://api.coingecko.com/api/v3/simple/price?ids=bitcoin&vs_currencies=usd,rub"
            response = self.session.get(url, timeout=10)
            data = response.json()
            
            btc = data.get('bitcoin', {})
            
            return {
                'status': 'success',
                'crypto': 'Bitcoin',
                'price_usd': btc.get('usd'),
                'price_rub': btc.get('rub'),
                'timestamp': datetime.now().isoformat(),
                'source': 'coingecko'
            }
        except Exception as e:
            return {'status': 'error', 'message': str(e)}
    
    def get_weather(self, city: str = "Moscow") -> Dict:
        """Получить погоду"""
        try:
            # Используем простой API
            url = f"https://api.open-meteo.com/v1/forecast?latitude=55.75&longitude=37.62&current=temperature_2m,weather_code,wind_speed_10m"
            response = self.session.get(url, timeout=10)
            data = response.json()
            
            current = data.get('current', {})
            
            weather_codes = {
                0: 'Ясное небо',
                1: 'Облачно',
                2: 'Переменная облачность',
                3: 'Пасмурно',
                45: 'Туман',
                48: 'Туман с изморосью',
                51: 'Легкая морось',
                53: 'Морось',
                55: 'Интенсивная морось',
                61: 'Легкий дождь',
                63: 'Умеренный дождь',
                65: 'Сильный дождь',
                71: 'Легкий снег',
                73: 'Умеренный снег',
                75: 'Сильный снег',
                77: 'Зёрна снега',
                80: 'Сильный ливень',
                81: 'Ливень с грозой',
                82: 'Сильный ливень с грозой',
                85: 'Снег с ливнем',
                86: 'Сильный снег с ливнем',
                95: 'Гроза',
                96: 'Гроза с градом',
                99: 'Гроза с сильным градом'
            }
            
            weather_code = current.get('weather_code', 0)
            
            return {
                'status': 'success',
                'city': city,
                'temperature': current.get('temperature_2m'),
                'weather': weather_codes.get(weather_code, 'Неизвестно'),
                'wind_speed': current.get('wind_speed_10m'),
                'timestamp': datetime.now().isoformat(),
                'source': 'open-meteo'
            }
        except Exception as e:
            return {'status': 'error', 'message': str(e)}
    
    def get_news(self, topic: str = "technology") -> Dict:
        """Получить новости"""
        try:
            # Используем NewsAPI
            url = f"https://newsapi.org/v2/everything?q={topic}&language=ru&sortBy=publishedAt&pageSize=5"
            response = self.session.get(url, timeout=10)
            
            if response.status_code != 200:
                return {'status': 'error', 'message': f"API вернул ошибку: {response.status_code}"}
            
            data = response.json()
            articles = data.get('articles', [])
            
            news_list = []
            for article in articles[:5]:
                news_list.append({
                    'title': article.get('title'),
                    'description': article.get('description'),
                    'url': article.get('url'),
                    'source': article.get('source', {}).get('name'),
                    'published_at': article.get('publishedAt')
                })
            
            return {
                'status': 'success',
                'topic': topic,
                'news': news_list,
                'timestamp': datetime.now().isoformat()
            }
        except Exception as e:
            return {'status': 'error', 'message': str(e)}
    
    def parse_search_results(self, html_content: str) -> str:
        """Парсить результаты поиска из HTML"""
        try:
            soup = BeautifulSoup(html_content, 'html.parser')
            
            # Ищем первый наиболее релевантный результат
            text_blocks = soup.find_all(['p', 'h2', 'h3', 'span'], limit=10)
            
            summary = []
            for block in text_blocks:
                text = block.get_text().strip()
                if text and len(text) > 20 and len(text) < 500:
                    summary.append(text)
            
            return ' '.join(summary[:3]) if summary else "Не удалось парсить результаты"
        except Exception as e:
            return f"Ошибка парсинга: {str(e)}"


def get_web_scraper() -> WebScraper:
    """Factory функция для получения скрейпера"""
    return WebScraper()
