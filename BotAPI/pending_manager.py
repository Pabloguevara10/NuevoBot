import tkinter as tk
from tkinter import messagebox
import csv
import os
import threading
import time

class PendingOrderManager:
    def __init__(self, config):
        self.cfg = config
        self.orders = [] 
        self._load_orders()
        self.lock = threading.Lock()

    def _load_orders(self):
        if not os.path.exists(self.cfg.PENDING_ORDERS_FILE): return
        try:
            with open(self.cfg.PENDING_ORDERS_FILE, 'r') as f:
                reader = csv.DictReader(f)
                self.orders = []
                for row in reader:
                    if row['active'] == 'True':
                        self.orders.append({
                            'id': int(row['id']),
                            'type': row['type'],
                            'price': float(row['price']),
                            'amount': float(row['amount']),
                            'dist_pct': float(row.get('dist_pct', self.cfg.DEFAULT_PENDING_DIST_PCT)),
                            'active': True,
                            'strategy': row['strategy']
                        })
        except: self.orders = []

    def _save_orders(self):
        with open(self.cfg.PENDING_ORDERS_FILE, 'w', newline='') as f:
            writer = csv.DictWriter(f, fieldnames=['id', 'type', 'price', 'amount', 'dist_pct', 'active', 'strategy'])
            writer.writeheader()
            writer.writerows(self.orders)

    def abrir_ventana_input(self):
        t = threading.Thread(target=self._gui_thread)
        t.start()

    def _gui_thread(self):
        root = tk.Tk()
        root.title("Gestor de Órdenes Pendientes")
        root.geometry("350x320")
        root.attributes("-topmost", True)
        root.configure(bg="#f0f0f0")

        lbl_font = ("Arial", 10, "bold")
        ent_bg = "#ffffff"

        frame = tk.Frame(root, bg="#f0f0f0", padx=20, pady=20)
        frame.pack(expand=True, fill="both")

        tk.Label(frame, text="Tipo de Orden:", bg="#f0f0f0", font=lbl_font).grid(row=0, column=0, sticky="w", pady=5)
        v_type = tk.StringVar(value="LONG")
        tk.OptionMenu(frame, v_type, "LONG", "SHORT").grid(row=0, column=1, sticky="e")

        tk.Label(frame, text="Precio Disparo (USDT):", bg="#f0f0f0", font=lbl_font).grid(row=1, column=0, sticky="w", pady=5)
        e_price = tk.Entry(frame, bg=ent_bg)
        e_price.grid(row=1, column=1)

        tk.Label(frame, text="Capital (USDT):", bg="#f0f0f0", font=lbl_font).grid(row=2, column=0, sticky="w", pady=5)
        e_amount = tk.Entry(frame, bg=ent_bg)
        e_amount.grid(row=2, column=1)

        tk.Label(frame, text="Distancia Activación (%):", bg="#f0f0f0", font=lbl_font).grid(row=3, column=0, sticky="w", pady=5)
        e_dist = tk.Entry(frame, bg=ent_bg)
        e_dist.insert(0, str(self.cfg.DEFAULT_PENDING_DIST_PCT))
        e_dist.grid(row=3, column=1)

        def save():
            try:
                price = float(e_price.get())
                amt = float(e_amount.get())
                dist = float(e_dist.get())
                side = v_type.get()
                
                new_order = {
                    'id': int(time.time()),
                    'type': side,
                    'price': price,
                    'amount': amt,
                    'dist_pct': dist,
                    'active': True,
                    'strategy': 'PENDING_LIMIT'
                }
                
                with self.lock:
                    self.orders.append(new_order)
                    self._save_orders()
                
                messagebox.showinfo("Éxito", f"Orden {side} @ {price} Guardada.\nQuedará en espera.")
                root.destroy()
            except ValueError:
                messagebox.showerror("Error", "Por favor ingresa números válidos.")

        tk.Button(frame, text="💾 GUARDAR EN COLA", command=save, bg="#008000", fg="white", font=("Arial", 10, "bold"), height=2).grid(row=5, column=0, columnspan=2, pady=20, sticky="we")
        
        root.mainloop()

    def verificar_proximidad(self, precio_actual):
        with self.lock:
            for order in self.orders:
                if not order['active']: continue
                dist_pct = abs(precio_actual - order['price']) / precio_actual * 100
                if dist_pct <= order['dist_pct']:
                    return order
        return None

    def desactivar_orden(self, order_id):
        with self.lock:
            for order in self.orders:
                if order['id'] == int(order_id):
                    order['active'] = False
            self._save_orders()
            self.orders = [o for o in self.orders if o['active']]