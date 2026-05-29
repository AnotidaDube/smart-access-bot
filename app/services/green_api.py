import requests
import logging
from app.config import settings

logger = logging.getLogger(__name__)

class GreenAPIClient:
    def __init__(self):
        self.instance_id = settings.GREEN_API_INSTANCE_ID
        self.token = settings.GREEN_API_TOKEN
        self.base_url = f"https://api.greenapi.com/waInstance{self.instance_id}"

    def send_message(self, chat_id: str, message: str):
        """Sends a text message back to the WhatsApp user."""
        url = f"{self.base_url}/sendMessage/{self.token}"
        payload = {
            "chatId": chat_id,
            "message": message
        }
        try:
            response = requests.post(url, json=payload, timeout=10)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            logger.error(f"Failed to send message to {chat_id}: {e}")
            return None