from sqlalchemy.orm import Session
import datetime
import secrets
import re
from app.models import UserSession, TransactionRecord, PaymentProvider
from app.services.green_api import GreenAPIClient
from app.services.meter_api import MeterManagementAPI
from app.services.payment_api import payment_service

whatsapp_client = GreenAPIClient()
meter_client = MeterManagementAPI()

def generate_ref():
    """Generates a unique transaction reference."""
    date_str = datetime.datetime.utcnow().strftime("%Y%m%d")
    random_hex = secrets.token_hex(2).upper()
    return f"SAM-{date_str}-{random_hex}"

class ChatbotStateHandler:
    # Added sender_name parameter
    def __init__(self, db: Session, sender: str, text: str, sender_name: str = ""):
        self.db = db
        self.sender = sender
        self.text = text.strip()
        self.sender_name = sender_name
        self.is_new_user = False # Track if this is their first time
        
        # Fetch or create the user session
        self.session = self.db.query(UserSession).filter_by(whatsapp_num=self.sender).first()
        if not self.session:
            self.is_new_user = True # We had to create them, so they are new!
            self.session = UserSession(whatsapp_num=self.sender, current_state="MAIN_MENU", context_data={})
            self.db.add(self.session)
            self.db.commit()
 
    def process(self):
        # --- NEW: SESSION TIMEOUT LOGIC (15 MINUTES) ---
        now = datetime.datetime.utcnow()
        if self.session.updated_at:
            # Calculate how many seconds have passed since their last message
            time_diff = now - self.session.updated_at
            
            # If it has been more than 15 minutes (900 seconds) and they aren't already at the menu
            if time_diff.total_seconds() > 900 and self.session.current_state != "MAIN_MENU":
                # Silently reset them
                self.session.current_state = "MAIN_MENU"
                self.session.context_data = {}
                self.db.commit()
                # We don't send a message here, we just let the logic below handle their new text normally.
        # -----------------------------------------------

        state = self.session.current_state
        clean_text = self.text.lower()
        
        # --- SMART UX NAVIGATION ---
        # 1. Greetings & Main Menu
        if clean_text in ['hi', 'hello', 'menu', 'hie']:
            if self.is_new_user:
                msg = f"👋 Welcome to Smart Access, {self.sender_name}! ⚡\n\nWe provide secure, instant automated gas refills straight to your meter."
            else:
                msg = f"👋 Welcome back, {self.sender_name}! ⚡\n\nReady to top up your gas today?"
            
            self._reset_to_menu(msg)
            self._show_menu_options()
            return
            
        # 2. Cancellations (Makes more sense than saying 'Welcome back' when they cancel an action)
        if clean_text in ['0', 'cancel']:
            self._reset_to_menu("🚫 Operation cancelled. What would you like to do instead?")
            self._show_menu_options()
            return
        # ---------------------------

        # Route the user input to the correct handler based on their current state.
        if state == "MAIN_MENU":
            self._handle_main_menu()
        elif state == "AWAITING_METER":
            self._handle_awaiting_meter()
        elif state == "AWAITING_AMOUNT":
            self._handle_awaiting_amount()
        elif state == "AWAITING_PAYMENT_METHOD":
            self._handle_payment_method()
        elif state == "AWAITING_ECOCASH_NUMBER":
            self._handle_awaiting_ecocash_number()
        else:
            self._reset_to_menu("I didn't understand that. Let's start over.")
            self._show_menu_options()

    def _show_menu_options(self):
        """Displays the main options to the user."""
        menu = (
            "Today's gas price is USD 1.80 per kg.\n\n"
            "Reply with a number:\n"
            "1️⃣ Recharge gas meter\n"
            "2️⃣ Get help (Coming soon)"
        )
        whatsapp_client.send_message(self.sender, menu)

    def _handle_main_menu(self):
        if self.text == "1":
            self.session.current_state = "AWAITING_METER"
            self.db.commit()
            whatsapp_client.send_message(self.sender, "Please enter your meter number to proceed:\n\nReply *0* to cancel.")
        else:
            self._show_menu_options()

    def _handle_awaiting_meter(self):
        try:
            meter_no = self.text
            whatsapp_client.send_message(self.sender, "Checking meter details, please wait...")
            
            # --- TEMPORARY MOCK FOR TESTING ---
            if meter_no == "11112222333":
                meter_info = {
                    "errcode": "0", 
                    "value": {"customerName": "Test Account"}
                }
            else:
                meter_info = meter_client.get_meter_info(meter_no)
            # ----------------------------------
            
            # Failsafe in case the API returned a string or None instead of a dictionary
            if not isinstance(meter_info, dict):
                meter_info = {"errcode": "-1", "errmsg": f"System returned bad data type: {type(meter_info)}", "raw": str(meter_info)}

            # Check if the API returned a success code
            if str(meter_info.get("errcode")) == "0":
                data = meter_info.get("value", {})
                name = data.get("customerName", "Unknown")
                
                context = dict(self.session.context_data)
                context['meter_no'] = meter_no
                self.session.context_data = context
                self.session.current_state = "AWAITING_AMOUNT"
                self.db.commit()
                
                whatsapp_client.send_message(
                    self.sender, 
                    f"✅ Valid! Registered to: *{name}*\n\n"
                    "Enter recharge amount in USD (e.g., 15.00):\n\n"
                    "Reply *0* to cancel."
                )
            else:
                # TROUBLESHOOTING MODE: Expose the exact API error message
                error_msg = meter_info.get("errmsg", "Unknown API Error")
                raw_response = str(meter_info) 
                
                whatsapp_client.send_message(
                    self.sender, 
                    f"❌ API Rejected the number.\n\n"
                    f"*Server Reason:* {error_msg}\n"
                    f"*Raw Data:* {raw_response}\n\n"
                    f"Reply *0* to cancel."
                )
                
        except Exception as e:
            # If the code physically crashes, send the Python error to WhatsApp!
            import traceback
            error_trace = traceback.format_exc()
            print("\n=== SYSTEM CRASH ===")
            print(error_trace)
            print("====================\n")
            
            whatsapp_client.send_message(
                self.sender, 
                f"⚠️ CRITICAL PYTHON CRASH:\n\n{str(e)}\n\nCheck your computer terminal for the exact line number!"
            )

    def _handle_awaiting_amount(self):
        # 1. Normalize commas to periods (in case they type 15,50)
        normalized_text = self.text.replace(',', '.')
        
        # 2. Extract the first valid number pattern from the text
        match = re.search(r'\d+(?:\.\d+)?', normalized_text)
        
        if not match:
            whatsapp_client.send_message(
                self.sender, 
                "⚠️ We couldn't detect a valid number. Please reply with the amount (e.g., 15.00) or *0* to cancel:"
            )
            return

        clean_amount_str = match.group()

        try:
            amount = float(clean_amount_str)
            if amount <= 0 or amount > 10000:
                raise ValueError
        except ValueError:
            whatsapp_client.send_message(
                self.sender, 
                "⚠️ Please enter a valid positive amount between $1 and $10,000 (e.g., 15.00) or reply *0* to cancel:"
            )
            return

        context = dict(self.session.context_data)
        context['amount'] = amount
        self.session.context_data = context
        self.session.current_state = "AWAITING_PAYMENT_METHOD"
        self.db.commit()

        menu = (
            f"You are about to recharge USD {amount:.2f}.\n"
            "Choose a payment method to finish this transaction:\n\n"
            "1️⃣ EcoCash\n"
            "2️⃣ InnBucks\n"
            "3️⃣ Paynow\n\n"
            "Reply with the number or *0* to cancel."
        )
        whatsapp_client.send_message(self.sender, menu)

    def _handle_payment_method(self):
        provider_map = {"1": PaymentProvider.ECOCASH, "2": PaymentProvider.INNBUCKS, "3": PaymentProvider.PAYNOW}
        
        if self.text not in provider_map:
            whatsapp_client.send_message(self.sender, "⚠️ Invalid choice. Reply 1 for EcoCash, 2 for InnBucks, 3 for Paynow, or 0 to cancel.")
            return

        provider = provider_map[self.text]
        
        context = dict(self.session.context_data)
        context['provider'] = provider.value
        self.session.context_data = context
        
        if provider == PaymentProvider.ECOCASH:
            self.session.current_state = "AWAITING_ECOCASH_NUMBER"
            self.db.commit()
            whatsapp_client.send_message(
                self.sender, 
                "📱 Please enter the EcoCash number you want to pay with (e.g., 0771234567):\n\nReply *0* to cancel."
            )
        else:
            msg = f"⏳ {provider.value} integration is coming soon! Please use EcoCash for now."
            self._reset_to_menu(msg)

    def _handle_awaiting_ecocash_number(self):
        ecocash_number = self.text.strip()
        
        if not ecocash_number.startswith(("077", "078")) or len(ecocash_number) != 10:
            whatsapp_client.send_message(self.sender, "⚠️ Invalid EcoCash number. Please enter a valid 10-digit number starting with 077 or 078:")
            return

        context = self.session.context_data
        meter_no = context.get('meter_no')
        amount = context.get('amount')
        provider = PaymentProvider.ECOCASH
        ref_num = generate_ref()

        transaction = TransactionRecord(
            reference_number=ref_num,
            whatsapp_num=self.sender,
            meter_number=meter_no,
            amount_usd=amount,
            provider=provider
        )
        self.db.add(transaction)
        self.db.commit()

        whatsapp_client.send_message(self.sender, "⏳ Connecting to EcoCash, please wait...")
        
        # NOTE: While testing in Paynow Sandbox, enter 0771111111 when prompted in WhatsApp!
        payment_response = payment_service.trigger_ecocash_payment(ecocash_number, amount, ref_num)
        
        if payment_response["status"] == "success":
            msg = (
                f"✅ Payment Initiated!\n\n"
                f"Ref: {ref_num}\n"
                f"Amount: USD {amount:.2f}\n\n"
                f"📱 *Check the phone ({ecocash_number}) right now!* A prompt has been sent. Enter your PIN to complete the transaction."
            )
        else:
            msg = f"❌ Sorry, the EcoCash network failed to respond: {payment_response.get('error_msg')}"
            
        self._reset_to_menu(msg)

    def _reset_to_menu(self, message: str):
        """Clears the user session data and sets the state back to MAIN_MENU."""
        self.session.current_state = "MAIN_MENU"
        self.session.context_data = {}
        # Update the timestamp so the 15-minute clock restarts
        self.session.updated_at = datetime.datetime.utcnow() 
        self.db.commit()
        whatsapp_client.send_message(self.sender, message)