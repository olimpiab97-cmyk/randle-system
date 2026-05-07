import time
import random
import requests

URL = "http://127.0.0.1:5000/webhook"

def simulate_market(start_price=69250):
    price = start_price

    while True:
        move = random.randint(-5, 5)
        price += move

        payload = {
            "event": "price_update",
            "price": price
        }

        response = requests.post(URL, json=payload)

        print(f"\nPRICE: {price}")
        print("RESPONSE:", response.json())

        time.sleep(0.5)

if __name__ == "__main__":
    print("🚀 Simulating market → webhook...")
    simulate_market()