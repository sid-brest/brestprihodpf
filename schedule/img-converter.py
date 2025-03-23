import re
import os
import platform
from PIL import Image
import pytesseract
from pathlib import Path
import shutil
from datetime import datetime
import logging

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
            r"\b(?:Январ[ь|я]|Феврал[ь|я]|Март[а]?|Апрел[ь|я]|Ма[й|я]|Июн[ь|я]|Июл[ь|я]|Август[а]?|Сентябр[ь|я]|Октябр[ь|я]|Ноябр[ь|я]|Декабр[ь|я])\s*,\s*(?:Понедельник|Вторник|Сред[а|у]|Четверг|Пятниц[а|у]|Суббот[а|у]|Воскресенье)\s*",
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


def create_schedule_html(text):
    """Преобразует текст расписания в HTML-структуру для index.html"""
    # Разбиваем текст на записи по тегу h3
    entries = re.split(r"<h3>(.*?)</h3>", text)
    entries = [e.strip() for e in entries if e.strip()]

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

    return "\n".join(rows)


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
        start_marker = "<!------------------------------ Insert Schedule ------------------------------>"
        end_marker = "<!------------------------------ Insert Schedule ------------------------------>"

        # Формируем новое содержимое
        schedule_section = f"{start_marker}\n{schedule_html}\n      {end_marker}"

        # Заменяем старую секцию на новую
        pattern = f"{start_marker}.*?{end_marker}"
        new_content = re.sub(pattern, schedule_section, content, flags=re.DOTALL)

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


def main():
    try:
        # Настраиваем логирование
        setup_logging()
        
        print(f"Операционная система: {OPERATING_SYSTEM}")
        print(f"Путь к Tesseract: {pytesseract.pytesseract.tesseract_cmd}")

        # Проверяем наличие Tesseract
        if not check_tesseract():
            return

        # Распознаем текст с изображений
        recognized_text = recognize_text_from_images()

        if not recognized_text:
            return

        logging.info("Обработка распознанного текста...")
        print("\nОбработка распознанного текста...")
        # Обрабатываем распознанный текст
        processed_text = process_text(recognized_text)

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
        print(f"Содержимое schedule_html:\n{schedule_html}")
        update_index_html(schedule_html)

        logging.info("✓ Все операции успешно завершены!")
        print("\n✓ Все операции успешно завершены!")

    except Exception as e:
        logging.error(f"❌ Произошла ошибка: {str(e)}")
        print(f"\n❌ Произошла ошибка: {str(e)}")


if __name__ == "__main__":
    main()