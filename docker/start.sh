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
DOCKER_DIR="${PROJECT_ROOT}/docker"
SETUP_SCRIPT="${DOCKER_DIR}/setup.sh"

log_info "Запуск из директории: ${SCRIPT_DIR}"
log_info "Корневая директория проекта: ${PROJECT_ROOT}"

# Проверка существования docker директории
if [ ! -d "$DOCKER_DIR" ]; then
    log_error "Директория Docker не найдена: $DOCKER_DIR"
    log_error "Проверьте структуру проекта и запустите скрипт из корректного местоположения."
    exit 1
fi

# Проверка существования setup.sh
if [ ! -f "$SETUP_SCRIPT" ]; then
    log_error "Установочный скрипт не найден: $SETUP_SCRIPT"
    log_error "Убедитесь, что файл setup.sh существует в директории Docker."
    exit 1
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

# Проверка установки Docker
if ! command -v docker &> /dev/null; then
    log_warning "Docker не установлен. Необходима установка Docker."
    log_info "Запуск установочного скрипта..."
    
    # Проверка прав администратора
    if [ "$EUID" -ne 0 ]; then
        log_warning "Для установки Docker требуются права администратора."
        log_info "Запуск скрипта с sudo..."
        sudo "$SETUP_SCRIPT"
        if [ $? -ne 0 ]; then
            log_error "Не удалось запустить установочный скрипт с sudo."
            exit 1
        fi
    else
        # Если скрипт уже запущен с правами администратора
        "$SETUP_SCRIPT"
        if [ $? -ne 0 ]; then
            log_error "Не удалось выполнить установочный скрипт."
            exit 1
        fi
    fi
else
    log_success "Docker уже установлен."
    
    # Проверка запуска Docker
    if ! docker info &>/dev/null; then
        log_warning "Docker установлен, но не запущен или требуются права администратора."
        log_info "Попытка запуска службы Docker..."
        
        sudo systemctl start docker
        if [ $? -ne 0 ]; then
            log_error "Не удалось запустить службу Docker."
            exit 1
        fi
        log_success "Служба Docker запущена."
    fi
    
    # Проверка существования контейнеров
    if docker ps -a | grep -q "church-schedule-bot"; then
        log_info "Найден контейнер church-schedule-bot."
        
        # Проверка, запущен ли контейнер
        if docker ps | grep -q "church-schedule-bot"; then
            log_success "Бот уже запущен."
            log_info "Для перезапуска используйте: docker-compose restart church-bot"
            log_info "Для просмотра логов: docker logs church-schedule-bot"
        else
            log_warning "Бот не запущен."
            log_info "Запуск бота..."
            
            cd "$DOCKER_DIR" && docker-compose up -d
            if [ $? -ne 0 ]; then
                log_error "Не удалось запустить бота."
                exit 1
            fi
            log_success "Бот успешно запущен!"
        fi
    else
        log_warning "Контейнер бота не найден. Возможно, необходима первичная настройка."
        log_info "Переход в директорию Docker и запуск docker-compose..."
        
        cd "$DOCKER_DIR" || exit 1
        
        # Проверка существования файла .env
        if [ ! -f ".env" ]; then
            log_warning "Файл .env не найден. Создается из шаблона..."
            
            if [ -f ".env.template" ]; then
                cp ".env.template" ".env"
                log_warning "Пожалуйста, отредактируйте файл .env перед запуском."
                log_info "Выполните: nano ${DOCKER_DIR}/.env"
                exit 0
            else
                log_error "Шаблон .env.template не найден. Невозможно создать конфигурацию."
                exit 1
            fi
        fi
        
        # Запуск docker-compose
        docker-compose up -d
        if [ $? -ne 0 ]; then
            log_error "Не удалось запустить контейнеры."
            exit 1
        fi
        log_success "Контейнеры успешно запущены!"
    fi
fi

# Вывод информации о доступе к Portainer
if docker ps | grep -q "portainer"; then
    log_success "Portainer запущен и доступен по адресу: http://localhost:9000"
fi

log_success "Операция завершена успешно!"
exit 0