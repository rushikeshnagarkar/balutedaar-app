from flask import Flask, jsonify, request, render_template, session, redirect, url_for
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

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    filename='app.log',
    format='%(asctime)s - %(levelname)s - %(message)s'
)

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

app = Flask(__name__)
app.secret_key = os.getenv("FLASK_SECRET_KEY", os.urandom(24))
load_dotenv()

# Validate environment variables
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
ADMIN_USERNAME = os.getenv("ADMIN_USERNAME", "admin")
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "admin123")

# Greeting words
greeting_word = ['Hi', 'hi', 'HI', 'Hii', 'hii', 'HII', 'Hello', 'hello', 'HELLO', 'Welcome', 'welcome', 'WELCOME', 'Hey', 'hey', 'HEY']

# Messages
m1 = '''✅ Combo boxes available for {date}:\n{combo_list}\nWould you like to book?'''
m3 = '''🚚 Just one more step!

Kindly share your complete delivery address in English (e.g., Flat 101, Baner Road, Pune) so we can deliver your veggies without any delay.'''
invalid_address = '''😕 Oops! That doesn’t look like a valid address. Please enter a complete address with house/flat number, street name, and area (e.g., Flat 101, Baner Road, Pune). Use letters, numbers, spaces, commas, periods, hyphens, or slashes only.'''
invalid_name = '''⚠️ Please enter a valid name using alphabetic characters, numbers, or spaces only.'''
out_of_stock = '''❌ Sorry! {combo_name} is out of stock or insufficient quantity available. Please try again tomorrow or select available combos.'''
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

CATALOG_ID = os.getenv("CATALOG_ID", "1221166119417288")
SUPPORTED_PINCODES = os.getenv("SUPPORTED_PINCODES", "411038,411052,411058,411041").split(",")

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
    1: 0.10,  # 10% off for 1 successful referral
    2: 0.20,  # 20% off for 2 successful referrals
    3: 0.30,  # 30% off for 3 successful referrals
    4: 0.40,  # 40% off for 4 successful referrals
    5: 0.50   # 50% off for 5 successful referrals
}

def get_combo_availability(date):
    try:
        cnx = pymysql.connect(user=usr, password=pas, host=aws_host, database=db)
        cursor = cnx.cursor()
        cursor.execute(
            "SELECT combo_id, combo_name, total_boxes, remaining FROM combo_inventory WHERE date = %s",
            (date,)
        )
        inventory = cursor.fetchall()
        cnx.close()
        combo_list = []
        for combo_id, combo_name, total_boxes, remaining in inventory:
            combo_list.append(f"🥦 {combo_name}: {remaining}/{total_boxes} boxes left")
        return "\n".join(combo_list) if combo_list else "No combos available."
    except Exception as e:
        logging.error(f"Failed to fetch combo availability: {e}")
        combo_list = []
        for combo_id, combo_data in FALLBACK_COMBOS.items():
            combo_list.append(f"🥦 {combo_data['name']}: 0 boxes left")
        return "\n".join(combo_list)

def check_inventory(combo_id, quantity, date):
    try:
        cnx = pymysql.connect(user=usr, password=pas, host=aws_host, database=db)
        cursor = cnx.cursor()
        cursor.execute(
            "SELECT remaining, combo_name FROM combo_inventory WHERE date = %s AND combo_id = %s",
            (date, combo_id)
        )
        result = cursor.fetchone()
        cnx.close()
        if result and result[0] >= quantity:
            return True, result[1]
        return False, result[1] if result else get_combo_name(combo_id)
    except Exception as e:
        logging.error(f"Failed to check inventory for combo_id {combo_id}: {e}")
        return False, get_combo_name(combo_id)

def update_inventory(combo_id, quantity, date):
    try:
        cnx = pymysql.connect(user=usr, password=pas, host=aws_host, database=db)
        cursor = cnx.cursor()
        cursor.execute(
            "UPDATE combo_inventory SET booked = booked + %s, remaining = remaining - %s WHERE date = %s AND combo_id = %s",
            (quantity, quantity, date, combo_id)
        )
        cnx.commit()
        cnx.close()
    except Exception as e:
        logging.error(f"Failed to update inventory for combo_id {combo_id}: {e}")
        cnx.rollback()
        cnx.close()

def generate_referral_code(user_phone):
    try:
        cnx = pymysql.connect(user=usr, password=pas, host=aws_host, database=db)
        cursor = cnx.cursor()
        month_year = datetime.now().strftime('%Y-%m')
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
        'referer': 'myaccount.rmlconnect.net'
    }
    try:
        response = requests.post(url, headers=headers, data=payload.encode('utf-8'), verify=False, timeout=10)
        response.raise_for_status()
        savesentlog(frm, response.text, response.status_code, message)
        return response.text
    except requests.RequestException as e:
        logging.error(f"Interactive 3-button failed: {e}")
        return None

def send_multi_product_message(rcvr, catalog_id, message):
    url = "https://apis.rmlconnect.net/wba/v1/messages"
    if not rcvr.startswith('+'):
        rcvr = f"+91{rcvr.strip()[-10:]}"
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
                        "product_items": [
                            {"product_retailer_id": "D-9011"},
                            {"product_retailer_id": "A-9011"},
                            {"product_retailer_id": "E-9011"},
                            {"product_retailer_id": "B-9011"},
                            {"product_retailer_id": "C-9011"},
                            {"product_retailer_id": "xzwqdyrcl9"},
                            {"product_retailer_id": "7e8sbb1xg8"},
                            {"product_retailer_id": "dm4ngkc9xr"}
                        ]
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
            "callback_url": os.getenv("PAYMENT_CALLBACK_URL", "http://13.202.207.66:5000/payment-callback"),
            "callback_method": "get"
        }
        payment_link = razorpay_client.payment_link.create(payment_link_data)
        payment_url = payment_link.get("short_url", "")
        if not payment_url:
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
    except Exception as e:
        logging.error(f"Failed to send payment message to {frm}: {str(e)}")
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
        delivery_date = (datetime.now() + timedelta(days=1)).date()
        for item in cart_items:
            combo_id, combo_name, quantity, price = item
            is_available, _ = check_inventory(combo_id, quantity, delivery_date)
            if not is_available:
                return {"total": 0, "message": f"Error: {combo_name} is out of stock or insufficient quantity."}
            subtotal = float(price) * quantity
            total += subtotal
            cursor.execute(
                "INSERT INTO orders (user_phone, customer_name, combo_id, combo_name, price, quantity, total_amount, address, pincode, payment_method, payment_status, order_status, reference_id, referral_code, delivery_date) "
                "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
                (rcvr, name, combo_id, combo_name, float(price), quantity, subtotal, address, pincode, payment_method,
                 'Pending' if payment_method != 'COD' else 'Completed', 'Placed', reference_id, referral_code, delivery_date)
            )
            update_inventory(combo_id, quantity, delivery_date)
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
        new_referral_code = generate_referral_code(rcvr)
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
    return pincode in SUPPORTED_PINCODES

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
            cart_message += f"🎁 Referral Discount: -₹20.00\n"
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

# Admin Dashboard Routes
@app.route('/admin/login', methods=['GET', 'POST'])
def admin_login():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        if username == ADMIN_USERNAME and password == ADMIN_PASSWORD:
            session['logged_in'] = True
            return redirect(url_for('admin_dashboard'))
        return render_template('admin_login.html', error="Invalid credentials. Try again.")
    return render_template('admin_login.html')

@app.route('/admin', methods=['GET'])
def admin_dashboard():
    if not session.get('logged_in'):
        return redirect(url_for('admin_login'))
    try:
        cnx = pymysql.connect(user=usr, password=pas, host=aws_host, database=db)
        cursor = cnx.cursor()
        tomorrow = (datetime.now() + timedelta(days=1)).date()
        cursor.execute(
            "SELECT order_id, user_phone, customer_name, combo_name, quantity, total_amount, address, pincode, order_status, payment_status "
            "FROM orders WHERE delivery_date = %s",
            (tomorrow,)
        )
        orders = cursor.fetchall()
        cursor.execute(
            "SELECT combo_id, combo_name, total_boxes, booked, remaining "
            "FROM combo_inventory WHERE date = %s",
            (tomorrow,)
        )
        inventory = cursor.fetchall()
        cursor.execute("SELECT combo_id, combo_name FROM combos")
        combos = cursor.fetchall()
        cnx.close()
        return render_template('admin_dashboard.html', orders=orders, inventory=inventory, combos=combos)
    except Exception as e:
        logging.error(f"Admin dashboard error: {e}")
        return render_template('admin_dashboard.html', error=str(e))

@app.route('/admin/update_inventory', methods=['POST'])
def update_inventory_route():
    if not session.get('logged_in'):
        return redirect(url_for('admin_login'))
    try:
        cnx = pymysql.connect(user=usr, password=pas, host=aws_host, database=db)
        cursor = cnx.cursor()
        tomorrow = (datetime.now() + timedelta(days=1)).date()
        for combo_id, combo_data in FALLBACK_COMBOS.items():
            total_boxes = int(request.form.get(f'quantity_{combo_id}', 0))
            combo_name = combo_data['name']
            cursor.execute(
                "INSERT INTO combo_inventory (date, combo_id, combo_name, total_boxes, booked, remaining) "
                "VALUES (%s, %s, %s, %s, %s, %s) ON DUPLICATE KEY UPDATE total_boxes = %s, remaining = remaining + (%s - total_boxes)",
                (tomorrow, combo_id, combo_name, total_boxes, 0, total_boxes, total_boxes, total_boxes)
            )
        cnx.commit()
        cnx.close()
        return redirect(url_for('admin_dashboard'))
    except Exception as e:
        logging.error(f"Update inventory error: {e}")
        return render_template('admin_dashboard.html', error=str(e))

@app.route('/admin/logout', methods=['GET'])
def admin_logout():
    session.pop('logged_in', None)
    return redirect(url_for('admin_login'))

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
        check_already_valid = "SELECT name, pincode, selected_combo, quantity, address, payment_method, is_valid, order_amount, is_info, main_menu, is_main, is_temp, sub_menu, is_submenu, combo_id, is_referral, referral_code FROM users WHERE phone_number = %s"
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
                points_earned = cursor.fetchone()[0] or 0
                cursor.execute("SELECT balutedaar_points FROM users WHERE phone_number = %s", (frm,))
                total_points = cursor.fetchone()[0] or 0
                discount_percentage = TIERED_DISCOUNTS.get(usage_count, 0) * 100
                status_message = f"Refer {5 - usage_count} more friends for a FREE ₹200 Veggie Box!" if usage_count < 5 else "You unlocked a FREE ₹200 Veggie Box!"
                message = (
                    f"🌟 Your Rewards Summary:\n"
                    f"📊 Current Code: {code} (Used by {usage_count}/5 friends)\n"
                    f"💰 Points This Month: ₹{points_earned}\n"
                    f"💸 Total Points: ₹{total_points}\n"
                    f"🎁 Your Next Order Discount: {discount_percentage}% OFF\n"
                    f"🎁 {status_message}\n"
                    f"👉 Type ‘Redeem’ to use points!"
                )
                send_message(frm, message, "rewards_summary")
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
                    send_message(frm, wl.format(name=name), 'pincode')
                else:
                    cursor.execute("INSERT INTO users (phone_number, camp_id, is_valid, is_info, balutedaar_points) VALUES (%s, %s, %s, %s, %s)",
                                  (frm, '1', '1', '1', 0))
                    cnx.commit()
                    send_message(frm, wl_fallback, 'welcome_message')
            
            if camp_id == '1':
                if is_info == '1' and pincode is None:
                    if is_valid_name(resp1):
                        name = resp1
                        cursor.execute("UPDATE users SET name = %s, is_main = %s, is_info = %s WHERE phone_number = %s",
                                      (name, '1', '0', frm))
                        cnx.commit()
                        send_message(frm, r2.format(name=name), 'pincode')
                    else:
                        send_message(frm, invalid_name, "invalid_name")
                
                if is_main == '1' and pincode is None:
                    pincode = resp1
                    if pincode.isdigit() and len(pincode) == 6 and check_pincode(pincode):
                        cursor.execute("UPDATE users SET pincode = %s, is_referral = %s, is_main = %s WHERE phone_number = %s",
                                      (pincode, '1', '0', frm))
                        cnx.commit()
                        combo_list = get_combo_availability((datetime.now() + timedelta(days=1)).date())
                        send_message(frm, m1.format(date=(datetime.now() + timedelta(days=1)).strftime('%Y-%m-%d'), combo_list=combo_list), 'combo_availability')
                        send_referral_prompt_with_button(frm, referral_prompt, 'referral_code')
                    else:
                        send_message(frm, r3 if pincode.isdigit() and len(pincode) == 6 else r4, 'pincode_error')
                
                if is_referral == '1':
                    if msg_type == 'interactive' and resp1 == 'skip_button':
                        cursor.execute("UPDATE users SET is_referral = %s, main_menu = %s WHERE phone_number = %s", ('0', '1', frm))
                        cnx.commit()
                        send_multi_product_message(frm, CATALOG_ID, 'menu')
                    else:
                        is_valid, message = validate_referral_code(resp1, frm)
                        if is_valid:
                            cursor.execute("UPDATE users SET referral_code = %s, is_referral = %s, main_menu = %s WHERE phone_number = %s",
                                          (resp1, '0', '1', frm))
                            cnx.commit()
                            send_message(frm, referral_success, 'referral_success')
                            send_multi_product_message(frm, CATALOG_ID, 'menu')
                        else:
                            send_referral_prompt_with_button(frm, invalid_referral.format(code=resp1), 'invalid_referral')
                
                if main_menu == '1' and msg_type == 'order':
                    if 'product_items' in response["messages"][0]["order"]:
                        product_items = response["messages"][0]["order"]["product_items"]
                        total_amount = 0
                        valid_selection = False
                        cursor.execute("DELETE FROM user_cart WHERE phone_number = %s", (frm,))
                        cnx.commit()
                        delivery_date = (datetime.now() + timedelta(days=1)).date()
                        for item in product_items:
                            combo_id = item.get("product_retailer_id", "").strip()
                            quantity = int(item.get("quantity", 1))
                            is_available, combo_name = check_inventory(combo_id, quantity, delivery_date)
                            if not is_available:
                                send_message(frm, out_of_stock.format(combo_name=combo_name), "out_of_stock")
                                send_multi_product_message(frm, CATALOG_ID, 'menu')
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
                            send_multi_product_message(frm, CATALOG_ID, 'menu')
                            send_message(frm, "Sorry, none of the selected products are available. Please choose another combo.", "illegal_combo")
                
                if is_temp == '1' and address is None:
                    if is_valid_address(resp1):
                        address = resp1
                        cursor.execute("UPDATE users SET address = %s, is_submenu = %s WHERE phone_number = %s", (address, '1', frm))
                        cnx.commit()
                        order_summary, total, item_count = get_cart_summary(frm, name, address)
                        if item_count == 0:
                            send_message(frm, order_summary, "no_order")
                            send_multi_product_message(frm, CATALOG_ID, 'menu')
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
                        send_multi_product_message(frm, CATALOG_ID, "menu")
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
                                    send_message(frm, checkout_result["message"], "invalid_order")
                                    cursor.execute("UPDATE users SET payment_method = NULL WHERE phone_number = %s", (frm,))
                                    cnx.commit()
                                    cnx.close()
                                    return 'Success'
                                
                                cursor.execute(
                                    "SELECT combo_id, combo_name, price, quantity, total_amount, address, referral_code "
                                    "FROM orders WHERE user_phone = %s AND reference_id = %s AND payment_method = 'COD' AND order_status = 'Placed'",
                                    (frm, reference_id)
                                )
                                items = cursor.fetchall()
                                if not items:
                                    send_message(frm, "Error: No order found. Please try again.", "no_order")
                                    cursor.execute("UPDATE users SET payment_method = NULL WHERE phone_number = %s", (frm,))
                                    cnx.commit()
                                    cnx.close()
                                    return 'Success'
                                
                                total = checkout_result["total"]
                                new_referral_code = checkout_result["referral_code"]
                                discount_percentage = checkout_result["discount_percentage"]
                                confirmation = f"Dear *{name}*,\n\nThank you for your order with Balutedaar! Below is your order confirmation:\n\n📦 *Order Details*:\n"
                                for item in items:
                                    combo_id, combo_name, price, quantity, item_total, address, order_referral_code = item
                                    subtotal = float(price) * quantity
                                    confirmation += f"🛒 {combo_name} x{quantity}: ₹{subtotal:.2f}\n"
                                if order_referral_code:
                                    confirmation += f"🎁 Referral Discount: -₹20.00\n"
                                if discount_percentage > 0:
                                    confirmation += f"🎁 Tiered Discount ({int(discount_percentage * 100)}%): -₹{(item_total - total):.2f}\n"
                                confirmation += f"\n💰 Total Amount: ₹{total:.2f}\n📍 Delivery Address: {address}\n"
                                confirmation += f"🚚 Delivery Schedule: Your order will be delivered to your doorstep by tomorrow 9 AM.\n\n"
                                confirmation += f"🎉 Here’s your unique referral code: {new_referral_code}\nRefer your friends to earn ₹50 per order they place!\n\n"
                                confirmation += f"We appreciate your support for fresh, sustainable produce. If you’ve any questions, reach out!\n\nBest regards,\nThe Balutedaar Team"
                                send_message(frm, confirmation, "order_confirmation")
                                gamified_prompt = (
                                    f"🎯 Mission Veggie-Star: UNLOCK REWARDS!\n"
                                    f"Share your code *{new_referral_code}* with up to 5 friends this month and get:\n"
                                    f"🥕 ₹50 Balutedaar Points per friend\n"
                                    f"🥬 Friends get 10% OFF\n"
                                    f"🎁 Refer 5 friends = FREE ₹200 Veggie Box!\n"
                                    f"📤 Tap to Share: Tap here to get the message: https://wa.me/+917477751777?text=Use+my+code+%22{new_referral_code}%22+to+get+fresh+veggies!%0Awith+Bot+number:+917477751777%0ASend+%22Hi%22+to+Start."
                                )
                                send_message(frm, gamified_prompt, "gamified_prompt")
                                cursor.execute("UPDATE users SET is_submenu = '0', payment_method = NULL WHERE phone_number = %s", (frm,))
                                cnx.commit()
                                cnx.close()
                                return 'Success'
                            elif payment_method == "Pay Now":
                                reference_id = f"q9{uuid.uuid4().hex[:8]}"
                                checkout_result = checkout(frm, name, address, pincode, payment_method, cnx, cursor, reference_id)
                                if checkout_result["total"] == 0:
                                    send_message(frm, checkout_result["message"], "invalid_order")
                                    cursor.execute("UPDATE users SET payment_method = NULL WHERE phone_number = %s", (frm,))
                                    cnx.commit()
                                    cnx.close()
                                    return 'Success'
                                
                                payment_url = send_payment_message(frm, name, address, pincode, items, total_amount, reference_id, referral_code, discount_percentage)
                                if not payment_url:
                                    send_message(frm, "Error generating payment link. Please try again.", "payment_error")
                                    cursor.execute("UPDATE users SET payment_method = NULL WHERE phone_number = %s", (frm,))
                                    cnx.commit()
                                    cnx.close()
                                    return 'Success'
                                
                                cursor.execute("UPDATE users SET is_submenu = '0' WHERE phone_number = %s", (frm,))
                                cnx.commit()
                                cnx.close()
                                return 'Success'

        cnx.commit()
        cnx.close()
        return 'Success', 200
    except Exception as e:
        logging.error(f"Main handler error: {str(e)}")
        if cnx:
            cnx.rollback()
            cnx.close()
        return jsonify({"error": str(e)}), 400

@app.route('/payment-callback', methods=['GET'])
def payment_callback():
    try:
        payment_id = request.args.get('razorpay_payment_id')
        payment_link_id = request.args.get('razorpay_payment_link_id')
        payment_link_reference_id = request.args.get('razorpay_payment_link_reference_id')
        payment_link_status = request.args.get('razorpay_payment_link_status')
        signature = request.args.get('razorpay_signature')

        if payment_link_status == 'paid':
            cnx = pymysql.connect(user=usr, password=pas, host=aws_host, database=db)
            cursor = cnx.cursor()
            cursor.execute(
                "UPDATE orders SET payment_status = 'Completed', order_status = 'Confirmed' WHERE reference_id = %s",
                (payment_link_reference_id,)
            )
            cursor.execute(
                "SELECT user_phone, customer_name, address, pincode, combo_id, combo_name, price, quantity, total_amount, referral_code "
                "FROM orders WHERE reference_id = %s",
                (payment_link_reference_id,)
            )
            items = cursor.fetchall()
            
            if items:
                frm = items[0][0]
                cursor.execute("UPDATE users SET pincode = NULL WHERE phone_number = %s", (frm,))
                new_referral_code = generate_referral_code(frm)
                frm, name, address, pincode = items[0][0:4]
                total = 0
                confirmation = f"Dear *{name}*,\n\nThank you for your payment! Your order has been confirmed:\n\n📦 *Order Details*:\n"
                referral_code = items[0][9]
                discount_percentage = get_tiered_discount(frm)
                for item in items:
                    combo_name, price, quantity = item[5:8]
                    subtotal = float(price) * quantity
                    total += subtotal
                    confirmation += f"🛒 {combo_name} x{quantity}: ₹{subtotal:.2f}\n"
                if referral_code:
                    confirmation += f"🎁 Referral Discount: -₹20.00\n"
                    total = max(total - 20, 0)
                if discount_percentage > 0:
                    discount_amount = total * discount_percentage
                    confirmation += f"🎁 Tiered Discount ({int(discount_percentage * 100)}%): -₹{discount_amount:.2f}\n"
                    total = max(total * (1 - discount_percentage), 0)
                confirmation += f"\n💰 Total Amount: ₹{total:.2f}\n📍 Delivery Address: {address}\n"
                confirmation += f"🚚 Your order will be delivered by tomorrow 9 AM.\n\n"
                confirmation += f"🎉 Here’s your unique referral code: {new_referral_code}\nRefer your friends to earn ₹50 per order they place!\n\n"
                confirmation += "We appreciate your support for fresh, sustainable produce!\nBest regards,\nThe Balutedaar Team"
                send_message(frm, confirmation, "payment_confirmation")
                gamified_prompt = (
                    f"🎯 Mission Veggie-Star: UNLOCK REWARDS!\n"
                    f"Share your code *{new_referral_code}* with up to 5 friends this month and get:\n"
                    f"🥕 ₹50 Balutedaar Points per friend\n"
                    f"🥬 Friends get 10% OFF\n"
                    f"🎁 Refer 5 friends = FREE ₹200 Veggie Box!\n"
                    f"📤 Tap to Share: Tap here to get the message: https://wa.me/+917477751777?text=Use+my+code+%22{new_referral_code}%22+to+get+fresh+veggies!%0Awith+Bot+number:+917477751777%0ASend+%22Hi%22+to+Start."
                )
                send_message(frm, gamified_prompt, "gamified_prompt")
            
            cnx.commit()
            cnx.close()
            return "Payment successful! Your order is confirmed." if items else ("Error: Order not found", 400)
        else:
            cnx = pymysql.connect(user=usr, password=pas, host=aws_host, database=db)
            cursor = cnx.cursor()
            cursor.execute(
                "SELECT user_phone, customer_name FROM orders WHERE reference_id = %s",
                (payment_link_reference_id,)
            )
            result = cursor.fetchone()
            cnx.close()
            if result:
                frm, name = result
                send_message(frm, f"Dear *{name}*, your payment was not completed. Please try again.", "payment_failed")
            return "Payment failed or cancelled. Please try again."
    except Exception as e:
        logging.error(f"Payment callback error: {str(e)}")
        if 'cnx' in locals():
            cnx.rollback()
            cnx.close()
        return jsonify({"error": str(e)}), 500

if __name__ == '__main__':
    app.debug = True
    app.run(host='0.0.0.0', port=5000)
