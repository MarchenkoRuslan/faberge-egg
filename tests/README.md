# Тесты для бекенда маркетплейса

## Установка зависимостей

```bash
pip install -r requirements.txt
```

## Запуск тестов

### Все тесты
```bash
pytest
```

### С подробным выводом
```bash
pytest -v
```

### С покрытием кода
```bash
pytest --cov=app --cov-report=html
```

После выполнения команды откройте `htmlcov/index.html` в браузере для просмотра отчета о покрытии.

### Конкретный файл тестов
```bash
pytest tests/test_auth.py
```

### Конкретный тест
```bash
pytest tests/test_auth.py::test_register_success
```

### Только быстрые тесты (без интеграционных)
```bash
pytest -k "not integration"
```

## Структура тестов

- `test_auth.py` - Тесты авторизации (регистрация, логин, JWT)
- `test_lots.py` - Тесты лотов (список, получение по ID)
- `test_orders.py` - Тесты заказов (создание, список, статус)
- `test_webhooks.py` - Тесты webhooks (Stripe, PayKilla)
- `test_services.py` - Тесты сервисов (Stripe, PayKilla с моками)
- `test_dependencies.py` - Тесты зависимостей (авторизация)
- `test_integration.py` - Интеграционные тесты (полный flow)

## Фикстуры

- `client` - FastAPI TestClient
- `db` - Тестовая БД (in-memory SQLite)
- `test_user` - Тестовый пользователь
- `test_user2` - Второй тестовый пользователь
- `test_lot` - Тестовый лот
- `test_lot_inactive` - Неактивный тестовый лот
- `auth_token` - JWT токен для тестового пользователя
- `auth_headers` - Заголовки с авторизацией

## Примечания

- Все тесты используют изолированную тестовую БД (in-memory SQLite)
- Внешние сервисы (Stripe, PayKilla) мокируются
- Каждый тест выполняется в отдельной транзакции БД
