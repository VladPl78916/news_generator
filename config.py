import os

class Config:
    UPLOAD_FOLDER = 'static/uploads'
    ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif'}
    MAX_FILES = 4
    MAX_FILE_SIZE = 30 * 1024 * 1024  