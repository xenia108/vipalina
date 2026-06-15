#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import requests
from bs4 import BeautifulSoup
import os
import logging
import time
import re
from urllib.parse import urljoin, urlparse
from typing import Set, List

class ZeroCoderParser:
    def __init__(self, base_url: str = "https://zerocoder.ru", output_dir: str = "parsed_pages"):
        self.base_url = base_url
        self.output_dir = output_dir
        self.visited_urls: Set[str] = set()
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        })
        
        # Настройка логирования
        self.setup_logging()
        
        # Создание директории для результатов
        self.create_output_directory()
    
    def setup_logging(self):
        """Настройка системы логирования"""
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - %(levelname)s - %(message)s',
            handlers=[
                logging.FileHandler('zerocoder_parser.log', encoding='utf-8'),
                logging.StreamHandler()
            ]
        )
        self.logger = logging.getLogger(__name__)
        self.logger.info("Парсер ZeroCoder.ru запущен")
    
    def create_output_directory(self):
        """Создание директории для сохранения результатов"""
        if not os.path.exists(self.output_dir):
            os.makedirs(self.output_dir)
            self.logger.info(f"Создана директория: {self.output_dir}")
    
    def is_valid_url(self, url: str) -> bool:
        """Проверка валидности URL и принадлежности к домену zerocoder.ru"""
        parsed = urlparse(url)
        return (parsed.netloc == 'zerocoder.ru' or 
                parsed.netloc == 'www.zerocoder.ru' or
                parsed.netloc == '' and url.startswith('/'))
    
    def clean_filename(self, text: str) -> str:
        """Очистка текста для использования в качестве имени файла"""
        # Удаляем недопустимые символы для имени файла
        cleaned = re.sub(r'[<>:"/\\|?*]', '_', text)
        # Ограничиваем длину
        if len(cleaned) > 100:
            cleaned = cleaned[:100]
        return cleaned.strip()
    
    def extract_text_content(self, soup: BeautifulSoup) -> str:
        """Извлечение текстового содержимого страницы"""
        # Удаляем ненужные элементы
        for element in soup(['script', 'style', 'nav', 'footer', 'header']):
            element.decompose()
        
        # Извлекаем заголовок
        title = soup.find('title')
        title_text = title.get_text().strip() if title else "Без заголовка"
        
        # Извлекаем основной контент
        main_content = soup.find('main') or soup.find('article') or soup.find('div', class_='content')
        if main_content:
            content_text = main_content.get_text(separator='\n', strip=True)
        else:
            # Если нет основного контейнера, берем весь body
            body = soup.find('body')
            content_text = body.get_text(separator='\n', strip=True) if body else soup.get_text(separator='\n', strip=True)
        
        # Формируем итоговый текст
        result = f"ЗАГОЛОВОК: {title_text}\n\n"
        result += f"СОДЕРЖИМОЕ:\n{content_text}"
        
        return result
    
    def save_page_content(self, url: str, content: str, title: str = None):
        """Сохранение содержимого страницы в файл"""
        # Генерируем имя файла на основе URL
        parsed_url = urlparse(url)
        path_parts = [part for part in parsed_url.path.split('/') if part]
        
        if not path_parts:
            filename = "index.txt"
        else:
            filename = self.clean_filename('_'.join(path_parts)) + ".txt"
        
        # Если есть заголовок, используем его для улучшения имени файла
        if title and title != "Без заголовка":
            clean_title = self.clean_filename(title)
            if clean_title:
                filename = f"{clean_title}_{filename}"
        
        filepath = os.path.join(self.output_dir, filename)
        
        # Проверяем, что файл с таким именем не существует, если да - добавляем номер
        counter = 1
        original_filepath = filepath
        while os.path.exists(filepath):
            name, ext = os.path.splitext(original_filepath)
            filepath = f"{name}_{counter}{ext}"
            counter += 1
        
        try:
            with open(filepath, 'w', encoding='utf-8') as f:
                f.write(f"URL: {url}\n")
                f.write("=" * 50 + "\n\n")
                f.write(content)
            
            self.logger.info(f"Сохранено: {filepath}")
        except Exception as e:
            self.logger.error(f"Ошибка при сохранении файла {filepath}: {e}")
    
    def parse_page(self, url: str) -> List[str]:
        """Парсинг отдельной страницы"""
        if url in self.visited_urls:
            return []
        
        self.visited_urls.add(url)
        self.logger.info(f"Парсинг страницы: {url}")
        
        try:
            response = self.session.get(url, timeout=10)
            response.raise_for_status()
            
            soup = BeautifulSoup(response.content, 'lxml')
            
            # Извлекаем текстовый контент
            text_content = self.extract_text_content(soup)
            
            # Получаем заголовок для имени файла
            title = soup.find('title')
            title_text = title.get_text().strip() if title else None
            
            # Сохраняем контент
            self.save_page_content(url, text_content, title_text)
            
            # Извлекаем ссылки на другие страницы того же домена
            links = []
            for link in soup.find_all('a', href=True):
                href = link['href']
                absolute_url = urljoin(url, href)
                
                if self.is_valid_url(absolute_url) and absolute_url not in self.visited_urls:
                    # Убираем якоря и параметры запроса для чистоты
                    clean_url = absolute_url.split('#')[0].split('?')[0]
                    if clean_url not in links and clean_url != url:
                        links.append(clean_url)
            
            return links
            
        except requests.RequestException as e:
            self.logger.error(f"Ошибка при загрузке страницы {url}: {e}")
            return []
        except Exception as e:
            self.logger.error(f"Неожиданная ошибка при обработке {url}: {e}")
            return []
    
    def run(self, max_depth: int = 2):
        """Запуск парсера"""
        self.logger.info(f"Начинаем парсинг сайта {self.base_url} с максимальной глубиной {max_depth}")
        
        urls_to_process = [self.base_url]
        current_depth = 0
        
        while urls_to_process and current_depth < max_depth:
            self.logger.info(f"Обрабатываем уровень {current_depth + 1}, страниц: {len(urls_to_process)}")
            
            next_level_urls = []
            
            for url in urls_to_process:
                # Небольшая задержка между запросами
                time.sleep(1)
                
                new_urls = self.parse_page(url)
                next_level_urls.extend(new_urls)
            
            # Убираем дубликаты
            urls_to_process = list(set(next_level_urls))
            current_depth += 1
        
        self.logger.info(f"Парсинг завершен. Обработано {len(self.visited_urls)} страниц")
        self.logger.info(f"Результаты сохранены в директории: {self.output_dir}")

def main():
    """Главная функция"""
    parser = ZeroCoderParser()
    parser.run(max_depth=2)

if __name__ == "__main__":
    main() 