/
├── LICENSE.md                # лицензия проекта
├── README.md                 # общее описание, инструкции по запуску
├── backend/                  # сервер Flask и бот
│   ├── app/
│   │   ├── __init__.py       # объявление пакета
│   │   ├── auth.py           # проверка initData от Telegram (HMAC)
│   │   ├── bot.py            # инициализация TeleBot, обработчики, оплата
│   │   └── main.py           # Flask‑приложение, API, webhook
│   ├── data/
│   │   ├── categories.json   # категории меню
│   │   ├── info.json         # информация о кафе
│   │   └── menu/             # блюда по категориям (несколько *.json)
│   └── requirements.txt      # зависимости: Flask, Flask-Cors, pyTelegramBotAPI...
├── frontend/                 # статический фронтенд для Telegram Mini App
│   ├── index.html            # единственная HTML‑страница приложения
│   ├── css/
│   │   └── index.css         # стили
│   ├── icons/                # SVG‑иконки
│   ├── js/
│   │   ├── index.js          # точка входа SPA
│   │   ├── cart/cart.js      # модель и методы корзины
│   │   ├── jquery/extensions.js # расширения jQuery
│   │   ├── pages/            # логика отдельных страниц (main, category, details, cart)
│   │   ├── requests/requests.js # функции GET/POST к backend
│   │   ├── routing/route.js  # базовый класс маршрута
│   │   ├── routing/router.js # клиентский роутер и snackbar
│   │   ├── telegram/telegram.js # обёртка Telegram.WebApp API
│   │   └── utils/            # утилиты (DOM, currency, snackbar и др.)
│   ├── lottie/               # анимации Lottie
│   └── pages/                # HTML-фрагменты для SPA
└── screenshots/
    └── laurel-cafe-mini-app.png  # пример внешнего вида

### Ключевые моменты и точки расширения

- **Фронтенд**: каталог `frontend/` содержит статические файлы SPA (HTML/CSS/JS). Основная страница `index.html`, «псевдо-страницы» хранятся в `frontend/pages/`.
- **Фласк-приложение**: в `backend/app/main.py` настраивается Flask, задаются маршруты (`/info`, `/categories`, `/menu/<id>`, `/order` и др.) и вызывается `bot.refresh_webhook()` для Telegram webhook.
- **Логика бота и оплаты**: файл `backend/app/bot.py` инициализирует TeleBot, обрабатывает webhook и успешную оплату (`handle_successful_payment`, `handle_pre_checkout_query`). Метод `create_invoice_link` формирует ссылку на оплату с использованием `PAYMENT_PROVIDER_TOKEN`. В `main.py` маршрут `/order` преобразует содержимое корзины в `LabeledPrice` и вызывает `bot.create_invoice_link`.
- **Корзина**: клиентская логика корзины реализована в `frontend/js/cart/cart.js` и связана со страницами `pages/cart.js`, `pages/details.js` и `pages/main.js`. Состояние корзины хранится в `localStorage`.
- **Возможные доработки**:
  - Отключение/изменение оплаты можно сделать в `backend/app/bot.py` (метод `create_invoice_link`, обработчики `handle_pre_checkout_query`, `handle_successful_payment`) и в `/order` (создание `invoice_url`).
  - Добавление логики сервера (например, хранение заказов, админ-панель) — в `backend/app/main.py` можно создавать новые Flask-маршруты или вынести их в отдельный модуль.
  - Расширить функциональность корзины или хранение заказов можно через методы в `frontend/js/cart/` и соответствующие API в backend.
