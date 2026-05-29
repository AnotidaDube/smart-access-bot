import requests

# This is the local URL of your FastAPI server
url = "http://127.0.0.1:8001/webhook/greenapi"

# This is the exact data structure Green API sends when someone texts "1"
fake_green_api_payload = {
    "typeWebhook": "incomingMessageReceived",
    "senderData": {
        "sender": "263783219519@c.us" # A fake phone number
    },
    "messageData": {
        "typeMessage": "textMessage",
        "textMessageData": {
            "textMessage": "303232303302" # Pretending the user selected option 1
        }
    }
}

print("Sending fake WhatsApp message to local server...")
try:
    response = requests.post(url, json=fake_green_api_payload)
    print(f"Server responded with status code: {response.status_code}")
    print(f"Response data: {response.json()}")
except Exception as e:
    print(f"Failed to connect: {e}")