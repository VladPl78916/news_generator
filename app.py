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
    # Парсим HTML через BeautifulSoup
    soup = BeautifulSoup(html, 'html.parser')

    # Замена <strong>, <b>, <em>, <i>, <u>, <s>, <del>, <ins>
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

    # Обработка заголовков
    for h in soup.find_all(['h1', 'h2', 'h3']):
        h.name = 'b'  # Делаем жирным
        h.append(soup.new_tag('br'))  # Добавляем перенос строки после заголовка

    # Обработка параграфов
    for p in soup.find_all('p'):
        p.insert_after(soup.new_tag('br'))
        p.unwrap()  # Убираем <p>

    # Обработка списков
    for ul in soup.find_all('ul'):
        items = ul.find_all('li')
        new_content = ''
        for li in items:
            new_content += f'• {li.get_text(strip=False)}\n'
        new_tag = soup.new_tag('div')
        new_tag.string = new_content.strip()
        ul.replace_with(new_tag)

    for ol in soup.find_all('ol'):
        items = ol.find_all('li')
        new_content = ''
        for idx, li in enumerate(items, 1):
            new_content += f'{idx}. {li.get_text(strip=False)}\n'
        new_tag = soup.new_tag('div')
        new_tag.string = new_content.strip()
        ol.replace_with(new_tag)

    for li in soup.find_all('li'):
        li.unwrap()

    # Обработка тегов <br>
    for br in soup.find_all('br'):
        br.replace_with('\n')  # Замена <br> на \n

    # Добавление переноса строки перед и после списков
    for tag in soup.find_all(['ul', 'ol']):
        # Добавляем перевод строки перед списком
        if tag.previous_sibling and tag.previous_sibling.name not in ['br', 'p']:
            tag.insert_before(soup.new_tag('br'))

        # Добавляем перевод строки после списка
        if tag.next_sibling and tag.next_sibling.name not in ['br', 'p']:
            tag.insert_after(soup.new_tag('br'))

    # Обработка остальных тегов
    for tag in soup.find_all(True):
        if tag.name in allowed_tags:
            tag.name = allowed_tags[tag.name]
        else:
            tag.unwrap()  # Удаляем неподдерживаемые теги, оставляя текст

    # Склеиваем все в строку и чистим лишние пробелы/переводы
    cleaned_html = str(soup).replace('\r', '')
    cleaned_html = re.sub(r'\n{3,}', '\n\n', cleaned_html)  # Максимум два перевода строки
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