import tkinter as tk
from tkinter import ttk, messagebox
import math
import requests
import json

WEBHOOK_URL = "http://127.0.0.1:5000/webhook"


class TradeEntryApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Randle Entry Panel")
        self.root.geometry("520x520")
        self.root.resizable(False, False)

        self.symbol_var = tk.StringVar(value="MNQ")
        self.direction_var = tk.StringVar(value="long")
        self.contracts_var = tk.StringVar(value="2")
        self.atr_var = tk.StringVar(value="")
        self.entry_price_var = tk.StringVar(value="")

        self.build_ui()

    def build_ui(self):
        main = ttk.Frame(self.root, padding=16)
        main.pack(fill="both", expand=True)

        title = ttk.Label(main, text="Randle Entry Panel", font=("Segoe UI", 16, "bold"))
        title.pack(anchor="w", pady=(0, 12))

        form = ttk.Frame(main)
        form.pack(fill="x")

        # Symbol
        ttk.Label(form, text="Symbol").grid(row=0, column=0, sticky="w", pady=6)
        symbol_box = ttk.Combobox(
            form,
            textvariable=self.symbol_var,
            values=["MNQ", "M2K", "MES", "MGC", "NQ", "RTY", "ES", "GC"],
            state="readonly",
            width=18
        )
        symbol_box.grid(row=0, column=1, sticky="w", pady=6)

        # Direction
        ttk.Label(form, text="Direction").grid(row=1, column=0, sticky="w", pady=6)
        direction_frame = ttk.Frame(form)
        direction_frame.grid(row=1, column=1, sticky="w", pady=6)

        ttk.Radiobutton(direction_frame, text="Long", variable=self.direction_var, value="long").pack(side="left", padx=(0, 12))
        ttk.Radiobutton(direction_frame, text="Short", variable=self.direction_var, value="short").pack(side="left")

        # Contracts
        ttk.Label(form, text="Contracts").grid(row=2, column=0, sticky="w", pady=6)
        ttk.Entry(form, textvariable=self.contracts_var, width=20).grid(row=2, column=1, sticky="w", pady=6)

        # ATR
        ttk.Label(form, text="ATR (TV 1m, 14, RMA)").grid(row=3, column=0, sticky="w", pady=6)
        ttk.Entry(form, textvariable=self.atr_var, width=20).grid(row=3, column=1, sticky="w", pady=6)

        # Entry price
        ttk.Label(form, text="Entry Price").grid(row=4, column=0, sticky="w", pady=6)
        ttk.Entry(form, textvariable=self.entry_price_var, width=20).grid(row=4, column=1, sticky="w", pady=6)

        note = ttk.Label(
            main,
            text="ATR is rounded up automatically. Example: 11.25 -> 12",
            foreground="#555555"
        )
        note.pack(anchor="w", pady=(8, 12))

        preview_frame = ttk.LabelFrame(main, text="Calculated Trade Plan", padding=12)
        preview_frame.pack(fill="x", pady=(0, 12))

        self.preview_text = tk.Text(preview_frame, height=8, width=58)
        self.preview_text.pack(fill="x")
        self.preview_text.configure(state="disabled")

        button_frame = ttk.Frame(main)
        button_frame.pack(fill="x", pady=(0, 12))

        ttk.Button(button_frame, text="Preview", command=self.preview_trade).pack(side="left", padx=(0, 8))
        ttk.Button(button_frame, text="Submit Trade", command=self.submit_trade).pack(side="left", padx=(0, 8))
        ttk.Button(button_frame, text="Check State", command=self.check_state).pack(side="left", padx=(0, 8))
        ttk.Button(button_frame, text="Force Exit", command=self.force_exit).pack(side="left")

        log_frame = ttk.LabelFrame(main, text="Response Log", padding=12)
        log_frame.pack(fill="both", expand=True)

        self.log_text = tk.Text(log_frame, height=10, width=58)
        self.log_text.pack(fill="both", expand=True)

    def log(self, message):
        self.log_text.insert("end", message + "\n\n")
        self.log_text.see("end")

    def set_preview(self, message):
        self.preview_text.configure(state="normal")
        self.preview_text.delete("1.0", "end")
        self.preview_text.insert("1.0", message)
        self.preview_text.configure(state="disabled")

    def parse_inputs(self):
        symbol = self.symbol_var.get().strip().upper()
        direction = self.direction_var.get().strip().lower()

        if direction not in ("long", "short"):
            raise ValueError("Direction must be long or short.")

        try:
            contracts = float(self.contracts_var.get().strip())
        except ValueError:
            raise ValueError("Contracts must be numeric.")

        try:
            atr_raw = float(self.atr_var.get().strip())
        except ValueError:
            raise ValueError("ATR must be numeric.")

        try:
            entry_price = float(self.entry_price_var.get().strip())
        except ValueError:
            raise ValueError("Entry Price must be numeric.")

        if contracts <= 0:
            raise ValueError("Contracts must be greater than 0.")

        if atr_raw <= 0:
            raise ValueError("ATR must be greater than 0.")

        atr = math.ceil(atr_raw)

        if direction == "long":
            stop_price = entry_price - atr
            tp1_price = entry_price + atr
            be_trigger_price = entry_price + (atr / 2)
        else:
            stop_price = entry_price + atr
            tp1_price = entry_price - atr
            be_trigger_price = entry_price - (atr / 2)

        return {
            "symbol": symbol,
            "direction": direction,
            "position_size": contracts,
            "atr_raw": atr_raw,
            "atr_rounded": atr,
            "entry_price": entry_price,
            "stop_price": stop_price,
            "tp1_price": tp1_price,
            "be_trigger_price": be_trigger_price,
        }

    def preview_trade(self):
        try:
            trade = self.parse_inputs()
            preview = (
                f"Symbol: {trade['symbol']}\n"
                f"Direction: {trade['direction']}\n"
                f"Contracts: {trade['position_size']}\n"
                f"ATR raw: {trade['atr_raw']}\n"
                f"ATR rounded: {trade['atr_rounded']}\n"
                f"Entry Price: {trade['entry_price']}\n"
                f"Stop Price: {trade['stop_price']}\n"
                f"TP1 Price: {trade['tp1_price']}\n"
                f"BE Trigger: {trade['be_trigger_price']}\n"
            )
            self.set_preview(preview)
        except Exception as e:
            messagebox.showerror("Input Error", str(e))

    def submit_trade(self):
        try:
            trade = self.parse_inputs()

            payload = {
                "event": "enter_trade",
                "symbol": trade["symbol"],
                "direction": trade["direction"],
                "entry_price": trade["entry_price"],
                "stop_price": trade["stop_price"],
                "tp1_price": trade["tp1_price"],
                "be_trigger_price": trade["be_trigger_price"],
                "position_size": trade["position_size"],
            }

            response = requests.post(WEBHOOK_URL, json=payload, timeout=10)
            response.raise_for_status()

            data = response.json()
            self.log("ENTER TRADE SENT:")
            self.log(json.dumps(payload, indent=2))
            self.log("SERVER RESPONSE:")
            self.log(json.dumps(data, indent=2))

            if data.get("ok"):
                messagebox.showinfo("Success", "Trade submitted to Flask.")
            else:
                messagebox.showwarning("Warning", json.dumps(data, indent=2))

        except requests.RequestException as e:
            messagebox.showerror("Connection Error", f"Could not reach Flask app.\n\n{e}")
        except Exception as e:
            messagebox.showerror("Error", str(e))

    def check_state(self):
        try:
            payload = {"event": "state"}
            response = requests.post(WEBHOOK_URL, json=payload, timeout=10)
            response.raise_for_status()
            data = response.json()

            self.log("STATE RESPONSE:")
            self.log(json.dumps(data, indent=2))

        except requests.RequestException as e:
            messagebox.showerror("Connection Error", f"Could not reach Flask app.\n\n{e}")

    def force_exit(self):
        try:
            payload = {"event": "force_time_exit"}
            response = requests.post(WEBHOOK_URL, json=payload, timeout=10)
            response.raise_for_status()
            data = response.json()

            self.log("FORCE EXIT RESPONSE:")
            self.log(json.dumps(data, indent=2))

        except requests.RequestException as e:
            messagebox.showerror("Connection Error", f"Could not reach Flask app.\n\n{e}")


if __name__ == "__main__":
    root = tk.Tk()
    app = TradeEntryApp(root)
    root.mainloop()
