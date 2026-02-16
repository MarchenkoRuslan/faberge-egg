# Marketplace Backend (Python / FastAPI)

REST API для маркетплейса фракционных лотов: авторизация (JWT), лоты, заказы, Stripe и PayKilla.

## Запуск

```bash
cd backend
python -m venv venv
# Windows: venv\Scripts\activate
# Unix: source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
# Отредактировать .env (JWT_SECRET, STRIPE_*, PAYKILLA_*)
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

- API: http://localhost:8000  
- Swagger UI: http://localhost:8000/docs  
- ReDoc: http://localhost:8000/redoc  

## Эндпоинты

- **Auth:** `POST /api/auth/register`, `POST /api/auth/login` (получить JWT).
- **Lots:** `GET /api/lots`, `GET /api/lots/{id}` (публичные).
- **Orders:** `POST /api/orders`, `GET /api/orders/me`, `GET /api/orders/{id}/status` (нужен заголовок `Authorization: Bearer <token>`).
- **Webhooks:** `POST /webhooks/stripe`, `POST /webhooks/paykilla`.

В Swagger используйте кнопку **Authorize** и вставьте токен из ответа `/api/auth/login`.
