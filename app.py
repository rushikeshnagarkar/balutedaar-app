
from flask import Flask, jsonify, request
import requests
import json
from datetime import datetime
import pymysql
import urllib3
import re
import os
import razorpay
import uuidfrom dotenv import load_dotenv
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

app = Flask(__name__)
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


# Greeting words
greeting_word = ['Hi', 'hi', 'HI', 'Hii', 'hii', 'HII', 'Hello', 'hello', 'HELLO', 'Welcome', 'welcome', 'WELCOME', 'Hey', 'hey', 'HEY']

# Messages
m1 = '''Please select a combo from the list below:'''
m3 = '''🚚 Just one more step!

Kindly share your complete delivery address so we can deliver your veggies without any delay.'''
invalid_address = '''😕 Oops! That doesn’t look like a valid address. Please enter a complete address with house/flat number, street name, and area (e.g., Flat 101, Baner Road, Pune). Use letters, numbers, spaces, commas, periods, hyphens, or slashes only.'''
invalid_name = '''⚠️ Please enter a valid name using alphabetic characters only.'''
wl = '''Ram Ram Mandali 🙏

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
Please enter a *6-digit pincode* (e.g., 411038). 📍'''

CATALOG_ID = "1221166119417288"

FALLBACK_COMBOS = {
    "D-9011": {"name": "Amaranth Combo", "price": 1.00}, 
    "A-9011": {"name": "Methi Combo", "price": 1.00},
    "E-9011": {"name": "Dill Combo", "price": 1.00},
    "B-9011": {"name": "Kanda Paat Combo", "price": 1.00},
    "C-9011": {"name": "Palak Combo", "price": 1.00},
    "xzwqdyrcl9": {"name": "Spinach - पालक", "price": 1.00},
    "7e8sbb1xg8": {"name": "Fenugreek - मेथी", "price": 1.00},
    "dm4ngkc9xr": {"name": "Amaranth - लाल माठ", "price": 1.00}
}

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
    print(f"send_message headers: {headers}")
    print(f"send_message payload: {payload}")
    try:
        response = requests.post(url, data=payload.encode('utf-8'), headers=headers, verify=False)
        response.raise_for_status()
        print(f"send_message response: {response.text}")
        savesentlog(rcvr, response.text, response.status_code, message)
        return response.text
    except requests.RequestException as e:
        print(f"Failed to send message: {e}, Response: {response.text if 'response' in locals() else 'No response'}")
        return None

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
        print(f"Failed to save log: {e}")

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
        print(f"2-button response: {response.text}")
        savesentlog(rcvr, response.text, response.status_code, "order_summary")
        return response.text
    except requests.RequestException as e:
        print(f"Interactive 2-button failed: {e}, Response: {response.text if 'response' in locals() else 'No response'}")
        return None

def interactive_template_with_3button(frm, body, message):
    if not authkey:
        print(f"Skipping interactive_template_with_3button to {frm}: No authkey provided")
        return None
    url = "https://apis.rmlconnect.net/wba/v1/messages?source=UI"
    if not frm.startswith('+'):
        frm = f"+91{frm.strip()[-10:]}"
    if message == "payment":
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
        print(f"3-button payload: {payload}")
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
        print(f"Interactive 3-button failed: {e}, Response: {response.text if 'response' in locals() else 'No response'}")
        return None

def send_multi_product_message(rcvr, CATALOG_ID, message):
    url = "https://apis.rmlconnect.net/wba/v1/messages"
    if not rcvr.startswith('+'):
        rcvr = f"+91{rcvr.strip()[-10:]}"
    print(f"Sending multi-product message to: {rcvr}, CATALOG_ID: {CATALOG_ID}")
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
                "catalog_id": CATALOG_ID,
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
    print(f"Payload: {payload}")
    print(f"Headers: {headers}")
    try:
        response = requests.post(url, headers=headers, data=payload.encode('utf-8'), verify=False, timeout=10)
        response.raise_for_status()
        savesentlog(rcvr, response.text, response.status_code, message)
        return response.text
    except requests.RequestException as e:
        print(f"Multi-product message failed: {e}")
        return None

def send_payment_message(frm, name, address, pincode, items, order_amount, reference_id):
    try:
        print(f"Creating Razorpay payment link for user {frm}, amount: {order_amount}, reference_id: {reference_id}")
        # Create Razorpay payment link
        payment_link_data = {
            "amount": int(order_amount * 100),  # Convert to paise
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
            "callback_url": "https://f8ef-103-183-90-228.ngrok-free.app/payment-callback",
            "callback_method": "get"
        }
        print(f"Razorpay payment link data: {payment_link_data}")
        payment_link = razorpay_client.payment_link.create(payment_link_data)
        payment_url = payment_link.get("short_url", "")
        print(f"Razorpay payment link created: {payment_url}")

        # Prepare WhatsApp message
        message = (
            f"Dear *{name}*,\n\nPlease complete your payment of ₹{order_amount:.2f} for your Balutedaar order.\n\n"
            f"📦 Order Details:\n"
        )
        for item in items:
            combo_id, combo_name, price, quantity = item
            subtotal = float(price) * quantity
            message += f"🛒 {combo_name} x{quantity}: ₹{subtotal:.2f}\n"
        message += f"\n💰 Total: ₹{order_amount:.2f}\n📍 Delivery Address: {address}\n\n"
        message += f"Click here to pay: {payment_url}\n\n"
        message += "Complete the payment to confirm your order!"

        # Send via Route Mobile WhatsApp API
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
        print(f"Sending WhatsApp message to {frm}, payload: {payload}")
        response = requests.post(url, data=payload.encode('utf-8'), headers=headers, verify=False)
        response.raise_for_status()
        print(f"WhatsApp message sent, response: {response.text}")
        savesentlog(frm, response.text, response.status_code, "payment_link")
        return payment_url
    except Exception as e:
        print(f"Failed to send payment message for user {frm}: {str(e)}")
        return None

def checkout(rcvr, name, address, pincode, payment_method, cnx, cursor, reference_id=None):
    try:
        print(f"Starting checkout for user {rcvr}, payment_method: {payment_method}, reference_id: {reference_id}")
        
        # Validate user data from users table
        print(f"Fetching user data for {rcvr}")
        cursor.execute("SELECT name, address, pincode FROM users WHERE phone_number = %s", (rcvr,))
        user_data = cursor.fetchone()
        print(f"User data: {user_data}")
        if not user_data or not all(user_data[:3]):  # Check name, address, pincode
            print(f"Checkout failed: Incomplete user data for {rcvr}, user_data: {user_data}")
            return {"total": 0, "message": "Error: User data incomplete. Please provide name, address, and pincode."}
        
        # Get cart items
        cursor.execute("SELECT combo_id, combo_name, quantity, price FROM user_cart WHERE phone_number = %s", (rcvr,))
        cart_items = cursor.fetchall()
        print(f"Cart items: {cart_items}")
        if not cart_items:
            print(f"Checkout failed: No cart items for {rcvr}")
            return {"total": 0, "message": "Error: No valid order details found. Please select a combo."}
        
        total = 0
        for item in cart_items:
            combo_id, combo_name, quantity, price = item
            subtotal = float(price) * quantity
            total += subtotal
            
            # Insert order into orders table
            print(f"Inserting order: {combo_name} x{quantity}, price: {price}, total: {subtotal}, reference_id: {reference_id}")
            cursor.execute(
                "INSERT INTO orders (user_phone, customer_name, address, pincode, combo_id, combo_name, price, quantity, total_amount, payment_method, payment_status, order_status, reference_id) "
                "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
                (rcvr, name, address, pincode, combo_id, combo_name, float(price), quantity, subtotal, payment_method,
                 'Pending' if payment_method != 'COD' else 'Completed', 'Placed', reference_id)
            )
        
        # Log inserted orders for debugging
        cursor.execute(
            "SELECT id, combo_id, combo_name, quantity, price, total_amount, payment_method, order_status, created_at "
            "FROM orders WHERE user_phone = %s AND payment_method = %s",
            (rcvr, payment_method)
        )
        inserted_orders = cursor.fetchall()
        print(f"Inserted orders for {rcvr}: {inserted_orders}")
        
        # Clear cart
        cursor.execute("DELETE FROM user_cart WHERE phone_number = %s", (rcvr,))
        
        # Clear pincode from users table
        cursor.execute("UPDATE users SET pincode = NULL WHERE phone_number = %s", (rcvr,))
        
        cnx.commit()
        print(f"Checkout completed successfully for {rcvr}, total: ₹{total:.2f}")
        return {
            "total": total,
            "message": f"Order placed! Total: ₹{total:.2f}\nYour order will be delivered to {address}, Pincode: {pincode} by tomorrow 9 AM."
        }
    except Exception as e:
        print(f"Checkout failed for user {rcvr}: {str(e)}")
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
        print(f"Pincode check failed: {e}")
        return False

def get_combo_price(combo_id):
    try:
        # Check FALLBACK_COMBOS first
        if combo_id in FALLBACK_COMBOS:
            price = float(FALLBACK_COMBOS[combo_id].get("price", 0))
            print(f"Price for combo_id {combo_id} from FALLBACK_COMBOS: {price}")
            return price
        
        # Fallback to combos table if combo_id not in FALLBACK_COMBOS
        cnx = pymysql.connect(user=usr, password=pas, host=aws_host, database=db)
        cursor = cnx.cursor()
        cursor.execute("SELECT price FROM combos WHERE combo_id = %s", (combo_id,))
        result = cursor.fetchone()
        cnx.close()
        if result:
            price = float(result[0])
            print(f"Price for combo_id {combo_id} from combos table: {price}")
            return price
        
        # If not in combos table, return 0
        print(f"Price for combo_id {combo_id} not found in FALLBACK_COMBOS or combos table, returning 0")
        return 0
    except Exception as e:
        print(f"Failed to fetch price for combo_id {combo_id}: {e}")
        # On error, try FALLBACK_COMBOS as final fallback
        price = float(FALLBACK_COMBOS.get(combo_id, {}).get("price", 0))
        print(f"Price for combo_id {combo_id} from FALLBACK_COMBOS (error fallback): {price}")
        return price

def get_combo_name(combo_id):
    combo_id = combo_id.strip()
    try:
        cnx = pymysql.connect(user=usr, password=pas, host=aws_host, database=db)
        cursor = cnx.cursor()
        cursor.execute("SELECT combo_name FROM combos WHERE combo_id = %s", (combo_id,))
        result = cursor.fetchone()
        cnx.close()
        if result:
            print(f"Found combo_name: {result[0]} for combo_id: {combo_id}")
            return result[0]
        print(f"Combo_id {combo_id} not in database, checking FALLBACK_COMBOS")
        return FALLBACK_COMBOS.get(combo_id, {}).get("name", "Unknown Combo")
    except Exception as e:
        print(f"Failed to fetch name for combo_id {combo_id}: {e}")
        return FALLBACK_COMBOS.get(combo_id, {}).get("name", "Unknown Combo")

def reset_user_flags(frm, cnx, cursor):
    try:
        reset_query = """UPDATE users SET 
            is_info = '0', main_menu = '0', is_main = '0', 
            is_temp = '0', sub_menu = '0', is_submenu = '0',
            selected_combo = NULL, quantity = NULL, 
            address = NULL, payment_method = NULL, order_amount = NULL,
            combo_id = NULL, pincode = NULL
            WHERE phone_number = %s"""
        cursor.execute(reset_query, (frm,))
        cursor.execute("DELETE FROM user_cart WHERE phone_number = %s", (frm,))
        cnx.commit()
    except Exception as e:
        print(f"Reset flags failed: {e}")
        cnx.rollback()

def is_valid_name(resp1):
    if resp1 in greeting_word:
        return False
    if not re.match(r'^[\u0900-\u097Fa-zA-Z\s]+$', resp1):
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
        cursor.execute("SELECT combo_id, combo_name, quantity, price FROM user_cart WHERE phone_number = %s", (phone,))
        cart_items = cursor.fetchall()
        print(f"Cart items for {phone}: {cart_items}")
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
        
        cart_message += f"\n💰 Total Amount: ₹{total:.2f}"
        if address:
            cart_message += f"\n📍 Delivery Address: {address}"
        cnx.close()
        print(f"Generated summary for {phone}: {cart_message}")
        return cart_message, total, item_count
    except Exception as e:
        print(f"Error in get_cart_summary for {phone}: {e}")
        return "Error retrieving order details. Please try again.", 0, 0

@app.route('/', methods=['POST', 'GET'])
def Get_Message():
    cnx = None
    cursor = None
    try:
        response = request.json
        if response is None or not isinstance(response, dict): 
            print("No JSON data or invalid format")
            return 'Success'
        if 'statuses' in response: 
            print("Received status update, skipping")
            return 'Success'
        if 'messages' not in response:
            print("No 'messages' key in response")
            return 'Success'

        print(f"Received response: {response}")
        frm = str(response["messages"][0]["from"])
        msg_type = str(response["messages"][0]["type"])
        print(f"Message from: {frm}, Type: {msg_type}")

        if msg_type == 'text':
            resp1 = response["messages"][0]["text"]["body"]
        elif msg_type == 'interactive':
            interactive_data = response["messages"][0]["interactive"]
            if 'button_reply' in interactive_data:
                resp1 = interactive_data["button_reply"]["id"]
            elif 'list_reply' in interactive_data:
                resp1 = interactive_data["list_reply"]["id"]
            else:
                resp1 = ''
        elif msg_type == 'order':
            if 'product_items' in response["messages"][0]["order"]:
                resp1 = response["messages"][0]["order"]["product_items"][0]["product_retailer_id"]
            else:
                resp1 = ''
                print("Order message missing product_items")
        else:
            resp1 = ''
            
        print(f"Processed resp1: {resp1}")
        cnx = pymysql.connect(user=usr, password=pas, host=aws_host, database=db)
        cursor = cnx.cursor()
        check_already_valid = "SELECT name, pincode, selected_combo, quantity, address, payment_method, is_valid, order_amount, is_info, main_menu, is_main, is_temp, sub_menu, is_submenu, combo_id FROM users WHERE phone_number = %s"
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
        else:
            name, pincode, selected_combo, quantity, address, payment_method, is_valid, order_amount, is_info, main_menu, is_main, is_temp, sub_menu, is_submenu, combo_id = result
            camp_id = '1'

        if (msg_type == 'text' or msg_type == 'interactive' or msg_type == 'order') and len(frm) == 12:
            if resp1 in greeting_word:
                if result is None:  # New user
                    cursor.execute("INSERT INTO users (phone_number, camp_id, is_valid, is_info) VALUES (%s, %s, %s, %s)", (frm, '1', '1', '1'))
                    cnx.commit()
                    print('Inserted new user successfully')
                    send_message(frm, wl, 'welcome message')
                else:  # Existing user
                    print(f"Existing user {frm} detected, name: {name}")
                    if name:  # If name exists in database
                        reset_user_flags(frm, cnx, cursor)  # Reset order-related flags, cart, and pincode
                        cursor.execute("UPDATE users SET is_main = '1', is_valid = '1' WHERE phone_number = %s", (frm,))
                        cnx.commit()
                        print(f"Reset flags and set is_main for user {frm}")
                        send_message(frm, r2.format(name=name), 'pincode')  # Send pincode prompt with name
                    else:
                        # In case name is missing (edge case), ask for name
                        cursor.execute("UPDATE users SET is_info = '1', is_valid = '1' WHERE phone_number = %s", (frm,))
                        cnx.commit()
                        send_message(frm, wl, 'welcome message')

            if camp_id == '1':
                if is_info == '1' and pincode is None:
                    if all(x.isalpha() or x.isspace() for x in resp1) and is_valid_name(resp1):
                        print("Accepting name")
                        name = resp1
                        cursor.execute("UPDATE users SET name = %s, is_main = %s, is_info = %s WHERE phone_number = %s", (name, '1', '0', frm))
                        cnx.commit()
                        send_message(frm, r2.format(name=name), 'pincode')
                        print('Pincode Msg Delivered Successfully.......')
                    else:
                        send_message(frm, invalid_name, "invalid_name")    
                
                if is_main == '1' and pincode is None:
                    pincode = resp1
                    print(f'Processing pincode: {pincode}')
                    if pincode.isdigit() and len(pincode) == 6:
                        if check_pincode(pincode):
                            cursor.execute("UPDATE users SET pincode = %s, main_menu = %s, is_main = %s WHERE phone_number = %s", (pincode, '1', '0', frm))
                            cnx.commit()
                            print('Calling send_multi_product_message')
                            result = send_multi_product_message(frm, CATALOG_ID, 'menu')
                            print(f'send_multi_product_message result: {result}')
                        else:
                            send_message(frm, r3, 'pincode_error')
                    else:
                        send_message(frm, r4, 'invalid_pincode')
                
                # Address input block
                if is_temp == '1' and address is None:
                    print(f"Processing address input: {resp1}")
                    if is_valid_address(resp1):
                        address = resp1 
                        cursor.execute("UPDATE users SET address = %s, is_submenu = %s WHERE phone_number = %s", (address, '1', frm))
                        cnx.commit()
                        
                        # Generate order summary from user_cart table
                        order_summary, total, item_count = get_cart_summary(frm, name, address)
                        if item_count == 0:
                            send_message(frm, order_summary, "no_order")
                            send_multi_product_message(frm, CATALOG_ID, 'menu')
                        else:
                            order_summary += "\n\nPlease confirm your order or go back to the menu to make changes."
                            print("Sending order confirmation with buttons")
                            interactive_template_with_2button(frm, order_summary, "order_summary")
                    else:
                        print(f"Invalid address attempt: {resp1} from {frm}")
                        send_message(frm, invalid_address, 'invalid_address')
                
                # Product selection block
                elif main_menu == '1' and msg_type == 'order':
                    print("Entering product selection block")
                    if 'product_items' in response["messages"][0]["order"]:
                        product_items = response["messages"][0]["order"]["product_items"]
                        print(f"Processing {len(product_items)} product items")
                        
                        total_amount = 0
                        valid_selection = False
                        
                        # Clear existing cart items for this user
                        cursor.execute("DELETE FROM user_cart WHERE phone_number = %s", (frm,))
                        cnx.commit()
                        
                        # Log selected items
                        print(f"Selected product items: {product_items}")
                        
                        for item in product_items:
                            combo_id = item.get("product_retailer_id", "").strip()
                            quantity = int(item.get("quantity", 1))
                            item_price = get_combo_price(combo_id)  # Use updated get_combo_price
                            selected_combo = get_combo_name(combo_id)
                            print(f"Processing combo_id: {combo_id}, name: {selected_combo}, quantity: {quantity}, price: {item_price}")
                            
                            if selected_combo != "Unknown Combo" and item_price > 0:
                                total_amount += item_price * quantity
                                valid_selection = True
                                print(f"Storing cart item: {selected_combo} x{quantity}, price: {item_price}")
                                cursor.execute(
                                    "INSERT INTO user_cart (phone_number, combo_id, combo_name, quantity, price) VALUES (%s, %s, %s, %s, %s)",
                                    (frm, combo_id, selected_combo, quantity, item_price)
                                )
                                cnx.commit()
                            else:
                                print(f"Invalid combo_id {combo_id} or price 0")
                        
                        if valid_selection:
                            try:
                                cursor.execute("UPDATE users SET is_temp = '1' WHERE phone_number = %s", (frm,))
                                cnx.commit()
                                print("Sending address prompt")
                                send_message(frm, m3, "ask_address")
                            except Exception as e:
                                print(f"Database update failed: {e}")
                                send_multi_product_message(frm, CATALOG_ID, 'menu')
                                send_message(frm, "Error processing your selection. Please try again.", "error")
                        else:
                            print("No valid products selected")
                            send_multi_product_message(frm, CATALOG_ID, 'menu')
                            send_message(frm, "Sorry, none of the selected products are available. Please choose another combo.", "illegal_combo")
                    else:
                        print("No valid product items in order message")
                        send_multi_product_message(frm, CATALOG_ID, 'menu')
                
                elif is_submenu == '1' and payment_method is None:
                    print(f"Processing submenu input: {resp1}")
                    if resp1 == "1":  # Confirm
                        print("User confirmed order, sending payment options")
                        cursor.execute("UPDATE users SET is_submenu = '1' WHERE phone_number = %s", (frm,))
                        cnx.commit()
                        interactive_template_with_3button(frm, "💳 Please select your preferred payment method to continue:", "payment")
                    elif resp1 == "2":  # Main Menu
                        print("User selected Main Menu, resetting flags")
                        reset_user_flags(frm, cnx, cursor)
                        cursor.execute("UPDATE users SET main_menu = '1' WHERE phone_number = %s", (frm,))
                        cnx.commit()
                        send_multi_product_message(frm, CATALOG_ID, "menu")
                    else:
                        payment_method = {"3": "COD", "5": "Pay Now"}.get(resp1)
                        if payment_method:
                            print(f"User selected payment method: {payment_method}")
                            cursor.execute("UPDATE users SET payment_method = %s WHERE phone_number = %s", (payment_method, frm))
                            cnx.commit()
                            # Fetch cart items
                            cursor.execute("SELECT combo_id, combo_name, quantity, price FROM user_cart WHERE phone_number = %s", (frm,))
                            cart_items = cursor.fetchall()
                            print(f"Cart items for checkout: {cart_items}")
                            if not cart_items:
                                print("No valid order details in user_cart table")
                                send_message(frm, "No order details found! Please select a combo to proceed.", "no_order")
                                cursor.execute("UPDATE users SET payment_method = NULL WHERE phone_number = %s", (frm,))
                                cnx.commit()
                                cnx.close()
                                return 'Success'
                            
                            total_amount = sum(float(item[3]) * item[2] for item in cart_items)  # price * quantity
                            items = [(item[0], item[1], float(item[3]), item[2]) for item in cart_items]  # (combo_id, combo_name, price, quantity)
                            
                            if payment_method == "COD":
                                print(f"Processing COD checkout for user {frm}")
                                checkout_result = checkout(frm, name, address, pincode, payment_method, cnx, cursor)
                                if checkout_result["total"] == 0:
                                    print(f"Checkout failed during COD for user {frm}: {checkout_result['message']}")
                                    send_message(frm, checkout_result["message"], "invalid_order")
                                    cursor.execute("UPDATE users SET payment_method = NULL WHERE phone_number = %s", (frm,))
                                    cnx.commit()
                                    cnx.close()
                                    return 'Success'
                                
                                # Debug: Check orders table before confirmation query
                                cursor.execute(
                                    "SELECT id, combo_id, combo_name, quantity, price, total_amount, payment_method, order_status, created_at "
                                    "FROM orders WHERE user_phone = %s",
                                    (frm,)
                                )
                                all_orders = cursor.fetchall()
                                print(f"All orders for {frm} before confirmation: {all_orders}")
                                
                                # Generate final confirmation from orders
                                cursor.execute(
                                    "SELECT combo_id, combo_name, price, quantity, total_amount, address "
                                    "FROM orders WHERE user_phone = %s AND payment_method = 'COD' AND order_status = 'Placed' "
                                    "ORDER BY created_at DESC",
                                    (frm,)
                                )
                                items = cursor.fetchall()
                                print(f"Orders for confirmation: {items}")
                                if not items:
                                    # Fallback query to diagnose
                                    cursor.execute(
                                        "SELECT combo_id, combo_name, price, quantity, total_amount, address, payment_method, order_status "
                                        "FROM orders WHERE user_phone = %s ORDER BY created_at DESC",
                                        (frm,)
                                    )
                                    fallback_items = cursor.fetchall()
                                    print(f"Fallback query results for {frm}: {fallback_items}")
                                    send_message(frm, "Error: No order found. Please try again.", "no_order")
                                    cursor.execute("UPDATE users SET payment_method = NULL WHERE phone_number = %s", (frm,))
                                    cnx.commit()
                                    cnx.close()
                                    return 'Success'
                                
                                total = 0
                                item_count = 0
                                confirmation = f"Dear *{name}*,\n\nThank you for your order with Balutedaar! Below is your order confirmation:\n\n📦 *Order Details*:\n"
                                for item in items:
                                    combo_id, combo_name, price, quantity, item_total, address = item
                                    subtotal = float(price) * quantity
                                    total += subtotal
                                    item_count += 1
                                    confirmation += f"🛒 {combo_name} x{quantity}: ₹{subtotal:.2f}\n"
                                confirmation += f"\n💰 Total Amount: ₹{total:.2f}\n📍 Delivery Address: {address}\n"
                                confirmation += f"🚚 *Delivery Schedule*: Your order will be delivered to your doorstep by tomorrow 9 AM.\n\n"
                                confirmation += f"We appreciate your support for fresh, sustainable produce. If you have any questions, feel free to reach out!\n\nBest regards,\nThe Balutedaar Team"
                                print(f"Sending COD confirmation to {frm}")
                                cursor.execute("UPDATE users SET is_submenu = '0', payment_method = NULL WHERE phone_number = %s", (frm,))
                                cnx.commit()
                                send_message(frm, confirmation, "order_confirmation")
                                cnx.close()
                                return 'Success'
                            elif payment_method == "Pay Now":
                                print(f"Processing Pay Now for user {frm}")
                                reference_id = f"q9{uuid.uuid4().hex[:8]}"
                                print(f"Generated reference_id: {reference_id}")
                                
                                # Run checkout to move order to orders table
                                print(f"Calling checkout for Pay Now, user: {frm}")
                                checkout_result = checkout(frm, name, address, pincode, payment_method, cnx, cursor, reference_id)
                                if checkout_result["total"] == 0:
                                    print(f"Checkout failed during Pay Now for user {frm}: {checkout_result['message']}")
                                    send_message(frm, checkout_result["message"], "invalid_order")
                                    cursor.execute("UPDATE users SET payment_method = NULL WHERE phone_number = %s", (frm,))
                                    cnx.commit()
                                    cnx.close()
                                    return 'Success'
                                
                                # Send Razorpay payment link
                                print(f"Sending payment link for user {frm}")
                                payment_url = send_payment_message(frm, name, address, pincode, items, total_amount, reference_id)
                                if not payment_url:
                                    print(f"Failed to generate payment link for user {frm}")
                                    send_message(frm, "Error generating payment link. Please try again.", "payment_error")
                                    cursor.execute("UPDATE users SET payment_method = NULL WHERE phone_number = %s", (frm,))
                                    cnx.commit()
                                    cnx.close()
                                    return 'Success'
                                
                                print(f"Payment link sent successfully to {frm}: {payment_url}")
                                cursor.execute("UPDATE users SET is_submenu = '0' WHERE phone_number = %s", (frm,))
                                cnx.commit()
                                cnx.close()
                                return 'Success'

        cnx.commit()
        cnx.close()
        return 'Success'
    except Exception as e:
        print(f"Main handler error: {e}")
        if cnx:
            cnx.rollback()
            cnx.close()
        return 'Success'

@app.route('/payment-callback', methods=['GET'])
def payment_callback():
    try:
        payment_id = request.args.get('razorpay_payment_id')
        payment_link_id = request.args.get('razorpay_payment_link_id')
        payment_link_reference_id = request.args.get('razorpay_payment_link_reference_id')
        payment_link_status = request.args.get('razorpay_payment_link_status')
        signature = request.args.get('razorpay_signature')

        if payment_link_status == 'paid':
            try:
                razorpay_client.utility.verify_payment_link_signature({
                    "payment_link_id": payment_link_id,
                    "payment_link_reference_id": payment_link_reference_id,
                    "payment_link_status": payment_link_status,
                    "razorpay_payment_id": payment_id,
                    "razorpay_signature": signature
                })
                # Update order status in database
                cnx = pymysql.connect(user=usr, password=pas, host=aws_host, database=db)
                cursor = cnx.cursor()
                cursor.execute(
                    "UPDATE orders SET payment_status = 'Completed', order_status = 'Confirmed' WHERE reference_id = %s",
                    (payment_link_reference_id,)
                )
                cursor.execute(
                    "SELECT user_phone, customer_name, address, pincode, combo_id, combo_name, price, quantity, total_amount "
                    "FROM orders WHERE reference_id = %s",
                    (payment_link_reference_id,)
                )
                items = cursor.fetchall()
                
                # Clear pincode from users table
                if items:
                    frm = items[0][0]
                    cursor.execute("UPDATE users SET pincode = NULL WHERE phone_number = %s", (frm,))
                
                cnx.commit()
                cnx.close()
                
                if items:
                    frm, name, address, pincode = items[0][0:4]
                    total = items[0][8]
                    confirmation = f"Dear *{name}*,\n\nThank you for your payment! Your order is confirmed:\n\n📦 *Order Details*:\n"
                    for item in items:
                        combo_name, price, quantity = item[5:8]
                        subtotal = float(price) * quantity
                        confirmation += f"🛒 {combo_name} x{quantity}: ₹{subtotal:.2f}\n"
                    confirmation += f"\n💰 Total Amount: ₹{total:.2f}\n📍 Delivery Address: {address}\n"
                    confirmation += f"🚚 *Delivery Schedule*: Your order will be delivered by tomorrow 9 AM.\n\n"
                    confirmation += f"We appreciate your support for fresh, sustainable produce!\n\nBest regards,\nThe Balutedaar Team"
                    send_message(frm, confirmation, "payment_confirmation")
                return "Payment successful! Your order is confirmed."
            except Exception as e:
                print(f"Payment verification failed: {e}")
                return "Payment verification failed."
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
        print(f"Payment callback error: {e}")
        return "Error processing payment callback."

if __name__ == '__main__':
    app.debug = True
    app.run(host='0.0.0.0', port=5000)
