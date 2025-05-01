#!/bin/bash
#
# Универсальный скрипт для управления ботом расписания церковных богослужений
# Объединяет все функции из отдельных скриптов (setup.sh, start.sh, update.sh, fix-docker-permissions.sh)
#

# Цветовые коды для вывода
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Функция для вывода сообщений с префиксом
log_info() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

log_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1" >&2
}

log_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

# Функция для проверки ошибок
check_error() {
    if [ $? -ne 0 ]; then
        log_error "$1"
        exit 1
    fi
}

# Определение текущего каталога и структуры проекта
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"

# Функция для проверки Docker
check_docker() {
    log_info "Проверка Docker..."
    
    if ! command -v docker &>/dev/null; then
        log_error "Docker не установлен. Запустите сначала команду setup."
        return 1
    fi
    
    if ! docker info &>/dev/null; then
        log_warning "Нет прав доступа к Docker. Попытка исправления..."
        
        if groups | grep -q docker; then
            log_info "Пользователь в группе docker, но возможно изменения прав не применены."
            log_info "Применяем изменения для текущей сессии..."
            
            # Запуск с использованием newgrp
            if ! newgrp docker; then
                log_error "Не удалось применить группу docker"
                return 1
            fi
        else
            log_warning "Пользователь не в группе docker. Требуются права администратора."
            
            # Попытка исправить права доступа
            if ! fix_docker_permissions; then
                log_error "Не удалось исправить права доступа к Docker"
                return 1
            fi
        fi
    fi
    
    log_success "Docker доступен и настроен правильно"
    return 0
}

# Функция для установки Docker и необходимых компонентов
setup() {
    log_info "Начинаем установку и настройку необходимых компонентов..."
    
    # Проверка прав администратора
    if [ "$EUID" -ne 0 ]; then
        log_error "Пожалуйста, запустите скрипт с правами администратора (sudo)."
        exit 1
    fi
    
    # Обновление системных пакетов
    log_info "Обновление системных пакетов..."
    apt-get update
    check_error "Не удалось обновить список пакетов"
    
    apt-get upgrade -y
    check_error "Не удалось обновить системные пакеты"
    
    # Установка необходимых пакетов
    log_info "Установка необходимых пакетов..."
    apt-get install -y \
        apt-transport-https \
        ca-certificates \
        curl \
        gnupg \
        lsb-release \
        git \
        wget \
        python3-pip \
        tzdata
    check_error "Не удалось установить необходимые пакеты"
    
    # Настройка временной зоны
    log_info "Настройка временной зоны..."
    timedatectl set-timezone Europe/Minsk
    check_error "Не удалось установить временную зону"
    
    # Установка Docker
    log_info "Установка Docker..."
    # Добавление официального GPG ключа Docker
    curl -fsSL https://download.docker.com/linux/ubuntu/gpg | gpg --dearmor -o /usr/share/keyrings/docker-archive-keyring.gpg
    check_error "Не удалось добавить GPG ключ Docker"
    
    # Определение дистрибутива Linux
    if [ -f /etc/os-release ]; then
        . /etc/os-release
        OS=$NAME
    else
        OS="Unknown"
    fi
    
    # Настройка репозитория Docker
    if [[ "$OS" == *"Ubuntu"* ]] || [[ "$OS" == *"Debian"* ]]; then
        # Определение правильного репозитория в зависимости от дистрибутива
        if [[ "$OS" == *"Ubuntu"* ]]; then
            REPO_URL="https://download.docker.com/linux/ubuntu"
        else
            REPO_URL="https://download.docker.com/linux/debian"
        fi
        
        echo \
            "deb [arch=$(dpkg --print-architecture) signed-by=/usr/share/keyrings/docker-archive-keyring.gpg] $REPO_URL \
            $(lsb_release -cs) stable" | tee /etc/apt/sources.list.d/docker.list > /dev/null
        check_error "Не удалось настроить репозиторий Docker"
    else
        log_warning "Дистрибутив не распознан как Ubuntu или Debian. Попытка использовать Ubuntu репозиторий."
        echo \
            "deb [arch=$(dpkg --print-architecture) signed-by=/usr/share/keyrings/docker-archive-keyring.gpg] https://download.docker.com/linux/ubuntu \
            $(lsb_release -cs) stable" | tee /etc/apt/sources.list.d/docker.list > /dev/null
    fi
    
    # Установка Docker Engine
    apt-get update
    check_error "Не удалось обновить список пакетов после добавления репозитория Docker"
    
    apt-get install -y docker-ce docker-ce-cli containerd.io
    check_error "Не удалось установить Docker"
    
    # Настройка Docker для автозапуска
    systemctl enable docker
    check_error "Не удалось настроить автозапуск Docker"
    
    systemctl start docker
    check_error "Не удалось запустить Docker"
    
    # Установка Docker Compose
    log_info "Установка Docker Compose..."
    DOCKER_COMPOSE_VERSION=$(curl -s https://api.github.com/repos/docker/compose/releases/latest | grep -o '"tag_name": "[^"]*' | grep -o '[^"]*$')
    if [ -z "$DOCKER_COMPOSE_VERSION" ]; then
        DOCKER_COMPOSE_VERSION="v2.24.0"  # Резервная версия, если не удается получить последнюю
        log_warning "Не удалось определить последнюю версию Docker Compose, используем версию $DOCKER_COMPOSE_VERSION"
    else
        log_info "Найдена последняя версия Docker Compose: $DOCKER_COMPOSE_VERSION"
    fi
    
    curl -L "https://github.com/docker/compose/releases/download/$DOCKER_COMPOSE_VERSION/docker-compose-$(uname -s)-$(uname -m)" -o /usr/local/bin/docker-compose
    check_error "Не удалось загрузить Docker Compose"
    
    chmod +x /usr/local/bin/docker-compose
    check_error "Не удалось установить права на Docker Compose"
    
    # Создание символической ссылки для обратной совместимости
    ln -sf /usr/local/bin/docker-compose /usr/bin/docker-compose
    check_error "Не удалось создать символическую ссылку для Docker Compose"
    
    # Добавление текущего пользователя в группу docker
    CURRENT_USER=$(logname || echo $SUDO_USER)
    if [ -z "$CURRENT_USER" ]; then
        log_warning "Не удалось определить имя текущего пользователя"
        CURRENT_USER=$USER
    fi
    
    log_info "Добавление пользователя $CURRENT_USER в группу docker..."
    usermod -aG docker $CURRENT_USER
    check_error "Не удалось добавить пользователя в группу docker"
    
    # Создание необходимых директорий
    log_info "Создание необходимых директорий..."
    
    # Определяем директорию docker
    DOCKER_DIR="${SCRIPT_DIR}"
    
    # Создаем все необходимые директории
    mkdir -p ${DOCKER_DIR}/backups
    mkdir -p ${DOCKER_DIR}/logs
    mkdir -p ${DOCKER_DIR}/data
    mkdir -p ${DOCKER_DIR}/ssh
    
    chmod -R 755 ${DOCKER_DIR}/backups ${DOCKER_DIR}/logs ${DOCKER_DIR}/data
    chmod 700 ${DOCKER_DIR}/ssh  # Более строгие права для SSH ключей
    
    # Создание .env файла из шаблона, если он не существует
    if [ ! -f "${DOCKER_DIR}/.env" ]; then
        log_info "Создание .env файла..."
        
        cat > "${DOCKER_DIR}/.env" << EOL
# Токен бота телеграм
TELEGRAM_TOKEN=

# ID администратора в телеграме (только этот пользователь сможет использовать бота)
ADMIN_USER_ID=

# Данные для GitHub
REPO_URL=
GIT_USERNAME=
GIT_EMAIL=
GIT_TOKEN=

# Данные для подключения к хостингу
HOSTING_PATH=prihodpf@vh124.hoster.by
HOSTING_CERT=/app/ssh/id_rsa
HOSTING_PASSPHRASE=
HOSTING_DIR=/home/prihodpf/public_html

# Пути к файлам проекта
PROJECT_PATH=/app/project
INDEX_HTML_PATH=/app/project/index.html
DATABASE_PATH=/app/data/subscribers.db
EOL
        
        chmod 600 "${DOCKER_DIR}/.env"
        log_success "Создан файл .env. Пожалуйста, заполните его необходимыми данными."
    fi
    
    # Создание файла конфигурации Docker если нужно
    DOCKER_DAEMON_FILE="/etc/docker/daemon.json"
    if [ ! -f "$DOCKER_DAEMON_FILE" ]; then
        log_info "Создание файла конфигурации Docker..."
        mkdir -p /etc/docker
        cat > "$DOCKER_DAEMON_FILE" << EOL
{
  "log-driver": "json-file",
  "log-opts": {
    "max-size": "10m",
    "max-file": "3"
  },
  "default-ulimits": {
    "nofile": {
      "Name": "nofile",
      "Hard": 64000,
      "Soft": 64000
    }
  }
}
EOL
        log_success "Файл конфигурации Docker создан."
        
        # Перезапуск Docker для применения настроек
        log_info "Перезапуск Docker для применения настроек..."
        systemctl restart docker
        check_error "Не удалось перезапустить Docker"
    fi
    
    log_success "Установка завершена! Необходимо перезапустить сессию или выполнить команду: newgrp docker"
}

# Функция для исправления прав доступа к Docker
fix_docker_permissions() {
    # Проверка прав администратора
    if [ "$EUID" -ne 0 ]; then
        log_warning "Запуск с правами администратора (sudo)..."
        exec sudo "$0" fix_permissions
        exit $?
    fi
    
    log_info "Проверка установки Docker..."
    if ! command -v docker &>/dev/null; then
        log_error "Docker не установлен. Сначала установите Docker."
        log_info "Рекомендуется запустить ./church-bot-manager.sh setup"
        return 1
    fi
    
    log_info "Проверка статуса службы Docker..."
    systemctl status docker --no-pager || {
        log_warning "Служба Docker не запущена. Запуск..."
        systemctl start docker
        systemctl enable docker
        if systemctl status docker --no-pager; then
            log_success "Служба Docker запущена и настроена на автозапуск."
        else
            log_error "Не удалось запустить службу Docker."
            return 1
        fi
    }
    
    # Получение имени пользователя, который запустил sudo
    if [ -n "$SUDO_USER" ]; then
        REAL_USER="$SUDO_USER"
    else
        log_warning "Не удалось определить реального пользователя через SUDO_USER."
        log_info "Укажите имя пользователя вручную:"
        read -r REAL_USER
        if [ -z "$REAL_USER" ]; then
            log_error "Имя пользователя не указано."
            return 1
        fi
    fi
    
    log_info "Добавление пользователя $REAL_USER в группу docker..."
    if getent group docker &>/dev/null; then
        usermod -aG docker "$REAL_USER"
        log_success "Пользователь $REAL_USER добавлен в группу docker."
    else
        log_error "Группа docker не существует."
        return 1
    fi
    
    log_info "Настройка прав доступа к сокету Docker..."
    if [ -S /var/run/docker.sock ]; then
        chmod 666 /var/run/docker.sock
        log_success "Права доступа к сокету Docker настроены."
    else
        log_error "Сокет Docker не найден по пути /var/run/docker.sock"
        return 1
    fi
    
    log_info "Проверка прав доступа к сокету Docker..."
    ls -la /var/run/docker.sock
    
    log_success "Настройка прав доступа к Docker завершена."
    log_info "Теперь пользователь $REAL_USER должен иметь доступ к Docker."
    log_info "Для применения изменений в текущей сессии выполните команду:"
    echo -e "${BLUE}newgrp docker${NC}"
    
    return 0
}

# Функция для запуска бота
start_bot() {
    log_info "Запуск бота расписания богослужений..."
    
    # Проверка Docker
    if ! check_docker; then
        log_error "Невозможно запустить бота без доступа к Docker"
        return 1
    fi
    
    # Проверка существования docker-compose.yml
    if [ ! -f "${SCRIPT_DIR}/docker-compose.yml" ]; then
        log_error "Файл docker-compose.yml не найден в ${SCRIPT_DIR}"
        log_error "Проверьте структуру проекта и запустите скрипт из корректного местоположения."
        return 1
    fi
    
    # Проверка наличия директории bot
    if [ ! -d "${SCRIPT_DIR}/bot" ] && [ ! -d "${PROJECT_ROOT}/bot" ]; then
        log_warning "Директория bot не найдена ни в ${SCRIPT_DIR}, ни в ${PROJECT_ROOT}"
        log_info "Создание базовой структуры директорий..."
        mkdir -p "${SCRIPT_DIR}/bot"
        touch "${SCRIPT_DIR}/bot/requirements.txt"
        log_success "Базовая структура создана."
    fi
    
    # Создание директории для данных, если её нет
    DATA_DIR="${SCRIPT_DIR}/data"
    if [ ! -d "$DATA_DIR" ]; then
        log_info "Создание директории для данных..."
        mkdir -p "$DATA_DIR"
        chmod 777 "$DATA_DIR"  # Даем широкие права для доступа из контейнера
        log_success "Директория для данных создана: $DATA_DIR"
    fi
    
    # Проверка существования файла .env
    ENV_FILE="${SCRIPT_DIR}/.env"
    if [ ! -f "$ENV_FILE" ]; then
        log_warning "Файл .env не найден. Создается из шаблона..."
        
        cat > "$ENV_FILE" << 'EOF'
# Токен бота телеграм
TELEGRAM_TOKEN=

# ID администратора в телеграме (только этот пользователь сможет использовать бота)
ADMIN_USER_ID=

# Данные для GitHub
REPO_URL=
GIT_USERNAME=
GIT_EMAIL=
GIT_TOKEN=

# Данные для подключения к хостингу
HOSTING_PATH=prihodpf@vh124.hoster.by
HOSTING_CERT=/app/ssh/id_rsa
HOSTING_PASSPHRASE=
HOSTING_DIR=/home/prihodpf/public_html

# Пути к файлам проекта
PROJECT_PATH=/app/project
INDEX_HTML_PATH=/app/project/index.html
DATABASE_PATH=/app/data/subscribers.db
EOF
        
        chmod 600 "$ENV_FILE"
        log_warning "Создан файл .env. Пожалуйста, отредактируйте его перед запуском бота."
        log_info "Выполните: nano ${ENV_FILE}"
        
        # Проверка заполнен ли .env
        log_info "Нажмите Enter для продолжения после редактирования файла, или Ctrl+C для выхода."
        read -r
    fi
    
    # Проверка директории для SSH ключей
    SSH_DIR="${SCRIPT_DIR}/ssh"
    if [ ! -d "$SSH_DIR" ]; then
        log_info "Создание директории для SSH ключей..."
        mkdir -p "$SSH_DIR"
        chmod 700 "$SSH_DIR"  # Безопасные права доступа
        log_success "Директория для SSH ключей создана: $SSH_DIR"
        
        log_warning "Пожалуйста, поместите ваш приватный ключ (id_rsa) в директорию $SSH_DIR"
        log_info "Нажмите Enter для продолжения после добавления ключа, или Ctrl+C для выхода."
        read -r
    fi
    
    # Проверка наличия SSH ключа
    if [ ! -f "${SSH_DIR}/id_rsa" ]; then
        log_warning "SSH ключ не найден в директории ${SSH_DIR}"
        log_info "Пожалуйста, поместите ваш приватный ключ (id_rsa) в директорию $SSH_DIR"
        log_info "Нажмите Enter для продолжения после добавления ключа, или Ctrl+C для выхода."
        read -r
    else
        # Устанавливаем правильные разрешения для ключа
        chmod 600 "${SSH_DIR}/id_rsa"
        log_success "SSH ключ найден и настроен."
    fi
    
    # Проверка, заполнен ли .env
    if [ -f "$ENV_FILE" ]; then
        if ! grep -q "TELEGRAM_TOKEN=." "$ENV_FILE"; then
            log_warning "Токен Telegram бота не задан в файле .env"
            log_info "Пожалуйста, отредактируйте файл и укажите токен."
            return 1
        fi
    fi
    
    # Создание директории для бэкапов, если её нет
    BACKUP_DIR="${SCRIPT_DIR}/backups"
    if [ ! -d "$BACKUP_DIR" ]; then
        log_info "Создание директории для резервных копий..."
        mkdir -p "$BACKUP_DIR"
        chmod 755 "$BACKUP_DIR"
        log_success "Директория для резервных копий создана: $BACKUP_DIR"
    fi
    
    # Удаление конфликтующих контейнеров
    log_info "Проверка наличия конфликтующих контейнеров..."
    CONTAINERS_TO_REMOVE=()
    
    if docker ps -a --format '{{.Names}}' | grep -q "^church-schedule-bot$"; then
        CONTAINERS_TO_REMOVE+=("church-schedule-bot")
    fi
    
    if [ ${#CONTAINERS_TO_REMOVE[@]} -gt 0 ]; then
        log_warning "Найдены существующие контейнеры с конфликтующими именами: ${CONTAINERS_TO_REMOVE[*]}"
        log_info "Удаление конфликтующих контейнеров..."
        docker rm -f "${CONTAINERS_TO_REMOVE[@]}" > /dev/null 2>&1
        if [ $? -eq 0 ]; then
            log_success "Конфликтующие контейнеры успешно удалены."
        else
            log_error "Не удалось удалить конфликтующие контейнеры."
            log_info "Попробуйте выполнить вручную: docker rm -f ${CONTAINERS_TO_REMOVE[*]}"
            return 1
        fi
    fi
    
    # Запуск контейнеров
    log_info "Запуск контейнеров..."
    cd "$SCRIPT_DIR" || exit 1
    
    # Остановка существующих контейнеров
    docker-compose down 2>/dev/null
    
    # Сборка и запуск контейнеров
    log_info "Сборка и запуск контейнеров..."
    if ! docker-compose build --no-cache; then
        log_error "Не удалось собрать образы Docker."
        log_info "Попытка запуска с существующими образами..."
        
        # Пробуем запустить с существующими образами
        if ! docker-compose up -d; then
            log_error "Не удалось запустить контейнеры."
            return 1
        fi
    else
        # Запуск контейнеров
        if ! docker-compose up -d; then
            log_error "Не удалось запустить контейнеры."
            return 1
        fi
    fi
    
    # Проверка запущены ли контейнеры
    if docker ps | grep -q "church-schedule-bot"; then
        log_success "Бот успешно запущен!"
        log_info "Для просмотра логов выполните: docker logs church-schedule-bot -f"
    else
        log_error "Бот не запустился."
        log_info "Проверьте логи: docker-compose logs"
        return 1
    fi
    
    return 0
}

# Функция для обновления бота
update_bot() {
    log_info "Обновление бота расписания богослужений..."
    
    # Проверка Docker
    if ! check_docker; then
        log_error "Невозможно обновить бота без доступа к Docker"
        return 1
    fi
    
    # Обновление из Git репозитория (если мы находимся в Git репозитории)
    if [ -d ".git" ] || [ -d "../.git" ]; then
        log_info "Обновление из Git репозитория..."
        git pull
        check_error "Не удалось обновить код из Git репозитория"
    else
        log_warning "Директория .git не найдена. Пропуск обновления из Git."
    fi
    
    # Перезапуск контейнеров
    log_info "Перезапуск контейнеров..."
    cd "$SCRIPT_DIR" || exit 1
    
    docker-compose down
    check_error "Не удалось остановить контейнеры"
    
    docker-compose up -d
    check_error "Не удалось запустить контейнеры"
    
    # Проверка запущены ли контейнеры
    if docker ps | grep -q "church-schedule-bot"; then
        log_success "Бот успешно обновлен и запущен!"
        log_info "Для просмотра логов выполните: docker logs church-schedule-bot -f"
    else
        log_error "Бот не запустился после обновления."
        log_info "Проверьте логи: docker-compose logs"
        return 1
    fi
    
    return 0
}

# Функция для остановки бота
stop_bot() {
    log_info "Остановка бота расписания богослужений..."
    
    # Проверка Docker
    if ! check_docker; then
        log_error "Невозможно остановить бота без доступа к Docker"
        return 1
    fi
    
    # Остановка контейнеров
    cd "$SCRIPT_DIR" || exit 1
    
    docker-compose down
    check_error "Не удалось остановить контейнеры"
    
    log_success "Бот успешно остановлен"
    return 0
}

# Функция для просмотра логов
view_logs() {
    log_info "Просмотр логов бота..."
    
    # Проверка Docker
    if ! check_docker; then
        log_error "Невозможно просмотреть логи без доступа к Docker"
        return 1
    fi
    
    # Проверка аргумента для количества строк
    lines=100
    if [ ! -z "$1" ] && [ "$1" -eq "$1" ] 2>/dev/null; then
        lines=$1
    fi
    
    # Просмотр логов контейнера
    if docker ps | grep -q "church-schedule-bot"; then
        docker logs --tail $lines -f church-schedule-bot
    else
        log_error "Контейнер church-schedule-bot не запущен"
        return 1
    fi
    
    return 0
}

# Функция для создания резервной копии
backup() {
    log_info "Создание резервной копии данных бота..."
    
    # Создание директории для резервных копий
    BACKUP_DIR="${SCRIPT_DIR}/backups"
    mkdir -p "$BACKUP_DIR"
    
    # Текущая дата и время для имени бэкапа
    BACKUP_DATE=$(date +"%Y%m%d_%H%M%S")
    BACKUP_FILE="${BACKUP_DIR}/church_bot_backup_${BACKUP_DATE}.tar.gz"
    
    # Архивирование данных
    log_info "Архивирование данных бота..."
    tar -czf "$BACKUP_FILE" -C "${SCRIPT_DIR}" data .env ssh/id_rsa 2>/dev/null
    
    if [ $? -eq 0 ]; then
        log_success "Резервная копия успешно создана: $BACKUP_FILE"
        
        # Очистка старых резервных копий (оставляем последние 5)
        log_info "Очистка старых резервных копий..."
        ls -t "${BACKUP_DIR}"/church_bot_backup_*.tar.gz 2>/dev/null | tail -n +6 | xargs -r rm
        
        log_success "Операция резервного копирования завершена"
    else
        log_error "Не удалось создать резервную копию"
        return 1
    fi
    
    return 0
}

# Функция для восстановления из резервной копии
restore() {
    log_info "Восстановление из резервной копии..."
    
    # Проверка указанного файла
    BACKUP_FILE="$1"
    
    if [ -z "$BACKUP_FILE" ]; then
        # Если файл не указан, показываем список доступных бэкапов
        BACKUP_DIR="${SCRIPT_DIR}/backups"
        
        if [ ! -d "$BACKUP_DIR" ] || [ -z "$(ls -A "$BACKUP_DIR" 2>/dev/null)" ]; then
            log_error "Резервные копии не найдены в директории ${BACKUP_DIR}"
            return 1
        fi
        
        # Показываем список бэкапов
        log_info "Доступные резервные копии:"
        select backup_file in "${BACKUP_DIR}"/church_bot_backup_*.tar.gz; do
            if [ -n "$backup_file" ]; then
                BACKUP_FILE="$backup_file"
                break
            else
                log_error "Неверный выбор. Попробуйте еще раз."
            fi
        done
    fi
    
    # Проверка существования файла
    if [ ! -f "$BACKUP_FILE" ]; then
        log_error "Файл резервной копии не найден: $BACKUP_FILE"
        return 1
    fi
    
    # Остановка бота перед восстановлением
    log_info "Остановка бота перед восстановлением..."
    stop_bot
    
    # Создание временной директории для распаковки
    TEMP_DIR=$(mktemp -d)
    
    # Распаковка архива
    log_info "Распаковка архива резервной копии..."
    tar -xzf "$BACKUP_FILE" -C "$TEMP_DIR"
    
    if [ $? -ne 0 ]; then
        log_error "Не удалось распаковать архив: $BACKUP_FILE"
        rm -rf "$TEMP_DIR"
        return 1
    fi
    
    # Восстановление данных
    log_info "Восстановление данных..."
    
    # Создаем резервную копию текущих данных перед восстановлением
    CURRENT_BACKUP_DATE=$(date +"%Y%m%d_%H%M%S")
    CURRENT_BACKUP_DIR="${SCRIPT_DIR}/backups/backup_before_restore_${CURRENT_BACKUP_DATE}"
    mkdir -p "$CURRENT_BACKUP_DIR"
    
    # Копируем текущие данные
    cp -r "${SCRIPT_DIR}/data" "$CURRENT_BACKUP_DIR" 2>/dev/null
    cp "${SCRIPT_DIR}/.env" "$CURRENT_BACKUP_DIR" 2>/dev/null
    cp "${SCRIPT_DIR}/ssh/id_rsa" "$CURRENT_BACKUP_DIR" 2>/dev/null
    
    log_info "Текущие данные сохранены в: $CURRENT_BACKUP_DIR"
    
    # Восстанавливаем данные из бэкапа
    if [ -d "${TEMP_DIR}/data" ]; then
        rm -rf "${SCRIPT_DIR}/data" 2>/dev/null
        cp -r "${TEMP_DIR}/data" "${SCRIPT_DIR}/"
        chmod -R 755 "${SCRIPT_DIR}/data"
    fi
    
    if [ -f "${TEMP_DIR}/.env" ]; then
        cp "${TEMP_DIR}/.env" "${SCRIPT_DIR}/"
        chmod 600 "${SCRIPT_DIR}/.env"
    fi
    
    if [ -f "${TEMP_DIR}/id_rsa" ]; then
        mkdir -p "${SCRIPT_DIR}/ssh"
        cp "${TEMP_DIR}/id_rsa" "${SCRIPT_DIR}/ssh/"
        chmod 600 "${SCRIPT_DIR}/ssh/id_rsa"
    fi
    
    # Очистка временной директории
    rm -rf "$TEMP_DIR"
    
    log_success "Восстановление из резервной копии завершено"
    
    # Запуск бота после восстановления
    log_info "Запуск бота после восстановления..."
    start_bot
    
    return 0
}

# Функция для проверки статуса бота
status() {
    log_info "Проверка статуса бота расписания богослужений..."
    
    # Проверка Docker
    if ! check_docker; then
        log_error "Невозможно проверить статус бота без доступа к Docker"
        return 1
    fi
    
    # Проверка запущен ли контейнер
    if docker ps | grep -q "church-schedule-bot"; then
        log_success "Бот запущен и работает"
        
        # Получение информации о контейнере
        log_info "Информация о контейнере:"
        docker ps --format "table {{.ID}}\t{{.Image}}\t{{.Status}}\t{{.Ports}}" | grep church-schedule-bot
        
        # Проверка использования ресурсов
        log_info "Использование ресурсов:"
        docker stats --no-stream church-schedule-bot
    else
        # Проверка существует ли контейнер, но не запущен
        if docker ps -a | grep -q "church-schedule-bot"; then
            log_warning "Бот остановлен"
            
            # Получение информации о контейнере
            log_info "Информация о контейнере:"
            docker ps -a --format "table {{.ID}}\t{{.Image}}\t{{.Status}}\t{{.Ports}}" | grep church-schedule-bot
        else
            log_error "Контейнер бота не найден"
        fi
    fi
    
    # Проверка состояния файлов
    log_info "Проверка файлов проекта:"
    
    # Проверка .env
    if [ -f "${SCRIPT_DIR}/.env" ]; then
        log_success "Файл .env найден"
    else
        log_error "Файл .env не найден"
    fi
    
    # Проверка SSH ключа
    if [ -f "${SCRIPT_DIR}/ssh/id_rsa" ]; then
        log_success "SSH ключ найден"
    else
        log_error "SSH ключ не найден"
    fi
    
    # Проверка директории данных
    if [ -d "${SCRIPT_DIR}/data" ]; then
        log_success "Директория данных найдена"
        # Проверка наличия файлов в директории данных
        FILE_COUNT=$(find "${SCRIPT_DIR}/data" -type f | wc -l)
        log_info "Количество файлов в директории данных: $FILE_COUNT"
    else
        log_error "Директория данных не найдена"
    fi
    
    # Проверка директории логов
    if [ -d "${SCRIPT_DIR}/logs" ]; then
        log_success "Директория логов найдена"
        # Проверка наличия файлов в директории логов
        LOG_COUNT=$(find "${SCRIPT_DIR}/logs" -type f | wc -l)
        log_info "Количество файлов в директории логов: $LOG_COUNT"
    else
        log_error "Директория логов не найдена"
    fi
    
    # Проверка директории бэкапов
    if [ -d "${SCRIPT_DIR}/backups" ]; then
        log_success "Директория резервных копий найдена"
        # Проверка наличия файлов в директории бэкапов
        BACKUP_COUNT=$(find "${SCRIPT_DIR}/backups" -type f | wc -l)
        log_info "Количество файлов в директории резервных копий: $BACKUP_COUNT"
    else
        log_error "Директория резервных копий не найдена"
    fi
    
    return 0
}

# Функция для отображения справки
show_help() {
    echo -e "${BLUE}Церковный бот - Универсальный инструмент управления${NC}"
    echo ""
    echo "Использование: $0 [команда] [параметры]"
    echo ""
    echo -e "${GREEN}Доступные команды:${NC}"
    echo -e "  ${YELLOW}setup${NC}             - Установка всех необходимых компонентов (Docker, зависимости)"
    echo -e "  ${YELLOW}start${NC}             - Запуск бота"
    echo -e "  ${YELLOW}stop${NC}              - Остановка бота"
    echo -e "  ${YELLOW}restart${NC}           - Перезапуск бота"
    echo -e "  ${YELLOW}update${NC}            - Обновление бота из репозитория"
    echo -e "  ${YELLOW}logs [N]${NC}          - Просмотр логов бота (N - количество строк, по умолчанию 100)"
    echo -e "  ${YELLOW}status${NC}            - Проверка состояния бота"
    echo -e "  ${YELLOW}backup${NC}            - Создание резервной копии данных бота"
    echo -e "  ${YELLOW}restore [файл]${NC}    - Восстановление из резервной копии"
    echo -e "  ${YELLOW}fix_permissions${NC}   - Исправление прав доступа к Docker"
    echo -e "  ${YELLOW}help${NC}              - Показать эту справку"
    echo ""
    echo -e "${GREEN}Примеры:${NC}"
    echo -e "  $0 setup          - Установка всех необходимых компонентов"
    echo -e "  $0 start          - Запуск бота"
    echo -e "  $0 logs 50        - Показать последние 50 строк логов"
    echo -e "  $0 restore        - Восстановление из резервной копии (с выбором файла)"
    echo ""
}

# Основная функция выбора действия
main() {
    # Проверка аргументов
    if [ $# -eq 0 ]; then
        show_help
        exit 0
    fi
    
    # Обработка команд
    case "$1" in
        setup)
            setup
            ;;
        start)
            start_bot
            ;;
        stop)
            stop_bot
            ;;
        restart)
            stop_bot
            start_bot
            ;;
        update)
            update_bot
            ;;
        logs)
            view_logs "$2"
            ;;
        status)
            status
            ;;
        backup)
            backup
            ;;
        restore)
            restore "$2"
            ;;
        fix_permissions)
            fix_docker_permissions
            ;;
        help)
            show_help
            ;;
        *)
            log_error "Неизвестная команда: $1"
            show_help
            exit 1
            ;;
    esac
    
    exit $?
}

# Запуск основной функции
main "$@"