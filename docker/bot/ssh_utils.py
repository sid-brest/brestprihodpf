"""
Модуль для работы с SSH соединениями и выполнения команд на удаленном сервере.
"""
import os
import asyncio
import logging
import asyncssh
from typing import Tuple, Optional, List, Dict, Any
from dotenv import load_dotenv

# Загружаем переменные окружения
load_dotenv()

# Настройка логирования
logger = logging.getLogger(__name__)

# Константы для подключения
HOSTING_PATH = os.environ.get("HOSTING_PATH", "")
HOSTING_CERT = os.environ.get("HOSTING_CERT", "")
HOSTING_PASSPHRASE = os.environ.get("HOSTING_PASSPHRASE", "")
HOSTING_DIR = os.environ.get("HOSTING_DIR", "/home/prihodpf/public_html")

class SSHClient:
    """Класс для работы с SSH соединениями"""
    
    def __init__(self, host: str = HOSTING_PATH, 
                 key_path: str = HOSTING_CERT,
                 passphrase: str = HOSTING_PASSPHRASE,
                 remote_dir: str = HOSTING_DIR):
        """
        Инициализация SSH клиента.
        
        Args:
            host: Хост в формате user@hostname
            key_path: Путь к приватному ключу
            passphrase: Пароль для приватного ключа
            remote_dir: Удаленная директория для работы
        """
        self.host = host
        self.key_path = key_path
        self.passphrase = passphrase
        self.remote_dir = remote_dir
        self.conn = None
    
    async def connect(self) -> Tuple[bool, str]:
        """
        Установка SSH соединения.
        
        Returns:
            Tuple[bool, str]: (успех, сообщение)
        """
        try:
            # Проверяем наличие ключа
            if not os.path.exists(self.key_path):
                logger.error(f"SSH ключ не найден: {self.key_path}")
                return False, f"SSH ключ не найден: {self.key_path}"
            
            # Устанавливаем соединение
            self.conn = await asyncssh.connect(
                host=self.host.split('@')[1] if '@' in self.host else self.host,
                username=self.host.split('@')[0] if '@' in self.host else None,
                client_keys=[self.key_path],
                passphrase=self.passphrase,
                known_hosts=None  # Отключаем проверку known_hosts
            )
            
            logger.info(f"SSH соединение успешно установлено с {self.host}")
            return True, "SSH соединение успешно установлено"
        except asyncssh.Error as e:
            logger.error(f"Ошибка при подключении по SSH: {str(e)}")
            return False, f"Ошибка при подключении по SSH: {str(e)}"
        except Exception as e:
            logger.error(f"Ошибка при установке SSH соединения: {str(e)}")
            return False, f"Ошибка при установке SSH соединения: {str(e)}"
    
    async def disconnect(self) -> None:
        """Закрытие SSH соединения."""
        if self.conn:
            self.conn.close()
            await self.conn.wait_closed()
            self.conn = None
            logger.info("SSH соединение закрыто")
    
    async def execute_command(self, command: str) -> Tuple[bool, str]:
        """
        Выполнение команды на удаленном сервере.
        
        Args:
            command: Команда для выполнения
            
        Returns:
            Tuple[bool, str]: (успех, результат/ошибка)
        """
        try:
            if not self.conn:
                success, message = await self.connect()
                if not success:
                    return False, message
            
            # Выполняем команду
            logger.info(f"Выполнение команды: {command}")
            result = await self.conn.run(command, check=True)
            
            # Логируем результат
            if result.stdout:
                logger.info(f"Результат выполнения команды: {result.stdout}")
            if result.stderr:
                logger.warning(f"Ошибка при выполнении команды: {result.stderr}")
            
            # Возвращаем результат выполнения
            if result.exit_status == 0:
                return True, result.stdout
            else:
                return False, result.stderr or "Команда завершилась с ошибкой"
        except asyncssh.ProcessError as e:
            logger.error(f"Ошибка процесса SSH: {str(e)}")
            return False, f"Ошибка процесса SSH: {str(e)}"
        except Exception as e:
            logger.error(f"Ошибка при выполнении команды: {str(e)}")
            return False, f"Ошибка при выполнении команды: {str(e)}"
        finally:
            # Закрываем соединение
            await self.disconnect()
    
    async def update_hosting_from_git(self) -> Tuple[bool, str]:
        """
        Обновляет файлы на хостинге из Git репозитория.
        
        Returns:
            Tuple[bool, str]: (успех, результат/ошибка)
        """
        # Команды для обновления хостинга
        commands = [
            f"cd {self.remote_dir} && git reset --hard",
            "git -C /home/prihodpf/repositories/brestprihodpf pull",
            "rsync -a --exclude={'.*/','*.sh*','.git*'} /home/prihodpf/repositories/brestprihodpf/ /home/prihodpf/public_html",
            "chmod 775 /home/prihodpf/public_html"
        ]
        
        results = []
        success = True
        
        for cmd in commands:
            cmd_success, cmd_result = await self.execute_command(cmd)
            if not cmd_success:
                success = False
            results.append(f"CMD: {cmd}\nРезультат: {cmd_result}\n")
        
        return success, "\n".join(results)

async def test_ssh_connection() -> Tuple[bool, str]:
    """
    Тестирование SSH соединения с параметрами из .env файла.
    
    Returns:
        Tuple[bool, str]: (успех, сообщение)
    """
    try:
        ssh_client = SSHClient()
        success, message = await ssh_client.connect()
        
        if success:
            # Выполняем простую команду
            test_success, test_result = await ssh_client.execute_command("echo 'SSH подключение работает!'")
            await ssh_client.disconnect()
            
            if test_success:
                return True, f"SSH соединение успешно установлено и проверено:\n{test_result}"
            else:
                return False, f"SSH соединение установлено, но тестовая команда завершилась с ошибкой:\n{test_result}"
        else:
            return False, message
    except Exception as e:
        logger.error(f"Ошибка при тестировании SSH соединения: {str(e)}")
        return False, f"Ошибка при тестировании SSH соединения: {str(e)}"

async def update_hosting() -> Tuple[bool, str]:
    """
    Обновление хостинга из Git репозитория.
    
    Returns:
        Tuple[bool, str]: (успех, результат/ошибка)
    """
    try:
        ssh_client = SSHClient()
        return await ssh_client.update_hosting_from_git()
    except Exception as e:
        logger.error(f"Ошибка при обновлении хостинга: {str(e)}")
        return False, f"Ошибка при обновлении хостинга: {str(e)}"

# Тестирование модуля
if __name__ == "__main__":
    # Настройка логирования
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    )
    
    # Тестирование SSH подключения
    print("Тестирование SSH подключения...")
    result = asyncio.run(test_ssh_connection())
    print(f"Результат: {result}")
    
    # Тестирование обновления хостинга
    print("Тестирование обновления хостинга...")
    update_result = asyncio.run(update_hosting())
    print(f"Результат обновления: {update_result}")