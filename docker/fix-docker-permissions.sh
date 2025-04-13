#!/bin/bash
#
# Скрипт для исправления проблем с правами доступа к Docker
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

# Проверка прав администратора
if [ "$EUID" -ne 0 ]; then
    log_warning "Запуск с правами администратора (sudo)..."
    exec sudo "$0" "$@"
    exit $?
fi

log_info "Проверка установки Docker..."
if ! command -v docker &>/dev/null; then
    log_error "Docker не установлен. Сначала установите Docker."
    log_info "Рекомендуется запустить ./setup.sh"
    exit 1
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
        exit 1
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
        exit 1
    fi
fi

log_info "Добавление пользователя $REAL_USER в группу docker..."
if getent group docker &>/dev/null; then
    usermod -aG docker "$REAL_USER"
    log_success "Пользователь $REAL_USER добавлен в группу docker."
else
    log_error "Группа docker не существует."
    exit 1
fi

log_info "Настройка прав доступа к сокету Docker..."
if [ -S /var/run/docker.sock ]; then
    chmod 666 /var/run/docker.sock
    log_success "Права доступа к сокету Docker настроены."
else
    log_error "Сокет Docker не найден по пути /var/run/docker.sock"
    exit 1
fi

log_info "Проверка прав доступа к сокету Docker..."
ls -la /var/run/docker.sock

log_success "Настройка прав доступа к Docker завершена."
log_info "Теперь пользователь $REAL_USER должен иметь доступ к Docker."
log_info "Для применения изменений в текущей сессии выполните команду:"
echo -e "${BLUE}newgrp docker${NC}"

exit 0