#!/usr/bin/env python3
"""
Telegram бот для получения картинок и сохранения их в GitHub репозиторий
"""

import os
import json
import requests
import subprocess
from datetime import datetime
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes

# Конфигурация
BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')
GITHUB_TOKEN = os.getenv('GITHUB_TOKEN')
GITHUB_REPO = os.getenv('GITHUB_REPO', 'your-username/image-gallery')
GITHUB_USERNAME = os.getenv('GITHUB_USERNAME')
GITHUB_EMAIL = os.getenv('GITHUB_EMAIL')

# Папки
IMAGES_DIR = 'public/images'
METADATA_FILE = 'public/images.json'

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
🖼️ Добро пожаловать в Image Gallery Bot!

Просто отправьте мне картинку, и я добавлю её в галерею!

Команды:
/help - показать справку
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
                f"✅ Картинка успешно добавлена в галерею!\n\n"
                f"📁 Файл: {filename}\n"
                f"🌐 Сайт: https://your-username.github.io/image-gallery"
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
            # Настраиваем git
            subprocess.run(['git', 'config', 'user.name', GITHUB_USERNAME], check=True)
            subprocess.run(['git', 'config', 'user.email', GITHUB_EMAIL], check=True)
            
            # Добавляем файлы
            subprocess.run(['git', 'add', '.'], check=True)
            
            # Коммитим
            commit_message = f"Add new image: {filename}"
            subprocess.run(['git', 'commit', '-m', commit_message], check=True)
            
            # Пушим
            subprocess.run(['git', 'push', 'origin', 'main'], check=True)
            
        except subprocess.CalledProcessError as e:
            print(f"Git error: {e}")
            raise Exception("Ошибка при сохранении в GitHub")
    
    def run(self):
        """Запуск бота"""
        print("🤖 Запуск Telegram бота...")
        self.app.run_polling()

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
