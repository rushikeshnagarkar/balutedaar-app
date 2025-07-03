from flask import Flask, jsonify, request, render_template, redirect, url_for, session
import requests
import json
from datetime import datetime, timedelta
import pymysql
import urllib3
import re
import os
import razorpay
import uuid
import logging
from dotenv import load_dotenv
import random
import string
from functools import wraps

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    filename='app.log',
    format='%(asctime)s - %(levelname)s - %(message)s'
)

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

app = Flask(__name__)
app.secret_key = os.urandom(24)
load_dotenv()
required_env = ["MYSQL_HOST", "MYSQL_USER", "MYSQL_PASSWORD", "MYSQL_DB", "AUTH_KEY", "RAZORPAY_KEY_ID", "RAZORPAY_KEY_SECRET"]
for var in required_env:
    if not os.getenv(var):
        logging.error(f"Missing environment variable: {var}")
        exit(1)

aws_host = os.getenv("MYSQL_HOST")
usr = os.getenv("MYSQL_USER")
pas = os.getenv("MYSQL_PASSWORD")
db = os.getenv("MYSQL_DB")
authkey = os.getenv("AUTH_KEY")
razorpay_client = razorpay.Client(auth=(
    os.getenv("RAZORPAY_KEY_ID"),
    os.getenv("RAZORPAY_KEY_SECRET")
))

# Admin credentials
ADMIN_USERNAME = "admin"
ADMIN_PASSWORD = "admin123"

# Greeting words
greeting_word = ['Hi', 'hi', 'HI', 'Hii', 'hii', 'HII', 'Hello', 'hello', 'HELLO', 'Welcome', 'welcome', 'WELCOME', 'Hey', 'hey', 'HEY']

# Messages
m1 = '''Please select a combo from the list below:'''
m3 = '''🚚 Just one more step!

Kindly share your complete delivery address in English (e.g., Flat 101, Baner Road, Pune) so we can deliver your veggies without any delay.'''
invalid_address = '''😕 Oops! That doesn’t look like a valid address. Please enter a complete address with house/flat number, street name, and area (e.g., Flat 101, Baner Road, Pune). Use letters, numbers, spaces, commas, periods, hyphens, or slashes only.'''
invalid_name = '''⚠️ Please enter a valid name using alphabetic characters, numbers, or spaces only.'''
referral_prompt = '''🧩 Got a referral code? Drop it now for an instant 10% welcome discount!

Or click 'Skip' to browse our fresh veggie combos!'''
invalid_referral = '''⚠️ Sorry, the referral code {code} is invalid, expired, or has reached its limit. Try another code or click 'Skip' to continue!'''
referral_success = '''✅ Referral code accepted! 🎉 You’ve unlocked ₹20 OFF on your first order!'''
wl = '''Ram Ram Mandali 🙏

Hi, *{name}!* 👋

🌟 *Welcome to Balutedaar* 🌟
We bring you *Farm-Fresh Vegetable Boxes* handpicked with love by rural mothers, curated for urban families like yours! 💚

Here’s why you’ll love us:  
👩‍🌾 *Fresh from Mother Earth* – Pure, healthy veggies for your family.  
🌍 *Eco-Friendly* – Low carbon footprint for a greener planet.  
💸 *Support Farmers Directly* – Your purchase empowers farmers with fair earnings.  
👩‍💼 *Empower Rural Women* – Create jobs for hardworking women in villages.  
🌱 *Your Choice, Your Way* – Pick what’s best for your family, we’ll deliver!

🌟 *A small step towards fresh, sustainable, and empowering food for your loved ones!* 🇮🇳

Let’s get your fresh veggies on the way! 🚜  
Please share your *6-digit pincode* to continue. 📍'''
wl_fallback = '''Ram Ram Mandali 🙏

🌟 *Welcome to Balutedaar!* 🌿🥦

We bring you *Farm-Fresh Vegetable Boxes* handpicked with love by rural mothers, curated for urban families like yours! 💚

Here’s why you’ll love us:  
👩‍🌾 *Fresh from Mother Earth* – Pure, healthy veggies for your family.  
🌍 *Eco-Friendly* – Low carbon footprint for a greener planet.  
💸 *Support Farmers Directly* – Your purchase empowers farmers with fair earnings.  
👩‍💼 *Empower Rural Women* – Create jobs for hardworking women in villages.  
🌱 *Your Choice, Your Way* – Pick what’s best for your family, we’ll deliver!

🌟 *A small step towards fresh, sustainable, and empowering food for your loved ones!* 🇮🇳

Let’s get started – please enter your *Name* to order. 👇'''
r2 = '''*Hi {name}!* 👋  
Please enter your *6-digit pincode* to continue. 📍'''
r3 = '''*Sorry, this pincode is not served yet!* 😔  
We currently deliver to these areas:  
• *411038*  
• *411052*  
• *411058*    
• *411041*  
Please enter a valid pincode from the list above. 📍'''
r4 = '''*Invalid pincode!* ⚠️  
Please enter only a *6-digit pincode* (e.g., 411038). 📍'''
out_of_stock = '''❌ Sorry! Combo boxes are sold out for your pincode today. Please try again tomorrow or contact support.'''
availability_message = '''✅ Combo boxes available for your area on {date}:
{combo_list}
Would you like to book?'''

CATALOG_ID = "1221166119417288"

FALLBACK_COMBOS = {
    "D-9011": {"name": "Amaranth Combo", "price": 225.00}, 
    "A-9011": {"name": "Methi Combo", "price": 180.00},
    "E-9011": {"name": "Dill Combo", "price": 111.00},
    "B-9011": {"name": "Kanda Paat Combo", "price": 150.00},
    "C-9011": {"name": "Palak Combo", "price": 210.00},
    "xzwqdyrcl9": {"name": "Spinach - पालक", "price": 400.00},
    "7e8sbb1xg8": {"name": "Fenugreek - मेथी", "price": 370.00},
    "dm4ngkc9xr": {"name": "Amaranth - लाल माठ", "price": 380.00}
}

TIERED_DISCOUNTS = {
    1: 0.10,
    2: 0.20,
    3: 0.30,
    4: 0.40,
    5: 0.50
}

def init_combo_inventory():
    try:
        cnx = pymysql.connect(user=usr, password=pas, host=aws_host, database=db)
        cursor = cnx.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS combo_inventory (
                id INT AUTO_INCREMENT PRIMARY KEY,
                pincode VARCHAR(6) NOT NULL,
                date DATE NOT NULL,
                combo_id VARCHAR(50) NOT NULL,
                combo_name VARCHAR(100) NOT NULL,
                total_boxes INT NOT NULL,
                booked INT DEFAULT 0,
                remaining INT NOT NULL,
                UNIQUE(pincode, date, combo_id)
            )
        """)
        cnx.commit()
        cnx.close()
        logging.info("Combo inventory table initialized")
    except Exception as e:
        logging.error(f"Failed to initialize combo_inventory table: {e}")

def reset_daily_inventory():
    try:
        cnx = pymysql.connect(user=usr, password=pas, host=aws_host, database=db)
        cursor = cnx.cursor()
        today = datetime.now().date()
        cursor.execute("DELETE FROM combo_inventory WHERE date < %s", (today,))
        cnx.commit()
        cnx.close()
        logging.info("Daily inventory reset completed")
    except Exception as e:
        logging.error(f"Failed to reset daily inventory: {e}")

def check_combo_availability(pincode, date=None):
    try:
        if date is None:
            date = datetime.now().date()
        cnx = pymysql.connect(user=usr, password=pas, host=aws_host, database=db)
        cursor = cnx.cursor()
        cursor.execute(
            "SELECT combo_id, combo_name, remaining FROM combo_inventory WHERE pincode = %s AND date = %s",
            (pincode, date)
        )
        results = cursor.fetchall()
        cnx.close()
        return [{"combo_id": r[0], "combo_name": r[1], "remaining": r[2]} for r in results]
    except Exception as e:
        logging.error(f"Failed to check combo availability for pincode {pincode}: {e}")
        return []

def update_inventory_after_order(pincode, combo_id, quantity, date=None):
    try:
        if date is None:
            date = datetime.now().date()
        cnx = pymysql.connect(user=usr, password=pas, host=aws_host, database=db)
        cursor = cnx.cursor()
        cursor.execute(
            "UPDATE combo_inventory SET booked = booked + %s, remaining = remaining - %s "
            "WHERE pincode = %s AND combo_id = %s AND date = %s AND remaining >= %s",
            (quantity, quantity, pincode, combo_id, date, quantity)
        )
        affected_rows = cursor.rowcount
        cnx.commit()
        cnx.close()
        return affected_rows > 0
    except Exception as e:
        logging.error(f"Failed to update inventory for pincode {pincode}, combo {combo_id}: {e}")
        return False

def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'logged_in' not in session:
            return redirect(url_for('admin_login'))
        return f(*args, **kwargs)
    return decorated_function

@app.route('/admin/login', methods=['GET', 'POST'])
def admin_login():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        if username == ADMIN_USERNAME and password == ADMIN_PASSWORD:
            session['logged_in'] = True
            return redirect(url_for('admin_dashboard'))
        else:
            return render_template_string("""
                <!DOCTYPE html>
                <html>
                <head>
                    <title>Admin Login</title>
                    <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet">
                </head>
                <body>
                    <div class="container mt-5">
                        <h2>Admin Login</h2>
                        <div class="alert alert-danger">Invalid credentials. Try again.</div>
                        <form method="POST">
                            <div class="mb-3">
                                <label for="username" class="form-label">Username</label>
                                <input type="text" class="form-control" id="username" name="username" required>
                            </div>
                            <div class="mb-3">
                                <label for="password" class="form-label">Password</label>
                                <input type="password" class="form-control" id="password" name="password" required>
                            </div>
                            <button type="submit" class="btn btn-primary">Login</button>
                        </form>
                    </div>
                </body>
                </html>
            """)
    return render_template_string("""
        <!DOCTYPE html>
        <html>
        <head>
            <title>Admin Login</title>
            <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet">
        </head>
        <body>
            <div class="container mt-5">
                <h2>Admin Login</h2>
                <form method="POST">
                    <div class="mb-3">
                        <label for="username" class="form-label">Username</label>
                        <input type="text" class="form-control" id="username" name="username" required>
                    </div>
                    <div class="mb-3">
                        <label for="password" class="form-label">Password</label>
                        <input type="password" class="form-control" id="password" name="password" required>
                    </div>
                    <button type="submit" class="btn btn-primary">Login</button>
                </form>
            </div>
        </body>
        </html>
    """)

@app.route('/admin', methods=['GET', 'POST'])
@login_required
def admin_dashboard():
    try:
        cnx = pymysql.connect(user=usr, password=pas, host=aws_host, database=db)
        cursor = cnx.cursor()
        
        today = datetime.now().date()
        tomorrow = today + timedelta(days=1)
        cursor.execute(
            "SELECT order_id, user_phone, customer_name, combo_name, quantity, total_amount, address, pincode, order_status, payment_status "
            "FROM orders WHERE DATE(created_at) IN (%s, %s) ORDER BY created_at DESC",
            (today, tomorrow)
        )
        orders = cursor.fetchall()
        
        cursor.execute(
            "SELECT pincode, combo_id, combo_name, total_boxes, booked, remaining "
            "FROM combo_inventory WHERE date = %s ORDER BY pincode, combo_name",
            (tomorrow,)
        )
        inventory = cursor.fetchall()
        
        if request.method == 'POST':
            pincode = request.form.get('pincode')
            combo_id = request.form.get('combo_id')
            total_boxes = request.form.get('total_boxes')
            date = tomorrow
            if pincode and combo_id and total_boxes.isdigit():
                total_boxes = int(total_boxes)
                combo_name = get_combo_name(combo_id)
                cursor.execute(
                    "INSERT INTO combo_inventory (pincode, date, combo_id, combo_name, total_boxes, remaining) "
                    "VALUES (%s, %s, %s, %s, %s, %s) "
                    "ON DUPLICATE KEY UPDATE total_boxes = %s, remaining = total_boxes - booked",
                    (pincode, date, combo_id, combo_name, total_boxes, total_boxes, total_boxes)
                )
                cnx.commit()
                return redirect(url_for('admin_dashboard'))
        
        cnx.close()
        
        return render_template_string("""
            <!DOCTYPE html>
            <html>
            <head>
                <title>Balutedaar Admin Dashboard</title>
                <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet">
                <style>
                    body { background-color: #f8f9fa; }
                    .card { margin-bottom: 20px; }
                    .table { background-color: white; }
                </style>
            </head>
            <body>
                <div class="container mt-5">
                    <h1>Balutedaar Admin Dashboard</h1>
                    <a href="{{ url_for('logout') }}" class="btn btn-danger mb-3">Logout</a>
                    
                    <h2>Orders (Today & Tomorrow)</h2>
                    <div class="card">
                        <div class="card-body">
                            <table class="table table-striped">
                                <thead>
                                    <tr>
                                        <th>Order ID</th>
                                        <th>Customer</th>
                                        <th>Combo</th>
                                        <th>Qty</th>
                                        <th>Total</th>
                                        <th>Address</th>
                                        <th>Pincode</th>
                                        <th>Order Status</th>
                                        <th>Payment Status</th>
                                    </tr>
                                </thead>
                                <tbody>
                                    {% for order in orders %}
                                    <tr>
                                        <td>{{ order[0] }}</td>
                                        <td>{{ order[2] }} ({{ order[1] }})</td>
                                        <td>{{ order[3] }}</td>
                                        <td>{{ order[4] }}</td>
                                        <td>₹{{ '%.2f' % order[5] }}</td>
                                        <td>{{ order[6] }}</td>
                                        <td>{{ order[7] }}</td>
                                        <td>{{ order[8] }}</td>
                                        <td>{{ order[9] }}</td>
                                    </tr>
                                    {% else %}
                                    <tr><td colspan="9">No orders found</td></tr>
                                    {% endfor %}
                                </tbody>
                            </table>
                        </div>
                    </div>
                    
                    <h2>Combo Inventory (Tomorrow: {{ tomorrow }})</h2>
                    <div class="card">
                        <div class="card-body">
                            <table class="table table-striped">
                                <thead>
                                    <tr>
                                        <th>Pincode</th>
                                        <th>Combo</th>
                                        <th>Total Boxes</th>
                                        <th>Booked</th>
                                        <th>Remaining</th>
                                    </tr>
                                </thead>
                                <tbody>
                                    {% for item in inventory %}
                                    <tr>
                                        <td>{{ item[0] }}</td>
                                        <td>{{ item[2] }}</td>
                                        <td>{{ item[3] }}</td>
                                        <td>{{ item[4] }}</td>
                                        <td>{{ item[5] }}</td>
                                    </tr>
                                    {% else %}
                                    <tr><td colspan="5">No inventory set</td></tr>
                                    {% endfor %}
                                </tbody>
                            </table>
                        </div>
                    </div>
                    
                    <h2>Add/Update Combo Quantity</h2>
                    <div class="card">
                        <div class="card-body">
                            <form method="POST">
                                <div class="mb-3">
                                    <label for="pincode" class="form-label">Pincode</label>
                                    <select class="form-control" id="pincode" name="pincode" required>
                                        <option value="411038">411038</option>
                                        <option value="411052">411052</option>
                                        <option value="411058">411058</option>
                                        <option value="411041">411041</option>
                                    </select>
                                </div>
                                <div class="mb-3">
                                    <label for="combo_id" class="form-label">Combo</label>
                                    <select class="form-control" id="combo_id" name="combo_id" required>
                                        {% for combo_id, combo in combos.items() %}
                                        <option value="{{ combo_id }}">{{ combo.name }}</option>
                                        {% endfor %}
                                    </select>
                                </div>
                                <div class="mb-3">
                                    <label for="total_boxes" class="form-label">Total Boxes</label>
                                    <input type="number" class="form-control" id="total_boxes" name="total_boxes" min="0" required>
                                </div>
                                <button type="submit" class="btn btn-primary">Update Inventory</button>
                            </form>
                        </div>
                    </div>
                </div>
            </body>
            </html>
        """, orders=orders, inventory=inventory, tomorrow=tomorrow.strftime('%Y-%m-%d'), combos=FALLBACK_COMBOS)
    except Exception as e:
        logging.error(f"Admin dashboard error: {e}")
        return "Error loading dashboard", 500

@app.route('/admin/logout')
def logout():
    session.pop('logged_in', None)
    return redirect(url_for('admin_login'))

def generate_referral_code(user_phone):
    try:
        cnx = pymysql.connect(user=usr, password=pas, host=aws_host, database=db)
        cursor = cnx.cursor()
        month_year = datetime.now().strftime('%Y-%m')
        random.seed()
        while True:
            code = ''.join(random.choices(string.ascii_uppercase + string.digits, k=5))
            cursor.execute("SELECT COUNT(*) FROM referral_codes WHERE referral_code = %s", (code,))
            if cursor.fetchone()[0] == 0:
                break
        cursor.execute(
            "INSERT INTO referral_codes (user_phone, referral_code, month_year, usage_count, is_active, created_at) "
            "VALUES (%s, %s, %s, %s, %s, %s)",
            (user_phone, code, month_year, 0, True, datetime.now())
        )
        cnx.commit()
        cnx.close()
        return code
    except Exception as e:
        logging.error(f"Failed to generate referral code for {user_phone}: {e}")
        cnx.close()
        return None

def validate_referral_code(referral_code, friend_phone):
    try:
        cnx = pymysql.connect(user=usr, password=pas, host=aws_host, database=db)
        cursor = cnx.cursor()
        month_year = datetime.now().strftime('%Y-%m')
        expiry_date = datetime.now() - timedelta(days=30)
        cursor.execute(
            "SELECT user_phone, usage_count, created_at FROM referral_codes WHERE referral_code = %s AND month_year = %s AND is_active = %s",
            (referral_code, month_year, True)
        )
        result = cursor.fetchone()
        if not result:
            cnx.close()
            return False, "Code invalid or expired"
        user_phone, usage_count, created_at = result
        if user_phone == friend_phone:
            cnx.close()
            return False, "You cannot use your own referral code"
        if created_at < expiry_date:
            cursor.execute("UPDATE referral_codes SET is_active = %s WHERE referral_code = %s", (False, referral_code))
            cnx.commit()
            cnx.close()
            return False, "Code has expired"
        if usage_count >= 5:
            cnx.close()
            return False, "Code has reached its usage limit"
        cursor.execute(
            "SELECT COUNT(*) FROM referral_rewards WHERE referral_code = %s AND friend_phone = %s",
            (referral_code, friend_phone)
        )
        if cursor.fetchone()[0] > 0:
            cnx.close()
            return False, "You have already used this code"
        cnx.close()
        return True, user_phone
    except Exception as e:
        logging.error(f"Failed to validate referral code {referral_code}: {e}")
        return False, "Error validating code"

def assign_referral_rewards(user_phone, referral_code, friend_phone, order_id):
    try:
        cnx = pymysql.connect(user=usr, password=pas, host=aws_host, database=db)
        cursor = cnx.cursor()
        cursor.execute(
            "UPDATE referral_codes SET usage_count = usage_count + 1 WHERE referral_code = %s",
            (referral_code,)
        )
        cursor.execute("SELECT usage_count FROM referral_codes WHERE referral_code = %s", (referral_code,))
        usage_count = cursor.fetchone()[0]
        if usage_count >= 5:
            cursor.execute("UPDATE referral_codes SET is_active = %s WHERE referral_code = %s", (False, referral_code))
        
        cursor.execute(
            "INSERT INTO referral_rewards (user_phone, referral_code, friend_phone, points_earned, order_id, created_at) "
            "VALUES (%s, %s, %s, %s, %s, %s)",
            (user_phone, referral_code, friend_phone, 50, order_id, datetime.now())
        )
        cursor.execute(
            "UPDATE users SET balutedaar_points = balutedaar_points + %s WHERE phone_number = %s",
            (50, user_phone)
        )
        cursor.execute(
            "SELECT COUNT(*) FROM referral_rewards WHERE referral_code = %s",
            (referral_code,)
        )
        referral_count = cursor.fetchone()[0]
        if referral_count == 5:
            cursor.execute(
                "INSERT INTO rewards (user_phone, reward_type, status, created_at) "
                "VALUES (%s, %s, %s, %s)",
                (user_phone, 'Free Veggie Box', 'Pending', datetime.now())
            )
            send_message(user_phone, 
                f"🎉 Amazing job! Your code {referral_code} has been used by 5 friends, unlocking a FREE ₹200 Veggie Box! We'll notify you when it's ready to redeem.",
                "free_box_unlocked"
            )
        cnx.commit()
        send_message(user_phone, 
            f"🎉 Great news! Your friend used your code {referral_code} and you’ve earned ₹50 Balutedaar Points! {5 - usage_count} more referrals to unlock a FREE ₹200 Veggie Box!",
            "referral_reward"
        )
        cnx.close()
    except Exception as e:
        logging.error(f"Failed to assign referral rewards for {user_phone}: {e}")
        cnx.rollback()
        cnx.close()

def send_message(rcvr, body, message):
    url = "https://apis.rmlconnect.net/wba/v1/messages?source=UI"
    if not rcvr.startswith('+'):
        rcvr = f"+91{rcvr.strip()[-10:]}"
    payload = json.dumps({
        "phone": rcvr,
        "text": body,
        "enable_acculync": True,
        "extra": message
    })
    headers = {
        'Content-Type': "application/json",
        'Authorization': authkey,
        'referer': 'https://myaccount.rmlconnect.net/'
    }
    try:
        response = requests.post(url, data=payload.encode('utf-8'), headers=headers, verify=False)
        response.raise_for_status()
        savesentlog(rcvr, response.text, response.status_code, message)
        return response.text
    except requests.RequestException as e:
        logging.error(f"Failed to send message: {e}")
        return None

def send_referral_prompt_with_button(rcvr, body, message):
    url = "https://apis.rmlconnect.net/wba/v1/messages?source=UI"
    if not rcvr.startswith('+'):
        rcvr = f"+91{rcvr.strip()[-10:]}"
    payload = json.dumps({
        "phone": rcvr,
        "enable_acculync": False,
        "extra": message,
        "media": {
            "type": "interactive_list",
            "body": body,
            "button_text": "Choose an Option",
            "button": [
                {
                    "section_title": "Referral Options",
                    "row": [
                        {
                            "id": "skip_button",
                            "title": "Skip",
                            "description": "Skip referral and browse combos"
                        }
                    ]
                }
            ]
        }
    })
    headers = {
        'Content-Type': 'application/json',
        'Authorization': authkey,
        'referer': 'https://myaccount.rmlconnect.net/'
    }
    try:
        response = requests.post(url, data=payload.encode('utf-8'), headers=headers, verify=False)
        response.raise_for_status()
        savesentlog(rcvr, response.text, response.status_code, message)
        return response.text
    except requests.RequestException as e:
        logging.error(f"Failed to send referral prompt to {rcvr}: {e}")
        return None

def interactive_template_with_2button(rcvr, body, message):
    url = "https://apis.rmlconnect.net/wba/v1/messages?source=UI"
    if not rcvr.startswith('+'):
        rcvr = f"+91{rcvr.strip()[-10:]}"
    payload = json.dumps({
        "phone": rcvr,
        "enable_acculync": False,
        "extra": message,
        "media": {
            "type": "interactive_list",
            "body": body,
            "button_text": "Choose an Option",
            "button": [
                {
                    "section_title": "Order Actions",
                    "row": [
                        {
                            "id": "1",
                            "title": "Confirm",
                            "description": "Confirm your order"
                        }
                    ]
                },
                {
                    "section_title": "Menu Options",
                    "row": [
                        {
                            "id": "2",
                            "title": "Main Menu",
                            "description": "Return to main menu"
                        }
                    ]
                }
            ]
        }
    })
    headers = {
        'Content-Type': 'application/json',
        'Authorization': authkey,
        'referer': 'https://myaccount.rmlconnect.net/'
    }
    try:
        response = requests.post(url, data=payload.encode('utf-8'), headers=headers, verify=False)
        response.raise_for_status()
        savesentlog(rcvr, response.text, response.status_code, "order_summary")
        return response.text
    except requests.RequestException as e:
        logging.error(f"Interactive 2-button failed: {e}")
        return None

def interactive_template_with_3button(frm, body, message):
    url = "https://apis.rmlconnect.net/wba/v1/messages?source=UI"
    if not frm.startswith('+'):
        frm = f"+91{frm.strip()[-10:]}"
    payload = json.dumps({
        "phone": frm,
        "enable_acculync": False,
        "extra": message,
        "media": {
            "type": "interactive_list",
            "body": body,
            "button_text": "Choose Payment",
            "button": [
                {
                    "section_title": "Cash on Delivery",
                    "row": [
                        {
                            "id": "3",
                            "title": "COD",
                            "description": "Pay cash on delivery"
                        }
                    ]
                },
                {
                    "section_title": "Online Payment",
                    "row": [
                        {
                            "id": "5",
                            "title": "Pay Now",
                            "description": "Pay via UPI or Card"
                        }
                    ]
                }
            ]
        }
    })
    headers = {
        'Content-Type': 'application/json',
        'Authorization': authkey,
      
    }
    try:
        response = requests.post(url, headers=headers, data=payload.encode('utf-8'), verify=False, timeout=10)
        response.raise_for_status()
        savesentlog(frm, response.text, response.status_code, message)
        return response.text
    except requests.RequestException as e:
        logging.error(f"Interactive 3-button failed: {e}")
        return None

def send_multi_product_message(rcvr, catalog_id, message, available_combos=None):
    url = "https://apis.rmlconnect.net/wba/v1/messages"
    if not rcvr.startswith('+'):
        rcvr = f"+91{rcvr.strip()[-10:]}"
    product_items = []
    if available_combos:
        product_items = [{"product_retailer_id": combo["combo_id"]} for combo in available_combos]
    else:
        product_items = [
            {"product_retailer_id": combo_id} for combo_id in FALLBACK_COMBOS.keys()
        ]
    payload = json.dumps({
        "phone": rcvr,
        "catalog": {
            "type": "product_list",
            "header": {
                "type": "text",
                "text": "Explore Our Fresh Veggie Combos! 🥗"
            },
            "body": {
                "text": "Select a combo for farm-fresh vegetables delivered to you! 🚜"
            },
            "action": {
                "catalog_id": catalog_id,
                "sections": [
                    {
                        "title": "Fresh Vegetable Combos",
                        "product_items": product_items
                    }
                ]
            }
        }
    })
    headers = {
        'Content-Type': 'application/json',
        'Authorization': authkey
    }
    try:
        response = requests.post(url, headers=headers, data=payload.encode('utf-8'), verify=False, timeout=10)
        response.raise_for_status()
        savesentlog(rcvr, response.text, response.status_code, message)
        return response.text
    except requests.RequestException as e:
        logging.error(f"Multi-product message failed: {e}")
        return None

def send_payment_message(frm, name, address, pincode, items, order_amount, reference_id, referral_code=None, discount_percentage=0):
    try:
        final_amount = order_amount * (1 - discount_percentage)
        payment_link_data = {
            "amount": int(final_amount * 100),
            "currency": "INR",
            "accept_partial": False,
            "description": "Balutedaar Vegetable Combo Order",
            "customer": {
                "name": name,
                "contact": frm if frm.startswith('+') else f"+91{frm[-10:]}"
            },
            "notify": {
                "sms": True,
                "whatsapp": True
            },
            "reminder_enable": True,
            "reference_id": reference_id,
            "callback_url": "http://13.202.207.66:5000/payment-callback",
            "callback_method": "get"
        }
        payment_link = razorpay_client.payment_link.create(payment_link_data)
        payment_url = payment_link.get("short_url", "")
        if not payment_url:
            logging.error(f"Failed to generate payment URL for user {frm}")
            return None

        message = (
            f"Dear *{name}*,\n\nPlease complete your payment of ₹{final_amount:.2f} for your Balutedaar order.\n\n"
            f"📦 Order Details:\n"
        )
        for item in items:
            combo_id, combo_name, price, quantity = item
            subtotal = float(price) * quantity
            message += f"🛒 {combo_name} x{quantity}: ₹{subtotal:.2f}\n"
        if referral_code:
            message += f"🎁 Referral Discount: -₹20.00\n"
        if discount_percentage > 0:
            message += f"🎁 Tiered Discount ({int(discount_percentage * 100)}%): -₹{(order_amount - final_amount):.2f}\n"
        message += f"\n💰 Total: ₹{final_amount:.2f}\n📍 Delivery Address: {address}\n\n"
        message += f"Click here to pay: {payment_url}\n\n"
        message += "Complete the payment to confirm your order!"

        url = "https://apis.rmlconnect.net/wba/v1/messages?source=UI"
        payload = json.dumps({
            "phone": frm if frm.startswith('+') else f"+91{frm[-10:]}",
            "text": message,
            "enable_acculync": True,
            "extra": "payment_link"
        })
        headers = {
            'Content-Type': "application/json",
            'Authorization': authkey,
            'referer': 'myaccount.rmlconnect.net'
        }
        response = requests.post(url, data=payload.encode('utf-8'), headers=headers, verify=False, timeout=10)
        response.raise_for_status()
        savesentlog(frm, response.text, response.status_code, "payment_link")
        return payment_url
    except razorpay.errors.BadRequestError as e:
        logging.error(f"Razorpay BadRequestError for user {frm}: {str(e)}")
        return None
    except requests.RequestException as e:
        logging.error(f"Failed to send payment message to {frm}: {str(e)}")
        return None
    except Exception as e:
        logging.error(f"Unexpected error in send_payment_message for user {frm}: {str(e)}")
        return None

def get_tiered_discount(user_phone):
    try:
        cnx = pymysql.connect(user=usr, password=pas, host=aws_host, database=db)
        cursor = cnx.cursor()
        month_year = datetime.now().strftime('%Y-%m')
        cursor.execute(
            "SELECT COUNT(*) FROM referral_rewards WHERE user_phone = %s AND referral_code IN "
            "(SELECT referral_code FROM referral_codes WHERE month_year = %s)",
            (user_phone, month_year)
        )
        referral_count = cursor.fetchone()[0]
        cnx.close()
        return TIERED_DISCOUNTS.get(referral_count, 0)
    except Exception as e:
        logging.error(f"Failed to get tiered discount for {user_phone}: {e}")
        return 0

def checkout(rcvr, name, address, pincode, payment_method, cnx, cursor, reference_id=None):
    try:
        cursor.execute("SELECT name, address, pincode, referral_code FROM users WHERE phone_number = %s", (rcvr,))
        user_data = cursor.fetchone()
        if not user_data or not all(user_data[:3]):
            return {"total": 0, "message": "Error: User data incomplete. Please provide name, address, and pincode."}
        referral_code = user_data[3]
        
        cursor.execute("SELECT combo_id, combo_name, quantity, price FROM user_cart WHERE phone_number = %s", (rcvr,))
        cart_items = cursor.fetchall()
        if not cart_items:
            return {"total": 0, "message": "Error: No valid order details found. Please select a combo."}
        
        total = 0
        order_ids = []
        tomorrow = datetime.now().date() + timedelta(days=1)
        for item in cart_items:
            combo_id, combo_name, quantity, price = item
            cursor.execute(
                "SELECT remaining FROM combo_inventory WHERE pincode = %s AND combo_id = %s AND date = %s",
                (pincode, combo_id, tomorrow)
            )
            result = cursor.fetchone()
            if not result or result[0] < quantity:
                return {"total": 0, "message": f"Error: {combo_name} is out of stock or insufficient quantity available."}
            if not update_inventory_after_order(pincode, combo_id, quantity, tomorrow):
                return {"total": 0, "message": f"Error: Failed to update inventory for {combo_name}."}
            
            subtotal = float(price) * quantity
            total += subtotal
            cursor.execute(
                "INSERT INTO orders (user_phone, customer_name, combo_id, combo_name, price, quantity, total_amount, address, pincode, payment_method, payment_status, order_status, reference_id, referral_code, delivery_date) "
                "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
                (rcvr, name, combo_id, combo_name, float(price), quantity, subtotal, address, pincode, payment_method,
                 'Pending' if payment_method != 'COD' else 'Completed', 'Placed', reference_id, referral_code, tomorrow)
            )
            order_ids.append(cursor.lastrowid)
        
        discount_percentage = get_tiered_discount(rcvr)
        if referral_code:
            is_valid, user_phone = validate_referral_code(referral_code, rcvr)
            if is_valid:
                total = max(total - 20, 0)
                for order_id in order_ids:
                    assign_referral_rewards(user_phone, referral_code, rcvr, order_id)
        total = max(total * (1 - discount_percentage), 0)
        
        cursor.execute("DELETE FROM user_cart WHERE phone_number = %s", (rcvr,))
        cursor.execute("UPDATE users SET pincode = NULL, referral_code = NULL WHERE phone_number = %s", (rcvr,))
        cnx.commit()
        new_referral_code = Mourinho = generate_referral_code(rcvr)
        return {
            "total": total,
            "message": f"Order placed! Total: ₹{total:.2f}\nYour order will be delivered to {address}, Pincode: {pincode} by tomorrow 9 AM.",
            "referral_code": new_referral_code,
            "discount_percentage": discount_percentage
        }
    except Exception as e:
        logging.error(f"Checkout failed for user {rcvr}: {e}")
        cnx.rollback()
        return {"total": 0, "message": f"Error during checkout: {str(e)}. Please try again."}

def check_pincode(pincode):
    try:
        cnx = pymysql.connect(user=usr, password=pas, host=aws_host, database=db)
        cursor = cnx.cursor()
        cursor.execute("SELECT pincode FROM pincodes WHERE pincode = %s", (pincode,))
        result = cursor.fetchone()
        cnx.close()
        return result is not None
    except Exception as e:
        logging.error(f"Pincode check failed: {e}")
        return False

def get_combo_price(combo_id):
    try:
        if combo_id in FALLBACK_COMBOS:
            return float(FALLBACK_COMBOS[combo_id].get("price", 0))
        cnx = pymysql.connect(user=usr, password=pas, host=aws_host, database=db)
        cursor = cnx.cursor()
        cursor.execute("SELECT price FROM combos WHERE combo_id = %s", (combo_id,))
        result = cursor.fetchone()
        cnx.close()
        return float(result[0]) if result else 0
    except Exception as e:
        logging.error(f"Failed to fetch price for combo_id {combo_id}: {e}")
        return float(FALLBACK_COMBOS.get(combo_id, {}).get("price", 0))

def get_combo_name(combo_id):
    combo_id = combo_id.strip()
    try:
        cnx = pymysql.connect(user=usr, password=pas, host=aws_host, database=db)
        cursor = cnx.cursor()
        cursor.execute("SELECT combo_name FROM combos WHERE combo_id = %s", (combo_id,))
        result = cursor.fetchone()
        cnx.close()
        return result[0] if result else FALLBACK_COMBOS.get(combo_id, {}).get("name", "Unknown Combo")
    except Exception as e:
        logging.error(f"Failed to fetch name for combo_id {combo_id}: {e}")
        return FALLBACK_COMBOS.get(combo_id, {}).get("name", "Unknown Combo")

def reset_user_flags(frm, cnx, cursor):
    try:
        reset_query = """UPDATE users SET 
            is_info = '0', main_menu = '0', is_main = '0', 
            is_temp = '0', sub_menu = '0', is_submenu = '0',
            selected_combo = NULL, quantity = NULL, 
            address = NULL, payment_method = NULL, order_amount = NULL,
            combo_id = NULL, pincode = NULL, is_referral = '0', referral_code = NULL
            WHERE phone_number = %s"""
        cursor.execute(reset_query, (frm,))
        cursor.execute("DELETE FROM user_cart WHERE phone_number = %s", (frm,))
        cnx.commit()
    except Exception as e:
        logging.error(f"Reset flags failed: {e}")
        cnx.rollback()

def is_valid_name(resp1):
    if resp1.lower() in greeting_word:
        return False
    if not re.match(r'^[\u0900-\u097Fa-zA-Z0-9\s_@]+$', resp1):
        return False
    return True

def is_valid_address(address):
    address = address.strip()
    if len(address) < 10:
        return False
    if not re.match(r'^[a-zA-Z0-9\s,.-/]+$', address):
        return False
    if not (re.search(r'[a-zA-Z]', address) and re.search(r'[0-9]', address)):
        return False
    address_keywords = [
        'street', 'road', 'avenue', 'lane', 'building', 'apartment', 'flat',
        'house', 'society', 'colony', 'nagar', 'plot', 'sector', 'tower'
    ]
    has_keyword = any(keyword.lower() in address.lower() for keyword in address_keywords)
    if not has_keyword and len(address) < 15:
        return False
    return True

def get_cart_summary(phone, name, address=None):
    try:
        cnx = pymysql.connect(user=usr, password=pas, host=aws_host, database=db)
        cursor = cnx.cursor()
        cursor.execute("SELECT referral_code FROM users WHERE phone_number = %s", (phone,))
        referral_code = cursor.fetchone()[0]
        cursor.execute("SELECT combo_id, combo_name, quantity, price FROM user_cart WHERE phone_number = %s", (phone,))
        cart_items = cursor.fetchall()
        total = 0
        item_count = 0
        if not cart_items:
            cnx.close()
            return "No order details found! Please select a combo to proceed.", 0, 0
        
        cart_message = f"Hi *{name}*, 👋\n\nHere’s your Order Summary:\n\n"
        for item in cart_items:
            combo_id, combo_name, quantity, price = item
            subtotal = float(price) * quantity
            total += subtotal
            item_count += 1
            cart_message += f"🛒 {combo_name} x{quantity}: ₹{subtotal:.2f}\n"
        
        discount_percentage = get_tiered_discount(phone)
        if referral_code:
            cart_message += f"🎁 Referral Discount: -₹20. festive\n"
            total = max(total - 20, 0)
        if discount_percentage > 0:
            cart_message += f"🎁 Tiered Discount ({int(discount_percentage * 100)}%): -₹{(total * discount_percentage):.2f}\n"
            total = max(total * (1 - discount_percentage), 0)
        cart_message += f"\n💰 Total Amount: ₹{total:.2f}"
        if address:
            cart_message += f"\n📍 Delivery Address: {address}"
        cnx.close()
        return cart_message, total, item_count
    except Exception as e:
        logging.error(f"Error in get_cart_summary for {phone}: {e}")
        return "Error retrieving order details. Please try again.", 0, 0

def savesentlog(frm, response, statuscode, Body):
    try:
        response_data = json.loads(response) if response else {}
        message_id = response_data.get("messages", [{}])[0].get("id", "unknown")
        now = str(datetime.now())
        add_data = "INSERT INTO tbl_logs(sender_id, timestamp1, message_id, status, messagebody) VALUES (%s, %s, %s, %s, %s)"
        val = (str(frm), str(now), message_id, str(statuscode), Body)
        cnx = pymysql.connect(user=usr, max_allowed_packet=1073741824, password=pas, host=aws_host, database=db)
        cursor = cnx.cursor()
        cursor.execute(add_data, val)
        cnx.commit()
        cnx.close()
    except Exception as e:
        logging.error(f"Failed to save log: {e}")

@app.route('/', methods=['POST', 'GET'])
def Get_Message():
    cnx = None
    cursor = None
    logging.info(f"Incoming request: {request.method} {request.url} from {request.remote_addr}")
    try:
        if request.method == 'GET':
            return 'Send a POST request with JSON data', 405
        
        if not request.is_json:
            return jsonify({"error": "Content-Type must be application/json"}), 400
        
        response = request.json
        if response is None or not isinstance(response, dict):
            return jsonify({"error": "Invalid JSON payload"}), 400
        
        if 'statuses' in response:
            return 'Success', 200
        
        if 'messages' not in response:
            return jsonify({"error": "Missing 'messages' key"}), 400
        
        frm = str(response["messages"][0]["from"])
        msg_type = response["messages"][0]["type"]
        if msg_type == "interactive":
            interactive_data = response["messages"][0]["interactive"]
            resp1 = interactive_data.get("button_reply", {}).get("id", interactive_data.get("list_reply", {}).get("id", ""))
        elif msg_type == 'text':
            resp1 = response["messages"][0]["text"]["body"]
        elif msg_type == 'order':
            resp1 = response["messages"][0]["order"].get("product_items", [{}])[0].get("product_retailer_id", "")
        else:
            resp1 = ''
            
        cnx = pymysql.connect(user=usr, password=pas, host=aws_host, database=db)
        cursor = cnx.cursor()
        init_combo_inventory()
        check_already_valid = "SELECT name, pincode, selected_combo, quantity, address, payment_method, is Tempest, order_amount, is_info, main_menu, is_main, is_temp, sub_menu, is_submenu, combo_id, is_referral, referral_code FROM users WHERE phone_number = %s"
        cursor.execute(check_already_valid, (frm,))
        result = cursor.fetchone()

        if result is None:
            camp_id = '0'
            is_valid = '0'
            name = None
            pincode = None
            selected_combo = None
            quantity = None
            address = None
            payment_method = None
            order_amount = None
            is_info = '0'
            main_menu = '0'
            is_main = '0'
            is_temp = '0'
            sub_menu = '0'
            is_submenu = '0'
            combo_id = None
            is_referral = '0'
            referral_code = None
        else:
            name, pincode, selected_combo, quantity, address, payment_method, is_valid, order_amount, is_info, main_menu, is_main, is_temp, sub_menu, is_submenu, combo_id, is_referral, referral_code = result
            camp_id = '1'

        if (msg_type == 'text' or msg_type == 'interactive' or msg_type == 'order') and len(frm) == 12:
            if resp1.lower() == 'my rewards':
                cursor.execute(
                    "SELECT referral_code, usage_count FROM referral_codes WHERE user_phone = %s AND month_year = %s",
                    (frm, datetime.now().strftime('%Y-%m'))
                )
                code_data = cursor.fetchone()
                code = code_data[0] if code_data else "None"
                usage_count = code_data[1] if code_data else 0
                cursor.execute(
                    "SELECT SUM(points_earned) FROM referral_rewards WHERE user_phone = %s AND referral_code IN "
                    "(SELECT referral_code FROM referral_codes WHERE month_year = %s)",
                    (frm, datetime.now().strftime('%Y-%m'))
                )
                points_earned = cursor.fetchon()[0] or 0
                cursor.execute("SELECT balutedaar_points FROM users WHERE phone_number = %s", (frm,))
                total_points = cursor.fetchone()[0] or 0
                discount_percentage = TIERED_DISCOUNTS.get(usage_count, 0) * 100
                status_message = f"Refer {5 - usage_count} more friends for a FREE ₹200 Veggie Box!" if usage_count < 5 else "You unlocked a FREE ₹200 Veggie Box!"
                message = (
                    f"🌟 Your Rewards Summary:\n"
                    f"📊 Current Code: {code} (Used by {usage_count}/5 friends)\n"
                    f"💰 Points This Month: ₹{points_earned}\n"
                    f"💸 Total Points: ₹{total_points}\n"
                    f"🎁 Your Next Order Discount: {discountgrp_percentage}% OFF\n"
                    f"🎁 {status_message}\n"
                    f"👉 Type ‘Redeem’ to use points!"
                )
                send行驶(frm, message, "rewards_summary")
                cnx.commit()
                cnx.close()
                return 'Success'

            if resp1.lower() in greeting_word:
                profile_name = response.get("contacts", [{}])[0].get("profile", {}).get("name", "").strip()
                if profile_name and is_valid_name(profile_name):
                    name = profile_name
                    cursor.execute(
                        "INSERT INTO users (phone_number, camp_id, is_valid, name, is_main, balutedaar_points) VALUES (%s, %s, %s, %s, %s, %s)",
                        (frm, '1', '1', name, '1', 0)
                    )
                    cnx.commit()
                    send_message(frm, wl.format(name=name), 'welcome_message')
                else:
                    cursor.execute("INSERT INTO users (phone_number, camp_id, is_valid, is_info, balutedaar_points) VALUES (%s, %s, %s, %s, %s)",
                                  (frm, '1', '1', '1', 0))
                    cnx.commit()
                    send_message(frm, wl_fallback, 'welcome_message')
            
            elif is_info == '1' and pincode is None:
                if is_valid_name(resp1):
                    name = resp1
                    cursor.execute("UPDATE users SET name = %s, is_main = %s, is_info = %s WHERE phone_number = %s",
                                  (name, '1', '0', frm))
                    cnx.commit()
                    send_message(frm, r2.format(name=name), 'pincode')
                else:
                    send_message(frm, invalid_name, "invalid_name")
                
            elif is_main == '1' and pincode is None:
                pincode = resp1
                if pincode.isdigit() and len(pincode) == 6:
                    if check_pincode(pincode):
                        tomorrow = datetime.now().date() + timedelta(days=1)
                        available_combos = check_combo_availability(pincode, tomorrow)
                        # Create a dictionary for quick lookup of available combos
                        combo_availability = {combo['combo_id']: combo['remaining'] for combo in available_combos}
                        # List all combos from FALLBACK_COMBOS with their quantities
                        combo_list = "\n".join([
                            f"🥦 {FALLBACK_COMBOS[combo_id]['name']}: {combo_availability.get(combo_id, 0)} boxes left"
                            for combo_id in FALLBACK_COMBOS
                        ])
                        message = availability_message.format(date=tomorrow.strftime('%Y-%m-%d'), combo_list=combo_list)
                        send_message(frm, message, 'combo_availability')
                        send_referral_prompt_with_button(frm, referral_prompt, 'referral_code')
                        cursor.execute("UPDATE users SET pincode = %s, is_referral = %s, is_main = %s WHERE phone_number = %s",
                                      (pincode, '1', '0', frm))
                        cnx.commit()
                    else:
                        send_message(frm, r3, 'pincode_error')
                else:
                    send_message(frm, r4, 'invalid_pincode')
                
            elif is_referral == '1':
                if msg_type == 'interactive' and resp1 == 'skip_button':
                    cursor.execute("UPDATE users SET is_referral = %s, main_menu = %s WHERE phone_number = %s", ('0', '1', frm))
                    cnx.commit()
                    tomorrow = datetime.now().date() + timedelta(days=1)
                    available_combos = check_combo_availability(pincode, tomorrow)
                    if not available_combos:
                        send_message(frm, out_of_stock, 'out_of_stock')
                    else:
                        send_multi_product_message(frm, CATALOG_ID, 'menu', available_combos)
                else:
                    is_valid, message = validate_referral_code(resp1, frm)
                    if is_valid:
                        cursor.execute("UPDATE users SET referral_code = %s, is_referral = %s, main_menu = %s WHERE phone_number = %s",
                                      (resp1, '0', '1', frm))
                        cnx.commit()
                        send_message(frm, referral_success, 'referral_success')
                        tomorrow = datetime.now().date() + timedelta(days=1)
                        available_combos = check_combo_availability(pincode, tomorrow)
                        if not available_combos:
                            send_message(frm, out_of_stock, 'out_of_stock')
                        else:
                            combo_list = "\n".join([
                                f"🥦 {FALLBACK_COMBOS[combo_id]['name']}: {combo_availability.get(combo_id, 0)} boxes left"
                                for combo_id in FALLBACK_COMBOS
                            ])
                            message = availability_message.format(date=tomorrow.strftime('%Y-%-m-%d'), combo_list=combo_list)
                            send_message(frm, message, 'combo_availability')
                            send_multi_product_message(frm, CATALOG_ID, 'menu', available_combos)
                    else:
                        send_referral_prompt_with_button(frm, invalid_referral.format(code=resp1), 'invalid_referral')
                
            elif main_menu == '1' and msg_type == 'order':
                if 'product_items' in response["messages"][0]["order"]:
                    product_items = response["messages"][0]["order"]["product_items"]
                    total_amount = 0
                    valid_selection = False
                    cursor.execute("DELETE FROM user_cart WHERE phone_number = %s", (frm,))
                    cnx.commit()
                    tomorrow = datetime.now().date() + timedelta(days=1)
                    for item in product_items:
                        combo_id = item.get("product_retailer_id", "").strip()
                        quantity = int(item.get("quantity", 1))
                        cursor.execute(
                            "SELECT remaining FROM combo_inventory WHERE pincode = %s AND combo_id = %s AND date = %s",
                            (pincode, combo_id, tomorrow)
                        )
                        result = cursor.fetchone()
                        if not result or result[0] < quantity:
                            send_message(frm, f"❌ Sorry! {get_combo_name(combo_id)} is out of stock or insufficient quantity available. Please try again tomorrow or select available combos.", "out_of_stock")
                            available_combos = check_combo_availability(pincode, tomorrow)
                            send_multi_product_message(frm, CATALOG_ID, 'menu', available_combos)
                            cnx.commit()
                            cnx.close()
                            return 'Success'
                        item_price = get_combo_price(combo_id)
                        selected_combo = get_combo_name(combo_id)
                        if selected_combo != "Unknown Combo" and item_price > 0:
                            total_amount += item_price * quantity
                            valid_selection = True
                            cursor.execute(
                                "INSERT INTO user_cart (phone_number, combo_id, combo_name, quantity, price) VALUES (%s, %s, %s, %s, %s)",
                                (frm, combo_id, selected_combo, quantity, item_price)
                            )
                            cnx.commit()
                    if valid_selection:
                        cursor.execute("UPDATE users SET is_temp = '1' WHERE phone_number = %s", (frm,))
                        cnx.commit()
                        send_message(frm, m3, "ask_address")
                    else:
                        send_message(frm, "Sorry, none of the selected products are available. Please choose another combo.", "illegal_combo")
                        tomorrow = datetime.now().date() + timedelta(days=1)
                        available_combos = check_combo_availability(pincode, tomorrow)
                        send_multi_product_message(frm, CATALOG_ID, 'menu', available_combos)
                
            elif is_temp == '1' and address is None:
                if is_valid_address(resp1):
                    address = resp1
                    cursor.execute("UPDATE users SET address = %s, is_submenu = %s WHERE phone_number = %s", (address, '1', frm))
                    cnx.commit()
                    order_summary, total, item_count = get_cart_summary(frm, name, address)
                    if item_count == 0:
                        send_message(frm, order_summary, "no_order")
                        tomorrow = datetime.now().date() + timedelta(days=1)
                        available_combos = check_combo_availability(pincode, tomorrow)
                        if not available_combos:
                            send_message(frm, out_of_stock, 'out_of_stock')
                        else:
                            combo_list = "\n".join([
                                f"🥦 {FALLBACK_COMBOS[combo_id]['name']}: {combo_availability.get(combo_id, 0)} boxes left"
                                for combo_id in FALLBACK_COMBOS
                            ])
                            message = availability_message.format(date=tomorrow.strftime('%Y-%m-%d'), combo_list=combo_list)
                            send_message(frm, message, 'combo_availability')
                            send_multi_product_message(frm, CATALOG_ID, 'menu', available_combos)
                    else:
                        order_summary += "\n\nPlease confirm your order or go back to the menu to make changes."
                        interactive_template_with_2button(frm, order_summary, "order_summary")
                else:
                    send_message(frm, invalid_address, 'invalid_address')
                
            elif is_submenu == '1' and payment_method is None:
                if resp1 == "1":
                    cursor.execute("UPDATE users SET is_submenu = '1' WHERE phone_number = %s", (frm,))
                    cnx.commit()
                    interactive_template_with_3button(frm, "💳 Please select your preferred payment method to continue:", "payment")
                elif resp1 == "2":
                    reset_user_flags(frm, cnx, cursor)
                    cursor.execute("UPDATE users SET main_menu = '1' WHERE phone_number = %s", (frm,))
                    cnx.commit()
                    tomorrow = datetime.now().date() + timedelta(days=1)
                    available_combos = check_combo_availability(pincode, tomorrow)
                    if not available_combos:
                        send_message(frm, out_of_stock, 'out_of_stock')
                    else:
                        combo_list = "\n".join([
                            f"🥦 {FALLBACK_COMBOS[combo_id]['name']}: {combo_availability.get(combo_id, 0)} boxes left"
                            for combo_id in FALLBACK_COMBOS
                        ])
                        message = availability_message.format(date=tomorrow.strftime('%Y-%m-%d'), combo_list=combo_list)
                        send_message(frm, message, 'combo_availability')
                        send_multi_product_message(frm, CATALOG_ID, "menu", available_combos)
                else:
                    payment_method = {"3": "COD", "5": "Pay Now"}.get(resp1)
                    if payment_method:
                        cursor.execute("UPDATE users SET payment_method = %s WHERE phone_number = %s", (payment_method, frm))
                        cnx.commit()
                        cursor.execute("SELECT combo_id, combo_name, quantity, price FROM user_cart WHERE phone_number = %s", (frm,))
                        cart_items = cursor.fetchall()
                        if not cart_items:
                            send_message(frm, "No order details found! Please select a combo to proceed.", "no_order")
                            cursor.execute("UPDATE users SET payment_method = NULL WHERE phone_number = %s", (frm,))
                            cnx.commit()
                            cnx.close()
                            return 'Success'
                            
                        total_amount = sum(float(item[3]) * item[2] for item in cart_items)
                        items = [(item[0], item[1], float(item[3]), item[2]) for item in cart_items]
                        discount_percentage = get_tiered_discount(frm)
                        
                        if payment_method == "COD":
                            reference_id = f"q9{uuid.uuid4().hex[:8]}"
                            checkout_result = checkout(frm, name, address, pincode, payment_method, cnx, cursor, reference_id)
                            if checkout_result["total"] == 0:
                                send_message(frm, checkout_result["message"], "checkout_error")
                                cnx.close()
                                return 'Success'
                            else:
                                order_message = (
                                    f"{checkout_result['message']}\n\n"
                                    f"📦 Your order has been placed successfully!\n"
                                    f"💳 Payment Method: {payment_method}\n"
                                    f"🆔 Reference ID: {reference_id}\n"
                                    f"🎁 Your new referral code: {checkout_result['referral_code']}\n"
                                    f"Thank you for choosing Balutedaar! 🌱"
                                )
                                send_message(frm, order_message, "order_confirmation")
                                cnx.commit()
                                cnx.close()
                                return 'Success'
                            
                        elif payment_method == "Pay Now":
                            reference_id = f"q9{uuid.uuid4().hex[:8]}"
                            payment_url = send_payment_message(
                                frm, name, address, pincode, items, total_amount, reference_id,
                                referral_code=referral_code, discount_percentgrp=discount_percentage
                            )
                            if payment_url:
                                cursor.execute(
                                    "UPDATE users SET order_amount = %s, reference_id = %s WHERE phone_number = %s",
                                    (total_amount, reference_id, frm)
                                )
                                cnx.commit()
                                cnx.close()
                                return 'Success'
                            else:
                                send_message(frm, "Error generating payment link. Please try again or choose COD.", "payment_error")
                                cursor.execute("UPDATE users SET payment_method = NULL WHERE phone_number = %s", (frm,))
                                cnx.commit()
                                cnx.close()
                                return 'Success'
                        else:
                            interactive_template_with_3button(frm, "💳 Please select a valid payment method:", "payment")
                
            cnx.commit()
            cnx.close()
            return 'Success'
        
        cnx.close()
        return 'Success'
    except Exception as e:
        logging.error(f"Error in Get_Message: {e}")
        if cnx:
            cnx.rollback()
            cnx.close()
        return jsonify({"error": str(e)}), 500

@app.route('/payment-callback', methods=['GET'])
def payment_callback():
    try:
        payment_id = request.args.get('razorpay_payment_id')
        payment_link_id = request.args.get('razorpay_payment_link_id')
        payment_status = request.args.get('razorpay_payment_link_status')
        reference_id = request.args.get('razorpay_payment_link_reference_id')
        signature = request.args.get('razorpay_signature')

        logging.info(f"Payment callback received: payment_id={payment_id}, status={payment_status}, reference_id={reference_id}")

        cnx = pymysql.connect(user=usr, password=pas, host=aws_host, database=db)
        cursor = cnx.cursor()

        cursor.execute(
            "SELECT user_phone, customer_name, address, pincode, payment_method, order_amount FROM users WHERE reference_id = %s",
            (reference_id,)
        )
        user_data = cursor.fetchone()

        if not user_data:
            logging.error(f"No user found for reference_id: {reference_id}")
            cnx.close()
            return jsonify({"error": "Invalid reference ID"}), 400

        user_phone, name, address, pincode, payment_method, order_amount = user_data

        if payment_status == 'paid':
            cursor.execute(
                "UPDATE orders SET payment_status = %s, razorpay_payment_id = %s WHERE reference_id = %s",
                ('Completed', payment_id, reference_id)
            )
            checkout_result = checkout(user_phone, name, address, pincode, payment_method, cnx, cursor, reference_id)
            if checkout_result["total"] == 0:
                send_message(user_phone, checkout_result["message"], "checkout_error")
                cnx.rollback()
                cnx.close()
                return jsonify({"error": "Checkout failed"}), 500
            else:
                order_message = (
                    f"{checkout_result['message']}\n\n"
                    f"📦 Your order has been placed successfully!\n"
                    f"💳 Payment Method: Online Payment\n"
                    f"🆔 Payment ID: {payment_id}\n"
                    f"🆔 Reference ID: {reference_id}\n"
                    f"🎁 Your new referral code: {checkout_result['referral_code']}\n"
                    f"Thank you for choosing Balutedaar! 🌱"
                )
                send_message(user_phone, order_message, "order_confirmation")
                cnx.commit()
        else:
            cursor.execute(
                "UPDATE orders SET payment_status = %s WHERE reference_id = %s",
                ('Failed', reference_id)
            )
            send_message(user_phone, "Payment failed. Please try again or choose COD.", "payment_failed")
            cnx.commit()

        cnx.close()
        return jsonify({"status": "success"}), 200
    except Exception as e:
        logging.error(f"Payment callback error: {e}")
        if cnx:
            cnx.rollback()
            cnx.close()
        return jsonify({"error": str(e)}), 500
