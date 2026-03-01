import os
import sys
import logging
from datetime import datetime
from flask import Flask, render_template, request, redirect, url_for, flash, send_file
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
import psycopg2
from psycopg2.extras import RealDictCursor
import pandas as pd

# Logging
logging.basicConfig(level=logging.INFO, stream=sys.stdout)
logger = logging.getLogger(__name__)
logger.info("="*50)
logger.info("STARTING WITH POSTGRESQL ONLY")
logger.info("="*50)

app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'dev-key')

# Login setup
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'

class User(UserMixin):
    def __init__(self, id):
        self.id = id
        self.username = "admin"

admin_user = User(1)

@login_manager.user_loader
def load_user(user_id):
    return admin_user if user_id == '1' else None

# ========== POSTGRESQL ONLY - NO SQLITE ==========
def get_db_connection():
    """ONLY PostgreSQL - NO SQLITE"""
    try:
        # Try all possible Vercel PostgreSQL env vars
        database_url = (os.environ.get('POSTGRES_URL') or 
                       os.environ.get('DATABASE_URL'))
        
        if not database_url:
            # Construct from parts
            user = os.environ.get('POSTGRES_USER')
            password = os.environ.get('POSTGRES_PASSWORD')
            host = os.environ.get('POSTGRES_HOST')
            db = os.environ.get('POSTGRES_DATABASE')
            
            if all([user, password, host, db]):
                database_url = f"postgresql://{user}:{password}@{host}/{db}?sslmode=require"
        
        if not database_url:
            logger.error("NO DATABASE URL FOUND")
            raise ValueError("Database not configured")
        
        logger.info(f"Connecting to PostgreSQL...")
        conn = psycopg2.connect(database_url, connect_timeout=10)
        conn.cursor_factory = RealDictCursor
        logger.info("✅ PostgreSQL connected")
        return conn
        
    except Exception as e:
        logger.error(f"DB Error: {e}")
        raise

def init_db():
    """Create tables if not exist"""
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute('''
            CREATE TABLE IF NOT EXISTS customers (
                id SERIAL PRIMARY KEY,
                serial_no INTEGER NOT NULL,
                customer_id VARCHAR(50) UNIQUE NOT NULL,
                customer_name VARCHAR(200) NOT NULL,
                product VARCHAR(100) NOT NULL,
                date DATE NOT NULL,
                contact VARCHAR(50) NOT NULL,
                city VARCHAR(100) NOT NULL,
                amount DECIMAL(10,2) NOT NULL,
                purchase_confirmed BOOLEAN DEFAULT FALSE,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        conn.commit()
        cur.close()
        conn.close()
        logger.info("✅ Tables ready")
    except Exception as e:
        logger.error(f"Init error: {e}")

# Test connection at startup
try:
    logger.info("Testing database...")
    conn = get_db_connection()
    conn.close()
    logger.info("✅ Database OK")
    init_db()
except Exception as e:
    logger.error(f"Startup failed: {e}")

# ========== ROUTES ==========
@app.route('/')
def home():
    return redirect(url_for('dashboard') if current_user.is_authenticated else url_for('login'))

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        if request.form.get('username') == 'admin' and request.form.get('password') == 'admin123':
            login_user(admin_user)
            return redirect(url_for('dashboard'))
    return render_template('login.html')

@app.route('/dashboard')
@login_required
def dashboard():
    return render_template('dashboard.html', total_customers=0, total_amount="0")

@app.route('/debug')
def debug():
    """Check what's happening"""
    return {
        "postgres_url": bool(os.environ.get('POSTGRES_URL')),
        "database_url": bool(os.environ.get('DATABASE_URL')),
        "env_vars": [k for k in os.environ.keys() if 'POSTGRES' in k]
    }

@app.route('/health')
def health():
    try:
        conn = get_db_connection()
        conn.close()
        return {"status": "healthy", "db": "connected"}
    except Exception as e:
        return {"status": "unhealthy", "error": str(e)}, 500

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5001))
    app.run(host='0.0.0.0', port=port)