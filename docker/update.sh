#!/bin/bash
# Скрипт для обновления проекта из Git и перезапуска контейнеров

echo "Обновление проекта из Git..."
git pull

echo "Перезапуск контейнеров..."
docker-compose down
docker-compose up -d

echo "Готово! Контейнеры обновлены и запущены."
