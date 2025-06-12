import logging
import os
import re
import json
import uuid
import requests
import urllib3
import pymysql
import razorpay
from datetime import datetime
from flask import Flask, jsonify, request
from dotenv import load_dotenv
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

# Configure logging
logging.basicConfig(
    filename='app.log',
    level=logging.DEBUG,
    format='%(asctime)s %(levelname)s: %(message)s'
)

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

app = Flask(__name__)

# Load environment variables
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

# Constants
greeting_word = ['Hi', 'hi', 'HI', 'Hii', 'hii', 'HII', 'Hello', 'hello', 'HELLO', 'Welcome', 'welcome', 'WELCOME', 'Hey', 'hey', 'HEY']
CATALOG_ID = "1221166119417288"

# Messages
m1 = '''Please select a combo from the list below:'''
m3 = '''🚚 Just one more step!

Kindly share your complete delivery address so we can deliver your veggies without any delay.'''
invalid_address = '''😕 Oops! That doesn’t look like a valid address. Please enter a complete address with house/flat number, street name, and area (e.g., Flat 101, Gokhale Society, Kothrud Pune). Use letters, numbers, spaces, commas, periods, hyphens, or slashes only.'''
invalid_name = '''⚠️ Please enter a valid name using alphabetic characters only.'''
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
Please enter a *6-digit pincode* (e.g., 411038). 📍'''

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
    try:
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
        logging.info(f"send_message to {rcvr}, payload: {payload}")
        response = requests.post(url, data=payload.encode('utf-8'), headers=headers, verify=False, timeout=10)
        response.raise_for_status()
        logging.info(f"send_message response: {response.text}")
        savesentlog(rcvr, response.text, response.status_code, message)
        return response.text
    except requests.RequestException as e:
        logging.error(f"Failed to send message to {rcvr}: {e}, Response: {response.text if 'response' in locals() else 'No response'}")
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
    except Exception as e:
        logging.error(f"Failed to save log for {frm}: {e}")
    finally:
        if 'cnx' in locals():
            cnx.close()

def interactive_template_with_2button(rcvr, body, message):
    try:
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
        logging.info(f"2-button payload to {rcvr}: {payload}")
        response = requests.post(url, data=payload.encode('utf-8'), headers=headers, verify=False, timeout=10)
        response.raise_for_status()
        logging.info(f"2-button response: {response.text}")
        savesentlog(rcvr, response.text, response.status_code, message)
        return response.text
    except requests.RequestException as e:
        logging.error(f"Interactive 2-button failed for {rcvr}: {e}, Response: {response.text if 'response' in locals() else 'No response'}")
        send_message(rcvr, "Error processing order summary. Please try again.", "error")
        return None

def interactive_template_with_3button(rcvr, body, message):
    try:
        if not authkey:
            logging.warning(f"Skipping interactive_template_with_3button to {rcvr}: No authkey")
            return None
        url = "https://apis.rmlconnect.net/wba/v1/messages?source=UI"
        if not rcvr.startswith('+'):
            rcvr = f"+91{rcvr.strip()[-10:]}"
        if message == "payment":
            payload = json.dumps({
                "phone": rcvr,
                "enable_acculync": False,
                "extra": message,
                "media": {
                    "type": "interactive_list",
                    "body": body,
                    "button_text": "Choose Payment",
                    "button": [
                        {
                            "section_title": "Payment Options",
                            "row": [
                                {
                                    "id": "3",
                                    "title": "COD",
                                    "description": "Pay cash on delivery"
                                },
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
            logging.info(f"3-button payload to {rcvr}: {payload}")
        headers = {
            'Content-Type': 'application/json',
            'Authorization': authkey,
            'referer': 'myaccount.rmlconnect.net'
        }
        session = requests.Session()
        retries = Retry(total=2, backoff_factor=1, status_forcelist=[429, 500, 502, 503, 504])
        session.mount('https://', HTTPAdapter(max_retries=retries))
        response = session.post(url, headers=headers, data=payload.encode('utf-8'), verify=False, timeout=10)
        response.raise_for_status()
        logging.info(f"3-button response: {response.text}")
        savesentlog(rcvr, response.text, response.status_code, message)
        return response.text
    except requests.RequestException as e:
        logging.error(f"Interactive 3-button failed for {rcvr}: {e}, Response: {response.text if 'response' in locals() else 'No response'}")
        send_message(rcvr, "Error processing payment options. Please try again.", "payment_error")
        return None
    except Exception as e:
        logging.error(f"Unexpected error in interactive_template_with_3button for {rcvr}: {str(e)}", exc_info=True)
        send_message(rcvr, "Error processing payment options. Please try again.", "payment_error")
        return None

def interactive_template_with_address_buttons(rcvr, body, message):
    try:
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
                        "section_title": "Address Options",
                        "row": [
                            {
                                "id": "6",
                                "title": "Proceed",
                                "description": "Continue with this address"
                            }
                        ]
                    },
                    {
                        "section_title": "Change Address",
                        "row": [
                            {
                                "id": "7",
                                "title": "Enter New Address",
                                "description": "Provide a new delivery address"
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
        logging.info(f"Address buttons payload to {rcvr}: {payload}")
        response = requests.post(url, data=payload.encode('utf-8'), headers=headers, verify=False, timeout=10)
        response.raise_for_status()
        logging.info(f"Address buttons response: {response.text}")
        savesentlog(rcvr, response.text, response.status_code, message)
        return response.text
    except requests.RequestException as e:
        logging.error(f"Interactive address buttons failed for {rcvr}: {e}, Response: {response.text if 'response' in locals() else 'No response'}")
        send_message(rcvr, "Error processing address options. Please try again.", "error")
        return None

def send_multi_product_message(rcvr, catalog_id, message):
    try:
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
        logging.info(f"Multi-product payload to {rcvr}: {payload}")
        response = requests.post(url, headers=headers, data=payload.encode('utf-8'), verify=False, timeout=10)
        response.raise_for_status()
        logging.info(f"Multi-product response: {response.text}")
        savesent(response(rcvr, text, response.status_code, response.text))
        logging.info(f"Sent multi product response: {response.text}")
        return response.text
    except requests.RequestException as e:
        logging.error(f"Multi-product message failed for {rcvr}: {e}, Response: {response.text if 'response' in locals() else 'No response'}")
        return None

def send_payment_message(frm, name, address, pincode, items, order_amount, reference_id):
    try:
        logging.info(f"Creating payment link for {frm}, amount: {order_amount}, reference_id: {reference_id}")
        payment_link_data = {
            "amount": int(order_amount * 100),
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
        logging.info(f"Razorpay payment link data: {payment_link_data}")
        payment_link = razorpay_client.payment_link.create(payment_link_data)
        payment_url = payment_link.get("short_url", "")
        logging.info(f"Razorpay payment link created: {payment_url}")

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
        logging.info(f"Sending payment link to {frm}, payload: {payload}")
        response = requests.post(url, data=payload.encode('utf-8'), headers=headers, verify=False, timeout=10)
        response.raise_for_status()
        logging.info(f"Payment link response: {response.text}")
        savesentlog(frm, response.text, response.status_code, "payment_link")
        return payment_url
    except Exception as e:
        logging.error(f"Failed to send payment message for {frm}: {str(e)}")
        return None

def checkout(rcvr, name, address, pincode, payment_method, cnx, cursor, reference_id=None):
    try:
        logging.info(f"Starting checkout for {rcvr}, payment_method: {payment_method}, reference_id: {reference_id}")
        cursor.execute("SELECT name, address, pincode FROM users WHERE phone_number = %s", (rcvr,))
        user_data = cursor.fetchone()
        logging.info(f"User data for {rcvr}: {user_data}")
        if not user_data or not all(user_data[:3]):
            logging.error(f"Checkout failed: Incomplete user data for {rcvr}")
            return {"total": 0, "message": "Error: Please provide name, address, and pincode."}

        cursor.execute("SELECT combo_id, combo_name, quantity, price FROM user_cart WHERE phone_number = %s", (rcvr,))
        cart_items = cursor.fetchall()
        logging.info(f"Cart items for {rcvr}: {cart_items}")
        if not cart_items:
            logging.error(f"Checkout failed: No cart items for {rcvr}")
            return {"total": 0, "message": "Error: No valid order details found. Please select a combo."}

        total = 0
        for item in cart_items:
            combo_id, combo_name, quantity, price = item
            subtotal = float(price) * quantity
            total += subtotal
            cursor.execute(
                "INSERT INTO orders (user_phone, customer_name, address, pincode, combo_id, combo_name, price, quantity, total_amount, payment_method, payment_status, order_status, reference_id) "
                "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
                (rcvr, name, address, pincode, combo_id, combo_name, float(price), quantity, subtotal, payment_method,
                 'Pending' if payment_method != 'COD' else 'Completed', 'Placed', reference_id)
            )
            logging.info(f"Inserted order for {rcvr}: {combo_name} x{quantity}, subtotal: ₹{subtotal:.2f}")

        cursor.execute("DELETE FROM user_cart WHERE phone_number = %s", (rcvr,))
        cursor.execute("UPDATE users SET pincode = NULL WHERE phone_number = %s", (rcvr,))
        cnx.commit()
        logging.info(f"Checkout completed for {rcvr}, total: ₹{total:.2f}")
        return {
            "total": total,
            "message": f"Order placed successfully! Total: ₹{total:.2f}\nYour order will be delivered to {address}, Pincode: {pincode} by tomorrow 9 AM."
        }
    except Exception as e:
        logging.error(f"Checkout failed for {rcvr}: {str(e)}", exc_info=True)
        cnx.rollback()
        return {"total": 0, "message": f"Error during checkout: {str(e)}. Please try again."}

@app.route('/webhook', methods=['POST'])
def webhook():
    try:
        response = request.get_json()
        logging.info(f"Received webhook: {json.dumps(response, indent=2)}")
        if not response or 'messages' not in response:
            logging.warning("Invalid webhook data")
            return jsonify({"status": "error", "message": "Invalid data"}), 400

        cnx = pymysql.connect(user=usr, max_allowed_packet=1073741824, password=pas, host=aws_host, database=db)
        cursor = cnx.cursor()

        frm = response["messages"][0]["from"]
        msg_type = response["messages"][0]["type"]
        logging.info(f"Message from: {frm}, type: {msg_type}")

        check_already_valid = "SELECT name, pincode, selected_combo, quantity, address, payment_method, is_valid, order_amount, is_info, main_menu, is_main, is_temp, sub_menu, is_submenu, camp_id, combo_id FROM users WHERE phone_number = %s"
        cursor.execute(check_already_valid, (frm,))
        result = cursor.fetchone()

        if result:
            name, pincode, selected_combo, quantity, address, payment_method, is_valid, order_amount, is_info, main_menu, is_main, is_temp, sub_menu, is_submenu, camp_id, combo_id = result
        else:
            name = pincode = selected_combo = quantity = address = payment_method = order_amount = camp_id = combo_id = None
            is_valid = is_info = main_menu = is_main = is_temp = sub_menu = is_submenu = '0'

        if msg_type == "text":
            body = response["messages"][0]["text"]["body"].strip()
            logging.info(f"Text message body: {body}")

        elif msg_type == "interactive":
            interactive_data = response["messages"][0]["interactive"]
            if "button_reply" in interactive_data:
                resp1 = interactive_data["button_reply"]["id"]
            elif "list_reply" in interactive_data:
                resp1 = interactive_data["list_reply"]["id"]
            else:
                resp1 = ""
            logging.info(f"Interactive response: {resp1}")

        elif msg_type == "order":
            logging.info("Order message received")
            resp1 = ""

        else:
            logging.warning(f"Unsupported message type: {msg_type}")
            send_message(frm, "Sorry, I can't process that type of message.", "error")
            return jsonify({"status": "success"}), 200

        if not result and body.lower() in [x.lower() for x in greeting_word]:
            logging.info(f"New user {frm} greeted")
            send_message(frm, wl_fallback, "welcome")
            cursor.execute("INSERT INTO users (phone_number, is_info, created_at) VALUES (%s, %s, %s)", (frm, '1', datetime.now()))
            cnx.commit()
        
        elif is_info == '1':
            if re.match(r'^[a-zA-Z\s]+$', body):
                logging.info(f"Valid name received for {frm}: {body}")
                cursor.execute("UPDATE users SET name = %s, is_info = '0', is_valid = '1' WHERE phone_number = %s", (body, frm))
                cnx.commit()
                send_message(frm, r2.format(name=body), "ask_pincode")
            else:
                logging.warning(f"Invalid name for {frm}: {body}")
                send_message(frm, invalid_name, "invalid_name")
        
        elif is_valid == '1' and pincode is None:
            if re.match(r'^\d{6}$', body) and body in ['411038', '411052', '411058', '411041']:
                logging.info(f"Valid pincode for {frm}: {body}")
                cursor.execute("UPDATE users SET pincode = %s, main_menu = '1' WHERE phone_number = %s", (body, frm))
                cnx.commit()
                send_multi_product_message(frm, CATALOG_ID, "menu")
                send_message(frm, m1, "show_menu")
            else:
                logging.warning(f"Invalid or unsupported pincode for {frm}: {body}")
                send_message(frm, r3 if re.match(r'^\d{6}$', body) else r4, "invalid_pincode")
        
        elif main_menu == '1' and msg_type == 'order':
            logging.info(f"Entering product selection block for {frm}")
            try:
                if 'product_items' in response["messages"][0]["order"]:
                    product_items = response["messages"][0]["order"]["product_items"]
                    logging.info(f"Processing {len(product_items)} product items for {frm}: {product_items}")
                    
                    total_amount = 0
                    valid_selection = False
                    
                    cursor.execute("DELETE FROM user_cart WHERE phone_number = %s", (frm,))
                    cnx.commit()
                    logging.info(f"Cleared user_cart for {frm}")
                    
                    for item in product_items:
                        combo_id = item.get("product_retailer_id", "").strip()
                        quantity = int(item.get("quantity", 1))
                        item_price = get_combo_price(combo_id)
                        selected_combo = get_combo_name(combo_id)
                        logging.info(f"Processing combo_id: {combo_id}, name: {selected_combo}, quantity: {quantity}, price: {item_price}")
                        
                        if selected_combo != "Unknown Combo" and item_price > 0 and quantity > 0:
                            total_amount += item_price * quantity
                            valid_selection = True
                            try:
                                cursor.execute(
                                    "INSERT INTO user_cart (phone_number, combo_id, combo_name, quantity, price) VALUES (%s, %s, %s, %s, %s)",
                                    (frm, combo_id, selected_combo, quantity, item_price)
                                )
                                cnx.commit()
                                logging.info(f"Inserted cart item for {frm}: {selected_combo} x{quantity}, price: {item_price}")
                            except Exception as e:
                                logging.error(f"Failed to insert cart item {combo_id} for {frm}: {str(e)}")
                                cnx.rollback()
                        else:
                            logging.warning(f"Invalid combo_id {combo_id}, price {item_price}, or quantity {quantity} for {frm}")
                    
                    if valid_selection:
                        cursor.execute("UPDATE users SET is_temp = '1', main_menu = '0' WHERE phone_number = %s", (frm,))
                        cnx.commit()
                        logging.info(f"Updated user state for {frm}: is_temp = 1, main_menu = 0")
                        if camp_id == '1':
                            cursor.execute("SELECT address FROM users WHERE phone_number = %s AND address IS NOT NULL", (frm,))
                            previous_address = cursor.fetchone()
                            if previous_address:
                                address_message = f"Hi *{name}*, 👋\n\nWe have your previous address:\n📍 {previous_address[0]}\n\nWould you like to proceed with this address or enter a new one?"
                                logging.info(f"Sending address confirmation to {frm}: {previous_address[0]}")
                                interactive_template_with_address_buttons(frm, address_message, "address_confirmation")
                            else:
                                logging.info(f"No previous address for {frm}, asking for new address")
                                send_message(frm, m3, "ask_address")
                        else:
                            logging.info(f"New user {frm}, asking for new address")
                            send_message(frm, m3, "ask_address")
                    else:
                        logging.warning(f"No valid products selected for {frm}")
                        send_multi_product_message(frm, CATALOG_ID, 'menu')
                        send_message(frm, "Sorry, none of the selected products are available. Please choose another combo.", "illegal_combo")
                else:
                    logging.warning(f"No valid product items in order for {frm}")
                    send_multi_product_message(frm, CATALOG_ID, 'menu')
            except Exception as e:
                logging.error(f"Error in product selection for {frm}: {str(e)}", exc_info=True)
                cnx.rollback()
                send_message(frm, "Error processing your selection. Please try again.", "error")
        
        elif is_temp == '1' and address is None:
            if re.match(r'^[a-zA-Z0-9\s,.\/-]+$', body) and len(body) >= 10:
                logging.info(f"Valid address for {frm}: {body}")
                cursor.execute("UPDATE users SET address = %s, is_temp = '0', is_submenu = '1' WHERE phone_number = %s", (body, frm))
                cnx.commit()
                cart_summary = get_cart_summary(frm, cursor)
                interactive_template_with_2button(frm, cart_summary, "order_summary")
            else:
                logging.warning(f"Invalid address for {frm}: {body}")
                send_message(frm, invalid_address, "invalid_address")
        
        elif is_submenu == '1' and payment_method is None:
            logging.info(f"Processing submenu input for {frm}: {resp1}")
            try:
                if resp1 == "1":  # Confirm
                    logging.info(f"Checking user_cart for {frm}")
                    cursor.execute("SELECT COUNT(*) FROM user_cart WHERE phone_number = %s", (frm,))
                    cart_count = cursor.fetchone()[0]
                    logging.info(f"Cart item count for {frm}: {cart_count}")
                    if cart_count == 0:
                        logging.warning(f"No items in user_cart for {frm}, redirecting to menu")
                        send_message(frm, "No order details found! Please select a combo to proceed.", "no_order")
                        reset_user_flags(frm, cnx, cursor)
                        cursor.execute("UPDATE users SET main_menu = '1', is_submenu = '0' WHERE phone_number = %s", (frm,))
                        cnx.commit()
                        send_multi_product_message(frm, CATALOG_ID, "menu")
                    else:
                        logging.info(f"Updating users table for {frm}")
                        cursor.execute("UPDATE users SET is_submenu = '1', payment_method = 'Pending' WHERE phone_number = %s", (frm,))
                        cnx.commit()
                        logging.info(f"Calling interactive_template_with_3button for {frm}")
                        result = interactive_template_with_3button(frm, "💳 Please select your preferred payment method to continue:", "payment")
                        logging.info(f"interactive_template_with_3button result for {frm}: {result}")
                elif resp1 == "2":  # Main Menu
                    logging.info(f"User {frm} selected Main Menu, resetting flags")
                    reset_user_flags(frm, cnx, cursor)
                    cursor.execute("UPDATE users SET main_menu = '1', is_submenu = '0' WHERE phone_number = %s", (frm,))
                    cnx.commit()
                    send_multi_product_message(frm, CATALOG_ID, "menu")
                else:
                    logging.warning(f"Invalid submenu input for {frm}: {resp1}")
                    send_message(frm, "Invalid selection. Please choose Confirm or Main Menu.", "invalid_input")
            except Exception as e:
                logging.error(f"Error in submenu block for {frm}: {str(e)}", exc_info=True)
                cnx.rollback()
                send_message(frm, "An error occurred. Please try again.", "error")
        
        elif payment_method == 'Pending' and resp1 in ['3', '5']:
            logging.info(f"Processing payment selection for {frm}: {resp1}")
            try:
                if resp1 == "3":  # COD
                    payment_method = "COD"
                    result = checkout(frm, name, address, pincode, payment_method, cnx, cursor)
                    cursor.execute("UPDATE users SET payment_method = NULL, is_submenu = '0', main_menu = '1' WHERE phone_number = %s", (frm,))
                    cnx.commit()
                    send_message(frm, result["message"], "order_confirmation")
                elif resp1 == "5":  # Pay Now
                    cursor.execute("SELECT combo_id, combo_name, price, quantity FROM user_cart WHERE phone_number = %s", (frm,))
                    items = cursor.fetchall()
                    reference_id = str(uuid.uuid4())
                    result = send_payment_message(frm, name, address, pincode, items, sum(float(item[2]) * item[3] for item in items), reference_id)
                    if result:
                        cursor.execute("UPDATE users SET payment_method = 'Online', reference_id = %s WHERE phone_number = %s", (reference_id, frm))
                        cnx.commit()
                        send_message(frm, "Please complete the payment using the link sent.", "payment_initiated")
                    else:
                        send_message(frm, "Error generating payment link. Please try again.", "payment_error")
            except Exception as e:
                logging.error(f"Error in payment processing for {frm}: {str(e)}", exc_info=True)
                cnx.rollback()
                send_message(frm, "Error processing payment. Please try again.", "error")
        
        else:
            logging.warning(f"Unhandled state for {frm}: is_submenu={is_submenu}, payment_method={payment_method}, resp1={resp1}")
            send_message(frm, "I'm not sure how to proceed. Please start over by saying 'Hi'.", "unknown_state")

        cnx.commit()
        return jsonify({"status": "success"}), 200
    except Exception as e:
        logging.error(f"Webhook error: {str(e)}", exc_info=True)
        if 'cnx' in locals():
            cnx.rollback()
            cnx.close()
        return jsonify({"status": "error", "message": str(e)}), 500
    finally:
        if 'cnx' in locals():
            cnx.close()

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
