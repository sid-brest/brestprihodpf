#!/bin/bash
#
# Скрипт для установки Docker, Docker Compose и Portainer
# Автоматизирует настройку окружения для работы церковного бота
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

# Функция для бэкапа файлов перед их модификацией
backup_file() {
    if [ -f "$1" ]; then
        local backup_name="$1.bak.$(date +%Y%m%d%H%M%S)"
        cp "$1" "$backup_name"
        log_info "Создана резервная копия файла: $backup_name"
    fi
}

# Проверка прав администратора
if [ "$EUID" -ne 0 ]; then
    log_error "Пожалуйста, запустите скрипт с правами администратора (sudo)."
    exit 1
fi

# Определение дистрибутива Linux
if [ -f /etc/os-release ]; then
    . /etc/os-release
    OS=$NAME
    VERSION=$VERSION_ID
    log_info "Обнаружена операционная система: $OS $VERSION"
else
    log_warning "Невозможно определить дистрибутив Linux. Продолжение установки с настройками по умолчанию."
    OS="Unknown"
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

# Добавление официального GPG ключа Docker
log_info "Добавление официального GPG ключа Docker..."
curl -fsSL https://download.docker.com/linux/ubuntu/gpg | gpg --dearmor -o /usr/share/keyrings/docker-archive-keyring.gpg
check_error "Не удалось добавить GPG ключ Docker"

# Настройка стабильного репозитория Docker
log_info "Настройка репозитория Docker..."
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
log_info "Установка Docker Engine..."
apt-get update
check_error "Не удалось обновить список пакетов после добавления репозитория Docker"

apt-get install -y docker-ce docker-ce-cli containerd.io
check_error "Не удалось установить Docker"

# Настройка Docker для автозапуска
log_info "Настройка автозапуска Docker..."
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
log_info "Добавление пользователя $CURRENT_USER в группу docker..."
usermod -aG docker $CURRENT_USER
check_error "Не удалось добавить пользователя в группу docker"

# Проверка успешности установки Docker
log_info "Проверка установки Docker..."
if docker --version; then
    log_success "Docker успешно установлен!"
else
    log_error "Возникла проблема с установкой Docker."
    exit 1
fi

# Проверка успешности установки Docker Compose
log_info "Проверка установки Docker Compose..."
if docker-compose --version; then
    log_success "Docker Compose успешно установлен!"
else
    log_error "Возникла проблема с установкой Docker Compose."
    exit 1
fi

# Создание необходимых директорий
log_info "Создание необходимых директорий..."
mkdir -p portainer-data
mkdir -p backups
mkdir -p logs
chmod -R 755 portainer-data backups logs

# Создание .env файла из шаблона, если он не существует
if [ ! -f .env ]; then
    log_info "Создание .env файла из шаблона..."
    if [ -f .env.template ]; then
        cp .env.template .env
        chmod 600 .env  # Ограничение прав доступа для защиты конфиденциальных данных
        log_success "Файл .env создан из шаблона."
        log_warning "Пожалуйста, отредактируйте файл .env, заполнив все необходимые переменные."
    else
        log_error "Шаблон .env.template не найден."
        cat > .env << EOL
# Токен бота телеграм
TELEGRAM_TOKEN=

# ID администратора в телеграме (только этот пользователь сможет использовать бота)
ADMIN_USER_ID=

# Данные для GitHub
REPO_URL=
GIT_USERNAME=
GIT_EMAIL=
GIT_TOKEN=

# Пути к файлам проекта
PROJECT_PATH=/app/project
INDEX_HTML_PATH=/app/project/index.html
EOL
        chmod 600 .env
        log_success "Создан пустой файл .env. Пожалуйста, заполните его необходимыми переменными."
    fi
fi

# Проверка конфигурации Docker
log_info "Проверка конфигурации Docker..."
# Проверяем и создаем системный файл конфигурации Docker если нужно
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

# Настройка автоматических обновлений (опционально)
log_info "Настройка автоматических обновлений безопасности..."
apt-get install -y unattended-upgrades
check_error "Не удалось установить автоматические обновления"

# Запуск контейнеров
log_info "Подготовка к запуску контейнеров..."
if [ -f "docker-compose.yml" ]; then
    log_info "Найден файл docker-compose.yml, запуск контейнеров..."
    docker-compose up -d
    check_error "Не удалось запустить контейнеры"
    log_success "Контейнеры успешно запущены!"
else
    log_warning "Файл docker-compose.yml не найден в текущей директории."
    log_info "После настройки выполните команду: cd $(pwd) && docker-compose up -d"
fi

# Финальное сообщение
log_success "Установка завершена! Необходимо перезапустить сессию или компьютер, чтобы изменения вступили в силу."
log_info "После перезапуска Portainer будет доступен по адресу: http://localhost:9000"
log_info "Для начала работы с новой сессией без перезагрузки выполните команду: newgrp docker"

# Создаем скрипт для быстрого обновления из Git
cat > update.sh << EOL
#!/bin/bash
# Скрипт для обновления проекта из Git и перезапуска контейнеров

echo "Обновление проекта из Git..."
git pull

echo "Перезапуск контейнеров..."
docker-compose down
docker-compose up -d

echo "Готово! Контейнеры обновлены и запущены."
EOL

chmod +x update.sh
log_success "Создан скрипт update.sh для быстрого обновления проекта."

exit 0