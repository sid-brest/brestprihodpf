# Телеграм бот для обновления расписания богослужений

Этот бот помогает автоматизировать процесс обновления расписания богослужений на сайте православного прихода святых благоверных князей Петра и Февронии Муромских г. Бреста.

## Функциональные возможности

- Получение файлов с расписанием (DOCX, TXT) через Telegram
- Распознавание текста с изображений через OCR
- Умное форматирование текста по заданным правилам
- Предварительный просмотр и редактирование распознанного текста
- Автоматическое обновление HTML-страницы сайта
- Синхронизация изменений с GitHub репозиторием
- Резервные копии обновляемых файлов

## Системные требования

- Ubuntu/Debian или другая совместимая Linux-система
- Docker и Docker Compose
- Интернет-соединение для работы с Telegram API и GitHub

## Быстрая установка

1. Клонируйте репозиторий:
   ```bash
   git clone https://github.com/sid-brest/brestprihodpf.git
   cd brestprihodpf/docker
   ```

2. Запустите скрипт установки:
   ```bash
   sudo ./setup.sh
   ```

3. Отредактируйте файл `.env` с настройками:
   ```bash
   nano .env
   ```

4. Запустите бота:
   ```bash
   ./start.sh
   ```

## Детальная инструкция по установке

### 1. Подготовка

1. Создайте телеграм бота с помощью [@BotFather](https://t.me/BotFather) и получите токен
2. Узнайте свой ID в Telegram с помощью [@userinfobot](https://t.me/userinfobot)
3. Создайте персональный токен доступа GitHub:
   - Перейдите в Settings -> Developer settings -> Personal access tokens -> Tokens (classic)
   - Нажмите "Generate new token" -> "Generate new token (classic)"
   - Дайте токену название и выберите права доступа `repo`
   - Скопируйте и сохраните токен

### 2. Установка Docker и зависимостей

Скрипт `setup.sh` автоматически выполнит следующие действия:

- Установит Docker Engine и Docker Compose
- Настроит автозапуск Docker при старте системы
- Добавит вашего пользователя в группу docker
- Создаст необходимые директории для хранения данных
- Настроит ограничения для логов, чтобы избежать переполнения диска
- Создаст резервные директории

При необходимости можно выполнить установку вручную:

```bash
# Обновление системы
sudo apt update && sudo apt upgrade -y

# Установка базовых зависимостей
sudo apt install -y apt-transport-https ca-certificates curl software-properties-common

# Добавление ключа и репозитория Docker
curl -fsSL https://download.docker.com/linux/ubuntu/gpg | sudo gpg --dearmor -o /usr/share/keyrings/docker-archive-keyring.gpg
echo "deb [arch=$(dpkg --print-architecture) signed-by=/usr/share/keyrings/docker-archive-keyring.gpg] https://download.docker.com/linux/ubuntu $(lsb_release -cs) stable" | sudo tee /etc/apt/sources.list.d/docker.list > /dev/null

# Установка Docker
sudo apt update
sudo apt install -y docker-ce docker-ce-cli containerd.io

# Установка Docker Compose
sudo curl -L "https://github.com/docker/compose/releases/latest/download/docker-compose-$(uname -s)-$(uname -m)" -o /usr/local/bin/docker-compose
sudo chmod +x /usr/local/bin/docker-compose

# Добавление пользователя в группу docker
sudo usermod -aG docker $USER
newgrp docker
```

### 3. Настройка переменных окружения

Заполните файл `.env` следующими параметрами:

```
# Токен бота телеграм
TELEGRAM_TOKEN=ваш_токен_бота

# ID администратора в телеграме (только этот пользователь сможет использовать бота)
ADMIN_USER_ID=ваш_telegram_id

# Данные для GitHub
REPO_URL=https://github.com/ваш_аккаунт/ваш_репозиторий.git
GIT_USERNAME=ваше_имя_пользователя
GIT_EMAIL=ваш_email@пример.com
GIT_TOKEN=ваш_персональный_токен_github

# Пути к файлам проекта
PROJECT_PATH=/app/project
INDEX_HTML_PATH=/app/project/index.html
```

### 4. Запуск и использование

1. Запустите бота с помощью скрипта `start.sh`:
   ```bash
   ./start.sh
   ```

2. После успешного запуска, откройте Telegram и найдите вашего бота по имени.

3. Отправьте команду `/start` для начала работы.

## Использование бота

### Команды бота

- `/start` - Инициализация бота
- `/help` - Показать справку по использованию
- `/cancel` - Отменить текущую операцию
- `/status` - Проверить состояние бота

### Процесс обновления расписания

1. Отправьте боту документ с расписанием (файл DOCX или TXT) или фотографию расписания
2. Бот распознает и обработает текст, затем покажет предварительный результат
3. Проверьте результат и:
   - Нажмите кнопку "Подтвердить", если всё правильно
   - Нажмите кнопку "Редактировать", если нужно внести изменения
4. При выборе редактирования отправьте отредактированный текст боту
5. После подтверждения бот обновит расписание на сайте и в GitHub репозитории

### Форматирование текста расписания

При редактировании текста используйте следующие правила:
- Обозначайте заголовки (дата и день недели) звездочками: `*14 апреля, Воскресенье*`
- Каждая строка с временем и описанием службы должна начинаться с новой строки
- Используйте формат времени `08:30` (с ведущими нулями для часов)

## Управление контейнерами

### Базовые команды Docker

- Просмотр списка контейнеров:
  ```bash
  docker ps
  ```

- Перезапуск бота:
  ```bash
  docker-compose restart church-bot
  ```

- Просмотр логов бота:
  ```bash
  docker logs church-schedule-bot
  ```

- Остановка всех контейнеров:
  ```bash
  docker-compose down
  ```

## Структура проекта

```
brestprihodpf/
├── backups/           # Резервные копии index.html
├── docker/            # Файлы Docker и скрипты
│   ├── bot/           # Исходный код бота
│   │   ├── bot.py     # Основной файл бота
│   │   ├── img_text_converter.py # Модуль обработки текста
│   │   └── requirements.txt # Зависимости Python
│   ├── docker-compose.yml # Конфигурация Docker Compose
│   ├── Dockerfile     # Конфигурация образа Docker
│   ├── setup.sh       # Скрипт установки
│   └── start.sh       # Скрипт запуска
└── index.html         # HTML файл с расписанием
```

## Устранение неполадок

### Проблемы с доступом к Docker

Если вы получаете ошибку "permission denied" при работе с Docker:

1. Проверьте, что вы добавлены в группу docker:
   ```bash
   groups | grep docker
   ```

2. Если группа присутствует, но ошибка остается, примените изменения без перезагрузки:
   ```bash
   newgrp docker
   ```

3. Альтернативно, запустите скрипт с sudo:
   ```bash
   sudo ./start.sh
   ```

### Проблемы с распознаванием текста

Если есть проблемы с распознаванием текста:

1. Проверьте установку Tesseract OCR:
   ```bash
   tesseract --version
   ```

2. Убедитесь, что русский языковой пакет установлен:
   ```bash
   tesseract --list-langs
   ```

3. При необходимости установите дополнительные языковые пакеты:
   ```bash
   sudo apt install tesseract-ocr-rus
   ```

## Обновление бота

Для обновления бота из репозитория:

```bash
cd brestprihodpf
git pull
cd docker
docker-compose down
docker-compose up -d
```

## Лицензия

Проект предоставляется "как есть" для использования приходом святых благоверных князей Петра и Февронии Муромских г. Бреста.