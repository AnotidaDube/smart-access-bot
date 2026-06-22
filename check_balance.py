from app.services.meter_api import MeterManagementAPI

def run_balance_check():
    print("🔄 Logging into Zhongyi API...")
    client = MeterManagementAPI()
    
    # Ensure we are checking the LoRa database
    client.action = "lorawanMeter" 
    client.login()

    print("📡 Pulling meter records...")
    data = client._send_request(
        method_name="getAreaArchives",
        param_data={
            "pageNumber": "1",
            "pageSize": "1000",
            "areaId": client.area_id,
            "searchContent": "" 
        }
    )

    print("\n" + "="*40)
    for meter in data.get("values", []):
        if meter.get("serialnumber") == "20260610101500":
            print("🎉 SUCCESS! METER FOUND:")
            print(f"▶ Meter Number: {meter.get('serialnumber')}")
            print(f"▶ Cloud Balance: USD {meter.get('balance')}")
            print(f"▶ Valve Status: {meter.get('valveStatus')}")
            print("="*40 + "\n")
            return
            
    print("❌ Meter not found.")

if __name__ == "__main__":
    run_balance_check()