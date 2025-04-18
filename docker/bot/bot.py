"""
Телеграм-бот для обновления расписания богослужений и рассылки уведомлений подписчикам.
Расширенная версия с поддержкой базы данных подписчиков, автоматическими обновлениями и интерактивным интерфейсом.
"""
import os
import logging
import tempfile
from pathlib import Path
import re
import shutil
import git
import json
import subprocess
import asyncio
import threading
import time
from datetime import datetime, timedelta
from typing import Dict, List, Tuple, Optional, Any
from dotenv import load_dotenv
from ssh_utils import update_hosting, test_ssh_connection
from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton, ReplyKeyboardMarkup, ReplyKeyboardRemove
from telegram.ext import Application, CommandHandler, MessageHandler, filters, CallbackQueryHandler, ContextTypes, ConversationHandler


# Импортируем функции из текстового конвертера
from img_text_converter import (
    extract_text_from_txt, 
    extract_text_from_docx, 
    process_text, 
    create_schedule_html, 
    update_index_html,
    recognize_text_from_image
)

# Импортируем класс для работы с базой данных подписчиков
from db import SubscriberDatabase

# Загружаем переменные окружения из .env файла
load_dotenv()

# Настройка логирования
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", 
    level=logging.INFO,
    handlers=[
        logging.FileHandler("bot.log", encoding="utf-8"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# Константы
ADMIN_USER_ID = os.environ.get("ADMIN_USER_ID")  # ID администратора в Telegram
REPO_URL = os.environ.get("REPO_URL")  # URL репозитория на GitHub
REPO_PATH = os.path.join(tempfile.gettempdir(), "church_repo")  # Временный путь для клонирования репозитория
GIT_USERNAME = os.environ.get("GIT_USERNAME")  # Имя пользователя GitHub
GIT_EMAIL = os.environ.get("GIT_EMAIL")  # Email на GitHub
GIT_TOKEN = os.environ.get("GIT_TOKEN")  # Персональный токен доступа GitHub
PROJECT_PATH = os.environ.get("PROJECT_PATH", "/app/project")  # Путь к проекту
INDEX_HTML_PATH = os.environ.get("INDEX_HTML_PATH", "/app/project/index.html")  # Путь к index.html
DATABASE_PATH = os.environ.get("DATABASE_PATH", "/app/data/subscribers.db")  # Путь к базе данных

# Константы для подключения к хостингу
HOSTING_PATH = os.environ.get("HOSTING_PATH", "")  # Хост для подключения (user@hostname)
HOSTING_CERT = os.environ.get("HOSTING_CERT", "")  # Путь к приватному ключу SSH
HOSTING_PASSPHRASE = os.environ.get("HOSTING_PASSPHRASE", "")  # Парольная фраза для ключа
HOSTING_DIR = os.environ.get("HOSTING_DIR", "/home/prihodpf/public_html")  # Директория на хостинге

# Состояния для ConversationHandler
SCHEDULE_TIME, CONFIRM_REBOOT, COMPOSE_MESSAGE, CONFIRM_BROADCAST = range(4)

# Создаем временные папки
IMAGES_FOLDER = os.path.join(tempfile.gettempdir(), "church_bot_images")
TEXT_FOLDER = os.path.join(tempfile.gettempdir(), "church_bot_text")
Path(IMAGES_FOLDER).mkdir(exist_ok=True)
Path(TEXT_FOLDER).mkdir(exist_ok=True)

# Инициализируем базу данных подписчиков
subscriber_db = SubscriberDatabase(DATABASE_PATH)

# Время запуска бота
BOT_START_TIME = datetime.now()

# Статистика использования
USAGE_STATS = {
    "last_file_upload": None,
    "last_file_processing": None,
    "last_repo_push": None,
    "unauthorized_access_count": 0,
    "scheduled_updates": []
}

# Переменные для хранения текста
class TextProcessor:
    def __init__(self):
        self.current_text = None
        self.edited_text = None
        self.reset()
    
    def reset(self):
        """Сбросить все переменные"""
        self.current_text = None
        self.edited_text = None
        
    def set_current(self, text):
        """Установить текущий текст"""
        self.current_text = text
        
    def set_edited(self, text):
        """Установить отредактированный текст"""
        self.edited_text = text
        
    def get_final_text(self):
        """Получить финальный текст (отредактированный, если есть, иначе текущий)"""
        return self.edited_text if self.edited_text else self.current_text

# Создаем глобальный экземпляр обработчика текста
text_processor = TextProcessor()

# Функция для сохранения запланированных задач
def save_scheduled_tasks():
    """Сохранить запланированные задачи в файл"""
    try:
        with open(os.path.join(os.path.dirname(DATABASE_PATH), 'scheduled_tasks.json'), 'w', encoding='utf-8') as f:
            json.dump(USAGE_STATS["scheduled_updates"], f, ensure_ascii=False, default=str)
        logger.info("Запланированные задачи сохранены")
    except Exception as e:
        logger.error(f"Ошибка при сохранении запланированных задач: {str(e)}")

# Функция для загрузки запланированных задач
def load_scheduled_tasks():
    """Загрузить запланированные задачи из файла"""
    try:
        tasks_path = os.path.join(os.path.dirname(DATABASE_PATH), 'scheduled_tasks.json')
        if os.path.exists(tasks_path):
            with open(tasks_path, 'r', encoding='utf-8') as f:
                USAGE_STATS["scheduled_updates"] = json.load(f)
            logger.info("Запланированные задачи загружены")
    except Exception as e:
        logger.error(f"Ошибка при загрузке запланированных задач: {str(e)}")

# Функция для планирования задач
async def schedule_task(context, chat_id, task_time, task_function, description):
    """Планирование задачи на определенное время"""
    try:
        now = datetime.now()
        task_dt = datetime.strptime(task_time, "%Y-%m-%d %H:%M")
        
        # Если время уже прошло, отменяем планирование
        if task_dt <= now:
            await context.bot.send_message(
                chat_id=chat_id,
                text="⚠️ Указанное время уже прошло. Пожалуйста, укажите будущую дату и время."
            )
            return False
            
        # Вычисляем задержку в секундах
        delay = (task_dt - now).total_seconds()
        
        # Создаем задачу
        job = context.job_queue.run_once(
            task_function,
            delay,
            data={'chat_id': chat_id, 'description': description}
        )
        
        # Добавляем в список задач
        task_info = {
            'job_id': job.job_id,
            'time': task_time,
            'description': description,
            'created_at': now.strftime("%Y-%m-%d %H:%M:%S")
        }
        USAGE_STATS["scheduled_updates"].append(task_info)
        save_scheduled_tasks()
        
        await context.bot.send_message(
            chat_id=chat_id,
            text=f"✅ Запланировано задание: {description}\nВремя выполнения: {task_time}"
        )
        return True
    except Exception as e:
        logger.error(f"Ошибка при планировании задачи: {str(e)}")
        await context.bot.send_message(
            chat_id=chat_id,
            text=f"❌ Ошибка при планировании задачи: {str(e)}"
        )
        return False

# Задача обновления из репозитория
async def scheduled_pull_task(context):
    """Задача для запланированного обновления с репозитория"""
    job = context.job
    chat_id = job.data['chat_id']
    description = job.data['description']
    
    try:
        await context.bot.send_message(chat_id=chat_id, text=f"⏳ Выполняется запланированное задание: {description}")
        success, result = await pull_from_github_to_hosting(context)
        
        if success:
            await context.bot.send_message(chat_id=chat_id, text=f"✅ Запланированное задание выполнено успешно: {description}")
        else:
            await context.bot.send_message(chat_id=chat_id, text=f"❌ Ошибка при выполнении запланированного задания: {description}\n\nДетали: {result}")
    except Exception as e:
        logger.error(f"Ошибка в запланированной задаче: {str(e)}")
        await context.bot.send_message(chat_id=chat_id, text=f"❌ Ошибка в запланированной задаче: {str(e)}")

# Функция для получения времени работы
def get_uptime():
    """Получить время работы бота в формате дни, часы, минуты"""
    uptime = datetime.now() - BOT_START_TIME
    days = uptime.days
    hours, remainder = divmod(uptime.seconds, 3600)
    minutes, _ = divmod(remainder, 60)
    return f"{days}д {hours}ч {minutes}м"

# Функция для выполнения команды на сервере
async def execute_command(command, shell=True):
    """Выполнить команду на сервере и вернуть результат"""
    try:
        process = await asyncio.create_subprocess_shell(
            command,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            shell=shell
        )
        stdout, stderr = await process.communicate()
        
        if process.returncode != 0:
            logger.error(f"Ошибка выполнения команды: {stderr.decode('utf-8')}")
            return False, stderr.decode('utf-8')
            
        logger.info(f"Команда выполнена успешно: {stdout.decode('utf-8')}")
        return True, stdout.decode('utf-8')
    except Exception as e:
        logger.error(f"Ошибка при выполнении команды {command}: {str(e)}")
        return False, str(e)

# Функция для перезагрузки контейнера
async def reboot_container():
    """Перезагрузить Docker контейнер"""
    try:
        # Записываем в лог информацию о перезагрузке
        logger.info("Начинаем перезагрузку контейнера...")
        
        # Запускаем скрипт в отдельном потоке, чтобы не блокировать бота
        def delayed_reboot():
            # Даем боту время отправить сообщение перед перезагрузкой
            time.sleep(3)
            try:
                os.system("docker-compose restart church-bot")
            except Exception as e:
                logger.error(f"Ошибка при выполнении команды перезагрузки: {str(e)}")
            
        threading.Thread(target=delayed_reboot).start()
        return True
    except Exception as e:
        logger.error(f"Ошибка при перезагрузке контейнера: {str(e)}")
        return False

# Функция для загрузки файла index.html из репозитория
async def pull_from_github():
    """Загрузить файл index.html из репозитория GitHub"""
    try:
        # Удаляем локальный репозиторий, если он существует
        if os.path.exists(REPO_PATH):
            shutil.rmtree(REPO_PATH)
            
        # Клонируем репозиторий
        repo_url_with_token = REPO_URL.replace('https://', f'https://{GIT_TOKEN}@')
        
        # Клонируем репозиторий
        repo = git.Repo.clone_from(repo_url_with_token, REPO_PATH)
        
        # Путь к файлу index.html в репозитории
        index_path = os.path.join(REPO_PATH, "index.html")
        
        # Копируем файл из репозитория в рабочую директорию
        if os.path.exists(index_path):
            shutil.copy2(index_path, INDEX_HTML_PATH)
            logger.info(f"Файл index.html успешно загружен из репозитория")
            return True, "Файл index.html успешно загружен из репозитория"
        else:
            logger.error(f"Файл index.html не найден в репозитории")
            return False, "Файл index.html не найден в репозитории"
    except Exception as e:
        logger.error(f"Ошибка при загрузке файла из репозитория: {str(e)}")
        return False, str(e)

# Функция для обновления хостинга из репозитория
async def pull_from_github_to_hosting(context=None):
    """Обновить файлы на хостинге из репозитория GitHub"""
    try:
        if not HOSTING_PATH or not HOSTING_CERT:
            return False, "Не настроены параметры хостинга (HOSTING_PATH и HOSTING_CERT)"
            
        # Формируем команду для обновления файлов на хостинге
        command = f"ssh -i {HOSTING_CERT} {HOSTING_PATH} 'cd /var/www/html && git pull'"
        
        # Выполняем команду
        success, output = await execute_command(command)
        
        if success:
            USAGE_STATS["last_repo_push"] = datetime.now().strftime("%d.%m.%Y %H:%M")
            return True, output
        else:
            return False, output
    except Exception as e:
        logger.error(f"Ошибка при обновлении хостинга: {str(e)}")
        return False, str(e)

# Функция для отката изменений в репозитории
async def rollback_last_commit():
    """Откатить последний коммит в репозитории"""
    try:
        # Удаляем локальный репозиторий, если он существует
        if os.path.exists(REPO_PATH):
            shutil.rmtree(REPO_PATH)
            
        # Клонируем репозиторий
        repo_url_with_token = REPO_URL.replace('https://', f'https://{GIT_TOKEN}@')
        
        # Клонируем репозиторий
        repo = git.Repo.clone_from(repo_url_with_token, REPO_PATH)
        
        # Настраиваем имя пользователя и email для коммитов
        repo.config_writer().set_value("user", "name", GIT_USERNAME).release()
        repo.config_writer().set_value("user", "email", GIT_EMAIL).release()
        
        # Отменяем последний коммит и пушим изменения
        repo.git.reset('--hard', 'HEAD~1')
        repo.git.push('--force')
        
        # Обновляем хостинг
        await pull_from_github_to_hosting()
        
        logger.info("Последний коммит успешно отменен")
        return True, "Последний коммит успешно отменен и изменения отправлены на хостинг"
    except Exception as e:
        logger.error(f"Ошибка при откате последнего коммита: {str(e)}")
        return False, str(e)

#
# Обработчики команд
#

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Обработчик команды /start"""
    user_id = update.effective_user.id
    user = update.effective_user
    
    if str(user_id) == ADMIN_USER_ID:
        # Создаем клавиатуру с кнопками для администратора
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("🔄 Обновить расписание", callback_data="update_schedule")],
            [InlineKeyboardButton("⬇️ Загрузить из GitHub", callback_data="pull_github")],
            [InlineKeyboardButton("🔃 Обновить хостинг", callback_data="update_hosting")],
            [InlineKeyboardButton("⏰ Запланировать обновление", callback_data="schedule_update")],
            [InlineKeyboardButton("↩️ Откатить изменения", callback_data="rollback")],
            [InlineKeyboardButton("🔄 Перезагрузить бота", callback_data="reboot")],
            [InlineKeyboardButton("📊 Статус бота", callback_data="status")],
            [InlineKeyboardButton("📨 Рассылка подписчикам", callback_data="broadcast")]
        ])
        
        await update.message.reply_text(
            f"Привет, {update.effective_user.first_name}! 👋\n\n"
            "Я бот для обновления расписания богослужений на сайте прихода.\n\n"
            "Выберите действие:",
            reply_markup=keyboard
        )
    else:
        # Проверяем, подписан ли пользователь
        subscriber_exists = False
        try:
            # Добавляем пользователя, если он ещё не в базе
            subscriber_db.add_subscriber(
                user_id, 
                user.username or "", 
                f"{user.first_name} {user.last_name or ''}".strip()
            )
            subscriber_exists = True
        except Exception as e:
            logger.error(f"Ошибка при работе с базой данных подписчиков: {str(e)}")
        
        # Для обычных пользователей предлагаем подписку на обновления
        USAGE_STATS["unauthorized_access_count"] += 1
        
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("✅ Подписаться на обновления", callback_data="subscribe")],
            [InlineKeyboardButton("❌ Отписаться от обновлений", callback_data="unsubscribe")]
        ])
        
        subscription_status = "Вы уже подписаны на обновления расписания." if subscriber_exists else ""
        
        await update.message.reply_text(
            f"Здравствуйте, {update.effective_user.first_name}! 👋\n\n"
            "Это бот для отправки обновлений расписания богослужений.\n\n"
            f"{subscription_status}\n"
            "Вы можете подписаться на уведомления об изменениях в расписании:",
            reply_markup=keyboard
        )

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Обработчик команды /help"""
    user_id = update.effective_user.id
    
    if str(user_id) == ADMIN_USER_ID:
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("🏠 Главное меню", callback_data="main_menu")]
        ])
        
        await update.message.reply_text(
            "📖 Справка по командам бота:\n\n"
            "1️⃣ <b>Основные команды:</b>\n"
            "/start - Главное меню бота\n"
            "/help - Эта справка\n"
            "/status - Проверка состояния бота\n"
            "/cancel - Отменить текущую операцию\n\n"
            
            "2️⃣ <b>Управление расписанием:</b>\n"
            "/upload - Загрузить новое расписание\n"
            "/pull - Загрузить файл index.html из GitHub\n"
            "/push_hosting - Обновить хостинг из GitHub\n"
            "/rollback - Откатить последние изменения\n\n"
            
            "3️⃣ <b>Управление системой:</b>\n"
            "/reboot - Перезагрузить бота\n"
            "/schedule - Запланировать обновление\n"
            "/logs - Отправить файл логов\n\n"
            
            "4️⃣ <b>Подписчики:</b>\n"
            "/subscribers - Список подписчиков\n"
            "/broadcast - Отправить сообщение подписчикам\n\n"
            
            "Для загрузки расписания просто отправьте боту файл DOCX/TXT или фотографию с расписанием.",
            reply_markup=keyboard,
            parse_mode="HTML"
        )
    else:
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("✅ Подписаться на обновления", callback_data="subscribe")],
            [InlineKeyboardButton("❌ Отписаться от обновлений", callback_data="unsubscribe")]
        ])
        
        await update.message.reply_text(
            "📖 Справка по использованию бота:\n\n"
            "/start - Начать работу с ботом\n"
            "/subscribe - Подписаться на обновления расписания\n"
            "/unsubscribe - Отписаться от обновлений\n\n"
            "Этот бот автоматически отправит вам обновленное расписание богослужений, когда оно будет доступно.",
            reply_markup=keyboard
        )

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Обработчик команды /cancel"""
    user_id = update.effective_user.id
    
    if str(user_id) != ADMIN_USER_ID:
        return
        
    # Очищаем текущее состояние
    text_processor.reset()
    
    # Очищаем временные файлы
    try:
        for file in os.listdir(IMAGES_FOLDER):
            os.remove(os.path.join(IMAGES_FOLDER, file))
        for file in os.listdir(TEXT_FOLDER):
            os.remove(os.path.join(TEXT_FOLDER, file))
            
        # Проверяем, есть ли активный ConversationHandler
        if context.user_data.get('conversation_active'):
            context.user_data['conversation_active'] = False
            await update.message.reply_text("✅ Операция отменена.")
            return ConversationHandler.END
            
        await update.message.reply_text("✅ Операция отменена. Все временные файлы удалены.")
    except Exception as e:
        logger.error(f"Ошибка при очистке временных файлов: {str(e)}")
        await update.message.reply_text(f"❌ Ошибка при очистке временных файлов: {str(e)}")
    
    return ConversationHandler.END

async def status_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Обработчик команды /status - проверка состояния бота"""
    user_id = update.effective_user.id
    
    if str(user_id) != ADMIN_USER_ID:
        return
    
    status_message = "📊 Статус бота:\n\n"
    
    # Проверка доступа к index.html
    index_exists = os.path.exists(INDEX_HTML_PATH)
    status_message += f"📄 Файл index.html: {'✅ Доступен' if index_exists else '❌ Недоступен'}\n"
    
    # Проверка временных папок
    images_count = len(os.listdir(IMAGES_FOLDER)) if os.path.exists(IMAGES_FOLDER) else 0
    text_count = len(os.listdir(TEXT_FOLDER)) if os.path.exists(TEXT_FOLDER) else 0
    status_message += f"🖼️ Файлов во временной папке изображений: {images_count}\n"
    status_message += f"📝 Файлов во временной папке текстов: {text_count}\n"
    
    # Проверка состояния текста
    has_current = text_processor.current_text is not None
    has_edited = text_processor.edited_text is not None
    status_message += f"📋 Текущий текст: {'✅ Есть' if has_current else '❌ Нет'}\n"
    status_message += f"✏️ Отредактированный текст: {'✅ Есть' if has_edited else '❌ Нет'}\n"
    
    # Добавляем статистику использования
    status_message += f"⏱️ Время работы сервера: {get_uptime()}\n"
    
    if USAGE_STATS["last_file_upload"]:
        status_message += f"📅 Последняя загрузка файлов с расписанием: {USAGE_STATS['last_file_upload']}\n"
        
    if USAGE_STATS["last_file_processing"]:
        status_message += f"📅 Последняя обработка файлов с расписанием: {USAGE_STATS['last_file_processing']}\n"
        
    if USAGE_STATS["last_repo_push"]:
        status_message += f"🔄 Последний пуш в репозиторий: {USAGE_STATS['last_repo_push']}\n"
        
    status_message += f"🚫 Отказы в авторизации другим пользователям телеграм: {USAGE_STATS['unauthorized_access_count']}\n"
    
    # Проверка базы данных подписчиков
    try:
        subscriber_count = subscriber_db.get_subscriber_count()
        db_size = subscriber_db.get_database_size()
        status_message += f"👥 Количество подписчиков на обновления: {subscriber_count}\n"
        status_message += f"💾 Размер базы данных: {db_size.get('size_mb', 0)} МБ\n"
    except Exception as e:
        logger.error(f"Ошибка при получении информации о базе данных: {str(e)}")
        status_message += f"❌ Ошибка при получении информации о базе данных: {str(e)}\n"
    
    # Запланированные задачи
    if USAGE_STATS["scheduled_updates"]:
        status_message += "\n📆 Запланированные обновления:\n"
        for idx, task in enumerate(USAGE_STATS["scheduled_updates"], 1):
            status_message += f"{idx}. {task['description']} - {task['time']}\n"
    
    # Добавляем кнопки для действий
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("🏠 Главное меню", callback_data="main_menu")],
        [InlineKeyboardButton("📁 Отправить логи", callback_data="send_logs")]
    ])
    
    await update.message.reply_text(status_message, reply_markup=keyboard)

async def reboot_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Обработчик команды /reboot - перезагрузка бота"""
    user_id = update.effective_user.id
    
    if str(user_id) != ADMIN_USER_ID:
        return ConversationHandler.END
    
    keyboard = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("✅ Да, перезагрузить", callback_data="confirm_reboot"),
            InlineKeyboardButton("❌ Отмена", callback_data="cancel_reboot")
        ]
    ])
    
    await update.message.reply_text(
        "⚠️ Вы уверены, что хотите перезагрузить бота?\n\n"
        "Это приведет к временной недоступности бота на несколько секунд.",
        reply_markup=keyboard
    )
    
    context.user_data['conversation_active'] = True
    return CONFIRM_REBOOT

async def confirm_reboot(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Подтверждение перезагрузки бота"""
    query = update.callback_query
    await query.answer()
    
    if query.data == "confirm_reboot":
        await query.edit_message_text("🔄 Начинаю перезагрузку бота. Бот будет недоступен несколько секунд...")
        
        success = await reboot_container()
        
        if success:
            # Это сообщение не успеет отправиться, так как бот перезапустится
            await query.message.reply_text("✅ Бот успешно перезагружается...")
        else:
            await query.message.reply_text("❌ Ошибка при перезагрузке бота.")
    else:
        await query.edit_message_text("❌ Перезагрузка отменена.")
    
    context.user_data['conversation_active'] = False
    return ConversationHandler.END

async def pull_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Обработчик команды /pull - загрузка файла index.html из репозитория"""
    user_id = update.effective_user.id
    
    if str(user_id) != ADMIN_USER_ID:
        return
    
    message = await update.message.reply_text("⏳ Загружаю файл index.html из репозитория...")
    
    success, result = await pull_from_github()
    
    if success:
        await message.edit_text(f"✅ {result}")
    else:
        await message.edit_text(f"❌ Ошибка: {result}")

async def push_hosting_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Обработчик команды /push_hosting - обновление хостинга из репозитория"""
    user_id = update.effective_user.id
    
    if str(user_id) != ADMIN_USER_ID:
        return
    
    message = await update.message.reply_text("⏳ Обновляю файлы на хостинге из репозитория...")
    
    success, result = await pull_from_github_to_hosting(context)
    
    if success:
        await message.edit_text(f"✅ Хостинг успешно обновлен:\n\n{result}")
    else:
        await message.edit_text(f"❌ Ошибка при обновлении хостинга:\n\n{result}")

async def rollback_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Обработчик команды /rollback - откат последних изменений"""
    user_id = update.effective_user.id
    
    if str(user_id) != ADMIN_USER_ID:
        return
    
    keyboard = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("✅ Да, откатить", callback_data="confirm_rollback"),
            InlineKeyboardButton("❌ Отмена", callback_data="cancel_rollback")
        ]
    ])
    
    await update.message.reply_text(
        "⚠️ Вы уверены, что хотите откатить последний коммит?\n\n"
        "Это действие отменит последние изменения в расписании.",
        reply_markup=keyboard
    )

async def schedule_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Обработчик команды /schedule - планирование обновления"""
    user_id = update.effective_user.id
    
    if str(user_id) != ADMIN_USER_ID:
        return ConversationHandler.END
    
    await update.message.reply_text(
        "⏰ Планирование автоматического обновления хостинга\n\n"
        "Пожалуйста, укажите дату и время в формате:\n"
        "<b>ГГГГ-ММ-ДД ЧЧ:ММ</b>\n\n"
        "Например: 2025-05-01 12:00",
        parse_mode="HTML"
    )
    
    context.user_data['conversation_active'] = True
    return SCHEDULE_TIME

async def set_schedule_time(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Установка времени для планирования обновления"""
    user_id = update.effective_user.id
    
    if str(user_id) != ADMIN_USER_ID:
        context.user_data['conversation_active'] = False
        return ConversationHandler.END
    
    schedule_time = update.message.text.strip()
    
    # Проверяем формат даты и времени
    try:
        task_dt = datetime.strptime(schedule_time, "%Y-%m-%d %H:%M")
        
        # Сохраняем время в контексте
        context.user_data['schedule_time'] = schedule_time
        
        keyboard = InlineKeyboardMarkup([
            [
                InlineKeyboardButton("✅ Подтвердить", callback_data="confirm_schedule"),
                InlineKeyboardButton("❌ Отмена", callback_data="cancel_schedule")
            ]
        ])
        
        await update.message.reply_text(
            f"⏰ Запланировать обновление на {schedule_time}?\n\n"
            "Хостинг будет автоматически обновлен в указанное время.",
            reply_markup=keyboard
        )
        
        return SCHEDULE_TIME
    except ValueError:
        await update.message.reply_text(
            "❌ Некорректный формат даты и времени.\n\n"
            "Пожалуйста, укажите дату и время в формате ГГГГ-ММ-ДД ЧЧ:ММ\n"
            "Например: 2025-05-01 12:00"
        )
        return SCHEDULE_TIME

async def confirm_schedule(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Подтверждение планирования обновления"""
    query = update.callback_query
    await query.answer()
    
    if query.data == "confirm_schedule":
        schedule_time = context.user_data.get('schedule_time')
        if not schedule_time:
            await query.edit_message_text("❌ Ошибка: время не указано.")
            context.user_data['conversation_active'] = False
            return ConversationHandler.END
        
        # Планируем задачу обновления
        success = await schedule_task(
            context=context,
            chat_id=query.message.chat_id,
            task_time=schedule_time,
            task_function=scheduled_pull_task,
            description="Обновление хостинга из репозитория"
        )
        
        if success:
            await query.edit_message_text(f"✅ Обновление запланировано на {schedule_time}")
        else:
            await query.edit_message_text("❌ Ошибка при планировании обновления.")
    else:
        await query.edit_message_text("❌ Планирование отменено.")
    
    context.user_data['conversation_active'] = False
    return ConversationHandler.END

async def logs_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Обработчик команды /logs - отправка файла логов"""
    user_id = update.effective_user.id
    
    if str(user_id) != ADMIN_USER_ID:
        return
    
    try:
        log_files = ["bot.log", "img_text_converter.log"]
        existing_logs = [f for f in log_files if os.path.exists(f)]
        
        if not existing_logs:
            await update.message.reply_text("❌ Файлы логов не найдены.")
            return
        
        await update.message.reply_text("⏳ Подготавливаю файлы логов...")
        
        for log_file in existing_logs:
            with open(log_file, "rb") as file:
                await update.message.reply_document(
                    document=file,
                    filename=log_file,
                    caption=f"📄 Лог-файл {log_file}"
                )
        
        await update.message.reply_text("✅ Файлы логов отправлены.")
    except Exception as e:
        logger.error(f"Ошибка при отправке логов: {str(e)}")
        await update.message.reply_text(f"❌ Ошибка при отправке логов: {str(e)}")

async def subscribers_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Обработчик команды /subscribers - список подписчиков"""
    user_id = update.effective_user.id
    
    if str(user_id) != ADMIN_USER_ID:
        return
    
    try:
        subscribers = subscriber_db.get_subscribers()
        
        if not subscribers:
            await update.message.reply_text("📊 Список подписчиков пуст.")
            return
        
        message = "📊 Список подписчиков:\n\n"
        
        for idx, (chat_id, username, full_name) in enumerate(subscribers, 1):
            message += f"{idx}. {full_name} (@{username}) - ID: {chat_id}\n"
        
        # Разбиваем сообщение на части, если оно слишком длинное
        if len(message) > 4000:
            chunks = [message[i:i+4000] for i in range(0, len(message), 4000)]
            for chunk in chunks:
                await update.message.reply_text(chunk)
        else:
            await update.message.reply_text(message)
    except Exception as e:
        logger.error(f"Ошибка при получении списка подписчиков: {str(e)}")
        await update.message.reply_text(f"❌ Ошибка при получении списка подписчиков: {str(e)}")

async def broadcast_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Обработчик команды /broadcast - отправка сообщения подписчикам"""
    user_id = update.effective_user.id
    
    if str(user_id) != ADMIN_USER_ID:
        return ConversationHandler.END
    
    try:
        subscriber_count = subscriber_db.get_subscriber_count()
        
        if subscriber_count == 0:
            await update.message.reply_text("❌ Нет подписчиков для рассылки.")
            return ConversationHandler.END
        
        await update.message.reply_text(
            f"📣 Создание рассылки для {subscriber_count} подписчиков\n\n"
            "Введите текст сообщения, которое будет отправлено всем подписчикам:"
        )
        
        context.user_data['conversation_active'] = True
        return COMPOSE_MESSAGE
    except Exception as e:
        logger.error(f"Ошибка при подготовке рассылки: {str(e)}")
        await update.message.reply_text(f"❌ Ошибка при подготовке рассылки: {str(e)}")
        return ConversationHandler.END

async def compose_broadcast_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Ввод текста для рассылки"""
    user_id = update.effective_user.id
    
    if str(user_id) != ADMIN_USER_ID:
        context.user_data['conversation_active'] = False
        return ConversationHandler.END
    
    broadcast_text = update.message.text
    
    if not broadcast_text or len(broadcast_text.strip()) == 0:
        await update.message.reply_text("❌ Текст сообщения не может быть пустым. Пожалуйста, введите текст:")
        return COMPOSE_MESSAGE
    
    context.user_data['broadcast_text'] = broadcast_text
    
    keyboard = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("✅ Отправить", callback_data="confirm_broadcast"),
            InlineKeyboardButton("❌ Отмена", callback_data="cancel_broadcast")
        ]
    ])
    
    await update.message.reply_text(
        "📣 Предварительный просмотр сообщения:\n\n"
        f"{broadcast_text}\n\n"
        "Отправить это сообщение всем подписчикам?",
        reply_markup=keyboard
    )
    
    return CONFIRM_BROADCAST

async def confirm_broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Подтверждение отправки рассылки"""
    query = update.callback_query
    await query.answer()
    
    if query.data == "confirm_broadcast":
        broadcast_text = context.user_data.get('broadcast_text', '')
        
        if not broadcast_text:
            await query.edit_message_text("❌ Ошибка: текст сообщения не найден.")
            context.user_data['conversation_active'] = False
            return ConversationHandler.END
        
        try:
            subscribers = subscriber_db.get_subscribers()
            
            if not subscribers:
                await query.edit_message_text("❌ Нет подписчиков для рассылки.")
                context.user_data['conversation_active'] = False
                return ConversationHandler.END
            
            await query.edit_message_text(f"⏳ Отправка сообщения {len(subscribers)} подписчикам...")
            
            # Счетчики для статистики
            success_count = 0
            error_count = 0
            
            # Отправляем сообщение всем подписчикам
            for chat_id, username, full_name in subscribers:
                try:
                    await context.bot.send_message(
                        chat_id=chat_id,
                        text=broadcast_text,
                        parse_mode="HTML"
                    )
                    # Обновляем статистику уведомлений для пользователя
                    subscriber_db.update_notification_stats(chat_id)
                    success_count += 1
                except Exception as e:
                    logger.error(f"Ошибка при отправке сообщения пользователю {chat_id}: {str(e)}")
                    error_count += 1
            
            # Сохраняем информацию о рассылке
            subscriber_db.save_broadcast(
                message_text=broadcast_text,
                success_count=success_count,
                error_count=error_count,
                admin_id=int(ADMIN_USER_ID)
            )
            
            await query.message.reply_text(
                f"✅ Рассылка завершена!\n\n"
                f"📊 Статистика:\n"
                f"✓ Успешно отправлено: {success_count}\n"
                f"✗ Ошибок: {error_count}"
            )
        except Exception as e:
            logger.error(f"Ошибка при выполнении рассылки: {str(e)}")
            await query.message.reply_text(f"❌ Ошибка при выполнении рассылки: {str(e)}")
    else:
        await query.edit_message_text("❌ Рассылка отменена.")
    
    context.user_data['conversation_active'] = False
    return ConversationHandler.END

async def subscribe_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Обработчик команды /subscribe - подписка на обновления"""
    user = update.effective_user
    chat_id = update.effective_chat.id
    
    try:
        success = subscriber_db.add_subscriber(
            chat_id, 
            user.username or "", 
            f"{user.first_name} {user.last_name or ''}".strip()
        )
        
        if success:
            await update.message.reply_text(
                "✅ Вы успешно подписались на обновления расписания богослужений!\n\n"
                "Когда расписание будет обновлено, вы получите уведомление."
            )
        else:
            await update.message.reply_text(
                "❌ Произошла ошибка при подписке. Пожалуйста, попробуйте позже."
            )
    except Exception as e:
        logger.error(f"Ошибка при подписке пользователя: {str(e)}")
        await update.message.reply_text(
            "❌ Произошла ошибка при подписке. Пожалуйста, попробуйте позже."
        )

async def unsubscribe_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Обработчик команды /unsubscribe - отписка от обновлений"""
    chat_id = update.effective_chat.id
    
    try:
        success = subscriber_db.remove_subscriber(chat_id)
        
        if success:
            await update.message.reply_text(
                "✅ Вы успешно отписались от обновлений расписания.\n\n"
                "Вы больше не будете получать уведомления."
            )
        else:
            await update.message.reply_text(
                "❌ Произошла ошибка при отписке. Пожалуйста, попробуйте позже."
            )
    except Exception as e:
        logger.error(f"Ошибка при отписке пользователя: {str(e)}")
        await update.message.reply_text(
            "❌ Произошла ошибка при отписке. Пожалуйста, попробуйте позже."
        )

async def handle_document(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Обработчик для документов (DOCX, TXT)"""
    user_id = update.effective_user.id
    
    if str(user_id) != ADMIN_USER_ID:
        USAGE_STATS["unauthorized_access_count"] += 1
        return
        
    document = update.message.document
    file_ext = os.path.splitext(document.file_name)[1].lower()
    
    if file_ext not in ['.docx', '.txt']:
        await update.message.reply_text(
            "⚠️ Пожалуйста, отправьте документ в формате DOCX или TXT."
        )
        return
        
    status_message = await update.message.reply_text("📥 Получаю документ... Пожалуйста, подождите.")
    
    try:
        # Загружаем файл
        file = await context.bot.get_file(document.file_id)
        file_path = os.path.join(TEXT_FOLDER, document.file_name)
        await file.download_to_drive(file_path)
        
        # Обновляем статистику
        USAGE_STATS["last_file_upload"] = datetime.now().strftime("%d.%m.%Y %H:%M")
        
        await status_message.edit_text(f"✅ Документ получен: {document.file_name}\n⏳ Извлекаю текст...")
        
        # Извлекаем текст
        if file_ext == '.docx':
            text = extract_text_from_docx(file_path)
        else:  # .txt
            text = extract_text_from_txt(file_path)
            
        if not text:
            await status_message.edit_text("❌ Не удалось извлечь текст из документа.")
            return
            
        await status_message.edit_text("✅ Текст извлечен успешно\n⏳ Обрабатываю текст...")
            
        # Обрабатываем текст
        text_processor.set_current(process_text(text))
        
        # Обновляем статистику
        USAGE_STATS["last_file_processing"] = datetime.now().strftime("%d.%m.%Y %H:%M")
        
        await status_message.edit_text("✅ Текст обработан успешно!")
        
        # Отправляем результат и запрашиваем подтверждение
        formatted_text = text_processor.current_text.replace('<br />', '\n').replace('<h3>', '*').replace('</h3>', '*')
        message = f"📋 Вот результат обработки текста:\n\n{formatted_text}\n\nВсё правильно?"
        
        # Разбиваем сообщение на части, если оно слишком длинное
        if len(message) > 4000:
            chunks = [message[i:i+4000] for i in range(0, len(message), 4000)]
            for i, chunk in enumerate(chunks):
                if i == len(chunks) - 1:  # Последний кусок
                    keyboard = InlineKeyboardMarkup([
                        [
                            InlineKeyboardButton("✅ Подтвердить", callback_data="confirm"),
                            InlineKeyboardButton("✏️ Редактировать", callback_data="edit")
                        ]
                    ])
                    await update.message.reply_text(chunk, reply_markup=keyboard)
                else:
                    await update.message.reply_text(chunk)
        else:
            keyboard = InlineKeyboardMarkup([
                [
                    InlineKeyboardButton("✅ Подтвердить", callback_data="confirm"),
                    InlineKeyboardButton("✏️ Редактировать", callback_data="edit")
                ]
            ])
            await update.message.reply_text(message, reply_markup=keyboard)
            
    except Exception as e:
        logger.error(f"Ошибка при обработке документа: {str(e)}\n{traceback.format_exc()}")
        await status_message.edit_text(f"❌ Произошла ошибка при обработке документа: {str(e)}")

async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Обработчик для фотографий"""
    user_id = update.effective_user.id
    
    if str(user_id) != ADMIN_USER_ID:
        USAGE_STATS["unauthorized_access_count"] += 1
        return
    
    status_message = await update.message.reply_text("📥 Получаю изображение... Пожалуйста, подождите.")
    
    try:
        # Загружаем файл
        photo = update.message.photo[-1]  # Берем изображение с наивысшим разрешением
        file = await context.bot.get_file(photo.file_id)
        file_path = os.path.join(IMAGES_FOLDER, f"image_{photo.file_id}.jpg")
        await file.download_to_drive(file_path)
        
        # Обновляем статистику
        USAGE_STATS["last_file_upload"] = datetime.now().strftime("%d.%m.%Y %H:%M")
        
        # Уведомляем о начале обработки
        await status_message.edit_text("✅ Изображение получено\n⏳ Распознаю текст...")
        
        # Распознаем текст с изображения
        text = recognize_text_from_image(file_path, lang="rus")
        
        if not text:
            await status_message.edit_text("❌ Не удалось распознать текст с изображения.")
            return
            
        await status_message.edit_text("✅ Текст распознан успешно\n⏳ Обрабатываю текст...")
            
        # Обрабатываем текст
        text_processor.set_current(process_text(text))
        
        # Обновляем статистику
        USAGE_STATS["last_file_processing"] = datetime.now().strftime("%d.%m.%Y %H:%M")
        
        # Отправляем результат и запрашиваем подтверждение
        await status_message.edit_text("✅ Текст успешно распознан и обработан!")
        
        formatted_text = text_processor.current_text.replace('<br />', '\n').replace('<h3>', '*').replace('</h3>', '*')
        message = f"📋 Вот результат распознавания и обработки текста:\n\n{formatted_text}\n\nВсё правильно?"
        
        # Разбиваем сообщение на части, если оно слишком длинное
        if len(message) > 4000:
            chunks = [message[i:i+4000] for i in range(0, len(message), 4000)]
            for i, chunk in enumerate(chunks):
                if i == len(chunks) - 1:  # Последний кусок
                    keyboard = InlineKeyboardMarkup([
                        [
                            InlineKeyboardButton("✅ Подтвердить", callback_data="confirm"),
                            InlineKeyboardButton("✏️ Редактировать", callback_data="edit")
                        ]
                    ])
                    await update.message.reply_text(chunk, reply_markup=keyboard)
                else:
                    await update.message.reply_text(chunk)
        else:
            keyboard = InlineKeyboardMarkup([
                [
                    InlineKeyboardButton("✅ Подтвердить", callback_data="confirm"),
                    InlineKeyboardButton("✏️ Редактировать", callback_data="edit")
                ]
            ])
            await update.message.reply_text(message, reply_markup=keyboard)
            
    except Exception as e:
        logger.error(f"Ошибка при распознавании текста: {str(e)}")
        await status_message.edit_text(f"❌ Произошла ошибка при распознавании текста: {str(e)}")

async def handle_edited_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Обработчик для отредактированного текста"""
    user_id = update.effective_user.id
    
    if str(user_id) != ADMIN_USER_ID:
        return
    
    # Проверяем, есть ли активная беседа
    if context.user_data.get('conversation_active'):
        # Пропускаем обработку, если это часть ConversationHandler
        return
    
    if text_processor.current_text is None:
        await update.message.reply_text("⚠️ Нет текущего текста для редактирования. Пожалуйста, сначала отправьте документ или изображение.")
        return
        
    # Сохраняем отредактированный текст
    text_processor.set_edited(update.message.text)
    
    try:
        # Преобразуем простой текст в HTML формат
        processed_text = ""
        for line in text_processor.edited_text.split('\n'):
            line = line.strip()
            if line.startswith('*') and line.endswith('*'):
                # Это заголовок h3
                title = line.strip('*')
                processed_text += f"<h3>{title}</h3>\n"
            else:
                # Это обычный текст
                processed_text += f"<br />{line}\n"
        
        # Обновляем текущий текст
        text_processor.set_current(processed_text)
        
        # Запрашиваем подтверждение
        keyboard = InlineKeyboardMarkup([
            [
                InlineKeyboardButton("✅ Подтвердить", callback_data="confirm"),
                InlineKeyboardButton("❌ Отменить", callback_data="cancel")
            ]
        ])
        await update.message.reply_text(
            "✅ Текст обновлен. Подтвердите обновление или отмените.",
            reply_markup=keyboard
        )
    except Exception as e:
        logger.error(f"Ошибка при обработке отредактированного текста: {str(e)}")
        await update.message.reply_text(f"❌ Произошла ошибка при обработке текста: {str(e)}")

async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Обработчик нажатий на кнопки"""
    query = update.callback_query
    await query.answer()
    
    user_id = update.effective_user.id
    
    if query.data == "main_menu":
        # Возврат в главное меню
        if str(user_id) == ADMIN_USER_ID:
            keyboard = InlineKeyboardMarkup([
                [InlineKeyboardButton("🔄 Обновить расписание", callback_data="update_schedule")],
                [InlineKeyboardButton("⬇️ Загрузить из GitHub", callback_data="pull_github")],
                [InlineKeyboardButton("🔃 Обновить хостинг", callback_data="update_hosting")],
                [InlineKeyboardButton("⏰ Запланировать обновление", callback_data="schedule_update")],
                [InlineKeyboardButton("↩️ Откатить изменения", callback_data="rollback")],
                [InlineKeyboardButton("🔄 Перезагрузить бота", callback_data="reboot")],
                [InlineKeyboardButton("📊 Статус бота", callback_data="status")],
                [InlineKeyboardButton("📨 Рассылка подписчикам", callback_data="broadcast")]
            ])
            
            await query.edit_message_text(
                "🏠 Главное меню\n\n"
                "Выберите действие:",
                reply_markup=keyboard
            )
        else:
            # Для обычных пользователей
            keyboard = InlineKeyboardMarkup([
                [InlineKeyboardButton("✅ Подписаться на обновления", callback_data="subscribe")],
                [InlineKeyboardButton("❌ Отписаться от обновлений", callback_data="unsubscribe")]
            ])
            
            await query.edit_message_text(
                "Это бот для отправки обновлений расписания богослужений.\n\n"
                "Вы можете подписаться на уведомления об изменениях в расписании:",
                reply_markup=keyboard
            )
    
    elif query.data == "update_schedule":
        # Инструкция по обновлению расписания
        await query.edit_message_text(
            "📝 Обновление расписания богослужений\n\n"
            "Для обновления расписания отправьте мне один из следующих файлов:\n"
            "1. Документ в формате DOCX или TXT с текстом расписания\n"
            "2. Фотографию с текстом расписания\n\n"
            "После обработки файла вы сможете проверить и отредактировать результат."
        )
    
    elif query.data == "pull_github":
        # Загрузка файла index.html из репозитория
        await query.edit_message_text("⏳ Загружаю файл index.html из репозитория...")
        
        success, result = await pull_from_github()
        
        if success:
            await query.edit_message_text(f"✅ {result}")
        else:
            await query.edit_message_text(f"❌ Ошибка: {result}")
    
    elif query.data == "update_hosting":
        # Обновление хостинга из репозитория
        await query.edit_message_text("⏳ Обновляю файлы на хостинге из репозитория...")
        
        success, result = await pull_from_github_to_hosting(context)
        
        if success:
            await query.edit_message_text(f"✅ Хостинг успешно обновлен:\n\n{result}")
        else:
            await query.edit_message_text(f"❌ Ошибка при обновлении хостинга:\n\n{result}")
    
    elif query.data == "rollback":
        # Откат последних изменений
        if str(user_id) != ADMIN_USER_ID:
            return
            
        keyboard = InlineKeyboardMarkup([
            [
                InlineKeyboardButton("✅ Да, откатить", callback_data="confirm_rollback"),
                InlineKeyboardButton("❌ Отмена", callback_data="cancel_rollback")
            ]
        ])
        
        await query.edit_message_text(
            "⚠️ Вы уверены, что хотите откатить последний коммит?\n\n"
            "Это действие отменит последние изменения в расписании.",
            reply_markup=keyboard
        )
    
    elif query.data == "confirm_rollback":
        # Подтверждение отката изменений
        if str(user_id) != ADMIN_USER_ID:
            return
            
        await query.edit_message_text("⏳ Отменяю последний коммит...")
        
        success, result = await rollback_last_commit()
        
        if success:
            await query.edit_message_text(f"✅ {result}")
        else:
            await query.edit_message_text(f"❌ Ошибка: {result}")
    
    elif query.data == "cancel_rollback":
        # Отмена отката изменений
        if str(user_id) != ADMIN_USER_ID:
            return
            
        await query.edit_message_text("❌ Откат изменений отменен.")
    
    elif query.data == "reboot":
        # Перезагрузка бота
        if str(user_id) != ADMIN_USER_ID:
            return
            
        keyboard = InlineKeyboardMarkup([
            [
                InlineKeyboardButton("✅ Да, перезагрузить", callback_data="confirm_reboot"),
                InlineKeyboardButton("❌ Отмена", callback_data="cancel_reboot")
            ]
        ])
        
        await query.edit_message_text(
            "⚠️ Вы уверены, что хотите перезагрузить бота?\n\n"
            "Это приведет к временной недоступности бота на несколько секунд.",
            reply_markup=keyboard
        )
    
    elif query.data == "confirm_reboot":
        # Подтверждение перезагрузки
        if str(user_id) != ADMIN_USER_ID:
            return
            
        await query.edit_message_text("🔄 Начинаю перезагрузку бота. Бот будет недоступен несколько секунд...")
        
        success = await reboot_container()
        
        if success:
            # Это сообщение не успеет отправиться, так как бот перезапустится
            await query.message.reply_text("✅ Бот успешно перезагружается...")
        else:
            await query.message.reply_text("❌ Ошибка при перезагрузке бота.")
    
    elif query.data == "cancel_reboot":
        # Отмена перезагрузки
        if str(user_id) != ADMIN_USER_ID:
            return
            
        await query.edit_message_text("❌ Перезагрузка отменена.")
    
    elif query.data == "status":
        # Показать статус бота
        if str(user_id) != ADMIN_USER_ID:
            return
            
        status_message = "📊 Статус бота:\n\n"
        
        # Проверка доступа к index.html
        index_exists = os.path.exists(INDEX_HTML_PATH)
        status_message += f"📄 Файл index.html: {'✅ Доступен' if index_exists else '❌ Недоступен'}\n"
        
        # Проверка временных папок
        images_count = len(os.listdir(IMAGES_FOLDER)) if os.path.exists(IMAGES_FOLDER) else 0
        text_count = len(os.listdir(TEXT_FOLDER)) if os.path.exists(TEXT_FOLDER) else 0
        status_message += f"🖼️ Файлов во временной папке изображений: {images_count}\n"
        status_message += f"📝 Файлов во временной папке текстов: {text_count}\n"
        
        # Проверка состояния текста
        has_current = text_processor.current_text is not None
        has_edited = text_processor.edited_text is not None
        status_message += f"📋 Текущий текст: {'✅ Есть' if has_current else '❌ Нет'}\n"
        status_message += f"✏️ Отредактированный текст: {'✅ Есть' if has_edited else '❌ Нет'}\n"
        
        # Добавляем статистику использования
        status_message += f"⏱️ Время работы сервера: {get_uptime()}\n"
        
        if USAGE_STATS["last_file_upload"]:
            status_message += f"📅 Последняя загрузка файлов с расписанием: {USAGE_STATS['last_file_upload']}\n"
            
        if USAGE_STATS["last_file_processing"]:
            status_message += f"📅 Последняя обработка файлов с расписанием: {USAGE_STATS['last_file_processing']}\n"
            
        if USAGE_STATS["last_repo_push"]:
            status_message += f"🔄 Последний пуш в репозиторий: {USAGE_STATS['last_repo_push']}\n"
            
        status_message += f"🚫 Отказы в авторизации другим пользователям телеграм: {USAGE_STATS['unauthorized_access_count']}\n"
        
        # Информация о подписчиках
        try:
            subscriber_count = subscriber_db.get_subscriber_count()
            db_size = subscriber_db.get_database_size()
            status_message += f"👥 Количество подписчиков на обновления: {subscriber_count}\n"
            status_message += f"💾 Размер базы данных: {db_size.get('size_mb', 0)} МБ\n"
        except Exception as e:
            logger.error(f"Ошибка при получении информации о базе данных: {str(e)}")
            status_message += f"❌ Ошибка при получении информации о базе данных: {str(e)}\n"
        
        # Запланированные задачи
        if USAGE_STATS["scheduled_updates"]:
            status_message += "\n📆 Запланированные обновления:\n"
            for idx, task in enumerate(USAGE_STATS["scheduled_updates"], 1):
                status_message += f"{idx}. {task['description']} - {task['time']}\n"
        
        # Добавляем кнопки для действий
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("🏠 Главное меню", callback_data="main_menu")],
            [InlineKeyboardButton("📁 Отправить логи", callback_data="send_logs")]
        ])
        
        await query.edit_message_text(status_message, reply_markup=keyboard)
    
    elif query.data == "send_logs":
        # Отправка файлов логов
        if str(user_id) != ADMIN_USER_ID:
            return
            
        try:
            log_files = ["bot.log", "img_text_converter.log"]
            existing_logs = [f for f in log_files if os.path.exists(f)]
            
            if not existing_logs:
                await query.edit_message_text(
                    "❌ Файлы логов не найдены.",
                    reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🏠 Главное меню", callback_data="main_menu")]])
                )
                return
            
            await query.edit_message_text("⏳ Подготавливаю файлы логов...")
            
            for log_file in existing_logs:
                with open(log_file, "rb") as file:
                    await query.message.reply_document(
                        document=file,
                        filename=log_file,
                        caption=f"📄 Лог-файл {log_file}"
                    )
            
            await query.message.reply_text(
                "✅ Файлы логов отправлены.",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🏠 Главное меню", callback_data="main_menu")]])
            )
        except Exception as e:
            logger.error(f"Ошибка при отправке логов: {str(e)}")
            await query.edit_message_text(
                f"❌ Ошибка при отправке логов: {str(e)}",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🏠 Главное меню", callback_data="main_menu")]])
            )
    
    elif query.data == "schedule_update":
        # Запланировать обновление
        if str(user_id) != ADMIN_USER_ID:
            return
            
        await query.message.reply_text(
            "⏰ Планирование автоматического обновления хостинга\n\n"
            "Пожалуйста, укажите дату и время в формате:\n"
            "<b>ГГГГ-ММ-ДД ЧЧ:ММ</b>\n\n"
            "Например: 2025-05-01 12:00",
            parse_mode="HTML"
        )
        
        # Устанавливаем флаг активной беседы
        context.user_data['conversation_active'] = True
        context.user_data['current_state'] = SCHEDULE_TIME
    
    elif query.data == "confirm_schedule":
        # Подтверждение запланированного обновления
        if str(user_id) != ADMIN_USER_ID:
            return
            
        schedule_time = context.user_data.get('schedule_time')
        if not schedule_time:
            await query.edit_message_text("❌ Ошибка: время не указано.")
            context.user_data['conversation_active'] = False
            return
        
        # Планируем задачу обновления
        success = await schedule_task(
            context=context,
            chat_id=query.message.chat_id,
            task_time=schedule_time,
            task_function=scheduled_pull_task,
            description="Обновление хостинга из репозитория"
        )
        
        if success:
            await query.edit_message_text(f"✅ Обновление запланировано на {schedule_time}")
        else:
            await query.edit_message_text("❌ Ошибка при планировании обновления.")
            
        context.user_data['conversation_active'] = False
    
    elif query.data == "cancel_schedule":
        # Отмена запланированного обновления
        if str(user_id) != ADMIN_USER_ID:
            return
            
        await query.edit_message_text("❌ Планирование отменено.")
        context.user_data['conversation_active'] = False
    
    elif query.data == "broadcast":
        # Рассылка подписчикам
        if str(user_id) != ADMIN_USER_ID:
            return
            
        try:
            subscriber_count = subscriber_db.get_subscriber_count()
            
            if subscriber_count == 0:
                await query.edit_message_text(
                    "❌ Нет подписчиков для рассылки.",
                    reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🏠 Главное меню", callback_data="main_menu")]])
                )
                return
            
            await query.message.reply_text(
                f"📣 Создание рассылки для {subscriber_count} подписчиков\n\n"
                "Введите текст сообщения, которое будет отправлено всем подписчикам:"
            )
            
            # Устанавливаем флаг активной беседы
            context.user_data['conversation_active'] = True
            context.user_data['current_state'] = COMPOSE_MESSAGE
        except Exception as e:
            logger.error(f"Ошибка при подготовке рассылки: {str(e)}")
            await query.edit_message_text(
                f"❌ Ошибка при подготовке рассылки: {str(e)}",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🏠 Главное меню", callback_data="main_menu")]])
            )
    
    elif query.data == "confirm_broadcast":
        # Подтверждение рассылки
        if str(user_id) != ADMIN_USER_ID:
            return
            
        broadcast_text = context.user_data.get('broadcast_text', '')
        
        if not broadcast_text:
            await query.edit_message_text("❌ Ошибка: текст сообщения не найден.")
            context.user_data['conversation_active'] = False
            return
        
        try:
            subscribers = subscriber_db.get_subscribers()
            
            if not subscribers:
                await query.edit_message_text("❌ Нет подписчиков для рассылки.")
                context.user_data['conversation_active'] = False
                return
            
            await query.edit_message_text(f"⏳ Отправка сообщения {len(subscribers)} подписчикам...")
            
            # Счетчики для статистики
            success_count = 0
            error_count = 0
            
            # Отправляем сообщение всем подписчикам
            for chat_id, username, full_name in subscribers:
                try:
                    await context.bot.send_message(
                        chat_id=chat_id,
                        text=broadcast_text,
                        parse_mode="HTML"
                    )
                    # Обновляем статистику уведомлений для пользователя
                    subscriber_db.update_notification_stats(chat_id)
                    success_count += 1
                except Exception as e:
                    logger.error(f"Ошибка при отправке сообщения пользователю {chat_id}: {str(e)}")
                    error_count += 1
            
            # Сохраняем информацию о рассылке
            subscriber_db.save_broadcast(
                message_text=broadcast_text,
                success_count=success_count,
                error_count=error_count,
                admin_id=int(ADMIN_USER_ID)
            )
            
            await query.message.reply_text(
                f"✅ Рассылка завершена!\n\n"
                f"📊 Статистика:\n"
                f"✓ Успешно отправлено: {success_count}\n"
                f"✗ Ошибок: {error_count}",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🏠 Главное меню", callback_data="main_menu")]])
            )
        except Exception as e:
            logger.error(f"Ошибка при выполнении рассылки: {str(e)}")
            await query.message.reply_text(
                f"❌ Ошибка при выполнении рассылки: {str(e)}",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🏠 Главное меню", callback_data="main_menu")]])
            )
        
        context.user_data['conversation_active'] = False
    
    elif query.data == "cancel_broadcast":
        # Отмена рассылки
        if str(user_id) != ADMIN_USER_ID:
            return
            
        await query.edit_message_text("❌ Рассылка отменена.")
        context.user_data['conversation_active'] = False
    
    elif query.data == "subscribe":
        # Подписка на обновления
        try:
            user = update.effective_user
            chat_id = update.effective_chat.id
            
            success = subscriber_db.add_subscriber(
                chat_id, 
                user.username or "", 
                f"{user.first_name} {user.last_name or ''}".strip()
            )
            
            if success:
                await query.edit_message_text(
                    "✅ Вы успешно подписались на обновления расписания богослужений!\n\n"
                    "Когда расписание будет обновлено, вы получите уведомление."
                )
            else:
                await query.edit_message_text(
                    "❌ Произошла ошибка при подписке. Пожалуйста, попробуйте позже."
                )
        except Exception as e:
            logger.error(f"Ошибка при подписке пользователя: {str(e)}")
            await query.edit_message_text(
                "❌ Произошла ошибка при подписке. Пожалуйста, попробуйте позже."
            )
    
    elif query.data == "unsubscribe":
        # Отписка от обновлений
        try:
            chat_id = update.effective_chat.id
            
            success = subscriber_db.remove_subscriber(chat_id)
            
            if success:
                await query.edit_message_text(
                    "✅ Вы успешно отписались от обновлений расписания.\n\n"
                    "Вы больше не будете получать уведомления."
                )
            else:
                await query.edit_message_text(
                    "❌ Произошла ошибка при отписке. Пожалуйста, попробуйте позже."
                )
        except Exception as e:
            logger.error(f"Ошибка при отписке пользователя: {str(e)}")
            await query.edit_message_text(
                "❌ Произошла ошибка при отписке. Пожалуйста, попробуйте позже."
            )
    
    elif query.data == "confirm":
        # Подтверждение обновления расписания
        if str(user_id) != ADMIN_USER_ID:
            return
            
        confirmation_message = await query.edit_message_text("⏳ Подтверждено! Обновляю расписание на сайте...")
        
        try:
            final_text = text_processor.get_final_text()
            if not final_text:
                await confirmation_message.edit_text("❌ Ошибка: текст для обновления не найден.")
                return
                
            # Создаем HTML для расписания
            schedule_html = create_schedule_html(final_text)
            
            success = False
            
            # Сначала загружаем последнюю версию из репозитория
            success_pull, pull_result = await pull_from_github()
            if not success_pull:
                await query.message.reply_text(f"⚠️ Предупреждение: не удалось загрузить последнюю версию из репозитория: {pull_result}")
            
            # Пробуем сначала обновить непосредственно файл в монтированном томе
            if os.path.exists(INDEX_HTML_PATH):
                try:
                    update_index_html(INDEX_HTML_PATH, schedule_html)
                    await query.message.reply_text("✅ Файл index.html успешно обновлен локально!")
                    success = True
                except Exception as e:
                    logger.error(f"Ошибка при обновлении локального файла: {str(e)}")
                    await query.message.reply_text(f"❌ Не удалось обновить локальный файл: {str(e)}")
            
            # Вариант 2: Обновляем репозиторий GitHub
            if not success or REPO_URL:
                await query.message.reply_text("⏳ Обновляю репозиторий GitHub...")
                
                # Удаляем локальный репозиторий, если он существует
                if os.path.exists(REPO_PATH):
                    shutil.rmtree(REPO_PATH)
                    
                # Клонируем репозиторий
                repo_url_with_token = REPO_URL.replace('https://', f'https://{GIT_TOKEN}@')
                
                # Клонируем репозиторий
                repo = git.Repo.clone_from(repo_url_with_token, REPO_PATH)
                
                # Настраиваем имя пользователя и email для коммитов
                repo.config_writer().set_value("user", "name", GIT_USERNAME).release()
                repo.config_writer().set_value("user", "email", GIT_EMAIL).release()
                
                # Путь к файлу index.html в репозитории
                index_path = os.path.join(REPO_PATH, "index.html")
                
                # Обновляем index.html
                update_index_html(index_path, schedule_html)
                
                # Проверяем, есть ли изменения для коммита
                if repo.is_dirty(untracked_files=True):
                    # Коммитим и пушим изменения
                    repo.git.add(index_path)
                    commit_message = f"Update schedule - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
                    repo.git.commit('-m', commit_message)
                    repo.git.push()
                    
                    # Обновляем статистику
                    USAGE_STATS["last_repo_push"] = datetime.now().strftime("%d.%m.%Y %H:%M")
                    
                    await query.message.reply_text("✅ Расписание успешно обновлено и отправлено на GitHub!")
                    
                    # Обновляем хостинг
                    success_host, host_result = await pull_from_github_to_hosting(context)
                    if success_host:
                        await query.message.reply_text(f"✅ Хостинг успешно обновлен:\n\n{host_result}")
                    else:
                        await query.message.reply_text(f"⚠️ Не удалось обновить хостинг автоматически:\n\n{host_result}")
                else:
                    await query.message.reply_text("ℹ️ Изменений в расписании не обнаружено.")
            
                # Отправляем уведомление подписчикам, если есть
                try:
                    subscribers = subscriber_db.get_subscribers()
                    if subscribers:
                        notification_message = (
                            "📣 Обновлено расписание богослужений!\n\n"
                            "Пожалуйста, посетите сайт для просмотра нового расписания."
                        )
                        
                        sent_count = 0
                        for chat_id, _, _ in subscribers:
                            try:
                                await context.bot.send_message(
                                    chat_id=chat_id,
                                    text=notification_message
                                )
                                # Обновляем статистику уведомлений для пользователя
                                subscriber_db.update_notification_stats(chat_id)
                                sent_count += 1
                            except Exception as e:
                                logger.error(f"Ошибка при отправке уведомления пользователю {chat_id}: {str(e)}")
                        
                        await query.message.reply_text(f"✅ Уведомления об обновлении отправлены {sent_count} подписчикам.")
                except Exception as e:
                    logger.error(f"Ошибка при отправке уведомлений подписчикам: {str(e)}")
                    await query.message.reply_text(f"❌ Ошибка при отправке уведомлений подписчикам: {str(e)}")
            
            # Очищаем текущее состояние
            text_processor.reset()
            
            # Очищаем временные файлы
            for file in os.listdir(IMAGES_FOLDER):
                os.remove(os.path.join(IMAGES_FOLDER, file))
            for file in os.listdir(TEXT_FOLDER):
                os.remove(os.path.join(TEXT_FOLDER, file))
                
            await confirmation_message.edit_text("✅ Обновление расписания успешно завершено!")
                
        except Exception as e:
            logger.error(f"Ошибка при обновлении расписания: {str(e)}")
            await confirmation_message.edit_text(f"❌ Произошла ошибка при обновлении расписания: {str(e)}")
            
    elif query.data == "edit":
        # Редактирование текста расписания
        if str(user_id) != ADMIN_USER_ID:
            return
            
        if text_processor.current_text is None:
            await query.edit_message_text("❌ Нет текста для редактирования.")
            return
            
        # Форматируем текст для редактирования
        readable_text = text_processor.current_text.replace('<br />', '\n').replace('<h3>', '*').replace('</h3>', '*')
        
        await query.edit_message_text(
            "✏️ Пожалуйста, отправьте отредактированный текст.\n\n"
            "Правила форматирования:\n"
            "1. Обозначьте заголовки звездочками: *Заголовок*\n"
            "2. Обычный текст пишите как есть\n"
            "3. Разделяйте строки переносами\n\n"
            f"{readable_text}"
        )
        
    elif query.data == "cancel":
        # Отменяем текущую операцию
        if str(user_id) != ADMIN_USER_ID:
            return
            
        text_processor.reset()
        
        await query.edit_message_text("❌ Операция отменена.")
        
        # Очищаем временные файлы
        for file in os.listdir(IMAGES_FOLDER):
            os.remove(os.path.join(IMAGES_FOLDER, file))
        for file in os.listdir(TEXT_FOLDER):
            os.remove(os.path.join(TEXT_FOLDER, file))

# Добавим обработчики для различных вариантов планирования
async def handle_schedule_selection(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Обрабатывает выбор типа расписания"""
    query = update.callback_query
    await query.answer()
    
    if query.data == "cancel_schedule":
        await query.edit_message_text("❌ Планирование отменено.")
        context.user_data.pop('conversation_active', None)
        return ConversationHandler.END
    
    # Сохраняем тип расписания
    context.user_data['schedule_type'] = query.data
    
    if query.data == "schedule_daily":
        await query.edit_message_text(
            "🕙 Ежедневное обновление\n\n"
            "Укажите время в формате ЧЧ:ММ, например, 03:00"
        )
    elif query.data == "schedule_weekly":
        keyboard = [
            [
                InlineKeyboardButton("Пн", callback_data="day_1"),
                InlineKeyboardButton("Вт", callback_data="day_2"),
                InlineKeyboardButton("Ср", callback_data="day_3")
            ],
            [
                InlineKeyboardButton("Чт", callback_data="day_4"),
                InlineKeyboardButton("Пт", callback_data="day_5"),
                InlineKeyboardButton("Сб", callback_data="day_6")
            ],
            [
                InlineKeyboardButton("Вс", callback_data="day_0"),
                InlineKeyboardButton("❌ Отмена", callback_data="cancel_schedule")
            ]
        ]
        
        await query.edit_message_text(
            "📅 Еженедельное обновление\n\n"
            "Выберите день недели:",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        return SCHEDULE_TIME  # Особое состояние для выбора дня недели
    elif query.data == "schedule_custom":
        await query.edit_message_text(
            "📆 Указать дату и время\n\n"
            "Пожалуйста, укажите дату и время в формате:\n"
            "<b>ГГГГ-ММ-ДД ЧЧ:ММ</b>\n\n"
            "Например: 2025-05-01 12:00",
            parse_mode="HTML"
        )
    else:
        await query.edit_message_text("❌ Неизвестный тип расписания. Планирование отменено.")
        context.user_data.pop('conversation_active', None)
        return ConversationHandler.END
    
    return SCHEDULE_TIME

async def handle_weekly_day_selection(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Обрабатывает выбор дня недели для еженедельного обновления"""
    query = update.callback_query
    await query.answer()
    
    if query.data == "cancel_schedule":
        await query.edit_message_text("❌ Планирование отменено.")
        context.user_data.pop('conversation_active', None)
        return ConversationHandler.END
    
    # Получаем день недели (0-6, где 0=воскресенье)
    day = int(query.data.split('_')[1])
    context.user_data['schedule_day'] = day
    
    # Запрашиваем время
    await query.edit_message_text(
        f"📅 Еженедельное обновление ({['Вс', 'Пн', 'Вт', 'Ср', 'Чт', 'Пт', 'Сб'][day]})\n\n"
        "Укажите время в формате ЧЧ:ММ, например, 03:00"
    )
    
    return SCHEDULE_TIME

# Обработчик для ввода времени для различных типов расписания
async def process_schedule_time(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Обрабатывает ввод времени для планирования"""
    user_id = update.effective_user.id
    
    if str(user_id) != ADMIN_USER_ID:
        context.user_data.pop('conversation_active', None)
        return ConversationHandler.END
    
    schedule_type = context.user_data.get('schedule_type', '')
    
    if schedule_type == "schedule_daily":
        # Обрабатываем ежедневное расписание
        time_input = update.message.text.strip()
        
        # Проверяем формат времени
        try:
            hour, minute = map(int, time_input.split(':'))
            if hour < 0 or hour > 23 or minute < 0 or minute > 59:
                raise ValueError("Некорректное время")
            
            # Сохраняем время
            context.user_data['schedule_time'] = time_input
            
            # Создаем задачу
            now = datetime.now()
            schedule_time = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
            
            # Если время уже прошло сегодня, переносим на завтра
            if schedule_time <= now:
                schedule_time = schedule_time + timedelta(days=1)
            
            # Форматируем время для вывода
            scheduled_time_str = schedule_time.strftime("%Y-%m-%d %H:%M")
            
            # Добавляем задачу в планировщик
            job = context.job_queue.run_daily(
                scheduled_pull_task,
                time=schedule_time.time(),
                days=(0, 1, 2, 3, 4, 5, 6),  # Все дни недели
                data={
                    'chat_id': update.effective_chat.id,
                    'description': f"Ежедневное обновление хостинга в {time_input}"
                }
            )
            
            # Сохраняем информацию о задаче
            task_info = {
                'job_id': job.job_id,
                'type': 'daily',
                'time': time_input,
                'description': f"Ежедневное обновление хостинга в {time_input}",
                'created_at': now.strftime("%Y-%m-%d %H:%M:%S")
            }
            USAGE_STATS["scheduled_updates"].append(task_info)
            save_scheduled_tasks()
            
            await update.message.reply_text(
                f"✅ Запланировано ежедневное обновление хостинга в {time_input}\n\n"
                f"Следующее обновление: {scheduled_time_str}"
            )
            
        except Exception as e:
            logger.error(f"Ошибка при обработке времени: {str(e)}")
            await update.message.reply_text(
                "❌ Некорректный формат времени. Пожалуйста, укажите время в формате ЧЧ:ММ"
            )
            return SCHEDULE_TIME
    
    elif schedule_type == "schedule_weekly":
        # Обрабатываем еженедельное расписание
        time_input = update.message.text.strip()
        day = context.user_data.get('schedule_day', 0)
        day_names = ['Воскресенье', 'Понедельник', 'Вторник', 'Среда', 'Четверг', 'Пятница', 'Суббота']
        
        # Проверяем формат времени
        try:
            hour, minute = map(int, time_input.split(':'))
            if hour < 0 or hour > 23 or minute < 0 or minute > 59:
                raise ValueError("Некорректное время")
            
            # Сохраняем время
            context.user_data['schedule_time'] = time_input
            
            # Создаем задачу
            now = datetime.now()
            
            # Добавляем задачу в планировщик
            job = context.job_queue.run_daily(
                scheduled_pull_task,
                time=time(hour, minute),
                days=(day,),  # Только выбранный день недели
                data={
                    'chat_id': update.effective_chat.id,
                    'description': f"Еженедельное обновление хостинга ({day_names[day]}) в {time_input}"
                }
            )
            
            # Сохраняем информацию о задаче
            task_info = {
                'job_id': job.job_id,
                'type': 'weekly',
                'day': day,
                'time': time_input,
                'description': f"Еженедельное обновление хостинга ({day_names[day]}) в {time_input}",
                'created_at': now.strftime("%Y-%m-%d %H:%M:%S")
            }
            USAGE_STATS["scheduled_updates"].append(task_info)
            save_scheduled_tasks()
            
            await update.message.reply_text(
                f"✅ Запланировано еженедельное обновление хостинга каждый {day_names[day].lower()} в {time_input}"
            )
            
        except Exception as e:
            logger.error(f"Ошибка при обработке времени: {str(e)}")
            await update.message.reply_text(
                "❌ Некорректный формат времени. Пожалуйста, укажите время в формате ЧЧ:ММ"
            )
            return SCHEDULE_TIME
    
    elif schedule_type == "schedule_custom":
        # Обрабатываем разовое расписание
        datetime_input = update.message.text.strip()
        
        # Проверяем формат даты и времени
        try:
            schedule_time = datetime.strptime(datetime_input, "%Y-%m-%d %H:%M")
            
            # Если время уже прошло
            if schedule_time <= datetime.now():
                await update.message.reply_text(
                    "❌ Указанное время уже прошло. Пожалуйста, укажите будущую дату и время."
                )
                return SCHEDULE_TIME
            
            # Сохраняем время
            context.user_data['schedule_datetime'] = datetime_input
            
            # Создаем задачу
            success = await schedule_task(
                context=context,
                chat_id=update.effective_chat.id,
                task_time=datetime_input,
                task_function=scheduled_pull_task,
                description="Разовое обновление хостинга из репозитория"
            )
            
            if success:
                await update.message.reply_text(f"✅ Запланировано разовое обновление хостинга на {datetime_input}")
            else:
                await update.message.reply_text("❌ Ошибка при планировании обновления.")
            
        except ValueError:
            await update.message.reply_text(
                "❌ Некорректный формат даты и времени.\n\n"
                "Пожалуйста, укажите дату и время в формате ГГГГ-ММ-ДД ЧЧ:ММ\n"
                "Например: 2025-05-01 12:00"
            )
            return SCHEDULE_TIME
    
    else:
        await update.message.reply_text("❌ Неизвестный тип расписания. Планирование отменено.")
        
    context.user_data.pop('conversation_active', None)
    return ConversationHandler.END

def main() -> None:
    """Запуск бота"""
    try:
        # Загружаем запланированные задачи
        load_scheduled_tasks()
        
        # Создаем временные папки, если их нет
        Path(IMAGES_FOLDER).mkdir(exist_ok=True)
        Path(TEXT_FOLDER).mkdir(exist_ok=True)
        
        # Создаем директорию для данных базы данных, если она не существует
        Path(os.path.dirname(DATABASE_PATH)).mkdir(exist_ok=True)
        
        # Получаем токен бота из переменной окружения
        token = os.environ.get("TELEGRAM_TOKEN")
        
        if not token:
            logger.error("❌ Не указан токен бота в переменной окружения TELEGRAM_TOKEN")
            return
            
        # Создаем приложение
        application = Application.builder().token(token).build()
        
        # Добавляем обработчики команд
        application.add_handler(CommandHandler("start", start))
        application.add_handler(CommandHandler("help", help_command))
        application.add_handler(CommandHandler("cancel", cancel))
        application.add_handler(CommandHandler("status", status_command))
        application.add_handler(CommandHandler("pull", pull_command))
        application.add_handler(CommandHandler("push_hosting", update_hosting_command))
        application.add_handler(CommandHandler("rollback", rollback_command))
        application.add_handler(CommandHandler("logs", send_logs))
        application.add_handler(CommandHandler("subscribers", subscribers_command))
        application.add_handler(CommandHandler("subscribe", subscribe_command))
        application.add_handler(CommandHandler("unsubscribe", unsubscribe_command))
        application.add_handler(CommandHandler("test_ssh", test_ssh_command))
        application.add_handler(CommandHandler("restart_server", restart_server_command))
        
        # Добавляем ConversationHandler для команды /reboot
        reboot_conv_handler = ConversationHandler(
            entry_points=[CommandHandler("reboot", reboot_command)],
            states={
                CONFIRM_REBOOT: [CallbackQueryHandler(confirm_reboot, pattern="^confirm_reboot$|^cancel_reboot$")]
            },
            fallbacks=[CommandHandler("cancel", cancel)]
        )
        application.add_handler(reboot_conv_handler)
        
        # Добавляем ConversationHandler для команды /schedule
        schedule_conv_handler = ConversationHandler(
            entry_points=[CommandHandler("schedule", schedule_update_command)],
            states={
                SCHEDULE_TIME: [
                    MessageHandler(filters.TEXT & ~filters.COMMAND, process_schedule_time),
                    CallbackQueryHandler(handle_schedule_selection, 
                                         pattern="^schedule_daily$|^schedule_weekly$|^schedule_custom$|^cancel_schedule$"),
                    CallbackQueryHandler(handle_weekly_day_selection, pattern="^day_\d$")
                ]
            },
            fallbacks=[CommandHandler("cancel", cancel)]
        )
        application.add_handler(schedule_conv_handler)
        
        # Добавляем ConversationHandler для команды /broadcast
        broadcast_conv_handler = ConversationHandler(
            entry_points=[CommandHandler("broadcast", broadcast_command)],
            states={
                COMPOSE_MESSAGE: [MessageHandler(filters.TEXT & ~filters.COMMAND, compose_broadcast_message)],
                CONFIRM_BROADCAST: [CallbackQueryHandler(confirm_broadcast, pattern="^confirm_broadcast$|^cancel_broadcast$")]
            },
            fallbacks=[CommandHandler("cancel", cancel)]
        )
        application.add_handler(broadcast_conv_handler)
        
        # Добавляем обработчики сообщений
        application.add_handler(MessageHandler(filters.PHOTO, handle_photo))
        application.add_handler(MessageHandler(filters.Document.ALL, handle_document))
        application.add_handler(MessageHandler(
            filters.TEXT & ~filters.COMMAND & filters.User(int(ADMIN_USER_ID)), 
            handle_edited_text
        ))
        
        # Добавляем обработчик для кнопок
        application.add_handler(CallbackQueryHandler(handle_callback))
        
        logger.info("✅ Бот запущен и готов к работе")
        
        # Запускаем бота
        application.run_polling(allowed_updates=Update.ALL_TYPES)
        
    except Exception as e:
        logger.error(f"❌ Критическая ошибка при запуске бота: {str(e)}")
        import traceback
        logger.error(traceback.format_exc())

if __name__ == "__main__":
    main()