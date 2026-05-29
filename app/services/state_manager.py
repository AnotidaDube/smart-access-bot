from sqlalchemy.orm import Session
import datetime
import secrets
from app.models import UserSession, TransactionRecord, PaymentProvider
from app.services.green_api import GreenAPIClient
from app.services.meter_api import MeterManagementAPI

whatsapp_client = GreenAPIClient()
meter_client = MeterManagementAPI()

def generate_ref():
    """Generates a unique transaction reference."""
    date_str = datetime.datetime.utcnow().strftime("%Y%m%d")
    random_hex = secrets.token_hex(2).upper()
    return f"SAM-{date_str}-{random_hex}"

class ChatbotStateHandler:
    def __init__(self, db: Session, sender: str, text: str):
        self.db = db
        self.sender = sender
        self.text = text.strip()
        
        # Fetch or create the user session
        self.session = self.db.query(UserSession).filter_by(whatsapp_num=self.sender).first()
        if not self.session:
            self.session = UserSession(whatsapp_num=self.sender, current_state="MAIN_MENU", context_data={})
            self.db.add(self.session)
            self.db.commit()

    def process(self):
        state = self.session.current_state
        clean_text = self.text.lower()
        
        # Step 1: Global navigation. Always allow the user to cancel and go back to the start.
        # We include "0" here as the universal back button.
        if clean_text in ['0', 'cancel', 'menu', 'hi', 'hello']:
            self._reset_to_menu("Welcome back to Smart Access! ⚡\nHow can we help you today?")
            self._show_menu_options()
            return

        # Step 2: Route the user input to the correct handler based on their current state.
        if state == "MAIN_MENU":
            self._handle_main_menu()
        elif state == "AWAITING_METER":
            self._handle_awaiting_meter()
        elif state == "AWAITING_AMOUNT":
            self._handle_awaiting_amount()
        elif state == "AWAITING_PAYMENT_METHOD":
            self._handle_payment_method()
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
            # If they enter anything other than 1, show the menu again.
            self._show_menu_options()

    def _handle_awaiting_meter(self):
        meter_no = self.text
        whatsapp_client.send_message(self.sender, "Checking meter details, please wait...")
        
        # Verify with external API
        meter_info = meter_client.get_meter_info(meter_no)
        
        if meter_info.get("code") == "0": # Assuming 0 is success per API spec
            data = meter_info.get("data", {})
            name = data.get("userName", "Unknown")
            
            # Save meter to context and move to next step
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
            whatsapp_client.send_message(self.sender, "❌ Invalid meter number. Please try again or reply *0* to cancel.")

    def _handle_awaiting_amount(self):
        try:
            amount = float(self.text)
            if amount <= 0 or amount > 21474836.47:
                raise ValueError
        except ValueError:
            whatsapp_client.send_message(self.sender, "⚠️ Invalid amount. Please enter a valid number (e.g., 15.00) or reply *0* to cancel:")
            return

        # Save amount to context
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
        context = self.session.context_data
        meter_no = context.get('meter_no')
        amount = context.get('amount')
        ref_num = generate_ref()

        # Log pending transaction in database
        transaction = TransactionRecord(
            reference_number=ref_num,
            whatsapp_num=self.sender,
            meter_number=meter_no,
            amount_usd=amount,
            provider=provider
        )
        self.db.add(transaction)
        self.db.commit()

        # Alert the user
        msg = (
            f"⏳ Processing {provider.value} payment...\n"
            f"Amount: USD {amount:.2f}\n"
            f"Ref: {ref_num}\n\n"
            "Please check your phone for the PIN prompt. We will notify you once payment is received."
        )
        self._reset_to_menu(msg)

    def _reset_to_menu(self, message: str):
        """Clears the user session data and sets the state back to MAIN_MENU."""
        self.session.current_state = "MAIN_MENU"
        self.session.context_data = {}
        self.db.commit()
        whatsapp_client.send_message(self.sender, message)