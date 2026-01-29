# main.py

import os
import time
import requests
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, NoSuchElementException, StaleElementReferenceException
import cv2
import numpy as np
from urllib.parse import parse_qs, urlparse, unquote
import random

# --- Настройки ---
CHROMEDRIVER_PATH = r"C:\Users\Dmitriy\Documents\GitHub\Web-scraping\chromedriver.exe"
SEARCH_QUERIES = {"polar_bear": "polar bear", "brown_bear": "brown bear"}
IMAGES_NEEDED = 1000
IMAGES_TO_FETCH = int(IMAGES_NEEDED * 1.5)  # Еще больше запас
DATASET_DIR = "dataset"

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/133.0.0.0 Safari/537.36'
}
# --- /Настройки ---

def create_directories():
    """Создает папки для датасета."""
    os.makedirs(DATASET_DIR, exist_ok=True)
    for class_name in SEARCH_QUERIES.keys():
        os.makedirs(os.path.join(DATASET_DIR, class_name), exist_ok=True)
    print("Директории созданы.")

def download_image(url, save_path):
    """Загружает и сохраняет изображение, проверяя его корректность."""
    try:
        # Очистка URL от параметров
        clean_url = url.split('?')[0] if '?' in url else url
        
        response = requests.get(clean_url, headers=HEADERS, timeout=15, stream=True)
        response.raise_for_status()
        
        # Проверка размера файла
        content_length = int(response.headers.get('content-length', 0))
        if content_length < 5120:  # Минимальный размер 5KB
            print(f"  - Файл слишком маленький: {content_length} bytes")
            return False

        # Попробовать открыть как изображение
        image_array = np.asarray(bytearray(response.content), dtype=np.uint8)
        image_np = cv2.imdecode(image_array, cv2.IMREAD_COLOR)
        if image_np is None:
            print(f"  - Скачанный файл не является изображением или поврежден")
            return False

        # Проверка минимальных размеров изображения
        height, width = image_np.shape[:2]
        if width < 100 or height < 100:
            print(f"  - Изображение слишком маленькое: {width}x{height}")
            return False

        # Сохранить
        cv2.imwrite(save_path, image_np)
        print(f"  - Сохранено: {os.path.basename(save_path)}")
        return True
    except Exception as e:
        print(f"  - Ошибка при загрузке: {e}")
        return False

def setup_driver():
    """Настраивает веб-драйвер с обходом детектирования."""
    chrome_options = Options()
    
    # Обход детектирования автоматизации
    chrome_options.add_argument("--disable-blink-features=AutomationControlled")
    chrome_options.add_experimental_option("excludeSwitches", ["enable-automation"])
    chrome_options.add_experimental_option('useAutomationExtension', False)
    chrome_options.add_argument('--disable-extensions')
    
    # Дополнительные настройки для стабильности
    chrome_options.add_argument("--disable-gpu")
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("--disable-notifications")
    chrome_options.add_argument("--disable-popup-blocking")
    chrome_options.add_argument("--start-maximized")
    
    # Рандомные настройки для имитации человека
    chrome_options.add_argument(f"--window-size={random.randint(1200, 1920)},{random.randint(800, 1080)}")
    
    # User Agent
    chrome_options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/133.0.0.0 Safari/537.36")
    
    service = Service(CHROMEDRIVER_PATH)
    driver = webdriver.Chrome(service=service, options=chrome_options)
    
    # Дополнительные скрипты для обхода детектирования
    driver.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
    driver.execute_script("Object.defineProperty(navigator, 'plugins', {get: () => [1, 2, 3]})")
    driver.execute_script("Object.defineProperty(navigator, 'languages', {get: () => ['en-US', 'en']})")
    
    return driver

def wait_for_page_load(driver, max_wait=30):
    """Ждет полной загрузки страницы."""
    print("  - Ожидание полной загрузки страницы...")
    
    # Ждем, пока документ будет в состоянии complete или interactive
    WebDriverWait(driver, max_wait).until(
        lambda d: d.execute_script("return document.readyState") in ["complete", "interactive"]
    )
    
    # Дополнительная пауза для полной загрузки контента
    time.sleep(2)
    
    # Проверяем наличие основных элементов страницы
    try:
        # Проверяем наличие поисковой строки или футера
        WebDriverWait(driver, 5).until(
            EC.presence_of_element_located((By.TAG_NAME, "body"))
        )
        print("  - Страница загружена")
        return True
    except:
        print("  - Страница частично загружена")
        return True

def extract_image_urls_from_page(driver):
    """Извлекает все URL изображений со страницы без кликов."""
    unique_urls = set()
    
    # Способ 1: Ищем ссылки с параметром img_url
    try:
        links = driver.find_elements(By.CSS_SELECTOR, "a[href*='img_url']")
        print(f"  - Найдено {len(links)} ссылок с img_url")
        
        for link in links:
            try:
                href = link.get_attribute("href")
                if href and "img_url=" in href:
                    parsed_url = urlparse(href)
                    query_params = parse_qs(parsed_url.query)
                    
                    if 'img_url' in query_params:
                        original_url = unquote(query_params['img_url'][0])
                        if original_url.startswith(("http://", "https://")):
                            unique_urls.add(original_url)
            except:
                continue
    except Exception as e:
        print(f"  - Ошибка при извлечении ссылок способом 1: {e}")
    
    # Способ 2: Ищем теги img напрямую
    if len(unique_urls) < 50:  # Если мало ссылок, пробуем другой способ
        try:
            img_tags = driver.find_elements(By.CSS_SELECTOR, "img")
            print(f"  - Найдено {len(img_tags)} тегов img")
            
            for img in img_tags:
                try:
                    src = img.get_attribute("src")
                    if src and src.startswith(("http://", "https://")):
                        # Фильтруем служебные изображения Яндекса
                        if not any(x in src.lower() for x in ['yandex', 'captcha', 'logo', 'sprite', 'pixel']):
                            unique_urls.add(src)
                except:
                    continue
        except Exception as e:
            print(f"  - Ошибка при извлечении ссылок способом 2: {e}")
    
    # Способ 3: Ищем в атрибутах data-src
    if len(unique_urls) < 50:
        try:
            elements = driver.find_elements(By.CSS_SELECTOR, "[data-src]")
            print(f"  - Найдено {len(elements)} элементов с data-src")
            
            for elem in elements:
                try:
                    data_src = elem.get_attribute("data-src")
                    if data_src and data_src.startswith(("http://", "https://")):
                        unique_urls.add(data_src)
                except:
                    continue
        except Exception as e:
            print(f"  - Ошибка при извлечении ссылок способом 3: {e}")
    
    return unique_urls

def scrape_class_images(class_name, query, num_images_needed, num_images_to_fetch):
    """Собирает изображения для одного класса."""
    print(f"\n--- Начинается сбор для класса: {class_name} (поиск: '{query}', целевое кол-во: {num_images_needed}) ---")
    
    # --- Настройка Chrome ---
    driver = setup_driver()
    wait = WebDriverWait(driver, 20)
    # --- /Настройка ---

    search_url = f"https://yandex.ru/images/search?text={query}"
    print(f"  - Открываю URL: {search_url}")
    
    try:
        driver.get(search_url)
    except Exception as e:
        print(f"  - Ошибка при открытии страницы: {e}")
        driver.quit()
        return
    
    # --- ОЖИДАНИЕ ЗАГРУЗКИ СТРАНИЦЫ ---
    if not wait_for_page_load(driver, max_wait=30):
        print(f"  - Ошибка: Страница не загрузилась")
        driver.quit()
        return
    
    # Проверяем, не появилась ли капча
    page_source = driver.page_source.lower()
    if 'captcha' in page_source or 'robot' in page_source:
        print("  - ⚠️  Обнаружена капча или проверка на робота!")
        print("  - Пожалуйста, вручную пройдите проверку в браузере...")
        print("  - У вас есть 30 секунд")
        time.sleep(30)
        wait_for_page_load(driver, max_wait=10)
    
    # --- ПОДГРУЗКА ИЗОБРАЖЕНИЙ ПРОКРУТКОЙ ---
    print(f"  - Подгружаем изображения прокруткой...")
    
    unique_urls = set()
    scroll_attempts = 0
    max_scrolls = 50
    scroll_pause = 2
    
    while scroll_attempts < max_scrolls and len(unique_urls) < num_images_to_fetch:
        # Прокручиваем вниз
        driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
        time.sleep(scroll_pause)
        
        # Извлекаем ссылки
        new_urls = extract_image_urls_from_page(driver)
        unique_urls.update(new_urls)
        
        print(f"  - Собрано {len(unique_urls)} уникальных URL (попытка {scroll_attempts + 1}/{max_scrolls})")
        
        # Если мало новых ссылок, увеличиваем паузу
        if len(new_urls) < 5:
            scroll_pause = min(scroll_pause + 0.5, 5)
        
        scroll_attempts += 1
        
        # Проверяем, достигли ли цели
        if len(unique_urls) >= num_images_to_fetch:
            print(f"  - Достигнуто целевое количество ссылок: {len(unique_urls)}")
            break
    
    driver.quit()
    print(f"  - Сбор ссылок завершен. Всего уникальных URL: {len(unique_urls)}")

    # --- ЗАГРУЗКА ИЗОБРАЖЕНИЙ ---
    if len(unique_urls) == 0:
        print("  - ⚠️  Не найдено ни одного изображения!")
        return
    
    print(f"  - Начинаю загрузку изображений для '{class_name}'...")
    
    success_count = 0
    failed_urls = []
    
    for i, url in enumerate(list(unique_urls)):  # Конвертируем в список для безопасности
        if success_count >= num_images_needed:
            print(f"  - Целевое количество {num_images_needed} достигнуто.")
            break
        
        if i % 10 == 0:
            print(f"  - Прогресс: {success_count}/{num_images_needed} загружено, обработано {i}/{len(unique_urls)} URL")
        
        # Определяем расширение файла
        file_ext = ".jpg"
        lower_url = url.lower()
        if lower_url.endswith('.png'):
            file_ext = ".png"
        elif lower_url.endswith('.jpeg') or 'jpeg' in lower_url:
            file_ext = ".jpeg"
        elif lower_url.endswith('.gif'):
            file_ext = ".gif"
        elif lower_url.endswith('.bmp'):
            file_ext = ".bmp"
        elif lower_url.endswith('.webp'):
            file_ext = ".webp"
        
        filename = f"{success_count:04d}{file_ext}"
        filepath = os.path.join(DATASET_DIR, class_name, filename)

        if download_image(url, filepath):
            success_count += 1
        else:
            failed_urls.append(url)
        
        # Рандомная пауза между загрузками
        time.sleep(random.uniform(0.3, 0.8))

    print(f"\n  - Загрузка для '{class_name}' завершена!")
    print(f"    Успешно: {success_count}")
    print(f"    Не удалось: {len(failed_urls)}")
    
    # --- ПРОВЕРКА ИТОГОВОГО КОЛИЧЕСТВА ---
    if success_count < num_images_needed:
        print(f"  - ⚠️  Предупреждение: Не удалось достичь цели {num_images_needed}.")
        print(f"    Загружено: {success_count}")
        print(f"    Собрано уникальных URL: {len(unique_urls)}")
        
        # Сохраняем неудачные URL для анализа
        if failed_urls:
            failed_file = os.path.join(DATASET_DIR, class_name, "failed_urls.txt")
            with open(failed_file, 'w', encoding='utf-8') as f:
                for url in failed_urls:
                    f.write(url + '\n')
            print(f"    Список неудачных URL сохранен в: {failed_file}")
    else:
        print(f"  - ✅ Цель достигнута! Загружено {success_count} изображений.")


def main():
    """Основная функция для выполнения задачи."""
    print("=" * 60)
    print("ЗАПУСК СКРЕЙПИНГА ИЗОБРАЖЕНИЙ")
    print("=" * 60)
    
    create_directories()

    for class_name, query in SEARCH_QUERIES.items():
        scrape_class_images(class_name, query, IMAGES_NEEDED, IMAGES_TO_FETCH)

    print("\n" + "=" * 60)
    print("ВСЕ ЗАДАЧИ ПО СКРЕЙПИНГУ ЗАВЕРШЕНЫ")
    print("=" * 60)


if __name__ == "__main__":
    main()