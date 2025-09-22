#!/usr/bin/env python3
"""
Telegram бот для получения картинок и сохранения их в GitHub репозиторий
"""

import os
import json
import requests
import subprocess
import threading
from datetime import datetime
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
from http.server import HTTPServer, BaseHTTPRequestHandler

# Загружаем переменные окружения из .env файла
def load_env():
    env_file = '.env'
    if os.path.exists(env_file):
        with open(env_file, 'r') as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('#') and '=' in line:
                    key, value = line.split('=', 1)
                    os.environ[key] = value

load_env()

# Простой HTTP сервер для Render
class HealthHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == '/health':
            self.send_response(200)
            self.send_header('Content-type', 'text/plain')
            self.end_headers()
            self.wfile.write(b'Bot is running!')
        else:
            self.send_response(404)
            self.end_headers()

def start_http_server(port):
    """Запуск HTTP сервера для Render"""
    server = HTTPServer(('0.0.0.0', port), HealthHandler)
    print(f"🌐 HTTP сервер запущен на порту {port}")
    server.serve_forever()

# Конфигурация
BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')
GITHUB_TOKEN = os.getenv('GITHUB_TOKEN')
GITHUB_REPO = os.getenv('GITHUB_REPO', 'your-username/image-gallery')
GITHUB_USERNAME = os.getenv('GITHUB_USERNAME')
GITHUB_EMAIL = os.getenv('GITHUB_EMAIL')

# Папки (относительно корня репозитория)
IMAGES_DIR = '../images'
METADATA_FILE = '../images.json'

class ImageBot:
    def __init__(self):
        self.app = Application.builder().token(BOT_TOKEN).build()
        self.setup_handlers()
    
    def setup_handlers(self):
        """Настройка обработчиков команд"""
        self.app.add_handler(CommandHandler("start", self.start_command))
        self.app.add_handler(CommandHandler("help", self.help_command))
        self.app.add_handler(MessageHandler(filters.PHOTO, self.handle_photo))
        self.app.add_handler(MessageHandler(filters.Document.IMAGE, self.handle_document))
    
    async def start_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработчик команды /start"""
        welcome_message = """
🖼️ Привет, отправь мемокартинку и над ней посмеётся человек 5 (или больше)
        """
        await update.message.reply_text(welcome_message)
    
    async def help_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработчик команды /help"""
        help_message = """
📖 Справка по использованию:

1. Отправьте картинку как фото или документ
2. Бот автоматически сохранит её в галерею
3. Картинка появится на сайте через несколько секунд

Поддерживаемые форматы: JPG, PNG, GIF, WebP

Сайт галереи: https://your-username.github.io/image-gallery
        """
        await update.message.reply_text(help_message)
    
    async def handle_photo(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработчик фотографий"""
        photo = update.message.photo[-1]  # Берем фото наивысшего качества
        file_id = photo.file_id
        
        await self.process_image(update, context, file_id, 'photo')
    
    async def handle_document(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработчик документов (картинок)"""
        document = update.message.document
        
        # Проверяем, что это картинка
        if not document.mime_type.startswith('image/'):
            await update.message.reply_text("❌ Пожалуйста, отправьте картинку!")
            return
        
        await self.process_image(update, context, document.file_id, 'document')
    
    async def process_image(self, update: Update, context: ContextTypes.DEFAULT_TYPE, file_id: str, file_type: str):
        """Обработка и сохранение картинки"""
        try:
            # Показываем, что бот работает
            processing_msg = await update.message.reply_text("⏳ Обрабатываю картинку...")
            
            # Получаем файл
            file = await context.bot.get_file(file_id)
            
            # Генерируем имя файла
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            file_extension = self.get_file_extension(file.file_path)
            filename = f"image_{timestamp}{file_extension}"
            
            # Скачиваем файл
            file_path = os.path.join(IMAGES_DIR, filename)
            os.makedirs(IMAGES_DIR, exist_ok=True)
            
            await file.download_to_drive(file_path)
            
            # Обновляем метаданные
            await self.update_metadata(filename, update.message.from_user.username or "Anonymous")
            
            # Коммитим в GitHub
            await self.commit_to_github(filename)
            
            # Уведомляем пользователя
            await processing_msg.edit_text(
                f"✅ Прекол загружен, проверяй на сайте 🌐\n"
                f"https://evgn-ivanov.github.io/image-gallery/"
            )
            
        except Exception as e:
            await update.message.reply_text(f"❌ Ошибка при обработке картинки: {str(e)}")
    
    def get_file_extension(self, file_path: str) -> str:
        """Получение расширения файла"""
        if file_path.endswith('.jpg') or file_path.endswith('.jpeg'):
            return '.jpg'
        elif file_path.endswith('.png'):
            return '.png'
        elif file_path.endswith('.gif'):
            return '.gif'
        elif file_path.endswith('.webp'):
            return '.webp'
        else:
            return '.jpg'  # По умолчанию
    
    async def update_metadata(self, filename: str, username: str):
        """Обновление файла метаданных"""
        metadata = {
            "last_image": filename,
            "last_updated": datetime.now().isoformat(),
            "uploaded_by": username,
            "total_images": self.count_images()
        }
        
        with open(METADATA_FILE, 'w', encoding='utf-8') as f:
            json.dump(metadata, f, ensure_ascii=False, indent=2)
    
    def count_images(self) -> int:
        """Подсчет количества картинок"""
        if not os.path.exists(IMAGES_DIR):
            return 0
        
        image_extensions = ('.jpg', '.jpeg', '.png', '.gif', '.webp')
        count = 0
        for file in os.listdir(IMAGES_DIR):
            if file.lower().endswith(image_extensions):
                count += 1
        return count
    
    async def commit_to_github(self, filename: str):
        """Коммит изменений в GitHub"""
        try:
            # Переходим в корень репозитория
            repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            original_cwd = os.getcwd()
            os.chdir(repo_root)
            
            try:
                # Настраиваем git
                subprocess.run(['git', 'config', 'user.name', GITHUB_USERNAME], check=True)
                subprocess.run(['git', 'config', 'user.email', GITHUB_EMAIL], check=True)
                
                # Проверяем и настраиваем remote если нужно
                try:
                    subprocess.run(['git', 'remote', 'get-url', 'origin'], check=True, capture_output=True)
                except subprocess.CalledProcessError:
                    # Добавляем remote если его нет
                    remote_url = f"https://{GITHUB_USERNAME}:{GITHUB_TOKEN}@github.com/{GITHUB_REPO}.git"
                    subprocess.run(['git', 'remote', 'add', 'origin', remote_url], check=True)
                
                # Проверяем состояние HEAD и переключаемся на main если нужно
                try:
                    result = subprocess.run(['git', 'branch', '--show-current'], capture_output=True, text=True, check=True)
                    current_branch = result.stdout.strip()
                    if not current_branch or current_branch == '':
                        # Мы в detached HEAD, переключаемся на main
                        try:
                            subprocess.run(['git', 'checkout', 'main'], check=True)
                            print("Переключились на существующую ветку main")
                        except subprocess.CalledProcessError:
                            subprocess.run(['git', 'checkout', '-b', 'main'], check=True)
                            print("Создали новую ветку main")
                    elif current_branch != 'main':
                        # Переключаемся на main
                        subprocess.run(['git', 'checkout', 'main'], check=True)
                        print(f"Переключились с {current_branch} на main")
                except subprocess.CalledProcessError:
                    # Пытаемся переключиться на main, если не получается - создаем
                    try:
                        subprocess.run(['git', 'checkout', 'main'], check=True)
                        print("Переключились на существующую ветку main")
                    except subprocess.CalledProcessError:
                        subprocess.run(['git', 'checkout', '-b', 'main'], check=True)
                        print("Создали новую ветку main")
                
                # Сначала получаем последние изменения
                try:
                    subprocess.run(['git', 'pull', 'origin', 'main', '--rebase'], check=True)
                    print("Успешно получили последние изменения")
                except subprocess.CalledProcessError as e:
                    print(f"Ошибка при pull: {e}")
                    # Если pull не удался, делаем force push (осторожно!)
                    pass
                
                # Добавляем файлы
                subprocess.run(['git', 'add', '.'], check=True)
                
                # Коммитим
                commit_message = f"Add new image: {filename}"
                subprocess.run(['git', 'commit', '-m', commit_message], check=True)
                
                # Пушим
                try:
                    subprocess.run(['git', 'push', 'origin', 'main'], check=True)
                    print("Успешно отправили изменения")
                except subprocess.CalledProcessError as e:
                    print(f"Ошибка при push: {e}")
                    # Если push не удался, делаем force push
                    subprocess.run(['git', 'push', 'origin', 'main', '--force'], check=True)
                    print("Выполнили force push")
                
            finally:
                # Возвращаемся в исходную директорию
                os.chdir(original_cwd)
            
        except subprocess.CalledProcessError as e:
            print(f"Git error: {e}")
            print(f"Return code: {e.returncode}")
            print(f"Command: {e.cmd}")
            print(f"Output: {e.output}")
            raise Exception(f"Ошибка при сохранении в GitHub: {e}")
    
    def run(self):
        """Запуск бота"""
        print("🤖 Запуск Telegram бота...")
        
        # Принудительно завершаем все webhook'и
        try:
            import requests
            webhook_url = f"https://api.telegram.org/bot{BOT_TOKEN}/deleteWebhook"
            response = requests.post(webhook_url, data={'drop_pending_updates': True})
            print(f"Webhook удален: {response.status_code}")
        except Exception as e:
            print(f"Ошибка при удалении webhook: {e}")
        
        # Запускаем HTTP сервер в отдельном потоке для Render
        port = int(os.environ.get('PORT', 8000))
        http_thread = threading.Thread(target=start_http_server, args=(port,), daemon=True)
        http_thread.start()
        
        print(f"🌐 HTTP сервер запущен на порту {port}")
        print("🤖 Telegram бот запущен...")
        
        # Запускаем Telegram бота с обработкой ошибок
        max_retries = 3
        retry_count = 0
        
        while retry_count < max_retries:
            try:
                print(f"Попытка запуска бота #{retry_count + 1}")
                self.app.run_polling(drop_pending_updates=True, close_loop=False)
                break
            except Exception as e:
                retry_count += 1
                print(f"Ошибка при запуске бота (попытка {retry_count}): {e}")
                
                if "Conflict" in str(e) and "getUpdates" in str(e):
                    print("Обнаружен конфликт с другим экземпляром бота")
                    # Ждем дольше при конфликте
                    import time
                    time.sleep(10)
                else:
                    import time
                    time.sleep(5)
                
                if retry_count >= max_retries:
                    print("Достигнуто максимальное количество попыток. Бот остановлен.")
                    break
                else:
                    print("Перезапускаем бота...")

if __name__ == '__main__':
    # Проверяем переменные окружения
    required_vars = ['TELEGRAM_BOT_TOKEN', 'GITHUB_TOKEN', 'GITHUB_USERNAME', 'GITHUB_EMAIL']
    missing_vars = [var for var in required_vars if not os.getenv(var)]
    
    if missing_vars:
        print(f"❌ Отсутствуют переменные окружения: {', '.join(missing_vars)}")
        print("Создайте файл .env с необходимыми переменными")
        exit(1)
    
    bot = ImageBot()
    bot.run()
