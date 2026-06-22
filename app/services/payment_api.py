import logging
from paynow import Paynow
from app.config import settings

logger = logging.getLogger(__name__)

class PaymentGateway:
    def __init__(self):
        # Initialize Paynow using your centralized config settings
        integration_id = settings.PAYNOW_INTEGRATION_ID
        integration_key = settings.PAYNOW_INTEGRATION_KEY
        
        # Dynamically build the webhook URL from your settings.
        # This prevents hardcoding fragile Ngrok links.
        base_url = getattr(settings, 'SERVER_BASE_URL', 'http://127.0.0.1:8001').rstrip('/')
        webhook_url = f"{base_url}/webhook/paynow"
        
        self.paynow = Paynow(
            integration_id,
            integration_key,
            webhook_url, # Return URL
            webhook_url  # Result URL
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
                # Log the raw dictionary from Paynow for debugging
                logger.error(f"PAYNOW ERROR | RAW DATA: {response.data}")
                
                # Extract the specific error message provided by Paynow
                actual_error = response.data.get('error', 'Check server logs for details')
                
                return {
                    "status": "error",
                    "error_msg": actual_error
                }
                
        except Exception as e:
            logger.error(f"Payment System Error: {str(e)}")
            return {
                "status": "error",
                "error_msg": f"Internal System Error: {str(e)}"
            }

# Create a single instance to import elsewhere
payment_service = PaymentGateway()