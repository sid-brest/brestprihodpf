FROM python:3.11-slim

# Установка аргументов сборки
ARG DEBIAN_FRONTEND=noninteractive
ARG TZ=Europe/Minsk

# Установка рабочей директории
WORKDIR /app

# Настройка повторных попыток для APT
RUN mkdir -p /etc/apt/apt.conf.d && \
    echo 'Acquire::Retries "5";' > /etc/apt/apt.conf.d/80-retries && \
    echo 'APT::Install-Recommends "false";' > /etc/apt/apt.conf.d/71-no-recommends && \
    echo 'APT::Install-Suggests "false";' > /etc/apt/apt.conf.d/72-no-suggests

# Установка необходимых системных зависимостей (разделено для лучшей кешируемости)
RUN apt-get update && apt-get install -y \
    apt-utils \
    ca-certificates \
    curl \
    tzdata \
    && rm -rf /var/lib/apt/lists/*

# Установка зависимостей для локализации
RUN apt-get update && apt-get install -y \
    locales \
    && rm -rf /var/lib/apt/lists/* \
    && sed -i -e 's/# ru_RU.UTF-8 UTF-8/ru_RU.UTF-8 UTF-8/' /etc/locale.gen \
    && dpkg-reconfigure --frontend=noninteractive locales \
    && update-locale LANG=ru_RU.UTF-8

# Установка основных инструментов
RUN apt-get update && apt-get install -y \
    git \
    wget \
    ssh \
    sshpass \
    rsync \
    && rm -rf /var/lib/apt/lists/*

# Установка Tesseract OCR
RUN apt-get update && apt-get install -y \
    tesseract-ocr \
    tesseract-ocr-rus \
    && rm -rf /var/lib/apt/lists/*

# Настройка временной зоны
RUN ln -snf /usr/share/zoneinfo/$TZ /etc/localtime && echo $TZ > /etc/timezone

# Настройка SSH
RUN mkdir -p /root/.ssh && chmod 700 /root/.ssh
RUN echo "StrictHostKeyChecking no" > /etc/ssh/ssh_config.d/no_strict_host_checking.conf && \
    echo "UserKnownHostsFile /dev/null" >> /etc/ssh/ssh_config.d/no_strict_host_checking.conf

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

# Создание директорий для данных, логов и SSH
RUN mkdir -p /app/data /app/logs /app/ssh

# Создание пользователя без прав root для повышения безопасности
RUN groupadd -r botuser && useradd -r -g botuser -m -d /home/botuser botuser \
    && mkdir -p /tmp/images /tmp/text \
    && chown -R botuser:botuser /tmp/images /tmp/text /app/logs /app/data

# Копирование скриптов бота
COPY bot/ .

# Даем права на доступ к SSH директории и SSH команде
RUN chmod 700 /app/ssh \
    && chmod 600 /app/ssh/* 2>/dev/null || true \
    && chown -R botuser:botuser /app

# Скрипт для настройки SSH при запуске
RUN echo '#!/bin/bash\n\
if [ -f /app/ssh/id_rsa ]; then\n\
  mkdir -p ~/.ssh\n\
  cp -f /app/ssh/id_rsa ~/.ssh/\n\
  chmod 600 ~/.ssh/id_rsa\n\
fi\n\
exec "$@"' > /app/entrypoint.sh && \
    chmod +x /app/entrypoint.sh

# Переключение на непривилегированного пользователя
USER botuser

# Проверка работоспособности Tesseract
RUN tesseract --version || echo "Tesseract installed but command failed, continuing anyway"

# Новая точка входа и команда запуска
ENTRYPOINT ["/app/entrypoint.sh"]
CMD ["python", "bot.py"]