FROM python:3.11-slim

# Установка аргументов сборки
ARG DEBIAN_FRONTEND=noninteractive
ARG TZ=Europe/Minsk

# Установка рабочей директории
WORKDIR /app

# Установка необходимых системных зависимостей
RUN apt-get update && apt-get install -y --no-install-recommends \
    tesseract-ocr \
    tesseract-ocr-rus \
    git \
    wget \
    curl \
    ca-certificates \
    tzdata \
    locales \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/* \
    && ln -snf /usr/share/zoneinfo/$TZ /etc/localtime \
    && echo $TZ > /etc/timezone \
    && sed -i -e 's/# ru_RU.UTF-8 UTF-8/ru_RU.UTF-8 UTF-8/' /etc/locale.gen \
    && dpkg-reconfigure --frontend=noninteractive locales \
    && update-locale LANG=ru_RU.UTF-8

# Настройка переменных окружения
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    LANG=ru_RU.UTF-8 \
    LC_ALL=ru_RU.UTF-8 \
    TZ=$TZ

# Копирование requirements.txt и установка зависимостей Python
COPY bot/requirements.txt .
RUN pip install --no-cache-dir --upgrade pip setuptools wheel \
    && pip install --no-cache-dir -r requirements.txt

# Создание пользователя без прав root для повышения безопасности
RUN groupadd -r botuser && useradd -r -g botuser -m -d /home/botuser botuser \
    && mkdir -p /tmp/images /tmp/text /app/logs \
    && chown -R botuser:botuser /tmp/images /tmp/text /app/logs

# Копирование скриптов бота
COPY bot/ .
RUN chown -R botuser:botuser /app

# Переключение на непривилегированного пользователя
USER botuser

# Проверка работоспособности Tesseract
RUN tesseract --version

# Точка входа и команда запуска
ENTRYPOINT ["python"]
CMD ["bot.py"]