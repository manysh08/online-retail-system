from flask import Flask, render_template, request, jsonify, redirect, url_for, session, flash
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
import sqlite3
import os
from datetime import datetime
import json
from functools import wraps
import re

app = Flask(__name__)
app.secret_key = 'your-secret-key-change-in-production'
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024
app.config['UPLOAD_FOLDER'] = 'static/uploads'

# Create upload folder if it doesn't exist
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

DATABASE = 'retail_system.db'

# ==================== DATABASE FUNCTIONS ====================

def get_db():
    """Get database connection"""
    db = sqlite3.connect(DATABASE)
    db.row_factory = sqlite3.Row
    return db

def convert_timestamps(data):
    """Convert timestamp strings to datetime objects"""
    if data is None:
        return None
    
    if isinstance(data, dict):
        for key in data:
            if key == 'created_at' and isinstance(data[key], str):
                try:
                    data[key] = datetime.strptime(data[key], '%Y-%m-%d %H:%M:%S')
                except (ValueError, TypeError):
                    pass
        return data
    elif isinstance(data, list):
        return [convert_timestamps(item) if isinstance(item, dict) else item for item in data]
    return data

def init_db():
    """Initialize database with tables"""
    db = get_db()
    cursor = db.cursor()
    
    # Users table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            email TEXT UNIQUE NOT NULL,
            password TEXT NOT NULL,
            full_name TEXT,
            phone TEXT,
            address TEXT,
            city TEXT,
            country TEXT,
            postal_code TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            is_admin BOOLEAN DEFAULT 0
        )
    ''')
    
    # Products table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS products (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            category TEXT NOT NULL,
            description TEXT,
            price REAL NOT NULL,
            original_price REAL,
            image_url TEXT,
            stock INTEGER DEFAULT 0,
            rating REAL DEFAULT 0,
            reviews_count INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    # Cart table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS cart (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            product_id INTEGER NOT NULL,
            quantity INTEGER DEFAULT 1,
            added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(user_id) REFERENCES users(id),
            FOREIGN KEY(product_id) REFERENCES products(id)
        )
    ''')
    
    # Orders table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS orders (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            order_number TEXT UNIQUE NOT NULL,
            total_amount REAL NOT NULL,
            payment_method TEXT,
            payment_status TEXT DEFAULT 'pending',
            delivery_address TEXT,
            delivery_phone TEXT,
            delivery_email TEXT,
            status TEXT DEFAULT 'pending',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(user_id) REFERENCES users(id)
        )
    ''')
    
    # Order items table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS order_items (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            order_id INTEGER NOT NULL,
            product_id INTEGER NOT NULL,
            quantity INTEGER NOT NULL,
            price REAL NOT NULL,
            FOREIGN KEY(order_id) REFERENCES orders(id),
            FOREIGN KEY(product_id) REFERENCES products(id)
        )
    ''')
    
    # Wishlist table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS wishlist (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            product_id INTEGER NOT NULL,
            added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(user_id) REFERENCES users(id),
            FOREIGN KEY(product_id) REFERENCES products(id)
        )
    ''')
    
    db.commit()

    # ==================== INSERT 20 SAMPLE PRODUCTS ====================
    # Only insert if products table is empty
    existing = cursor.execute('SELECT COUNT(*) FROM products').fetchone()[0]
    if existing == 0:
        products = [
            # Electronics
            (
                'Apple iPhone 15 Pro',
                'Electronics',
                'The latest iPhone 15 Pro with A17 Pro chip, titanium design, 48MP camera system, and USB-C connectivity. Available in Natural Titanium.',
                99999.00,
                109999.00,
                'https://encrypted-tbn0.gstatic.com/images?q=tbn:ANd9GcQIcFbX-CC1ugTZaxsSyZdHY8LkIHiQXJp_2g&s',
                50,
                4.8,
                2340
            ),
            (
                'Samsung Galaxy S24 Ultra',
                'Electronics',
                'Samsung Galaxy S24 Ultra with 200MP camera, built-in S Pen, Snapdragon 8 Gen 3, and 5000mAh battery. The ultimate Android flagship.',
                89999.00,
                99999.00,
                'https://images.unsplash.com/photo-1706439213386-b4c3a71a0b9a?w=600&q=80',
                40,
                4.7,
                1890
            ),
            (
                'Sony WH-1000XM5 Headphones',
                'Electronics',
                'Industry-leading noise cancelling wireless headphones with Auto Noise Cancelling Optimizer, 30-hour battery life and crystal clear hands-free calling.',
                24999.00,
                34999.00,
                'https://images.unsplash.com/photo-1505740420928-5e560c06d30e?w=600&q=80',
                80,
                4.9,
                3120
            ),
            (
                'Apple MacBook Air M3',
                'Electronics',
                'MacBook Air with M3 chip — supercharged by the next generation of Apple silicon. Featuring a stunning 13.6-inch Liquid Retina display and all-day battery life.',
                114900.00,
                129900.00,
                'https://images.unsplash.com/photo-1517336714731-489689fd1ca8?w=600&q=80',
                25,
                4.9,
                980
            ),
            (
                'iPad Pro 12.9 inch',
                'Electronics',
                'The ultimate iPad experience with the M2 chip, stunning Liquid Retina XDR display, and support for Apple Pencil and Magic Keyboard.',
                89900.00,
                99900.00,
                'https://images.unsplash.com/photo-1544244015-0df4b3ffc6b0?w=600&q=80',
                35,
                4.8,
                760
            ),

            # Fashion
            (
                'Men\'s Slim Fit Formal Shirt',
                'Fashion',
                'Premium cotton slim fit formal shirt with wrinkle-resistant fabric. Perfect for office and business meetings. Available in multiple colors.',
                1299.00,
                2499.00,
                'https://images.unsplash.com/photo-1602810318383-e386cc2a3ccf?w=600&q=80',
                150,
                4.3,
                540
            ),
            (
                'Women\'s Casual Denim Jacket',
                'Fashion',
                'Stylish casual denim jacket for women. Made from high-quality denim with a comfortable fit. Perfect for all seasons.',
                2499.00,
                3999.00,
                'https://images.unsplash.com/photo-1548536419-9f47e78b049d?w=600&q=80',
                120,
                4.5,
                820
            ),
            (
                'Nike Air Max 270',
                'Fashion',
                'The Nike Air Max 270 delivers visible cushioning under every step. The shoe\'s large Air unit and flexible outer sole make every step feel effortless.',
                9999.00,
                12999.00,
                'https://images.unsplash.com/photo-1542291026-7eec264c27ff?w=600&q=80',
                200,
                4.6,
                1450
            ),
            (
                'Leather Crossbody Handbag',
                'Fashion',
                'Premium genuine leather crossbody bag with multiple compartments. Elegant design suitable for casual and formal occasions.',
                3499.00,
                5999.00,
                'https://images.unsplash.com/photo-1548036328-c9fa89d128fa?w=600&q=80',
                90,
                4.4,
                630
            ),
            (
                'Men\'s Sports Running Watch',
                'Fashion',
                'Multifunctional sports watch with heart rate monitor, GPS tracking, waterproof design, and 7-day battery life. Ideal for fitness enthusiasts.',
                4999.00,
                7999.00,
                'https://images.unsplash.com/photo-1523275335684-37898b6baf30?w=600&q=80',
                110,
                4.5,
                920
            ),

            # Home & Kitchen
            (
                'Instant Pot Duo 7-in-1',
                'Home & Kitchen',
                'The Instant Pot Duo is a 7-in-1 multi-use programmable pressure cooker, slow cooker, rice cooker, steamer, sauté pan, yogurt maker and food warmer.',
                6999.00,
                9999.00,
                'https://images.unsplash.com/photo-1585515320310-259814833e62?w=600&q=80',
                65,
                4.7,
                2100
            ),
            (
                'Philips Air Fryer XXL',
                'Home & Kitchen',
                'Philips Air Fryer XXL uses hot air to fry food. Get the taste and texture of fried food with up to 90% less fat. Twin TurboStar technology.',
                9999.00,
                14999.00,
                'https://images.unsplash.com/photo-1648897580536-87cf49e3f3e8?w=600&q=80',
                45,
                4.6,
                1340
            ),
            (
                'Dyson V15 Detect Vacuum',
                'Home & Kitchen',
                'Dyson V15 Detect cordless vacuum with laser dust detection, HEPA filtration, and 60 minutes of run time. Automatically adapts suction to the task.',
                34999.00,
                44999.00,
                'https://images.unsplash.com/photo-1558618666-fcd25c85cd64?w=600&q=80',
                30,
                4.8,
                870
            ),
            (
                'Scented Soy Candle Set',
                'Home & Kitchen',
                'Set of 6 premium hand-poured soy wax candles with relaxing fragrances including lavender, vanilla, jasmine, sandalwood, rose and eucalyptus.',
                1499.00,
                2499.00,
                'https://images.unsplash.com/photo-1602178506521-35cad33a09bc?w=600&q=80',
                200,
                4.5,
                710
            ),
            (
                'Stainless Steel Water Bottle',
                'Home & Kitchen',
                'Double-wall vacuum insulated stainless steel water bottle. Keeps drinks cold for 24 hours and hot for 12 hours. BPA-free and leak-proof.',
                799.00,
                1499.00,
                'https://images.unsplash.com/photo-1602143407151-7111542de6e8?w=600&q=80',
                300,
                4.4,
                1890
            ),

            # Sports & Fitness
            (
                'Yoga Mat Premium Non-Slip',
                'Sports & Fitness',
                'Extra thick 6mm eco-friendly TPE yoga mat with non-slip surface, alignment lines, and carrying strap. Perfect for yoga, pilates and floor exercises.',
                1299.00,
                1999.00,
                'https://images.unsplash.com/photo-1592432678016-e910b452f9a2?w=600&q=80',
                180,
                4.6,
                1230
            ),
            (
                'Adjustable Dumbbell Set',
                'Sports & Fitness',
                'Space-saving adjustable dumbbell set ranging from 5kg to 25kg. Quick-adjust dial mechanism. Replaces 15 sets of weights. Ideal for home gym.',
                12999.00,
                19999.00,
                'https://images.unsplash.com/photo-1517836357463-d25dfeac3438?w=600&q=80',
                55,
                4.7,
                560
            ),
            (
                'Resistance Bands Set',
                'Sports & Fitness',
                'Set of 5 premium resistance bands with different resistance levels (10-50 lbs). Perfect for strength training, physical therapy, and stretching.',
                999.00,
                1799.00,
                'https://images.unsplash.com/photo-1598289431512-b97b0917affc?w=600&q=80',
                250,
                4.5,
                2340
            ),

            # Books
            (
                'Atomic Habits by James Clear',
                'Books',
                'An easy and proven way to build good habits and break bad ones. This book will reshape the way you think about progress and success. Bestseller with over 10 million copies sold.',
                499.00,
                799.00,
                'https://images.unsplash.com/photo-1544947950-fa07a98d237f?w=600&q=80',
                500,
                4.9,
                45600
            ),
            (
                'The Psychology of Money',
                'Books',
                'Timeless lessons on wealth, greed, and happiness by Morgan Housel. Doing well with money isn\'t necessarily about what you know. It\'s about how you behave.',
                399.00,
                699.00,
                'https://images.unsplash.com/photo-1553729459-efe14ef6055d?w=600&q=80',
                500,
                4.8,
                32100
            ),
        ]

        cursor.executemany('''
            INSERT INTO products (name, category, description, price, original_price, image_url, stock, rating, reviews_count)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', products)

        db.commit()

    db.close()

# ==================== AUTHENTICATION ====================

def login_required(f):
    """Decorator for login requirement"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            flash('Please log in first.', 'danger')
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

def admin_required(f):
    """Decorator for admin requirement"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            flash('Please log in first.', 'danger')
            return redirect(url_for('login'))
        
        db = get_db()
        user = db.execute('SELECT is_admin FROM users WHERE id = ?', (session['user_id'],)).fetchone()
        db.close()
        
        if not user or not user['is_admin']:
            flash('Admin access required.', 'danger')
            return redirect(url_for('index'))
        return f(*args, **kwargs)
    return decorated_function

@app.route('/register', methods=['GET', 'POST'])
def register():
    """User registration"""
    if request.method == 'POST':
        data = request.form
        db = get_db()
        
        # Validation
        if not data.get('username') or not data.get('email') or not data.get('password'):
            flash('Missing required fields.', 'danger')
            return redirect(url_for('register'))
        
        if len(data.get('password', '')) < 6:
            flash('Password must be at least 6 characters.', 'danger')
            return redirect(url_for('register'))
        
        # Email validation
        if not re.match(r'^[\w\.-]+@[\w\.-]+\.\w+$', data.get('email', '')):
            flash('Invalid email format.', 'danger')
            return redirect(url_for('register'))
        
        try:
            db.execute(
                'INSERT INTO users (username, email, password, full_name) VALUES (?, ?, ?, ?)',
                (data['username'], data['email'], generate_password_hash(data['password']), data.get('full_name', ''))
            )
            db.commit()
            flash('Registration successful! Please log in.', 'success')
            return redirect(url_for('login'))
        except sqlite3.IntegrityError:
            flash('Username or email already exists.', 'danger')
        finally:
            db.close()
        
        return redirect(url_for('register'))
    
    return render_template('register.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    """User login"""
    if request.method == 'POST':
        data = request.form
        db = get_db()
        
        user = db.execute(
            'SELECT * FROM users WHERE username = ?',
            (data.get('username'),)
        ).fetchone()
        db.close()
        
        if user and check_password_hash(user['password'], data.get('password', '')):
            session['user_id'] = user['id']
            session['username'] = user['username']
            session['is_admin'] = user['is_admin']
            flash(f'Welcome {user["username"]}!', 'success')
            return redirect(url_for('dashboard' if user['is_admin'] else 'index'))
        else:
            flash('Invalid username or password.', 'danger')
    
    return render_template('login.html')

@app.route('/admin-login', methods=['GET', 'POST'])
def admin_login():
    """Admin login"""
    if request.method == 'POST':
        data = request.form
        username = data.get('username')
        password = data.get('password')
        
        # Admin credentials: admin/111admin
        if username == 'admin' and password == '111admin':
            db = get_db()
            admin_user = db.execute('SELECT * FROM users WHERE username = ? AND is_admin = 1', ('admin',)).fetchone()
            
            if not admin_user:
                # Create admin user if doesn't exist
                db.execute(
                    'INSERT OR IGNORE INTO users (username, email, password, full_name, is_admin) VALUES (?, ?, ?, ?, ?)',
                    ('admin', 'admin@retailsystem.com', generate_password_hash('111admin'), 'Administrator', 1)
                )
                db.commit()
                admin_user = db.execute('SELECT * FROM users WHERE username = ?', ('admin',)).fetchone()
            
            session['user_id'] = admin_user['id']
            session['username'] = admin_user['username']
            session['is_admin'] = True
            flash('Admin login successful!', 'success')
            db.close()
            return redirect(url_for('dashboard'))
        else:
            flash('Invalid admin credentials.', 'danger')
    
    return render_template('admin_login.html')

@app.route('/logout')
def logout():
    """User logout"""
    session.clear()
    flash('You have been logged out.', 'success')
    return redirect(url_for('index'))

# ==================== MAIN PAGES ====================

@app.route('/')
def index():
    """Home page"""
    db = get_db()
    products = db.execute('SELECT * FROM products LIMIT 6').fetchall()
    categories = db.execute('SELECT DISTINCT category FROM products').fetchall()
    db.close()
    
    return render_template('index.html', products=products, categories=categories)

@app.route('/about')
def about():
    """About page"""
    return render_template('about.html')

@app.route('/contact')
def contact():
    """Contact page"""
    return render_template('contact.html')

@app.route('/products')
def products():
    """Products page with filtering and sorting"""
    db = get_db()
    
    # Get filters
    categories_param = request.args.get('categories', '')
    sort = request.args.get('sort', 'newest')
    search = request.args.get('search', '')
    min_price = request.args.get('min_price', '')
    max_price = request.args.get('max_price', '')
    
    query = 'SELECT * FROM products WHERE 1=1'
    params = []
    
    # Multiple category filter
    if categories_param:
        categories_list = [c.strip() for c in categories_param.split(',') if c.strip()]
        if categories_list:
            placeholders = ','.join(['?' for _ in categories_list])
            query += f' AND category IN ({placeholders})'
            params.extend(categories_list)
    
    # Price range filter
    if min_price:
        try:
            query += ' AND price >= ?'
            params.append(float(min_price))
        except ValueError:
            pass
    
    if max_price:
        try:
            query += ' AND price <= ?'
            params.append(float(max_price))
        except ValueError:
            pass
    
    if search:
        query += ' AND (name LIKE ? OR description LIKE ?)'
        search_term = f'%{search}%'
        params.extend([search_term, search_term])
    
    # Sorting
    if sort == 'price_low':
        query += ' ORDER BY price ASC'
    elif sort == 'price_high':
        query += ' ORDER BY price DESC'
    elif sort == 'rating':
        query += ' ORDER BY rating DESC'
    else:  # newest
        query += ' ORDER BY created_at DESC'
    
    all_products = db.execute(query, params).fetchall()
    categories = db.execute('SELECT DISTINCT category FROM products ORDER BY category').fetchall()
    
    # Get price range
    price_range = db.execute('SELECT MIN(price) as min_price, MAX(price) as max_price FROM products').fetchone()
    db.close()
    
    # Convert prices to floats for template formatting
    try:
        display_min_price = float(min_price) if min_price else float(price_range['min_price'] or 0)
        display_max_price = float(max_price) if max_price else float(price_range['max_price'] or 0)
        price_min = float(price_range['min_price'] or 0)
        price_max = float(price_range['max_price'] or 0)
    except (ValueError, TypeError):
        display_min_price = 0.0
        display_max_price = 0.0
        price_min = 0.0
        price_max = 0.0
    
    return render_template('products.html', 
                         products=all_products, 
                         categories=categories,
                         selected_categories=categories_param,
                         sort=sort,
                         search=search,
                         min_price=display_min_price,
                         max_price=display_max_price,
                         price_min=price_min,
                         price_max=price_max)

@app.route('/product/<int:product_id>')
def product_detail(product_id):
    """Product detail page"""
    db = get_db()
    product = db.execute('SELECT * FROM products WHERE id = ?', (product_id,)).fetchone()
    db.close()
    
    if not product:
        flash('Product not found.', 'danger')
        return redirect(url_for('products'))
    
    return render_template('product_details.html', product=product)

@app.route('/comparison')
def comparison():
    """Product comparison page"""
    product_ids = request.args.get('ids', '')
    
    if not product_ids:
        flash('No products selected for comparison.', 'info')
        return redirect(url_for('products'))
    
    try:
        ids_list = [int(id) for id in product_ids.split(',') if id.strip()]
    except (ValueError, AttributeError):
        flash('Invalid product IDs.', 'danger')
        return redirect(url_for('products'))
    
    if not ids_list or len(ids_list) > 5:
        flash('Select 1-5 products for comparison.', 'warning')
        return redirect(url_for('products'))
    
    db = get_db()
    placeholders = ','.join(['?' for _ in ids_list])
    
    # SQLite doesn't support FIELD(), so fetch and sort in Python
    comparison_products = db.execute(
        f'SELECT * FROM products WHERE id IN ({placeholders})',
        tuple(ids_list)
    ).fetchall()
    db.close()
    
    if not comparison_products:
        flash('Products not found.', 'danger')
        return redirect(url_for('products'))
    
    # Convert to list and sort to preserve order from URL
    products_dict = {p['id']: p for p in comparison_products}
    comparison_products = [products_dict[id] for id in ids_list if id in products_dict]
    
    return render_template('comparison.html', products=comparison_products)

# ==================== SHOPPING CART ====================

@app.route('/cart')
def cart():
    """Shopping cart page"""
    user_id = session.get('user_id')
    cart_items = []
    total = 0
    
    if user_id:
        db = get_db()
        cart_items = db.execute('''
            SELECT c.id, c.quantity, p.* FROM cart c
            JOIN products p ON c.product_id = p.id
            WHERE c.user_id = ?
        ''', (user_id,)).fetchall()
        
        total = sum(item['price'] * item['quantity'] for item in cart_items)
        db.close()
    
    return render_template('cart.html', cart_items=cart_items, total=total)

@app.route('/api/cart/add', methods=['POST'])
@login_required
def add_to_cart():
    """Add product to cart"""
    data = request.json
    product_id = data.get('product_id')
    quantity = data.get('quantity', 1)
    
    db = get_db()
    
    # Check if product exists
    product = db.execute('SELECT * FROM products WHERE id = ?', (product_id,)).fetchone()
    if not product:
        return jsonify({'success': False, 'message': 'Product not found'}), 404
    
    # Check stock
    if product['stock'] < quantity:
        return jsonify({'success': False, 'message': 'Insufficient stock'}), 400
    
    # Check if already in cart
    existing = db.execute(
        'SELECT * FROM cart WHERE user_id = ? AND product_id = ?',
        (session['user_id'], product_id)
    ).fetchone()
    
    if existing:
        new_quantity = existing['quantity'] + quantity
        if product['stock'] < new_quantity:
            return jsonify({'success': False, 'message': 'Insufficient stock'}), 400
        db.execute(
            'UPDATE cart SET quantity = ? WHERE id = ?',
            (new_quantity, existing['id'])
        )
    else:
        db.execute(
            'INSERT INTO cart (user_id, product_id, quantity) VALUES (?, ?, ?)',
            (session['user_id'], product_id, quantity)
        )
    
    db.commit()
    db.close()
    
    return jsonify({'success': True, 'message': 'Added to cart'})

@app.route('/api/cart/update', methods=['POST'])
@login_required
def update_cart():
    """Update cart item quantity"""
    data = request.json
    cart_id = data.get('cart_id')
    quantity = data.get('quantity')
    
    if quantity <= 0:
        return jsonify({'success': False, 'message': 'Invalid quantity'}), 400
    
    db = get_db()
    
    # Get cart item
    item = db.execute(
        'SELECT c.*, p.stock FROM cart c JOIN products p ON c.product_id = p.id WHERE c.id = ?',
        (cart_id,)
    ).fetchone()
    
    if not item:
        return jsonify({'success': False, 'message': 'Cart item not found'}), 404
    
    if item['stock'] < quantity:
        return jsonify({'success': False, 'message': 'Insufficient stock'}), 400
    
    db.execute('UPDATE cart SET quantity = ? WHERE id = ?', (quantity, cart_id))
    db.commit()
    db.close()
    
    return jsonify({'success': True, 'message': 'Updated'})

@app.route('/api/cart/remove/<int:cart_id>', methods=['DELETE'])
@login_required
def remove_from_cart(cart_id):
    """Remove item from cart"""
    db = get_db()
    db.execute('DELETE FROM cart WHERE id = ? AND user_id = ?', (cart_id, session['user_id']))
    db.commit()
    db.close()
    
    return jsonify({'success': True, 'message': 'Removed from cart'})

@app.route('/api/cart/count')
def cart_count():
    """Get cart item count"""
    count = 0
    if session.get('user_id'):
        db = get_db()
        result = db.execute(
            'SELECT SUM(quantity) as count FROM cart WHERE user_id = ?',
            (session['user_id'],)
        ).fetchone()
        count = result['count'] or 0
        db.close()
    
    return jsonify({'count': count})

# ==================== CHECKOUT & ORDERS ====================

@app.route('/checkout', methods=['GET', 'POST'])
@login_required
def checkout():
    """Checkout page"""
    db = get_db()
    user = db.execute('SELECT * FROM users WHERE id = ?', (session['user_id'],)).fetchone()
    cart_items = db.execute('''
        SELECT c.id, c.quantity, p.* FROM cart c
        JOIN products p ON c.product_id = p.id
        WHERE c.user_id = ?
    ''', (session['user_id'],)).fetchall()
    db.close()
    
    if not cart_items:
        flash('Your cart is empty.', 'warning')
        return redirect(url_for('cart'))
    
    total = sum(item['price'] * item['quantity'] for item in cart_items)
    
    if request.method == 'POST':
        delivery_address = request.form.get('delivery_address')
        delivery_phone = request.form.get('delivery_phone')
        delivery_email = request.form.get('delivery_email')
        
        if not all([delivery_address, delivery_phone, delivery_email]):
            flash('Please fill all delivery details.', 'danger')
            return redirect(url_for('checkout'))
        
        db = get_db()
        
        # Create order
        order_number = f"ORD-{datetime.now().strftime('%Y%m%d%H%M%S')}"
        db.execute('''
            INSERT INTO orders (user_id, order_number, total_amount, delivery_address, delivery_phone, delivery_email)
            VALUES (?, ?, ?, ?, ?, ?)
        ''', (session['user_id'], order_number, total, delivery_address, delivery_phone, delivery_email))
        
        db.commit()
        order = db.execute('SELECT id FROM orders WHERE order_number = ?', (order_number,)).fetchone()
        order_id = order['id']
        
        # Add order items
        for item in cart_items:
            db.execute('''
                INSERT INTO order_items (order_id, product_id, quantity, price)
                VALUES (?, ?, ?, ?)
            ''', (order_id, item['id'], item['quantity'], item['price']))
        
        db.commit()
        db.close()
        
        session['order_id'] = order_id
        session['order_number'] = order_number
        session['order_total'] = total
        
        return redirect(url_for('payment'))
    
    return render_template('checkout.html', user=user, cart_items=cart_items, total=total)

@app.route('/payment', methods=['GET', 'POST'])
@login_required
def payment():
    """Payment page"""
    order_id = session.get('order_id')
    order_number = session.get('order_number')
    order_total = session.get('order_total')
    
    if not order_id:
        flash('No order found.', 'danger')
        return redirect(url_for('cart'))
    
    if request.method == 'POST':
        payment_method = request.form.get('payment_method')
        
        if payment_method == 'upi':
            upi_id = request.form.get('upi_id')
            if not upi_id:
                flash('Please enter UPI ID.', 'danger')
                return redirect(url_for('payment'))
        elif payment_method == 'card':
            card_holder = request.form.get('card_holder')
            card_number = request.form.get('card_number')
            expiry = request.form.get('expiry')
            cvv = request.form.get('cvv')
            
            if not all([card_holder, card_number, expiry, cvv]):
                flash('Please fill all card details.', 'danger')
                return redirect(url_for('payment'))
        elif payment_method != 'cod':
            flash('Invalid payment method.', 'danger')
            return redirect(url_for('payment'))
        
        # Update order with payment details
        db = get_db()
        db.execute('''
            UPDATE orders SET payment_method = ?, payment_status = ?, status = ?
            WHERE id = ?
        ''', (payment_method, 'completed', 'confirmed' if payment_method != 'cod' else 'pending', order_id))
        
        # Clear cart
        db.execute('DELETE FROM cart WHERE user_id = ?', (session['user_id'],))
        db.commit()
        db.close()
        
        # Clear session variables
        session.pop('order_id', None)
        session.pop('order_number', None)
        session.pop('order_total', None)
        
        flash('Payment successful! Your order has been placed.', 'success')
        return redirect(url_for('order_confirmation', order_id=order_id))
    
    return render_template('payment.html', 
                         order_number=order_number, 
                         order_total=order_total)

@app.route('/order-confirmation/<int:order_id>')
@login_required
def order_confirmation(order_id):
    """Order confirmation page"""
    db = get_db()
    order = db.execute('''
        SELECT * FROM orders WHERE id = ? AND user_id = ?
    ''', (order_id, session['user_id'])).fetchone()
    
    if not order:
        flash('Order not found.', 'danger')
        return redirect(url_for('index'))
    
    order_items = db.execute('''
        SELECT oi.*, p.name, p.image_url FROM order_items oi
        JOIN products p ON oi.product_id = p.id
        WHERE oi.order_id = ?
    ''', (order_id,)).fetchall()
    db.close()
    
    # Convert order to dict and convert timestamps
    order = dict(order)
    order = convert_timestamps(order)
    
    return render_template('order_confirmation.html', order=order, order_items=order_items)

@app.route('/orders')
@login_required
def my_orders():
    """My orders page"""
    db = get_db()
    orders = db.execute('''
        SELECT * FROM orders WHERE user_id = ? ORDER BY created_at DESC
    ''', (session['user_id'],)).fetchall()
    db.close()
    
    # Convert orders list
    orders = [dict(order) for order in orders]
    orders = convert_timestamps(orders)
    
    return render_template('my_orders.html', orders=orders)

@app.route('/order/<int:order_id>')
@login_required
def order_detail(order_id):
    """Order detail page"""
    db = get_db()
    order = db.execute('''
        SELECT * FROM orders WHERE id = ? AND user_id = ?
    ''', (order_id, session['user_id'])).fetchone()
    
    if not order:
        flash('Order not found.', 'danger')
        return redirect(url_for('my_orders'))
    
    order_items = db.execute('''
        SELECT oi.*, p.name, p.image_url FROM order_items oi
        JOIN products p ON oi.product_id = p.id
        WHERE oi.order_id = ?
    ''', (order_id,)).fetchall()
    db.close()
    
    # Convert order to dict and convert timestamps
    order = dict(order)
    order = convert_timestamps(order)
    
    return render_template('order_detail.html', order=order, order_items=order_items)

# ==================== USER PROFILE ====================

@app.route('/profile')
@login_required
def profile():
    """User profile page"""
    db = get_db()
    user = db.execute('SELECT * FROM users WHERE id = ?', (session['user_id'],)).fetchone()
    db.close()
    
    return render_template('profile.html', user=user)

@app.route('/api/profile/update', methods=['POST'])
@login_required
def update_profile():
    """Update user profile"""
    data = request.json
    db = get_db()
    
    db.execute('''
        UPDATE users SET full_name = ?, phone = ?, address = ?, city = ?, country = ?, postal_code = ?
        WHERE id = ?
    ''', (data.get('full_name'), data.get('phone'), data.get('address'), 
          data.get('city'), data.get('country'), data.get('postal_code'), session['user_id']))
    
    db.commit()
    db.close()
    
    return jsonify({'success': True, 'message': 'Profile updated'})

# ==================== ADMIN DASHBOARD ====================

@app.route('/admin/dashboard')
@admin_required
def dashboard():
    """Admin dashboard"""
    db = get_db()
    
    total_users = db.execute('SELECT COUNT(*) as count FROM users WHERE is_admin = 0').fetchone()['count']
    total_products = db.execute('SELECT COUNT(*) as count FROM products').fetchone()['count']
    total_orders = db.execute('SELECT COUNT(*) as count FROM orders').fetchone()['count']
    total_revenue = db.execute('SELECT SUM(total_amount) as total FROM orders WHERE payment_status = "completed"').fetchone()['total'] or 0
    
    recent_orders = db.execute('''
        SELECT o.*, u.username FROM orders o
        JOIN users u ON o.user_id = u.id
        ORDER BY o.created_at DESC LIMIT 5
    ''').fetchall()
    
    db.close()
    
    # Convert recent_orders list
    recent_orders = [dict(order) for order in recent_orders]
    recent_orders = convert_timestamps(recent_orders)
    
    return render_template('admin_dashboard.html',
                         total_users=total_users,
                         total_products=total_products,
                         total_orders=total_orders,
                         total_revenue=total_revenue,
                         recent_orders=recent_orders)

@app.route('/admin/products')
@admin_required
def admin_products():
    """Admin products management"""
    db = get_db()
    products = db.execute('SELECT * FROM products ORDER BY created_at DESC').fetchall()
    db.close()
    
    return render_template('admin_products.html', products=products)

@app.route('/admin/product/add', methods=['GET', 'POST'])
@admin_required
def add_product():
    """Add new product"""
    if request.method == 'POST':
        data = request.form
        
        if not all([data.get('name'), data.get('category'), data.get('price'), data.get('stock')]):
            flash('Missing required fields.', 'danger')
            return redirect(url_for('add_product'))
        
        db = get_db()
        db.execute('''
            INSERT INTO products (name, category, description, price, original_price, stock, image_url)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        ''', (data['name'], data['category'], data.get('description'),
              float(data['price']), float(data.get('original_price', 0)),
              int(data['stock']), data.get('image_url', 'https://via.placeholder.com/400')))
        
        db.commit()
        db.close()
        
        flash('Product added successfully!', 'success')
        return redirect(url_for('admin_products'))
    
    return render_template('admin_add_product.html')

@app.route('/admin/product/edit/<int:product_id>', methods=['GET', 'POST'])
@admin_required
def edit_product(product_id):
    """Edit product"""
    db = get_db()
    product = db.execute('SELECT * FROM products WHERE id = ?', (product_id,)).fetchone()
    
    if not product:
        flash('Product not found.', 'danger')
        return redirect(url_for('admin_products'))
    
    if request.method == 'POST':
        data = request.form
        
        db.execute('''
            UPDATE products SET name = ?, category = ?, description = ?, price = ?, 
            original_price = ?, stock = ?, image_url = ? WHERE id = ?
        ''', (data['name'], data['category'], data.get('description'),
              float(data['price']), float(data.get('original_price', 0)),
              int(data['stock']), data.get('image_url', product['image_url']), product_id))
        
        db.commit()
        db.close()
        
        flash('Product updated successfully!', 'success')
        return redirect(url_for('admin_products'))
    
    db.close()
    return render_template('admin_edit_product.html', product=product)

@app.route('/admin/product/delete/<int:product_id>', methods=['POST'])
@admin_required
def delete_product(product_id):
    """Delete product"""
    db = get_db()
    db.execute('DELETE FROM products WHERE id = ?', (product_id,))
    db.commit()
    db.close()
    
    flash('Product deleted successfully!', 'success')
    return redirect(url_for('admin_products'))

@app.route('/admin/orders')
@admin_required
def admin_orders():
    """Admin orders management"""
    db = get_db()
    orders = db.execute('''
        SELECT o.*, u.username, u.email FROM orders o
        JOIN users u ON o.user_id = u.id
        ORDER BY o.created_at DESC
    ''').fetchall()
    db.close()
    
    return render_template('admin_orders.html', orders=orders)

@app.route('/admin/order/<int:order_id>')
@admin_required
def admin_order_detail(order_id):
    """Admin order detail"""
    db = get_db()
    order = db.execute('''
        SELECT o.*, u.* FROM orders o
        JOIN users u ON o.user_id = u.id
        WHERE o.id = ?
    ''', (order_id,)).fetchone()
    
    if not order:
        flash('Order not found.', 'danger')
        return redirect(url_for('admin_orders'))
    
    order_items = db.execute('''
        SELECT oi.*, p.name, p.image_url FROM order_items oi
        JOIN products p ON oi.product_id = p.id
        WHERE oi.order_id = ?
    ''', (order_id,)).fetchall()
    db.close()
    
    return render_template('admin_order_detail.html', order=order, order_items=order_items)

@app.route('/admin/order/<int:order_id>/update-status', methods=['POST'])
@admin_required
def update_order_status(order_id):
    """Update order status"""
    data = request.json
    status = data.get('status')
    
    db = get_db()
    db.execute('UPDATE orders SET status = ? WHERE id = ?', (status, order_id))
    db.commit()
    db.close()
    
    return jsonify({'success': True, 'message': 'Order status updated'})

@app.route('/admin/users')
@admin_required
def admin_users():
    """Admin users management"""
    db = get_db()
    users = db.execute('SELECT * FROM users WHERE is_admin = 0 ORDER BY created_at DESC').fetchall()
    db.close()
    
    # Convert users list
    users = [dict(user) for user in users]
    users = convert_timestamps(users)
    
    return render_template('admin_users.html', users=users)

# ==================== ERROR HANDLERS ====================

@app.errorhandler(404)
def not_found(error):
    return render_template('404.html'), 404

@app.errorhandler(500)
def internal_error(error):
    return render_template('500.html'), 500

# ==================== RUN APPLICATION ====================

if __name__ == '__main__':
    init_db()
    app.run(debug=True, host='0.0.0.0', port=5000)