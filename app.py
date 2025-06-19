import os
import logging
import asyncio
from flask import Flask, render_template, request, jsonify
from dotenv import load_dotenv
from telegram import Bot, InputMediaPhoto
from telegram.error import TelegramError
from config import Config
from bs4 import BeautifulSoup
import re

load_dotenv()

app = Flask(__name__)
app.config.from_object(Config)
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

# Telegram конфигурация
TELEGRAM_TOKEN = os.getenv('TELEGRAM_TOKEN')
TELEGRAM_CHANNEL = os.getenv('TELEGRAM_CHANNEL')

def clean_telegram_html(html):
    # Удаляем теги <p> и заменяем их переносами строк
    html = re.sub(r'</?p[^>]*>', '\n', html)
    
    # Удаляем другие неподдерживаемые теги, оставляя только базовое форматирование
    soup = BeautifulSoup(html, 'html.parser')
    
    # Разрешенные теги и их преобразование
    allowed_tags = {
        'b': 'b',
        'strong': 'b',
        'i': 'i',
        'em': 'i',
        'u': 'u',
        'ins': 'u',
        's': 's',
        'strike': 's',
        'del': 's',
        'a': 'a',
        'code': 'code',
        'pre': 'pre'
    }
    
    for tag in soup.find_all(True):
        if tag.name not in allowed_tags:
            # Неподдерживаемый тег - заменяем его содержимым
            tag.unwrap()
        else:
            # Переименовываем теги в соответствии со стандартом Telegram
            tag.name = allowed_tags[tag.name]
    
    # Преобразуем обратно в строку и удаляем лишние переносы
    cleaned_html = str(soup)
    cleaned_html = re.sub(r'\n{3,}', '\n\n', cleaned_html)  # Убираем множественные переносы
    return cleaned_html.strip()

async def send_to_telegram(title, content, files):
    """Асинхронная функция для отправки сообщений в Telegram"""
    bot = Bot(token=TELEGRAM_TOKEN)
    
    cleaned_content = clean_telegram_html(content)
    message = f"<b>{title}</b>\n\n{cleaned_content}"
    
    if files:
        # Создаем медиагруппу
        media_group = []
        for i, file_path in enumerate(files):
            with open(file_path, 'rb') as file:
                # Добавляем подпись только к первому изображению
                if i == 0:
                    media_group.append(
                        InputMediaPhoto(
                            media=file,
                            caption=message,
                            parse_mode='HTML'
                        )
                    )
                else:
                    media_group.append(InputMediaPhoto(media=file))
        
        await bot.send_media_group(chat_id=TELEGRAM_CHANNEL, media=media_group)
    else:
        await bot.send_message(
            chat_id=TELEGRAM_CHANNEL,
            text=message,
            parse_mode='HTML'
        )

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/publish', methods=['POST'])
def publish():
    saved_files = []
    try:
        # Получаем данные формы
        title = request.form['title']
        content = request.form['content']
        platforms = request.form.getlist('platforms')
        files = request.files.getlist('photos')
        
        # Проверка платформ
        if 'telegram' not in platforms:
            return jsonify({'error': 'Поддержка только для Telegram в текущей реализации'}), 400
        
        # Валидация файлов
        if len(files) > Config.MAX_FILES:
            return jsonify({'error': f'Максимум {Config.MAX_FILES} файлов'}), 400
        
        for file in files:
            if file.filename == '':
                continue
            if file.content_length > Config.MAX_FILE_SIZE:
                return jsonify({'error': f'Файл {file.filename} превышает 30 МБ'}), 400
            if not any(file.filename.lower().endswith(ext) for ext in Config.ALLOWED_EXTENSIONS):
                return jsonify({'error': f'Недопустимый формат файла: {file.filename}'}), 400
            
            file_path = os.path.join(app.config['UPLOAD_FOLDER'], file.filename)
            file.save(file_path)
            saved_files.append(file_path)
        
        # Проверка конфигурации Telegram
        if not TELEGRAM_TOKEN or not TELEGRAM_CHANNEL:
            return jsonify({'error': 'Ошибка конфигурации Telegram'}), 500
        
        # Запускаем асинхронную отправку
        asyncio.run(send_to_telegram(title, content, saved_files))
        
        return jsonify({'success': 'Новость опубликована в Telegram'})
    
    except TelegramError as e:
        logging.error(f"Telegram error: {e}")
        return jsonify({'error': f'Ошибка Telegram: {e}'}), 500
    except Exception as e:
        logging.exception("Ошибка публикации")
        return jsonify({'error': str(e)}), 500
    finally:
        # Удаляем временные файлы
        for file_path in saved_files:
            try:
                os.remove(file_path)
            except OSError:
                pass

if __name__ == '__main__':
    app.run(debug=True, port=5001)