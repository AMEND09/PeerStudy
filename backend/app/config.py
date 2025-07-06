import os

class Config:
    SECRET_KEY = os.environ.get('SECRET_KEY') or 'a-very-secret-key-you-should-change'

    SQLALCHEMY_DATABASE_URI = os.environ.get('DATABASE_URL') or \
        'postgresql://noteshare_user:noteshareadmin@localhost:5432/noteshare_db'
    SQLALCHEMY_TRACK_MODIFICATIONS = False