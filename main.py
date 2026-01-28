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

# --- Настройки ---
# Укажите путь к вашему chromedriver.exe
CHROMEDRIVER_PATH = "/path/to/chromedriver" # <<< ЗАМЕНИТЕ НА ВАШ ПУТЬ >>>

SEARCH_QUERIES = {"polar_bear": "polar bear", "brown_bear": "brown bear"}
IMAGES_NEEDED = 1000
IMAGES_TO_FETCH = int(IMAGES_NEEDED * 1.1) # Собираем с запасом
DATASET_DIR = "dataset"

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
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
        response = requests.get(url, headers=HEADERS, timeout=10)
        response.raise_for_status()

        # Попробовать открыть как изображение
        image_array = np.asarray(bytearray(response.content), dtype=np.uint8)
        image_np = cv2.imdecode(image_array, cv2.IMREAD_COLOR)
        if image_np is None:
             print(f"  - Скачанный файл не является изображением или поврежден: {url}")
             return False

        # Сохранить
        cv2.imwrite(save_path, image_np)
        print(f"  - Сохранено: {save_path}")
        return True
    except Exception as e:
        print(f"  - Ошибка при загрузке {url}: {e}")
        return False

def scrape_class_images(class_name, query, num_images_needed, num_images_to_fetch):
    """Собирает изображения для одного класса."""
    print(f"\n--- Начинается сбор для класса: {class_name} (поиск: '{query}', целевое кол-во: {num_images_needed}) ---")
    
    # --- Настройка Chrome ---
    chrome_options = Options()
    # chrome_options.add_argument("--headless") # Раскомментируйте для запуска без GUI
    service = Service(CHROMEDRIVER_PATH)
    driver = webdriver.Chrome(service=service, options=chrome_options)
    wait = WebDriverWait(driver, 10)
    # --- /Настройка ---

    search_url = f"https://yandex.ru/images/search?text={query}"
    driver.get(search_url)

    # Ждем загрузки страницы поиска
    try:
        wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, ".serp-item__link")))
    except TimeoutException:
        print(f"  - Ошибка: Не удалось дождаться загрузки результатов поиска для '{query}'")
        driver.quit()
        return

    # Прокручиваем страницу, чтобы подгрузить больше изображений
    print(f"  - Подгружаем изображения...")
    last_height = driver.execute_script("return document.body.scrollHeight")
    while True:
        driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
        time.sleep(2) # Ждать подгрузки

        new_height = driver.execute_script("return document.body.scrollHeight")
        if new_height == last_height:
            print("  - Достигнут конец страницы или прокрутка не далее результатов.")
            break
        last_height = new_height

    # Находим элементы миниатюр
    img_elements = driver.find_elements(By.CSS_SELECTOR, ".serp-item__link")
    print(f"  - Найдено {len(img_elements)} миниатюр. Начинаю сбор ссылок на оригиналы...")

    unique_urls = set()
    for i, elem in enumerate(img_elements):
        if len(unique_urls) >= num_images_to_fetch:
            print(f"  - Собрано {num_images_to_fetch} потенциальных ссылок.")
            break
        
        try:
            # Прокручиваем элемент в видимую область перед кликом
            driver.execute_script("arguments[0].scrollIntoView();", elem)
            time.sleep(0.1) # Небольшая пауза после прокрутки

            # Кликнуть на миниатюру
            elem.click()
            
            # Ждать открытия панели с деталями
            detail_view_img = wait.until(
                EC.presence_of_element_located((By.CSS_SELECTOR, ".MMImage-Origin"))
            )
            
            # Получить ссылку на оригинальное изображение
            original_url = detail_view_img.get_attribute("src")
            
            if original_url and original_url.startswith(("http://", "https://")):
                unique_urls.add(original_url)
                print(f"    - Найдена ссылка ({len(unique_urls)}): {original_url.split('/')[-1][:30]}...")
            
            # Закрыть панель (Esc)
            driver.find_element(By.TAG_NAME, 'body').send_keys(u'\ue00c')
            time.sleep(0.2) # Пауза после закрытия
            
        except (TimeoutException, NoSuchElementException, StaleElementReferenceException) as e:
            # Если элемент недоступен или панель не открылась, просто пропускаем
            # print(f"  - Пропуск миниатюры {i+1}, ошибка: {e}")
            continue
        except Exception as e:
            print(f"  - Неожиданная ошибка при обработке миниатюры {i+1}: {e}")
            continue

    driver.quit()
    print(f"  - Сбор ссылок для '{class_name}' завершен. Найдено уникальных URL: {len(unique_urls)}")

    # --- Загрузка изображений ---
    print(f"  - Начинаю загрузку изображений для '{class_name}'...")
    downloaded_paths = []
    success_count = 0
    
    for i, url in enumerate(unique_urls):
        if success_count >= num_images_needed:
            print(f"  - Целевое количество {num_images_needed} достигнуто.")
            break

        filename = f"{success_count:04d}.jpg" # 0000.jpg, 0001.jpg, ...
        filepath = os.path.join(DATASET_DIR, class_name, filename)

        if download_image(url, filepath):
            downloaded_paths.append(filepath)
            success_count += 1
        # else:
        #     print(f"  - Пропущено изображение {i+1} из-за ошибки загрузки.")
        
        # Пауза между загрузками
        time.sleep(0.5)

    print(f"  - Загрузка для '{class_name}' завершена. Успешно загружено: {success_count}")

    # --- Проверка итогового количества ---
    if success_count < num_images_needed:
         print(f"  - Предупреждение: Не удалось достичь цели {num_images_needed}. Загружено только {success_count} изображений.")


def main():
    """Основная функция для выполнения задачи."""
    create_directories()

    for class_name, query in SEARCH_QUERIES.items():
        scrape_class_images(class_name, query, IMAGES_NEEDED, IMAGES_TO_FETCH)

    print("\n--- Все задачи по скрейпингу завершены ---")

if __name__ == "__main__":
    main()