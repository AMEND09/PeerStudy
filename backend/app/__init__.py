from flask import Flask, jsonify
from flask_migrate import Migrate
from flask_cors import CORS
from flask_jwt_extended import JWTManager 
from .config import Config
from .models import db, bcrypt
from .routes import api_bp

def create_app(config_class=Config):
    app = Flask(__name__)
    app.config.from_object(config_class)
    app.config["JWT_SECRET_KEY"] = app.config["SECRET_KEY"]

    db.init_app(app)
    bcrypt.init_app(app)
    jwt = JWTManager(app) 
    migrate = Migrate(app, db)
    CORS(app) 

    app.register_blueprint(api_bp, url_prefix='/api')

    return app