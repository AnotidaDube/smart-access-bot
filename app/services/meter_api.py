import hashlib
import base64
import requests
import time
import logging
from datetime import datetime
from app.config import settings

logger = logging.getLogger(__name__)

class MeterManagementAPI:
    def __init__(self):
        self.base_url = settings.METER_API_BASE_URL.rstrip('/')
        self.app_id = settings.METER_API_APP_ID
        self.app_secret = settings.METER_API_APP_SECRET

    def _generate_headers(self) -> dict:
        """
        Generates the strict cryptographic headers required by the Access Corp API.
        """
        # Get current time in yyyyMMddHHmmss format
        current_time = datetime.now().strftime("%Y%m%d%H%M%S")
        
        # 1. Generate MD5 AccessToken: MD5(appId + appSecret + time)
        md5_string = f"{self.app_id}{self.app_secret}{current_time}"
        access_token = hashlib.md5(md5_string.encode('utf-8')).hexdigest()
        
        # 2. Generate Base64 Authorization: Base64(appId:time)
        auth_string = f"{self.app_id}:{current_time}"
        authorization = base64.b64encode(auth_string.encode('utf-8')).decode('utf-8')
        
        return {
            "Accept": "application/json",
            "Content-Type": "application/json;charset=utf-8",
            "AccessToken": access_token,
            "Authorization": authorization
        }

    def get_meter_info(self, meter_no: str) -> dict:
        """
        Fetches meter details (name, address, balance) before allowing payment.
        """
        url = f"{self.base_url}/meterInfo?meterNo={meter_no}"
        headers = self._generate_headers()
        
        try:
            response = requests.get(url, headers=headers, timeout=15)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            logger.error(f"Failed to fetch meter info for {meter_no}: {e}")
            return {"code": "ERROR", "message": str(e)}

    def post_top_up(self, pay_id: str, pay_time: str, pay_amount: str, meter_no: str, user_code: str) -> dict:
        """
        Logs a successful payment to the Meter Management System.
        Includes the mandatory 30-second retry logic if the first attempt fails.
        """
        url = f"{self.base_url}/topUp"
        payload = {
            "payId": pay_id,
            "payTime": pay_time,
            "payAmount": pay_amount,
            "meterNo": meter_no,
            "userCode": user_code
        }
        
        for attempt in range(2): # Try once, then retry once
            headers = self._generate_headers() # Regenerate headers for accurate timestamp
            try:
                response = requests.post(url, json=payload, headers=headers, timeout=15)
                response.raise_for_status()
                return response.json()
                
            except requests.exceptions.RequestException as e:
                logger.error(f"Attempt {attempt + 1} failed to post top-up for {meter_no}: {e}")
                if attempt == 0:
                    logger.info("Waiting 30 seconds before retrying as per specification...")
                    time.sleep(30)
                else:
                    return {"code": "ERROR", "message": str(e)}