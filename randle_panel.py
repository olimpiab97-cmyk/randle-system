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

        ttk.Label(form, text="Symbol").grid(row=0, column=0, sticky="w", pady=6)
        symbol_box = ttk.Combobox(
            form,
            textvariable=self.symbol_var,
            values=["MNQ", "M2K", "MES", "MGC", "NQ", "RTY", "ES", "GC"],
            state="readonly",
            width=18
        )
        symbol_box.grid(row=0, column=1, sticky="w", pady=6)

        ttk.Label(form, text="Direction").grid(row=1, column=0, sticky="w", pady=6)
        direction_frame = ttk.Frame(form)
        direction_frame.grid(row=1, column=1, sticky="w", pady=6)

        ttk.Radiobutton(direction_frame, text="Long", variable=self.direction_var, value="long").pack(side="left", padx=(0, 12))
        ttk.Radiobutton(direction_frame, text="Short", variable=self.direction_var, value="short").pack(side="left")

        ttk.Label(form, text="Contracts").grid(row=2, column=0, sticky="w", pady=6)
        ttk.Entry(form, textvariable=self.contracts_var, width=20).grid(row=2, column=1, sticky="w", pady=6)

        ttk.Label(form, text="ATR (1m)").grid(row=3, column=0, sticky="w", pady=6)
        ttk.Entry(form, textvariable=self.atr_var, width=20).grid(row=3, column=1, sticky="w", pady=6)

        ttk.Label(form, text="Entry Price").grid(row=4, column=0, sticky="w", pady=6)
        ttk.Entry(form, textvariable=self.entry_price_var, width=20).grid(row=4, column=1, sticky="w", pady=6)

        preview_frame = ttk.LabelFrame(main, text="Trade Plan", padding=12)
        preview_frame.pack(fill="x", pady=(10, 12))

        self.preview_text = tk.Text(preview_frame, height=6)
        self.preview_text.pack(fill="x")
        self.preview_text.configure(state="disabled")

        button_frame = ttk.Frame(main)
        button_frame.pack(fill="x", pady=(0, 12))

        ttk.Button(button_frame, text="Preview", command=self.preview_trade).pack(side="left", padx=5)
        ttk.Button(button_frame, text="Submit Trade", command=self.submit_trade).pack(side="left", padx=5)
        ttk.Button(button_frame, text="Check State", command=self.check_state).pack(side="left", padx=5)
        ttk.Button(button_frame, text="Force Exit", command=self.force_exit).pack(side="left", padx=5)

        log_frame = ttk.LabelFrame(main, text="Log", padding=12)
        log_frame.pack(fill="both", expand=True)

        self.log_text = tk.Text(log_frame)
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
        symbol = self.symbol_var.get().upper()
        direction = self.direction_var.get()

        contracts = float(self.contracts_var.get())
        atr = math.ceil(float(self.atr_var.get()))
        entry = float(self.entry_price_var.get())

        if direction == "long":
            stop = entry - atr
            tp1 = entry + atr
            be = entry + (atr / 2)
        else:
            stop = entry + atr
            tp1 = entry - atr
            be = entry - (atr / 2)

        return symbol, direction, contracts, entry, stop, tp1, be

    def preview_trade(self):
        try:
            symbol, direction, contracts, entry, stop, tp1, be = self.parse_inputs()
            text = f"{symbol} {direction}\nEntry: {entry}\nStop: {stop}\nTP1: {tp1}\nBE: {be}"
            self.set_preview(text)
        except Exception as e:
            messagebox.showerror("Error", str(e))

    def submit_trade(self):
        try:
            symbol, direction, contracts, entry, stop, tp1, be = self.parse_inputs()

            payload = {
                "event": "enter_trade",
                "symbol": symbol,
                "direction": direction,
                "entry_price": entry,
                "stop_price": stop,
                "tp1_price": tp1,
                "be_trigger_price": be,
                "position_size": contracts,
            }

            r = requests.post(WEBHOOK_URL, json=payload)
            self.log("SENT:\n" + json.dumps(payload, indent=2))
            self.log("RESPONSE:\n" + r.text)

        except Exception as e:
            messagebox.showerror("Error", str(e))

    def check_state(self):
        r = requests.post(WEBHOOK_URL, json={"event": "state"})
        self.log(r.text)

    def force_exit(self):
        r = requests.post(WEBHOOK_URL, json={"event": "force_time_exit"})
        self.log(r.text)


if __name__ == "__main__":
    root = tk.Tk()
    app = TradeEntryApp(root)
    root.mainloop()
