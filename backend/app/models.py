from flask_sqlalchemy import SQLAlchemy
from datetime import datetime

# SQLAlchemy instance (shared across application)
db = SQLAlchemy()

class Order(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    chat_id = db.Column(db.BigInteger)
    name = db.Column(db.String(80))
    phone = db.Column(db.String(50))
    pay_method = db.Column(db.String(20))
    cart = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


class Product(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    category_id = db.Column(db.String(50), nullable=False)
    name = db.Column(db.String(120), nullable=False)
    description = db.Column(db.Text, nullable=False)
    price = db.Column(db.Float, nullable=False)
    discount = db.Column(db.Integer, default=0)
    image_url = db.Column(db.Text, nullable=False)
    gallery = db.Column(db.Text)

