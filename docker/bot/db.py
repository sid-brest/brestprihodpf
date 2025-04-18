"""
Модуль для работы с базой данных подписчиков.
Предоставляет функциональность для хранения и управления подписчиками,
группами, шаблонами сообщений и запланированными рассылками.
"""
import os
import sqlite3
import logging
import json
import csv
import time
import threading
from datetime import datetime, timedelta
from typing import List, Tuple, Optional, Dict, Any, Set, Union
from pathlib import Path

# Настройка логирования
logger = logging.getLogger(__name__)

# Путь к файлу базы данных подписчиков
DEFAULT_DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "subscribers.db")

class SubscriberDatabase:
    """Класс для управления базой данных подписчиков."""
    
    def __init__(self, db_path: str = DEFAULT_DB_PATH):
        """
        Инициализация базы данных подписчиков.
        
        Args:
            db_path: Путь к файлу базы данных. По умолчанию в текущей директории.
        """
        self.db_path = db_path
        # Блокировка для обеспечения потокобезопасности
        self._lock = threading.RLock()
        self._initialize_db()
    
    def _initialize_db(self) -> None:
        """Инициализирует структуру базы данных, если она не существует."""
        with self._lock:
            try:
                # Создаем директорию для базы данных, если она не существует
                os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
                
                conn = sqlite3.connect(self.db_path)
                cursor = conn.cursor()
                
                # Создаем таблицу подписчиков, если она не существует
                cursor.execute('''
                CREATE TABLE IF NOT EXISTS subscribers (
                    chat_id INTEGER PRIMARY KEY,
                    username TEXT,
                    full_name TEXT,
                    subscribed INTEGER DEFAULT 1,
                    subscription_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    last_notification_date TIMESTAMP,
                    notification_count INTEGER DEFAULT 0,
                    user_timezone TEXT DEFAULT 'Europe/Minsk',
                    user_preferences TEXT
                )
                ''')
                
                # Создаем таблицу для истории рассылок
                cursor.execute('''
                CREATE TABLE IF NOT EXISTS broadcast_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    message_text TEXT,
                    sent_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    success_count INTEGER DEFAULT 0,
                    error_count INTEGER DEFAULT 0,
                    admin_id INTEGER,
                    target_group TEXT
                )
                ''')
                
                # Создаем таблицу для статистики
                cursor.execute('''
                CREATE TABLE IF NOT EXISTS usage_stats (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    action_type TEXT,
                    action_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    details TEXT,
                    user_id INTEGER
                )
                ''')
                
                # Создаем таблицу для групп подписчиков
                cursor.execute('''
                CREATE TABLE IF NOT EXISTS subscriber_groups (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    group_name TEXT UNIQUE,
                    description TEXT,
                    created_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
                ''')
                
                # Создаем таблицу связей подписчиков с группами
                cursor.execute('''
                CREATE TABLE IF NOT EXISTS subscriber_group_links (
                    chat_id INTEGER,
                    group_id INTEGER,
                    added_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    PRIMARY KEY (chat_id, group_id),
                    FOREIGN KEY (chat_id) REFERENCES subscribers(chat_id),
                    FOREIGN KEY (group_id) REFERENCES subscriber_groups(id)
                )
                ''')
                
                # Создаем таблицу для запланированных рассылок
                cursor.execute('''
                CREATE TABLE IF NOT EXISTS scheduled_broadcasts (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    message_text TEXT,
                    scheduled_date TIMESTAMP,
                    target_group TEXT,
                    admin_id INTEGER,
                    created_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    status TEXT DEFAULT 'pending',
                    completed_date TIMESTAMP
                )
                ''')
                
                # Создаем таблицу для шаблонов сообщений
                cursor.execute('''
                CREATE TABLE IF NOT EXISTS message_templates (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    template_name TEXT UNIQUE,
                    template_text TEXT,
                    created_by INTEGER,
                    created_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    last_used_date TIMESTAMP
                )
                ''')
                
                # Добавим несколько базовых групп, если таблица пуста
                cursor.execute("SELECT COUNT(*) FROM subscriber_groups")
                if cursor.fetchone()[0] == 0:
                    default_groups = [
                        ("all", "Все подписчики"),
                        ("active", "Активные подписчики"),
                        ("inactive", "Неактивные подписчики"),
                    ]
                    for name, desc in default_groups:
                        cursor.execute(
                            "INSERT INTO subscriber_groups (group_name, description) VALUES (?, ?)",
                            (name, desc)
                        )
                
                conn.commit()
                conn.close()
                logger.info(f"База данных подписчиков инициализирована: {self.db_path}")
            except Exception as e:
                logger.error(f"Ошибка при инициализации базы данных: {str(e)}")
                raise
    
    def _dict_to_json(self, data: Dict) -> str:
        """Преобразует словарь в JSON-строку."""
        try:
            return json.dumps(data, ensure_ascii=False)
        except Exception as e:
            logger.error(f"Ошибка при преобразовании словаря в JSON: {str(e)}")
            return "{}"
    
    def _json_to_dict(self, json_str: str) -> Dict:
        """Преобразует JSON-строку в словарь."""
        if not json_str:
            return {}
        try:
            return json.loads(json_str)
        except Exception as e:
            logger.error(f"Ошибка при преобразовании JSON в словарь: {str(e)}")
            return {}
    
    def add_subscriber(self, chat_id: int, username: str, full_name: str, 
                       timezone: str = 'Europe/Minsk', preferences: Dict = None) -> bool:
        """
        Добавляет или обновляет подписчика в базе данных.
        
        Args:
            chat_id: ID чата в Telegram
            username: Имя пользователя (username)
            full_name: Полное имя пользователя
            timezone: Часовой пояс пользователя
            preferences: Словарь с предпочтениями пользователя
            
        Returns:
            bool: True в случае успеха, иначе False
        """
        with self._lock:
            try:
                conn = sqlite3.connect(self.db_path)
                cursor = conn.cursor()
                
                # Преобразуем preferences в JSON
                prefs_json = self._dict_to_json(preferences or {})
                
                # Проверяем, существует ли уже этот пользователь
                cursor.execute("SELECT subscribed FROM subscribers WHERE chat_id = ?", (chat_id,))
                row = cursor.fetchone()
                
                if row is not None:
                    # Пользователь существует, обновляем данные и статус подписки
                    cursor.execute(
                        "UPDATE subscribers SET username = ?, full_name = ?, subscribed = 1, "
                        "subscription_date = CURRENT_TIMESTAMP, user_timezone = ?, "
                        "user_preferences = ? WHERE chat_id = ?",
                        (username, full_name, timezone, prefs_json, chat_id)
                    )
                else:
                    # Новый пользователь
                    cursor.execute(
                        "INSERT INTO subscribers (chat_id, username, full_name, subscribed, user_timezone, user_preferences) "
                        "VALUES (?, ?, ?, 1, ?, ?)",
                        (chat_id, username, full_name, timezone, prefs_json)
                    )
                
                # Записываем действие в статистику
                cursor.execute(
                    "INSERT INTO usage_stats (action_type, details, user_id) VALUES (?, ?, ?)",
                    ("subscribe", f"User {username} ({full_name}) subscribed", chat_id)
                )
                
                conn.commit()
                conn.close()
                logger.info(f"Пользователь {username} ({chat_id}) успешно подписан")
                return True
            except Exception as e:
                logger.error(f"Ошибка при добавлении подписчика: {str(e)}")
                return False
    
    def remove_subscriber(self, chat_id: int) -> bool:
        """
        Отписывает пользователя (устанавливает subscribed = 0).
        
        Args:
            chat_id: ID чата в Telegram
            
        Returns:
            bool: True в случае успеха, иначе False
        """
        with self._lock:
            try:
                conn = sqlite3.connect(self.db_path)
                cursor = conn.cursor()
                
                # Получаем информацию о пользователе для лога
                cursor.execute("SELECT username, full_name FROM subscribers WHERE chat_id = ?", (chat_id,))
                row = cursor.fetchone()
                username = row[0] if row else "Unknown"
                full_name = row[1] if row else "Unknown"
                
                # Отписываем пользователя
                cursor.execute("UPDATE subscribers SET subscribed = 0 WHERE chat_id = ?", (chat_id,))
                
                # Записываем действие в статистику
                cursor.execute(
                    "INSERT INTO usage_stats (action_type, details, user_id) VALUES (?, ?, ?)",
                    ("unsubscribe", f"User {username} ({full_name}) unsubscribed", chat_id)
                )
                
                conn.commit()
                conn.close()
                logger.info(f"Пользователь {username} ({chat_id}) отписан")
                return True
            except Exception as e:
                logger.error(f"Ошибка при отписке пользователя: {str(e)}")
                return False
    
    def get_subscribers(self) -> List[Tuple[int, str, str]]:
        """
        Получает список активных подписчиков.
        
        Returns:
            List[Tuple[int, str, str]]: Список подписчиков (chat_id, username, full_name)
        """
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            cursor.execute("SELECT chat_id, username, full_name FROM subscribers WHERE subscribed = 1")
            subscribers = cursor.fetchall()
            conn.close()
            return subscribers
        except Exception as e:
            logger.error(f"Ошибка при получении списка подписчиков: {str(e)}")
            return []
    
    def get_subscriber_count(self) -> int:
        """
        Получает количество активных подписчиков.
        
        Returns:
            int: Количество подписчиков
        """
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) FROM subscribers WHERE subscribed = 1")
            count = cursor.fetchone()[0]
            conn.close()
            return count
        except Exception as e:
            logger.error(f"Ошибка при получении количества подписчиков: {str(e)}")
            return 0
    
    def save_broadcast(self, message_text: str, success_count: int, error_count: int, admin_id: int,
                       target_group: str = "all") -> bool:
        """
        Сохраняет информацию о выполненной рассылке.
        
        Args:
            message_text: Текст рассылки
            success_count: Количество успешных отправок
            error_count: Количество ошибок отправки
            admin_id: ID администратора, запустившего рассылку
            target_group: Целевая группа рассылки
            
        Returns:
            bool: True в случае успеха, иначе False
        """
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            cursor.execute(
                "INSERT INTO broadcast_history (message_text, success_count, error_count, admin_id, target_group) "
                "VALUES (?, ?, ?, ?, ?)",
                (message_text, success_count, error_count, admin_id, target_group)
            )
            conn.commit()
            conn.close()
            return True
        except Exception as e:
            logger.error(f"Ошибка при сохранении информации о рассылке: {str(e)}")
            return False
    
    def update_notification_stats(self, chat_id: int) -> bool:
        """
        Обновляет статистику уведомлений для пользователя.
        
        Args:
            chat_id: ID чата в Telegram
            
        Returns:
            bool: True в случае успеха, иначе False
        """
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            cursor.execute(
                "UPDATE subscribers SET last_notification_date = CURRENT_TIMESTAMP, "
                "notification_count = notification_count + 1 WHERE chat_id = ?",
                (chat_id,)
            )
            conn.commit()
            conn.close()
            return True
        except Exception as e:
            logger.error(f"Ошибка при обновлении статистики уведомлений: {str(e)}")
            return False
    
    def add_stat_record(self, action_type: str, details: str, user_id: int = None) -> bool:
        """
        Добавляет запись в таблицу статистики.
        
        Args:
            action_type: Тип действия (например, "upload", "update", "error")
            details: Детали действия
            user_id: ID пользователя (опционально)
            
        Returns:
            bool: True в случае успеха, иначе False
        """
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            cursor.execute(
                "INSERT INTO usage_stats (action_type, details, user_id) VALUES (?, ?, ?)",
                (action_type, details, user_id)
            )
            conn.commit()
            conn.close()
            return True
        except Exception as e:
            logger.error(f"Ошибка при добавлении записи статистики: {str(e)}")
            return False
    
    def get_broadcast_history(self, limit: int = 10) -> List[Dict[str, Any]]:
        """
        Получает историю рассылок.
        
        Args:
            limit: Максимальное количество записей
            
        Returns:
            List[Dict[str, Any]]: Список записей с информацией о рассылках
        """
        try:
            conn = sqlite3.connect(self.db_path)
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute(
                "SELECT id, message_text, sent_date, success_count, error_count, admin_id, target_group "
                "FROM broadcast_history ORDER BY sent_date DESC LIMIT ?",
                (limit,)
            )
            rows = cursor.fetchall()
            conn.close()
            
            return [dict(row) for row in rows]
        except Exception as e:
            logger.error(f"Ошибка при получении истории рассылок: {str(e)}")
            return []
    
    def get_usage_stats(self, action_type: str = None, limit: int = 100) -> List[Dict[str, Any]]:
        """
        Получает статистику использования.
        
        Args:
            action_type: Тип действия для фильтрации (опционально)
            limit: Максимальное количество записей
            
        Returns:
            List[Dict[str, Any]]: Список записей статистики
        """
        try:
            conn = sqlite3.connect(self.db_path)
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            
            if action_type:
                cursor.execute(
                    "SELECT id, action_type, action_date, details, user_id "
                    "FROM usage_stats WHERE action_type = ? ORDER BY action_date DESC LIMIT ?",
                    (action_type, limit)
                )
            else:
                cursor.execute(
                    "SELECT id, action_type, action_date, details, user_id "
                    "FROM usage_stats ORDER BY action_date DESC LIMIT ?",
                    (limit,)
                )
            
            rows = cursor.fetchall()
            conn.close()
            
            return [dict(row) for row in rows]
        except Exception as e:
            logger.error(f"Ошибка при получении статистики использования: {str(e)}")
            return []
    
    def get_active_subscribers_details(self) -> List[Dict[str, Any]]:
        """
        Получает подробную информацию об активных подписчиках.
        
        Returns:
            List[Dict[str, Any]]: Список подписчиков с детальной информацией
        """
        try:
            conn = sqlite3.connect(self.db_path)
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute(
                "SELECT chat_id, username, full_name, subscription_date, "
                "last_notification_date, notification_count, user_timezone, user_preferences "
                "FROM subscribers WHERE subscribed = 1 ORDER BY subscription_date DESC"
            )
            rows = cursor.fetchall()
            conn.close()
            
            result = []
            for row in rows:
                subscriber_data = dict(row)
                # Преобразуем JSON-строку предпочтений в словарь
                if 'user_preferences' in subscriber_data and subscriber_data['user_preferences']:
                    subscriber_data['user_preferences'] = self._json_to_dict(subscriber_data['user_preferences'])
                result.append(subscriber_data)
            
            return result
        except Exception as e:
            logger.error(f"Ошибка при получении подробной информации о подписчиках: {str(e)}")
            return []
    
    def clear_old_stats(self, days: int = 90) -> bool:
        """
        Удаляет старые записи статистики.
        
        Args:
            days: Количество дней, старше которых записи будут удалены
            
        Returns:
            bool: True в случае успеха, иначе False
        """
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            cursor.execute(
                "DELETE FROM usage_stats WHERE action_date < datetime('now', ?)",
                (f'-{days} days',)
            )
            deleted_count = cursor.rowcount
            conn.commit()
            conn.close()
            logger.info(f"Удалено {deleted_count} старых записей статистики (старше {days} дней)")
            return True
        except Exception as e:
            logger.error(f"Ошибка при очистке старой статистики: {str(e)}")
            return False
    
    def backup_database(self, backup_dir: str = None) -> Optional[str]:
        """
        Создает резервную копию базы данных.
        
        Args:
            backup_dir: Директория для сохранения резервной копии
            
        Returns:
            Optional[str]: Путь к созданной резервной копии или None в случае ошибки
        """
        try:
            # Если директория не указана, создаем директорию backups в текущей директории
            if not backup_dir:
                backup_dir = os.path.join(os.path.dirname(self.db_path), "backups")
            
            os.makedirs(backup_dir, exist_ok=True)
            
            # Создаем имя файла резервной копии с датой и временем
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            backup_filename = f"subscribers_backup_{timestamp}.db"
            backup_path = os.path.join(backup_dir, backup_filename)
            
            # Создаем резервную копию
            conn = sqlite3.connect(self.db_path)
            backup_conn = sqlite3.connect(backup_path)
            
            conn.backup(backup_conn)
            
            conn.close()
            backup_conn.close()
            
            logger.info(f"Создана резервная копия базы данных: {backup_path}")
            return backup_path
        except Exception as e:
            logger.error(f"Ошибка при создании резервной копии базы данных: {str(e)}")
            return None
    
    def restore_database(self, backup_path: str) -> bool:
        """
        Восстанавливает базу данных из резервной копии.
        
        Args:
            backup_path: Путь к файлу резервной копии
            
        Returns:
            bool: True в случае успеха, иначе False
        """
        try:
            if not os.path.exists(backup_path):
                logger.error(f"Файл резервной копии не найден: {backup_path}")
                return False
                
            # Сначала создаем резервную копию текущей базы данных
            self.backup_database()
            
            # Восстанавливаем из указанной резервной копии
            backup_conn = sqlite3.connect(backup_path)
            conn = sqlite3.connect(self.db_path)
            
            backup_conn.backup(conn)
            
            conn.close()
            backup_conn.close()
            
            logger.info(f"База данных успешно восстановлена из: {backup_path}")
            return True
        except Exception as e:
            logger.error(f"Ошибка при восстановлении базы данных: {str(e)}")
            return False
    
    def get_subscriber_stats(self) -> Dict[str, Any]:
        """
        Получает статистическую информацию о подписчиках.
        
        Returns:
            Dict[str, Any]: Словарь с статистикой
        """
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            # Общее количество подписчиков (активных и неактивных)
            cursor.execute("SELECT COUNT(*) FROM subscribers")
            total_count = cursor.fetchone()[0]
            
            # Количество активных подписчиков
            cursor.execute("SELECT COUNT(*) FROM subscribers WHERE subscribed = 1")
            active_count = cursor.fetchone()[0]
            
            # Количество отписавшихся пользователей
            cursor.execute("SELECT COUNT(*) FROM subscribers WHERE subscribed = 0")
            unsubscribed_count = cursor.fetchone()[0]
            
            # Новые подписчики за последние 7 дней
            cursor.execute(
                "SELECT COUNT(*) FROM subscribers WHERE subscription_date >= datetime('now', '-7 days')"
            )
            new_week_count = cursor.fetchone()[0]
            
            # Новые подписчики за последние 30 дней
            cursor.execute(
                "SELECT COUNT(*) FROM subscribers WHERE subscription_date >= datetime('now', '-30 days')"
            )
            new_month_count = cursor.fetchone()[0]
            
            # Общее количество отправленных уведомлений
            cursor.execute("SELECT SUM(notification_count) FROM subscribers")
            total_notifications = cursor.fetchone()[0] or 0
            
            conn.close()
            
            return {
                "total_subscribers": total_count,
                "active_subscribers": active_count,
                "unsubscribed": unsubscribed_count,
                "new_last_week": new_week_count,
                "new_last_month": new_month_count,
                "total_notifications": total_notifications,
                "stats_date": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            }
        except Exception as e:
            logger.error(f"Ошибка при получении статистики подписчиков: {str(e)}")
            return {
                "error": str(e),
                "stats_date": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            }
    # Методы для работы с группами подписчиков
    def create_group(self, group_name: str, description: str) -> bool:
        """
        Создает новую группу для подписчиков.
        
        Args:
            group_name: Название группы (уникальное)
            description: Описание группы
            
        Returns:
            bool: True в случае успеха, иначе False
        """
        with self._lock:
            try:
                conn = sqlite3.connect(self.db_path)
                cursor = conn.cursor()
                
                # Проверяем, существует ли уже группа с таким именем
                cursor.execute("SELECT id FROM subscriber_groups WHERE group_name = ?", (group_name,))
                if cursor.fetchone():
                    logger.warning(f"Группа с именем '{group_name}' уже существует")
                    conn.close()
                    return False
                
                # Создаем новую группу
                cursor.execute(
                    "INSERT INTO subscriber_groups (group_name, description) VALUES (?, ?)",
                    (group_name, description)
                )
                
                conn.commit()
                conn.close()
                logger.info(f"Создана новая группа подписчиков: {group_name}")
                return True
            except Exception as e:
                logger.error(f"Ошибка при создании группы подписчиков: {str(e)}")
                return False
    
    def add_subscriber_to_group(self, chat_id: int, group_name: str) -> bool:
        """
        Добавляет подписчика в группу.
        
        Args:
            chat_id: ID чата в Telegram
            group_name: Название группы
            
        Returns:
            bool: True в случае успеха, иначе False
        """
        with self._lock:
            try:
                conn = sqlite3.connect(self.db_path)
                cursor = conn.cursor()
                
                # Получаем ID группы
                cursor.execute("SELECT id FROM subscriber_groups WHERE group_name = ?", (group_name,))
                group_row = cursor.fetchone()
                if not group_row:
                    logger.warning(f"Группа с именем '{group_name}' не найдена")
                    conn.close()
                    return False
                
                group_id = group_row[0]
                
                # Проверяем существование подписчика
                cursor.execute("SELECT chat_id FROM subscribers WHERE chat_id = ?", (chat_id,))
                if not cursor.fetchone():
                    logger.warning(f"Подписчик с ID {chat_id} не найден")
                    conn.close()
                    return False
                
                # Проверяем, не состоит ли уже подписчик в группе
                cursor.execute(
                    "SELECT 1 FROM subscriber_group_links WHERE chat_id = ? AND group_id = ?",
                    (chat_id, group_id)
                )
                if cursor.fetchone():
                    logger.info(f"Подписчик {chat_id} уже состоит в группе '{group_name}'")
                    conn.close()
                    return True
                
                # Добавляем подписчика в группу
                cursor.execute(
                    "INSERT INTO subscriber_group_links (chat_id, group_id) VALUES (?, ?)",
                    (chat_id, group_id)
                )
                
                conn.commit()
                conn.close()
                logger.info(f"Подписчик {chat_id} добавлен в группу '{group_name}'")
                return True
            except Exception as e:
                logger.error(f"Ошибка при добавлении подписчика в группу: {str(e)}")
                return False
    
    def remove_subscriber_from_group(self, chat_id: int, group_name: str) -> bool:
        """
        Удаляет подписчика из группы.
        
        Args:
            chat_id: ID чата в Telegram
            group_name: Название группы
            
        Returns:
            bool: True в случае успеха, иначе False
        """
        with self._lock:
            try:
                conn = sqlite3.connect(self.db_path)
                cursor = conn.cursor()
                
                # Получаем ID группы
                cursor.execute("SELECT id FROM subscriber_groups WHERE group_name = ?", (group_name,))
                group_row = cursor.fetchone()
                if not group_row:
                    logger.warning(f"Группа с именем '{group_name}' не найдена")
                    conn.close()
                    return False
                
                group_id = group_row[0]
                
                # Удаляем подписчика из группы
                cursor.execute(
                    "DELETE FROM subscriber_group_links WHERE chat_id = ? AND group_id = ?",
                    (chat_id, group_id)
                )
                
                conn.commit()
                conn.close()
                logger.info(f"Подписчик {chat_id} удален из группы '{group_name}'")
                return True
            except Exception as e:
                logger.error(f"Ошибка при удалении подписчика из группы: {str(e)}")
                return False
    
    def get_subscriber_groups(self) -> List[Dict[str, Any]]:
        """
        Получает список всех групп подписчиков.
        
        Returns:
            List[Dict[str, Any]]: Список групп с их описаниями
        """
        try:
            conn = sqlite3.connect(self.db_path)
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            
            cursor.execute(
                "SELECT id, group_name, description, created_date FROM subscriber_groups ORDER BY group_name"
            )
            rows = cursor.fetchall()
            
            conn.close()
            return [dict(row) for row in rows]
        except Exception as e:
            logger.error(f"Ошибка при получении списка групп подписчиков: {str(e)}")
            return []
    
    def get_subscribers_in_group(self, group_name: str) -> List[Dict[str, Any]]:
        """
        Получает список подписчиков в группе.
        
        Args:
            group_name: Название группы
            
        Returns:
            List[Dict[str, Any]]: Список подписчиков в группе
        """
        try:
            conn = sqlite3.connect(self.db_path)
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            
            cursor.execute("""
                SELECT s.chat_id, s.username, s.full_name, s.subscription_date, sgl.added_date
                FROM subscribers s
                JOIN subscriber_group_links sgl ON s.chat_id = sgl.chat_id
                JOIN subscriber_groups sg ON sgl.group_id = sg.id
                WHERE sg.group_name = ? AND s.subscribed = 1
                ORDER BY sgl.added_date DESC
            """, (group_name,))
            
            rows = cursor.fetchall()
            conn.close()
            
            return [dict(row) for row in rows]
        except Exception as e:
            logger.error(f"Ошибка при получении подписчиков из группы '{group_name}': {str(e)}")
            return []
    
    # Методы для работы с шаблонами сообщений
    def save_message_template(self, template_name: str, template_text: str, created_by: int) -> bool:
        """
        Сохраняет шаблон сообщения.
        
        Args:
            template_name: Название шаблона (уникальное)
            template_text: Текст шаблона сообщения
            created_by: ID пользователя, создавшего шаблон
            
        Returns:
            bool: True в случае успеха, иначе False
        """
        with self._lock:
            try:
                conn = sqlite3.connect(self.db_path)
                cursor = conn.cursor()
                
                # Проверяем, существует ли уже шаблон с таким именем
                cursor.execute("SELECT id FROM message_templates WHERE template_name = ?", (template_name,))
                row = cursor.fetchone()
                
                if row:
                    # Обновляем существующий шаблон
                    cursor.execute(
                        "UPDATE message_templates SET template_text = ? WHERE id = ?",
                        (template_text, row[0])
                    )
                else:
                    # Создаем новый шаблон
                    cursor.execute(
                        "INSERT INTO message_templates (template_name, template_text, created_by) VALUES (?, ?, ?)",
                        (template_name, template_text, created_by)
                    )
                
                conn.commit()
                conn.close()
                logger.info(f"Шаблон сообщения '{template_name}' сохранен")
                return True
            except Exception as e:
                logger.error(f"Ошибка при сохранении шаблона сообщения: {str(e)}")
                return False
    
    def get_message_template(self, template_name: str) -> Optional[Dict[str, Any]]:
        """
        Получает шаблон сообщения по названию.
        
        Args:
            template_name: Название шаблона
            
        Returns:
            Optional[Dict[str, Any]]: Информация о шаблоне или None, если шаблон не найден
        """
        try:
            conn = sqlite3.connect(self.db_path)
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            
            cursor.execute(
                "SELECT id, template_name, template_text, created_by, created_date, last_used_date "
                "FROM message_templates WHERE template_name = ?",
                (template_name,)
            )
            
            row = cursor.fetchone()
            conn.close()
            
            if row:
                # Обновляем дату последнего использования
                self.update_template_usage(template_name)
                return dict(row)
            return None
        except Exception as e:
            logger.error(f"Ошибка при получении шаблона сообщения '{template_name}': {str(e)}")
            return None
    
    def update_template_usage(self, template_name: str) -> bool:
        """
        Обновляет дату последнего использования шаблона.
        
        Args:
            template_name: Название шаблона
            
        Returns:
            bool: True в случае успеха, иначе False
        """
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            cursor.execute(
                "UPDATE message_templates SET last_used_date = CURRENT_TIMESTAMP WHERE template_name = ?",
                (template_name,)
            )
            
            conn.commit()
            conn.close()
            return True
        except Exception as e:
            logger.error(f"Ошибка при обновлении даты использования шаблона: {str(e)}")
            return False
    
    def list_message_templates(self) -> List[Dict[str, Any]]:
        """
        Получает список всех шаблонов сообщений.
        
        Returns:
            List[Dict[str, Any]]: Список шаблонов
        """
        try:
            conn = sqlite3.connect(self.db_path)
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            
            cursor.execute(
                "SELECT id, template_name, template_text, created_by, created_date, last_used_date "
                "FROM message_templates ORDER BY template_name"
            )
            
            rows = cursor.fetchall()
            conn.close()
            
            return [dict(row) for row in rows]
        except Exception as e:
            logger.error(f"Ошибка при получении списка шаблонов сообщений: {str(e)}")
            return []
    
    def delete_message_template(self, template_name: str) -> bool:
        """
        Удаляет шаблон сообщения.
        
        Args:
            template_name: Название шаблона
            
        Returns:
            bool: True в случае успеха, иначе False
        """
        with self._lock:
            try:
                conn = sqlite3.connect(self.db_path)
                cursor = conn.cursor()
                
                cursor.execute("DELETE FROM message_templates WHERE template_name = ?", (template_name,))
                
                deleted = cursor.rowcount > 0
                conn.commit()
                conn.close()
                
                if deleted:
                    logger.info(f"Шаблон сообщения '{template_name}' удален")
                else:
                    logger.warning(f"Шаблон сообщения '{template_name}' не найден")
                
                return deleted
            except Exception as e:
                logger.error(f"Ошибка при удалении шаблона сообщения: {str(e)}")
                return False
    
    # Методы для запланированных рассылок
    def schedule_broadcast(self, message_text: str, scheduled_date: str, 
                           target_group: str, admin_id: int) -> bool:
        """
        Планирует рассылку сообщений.
        
        Args:
            message_text: Текст сообщения
            scheduled_date: Дата и время рассылки (формат: 'YYYY-MM-DD HH:MM:SS')
            target_group: Название целевой группы или 'all' для всех
            admin_id: ID администратора, создавшего рассылку
            
        Returns:
            bool: True в случае успеха, иначе False
        """
        with self._lock:
            try:
                conn = sqlite3.connect(self.db_path)
                cursor = conn.cursor()
                
                cursor.execute(
                    "INSERT INTO scheduled_broadcasts (message_text, scheduled_date, target_group, admin_id) "
                    "VALUES (?, ?, ?, ?)",
                    (message_text, scheduled_date, target_group, admin_id)
                )
                
                broadcast_id = cursor.lastrowid
                conn.commit()
                conn.close()
                
                logger.info(f"Запланирована рассылка #{broadcast_id} на {scheduled_date} для группы '{target_group}'")
                return True
            except Exception as e:
                logger.error(f"Ошибка при планировании рассылки: {str(e)}")
                return False
    
    def get_pending_broadcasts(self) -> List[Dict[str, Any]]:
        """
        Получает список запланированных рассылок, ожидающих отправки.
        
        Returns:
            List[Dict[str, Any]]: Список запланированных рассылок
        """
        try:
            conn = sqlite3.connect(self.db_path)
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            
            cursor.execute(
                "SELECT id, message_text, scheduled_date, target_group, admin_id, created_date "
                "FROM scheduled_broadcasts "
                "WHERE status = 'pending' AND scheduled_date <= datetime('now', 'localtime') "
                "ORDER BY scheduled_date"
            )
            
            rows = cursor.fetchall()
            conn.close()
            
            return [dict(row) for row in rows]
        except Exception as e:
            logger.error(f"Ошибка при получении запланированных рассылок: {str(e)}")
            return []
    
    def update_broadcast_status(self, broadcast_id: int, status: str) -> bool:
        """
        Обновляет статус запланированной рассылки.
        
        Args:
            broadcast_id: ID рассылки
            status: Новый статус ('completed', 'failed', 'canceled')
            
        Returns:
            bool: True в случае успеха, иначе False
        """
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            cursor.execute(
                "UPDATE scheduled_broadcasts SET status = ?, completed_date = CURRENT_TIMESTAMP "
                "WHERE id = ?",
                (status, broadcast_id)
            )
            
            conn.commit()
            conn.close()
            
            logger.info(f"Обновлен статус рассылки #{broadcast_id}: {status}")
            return True
        except Exception as e:
            logger.error(f"Ошибка при обновлении статуса рассылки: {str(e)}")
            return False
    
    def cancel_broadcast(self, broadcast_id: int) -> bool:
        """
        Отменяет запланированную рассылку.
        
        Args:
            broadcast_id: ID рассылки
            
        Returns:
            bool: True в случае успеха, иначе False
        """
        return self.update_broadcast_status(broadcast_id, 'canceled')
    
    # Методы для экспорта/импорта данных
    def export_subscribers_to_csv(self, output_path: str, active_only: bool = True) -> bool:
        """
        Экспортирует список подписчиков в CSV-файл.
        
        Args:
            output_path: Путь для сохранения CSV-файла
            active_only: Экспортировать только активных подписчиков
            
        Returns:
            bool: True в случае успеха, иначе False
        """
        try:
            conn = sqlite3.connect(self.db_path)
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            
            if active_only:
                cursor.execute(
                    "SELECT chat_id, username, full_name, subscription_date, "
                    "last_notification_date, notification_count "
                    "FROM subscribers WHERE subscribed = 1 ORDER BY subscription_date"
                )
            else:
                cursor.execute(
                    "SELECT chat_id, username, full_name, subscribed, subscription_date, "
                    "last_notification_date, notification_count "
                    "FROM subscribers ORDER BY subscription_date"
                )
            
            rows = cursor.fetchall()
            conn.close()
            
            if not rows:
                logger.warning("Нет данных для экспорта в CSV")
                return False
            
            # Создаем директорию для экспорта, если она не существует
            os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
            
            with open(output_path, 'w', newline='', encoding='utf-8') as csv_file:
                writer = csv.writer(csv_file)
                
                # Записываем заголовки
                writer.writerow([key for key in dict(rows[0]).keys()])
                
                # Записываем данные
                for row in rows:
                    writer.writerow([value for value in dict(row).values()])
            
            logger.info(f"Список подписчиков экспортирован в CSV: {output_path}")
            return True
        except Exception as e:
            logger.error(f"Ошибка при экспорте подписчиков в CSV: {str(e)}")
            return False
    
    def export_subscribers_to_json(self, output_path: str, active_only: bool = True) -> bool:
        """
        Экспортирует список подписчиков в JSON-файл.
        
        Args:
            output_path: Путь для сохранения JSON-файла
            active_only: Экспортировать только активных подписчиков
            
        Returns:
            bool: True в случае успеха, иначе False
        """
        try:
            conn = sqlite3.connect(self.db_path)
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            
            if active_only:
                cursor.execute(
                    "SELECT chat_id, username, full_name, subscription_date, "
                    "last_notification_date, notification_count "
                    "FROM subscribers WHERE subscribed = 1 ORDER BY subscription_date"
                )
            else:
                cursor.execute(
                    "SELECT chat_id, username, full_name, subscribed, subscription_date, "
                    "last_notification_date, notification_count "
                    "FROM subscribers ORDER BY subscription_date"
                )
            
            rows = cursor.fetchall()
            conn.close()
            
            if not rows:
                logger.warning("Нет данных для экспорта в JSON")
                return False
            
            # Преобразуем данные в список словарей
            subscribers_data = [dict(row) for row in rows]
            
            # Создаем директорию для экспорта, если она не существует
            os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
            
            # Записываем в JSON-файл
            with open(output_path, 'w', encoding='utf-8') as json_file:
                json.dump(subscribers_data, json_file, ensure_ascii=False, indent=4, default=str)
            
            logger.info(f"Список подписчиков экспортирован в JSON: {output_path}")
            return True
        except Exception as e:
            logger.error(f"Ошибка при экспорте подписчиков в JSON: {str(e)}")
            return False
    
    def import_subscribers_from_csv(self, csv_path: str) -> Tuple[int, int]:
        """
        Импортирует подписчиков из CSV-файла.
        
        Args:
            csv_path: Путь к CSV-файлу
            
        Returns:
            Tuple[int, int]: (количество успешно импортированных, количество ошибок)
        """
        try:
            if not os.path.exists(csv_path):
                logger.error(f"Файл CSV не найден: {csv_path}")
                return 0, 0
            
            success_count = 0
            error_count = 0
            
            # Открываем соединение с базой данных один раз для всех операций
            conn = sqlite3.connect(self.db_path)
            
            with open(csv_path, 'r', encoding='utf-8') as csv_file:
                reader = csv.DictReader(csv_file)
                
                for row in reader:
                    try:
                        chat_id = int(row.get('chat_id', 0))
                        username = row.get('username', '')
                        full_name = row.get('full_name', '')
                        subscribed = int(row.get('subscribed', 1))
                        
                        if chat_id <= 0:
                            logger.warning(f"Пропуск строки с неверным chat_id: {row}")
                            error_count += 1
                            continue
                        
                        # Добавляем или обновляем подписчика
                        cursor = conn.cursor()
                        cursor.execute(
                            "INSERT OR REPLACE INTO subscribers (chat_id, username, full_name, subscribed) "
                            "VALUES (?, ?, ?, ?)",
                            (chat_id, username, full_name, subscribed)
                        )
                        conn.commit()
                        
                        success_count += 1
                    except Exception as e:
                        logger.error(f"Ошибка при импорте строки {row}: {str(e)}")
                        error_count += 1
            
            # Закрываем соединение после всех операций
            conn.close()
            
            logger.info(
                f"Импорт из CSV завершен. Успешно: {success_count}, Ошибок: {error_count}"
            )
            return success_count, error_count
        except Exception as e:
            logger.error(f"Ошибка при импорте подписчиков из CSV: {str(e)}")
            return 0, 1
    
    def import_subscribers_from_json(self, json_path: str) -> Tuple[int, int]:
        """
        Импортирует подписчиков из JSON-файла.
        
        Args:
            json_path: Путь к JSON-файлу
            
        Returns:
            Tuple[int, int]: (количество успешно импортированных, количество ошибок)
        """
        try:
            if not os.path.exists(json_path):
                logger.error(f"Файл JSON не найден: {json_path}")
                return 0, 0
            
            with open(json_path, 'r', encoding='utf-8') as json_file:
                subscribers_data = json.load(json_file)
            
            success_count = 0
            error_count = 0
            
            # Открываем соединение с базой данных один раз для всех операций
            conn = sqlite3.connect(self.db_path)
            
            for subscriber in subscribers_data:
                try:
                    chat_id = int(subscriber.get('chat_id', 0))
                    username = subscriber.get('username', '')
                    full_name = subscriber.get('full_name', '')
                    subscribed = int(subscriber.get('subscribed', 1))
                    
                    if chat_id <= 0:
                        logger.warning(f"Пропуск записи с неверным chat_id: {subscriber}")
                        error_count += 1
                        continue
                    
                    # Добавляем или обновляем подписчика
                    cursor = conn.cursor()
                    cursor.execute(
                        "INSERT OR REPLACE INTO subscribers (chat_id, username, full_name, subscribed) "
                        "VALUES (?, ?, ?, ?)",
                        (chat_id, username, full_name, subscribed)
                    )
                    conn.commit()
                    
                    success_count += 1
                except Exception as e:
                    logger.error(f"Ошибка при импорте записи {subscriber}: {str(e)}")
                    error_count += 1
            
            # Закрываем соединение после всех операций
            conn.close()
            
            logger.info(
                f"Импорт из JSON завершен. Успешно: {success_count}, Ошибок: {error_count}"
            )
            return success_count, error_count
        except Exception as e:
            logger.error(f"Ошибка при импорте подписчиков из JSON: {str(e)}")
            return 0, 1
    
    # Дополнительные методы для анализа данных
    def get_subscriber_activity_stats(self, days: int = 30) -> Dict[str, Any]:
        """
        Получает статистику активности подписчиков за указанный период.
        
        Args:
            days: Количество дней для анализа
            
        Returns:
            Dict[str, Any]: Статистика активности
        """
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            # Подписчики, получившие уведомления за период
            cursor.execute(
                "SELECT COUNT(DISTINCT chat_id) FROM subscribers "
                "WHERE last_notification_date >= datetime('now', ?) AND subscribed = 1",
                (f'-{days} days',)
            )
            active_subscribers = cursor.fetchone()[0] or 0
            
            # Общее количество уведомлений за период
            cursor.execute(
                "SELECT COUNT(*) FROM usage_stats "
                "WHERE action_type = 'notification' AND action_date >= datetime('now', ?)",
                (f'-{days} days',)
            )
            total_notifications = cursor.fetchone()[0] or 0
            
            # Новые подписчики за период
            cursor.execute(
                "SELECT COUNT(*) FROM subscribers "
                "WHERE subscription_date >= datetime('now', ?)",
                (f'-{days} days',)
            )
            new_subscribers = cursor.fetchone()[0] or 0
            
            # Отписавшиеся за период
            cursor.execute(
                "SELECT COUNT(*) FROM usage_stats "
                "WHERE action_type = 'unsubscribe' AND action_date >= datetime('now', ?)",
                (f'-{days} days',)
            )
            unsubscribed = cursor.fetchone()[0] or 0
            
            conn.close()
            
            return {
                "period_days": days,
                "active_subscribers": active_subscribers,
                "total_notifications": total_notifications,
                "new_subscribers": new_subscribers,
                "unsubscribed": unsubscribed,
                "stats_date": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            }
        except Exception as e:
            logger.error(f"Ошибка при получении статистики активности: {str(e)}")
            return {
                "error": str(e),
                "stats_date": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            }
    
    def get_database_size(self) -> Dict[str, Any]:
        """
        Получает информацию о размере базы данных.
        
        Returns:
            Dict[str, Any]: Информация о размере базы данных
        """
        try:
            db_size = os.path.getsize(self.db_path)
            
            # Получаем размер в МБ
            db_size_mb = db_size / (1024 * 1024)
            
            # Получаем количество записей в основных таблицах
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            tables = {
                "subscribers": "SELECT COUNT(*) FROM subscribers",
                "broadcast_history": "SELECT COUNT(*) FROM broadcast_history",
                "usage_stats": "SELECT COUNT(*) FROM usage_stats",
                "subscriber_groups": "SELECT COUNT(*) FROM subscriber_groups",
                "message_templates": "SELECT COUNT(*) FROM message_templates",
                "scheduled_broadcasts": "SELECT COUNT(*) FROM scheduled_broadcasts"
            }
            
            records_count = {}
            for table_name, query in tables.items():
                try:
                    cursor.execute(query)
                    records_count[table_name] = cursor.fetchone()[0]
                except sqlite3.OperationalError:
                    # Таблица может отсутствовать
                    records_count[table_name] = 0
            
            conn.close()
            
            return {
                "db_path": self.db_path,
                "size_bytes": db_size,
                "size_mb": round(db_size_mb, 2),
                "records_count": records_count,
                "last_backup": self._get_last_backup_date(),
                "stats_date": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            }
        except Exception as e:
            logger.error(f"Ошибка при получении информации о размере базы данных: {str(e)}")
            return {
                "error": str(e),
                "stats_date": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            }
    
    def _get_last_backup_date(self) -> Optional[str]:
        """
        Получает дату последнего резервного копирования.
        
        Returns:
            Optional[str]: Дата последнего бэкапа или None
        """
        try:
            backup_dir = os.path.join(os.path.dirname(self.db_path), "backups")
            if not os.path.exists(backup_dir):
                return None
                
            backup_files = [
                os.path.join(backup_dir, f) for f in os.listdir(backup_dir)
                if f.startswith("subscribers_backup_")
            ]
            
            if not backup_files:
                return None
                
            # Находим самый новый файл
            latest_backup = max(backup_files, key=os.path.getmtime)
            
            # Получаем дату создания файла
            backup_date = datetime.fromtimestamp(os.path.getmtime(latest_backup))
            return backup_date.strftime("%Y-%m-%d %H:%M:%S")
        except Exception as e:
            logger.error(f"Ошибка при получении даты последнего бэкапа: {str(e)}")
            return None
    
    def cleanup_database(self, days_to_keep_stats: int = 90,
                         max_backups: int = 10,
                         vacuum: bool = True) -> Dict[str, Any]:
        """
        Выполняет очистку и оптимизацию базы данных.
        
        Args:
            days_to_keep_stats: Количество дней для хранения статистики
            max_backups: Максимальное количество резервных копий
            vacuum: Выполнить VACUUM для оптимизации базы данных
            
        Returns:
            Dict[str, Any]: Результаты операции
        """
        with self._lock:
            try:
                results = {
                    "stats_deleted": 0,
                    "backups_deleted": 0,
                    "vacuum_performed": False,
                    "errors": []
                }
                
                conn = None
                
                # 1. Очистка старой статистики
                try:
                    conn = sqlite3.connect(self.db_path)
                    cursor = conn.cursor()
                    
                    cursor.execute(
                        "DELETE FROM usage_stats WHERE action_date < datetime('now', ?)",
                        (f'-{days_to_keep_stats} days',)
                    )
                    
                    results["stats_deleted"] = cursor.rowcount
                    conn.commit()
                except Exception as e:
                    error_msg = f"Ошибка при очистке статистики: {str(e)}"
                    logger.error(error_msg)
                    results["errors"].append(error_msg)
                
                # 2. Удаление старых резервных копий
                try:
                    backup_dir = os.path.join(os.path.dirname(self.db_path), "backups")
                    if os.path.exists(backup_dir):
                        backup_files = [
                            os.path.join(backup_dir, f) for f in os.listdir(backup_dir)
                            if f.startswith("subscribers_backup_")
                        ]
                        
                        if len(backup_files) > max_backups:
                            # Сортируем по времени создания (старые в начале)
                            backup_files.sort(key=os.path.getmtime)
                            
                            # Удаляем лишние (старые) файлы
                            files_to_delete = backup_files[:-max_backups]
                            for file_path in files_to_delete:
                                os.remove(file_path)
                                results["backups_deleted"] += 1
                except Exception as e:
                    error_msg = f"Ошибка при удалении старых резервных копий: {str(e)}"
                    logger.error(error_msg)
                    results["errors"].append(error_msg)
                
                # 3. Оптимизация базы данных (VACUUM)
                if vacuum and conn:
                    try:
                        conn.execute("VACUUM")
                        results["vacuum_performed"] = True
                    except Exception as e:
                        error_msg = f"Ошибка при выполнении VACUUM: {str(e)}"
                        logger.error(error_msg)
                        results["errors"].append(error_msg)
                
                # Закрываем соединение с базой данных, если оно было открыто
                if conn:
                    conn.close()
                
                logger.info(
                    f"Очистка базы данных завершена. Удалено записей статистики: {results['stats_deleted']}, "
                    f"удалено резервных копий: {results['backups_deleted']}"
                )
                
                return results
            except Exception as e:
                logger.error(f"Ошибка при очистке базы данных: {str(e)}")
                return {
                    "error": str(e),
                    "stats_date": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                }


# Для тестирования модуля при непосредственном запуске
if __name__ == "__main__":
    # Настройка логирования для тестирования
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    )
    
    # Пример использования
    print("Тестирование модуля для работы с базой данных подписчиков")
    
    # Создаем временную базу данных для теста
    test_db_path = "test_subscribers.db"
    if os.path.exists(test_db_path):
        os.remove(test_db_path)
    
    try:
        db = SubscriberDatabase(test_db_path)
        
        # Добавляем тестовых подписчиков
        print("Добавление тестовых подписчиков...")
        db.add_subscriber(123456, "test_user1", "Test User 1")
        db.add_subscriber(234567, "test_user2", "Test User 2")
        db.add_subscriber(345678, "test_user3", "Test User 3")
        
        # Проверяем количество подписчиков
        print(f"Количество подписчиков: {db.get_subscriber_count()}")
        
        # Получаем список подписчиков
        subscribers = db.get_subscribers()
        print("Список подписчиков:")
        for chat_id, username, full_name in subscribers:
            print(f"  - {full_name} (@{username}) - ID: {chat_id}")
        
        # Отписываем одного подписчика
        print("Отписываем одного подписчика...")
        db.remove_subscriber(234567)
        print(f"Количество подписчиков после отписки: {db.get_subscriber_count()}")
        
        # Добавляем статистику
        db.add_stat_record("test", "Test action", 123456)
        
        # Создаем резервную копию
        backup_path = db.backup_database()
        print(f"Резервная копия создана: {backup_path}")
        
        # Создаем группу и добавляем в нее подписчика
        print("Создаем группу и добавляем в нее подписчика...")
        db.create_group("test_group", "Test Group Description")
        db.add_subscriber_to_group(123456, "test_group")
        
        # Сохраняем шаблон сообщения
        print("Сохраняем тестовый шаблон сообщения...")
        db.save_message_template("welcome", "Привет, {{name}}! Добро пожаловать!", 123456)
        
        # Получаем статистику подписчиков
        stats = db.get_subscriber_stats()
        print("Статистика подписчиков:")
        for key, value in stats.items():
            print(f"  - {key}: {value}")
        
        # Экспортируем подписчиков в CSV и JSON
        print("Экспорт данных...")
        db.export_subscribers_to_csv("test_export.csv")
        db.export_subscribers_to_json("test_export.json")
        
        # Планируем рассылку
        print("Планирование тестовой рассылки...")
        scheduled_date = (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%d %H:%M:%S")
        db.schedule_broadcast("Тестовое сообщение", scheduled_date, "all", 123456)
        
        # Получаем информацию о базе данных
        db_info = db.get_database_size()
        print("Информация о базе данных:")
        for key, value in db_info.items():
            if key != "records_count":
                print(f"  - {key}: {value}")
            else:
                print("  - records_count:")
                for table, count in value.items():
                    print(f"      {table}: {count}")
        
        # Проверяем очистку базы данных
        print("Тестирование очистки базы данных...")
        cleanup_results = db.cleanup_database()
        print("Результаты очистки базы данных:")
        for key, value in cleanup_results.items():
            print(f"  - {key}: {value}")
        
        print("Тест потокобезопасности...")
        # Тестирование потокобезопасности
        def test_thread(thread_id):
            for i in range(5):
                print(f"Thread {thread_id} добавляет подписчика {i}")
                db.add_subscriber(thread_id * 1000 + i, f"thread_user_{thread_id}_{i}", f"Thread {thread_id} User {i}")
                time.sleep(0.1)
        
        threads = []
        for i in range(3):
            t = threading.Thread(target=test_thread, args=(i,))
            threads.append(t)
            t.start()
            
        for t in threads:
            t.join()
            
        print(f"Итоговое количество подписчиков после теста потоков: {db.get_subscriber_count()}")
        
    finally:
        # Удаляем тестовую базу данных
        if os.path.exists(test_db_path):
            os.remove(test_db_path)
        
        # Удаляем резервные копии, если они были созданы
        backup_dir = os.path.join(os.path.dirname(test_db_path), "backups")
        if os.path.exists(backup_dir):
            for file in os.listdir(backup_dir):
                if file.startswith("subscribers_backup_"):
                    os.remove(os.path.join(backup_dir, file))
            os.rmdir(backup_dir)
            
        # Удаляем тестовые экспортные файлы
        for test_file in ["test_export.csv", "test_export.json"]:
            if os.path.exists(test_file):
                os.remove(test_file)
    
    print("Тестирование завершено успешно")