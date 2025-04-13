"""
Модуль для обработки текста расписания богослужений и обновления сайта.
Включает функции для извлечения текста из различных форматов,
обработки его согласно заданным правилам и обновления HTML страницы.
"""
import re
import os
import logging
import shutil
from pathlib import Path
from datetime import datetime
import traceback
import docx  # Для работы с DOCX файлами

# Настройка логирования
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
    handlers=[
        logging.FileHandler("img_text_converter.log", encoding="utf-8"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

def extract_text_from_txt(file_path):
    """
    Извлекает текст из TXT файла с учетом различных кодировок.
    
    Args:
        file_path (str): Путь к TXT файлу
        
    Returns:
        str: Извлеченный текст или пустая строка в случае ошибки
    """
    encodings = ['utf-8', 'cp1251', 'koi8-r', 'latin-1']
    
    for encoding in encodings:
        try:
            with open(file_path, 'r', encoding=encoding) as file:
                text = file.read()
                logger.info(f"Успешно прочитан файл {file_path} в кодировке {encoding}")
                return text
        except UnicodeDecodeError:
            continue
        except Exception as e:
            logger.error(f"Ошибка при чтении файла {file_path}: {str(e)}")
    
    logger.error(f"Не удалось прочитать файл {file_path} ни в одной из кодировок")
    return ""


def extract_text_from_docx(file_path):
    """
    Извлекает текст из DOCX файла.
    
    Args:
        file_path (str): Путь к DOCX файлу
        
    Returns:
        str: Извлеченный текст или пустая строка в случае ошибки
    """
    try:
        doc = docx.Document(file_path)
        text = "\n".join([paragraph.text for paragraph in doc.paragraphs if paragraph.text.strip()])
        logger.info(f"Успешно извлечен текст из DOCX файла {file_path}")
        return text
    except Exception as e:
        logger.error(f"Ошибка при чтении DOCX файла {file_path}: {str(e)}\n{traceback.format_exc()}")
        return ""


def process_text(input_text):
    """
    Обрабатывает распознанный текст согласно заданным правилам.
    
    Эта функция выполняет следующие преобразования:
    1. Удаляет строки с "Расписание Богослужений" или "Прихода"
    2. Заменяет формат времени с "hh-mm" на "hh:mm -"
    3. Добавляет ведущий ноль к часам, если формат "h:mm"
    4. Удаляет пустые строки и лишние пробелы
    5. Форматирует заголовки с датами и днями недели в теги <h3>
    6. Добавляет теги <br /> к остальным строкам
    
    Args:
        input_text (str): Исходный текст для обработки
        
    Returns:
        str: Обработанный текст с HTML-тегами
    """
    try:
        # Проверка на пустой ввод
        if not input_text or not input_text.strip():
            logger.error("Получен пустой текст для обработки")
            return ""
            
        # Предварительная очистка текста от лишних пробелов и переносов строк
        input_text = input_text.strip()
        
        # Удаляем строки, содержащие "Расписание Богослужений" или "Прихода"
        input_text = re.sub(r"Расписание Богослужений.*?\n|Прихода.*?\n", "", input_text)

        # Заменяем скобки на запятую в строках, содержащих день недели
        input_text = re.sub(
            r"(\b[а-я]+)\s*\(\s*([а-я]+)\s*\)", r"\1, \2", input_text, flags=re.IGNORECASE
        )

        # Заменяем формат времени с "hh-mm" на "hh:mm -"
        input_text = re.sub(r"(\d{1,2})-(\d{2})(?!\d)", r"\1:\2 -", input_text)

        # Добавляем ведущий ноль к часам, если формат "h:mm"
        input_text = re.sub(r"(?<!\d)(\d):(\d{2})(?!\d)", r"0\1:\2", input_text)

        # Удаляем пустые строки и лишние пробелы
        input_text = re.sub(r"\n\s*\n", "\n", input_text)
        input_text = re.sub(r"[ ]{2,}", " ", input_text)

        # Разбиваем текст на строки
        rows = input_text.strip().split("\n")

        # Инициализируем выходной текст
        output_text = ""
        prev_was_h3 = False  # Флаг для отслеживания, была ли предыдущая строка заголовком h3

        # Обрабатываем каждую строку
        for row in rows:
            row = row.strip()
            if not row:  # Пропускаем пустые строки
                continue
                
            # Проверяем, содержит ли строка месяц и день недели (формат заголовка)
            if re.search(
                r"\b(?:Январ[ь|я]|Феврал[ь|я]|Март[а]?|Апрел[ь|я]|Ма[й|я]|Июн[ь|я]|Июл[ь|я]|Август[а]?|Сентябр[ь|я]|Октябр[ь|я]|Ноябр[ь|я]|Декабр[ь|я])\s*,\s*(?:Понедельник|Вторник|Сред[а|у]|Четверг|Пятниц[а|у]|Суббот[а|у]|Воскресенье)\s*",
                row,
                flags=re.IGNORECASE,
            ):
                output_text += f"<h3>{row}</h3>\n"
                prev_was_h3 = True
            else:
                if prev_was_h3:
                    # После заголовка h3 добавляем одиночный br
                    output_text += f"<br />{row}\n"
                    prev_was_h3 = False
                else:
                    # Добавляем двойной br перед текстом, начинающимся с времени
                    if re.match(r"\d{1,2}:\d{2}", row):
                        output_text += f"<br /><br />{row}\n"
                    # Добавляем двойной br перед отдельно стоящим текстом (без шаблона времени)
                    elif not re.match(r"\d{1,2}:\d{2}.*", row):
                        output_text += f"<br /><br />{row}\n"
                    else:
                        output_text += f"<br />{row}\n"

        # Удаляем пробелы после тегов <br /> и <h3>
        output_text = re.sub(r"<br />\s*", "<br />", output_text)
        output_text = re.sub(r"<h3>\s*", "<h3>", output_text)
        
        logger.info("Текст успешно обработан")
        return output_text
        
    except Exception as e:
        logger.error(f"Ошибка при обработке текста: {str(e)}\n{traceback.format_exc()}")
        return input_text  # Возвращаем исходный текст в случае ошибки


def create_schedule_html(text):
    """
    Преобразует текст расписания в HTML-структуру для index.html.
    
    Функция разбивает текст по тегам <h3> и группирует записи по 4 для каждого ряда.
    
    Args:
        text (str): Обработанный текст с HTML тегами
        
    Returns:
        str: HTML-структура для вставки в index.html
    """
    try:
        if not text or not text.strip():
            logger.error("Получен пустой текст для создания HTML")
            return ""
            
        # Разбиваем текст на записи по тегу h3
        entries = re.split(r"<h3>(.*?)</h3>", text)
        entries = [e.strip() for e in entries if e.strip()]
        
        if not entries:
            logger.error("Не найдены записи с тегами h3 в тексте")
            return ""

        # Группируем записи по 4 (для каждого ряда)
        rows = []
        current_row = []

        for i in range(0, len(entries), 2):
            if i + 1 < len(entries):
                date = entries[i]
                content = entries[i + 1]

                entry_html = f"""
        <div class="col-lg-3 col-sm-6 probootstrap-animate">
          <div class="form-group">
            <h3>{date}</h3>
            {content}
          </div>
        </div>"""

                current_row.append(entry_html)

                if len(current_row) == 4:
                    rows.append(
                        "\n      <!------------------------------ row ------------------------------>"
                        f'\n      <div class="row">{"".join(current_row)}\n      </div>\n'
                    )
                    current_row = []

        # Добавляем оставшиеся записи, если есть
        if current_row:
            rows.append(
                "\n      <!------------------------------ row ------------------------------>"
                f'\n      <div class="row">{"".join(current_row)}\n      </div>\n'
            )

        logger.info(f"HTML-структура успешно создана: {len(entries)//2} записей, {len(rows)} рядов")
        return "\n".join(rows)
        
    except Exception as e:
        logger.error(f"Ошибка при создании HTML-структуры: {str(e)}\n{traceback.format_exc()}")
        return ""


def update_index_html(index_path, schedule_html):
    """
    Обновляет файл index.html с новым расписанием.
    
    Функция создает резервную копию исходного файла, затем обновляет секцию 
    расписания между указанными маркерами.
    
    Args:
        index_path (str): Путь к файлу index.html
        schedule_html (str): HTML-структура расписания для вставки
        
    Returns:
        bool: True в случае успеха, False в случае ошибки
    """
    try:
        # Проверяем существование файла
        if not os.path.exists(index_path):
            logger.error(f"Файл index.html не найден по пути: {index_path}")
            return False
            
        # Проверяем, что HTML не пустой
        if not schedule_html or not schedule_html.strip():
            logger.error("Получен пустой HTML для обновления")
            return False
            
        # Создаем резервную копию
        backup_dir = os.path.join(os.path.dirname(index_path), "backups")
        Path(backup_dir).mkdir(exist_ok=True)

        # Удаляем старые резервные копии, если их больше 10
        backup_files = sorted(
            Path(backup_dir).glob("index.html.backup_*"), key=os.path.getmtime
        )
        if len(backup_files) > 10:
            for old_backup in backup_files[:-10]:
                os.remove(old_backup)
                logger.info(f"Удалена старая резервная копия: {old_backup}")

        # Создаем новую резервную копию
        backup_file = os.path.join(
            backup_dir, f"index.html.backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        )
        shutil.copy2(index_path, backup_file)
        logger.info(f"Создана резервная копия index.html: {backup_file}")

        # Читаем содержимое файла
        with open(index_path, "r", encoding="utf-8") as file:
            content = file.read()

        # Находим секцию расписания и заменяем её
        start_marker = "<!------------------------------ Insert Schedule ------------------------------>"
        end_marker = "<!------------------------------ Insert Schedule ------------------------------>"

        # Проверяем наличие маркеров
        if start_marker not in content or content.count(start_marker) != 2:
            logger.error(f"Маркеры начала/конца секции расписания не найдены или некорректны в файле: {index_path}")
            return False

        # Формируем новое содержимое
        schedule_section = f"{start_marker}\n{schedule_html}\n      {end_marker}"

        # Заменяем старую секцию на новую
        pattern = f"{start_marker}.*?{end_marker}"
        new_content = re.sub(pattern, schedule_section, content, flags=re.DOTALL)

        # Проверяем, что содержимое изменилось
        if new_content == content:
            logger.info("Содержимое файла не изменилось")
            return True

        # Записываем обновленное содержимое
        with open(index_path, "w", encoding="utf-8") as file:
            file.write(new_content)

        logger.info(f"Файл index.html успешно обновлен: {index_path}")
        return True

    except Exception as e:
        logger.error(f"Ошибка при обновлении index.html: {str(e)}\n{traceback.format_exc()}")
        
        # Пытаемся восстановить из резервной копии, если она была создана
        if 'backup_file' in locals() and os.path.exists(backup_file):
            try:
                shutil.copy2(backup_file, index_path)
                logger.info(f"Восстановлен файл из резервной копии: {backup_file}")
            except Exception as restore_error:
                logger.error(f"Ошибка при восстановлении из резервной копии: {str(restore_error)}")
                
        return False


def recognize_text_from_image(image_path, lang="rus"):
    """
    Распознает текст с изображения с помощью Tesseract OCR.
    
    Args:
        image_path (str): Путь к изображению
        lang (str): Язык для распознавания (по умолчанию "rus" - русский)
        
    Returns:
        str: Распознанный текст или пустая строка в случае ошибки
    """
    try:
        # Импортируем здесь, чтобы не требовать pytesseract для всех функций
        import pytesseract
        from PIL import Image
        
        # Проверяем путь к Tesseract на разных платформах
        if os.name == 'nt':  # Windows
            if os.path.exists(r"C:\Program Files\Tesseract-OCR\tesseract.exe"):
                pytesseract.pytesseract.tesseract_cmd = r"C:\Program Files\Tesseract-OCR\tesseract.exe"
            elif os.path.exists(r"C:\Program Files (x86)\Tesseract-OCR\tesseract.exe"):
                pytesseract.pytesseract.tesseract_cmd = r"C:\Program Files (x86)\Tesseract-OCR\tesseract.exe"
        else:  # Linux/Mac
            pytesseract.pytesseract.tesseract_cmd = '/usr/bin/tesseract'
        
        # Проверяем существование файла
        if not os.path.exists(image_path):
            logger.error(f"Файл изображения не найден: {image_path}")
            return ""
        
        # Открываем изображение
        image = Image.open(image_path)
        
        # Предобработка изображения (опционально)
        # image = image.convert('L')  # Преобразование в оттенки серого
        
        # Распознаем текст
        text = pytesseract.image_to_string(image, lang=lang)
        
        if not text.strip():
            logger.warning(f"Не удалось распознать текст с изображения: {image_path}")
            return ""
            
        logger.info(f"Текст успешно распознан с изображения: {image_path}")
        return text
        
    except ImportError as e:
        logger.error(f"Отсутствуют необходимые библиотеки для распознавания текста: {str(e)}")
        return ""
    except Exception as e:
        logger.error(f"Ошибка при распознавании текста с изображения: {str(e)}\n{traceback.format_exc()}")
        return ""


def get_version():
    """
    Возвращает информацию о версии модуля.
    
    Returns:
        dict: Словарь с информацией о версии
    """
    return {
        "name": "img_text_converter",
        "version": "1.2.0",
        "date": "2025-04-13",
        "description": "Модуль для обработки текста расписания богослужений и обновления сайта"
    }


# Для тестирования модуля при непосредственном запуске
if __name__ == "__main__":
    print("Модуль img_text_converter")
    print(f"Версия: {get_version()['version']}")
    print("Этот модуль предназначен для использования в качестве библиотеки.")
    print("Для тестирования функций используйте отдельный скрипт.")