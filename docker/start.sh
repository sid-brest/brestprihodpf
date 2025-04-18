#!/bin/bash
#
# Скрипт для быстрого запуска бота расписания богослужений
# Проверяет окружение и запускает необходимые компоненты
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

# Определение текущего каталога и структуры проекта
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
DOCKER_DIR="${SCRIPT_DIR}"
SETUP_SCRIPT="${DOCKER_DIR}/setup.sh"

log_info "Запуск из директории: ${SCRIPT_DIR}"
log_info "Корневая директория проекта: ${PROJECT_ROOT}"

# Проверка прав доступа к Docker
if ! docker info &>/dev/null; then
    log_warning "Нет прав доступа к Docker. Проверка наличия пользователя в группе docker..."
    
    # Проверяем есть ли пользователь в группе docker
    if groups | grep -q docker; then
        log_info "Пользователь в группе docker, но возможно изменения прав не применены."
        log_info "Применяем изменения для текущей сессии..."
        
        # Запуск с использованием newgrp
        exec newgrp docker << EOF
        bash "${BASH_SOURCE[0]}"
EOF
        exit 0
    else
        log_warning "Пользователь не в группе docker. Требуются права администратора."
        
        # Проверка можно ли использовать sudo
        if command -v sudo &>/dev/null; then
            log_info "Запуск с правами администратора через sudo..."
            exec sudo "$0"
            exit 0
        else
            log_error "Команда sudo недоступна. Добавьте пользователя в группу docker:"
            log_info "sudo usermod -aG docker $USER && newgrp docker"
            exit 1
        fi
    fi
fi

# Проверка существования setup.sh
if [ ! -f "$SETUP_SCRIPT" ]; then
    log_warning "Установочный скрипт не найден: $SETUP_SCRIPT"
    log_info "Создание базового скрипта setup.sh..."
    
    cat > "$SETUP_SCRIPT" << 'EOF'
#!/bin/bash
echo "Установка Docker и необходимых компонентов..."
sudo apt-get update && sudo apt-get install -y docker.io docker-compose
sudo usermod -aG docker $USER
echo "Установка завершена. Перезапустите терминал или выполните: newgrp docker"
EOF
    
    chmod +x "$SETUP_SCRIPT"
    log_success "Скрипт setup.sh создан."
fi

# Проверка прав на выполнение setup.sh
if [ ! -x "$SETUP_SCRIPT" ]; then
    log_warning "Установочный скрипт не имеет прав на выполнение. Устанавливаем права..."
    chmod +x "$SETUP_SCRIPT"
    if [ $? -ne 0 ]; then
        log_error "Не удалось установить права на выполнение для $SETUP_SCRIPT"
        log_error "Попробуйте выполнить: sudo chmod +x $SETUP_SCRIPT"
        exit 1
    fi
    log_success "Права установлены успешно."
fi

# Проверка существования docker-compose.yml
if [ ! -f "${DOCKER_DIR}/docker-compose.yml" ]; then
    log_error "Файл docker-compose.yml не найден в ${DOCKER_DIR}"
    log_error "Проверьте структуру проекта и запустите скрипт из корректного местоположения."
    exit 1
fi

# Проверка наличия директории bot
if [ ! -d "${DOCKER_DIR}/bot" ] && [ ! -d "${PROJECT_ROOT}/bot" ]; then
    log_warning "Директория bot не найдена ни в ${DOCKER_DIR}, ни в ${PROJECT_ROOT}"
    log_info "Создание базовой структуры директорий..."
    mkdir -p "${DOCKER_DIR}/bot"
    touch "${DOCKER_DIR}/bot/requirements.txt"
    log_success "Базовая структура создана."
fi

# Создание директории для данных, если её нет
DATA_DIR="${DOCKER_DIR}/data"
if [ ! -d "$DATA_DIR" ]; then
    log_info "Создание директории для данных подписчиков..."
    mkdir -p "$DATA_DIR"
    chmod 777 "$DATA_DIR"  # Даем широкие права для доступа из контейнера
    log_success "Директория для данных создана: $DATA_DIR"
fi

# Проверка существования файла .env
ENV_FILE="${DOCKER_DIR}/.env"
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
HOSTING_PASSPHRASE=b54=nr*Dzq)y
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
SSH_DIR="${DOCKER_DIR}/ssh"
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
        exit 1
    fi
fi

# Проверка установки Docker
if ! command -v docker &>/dev/null; then
    log_warning "Docker не установлен. Необходима установка Docker."
    log_info "Запуск установочного скрипта..."
    
    # Запуск setup.sh
    "$SETUP_SCRIPT"
    if [ $? -ne 0 ]; then
        log_error "Не удалось выполнить установочный скрипт."
        exit 1
    fi
    
    log_info "Пожалуйста, перезапустите терминал или выполните: newgrp docker"
    log_info "Затем запустите скрипт снова."
    exit 0
else
    log_success "Docker установлен."
    
    # Проверка Docker Compose
    if ! command -v docker-compose &>/dev/null; then
        log_warning "Docker Compose не установлен."
        log_info "Проверка наличия docker compose plugin..."
        
        if docker compose version &>/dev/null; then
            log_success "Найден docker compose plugin."
            # Создаем алиас
            alias docker-compose="docker compose"
        else
            log_warning "Docker Compose не найден. Попытка установки..."
            "$SETUP_SCRIPT"
            if [ $? -ne 0 ]; then
                log_error "Не удалось установить Docker Compose."
                exit 1
            fi
        fi
    else
        log_success "Docker Compose установлен."
    fi
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
        exit 1
    fi
fi

# Запуск контейнеров
log_info "Запуск контейнеров..."
cd "$DOCKER_DIR" || exit 1

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
        exit 1
    fi
else
    # Запуск контейнеров
    if ! docker-compose up -d; then
        log_error "Не удалось запустить контейнеры."
        exit 1
    fi
fi

# Проверка запущены ли контейнеры
if docker ps | grep -q "church-schedule-bot"; then
    log_success "Бот успешно запущен!"
    log_info "Для просмотра логов выполните: docker logs church-schedule-bot -f"
else
    log_error "Бот не запустился."
    log_info "Проверьте логи: docker-compose logs"
    exit 1
fi

log_success "Операция завершена успешно!"
exit 0