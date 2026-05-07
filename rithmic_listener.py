import time
from app import process_price_update

def handle_rithmic_price(price: float):
    response_body, status_code = process_price_update(price)
    print("RITHMIC PRICE:", price)
    print("RESULT:", response_body, status_code)

if __name__ == "__main__":
    print("Starting mock Rithmic listener...")

    test_prices = [69265, 69276, 69291]

    for price in test_prices:
        handle_rithmic_price(price)
        time.sleep(2)