import re
import os
import platform
from PIL import Image
import pytesseract
from pathlib import Path
import shutil
from datetime import datetime
import logging
import docx  # Для работы с DOCX файлами

# Определяем операционную систему
OPERATING_SYSTEM = platform.system()

# Устанавливаем путь к Tesseract в зависимости от операционной системы
if OPERATING_SYSTEM == "Windows":
    pytesseract.pytesseract.tesseract_cmd = r"C:\Program Files\Tesseract-OCR\tesseract.exe"
else:  # Linux/Ubuntu
    pytesseract.pytesseract.tesseract_cmd = r"/usr/bin/tesseract"

# Пути к файлам и папкам
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PARENT_DIR = os.path.dirname(SCRIPT_DIR)
IMAGES_FOLDER = os.path.join(SCRIPT_DIR, "images")
TEXT_FOLDER = os.path.join(SCRIPT_DIR, "text")  # Новая папка для текстовых файлов
OUTPUT_FILE = os.path.join(SCRIPT_DIR, "result.txt")
INDEX_FILE = os.path.join(PARENT_DIR, "index.html")
LOG_DIR = os.path.join(SCRIPT_DIR, "logs")


# Настройка логирования
def setup_logging():
    """Настраивает логирование в файл с текущей датой в имени"""
    Path(LOG_DIR).mkdir(exist_ok=True)

    # Удаляем старые логи, если их больше 10
    log_files = sorted(Path(LOG_DIR).glob("log_*.txt"), key=os.path.getmtime)
    if len(log_files) > 10:
        for old_log in log_files[:-10]:
            os.remove(old_log)

    # Создаем новый лог-файл
    log_filename = f"log_{datetime.now().strftime('%Y-%m-%d')}.txt"
    log_filepath = os.path.join(LOG_DIR, log_filename)

    logging.basicConfig(
        filename=log_filepath,
        level=logging.INFO,
        format="%(asctime)s - %(levelname)s - %(message)s",
        encoding="utf-8",
    )
    logging.info("Логирование настроено.")
    logging.info(f"Операционная система: {OPERATING_SYSTEM}")
    logging.info(f"Путь к Tesseract: {pytesseract.pytesseract.tesseract_cmd}")


def check_files_in_folders():
    """Проверяет наличие файлов в папках images и text"""
    # Создаем папки, если они не существуют
    Path(IMAGES_FOLDER).mkdir(exist_ok=True)
    Path(TEXT_FOLDER).mkdir(exist_ok=True)
    
    # Получаем списки файлов
    image_files = [
        f for f in os.listdir(IMAGES_FOLDER) 
        if f.lower().endswith((".png", ".jpg", ".jpeg"))
    ]
    
    text_files = [
        f for f in os.listdir(TEXT_FOLDER)
        if f.lower().endswith((".txt", ".docx"))
    ]
    
    return image_files, text_files


def extract_text_from_txt(file_path):
    """Извлекает текст из TXT файла"""
    try:
        with open(file_path, 'r', encoding='utf-8-sig') as file:
            return file.read()
    except UnicodeDecodeError:
        # Пробуем другие кодировки, если utf-8 не работает
        try:
            with open(file_path, 'r', encoding='cp1251') as file:
                return file.read()
        except Exception as e:
            logging.error(f"Не удалось прочитать файл {file_path}: {str(e)}")
            return ""


def extract_text_from_docx(file_path):
    """Извлекает текст из DOCX файла"""
    try:
        doc = docx.Document(file_path)
        text = "\n".join([paragraph.text for paragraph in doc.paragraphs])
        return text
    except Exception as e:
        logging.error(f"Не удалось прочитать файл {file_path}: {str(e)}")
        return ""


def read_text_from_files():
    """Читает текст из файлов в папке text"""
    extracted_text = ""
    
    # Получаем список текстовых файлов
    text_files = [
        f for f in os.listdir(TEXT_FOLDER)
        if f.lower().endswith((".txt", ".docx"))
    ]
    
    if not text_files:
        logging.warning("В папке text нет текстовых файлов.")
        print("В папке text нет текстовых файлов.")
        print(f"Пожалуйста, добавьте файлы DOCX или TXT в папку: {TEXT_FOLDER}")
        return ""
    
    logging.info(f"Найдено текстовых файлов: {len(text_files)}")
    print(f"Найдено текстовых файлов: {len(text_files)}")
    print("Начинаю чтение текстовых файлов...")
    
    # Обрабатываем каждый файл
    for i, text_file in enumerate(text_files, 1):
        file_path = os.path.join(TEXT_FOLDER, text_file)
        try:
            logging.info(f"Обработка файла {i}/{len(text_files)}: {text_file}")
            print(f"Обработка файла {i}/{len(text_files)}: {text_file}")
            
            # Определяем формат и извлекаем текст
            if text_file.lower().endswith(".txt"):
                text = extract_text_from_txt(file_path)
            elif text_file.lower().endswith(".docx"):
                text = extract_text_from_docx(file_path)
            
            extracted_text += text + "\n"
            logging.info(f"✓ Успешно извлечен текст из файла: {text_file}")
            print(f"✓ Успешно извлечен текст из файла: {text_file}")
            
        except Exception as e:
            logging.error(f"❌ Ошибка при обработке файла {text_file}: {str(e)}")
            print(f"❌ Ошибка при обработке файла {text_file}: {str(e)}")
            continue
    
    return extracted_text


def recognize_text_from_images():
    """Распознает текст со всех изображений в указанной папке"""
    recognized_text = ""

    # Создаем папку images, если она не существует
    Path(IMAGES_FOLDER).mkdir(exist_ok=True)

    # Получаем список всех файлов изображений в папке
    image_files = [
        f
        for f in os.listdir(IMAGES_FOLDER)
        if f.lower().endswith((".png", ".jpg", ".jpeg"))
    ]

    if not image_files:
        logging.warning("В папке images нет изображений.")
        print("В папке images нет изображений.")
        print(f"Пожалуйста, добавьте изображения в папку: {IMAGES_FOLDER}")
        return ""

    logging.info(f"Найдено изображений: {len(image_files)}")
    print(f"Найдено изображений: {len(image_files)}")
    print("Начинаю распознавание текста...")

    # Обрабатываем каждое изображение
    for i, image_file in enumerate(image_files, 1):
        image_path = os.path.join(IMAGES_FOLDER, image_file)
        try:
            logging.info(f"Обработка изображения {i}/{len(image_files)}: {image_file}")
            print(f"Обработка изображения {i}/{len(image_files)}: {image_file}")

            # Открываем изображение
            image = Image.open(image_path)

            # Распознаем текст (указываем русский язык)
            text = pytesseract.image_to_string(image, lang="rus")

            recognized_text += text + "\n"
            logging.info(f"✓ Успешно распознан текст из файла: {image_file}")
            print(f"✓ Успешно распознан текст из файла: {image_file}")

        except Exception as e:
            logging.error(f"❌ Ошибка при обработке файла {image_file}: {str(e)}")
            print(f"❌ Ошибка при обработке файла {image_file}: {str(e)}")
            continue

    return recognized_text


def process_text(input_text):
    """Обрабатывает распознанный текст согласно заданным правилам"""

    # Remove rows that contain "Расписание Богослужений" or "Прихода"
    input_text = re.sub(r"Расписание Богослужений.*?\n|Прихода.*?\n", "", input_text)

    # Remove "(" and ")" in rows that contain the day of the week
    input_text = re.sub(
        r"(\b[а-я]+)\s*\(\s*([а-я]+)\s*\)", r"\1, \2", input_text, flags=re.IGNORECASE
    )

    # Replace time format from "hh-mm" to "hh:mm"
    input_text = re.sub(r"(\d{1,2})-(\d{2})(?!\d)", r"\1:\2 -", input_text)

    # Replace time format from "h:mm" to "hh:mm"
    input_text = re.sub(r"(?<!\d)(\d):(\d{2})(?!\d)", r"0\1:\2", input_text)

    # Remove empty rows and more than one spaces
    input_text = re.sub(r"\n\s*\n", "\n", input_text)
    input_text = re.sub(r"[ ]{2,}", " ", input_text)

    # Split input text into rows
    rows = input_text.strip().split("\n")

    # Define output text variable
    output_text = ""
    prev_was_h3 = False  # Flag to track if previous line was h3

    # Loop through rows
    for row in rows:
        # Check if row contains month and day name
        if re.search(
            r"\b(?:Январ[ья]|Феврал[ья]|Марта?|Апрел[ья]|Ма[йя]|Июн[ья]|Июл[ья]|Августа?|Сентябр[ья]|Октябр[ья]|Ноябр[ья]|Декабр[ья])\s*,\s*(?:Понедельник|Вторник|Сред[ау]|Четверг|Пятниц[ау]|Суббот[ау]|Воскресенье)\s*",
            row,
            flags=re.IGNORECASE,
        ):
            output_text += f"<h3>{row}</h3>\n"
            prev_was_h3 = True
        else:
            if prev_was_h3:
                # After h3, just add a single br
                output_text += f"<br />{row.strip()}\n"
                prev_was_h3 = False
            else:
                # Add empty line before text if it starts with a time
                if re.match(r"\d{1,2}:\d{2}", row.strip()):
                    output_text += f"<br /><br />{row.strip()}\n"
                # Add empty line before standalone text (without time pattern)
                elif not re.match(r"\d{1,2}:\d{2}.*", row.strip()):
                    output_text += f"<br /><br />{row.strip()}\n"
                else:
                    output_text += f"<br />{row.strip()}\n"

    # Remove spaces after <br /> and <h3> tag
    output_text = re.sub(r"<br />\s*", "<br />", output_text)
    output_text = re.sub(r"<h3>\s*", "<h3>", output_text)

    return output_text


MONTHS_GENITIVE = {
    "января": 1, "февраля": 2, "марта": 3, "апреля": 4, "мая": 5, "июня": 6,
    "июля": 7, "августа": 8, "сентября": 9, "октября": 10, "ноября": 11, "декабря": 12,
}
MONTH_NAME_BY_NUMBER = {number: name for name, number in MONTHS_GENITIVE.items()}
TIME_LINE_RE = re.compile(r"^(\d{1,2}:\d{2})\s*[-–—]\s*(.+)$")
DATE_HEADING_RE = re.compile(r"^(\d{1,2})\s+([а-яё]+)\s*,\s*([а-яё]+)\s*$", re.IGNORECASE)


def guess_year(month: int) -> int:
    """Год расписания: текущий, с поправкой на стык декабрь/январь."""
    today = datetime.now()
    if month == 1 and today.month == 12:
        return today.year + 1
    if month == 12 and today.month == 1:
        return today.year - 1
    return today.year


def parse_day(heading: str, lines: list[str]) -> dict:
    """Разбирает заголовок дня ("7 ноября, суббота") и строки расписания.

    Строка со временем ("08:30 - ...") становится записью; строка без времени,
    начинающаяся со строчной буквы, продолжает предыдущую запись (перенос OCR);
    остальные строки без времени (память святого, родительская суббота) - заметки.
    """
    match = DATE_HEADING_RE.match(heading.strip())
    if not match:
        raise ValueError(f"Не удалось разобрать дату: {heading!r}")
    day = int(match.group(1))
    month = MONTHS_GENITIVE.get(match.group(2).lower())
    if not month:
        raise ValueError(f"Неизвестный месяц в заголовке: {heading!r}")
    weekday = match.group(3).lower()

    items: list[dict] = []
    for line in lines:
        time_match = TIME_LINE_RE.match(line)
        if time_match:
            items.append({"time": time_match.group(1), "text": time_match.group(2).strip()})
            continue
        last = items[-1] if items else None
        if re.match(r"^[а-яё]", line) and last and "time" in last:
            last["text"] = f"{last['text']} {line}"
            continue
        items.append({"note": line})

    return {
        "day": day,
        "month": month,
        "weekday": weekday,
        "iso": f"{guess_year(month)}-{month:02d}-{day:02d}",
        "items": items,
    }


def render_day(day: dict) -> str:
    """HTML-карточка одного дня."""
    rows = []
    for item in day["items"]:
        if "time" in item:
            rows.append(
                f'              <li class="schedule-item"><time>{item["time"]}</time><span>{item["text"]}</span></li>'
            )
        else:
            rows.append(f'              <li class="schedule-note">{item["note"]}</li>')
    rows_html = "\n".join(rows)
    month_name = MONTH_NAME_BY_NUMBER[day["month"]]
    return f"""        <div class="col-lg-3 col-sm-6 schedule-col">
          <article class="schedule-day" data-date="{day['iso']}">
            <h3 class="schedule-date">{day['day']} {month_name} <span class="schedule-weekday">{day['weekday']}</span></h3>
            <ul class="schedule-list">
{rows_html}
            </ul>
          </article>
        </div>"""


def render_period(days: list[dict]) -> str:
    """Подзаголовок с периодом расписания, например "7 – 15 ноября"."""
    first, last = days[0], days[-1]
    if first["month"] == last["month"]:
        text = f"{first['day']} – {last['day']} {MONTH_NAME_BY_NUMBER[first['month']]}"
    else:
        text = (
            f"{first['day']} {MONTH_NAME_BY_NUMBER[first['month']]} – "
            f"{last['day']} {MONTH_NAME_BY_NUMBER[last['month']]}"
        )
    return f'      <p class="schedule-period">{text}</p>'


def create_schedule_html(text: str) -> str:
    """Преобразует обработанный текст (<h3>дата</h3> + строки через <br />) в карточки расписания."""
    parts = re.split(r"<h3>(.*?)</h3>", text)
    days = []
    for i in range(1, len(parts) - 1, 2):
        heading = parts[i]
        lines = [line.strip() for line in re.split(r"<br\s*/?>", parts[i + 1]) if line.strip()]
        days.append(parse_day(heading, lines))
    if not days:
        raise ValueError("В тексте не найдено ни одного дня расписания")

    cards = "\n".join(render_day(day) for day in days)
    return f'{render_period(days)}\n      <div class="row schedule-grid">\n{cards}\n      </div>'


def update_index_html(schedule_html):
    try:
        # Создаем резервную копию
        backup_dir = os.path.join(PARENT_DIR, "backups")
        Path(backup_dir).mkdir(exist_ok=True)

        # Удаляем старые резервные копии, если их больше 10
        backup_files = sorted(
            Path(backup_dir).glob("index.html.backup_*"), key=os.path.getmtime
        )
        if len(backup_files) > 10:
            for old_backup in backup_files[:-10]:
                os.remove(old_backup)

        # Создаем новую резервную копию
        backup_file = os.path.join(
            backup_dir, f"index.html.backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        )
        shutil.copy2(INDEX_FILE, backup_file)
        logging.info(f"✓ Создана резервная копия index.html: {backup_file}")
        print(f"✓ Создана резервная копия index.html: {backup_file}")

        # Читаем содержимое файла
        with open(INDEX_FILE, "r", encoding="utf-8") as file:
            content = file.read()

        # Находим секцию расписания и заменяем её
        start_marker = "<!-- Insert Schedule: start -->"
        end_marker = "<!-- Insert Schedule: end -->"

        # Формируем новое содержимое
        schedule_section = f"{start_marker}\n{schedule_html}\n      {end_marker}"

        # Заменяем старую секцию на новую (маркеры экранируем; замена через lambda,
        # чтобы обратные слэши в тексте расписания не трактовались как спецпоследовательности)
        pattern = f"{re.escape(start_marker)}.*?{re.escape(end_marker)}"
        new_content, replaced = re.subn(pattern, lambda _m: schedule_section, content, flags=re.DOTALL)
        if replaced != 1:
            raise RuntimeError(
                f"Маркеры расписания не найдены или найдены несколько раз ({replaced}). index.html не изменён."
            )

        # Записываем обновленное содержимое
        with open(INDEX_FILE, "w", encoding="utf-8") as file:
            file.write(new_content)

        logging.info("✓ Файл index.html успешно обновлен")
        print(f"✓ Файл index.html успешно обновлен")

    except Exception as e:
        logging.error(f"❌ Ошибка при обновлении index.html: {str(e)}")
        print(f"❌ Ошибка при обновлении index.html: {str(e)}")
        if "backup_file" in locals():
            logging.info(f"Восстанавливаем из резервной копии: {backup_file}")
            print(f"Восстанавливаем из резервной копии: {backup_file}")
            shutil.copy2(backup_file, INDEX_FILE)


def check_tesseract():
    """Проверяет наличие и версию Tesseract OCR"""
    try:
        if OPERATING_SYSTEM == "Windows":
            if not os.path.exists(pytesseract.pytesseract.tesseract_cmd):
                logging.error("❌ Ошибка: Tesseract-OCR не найден!")
                print("❌ Ошибка: Tesseract-OCR не найден!")
                print(
                    "Пожалуйста, установите Tesseract-OCR и убедитесь, что путь корректный:"
                )
                print(pytesseract.pytesseract.tesseract_cmd)
                return False
        
        # Проверка версии Tesseract
        try:
            tesseract_version = pytesseract.get_tesseract_version()
            logging.info(f"Tesseract версия: {tesseract_version}")
            print(f"Tesseract версия: {tesseract_version}")
            
            # Проверка наличия русского языкового пакета
            langs = pytesseract.get_languages()
            if 'rus' not in langs:
                logging.error("❌ Ошибка: Русский языковой пакет для Tesseract не найден!")
                print("❌ Ошибка: Русский языковой пакет для Tesseract не найден!")
                print("Установите языковой пакет для русского языка (rus)")
                if OPERATING_SYSTEM == "Linux":
                    print("Для Ubuntu: sudo apt-get install tesseract-ocr-rus")
                return False
            
            logging.info(f"Доступные языки Tesseract: {', '.join(langs)}")
            return True
            
        except Exception as e:
            logging.error(f"❌ Ошибка при проверке Tesseract: {str(e)}")
            print(f"❌ Ошибка при проверке Tesseract: {str(e)}")
            return False
            
    except Exception as e:
        logging.error(f"❌ Ошибка при проверке Tesseract: {str(e)}")
        print(f"❌ Ошибка при проверке Tesseract: {str(e)}")
        return False


def get_user_choice(image_files, text_files):
    """Запрашивает у пользователя, какой источник использовать"""
    print("\nНайдены файлы для обработки:")
    
    if image_files:
        print(f"1. Изображения в папке '{IMAGES_FOLDER}' ({len(image_files)} файлов)")
    
    if text_files:
        print(f"2. Текстовые файлы в папке '{TEXT_FOLDER}' ({len(text_files)} файлов)")
        
    if image_files and text_files:
        valid_choices = ['1', '2']
        choice = ""
        while choice not in valid_choices:
            choice = input("\nВыберите источник данных (1 - изображения, 2 - текстовые файлы): ")
            if choice not in valid_choices:
                print("Неверный выбор. Пожалуйста, введите 1 или 2.")
        
        return int(choice)
    elif image_files:
        print("\nБудут использованы файлы изображений.")
        return 1
    else:
        print("\nБудут использованы текстовые файлы.")
        return 2


def main():
    try:
        # Настраиваем логирование
        setup_logging()
        
        print(f"Операционная система: {OPERATING_SYSTEM}")
        
        # Проверяем наличие файлов в обеих папках
        image_files, text_files = check_files_in_folders()
        
        if not image_files and not text_files:
            logging.warning("Не найдено файлов для обработки ни в images, ни в text папках")
            print("\nНе найдено файлов для обработки!")
            print(f"Пожалуйста, добавьте изображения в папку '{IMAGES_FOLDER}'")
            print(f"или текстовые файлы (docx, txt) в папку '{TEXT_FOLDER}'")
            return
            
        # Запрашиваем выбор источника, если доступно несколько
        source_choice = get_user_choice(image_files, text_files)
        
        # Получаем текст в зависимости от выбора пользователя
        if source_choice == 1:
            # Проверяем наличие Tesseract для распознавания изображений
            if not check_tesseract():
                return
                
            extracted_text = recognize_text_from_images()
        else:
            extracted_text = read_text_from_files()
            
        if not extracted_text:
            print("Не удалось извлечь текст из выбранных файлов.")
            return

        logging.info("Обработка извлеченного текста...")
        print("\nОбработка извлеченного текста...")
        # Обрабатываем извлеченный текст
        processed_text = process_text(extracted_text)

        # Записываем результат в файл
        with open(OUTPUT_FILE, "w", encoding="utf-8") as file:
            file.write(processed_text)

        logging.info(f"✓ Результат сохранен в файл: {OUTPUT_FILE}")
        print(f"✓ Результат сохранен в файл: {OUTPUT_FILE}")

        # Создаем HTML-структуру для расписания
        logging.info("Создание HTML-структуры расписания...")
        print("\nСоздание HTML-структуры расписания...")
        schedule_html = create_schedule_html(processed_text)

        # Обновляем index.html
        logging.info("Обновление index.html...")
        print("\nОбновление index.html...")
        update_index_html(schedule_html)

        logging.info("✓ Все операции успешно завершены!")
        print("\n✓ Все операции успешно завершены!")

    except Exception as e:
        logging.error(f"❌ Произошла ошибка: {str(e)}")
        print(f"\n❌ Произошла ошибка: {str(e)}")


if __name__ == "__main__":
    main()