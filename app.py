import os
import sys
import logging
from datetime import datetime
from flask import Flask, render_template, request, redirect, url_for, flash, send_file, session
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
import psycopg2
from psycopg2.extras import RealDictCursor
import pandas as pd
from werkzeug.security import generate_password_hash, check_password_hash

# ============================================================================
# LOGGING CONFIGURATION (MUST BE FIRST)
# ============================================================================
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

# ============================================================================
# INITIALIZE FLASK APPLICATION
# ============================================================================
app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'dev-secret-key-123')

# ============================================================================
# SETUP LOGIN MANAGER
# ============================================================================
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'
login_manager.login_message = "Please log in to access this page."

# ============================================================================
# USER CLASS FOR AUTHENTICATION
# ============================================================================
class User(UserMixin):
    """Admin user class"""
    def __init__(self, id):
        self.id = id
        self.username = "admin"

admin_user = User(1)

@login_manager.user_loader
def load_user(user_id):
    """Load user from session"""
    if user_id == '1':
        return admin_user
    return None

# ============================================================================
# DATABASE FUNCTIONS
# ============================================================================
def get_db_connection():
    """
    Get database connection using Vercel PostgreSQL environment variables
    """
    try:
        # First try to get the database URL from environment
        database_url = os.environ.get('POSTGRES_URL')
        
        if not database_url:
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
            error_msg = "No database connection string found"
            logger.error(error_msg)
            raise ValueError(error_msg)
        
        logger.info(f"Connecting to PostgreSQL database")
        
        # Use psycopg2 for PostgreSQL, NOT sqlite3!
        conn = psycopg2.connect(database_url, connect_timeout=10)
        conn.cursor_factory = RealDictCursor
        logger.info("✅ PostgreSQL connection established")
        return conn
        
    except Exception as e:
        logger.error(f"Database connection failed: {e}")
        raise
# ============================================================================
# TEST DATABASE ON STARTUP
# ============================================================================
try:
    logger.info("Testing database connection on startup...")
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT 1")
    cur.close()
    conn.close()
    logger.info("✅ Database connection successful!")
    
    # Initialize tables if needed
    init_database()
    
except Exception as e:
    logger.error(f"❌ Database connection failed: {e}")
    logger.error("This will cause 500 errors!")

# ============================================================================
# HELPER FUNCTIONS
# ============================================================================
def get_next_serial_no():
    """Gets the next serial number by finding the maximum in the database"""
    conn = None
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute('SELECT MAX(serial_no) FROM customers')
        result = cur.fetchone()
        cur.close()
        
        if result['max'] is None:
            return 1
        return result['max'] + 1
    except Exception as e:
        logger.error(f"Error getting next serial number: {e}")
        return 1
    finally:
        if conn:
            conn.close()

def format_amount(amount):
    """Formats amount with comma separator (Indian style: 50,000)"""
    try:
        return f"{float(amount):,.0f}"
    except:
        return "0"

# ============================================================================
# ERROR HANDLERS
# ============================================================================
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

# ============================================================================
# ROUTES
# ============================================================================
@app.route('/')
def home():
    """Home page - redirects to login or dashboard"""
    if current_user.is_authenticated:
        return redirect(url_for('dashboard'))
    return redirect(url_for('login'))

@app.route('/login', methods=['GET', 'POST'])
def login():
    """Login page - handles user authentication"""
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        
        if username == 'admin' and password == 'admin123':
            login_user(admin_user)
            flash('✅ Login successful!', 'success')
            next_page = request.args.get('next')
            return redirect(next_page) if next_page else redirect(url_for('dashboard'))
        else:
            flash('❌ Invalid username or password', 'danger')
    
    return render_template('login.html')

@app.route('/logout')
@login_required
def logout():
    """Logs out the current user"""
    logout_user()
    flash('👋 Logged out successfully', 'info')
    return redirect(url_for('login'))

@app.route('/dashboard')
@login_required
def dashboard():
    """Main dashboard after login"""
    conn = None
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        
        cur.execute('SELECT COUNT(*) FROM customers')
        total_customers = cur.fetchone()['count']
        
        cur.execute('SELECT COALESCE(SUM(amount), 0) FROM customers')
        total_amount = cur.fetchone()['coalesce']
        
        cur.close()
        
        return render_template('dashboard.html', 
                             total_customers=total_customers,
                             total_amount=format_amount(total_amount))
    except Exception as e:
        logger.error(f"Dashboard error: {e}")
        flash('Error loading dashboard', 'danger')
        return render_template('dashboard.html', total_customers=0, total_amount="0")
    finally:
        if conn:
            conn.close()

@app.route('/add', methods=['GET', 'POST'])
@login_required
def add_customer():
    """Page to add new customer"""
    if request.method == 'POST':
        conn = None
        try:
            # Get form data
            customer_id = request.form.get('customer_id')
            customer_name = request.form.get('customer_name')
            product = request.form.get('product')
            date = request.form.get('date')
            contact = request.form.get('contact')
            city = request.form.get('city')
            amount = float(request.form.get('amount', 0))
            purchase_confirmed = request.form.get('purchase_confirmed') == 'on'
            
            # Validate required fields
            if not all([customer_id, customer_name, product, date, contact, city]):
                flash('❌ All fields are required!', 'danger')
                return redirect(url_for('add_customer'))
            
            # Get next serial number
            serial_no = get_next_serial_no()
            
            # Save to database
            conn = get_db_connection()
            cur = conn.cursor()
            cur.execute('''
                INSERT INTO customers 
                (serial_no, customer_id, customer_name, product, date, contact, city, amount, purchase_confirmed)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            ''', (serial_no, customer_id, customer_name, product, date, contact, city, amount, purchase_confirmed))
            
            conn.commit()
            cur.close()
            
            flash(f'✅ Customer {customer_id} added successfully!', 'success')
            return redirect(url_for('view_customers'))
            
        except psycopg2.IntegrityError:
            flash(f'❌ Customer ID {customer_id} already exists!', 'danger')
        except ValueError as e:
            flash(f'❌ Invalid amount format!', 'danger')
        except Exception as e:
            logger.error(f"Error adding customer: {e}")
            flash(f'❌ Error: {str(e)}', 'danger')
        finally:
            if conn:
                conn.close()
    
    # For GET request, show form with next serial number
    next_serial = get_next_serial_no()
    return render_template('add_customer.html', next_serial=next_serial)

@app.route('/customers')
@login_required
def view_customers():
    """Displays all customers in a table with search functionality"""
    search_query = request.args.get('search', '')
    conn = None
    
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        
        if search_query:
            # Search across multiple columns using PostgreSQL ILIKE (case-insensitive)
            cur.execute('''
                SELECT * FROM customers 
                WHERE customer_id ILIKE %s 
                   OR customer_name ILIKE %s 
                   OR product ILIKE %s 
                   OR city ILIKE %s
                ORDER BY serial_no
            ''', (f'%{search_query}%', f'%{search_query}%', f'%{search_query}%', f'%{search_query}%'))
        else:
            cur.execute('SELECT * FROM customers ORDER BY serial_no')
        
        customers = cur.fetchall()
        cur.close()
        
        # Convert to list of dictionaries and add formatted fields
        customers_list = []
        for customer in customers:
            customer_dict = dict(customer)
            customer_dict['amount_formatted'] = format_amount(customer_dict['amount'])
            customer_dict['purchase_icon'] = '✅' if customer_dict['purchase_confirmed'] else '❌'
            customers_list.append(customer_dict)
        
        return render_template('view_customers.html', customers=customers_list, search_query=search_query)
    
    except Exception as e:
        logger.error(f"Error viewing customers: {e}")
        flash('Error loading customers', 'danger')
        return render_template('view_customers.html', customers=[], search_query=search_query)
    finally:
        if conn:
            conn.close()

@app.route('/edit/<int:id>', methods=['GET', 'POST'])
@login_required
def edit_customer(id):
    """Edit an existing customer"""
    conn = None
    
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        
        if request.method == 'POST':
            # Get updated form data
            customer_id = request.form.get('customer_id')
            customer_name = request.form.get('customer_name')
            product = request.form.get('product')
            date = request.form.get('date')
            contact = request.form.get('contact')
            city = request.form.get('city')
            amount = float(request.form.get('amount', 0))
            purchase_confirmed = request.form.get('purchase_confirmed') == 'on'
            
            # Update database
            cur.execute('''
                UPDATE customers 
                SET customer_id = %s, customer_name = %s, product = %s, date = %s, 
                    contact = %s, city = %s, amount = %s, purchase_confirmed = %s
                WHERE id = %s
            ''', (customer_id, customer_name, product, date, contact, city, amount, purchase_confirmed, id))
            
            conn.commit()
            flash('✅ Customer updated successfully!', 'success')
            return redirect(url_for('view_customers'))
        
        # GET request - load existing customer data
        cur.execute('SELECT * FROM customers WHERE id = %s', (id,))
        customer = cur.fetchone()
        
        if customer is None:
            flash('❌ Customer not found!', 'danger')
            return redirect(url_for('view_customers'))
        
        return render_template('edit_customer.html', customer=dict(customer))
    
    except Exception as e:
        logger.error(f"Error editing customer: {e}")
        flash(f'❌ Error: {str(e)}', 'danger')
        return redirect(url_for('view_customers'))
    finally:
        if conn:
            conn.close()

@app.route('/delete/<int:id>')
@login_required
def delete_customer(id):
    """Deletes a customer from the database"""
    conn = None
    
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        
        # Get customer ID for confirmation message
        cur.execute('SELECT customer_id FROM customers WHERE id = %s', (id,))
        customer = cur.fetchone()
        
        if customer:
            cur.execute('DELETE FROM customers WHERE id = %s', (id,))
            conn.commit()
            flash(f'✅ Customer {customer["customer_id"]} deleted successfully!', 'success')
        else:
            flash('❌ Customer not found!', 'danger')
        
        return redirect(url_for('view_customers'))
    
    except Exception as e:
        logger.error(f"Error deleting customer: {e}")
        flash(f'❌ Error: {str(e)}', 'danger')
        return redirect(url_for('view_customers'))
    finally:
        if conn:
            conn.close()

@app.route('/export')
@login_required
def export_to_excel():
    """Exports all customer data to an Excel file and downloads it"""
    conn = None
    
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        
        # Get all customer data
        cur.execute('''
            SELECT serial_no, customer_id, customer_name, product, 
                   TO_CHAR(date, 'YYYY-MM-DD') as date, 
                   contact, city, amount, 
                   CASE WHEN purchase_confirmed THEN 'Yes' ELSE 'No' END as purchase_confirmed
            FROM customers 
            ORDER BY serial_no
        ''')
        
        customers = cur.fetchall()
        cur.close()
        
        if not customers:
            flash('❌ No data to export!', 'warning')
            return redirect(url_for('view_customers'))
        
        # Convert to pandas DataFrame
        df = pd.DataFrame(customers, columns=[
            'Serial No', 'Customer ID', 'Customer Name', 'Product', 'Date',
            'Contact', 'City', 'Amount', 'Purchase Confirmed'
        ])
        
        # Format amount column with comma separator
        df['Amount'] = df['Amount'].apply(lambda x: f"{float(x):,.0f}")
        
        # Generate filename with timestamp
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        filename = f'customers_{timestamp}.xlsx'
        filepath = f'exports/{filename}'
        
        # Ensure exports directory exists
        os.makedirs('exports', exist_ok=True)
        
        # Create Excel file
        with pd.ExcelWriter(filepath, engine='openpyxl') as writer:
            df.to_excel(writer, sheet_name='Customers', index=False)
            
            # Auto-adjust column widths
            worksheet = writer.sheets['Customers']
            for column in worksheet.columns:
                max_length = 0
                column_letter = column[0].column_letter
                for cell in column:
                    try:
                        if len(str(cell.value)) > max_length:
                            max_length = len(str(cell.value))
                    except:
                        pass
                adjusted_width = min(max_length + 2, 30)
                worksheet.column_dimensions[column_letter].width = adjusted_width
        
        flash(f'✅ Excel file generated: {filename}', 'success')
        return send_file(filepath, as_attachment=True, download_name=filename)
        
    except Exception as e:
        logger.error(f"Export error: {e}")
        flash(f'❌ Error exporting: {str(e)}', 'danger')
        return redirect(url_for('dashboard'))
    finally:
        if conn:
            conn.close()

# ============================================================================
# HEALTH CHECK ENDPOINTS
# ============================================================================
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

# ============================================================================
# FOR LOCAL DEVELOPMENT
# ============================================================================
if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5001))
    app.run(host='0.0.0.0', port=port, debug=True)