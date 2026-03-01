import os
import sys
import logging

# Configure logging to output to stdout (visible in Vercel logs)
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    stream=sys.stdout
)
logger = logging.getLogger(__name__)

# Log startup information
logger.info("=" * 60)
logger.info("Starting Kohinoor Power Solutions App")
logger.info("=" * 60)
logger.info(f"Python version: {sys.version}")
logger.info(f"Current directory: {os.getcwd()}")
logger.info(f"Files in directory: {os.listdir('.')}")

# Check environment variables (without exposing secrets)
env_vars = [k for k in os.environ.keys() if 'PASSWORD' not in k.upper() and 'SECRET' not in k.upper()]
logger.info(f"Environment variables: {env_vars}")

app = Flask(__name__)

@app.errorhandler(500)
def internal_error(error):
    logger.error(f"500 Error: {error}")
    logger.error(f"Request path: {request.path}")
    logger.error(f"Request method: {request.method}")
    return "Internal Server Error - Check logs for details", 500

@app.errorhandler(Exception)
def handle_exception(e):
    logger.error(f"Unhandled exception: {e}", exc_info=True)
    return "Internal Server Error", 500
# Test database connection on startup
try:
    logger.info("Testing database connection...")
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT 1")
    cur.close()
    conn.close()
    logger.info("✅ Database connection successful!")
except Exception as e:
    logger.error(f"❌ Database connection failed: {e}")
    logger.error("This will cause 500 errors!")
import os
import psycopg2
from psycopg2.extras import RealDictCursor
import logging

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def get_db_connection():
    """
    Get database connection using Vercel PostgreSQL environment variables
    """
    try:
        # Use Vercel's POSTGRES_URL environment variable
        database_url = os.environ.get('POSTGRES_URL')
        
        if not database_url:
            # Fallback to constructing from individual variables
            database_url = os.environ.get('DATABASE_URL')
            
            if not database_url:
                # Construct from individual PostgreSQL variables
                user = os.environ.get('POSTGRES_USER')
                password = os.environ.get('POSTGRES_PASSWORD')
                host = os.environ.get('POSTGRES_HOST')
                database = os.environ.get('POSTGRES_DATABASE')
                
                if all([user, password, host, database]):
                    database_url = f"postgresql://{user}:{password}@{host}/{database}?sslmode=require"
        
        if not database_url:
            raise ValueError("No database connection string found in environment variables")
        
        logger.info(f"Connecting to database at: {host if 'host' in locals() else 'using URL'}")
        
        # Connect with timeout
        conn = psycopg2.connect(
            database_url,
            connect_timeout=10,
            sslmode='require'
        )
        
        # Return dictionary-like rows
        conn.cursor_factory = RealDictCursor
        return conn
        
    except Exception as e:
        logger.error(f"Database connection failed: {e}")
        raise

def init_database():
    """
    Initialize database tables
    """
    conn = None
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        
        # Create customers table
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
        
        # Create index for faster searches
        cur.execute('''
            CREATE INDEX IF NOT EXISTS idx_customer_search 
            ON customers(customer_id, customer_name, product, city)
        ''')
        
        conn.commit()
        cur.close()
        logger.info("✅ Database initialized successfully!")
        
    except Exception as e:
        logger.error(f"Database initialization failed: {e}")
        raise
    finally:
        if conn:
            conn.close()

@app.route('/api/health')
def health_check():
    """Health check endpoint to verify database connection"""
    conn = None
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute('SELECT 1')
        cur.close()
        
        # Check if tables exist
        cur = conn.cursor()
        cur.execute("""
            SELECT EXISTS (
                SELECT FROM information_schema.tables 
                WHERE table_name = 'customers'
            );
        """)
        tables_exist = cur.fetchone()[0]
        cur.close()
        
        return {
            "status": "healthy",
            "database": "connected",
            "tables_exist": tables_exist,
            "environment": os.environ.get('VERCEL_ENV', 'development')
        }, 200
        
    except Exception as e:
        logger.error(f"Health check failed: {e}")
        return {
            "status": "unhealthy",
            "error": str(e),
            "database_url_set": bool(os.environ.get('POSTGRES_URL'))
        }, 500
    finally:
        if conn:
            conn.close()

@app.route('/debug')
def debug():
    """Simple debug endpoint"""
    result = {
        "status": "running",
        "database_url_set": bool(os.environ.get('POSTGRES_URL')),
        "environment": os.environ.get('VERCEL_ENV', 'unknown'),
    }
    
    # Test database
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("SELECT 1")
        cur.close()
        conn.close()
        result["database"] = "connected"
    except Exception as e:
        result["database"] = f"error: {str(e)}"
    
    return result