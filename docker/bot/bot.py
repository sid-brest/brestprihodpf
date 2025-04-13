import os
import logging
import tempfile
from pathlib import Path
import re
import shutil
import git
from datetime import datetime
import traceback
from dotenv import load_dotenv

from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import Application, CommandHandler, MessageHandler, filters, CallbackQueryHandler, ContextTypes

# Импортируем функции из текстового конвертера
from img_text_converter import (
    extract_text_from_txt, 
    extract_text_from_docx, 
    process_text, 
    create_schedule_html, 
    update_index_html
)

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

# Проверка наличия необходимых переменных окружения
required_env_vars = ["TELEGRAM_TOKEN", "ADMIN_USER_ID", "REPO_URL", "GIT_USERNAME", "GIT_EMAIL", "GIT_TOKEN"]
missing_vars = [var for var in required_env_vars if not os.environ.get(var)]
if missing_vars:
    logger.error(f"Отсутствуют необходимые переменные окружения: {', '.join(missing_vars)}")
    exit(1)

# Создаем временные папки
IMAGES_FOLDER = os.path.join(tempfile.gettempdir(), "church_bot_images")
TEXT_FOLDER = os.path.join(tempfile.gettempdir(), "church_bot_text")
Path(IMAGES_FOLDER).mkdir(exist_ok=True)
Path(TEXT_FOLDER).mkdir(exist_ok=True)

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

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Обработчик команды /start"""
    user_id = update.effective_user.id
    
    if str(user_id) != ADMIN_USER_ID:
        await update.message.reply_text(
            "Извините, этот бот предназначен только для администратора."
        )
        return
        
    await update.message.reply_text(
        f"Привет, {update.effective_user.first_name}! 👋\n\n"
        "Я бот для обновления расписания богослужений на сайте прихода.\n\n"
        "Пришлите мне документ (DOCX или TXT) или изображение с расписанием, и я помогу его обработать и обновить на сайте."
    )

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Обработчик команды /help"""
    user_id = update.effective_user.id
    
    if str(user_id) != ADMIN_USER_ID:
        return
        
    await update.message.reply_text(
        "Инструкция по использованию бота:\n\n"
        "1. Отправьте мне документ (DOCX, TXT) или изображение с расписанием\n"
        "2. Я извлеку и обработаю текст\n"
        "3. Проверьте результат и подтвердите или отредактируйте его\n"
        "4. После подтверждения я обновлю сайт и отправлю изменения на GitHub\n\n"
        "Дополнительные команды:\n"
        "/start - Начать работу с ботом\n"
        "/help - Показать эту справку\n"
        "/cancel - Отменить текущую операцию\n"
        "/status - Проверить состояние бота"
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
        await update.message.reply_text("✅ Операция отменена. Все временные файлы удалены.")
    except Exception as e:
        logger.error(f"Ошибка при очистке временных файлов: {str(e)}")
        await update.message.reply_text(f"❌ Ошибка при очистке временных файлов: {str(e)}")

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
    
    # Проверка переменных окружения
    env_vars = {
        "ADMIN_USER_ID": ADMIN_USER_ID,
        "REPO_URL": REPO_URL,
        "GIT_USERNAME": GIT_USERNAME,
        "GIT_EMAIL": GIT_EMAIL,
        "GIT_TOKEN": "***" if GIT_TOKEN else None,
        "PROJECT_PATH": PROJECT_PATH,
        "INDEX_HTML_PATH": INDEX_HTML_PATH
    }
    
    status_message += "\n🔑 Переменные окружения:\n"
    for key, value in env_vars.items():
        status_icon = "✅" if value else "❌"
        # Не показываем значения конфиденциальных переменных
        if key in ["GIT_TOKEN", "ADMIN_USER_ID"]:
            display_value = "Установлено" if value else "Не установлено"
        else:
            display_value = value if value else "Не установлено"
        status_message += f"{status_icon} {key}: {display_value}\n"
    
    await update.message.reply_text(status_message)

async def handle_document(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Обработчик для документов (DOCX, TXT)"""
    user_id = update.effective_user.id
    
    if str(user_id) != ADMIN_USER_ID:
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
        
        await status_message.edit_text("✅ Текст обработан успешно!")
        
        # Отправляем результат и запрашиваем подтверждение
        # Исправлено: избегаем использования обратных косых черт внутри f-строк
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
        return
    
    status_message = await update.message.reply_text("📥 Получаю изображение... Пожалуйста, подождите.")
    
    try:
        # Загружаем файл
        photo = update.message.photo[-1]  # Берем изображение с наивысшим разрешением
        file = await context.bot.get_file(photo.file_id)
        file_path = os.path.join(IMAGES_FOLDER, f"image_{photo.file_id}.jpg")
        await file.download_to_drive(file_path)
        
        # Уведомляем о начале обработки
        await status_message.edit_text("✅ Изображение получено\n⏳ Распознаю текст...")
        
        try:
            # Import здесь, чтобы не требовать pytesseract для всех функций
            import pytesseract
            from PIL import Image
            
            # Устанавливаем путь к Tesseract для Docker
            pytesseract.pytesseract.tesseract_cmd = '/usr/bin/tesseract'
            
            # Открываем изображение
            image = Image.open(file_path)
            
            # Распознаем текст (русский язык)
            text = pytesseract.image_to_string(image, lang="rus")
            
            if not text:
                await status_message.edit_text("❌ Не удалось распознать текст с изображения.")
                return
                
            await status_message.edit_text("✅ Текст распознан успешно\n⏳ Обрабатываю текст...")
                
            # Обрабатываем текст
            text_processor.set_current(process_text(text))
            
            # Отправляем результат и запрашиваем подтверждение
            await status_message.edit_text("✅ Текст успешно распознан и обработан!")
            
            # Исправлено: избегаем использования обратных косых черт внутри f-строк
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
                
        except ImportError:
            await status_message.edit_text("❌ Ошибка: отсутствуют необходимые библиотеки для распознавания текста (pytesseract, PIL).")
            logger.error("Отсутствуют необходимые библиотеки: pytesseract, PIL")
            
    except Exception as e:
        logger.error(f"Ошибка при распознавании текста: {str(e)}\n{traceback.format_exc()}")
        await status_message.edit_text(f"❌ Произошла ошибка при распознавании текста: {str(e)}")

async def handle_edited_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Обработчик для отредактированного текста"""
    user_id = update.effective_user.id
    
    if str(user_id) != ADMIN_USER_ID:
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
        logger.error(f"Ошибка при обработке отредактированного текста: {str(e)}\n{traceback.format_exc()}")
        await update.message.reply_text(f"❌ Произошла ошибка при обработке текста: {str(e)}")

async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Обработчик нажатий на кнопки"""
    query = update.callback_query
    await query.answer()
    
    user_id = update.effective_user.id
    
    if str(user_id) != ADMIN_USER_ID:
        return
        
    if query.data == "confirm":
        confirmation_message = await query.edit_message_text("⏳ Подтверждено! Обновляю расписание на сайте...")
        
        try:
            final_text = text_processor.get_final_text()
            if not final_text:
                await confirmation_message.edit_text("❌ Ошибка: текст для обновления не найден.")
                return
                
            # Создаем HTML для расписания
            schedule_html = create_schedule_html(final_text)
            
            success = False
            
            # Пробуем сначала обновить непосредственно файл в монтированном томе
            if os.path.exists(INDEX_HTML_PATH):
                try:
                    update_index_html(INDEX_HTML_PATH, schedule_html)
                    await query.message.reply_text("✅ Файл index.html успешно обновлен локально!")
                    success = True
                except Exception as e:
                    logger.error(f"Ошибка при обновлении локального файла: {str(e)}\n{traceback.format_exc()}")
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
                    
                    await query.message.reply_text("✅ Расписание успешно обновлено и отправлено на GitHub!")
                else:
                    await query.message.reply_text("ℹ️ Изменений в расписании не обнаружено.")
            
            # Очищаем текущее состояние
            text_processor.reset()
            
            # Очищаем временные файлы
            for file in os.listdir(IMAGES_FOLDER):
                os.remove(os.path.join(IMAGES_FOLDER, file))
            for file in os.listdir(TEXT_FOLDER):
                os.remove(os.path.join(TEXT_FOLDER, file))
                
            await confirmation_message.edit_text("✅ Обновление расписания успешно завершено!")
                
        except Exception as e:
            logger.error(f"Ошибка при обновлении расписания: {str(e)}\n{traceback.format_exc()}")
            await confirmation_message.edit_text(f"❌ Произошла ошибка при обновлении расписания: {str(e)}")
            
    elif query.data == "edit":
        if text_processor.current_text is None:
            await query.edit_message_text("❌ Нет текста для редактирования.")
            return
            
        # Исправлено: избегаем использования обратных косых черт внутри f-строк
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
        text_processor.reset()
        
        await query.edit_message_text("❌ Операция отменена.")
        
        # Очищаем временные файлы
        for file in os.listdir(IMAGES_FOLDER):
            os.remove(os.path.join(IMAGES_FOLDER, file))
        for file in os.listdir(TEXT_FOLDER):
            os.remove(os.path.join(TEXT_FOLDER, file))

def main() -> None:
    """Запуск бота"""
    try:
        # Создаем временные папки, если их нет
        Path(IMAGES_FOLDER).mkdir(exist_ok=True)
        Path(TEXT_FOLDER).mkdir(exist_ok=True)
        
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
        logger.error(f"❌ Критическая ошибка при запуске бота: {str(e)}\n{traceback.format_exc()}")

if __name__ == "__main__":
    main()