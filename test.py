import unittest
import json
import sqlite3
import os
import sys
import time
import tempfile
import uuid
from werkzeug.security import generate_password_hash

# ── Make sure app.py is importable from the same directory ──────────────────
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from app import app, init_db, get_db, DATABASE


# ════════════════════════════════════════════════════════════════════════════
#  HELPERS
# ════════════════════════════════════════════════════════════════════════════

def get_row_counts(db):
    """Return a snapshot of every table's row-count."""
    tables = ['users', 'products', 'cart', 'orders', 'order_items', 'wishlist']
    return {t: db.execute(f'SELECT COUNT(*) FROM {t}').fetchone()[0] for t in tables}


# ════════════════════════════════════════════════════════════════════════════
#  BASE TEST CASE  –  fresh in-memory DB per test
# ════════════════════════════════════════════════════════════════════════════

class BaseTestCase(unittest.TestCase):

    def setUp(self):
        """
        Redirect the app to a dedicated test DB, rebuild schema,
        seed ONE user + ONE product so routes have something to work with.
        No extra rows should remain after any test.
        """
        # Use unique test database filename for each test to avoid locking issues
        self.test_db = f'test_retail_{uuid.uuid4().hex[:8]}.db'

        # point the module-level constant to our test DB
        import app as app_module
        app_module.DATABASE = self.test_db

        app.config['TESTING'] = True
        app.config['WTF_CSRF_ENABLED'] = False
        app.secret_key = 'test-secret-key'

        self.client = app.test_client()

        # build fresh schema only (without auto-inserting 20 products)
        self._init_test_db()

        # seed baseline data  (1 user, 1 product)
        db = get_db()
        db.execute(
            'INSERT OR IGNORE INTO users '
            '(username, email, password, full_name, is_admin) '
            'VALUES (?,?,?,?,?)',
            ('testuser', 'test@test.com',
             generate_password_hash('password123'), 'Test User', 0)
        )
        db.execute(
            'INSERT OR IGNORE INTO products '
            '(name, category, description, price, original_price, stock, image_url, rating, reviews_count) '
            'VALUES (?,?,?,?,?,?,?,?,?)',
            ('Test Product', 'Electronics', 'A test product description',
             999.00, 1299.00, 100,
             'https://images.unsplash.com/photo-1592750475338-74b7b21085ab?w=600&q=80',
             4.5, 10)
        )
        db.commit()
        db.close()

        # remember baseline counts so we can assert no leakage
        db = get_db()
        self.baseline = get_row_counts(db)
        db.close()

    def _init_test_db(self):
        """Initialize test database schema ONLY (no auto-insert of products)"""
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
        db.close()

    def tearDown(self):
        """Delete test DB after every test, ensuring connections are closed."""
        # Close any open connections
        try:
            import app as app_module
            if hasattr(app_module, '_db'):
                app_module._db.close()
        except:
            pass
        
        # Wait a moment to ensure file is released
        time.sleep(0.1)
        
        # Delete test DB file
        if os.path.exists(self.test_db):
            try:
                os.remove(self.test_db)
            except Exception as e:
                # If file is still locked, try again after a delay
                time.sleep(0.5)
                try:
                    os.remove(self.test_db)
                except:
                    pass

    # ── convenience: log in as the seeded user ───────────────────────────
    def login(self, username='testuser', password='password123'):
        return self.client.post('/login', data={
            'username': username, 'password': password
        }, follow_redirects=True)

    def logout(self):
        return self.client.get('/logout', follow_redirects=True)

    def login_admin(self):
        return self.client.post('/admin-login', data={
            'username': 'admin', 'password': '111admin'
        }, follow_redirects=True)

    def get_product_id(self):
        db = get_db()
        p = db.execute('SELECT id FROM products LIMIT 1').fetchone()
        db.close()
        return p['id']

    def get_user_id(self):
        db = get_db()
        u = db.execute("SELECT id FROM users WHERE username='testuser'").fetchone()
        db.close()
        return u['id']


# ════════════════════════════════════════════════════════════════════════════
#  1. AUTHENTICATION TESTS
# ════════════════════════════════════════════════════════════════════════════

class TestAuthentication(BaseTestCase):

    # ── registration ────────────────────────────────────────────────────
    def test_register_page_loads(self):
        r = self.client.get('/register')
        self.assertEqual(r.status_code, 200)

    def test_register_new_user(self):
        db = get_db()
        before = db.execute('SELECT COUNT(*) FROM users').fetchone()[0]
        db.close()

        r = self.client.post('/register', data={
            'username': 'newuser',
            'email':    'new@test.com',
            'password': 'newpass123',
            'full_name': 'New User'
        }, follow_redirects=True)
        self.assertEqual(r.status_code, 200)

        db = get_db()
        after = db.execute('SELECT COUNT(*) FROM users').fetchone()[0]
        user  = db.execute("SELECT * FROM users WHERE username='newuser'").fetchone()
        db.close()

        self.assertEqual(after, before + 1)
        self.assertIsNotNone(user)

        # clean up the extra user so baseline is restored
        db = get_db()
        db.execute("DELETE FROM users WHERE username='newuser'")
        db.commit()
        db.close()

    def test_register_duplicate_username(self):
        db = get_db()
        before = db.execute('SELECT COUNT(*) FROM users').fetchone()[0]
        db.close()

        self.client.post('/register', data={
            'username': 'testuser',       # already exists
            'email':    'other@test.com',
            'password': 'pass123',
        }, follow_redirects=True)

        db = get_db()
        after = db.execute('SELECT COUNT(*) FROM users').fetchone()[0]
        db.close()
        self.assertEqual(before, after, "Duplicate user must NOT be inserted")

    def test_register_short_password(self):
        db = get_db()
        before = db.execute('SELECT COUNT(*) FROM users').fetchone()[0]
        db.close()

        self.client.post('/register', data={
            'username': 'shortpwduser',
            'email':    'short@test.com',
            'password': '123',            # too short
        }, follow_redirects=True)

        db = get_db()
        after = db.execute('SELECT COUNT(*) FROM users').fetchone()[0]
        db.close()
        self.assertEqual(before, after, "Short-password user must NOT be inserted")

    def test_register_invalid_email(self):
        db = get_db()
        before = db.execute('SELECT COUNT(*) FROM users').fetchone()[0]
        db.close()

        self.client.post('/register', data={
            'username': 'bademailuser',
            'email':    'not-an-email',
            'password': 'validpass',
        }, follow_redirects=True)

        db = get_db()
        after = db.execute('SELECT COUNT(*) FROM users').fetchone()[0]
        db.close()
        self.assertEqual(before, after, "Invalid-email user must NOT be inserted")

    # ── login / logout ───────────────────────────────────────────────────
    def test_login_page_loads(self):
        r = self.client.get('/login')
        self.assertEqual(r.status_code, 200)

    def test_login_valid_credentials(self):
        r = self.login()
        self.assertEqual(r.status_code, 200)
        self.assertIn(b'testuser', r.data)

    def test_login_invalid_credentials(self):
        r = self.client.post('/login', data={
            'username': 'testuser',
            'password': 'wrongpassword'
        }, follow_redirects=True)
        self.assertIn(b'Invalid', r.data)

    def test_logout(self):
        self.login()
        r = self.logout()
        self.assertEqual(r.status_code, 200)

    # ── admin login ──────────────────────────────────────────────────────
    def test_admin_login_valid(self):
        r = self.login_admin()
        self.assertEqual(r.status_code, 200)

        # clean up admin user created during login
        db = get_db()
        db.execute("DELETE FROM users WHERE username='admin'")
        db.commit()
        db.close()

    def test_admin_login_invalid(self):
        r = self.client.post('/admin-login', data={
            'username': 'admin',
            'password': 'wrongpassword'
        }, follow_redirects=True)
        self.assertIn(b'Invalid', r.data)


# ════════════════════════════════════════════════════════════════════════════
#  2. PAGE / ROUTE TESTS
# ════════════════════════════════════════════════════════════════════════════

class TestPages(BaseTestCase):

    def test_home_page(self):
        r = self.client.get('/')
        self.assertEqual(r.status_code, 200)

    def test_products_page(self):
        r = self.client.get('/products')
        self.assertEqual(r.status_code, 200)

    def test_products_category_filter(self):
        r = self.client.get('/products?category=Electronics')
        self.assertEqual(r.status_code, 200)

    def test_products_search(self):
        r = self.client.get('/products?search=Test')
        self.assertEqual(r.status_code, 200)

    def test_products_sort_price_low(self):
        r = self.client.get('/products?sort=price_low')
        self.assertEqual(r.status_code, 200)

    def test_products_sort_price_high(self):
        r = self.client.get('/products?sort=price_high')
        self.assertEqual(r.status_code, 200)

    def test_products_sort_rating(self):
        r = self.client.get('/products?sort=rating')
        self.assertEqual(r.status_code, 200)

    def test_product_detail_valid(self):
        pid = self.get_product_id()
        r = self.client.get(f'/product/{pid}')
        self.assertEqual(r.status_code, 200)

    def test_product_detail_invalid(self):
        r = self.client.get('/product/99999', follow_redirects=True)
        self.assertEqual(r.status_code, 200)
        self.assertIn(b'not found', r.data.lower())

    def test_cart_page_guest(self):
        r = self.client.get('/cart')
        self.assertEqual(r.status_code, 200)

    def test_profile_requires_login(self):
        r = self.client.get('/profile', follow_redirects=True)
        self.assertIn(b'log in', r.data.lower())

    def test_checkout_requires_login(self):
        r = self.client.get('/checkout', follow_redirects=True)
        self.assertIn(b'log in', r.data.lower())

    def test_orders_requires_login(self):
        r = self.client.get('/orders', follow_redirects=True)
        self.assertIn(b'log in', r.data.lower())

    def test_404_page(self):
        r = self.client.get('/this-route-does-not-exist')
        self.assertEqual(r.status_code, 404)


# ════════════════════════════════════════════════════════════════════════════
#  3. CART TESTS
# ════════════════════════════════════════════════════════════════════════════

class TestCart(BaseTestCase):

    def setUp(self):
        super().setUp()
        self.login()
        self.pid = self.get_product_id()

    def _cart_count(self):
        db = get_db()
        n = db.execute('SELECT COUNT(*) FROM cart').fetchone()[0]
        db.close()
        return n

    def test_add_to_cart(self):
        before = self._cart_count()
        r = self.client.post('/api/cart/add',
                             json={'product_id': self.pid, 'quantity': 1},
                             content_type='application/json')
        self.assertEqual(r.status_code, 200)
        data = json.loads(r.data)
        self.assertTrue(data['success'])
        self.assertEqual(self._cart_count(), before + 1)

    def test_add_to_cart_increases_quantity(self):
        self.client.post('/api/cart/add',
                         json={'product_id': self.pid, 'quantity': 1},
                         content_type='application/json')
        count_after_first = self._cart_count()

        self.client.post('/api/cart/add',
                         json={'product_id': self.pid, 'quantity': 1},
                         content_type='application/json')
        # same product → quantity updated, NOT a new row
        self.assertEqual(self._cart_count(), count_after_first,
                         "Re-adding same product must update quantity, not insert new row")

        db = get_db()
        qty = db.execute('SELECT quantity FROM cart WHERE product_id=?',
                         (self.pid,)).fetchone()[0]
        db.close()
        self.assertEqual(qty, 2)

    def test_add_invalid_product(self):
        before = self._cart_count()
        r = self.client.post('/api/cart/add',
                             json={'product_id': 99999, 'quantity': 1},
                             content_type='application/json')
        self.assertEqual(r.status_code, 404)
        self.assertEqual(self._cart_count(), before,
                         "Invalid product must NOT create a cart row")

    def test_add_exceeds_stock(self):
        before = self._cart_count()
        r = self.client.post('/api/cart/add',
                             json={'product_id': self.pid, 'quantity': 9999},
                             content_type='application/json')
        self.assertEqual(r.status_code, 400)
        self.assertEqual(self._cart_count(), before,
                         "Over-stock add must NOT create a cart row")

    def test_cart_count_api(self):
        self.client.post('/api/cart/add',
                         json={'product_id': self.pid, 'quantity': 2},
                         content_type='application/json')
        r = self.client.get('/api/cart/count')
        data = json.loads(r.data)
        self.assertEqual(data['count'], 2)

    def test_update_cart(self):
        self.client.post('/api/cart/add',
                         json={'product_id': self.pid, 'quantity': 1},
                         content_type='application/json')
        db = get_db()
        cart_id = db.execute('SELECT id FROM cart WHERE product_id=?',
                             (self.pid,)).fetchone()['id']
        db.close()

        r = self.client.post('/api/cart/update',
                             json={'cart_id': cart_id, 'quantity': 3},
                             content_type='application/json')
        self.assertEqual(r.status_code, 200)

        db = get_db()
        qty = db.execute('SELECT quantity FROM cart WHERE id=?',
                         (cart_id,)).fetchone()[0]
        db.close()
        self.assertEqual(qty, 3)

    def test_remove_from_cart(self):
        self.client.post('/api/cart/add',
                         json={'product_id': self.pid, 'quantity': 1},
                         content_type='application/json')
        db = get_db()
        cart_id = db.execute('SELECT id FROM cart WHERE product_id=?',
                             (self.pid,)).fetchone()['id']
        db.close()

        before = self._cart_count()
        r = self.client.delete(f'/api/cart/remove/{cart_id}')
        self.assertEqual(r.status_code, 200)
        self.assertEqual(self._cart_count(), before - 1)

    def test_add_to_cart_requires_login(self):
        self.logout()
        before = self._cart_count()
        r = self.client.post('/api/cart/add',
                             json={'product_id': self.pid, 'quantity': 1},
                             content_type='application/json')
        # should redirect to login
        self.assertIn(r.status_code, [302, 401])
        self.assertEqual(self._cart_count(), before,
                         "Guest add-to-cart must NOT create a cart row")


# ════════════════════════════════════════════════════════════════════════════
#  4. CHECKOUT & ORDER TESTS
# ════════════════════════════════════════════════════════════════════════════

class TestCheckoutOrders(BaseTestCase):

    def setUp(self):
        super().setUp()
        self.login()
        self.pid = self.get_product_id()
        # put one item in the cart
        self.client.post('/api/cart/add',
                         json={'product_id': self.pid, 'quantity': 1},
                         content_type='application/json')

    def _order_count(self):
        db = get_db()
        n = db.execute('SELECT COUNT(*) FROM orders').fetchone()[0]
        db.close()
        return n

    def test_checkout_page_loads(self):
        r = self.client.get('/checkout')
        self.assertEqual(r.status_code, 200)

    def test_checkout_empty_cart_redirects(self):
        # remove what we added in setUp
        db = get_db()
        db.execute('DELETE FROM cart WHERE user_id=?', (self.get_user_id(),))
        db.commit()
        db.close()

        r = self.client.get('/checkout', follow_redirects=True)
        self.assertIn(b'empty', r.data.lower())

    def test_checkout_creates_order(self):
        before = self._order_count()
        r = self.client.post('/checkout', data={
            'delivery_address': '123 Test Street',
            'delivery_phone':   '9999999999',
            'delivery_email':   'test@test.com',
        }, follow_redirects=False)
        # should redirect to /payment
        self.assertIn(r.status_code, [302, 200])
        self.assertEqual(self._order_count(), before + 1)

    def test_checkout_missing_fields_no_order(self):
        before = self._order_count()
        self.client.post('/checkout', data={
            'delivery_address': '123 Street',
            # phone and email missing
        }, follow_redirects=True)
        self.assertEqual(self._order_count(), before,
                         "Incomplete checkout must NOT create an order")

    def test_payment_page_requires_order_in_session(self):
        # no order in session → redirect away
        r = self.client.get('/payment', follow_redirects=True)
        self.assertEqual(r.status_code, 200)

    def test_full_order_flow_cod(self):
        before_orders = self._order_count()
        db = get_db()
        before_cart = db.execute('SELECT COUNT(*) FROM cart WHERE user_id=?',
                                 (self.get_user_id(),)).fetchone()[0]
        db.close()

        # step 1: checkout
        self.client.post('/checkout', data={
            'delivery_address': '123 Test Street',
            'delivery_phone':   '9999999999',
            'delivery_email':   'test@test.com',
        }, follow_redirects=False)

        # step 2: payment
        r = self.client.post('/payment',
                             data={'payment_method': 'cod'},
                             follow_redirects=True)
        self.assertEqual(r.status_code, 200)
        self.assertEqual(self._order_count(), before_orders + 1)

        # cart must be cleared after payment
        db = get_db()
        after_cart = db.execute('SELECT COUNT(*) FROM cart WHERE user_id=?',
                                (self.get_user_id(),)).fetchone()[0]
        db.close()
        self.assertEqual(after_cart, 0, "Cart must be empty after successful order")

    def test_my_orders_page(self):
        r = self.client.get('/orders')
        self.assertEqual(r.status_code, 200)

    def test_order_detail_invalid(self):
        r = self.client.get('/order/99999', follow_redirects=True)
        self.assertEqual(r.status_code, 200)


# ════════════════════════════════════════════════════════════════════════════
#  5. PROFILE TESTS
# ════════════════════════════════════════════════════════════════════════════

class TestProfile(BaseTestCase):

    def setUp(self):
        super().setUp()
        self.login()

    def test_profile_page_loads(self):
        r = self.client.get('/profile')
        self.assertEqual(r.status_code, 200)

    def test_update_profile(self):
        r = self.client.post('/api/profile/update',
                             json={
                                 'full_name':   'Updated Name',
                                 'phone':       '9876543210',
                                 'address':     '456 New Street',
                                 'city':        'Mumbai',
                                 'country':     'India',
                                 'postal_code': '400001',
                             },
                             content_type='application/json')
        self.assertEqual(r.status_code, 200)
        data = json.loads(r.data)
        self.assertTrue(data['success'])

        db = get_db()
        user = db.execute("SELECT * FROM users WHERE username='testuser'").fetchone()
        db.close()
        self.assertEqual(user['full_name'], 'Updated Name')
        self.assertEqual(user['city'], 'Mumbai')

        # no extra user rows created
        db = get_db()
        count = db.execute('SELECT COUNT(*) FROM users WHERE is_admin=0').fetchone()[0]
        db.close()
        self.assertEqual(count, self.baseline['users'],
                         "Profile update must NOT insert extra user rows")

    def test_update_profile_requires_login(self):
        self.logout()
        r = self.client.post('/api/profile/update',
                             json={'full_name': 'Hacker'},
                             content_type='application/json')
        self.assertIn(r.status_code, [302, 401])


# ════════════════════════════════════════════════════════════════════════════
#  6. ADMIN TESTS
# ════════════════════════════════════════════════════════════════════════════

class TestAdmin(BaseTestCase):

    def setUp(self):
        super().setUp()
        self.login_admin()

    def tearDown(self):
        # remove admin user created during admin login
        db = get_db()
        db.execute("DELETE FROM users WHERE username='admin'")
        db.commit()
        db.close()
        super().tearDown()

    def test_dashboard_loads(self):
        r = self.client.get('/admin/dashboard')
        self.assertEqual(r.status_code, 200)

    def test_admin_products_page(self):
        r = self.client.get('/admin/products')
        self.assertEqual(r.status_code, 200)

    def test_admin_orders_page(self):
        r = self.client.get('/admin/orders')
        self.assertEqual(r.status_code, 200)

    def test_admin_users_page(self):
        r = self.client.get('/admin/users')
        self.assertEqual(r.status_code, 200)

    def test_add_product(self):
        db = get_db()
        before = db.execute('SELECT COUNT(*) FROM products').fetchone()[0]
        db.close()

        r = self.client.post('/admin/product/add', data={
            'name':           'Admin Test Product',
            'category':       'Electronics',
            'description':    'Added by admin test',
            'price':          '1999',
            'original_price': '2499',
            'stock':          '50',
            'image_url':      'https://images.unsplash.com/photo-1592750475338-74b7b21085ab?w=600',
        }, follow_redirects=True)
        self.assertEqual(r.status_code, 200)

        db = get_db()
        after = db.execute('SELECT COUNT(*) FROM products').fetchone()[0]
        db.close()
        self.assertEqual(after, before + 1)

        # clean up
        db = get_db()
        db.execute("DELETE FROM products WHERE name='Admin Test Product'")
        db.commit()
        db.close()

    def test_add_product_missing_fields(self):
        db = get_db()
        before = db.execute('SELECT COUNT(*) FROM products').fetchone()[0]
        db.close()

        self.client.post('/admin/product/add', data={
            'name': 'Incomplete Product',
            # price and stock missing
        }, follow_redirects=True)

        db = get_db()
        after = db.execute('SELECT COUNT(*) FROM products').fetchone()[0]
        db.close()
        self.assertEqual(before, after,
                         "Incomplete product must NOT be inserted")

    def test_edit_product(self):
        pid = self.get_product_id()
        r = self.client.post(f'/admin/product/edit/{pid}', data={
            'name':           'Updated Product Name',
            'category':       'Electronics',
            'description':    'Updated description',
            'price':          '1099',
            'original_price': '1399',
            'stock':          '80',
            'image_url':      'https://images.unsplash.com/photo-1592750475338-74b7b21085ab?w=600',
        }, follow_redirects=True)
        self.assertEqual(r.status_code, 200)

        db = get_db()
        p = db.execute('SELECT * FROM products WHERE id=?', (pid,)).fetchone()
        db.close()
        self.assertEqual(p['name'], 'Updated Product Name')
        self.assertEqual(p['price'], 1099.0)

        # count unchanged
        db = get_db()
        count = db.execute('SELECT COUNT(*) FROM products').fetchone()[0]
        db.close()
        self.assertEqual(count, self.baseline['products'],
                         "Edit must NOT change product count")

    def test_delete_product(self):
        # add a throwaway product
        db = get_db()
        db.execute(
            'INSERT INTO products (name,category,price,stock) VALUES (?,?,?,?)',
            ('ToDelete', 'Electronics', 1.0, 1)
        )
        db.commit()
        del_id = db.execute("SELECT id FROM products WHERE name='ToDelete'").fetchone()['id']
        before = db.execute('SELECT COUNT(*) FROM products').fetchone()[0]
        db.close()

        r = self.client.post(f'/admin/product/delete/{del_id}',
                             follow_redirects=True)
        self.assertEqual(r.status_code, 200)

        db = get_db()
        after = db.execute('SELECT COUNT(*) FROM products').fetchone()[0]
        db.close()
        self.assertEqual(after, before - 1)

    def test_update_order_status(self):
        # create an order first
        uid = self.get_user_id()
        db = get_db()
        db.execute(
            'INSERT INTO orders (user_id, order_number, total_amount, status) '
            'VALUES (?,?,?,?)',
            (uid, 'ORD-TEST-001', 999.0, 'pending')
        )
        db.commit()
        oid = db.execute("SELECT id FROM orders WHERE order_number='ORD-TEST-001'").fetchone()['id']
        db.close()

        r = self.client.post(f'/admin/order/{oid}/update-status',
                             json={'status': 'shipped'},
                             content_type='application/json')
        self.assertEqual(r.status_code, 200)
        data = json.loads(r.data)
        self.assertTrue(data['success'])

        db = get_db()
        o = db.execute('SELECT status FROM orders WHERE id=?', (oid,)).fetchone()
        db.close()
        self.assertEqual(o['status'], 'shipped')

        # clean up
        db = get_db()
        db.execute('DELETE FROM orders WHERE id=?', (oid,))
        db.commit()
        db.close()

    def test_admin_blocked_for_normal_user(self):
        self.logout()
        self.login()          # log in as normal user
        r = self.client.get('/admin/dashboard', follow_redirects=True)
        self.assertNotIn(b'dashboard', r.data.lower().replace(b' ', b''))
        self.logout()


# ════════════════════════════════════════════════════════════════════════════
#  7. DATA INTEGRITY — no orphan / ghost rows
# ════════════════════════════════════════════════════════════════════════════

class TestDataIntegrity(BaseTestCase):

    def test_no_extra_rows_after_failed_register(self):
        db = get_db()
        before = get_row_counts(db)
        db.close()

        # bad email
        self.client.post('/register', data={
            'username': 'ghost', 'email': 'bad', 'password': 'pass123'
        }, follow_redirects=True)

        db = get_db()
        after = get_row_counts(db)
        db.close()
        self.assertEqual(before, after,
                         "Failed registration must leave all counts unchanged")

    def test_no_extra_rows_after_failed_cart_add(self):
        self.login()
        db = get_db()
        before = get_row_counts(db)
        db.close()

        self.client.post('/api/cart/add',
                         json={'product_id': 99999, 'quantity': 1},
                         content_type='application/json')

        db = get_db()
        after = get_row_counts(db)
        db.close()
        self.assertEqual(before['cart'], after['cart'],
                         "Failed cart add must NOT create a cart row")

    def test_no_extra_rows_after_incomplete_checkout(self):
        self.login()
        self.client.post('/api/cart/add',
                         json={'product_id': self.get_product_id(), 'quantity': 1},
                         content_type='application/json')

        db = get_db()
        before_orders = db.execute('SELECT COUNT(*) FROM orders').fetchone()[0]
        db.close()

        self.client.post('/checkout', data={
            'delivery_address': 'only address'
            # phone & email missing
        }, follow_redirects=True)

        db = get_db()
        after_orders = db.execute('SELECT COUNT(*) FROM orders').fetchone()[0]
        db.close()
        self.assertEqual(before_orders, after_orders,
                         "Incomplete checkout must NOT insert an order")


# ════════════════════════════════════════════════════════════════════════════
#  RUNNER  –  clean PASS / FAIL output
# ════════════════════════════════════════════════════════════════════════════

class VerboseResult(unittest.TextTestResult):
    """Prints a clean PASS / FAIL line for every test."""
    def addSuccess(self, test):
        super().addSuccess(test)
        print(f"  PASS  {test._testMethodName}")

    def addFailure(self, test, err):
        super().addFailure(test, err)
        print(f"  FAIL  {test._testMethodName}")
        print(f"        {err[1]}")

    def addError(self, test, err):
        super().addError(test, err)
        print(f"  ERROR {test._testMethodName}")
        print(f"        {err[1]}")


class VerboseRunner(unittest.TextTestRunner):
    resultclass = VerboseResult


if __name__ == '__main__':
    SECTIONS = [
        ("Authentication",  TestAuthentication),
        ("Pages & Routes",  TestPages),
        ("Shopping Cart",   TestCart),
        ("Checkout/Orders", TestCheckoutOrders),
        ("User Profile",    TestProfile),
        ("Admin Panel",     TestAdmin),
        ("Data Integrity",  TestDataIntegrity),
    ]

    total_pass = total_fail = total_error = 0
    all_failures = []

    print("\n" + "=" * 60)
    print("   NEXUS RETAIL SYSTEM - TEST SUITE")
    print("=" * 60)

    for section_name, test_class in SECTIONS:
        suite = unittest.TestLoader().loadTestsFromTestCase(test_class)
        print(f"\n>  {section_name}")
        print("-" * 60)
        runner = VerboseRunner(stream=open(os.devnull, 'w'), verbosity=0)
        result = runner.run(suite)

        total_pass  += result.testsRun - len(result.failures) - len(result.errors)
        total_fail  += len(result.failures)
        total_error += len(result.errors)
        all_failures += result.failures + result.errors

    print("\n" + "=" * 60)
    print(f"  TOTAL : {total_pass + total_fail + total_error} tests")
    print(f"  PASS  : {total_pass}")
    print(f"  FAIL  : {total_fail}")
    print(f"  ERROR : {total_error}")
    print("=" * 60)

    if all_failures:
        print("\n-- FAILURE DETAILS --")
        for test, traceback in all_failures:
            print(f"\n  {test}")
            print(f"  {traceback.strip().splitlines()[-1]}")

    status = "ALL TESTS PASSED ✓" if (total_fail + total_error) == 0 else "SOME TESTS FAILED ✗"
    print(f"\n  {status}\n")
    sys.exit(0 if (total_fail + total_error) == 0 else 1)