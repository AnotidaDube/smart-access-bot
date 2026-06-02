import os
from paynow import Paynow
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

class PaymentGateway:
    def __init__(self):
        # Initialize Paynow with your keys from .env
        integration_id = os.getenv("PAYNOW_INTEGRATION_ID")
        integration_key = os.getenv("PAYNOW_INTEGRATION_KEY")
        
        # We set return and result URLs. In production, your FastAPI server will 
        # receive background updates here when a user types in their PIN.
        # Replace the example.com URLs with your active Ngrok URL + /webhook/paynow
        self.paynow = Paynow(
            integration_id,
            integration_key,
            "https://disposal-bodacious-slug.ngrok-free.de/webhook/paynow", # Return URL
            "https://disposal-bodacious-slug.ngrok-free.dev/webhook/paynow"  # Result URL
        )

    def trigger_ecocash_payment(self, phone_number: str, amount: float, reference: str):
        """Sends an STK push (PIN prompt) to the user's phone."""
        
        try:
            payment = self.paynow.create_payment(reference, "dubeanotida5@gmail.com")
            payment.add("Smart Access Gas Recharge", amount)
            
            # Send the mobile payment request
            response = self.paynow.send_mobile(payment, phone_number, 'ecocash')
            
            if response.success:
                return {
                    "status": "success",
                    "poll_url": response.poll_url,
                    "instructions": response.instructions
                }
            else:
                # Log the raw dictionary from Paynow to your VS Code terminal
                print(f"========== PAYNOW ERROR ==========")
                print(f"RAW DATA: {response.data}")
                print(f"==================================")
                
                # Extract the specific error message provided by Paynow
                actual_error = response.data.get('error', 'Check VS Code terminal for details')
                
                return {
                    "status": "error",
                    "error_msg": actual_error
                }
                
        except Exception as e:
            # Catch Python crashes (e.g., missing keys, network timeouts)
            print(f"SYSTEM ERROR: {str(e)}")
            return {
                "status": "error",
                "error_msg": f"Internal System Error: {str(e)}"
            }

# Create a single instance to import elsewhere
payment_service = PaymentGateway()