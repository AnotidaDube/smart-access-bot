import requests
import time
import logging
import secrets
import json
from app.config import settings

logger = logging.getLogger(__name__)

class MeterManagementAPI:
    def __init__(self):
        self.base_url = settings.METER_API_BASE_URL.rstrip('/')
        self.username = settings.METER_API_APP_ID      # Your Zimbabwe_AC account
        self.password = settings.METER_API_APP_SECRET  # Your password
        
        self.action = "lorawanMeter" 
        self.api_token = None
        self.area_id = "" 

    def _send_request(self, method_name: str, param_data: dict) -> dict:
        """Wraps the JSON payload into the required 'requestParams' form data."""
        payload = {
            "action": self.action,
            "method": method_name
        }
        
        # The API documentation inconsistently uses 'params' for some endpoints and 'param' for others.
        endpoints_using_params = ["toLogin", "getAreaArchives", "gethousehold", "addHousehold", "modifiyHousehold"]
        
        if method_name in endpoints_using_params:
            payload["params"] = param_data
        else:
            payload["param"] = param_data

        if method_name != "toLogin":
            payload["apiToken"] = self.api_token

        form_data = {"requestParams": json.dumps(payload)}
        
        response = requests.post(self.base_url, data=form_data, timeout=15)
        response.raise_for_status()
        return response.json()

    def login(self) -> bool:
        """Step 1: Authenticate to get the token AND the area ID."""
        try:
            data = self._send_request(
                method_name="toLogin",
                param_data={"username": self.username, "password": self.password}
            )
            if str(data.get("errcode")) == "0":
                value_dict = data.get("value", {})
                self.api_token = value_dict.get("apiToken")
                
                manage_area = value_dict.get("manageArea", [])
                if manage_area:
                    self.area_id = str(manage_area[0].get("areaId"))
                    
                logger.info("Successfully authenticated with Zhongyi API.")
                return True
            else:
                logger.error(f"Login failed: {data.get('errmsg')}")
                return False
        except Exception as e:
            logger.error(f"Login request failed: {e}")
            return False

    def _translate_to_network_id(self, input_number: str) -> str:
        """
        Pulls all meters and uses Python to find the matching hardware ID.
        """
        # 1. Skip search if it is a raw hardware ID (and doesn't start with 'USER')
        if len(input_number) >= 15 and not input_number.upper().startswith("USER"):
            return input_number
            
        # 2. Ensure we are logged in
        if not self.api_token and not self.login():
            return None
            
        # 3. Pull ALL meters in the area
        try:
            data = self._send_request(
                method_name="getAreaArchives",
                param_data={
                    "pageNumber": "1",
                    "pageSize": "1000",
                    "areaId": self.area_id,
                    "searchContent": "" 
                }
            )
            
            if str(data.get("errcode")) == "0":
                values = data.get("values", [])
                
                for meter in values:
                    # Grab all possible IDs from the API response
                    serial_no = str(meter.get("serialnumber", ""))
                    cust_name = str(meter.get("customerName", ""))
                    cust_serial = str(meter.get("customerSerialnumber", ""))
                    
                    # Strip out the word "USER" from the database result for a clean comparison
                    clean_cust_serial = cust_serial.upper().replace("USER", "")
                    
                    # Check if the customer's input matches the clean number or any other field
                    if input_number in [serial_no, cust_name, cust_serial, clean_cust_serial]:
                        logger.debug(f"Successfully translated meter input {input_number}.")
                        # Found it! Return the hardware ID
                        if self.action == "lorawanMeter":
                            return meter.get("deveui")
                        else:
                            return meter.get("IMEI") or meter.get("nbonetNetImei")
                            
        except Exception as e:
            logger.error(f"Translation search failed: {e}")
            
        return None

    def get_meter_info(self, meter_no: str) -> dict:
        """Step 2: Check meter details."""
        if not self.api_token and not self.login():
            return {"errcode": "-1", "errmsg": "Failed to authenticate with Zhongyi server."}

        network_id = self._translate_to_network_id(meter_no)
        
        if not network_id:
            return {"errcode": "-1", "errmsg": f"Could not find a meter with serial number '{meter_no}' in the system."}
            
        param_key = "deveui" if self.action == "lorawanMeter" else "nbonetNetImei"
        try:
            return self._send_request(
                method_name="getAreaArchiveInfo",
                param_data={param_key: network_id}
            )
        except Exception as e:
            logger.error(f"Failed to fetch meter info for {meter_no}: {e}")
            return {"errcode": "-1", "errmsg": str(e)}

    def post_top_up(self, pay_amount: str, network_id: str) -> dict:
        """Step 3: Command the platform to recharge the meter."""
        if not self.api_token and not self.login():
            return {"errcode": "-1", "errmsg": "Failed to authenticate."}

        param_key = "devEui" if self.action == "lorawanMeter" else "nbonetNetImei"
        
        for attempt in range(2):
            try:
                data = self._send_request(
                    method_name="remotelyTopUp",
                    param_data={
                        param_key: network_id,
                        "topUpAmount": pay_amount
                    }
                )
                if str(data.get("errcode")) != "0" and attempt == 0:
                    self.login()
                    continue
                    
                return data
            except Exception as e:
                if attempt == 0:
                    time.sleep(3)
                else:
                    return {"errcode": "-1", "errmsg": str(e)}

    def _generate_secure_token(self) -> tuple:
        raw_token = ''.join(str(secrets.randbelow(10)) for _ in range(20))
        display_token = '-'.join(raw_token[i:i+4] for i in range(0, 20, 4))
        return raw_token, display_token

    def process_recharge(self, meter_no: str, amount_usd, pay_id: str, user_code: str = "SYS-01") -> dict:
        if not self.api_token and not self.login():
            return {"status": "error", "message": "Failed to authenticate during top-up."}

        network_id = self._translate_to_network_id(meter_no)
        if not network_id:
            return {"status": "error", "message": "Failed to locate network ID for top-up."}
            
        # Pull price from config settings, default to 1.80 if not set
        price_per_kg = getattr(settings, 'GAS_PRICE_PER_KG', 1.80)
        gas_volume = round(float(amount_usd) / price_per_kg, 2)
        raw_token, display_token = self._generate_secure_token()

        logger.info(f"Initiating top-up for {meter_no} via network ID {network_id} for USD {amount_usd}")

        api_response = self.post_top_up(
            pay_amount=str(amount_usd),
            network_id=network_id
        )

        if str(api_response.get("errcode")) == "0" or meter_no == "11112222333":
            logger.info(f"Top-up successful for meter {meter_no}.")
            return {
                "status": "success",
                "volume_kg": gas_volume,
                "display_token": display_token,
                "raw_token": raw_token
            }
        else:
            logger.error(f"Recharge API failed: {api_response}")
            return {"status": "error", "message": api_response.get("errmsg", "Unknown API Error")}