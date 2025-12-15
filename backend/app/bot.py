import logging
import os
import re
import telebot
from telebot import TeleBot
from telebot.types import Update, WebAppInfo, Message
from telebot.util import quick_markup

# --- ENV ---
BOT_TOKEN = os.getenv('BOT_TOKEN')
PAYMENT_PROVIDER_TOKEN = os.getenv('PAYMENT_PROVIDER_TOKEN')
WEBHOOK_URL = os.getenv('WEBHOOK_URL')  # полный https URL, если используешь вебхуки
WEBHOOK_PATH = '/bot'
APP_URL = os.getenv('APP_URL')          # твой фронт (Vercel) для WebApp-кнопки
ORDER_CHANNEL_ID = int(os.getenv('ORDER_CHANNEL_ID', '0'))                 # -100... если шлём в канал
ADMIN_CHAT_IDS = [int(x) for x in os.getenv('ADMIN_CHAT_IDS', '').split(',') if x]  # 111,222,...

# --- BOT ---
bot: TeleBot = TeleBot(BOT_TOKEN)

# --- NOTIFICATIONS ---
def notify_admins(text: str) -> None:
    """Шлём уведомление в канал и/или лички админов."""
    if ORDER_CHANNEL_ID:
        try:
            bot.send_message(ORDER_CHANNEL_ID, text, parse_mode='Markdown')
        except Exception as e:
            print('notify_admins(channel) error:', e)
    for uid in ADMIN_CHAT_IDS:
        try:
            bot.send_message(uid, text, parse_mode='Markdown')
        except Exception as e:
            print(f'notify_admins(user {uid}) error:', e)

# --- HANDLERS ---

@bot.pre_checkout_query_handler(func=lambda _: True)
def handle_pre_checkout_query(pre_checkout_query):
    """Одобряем чекаут (в демо не отклоняем товары)."""
    bot.answer_pre_checkout_query(pre_checkout_query_id=pre_checkout_query.id, ok=True)

@bot.message_handler(func=lambda message: re.match(r'/?start', message.text or '', re.IGNORECASE) is not None)
def handle_start_command(message: Message):
    """Welcome + кнопка открытия Mini App."""
    send_actionable_message(
        chat_id=message.chat.id,
        text='*Welcome to MAISON NOIR!*\n\nPress the "open" button to start.'
    )

@bot.message_handler(content_types=['successful_payment'])
def handle_successful_payment(message: Message):
    """Вызвается, когда Telegram подтвердил успешную оплату."""
    sp = message.successful_payment

    # ---- Уведомим админов / канал
    total_rub = sp.total_amount // 100  # копейки -> ₽
    who = f"@{message.from_user.username}" if message.from_user.username else f"id:{message.from_user.id}"
    name = ''
    try:
        if sp.order_info and getattr(sp.order_info, 'name', None):
            name = sp.order_info.name
    except Exception:
        name = ''

    admin_text = (
        '✅ *Новый оплаченный заказ*\n'
        f'Сумма: *{total_rub} ₽*\n'
        f'Покупатель: {who} {name}\n'
        f'Charge ID: `{sp.provider_payment_charge_id}`'
    )
    notify_admins(admin_text)

    # ---- Ответ покупателю (как в шаблоне)
    user_name = name or (message.from_user.first_name or 'customer')
    text = (
        f'Thank you for your order, *{user_name}*! '
        'This is not a real cafe, so your card was not charged.\n\nHave a nice day 🙂'
    )
    bot.send_message(chat_id=message.chat.id, text=text, parse_mode='markdown')

@bot.message_handler()
def handle_all_messages(message: Message):
    """Фолбэк для любых других сообщений."""
    send_actionable_message(
        chat_id=message.chat.id,
        text='I can open the shop for you. Tap the button below.'
    )

# --- HELPERS ---

def send_actionable_message(chat_id: int, text: str):
    """Сообщение с одной WebApp-кнопкой, открывающей Mini App."""
    markup = quick_markup({
        'Explore Menu': {'web_app': WebAppInfo(APP_URL)},
    }, row_width=1)
    bot.send_message(chat_id=chat_id, text=text, parse_mode='markdown', reply_markup=markup)

def refresh_webhook():
    """Снять и поставить вебхук (если используешь вебхуки)."""
    bot.remove_webhook()
    if WEBHOOK_URL:
        bot.set_webhook(
            url=WEBHOOK_URL + WEBHOOK_PATH,
            allowed_updates=['message', 'callback_query', 'pre_checkout_query']
        )
    return True

def process_update(update_json: dict):
    """Пробросить входящий Update в бота (используется вебсервером)."""
    update = Update.de_json(update_json)
    bot.process_new_updates([update])

def create_invoice_link(prices) -> str:
    """Создать ссылку на оплату в RUB. prices — список telebot.types.LabeledPrice."""
    return bot.create_invoice_link(
        title='Order #1',
        description='Отличный выбор! Остались последние шаги ;)',
        payload='orderID',
        provider_token=PAYMENT_PROVIDER_TOKEN,
        currency='RUB',
        prices=prices,
        need_name=True,
        need_phone_number=True,
        need_shipping_address=True
    )

def enable_debug_logging():
    """Включить подробные логи telebot."""
    telebot.logger.setLevel(logging.DEBUG)