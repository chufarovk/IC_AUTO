import httpx
import os
from dotenv import load_dotenv
import asyncio
import json

# Загружаем переменные из .env файла в корне проекта
dotenv_path = os.path.join(os.path.dirname(__file__), '..', '.env')
load_dotenv(dotenv_path=dotenv_path)

# --- Настройки из .env ---
API_URL = os.getenv("API_1C_URL")
API_USER = os.getenv("API_1C_USER")
API_PASSWORD = os.getenv("API_1C_PASSWORD")

# --- Тестовый скрипт ---

async def test_connection():
    """
    Пытается подключиться к API 1С, явно запрашивая JSON.
    """
    print("--- Запуск теста подключения к API 1С (v3 - JSON) ---")

    if not all([API_URL, API_USER, API_PASSWORD]):
        print("\n❌ ОШИБКА: Не все переменные (API_1C_URL, API_1C_USER, API_1C_PASSWORD) заданы в .env файле.")
        return

    print(f"Целевой URL: {API_URL}")
    print(f"Пользователь: {API_USER}")

    base_url = API_URL.rstrip('/')
    auth = httpx.BasicAuth(username=API_USER, password=API_PASSWORD)
    
    # --- КЛЮЧЕВОЕ ИЗМЕНЕНИЕ: Добавляем параметр $format=json ---
    params = {
        "$format": "json"
    }
    
    try:
        async with httpx.AsyncClient(auth=auth, verify=False) as client:
            print(f"\nОтправка GET-запроса на: {base_url}")
            print(f"С параметром: {params}")
            
            response = await client.get(base_url, params=params, timeout=15.0)
            
            print(f"\nСтатус ответа: {response.status_code}")
            
            print("\n--- ЗАГОЛОВКИ ОТВЕТА ---")
            for key, value in response.headers.items():
                print(f"{key}: {value}")
            
            print("\n--- ТЕЛО ОТВЕТА (СЫРОЙ ТЕКСТ) ---")
            print(response.text)
            print("--- КОНЕЦ ТЕЛА ОТВЕТА ---\n")
            
            response.raise_for_status()
            
            # Попытка разобрать JSON
            try:
                data = response.json()
                print("✅ УСПЕХ! Ответ сервера - валидный JSON.")
                collections = [item.get('name') for item in data.get('value', [])]
                
                if collections:
                    print("\nСервер вернул список коллекций:")
                    for collection in collections[:10]:
                        print(f"- {collection}")
                else:
                    print("JSON получен, но список коллекций пуст. Это нормально.")

            except json.JSONDecodeError:
                print("❌ КРИТИЧЕСКАЯ ОШИБКА: Сервер все равно не вернул JSON, даже после запроса.")

    except httpx.HTTPStatusError as e:
        print(f"\n❌ ОШИБКА: Сервер вернул ошибку состояния {e.response.status_code}.")
        if e.response.status_code == 401:
            print("Причина: Неверный логин или пароль для API.")
            
    except httpx.RequestError as e:
        print(f"\n❌ ОШИБКА: Не удалось выполнить запрос. Проблема с сетью или URL.")
        print(f"Детали ошибки: {e}")
        
    except Exception as e:
        print(f"\n❌ ОШИБКА: Произошла непредвиденная ошибка.")
        print(f"Детали: {e}")

    print("\n--- Тест завершен ---")


if __name__ == "__main__":
    asyncio.run(test_connection())
