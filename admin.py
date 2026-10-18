import tkinter as tk
from tkinter import messagebox
from datetime import datetime
from pathlib import Path
import threading
import urllib.request
import urllib.parse
import json
import os
import sys
import subprocess

# Демонстрационная касса самообслуживания.
# Цены примерные, оплата не настоящая.

BG = "#f2f6f1"
GREEN = "#168447"
DARK_GREEN = "#086333"
LIGHT_GREEN = "#e3f3e7"
WHITE = "#ffffff"
TEXT = "#243329"
GRAY = "#718078"
RED = "#d93838"
CARD = "#ffffff"

BASE_DIR = Path(__file__).resolve().parent
ASSETS_DIR = BASE_DIR / "assets"
ASSETS_DIR.mkdir(exist_ok=True)

PRODUCTS = {
    "Хлеб пшеничный": {"price": 59.90, "barcode": "1001", "emoji": "🍞", "image": "bread.jpg", "query": "loaf of white bread"},
    "Молоко 3,2%": {"price": 99.90, "barcode": "1002", "emoji": "🥛", "image": "milk.jpg", "query": "carton of milk"},
    "Бананы": {"price": 139.90, "barcode": "1003", "emoji": "🍌", "image": "bananas.jpg", "query": "yellow bananas bunch"},
    "Яблоки": {"price": 179.90, "barcode": "1004", "emoji": "🍎", "image": "apples.jpg", "query": "red apples fruit"},
    "Сыр российский": {"price": 349.90, "barcode": "1005", "emoji": "🧀", "image": "cheese.jpg", "query": "yellow cheese block"},
    "Вода 1,5 л": {"price": 69.90, "barcode": "1006", "emoji": "💧", "image": "water.jpg", "query": "bottle of mineral water"},
    "Шоколад": {"price": 119.90, "barcode": "1007", "emoji": "🍫", "image": "chocolate.jpg", "query": "chocolate bar"},
    "Кофе": {"price": 499.90, "barcode": "1008", "emoji": "☕", "image": "coffee.jpg", "query": "jar of instant coffee"},
    "Печенье": {"price": 129.90, "barcode": "1009", "emoji": "🍪", "image": "cookies.jpg", "query": "cookies biscuits package"},
    "Сок 1 л": {"price": 149.90, "barcode": "1010", "emoji": "🧃", "image": "juice.jpg", "query": "carton of orange juice"},
    "Яйца 10 шт.": {"price": 109.90, "barcode": "1011", "emoji": "🥚", "image": "eggs.jpg", "query": "carton of eggs"},
    "Макароны": {"price": 79.90, "barcode": "1012", "emoji": "🍝", "image": "pasta.jpg", "query": "package of dry pasta"},
}

cart = []
image_refs = {}
product_buttons = {}
image_status = {}
closing = False

def money(value):
    return f"{value:,.2f}".replace(",", " ").replace(".", ",") + " ₽"

def load_image_bytes(url, timeout=8):
    request = urllib.request.Request(
        url,
        headers={"User-Agent": "Mozilla/5.0 SelfCheckoutDemo/1.0"}
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        data = response.read()
    if not data or len(data) > 12_000_000:
        raise ValueError("Invalid image")
    return data

def image_candidates(query):
    # Wikimedia Commons search API: images are fetched on demand.
    api = "https://commons.wikimedia.org/w/api.php?"
    params = urllib.parse.urlencode({
        "action": "query",
        "generator": "search",
        "gsrsearch": "filetype:bitmap " + query,
        "gsrnamespace": 6,
        "gsrlimit": 8,
        "prop": "imageinfo",
        "iiprop": "url",
        "iiurlwidth": 320,
        "format": "json"
    })
    url = api + params
    request = urllib.request.Request(
        url, headers={"User-Agent": "SelfCheckoutDemo/1.0 (Tkinter app)"}
    )
    with urllib.request.urlopen(request, timeout=10) as response:
        payload = json.loads(response.read().decode("utf-8"))
    pages = payload.get("query", {}).get("pages", {})
    results = []
    for page in pages.values():
        info = page.get("imageinfo", [{}])[0]
        candidate = info.get("thumburl") or info.get("url")
        if candidate and candidate.lower().split("?")[0].endswith(
            (".jpg", ".jpeg", ".png", ".webp")
        ):
            results.append(candidate)
    return results

def download_product_image(name, details):
    destination = ASSETS_DIR / details["image"]
    if destination.exists() and destination.stat().st_size > 0:
        return destination
    try:
        for url in image_candidates(details["query"]):
            try:
                data = load_image_bytes(url)
                # Tkinter PhotoImage supports PNG/GIF/PPM; use macOS sips
                # to convert downloaded JPEG/WEBP to PNG when available.
                temp = ASSETS_DIR / (details["image"] + ".download")
                temp.write_bytes(data)
                converted = ASSETS_DIR / (details["image"] + ".png")
                try:
                    subprocess.run(
                        ["sips", "-s", "format", "png", str(temp), "--out", str(converted)],
                        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                        check=True, timeout=10
                    )
                    temp.unlink(missing_ok=True)
                    return converted
                except Exception:
                    temp.unlink(missing_ok=True)
                    # If the original can be loaded by Tkinter, retain it.
                    if url.lower().split("?")[0].endswith(".png"):
                        destination.write_bytes(data)
                        return destination
            except Exception:
                continue
    except Exception:
        pass
    return None

def money_total():
    return sum(item["price"] for item in cart)

def add_product(name):
    product = PRODUCTS[name]
    cart.append({
        "name": name,
        "price": product["price"],
        "barcode": product["barcode"]
    })
    update_cart()
    status_label.config(text=f"✓ Добавлено: {name}", fg=GREEN)

def scan_barcode(event=None):
    code = barcode_entry.get().strip()
    barcode_entry.delete(0, tk.END)
    for name, product in PRODUCTS.items():
        if product["barcode"] == code:
            add_product(name)
            return
    status_label.config(text="Штрихкод не найден", fg=RED)

def update_cart():
    cart_list.delete(0, tk.END)
    for i, item in enumerate(cart, start=1):
        cart_list.insert(tk.END, f'{i}. {item["name"]} — {money(item["price"])}')
    total_label.config(text=money(money_total()))
    count_label.config(text=f"Товаров в корзине: {len(cart)}")

def remove_selected():
    selection = cart_list.curselection()
    if not selection:
        messagebox.showinfo("Корзина", "Выберите товар.")
        return
    del cart[selection[0]]
    update_cart()
    status_label.config(text="Товар удалён", fg=GREEN)

def clear_cart():
    if not cart:
        return
    if messagebox.askyesno("Очистить корзину", "Удалить все товары из корзины?"):
        cart.clear()
        update_cart()
        status_label.config(text="Корзина очищена", fg=GREEN)

def show_receipt(receipt):
    window = tk.Toplevel(root)
    window.title("Чек покупки")
    window.configure(bg=WHITE)
    window.geometry("460x650")
    tk.Label(window, text="ЧЕК ПОКУПКИ", font=("Arial", 20, "bold"),
             bg=WHITE, fg=GREEN).pack(pady=15)
    text_box = tk.Text(window, font=("Courier New", 12), bg=WHITE,
                       fg=TEXT, padx=15, pady=15, wrap="word")
    text_box.pack(fill="both", expand=True, padx=15)
    text_box.insert("1.0", receipt)
    text_box.config(state="disabled")

    def save_receipt():
        filename = "cheque_" + datetime.now().strftime("%Y%m%d_%H%M%S") + ".txt"
        path = BASE_DIR / filename
        path.write_text(receipt, encoding="utf-8")
        messagebox.showinfo("Чек сохранён", f"Файл создан:\n{path}")

    buttons = tk.Frame(window, bg=WHITE)
    buttons.pack(pady=12)
    tk.Button(buttons, text="СОХРАНИТЬ ЧЕК", command=save_receipt,
              bg=GREEN, fg=WHITE, font=("Arial", 12, "bold"),
              relief="flat", padx=15, pady=10).pack(side="left", padx=5)
    tk.Button(buttons, text="ЗАКРЫТЬ", command=window.destroy,
              bg=LIGHT_GREEN, fg=TEXT, font=("Arial", 12, "bold"),
              relief="flat", padx=15, pady=10).pack(side="left", padx=5)

def pay():
    if not cart:
        messagebox.showinfo("Оплата", "Сначала добавьте товары в корзину.")
        return
    amount = money_total()
    if not messagebox.askyesno(
        "Подтверждение",
        f"Итого к оплате: {money(amount)}\n\nВыполнить демонстрационную оплату?"
    ):
        return
    lines = [
        "       МАГАЗИН",
        "  КАССА САМООБСЛУЖИВАНИЯ",
        "=" * 34,
        datetime.now().strftime("%d.%m.%Y %H:%M:%S"),
        "-" * 34
    ]
    for item in cart:
        lines += [item["name"], "   " + money(item["price"])]
    lines += [
        "-" * 34, f"ТОВАРОВ: {len(cart)}", f"ИТОГО: {money(amount)}",
        "", "ОПЛАТА: ДЕМО-РЕЖИМ", "ДЕНЬГИ НЕ СПИСЫВАЛИСЬ",
        "", "Спасибо за покупку!", "=" * 34
    ]
    show_receipt("\n".join(lines))
    cart.clear()
    update_cart()
    status_label.config(text="✓ Демонстрационная оплата завершена", fg=GREEN)

def toggle_fullscreen(event=None):
    root.attributes("-fullscreen", not root.attributes("-fullscreen"))

def exit_app(event=None):
    root.destroy()

def make_placeholder(parent, emoji, width=150, height=94):
    # Native Tkinter fallback; no external image library needed.
    canvas = tk.Canvas(parent, width=width, height=height,
                       bg="#f6faf6", highlightthickness=0)
    canvas.create_text(width // 2, height // 2, text=emoji, font=("Arial", 44))
    return canvas

def set_product_image(name, path):
    if not path or not path.exists():
        return
    try:
        photo = tk.PhotoImage(file=str(path))
        # Keep image size reasonable for the product cards.
        factor = max(1, (photo.width() + 159) // 160, (photo.height() + 99) // 100)
        if factor > 1:
            photo = photo.subsample(factor, factor)
        image_refs[name] = photo
        widget = product_buttons.get(name)
        if widget and widget.winfo_exists():
            widget.configure(image=photo, compound="top")
            widget.image = photo
            image_status[name] = True
    except Exception:
        pass

def start_image_downloads():
    def worker():
        for name, details in PRODUCTS.items():
            path = download_product_image(name, details)
            if path:
                try:
                    root.after(0, lambda n=name, p=path: set_product_image(n, p))
                except RuntimeError:
                    return
    threading.Thread(target=worker, daemon=True).start()

# Main window
root = tk.Tk()
root.title("Касса самообслуживания")
root.configure(bg=BG)
root.attributes("-fullscreen", True)
root.minsize(900, 650)

header = tk.Frame(root, bg=GREEN, height=82)
header.pack(fill="x")
header.pack_propagate(False)

# Text-based brand treatment; not an official logo.
logo = tk.Frame(header, bg=GREEN)
logo.pack(side="left", padx=24, pady=10)
tk.Label(logo, text="✚", font=("Arial", 30, "bold"),
         bg=GREEN, fg=WHITE).pack(side="left", padx=(0, 8))
tk.Label(logo, text="ПЕРЕКРЁСТОК", font=("Arial", 25, "bold"),
         bg=GREEN, fg=WHITE).pack(side="left")
tk.Label(header, text="КАССА САМООБСЛУЖИВАНИЯ",
         font=("Arial", 16, "bold"), bg=GREEN, fg=WHITE).pack(side="right", padx=26)

main = tk.Frame(root, bg=BG)
main.pack(fill="both", expand=True, padx=18, pady=14)

catalog = tk.Frame(main, bg=BG)
catalog.pack(side="left", fill="both", expand=True, padx=(0, 15))
tk.Label(catalog, text="Выберите товары", font=("Arial", 22, "bold"),
         bg=BG, fg=TEXT).pack(anchor="w", pady=(0, 10))

grid = tk.Frame(catalog, bg=BG)
grid.pack(fill="both", expand=True)

for i, (name, product) in enumerate(PRODUCTS.items()):
    frame = tk.Frame(grid, bg=CARD, highlightbackground="#d6e2d8",
                     highlightthickness=1)
    frame.grid(row=i // 3, column=i % 3, sticky="nsew", padx=5, pady=5)
    frame.grid_propagate(False)

    placeholder = make_placeholder(frame, product["emoji"])
    placeholder.pack(pady=(7, 0))

    tk.Label(frame, text=name, font=("Arial", 12, "bold"),
             bg=CARD, fg=TEXT, wraplength=170).pack(pady=(4, 1))
    tk.Label(frame, text=money(product["price"]), font=("Arial", 13, "bold"),
             bg=CARD, fg=GREEN).pack(pady=(0, 3))
    button = tk.Button(frame, text="ДОБАВИТЬ", command=lambda n=name: add_product(n),
                       font=("Arial", 10, "bold"), bg=LIGHT_GREEN, fg=DARK_GREEN,
                       activebackground=GREEN, activeforeground=WHITE,
                       relief="flat", pady=5)
    button.pack(fill="x", padx=8, pady=(0, 8))
    product_buttons[name] = placeholder

for col in range(3):
    grid.columnconfigure(col, weight=1, uniform="catalogcol")
for row in range(4):
    grid.rowconfigure(row, weight=1, uniform="catalogrow")

side = tk.Frame(main, bg=WHITE, width=370)
side.pack(side="right", fill="y")
side.pack_propagate(False)

tk.Label(side, text="Ваша корзина", font=("Arial", 21, "bold"),
         bg=WHITE, fg=TEXT).pack(anchor="w", padx=16, pady=(17, 5))
count_label = tk.Label(side, text="Товаров в корзине: 0",
                       font=("Arial", 12), bg=WHITE, fg=GRAY)
count_label.pack(anchor="w", padx=16, pady=(0, 8))

cart_list = tk.Listbox(side, font=("Arial", 11), bg="#f7faf7", fg=TEXT,
                       selectbackground=GREEN, selectforeground=WHITE,
                       relief="flat", bd=0, highlightthickness=0)
cart_list.pack(fill="both", expand=True, padx=12, pady=5)

tk.Button(side, text="Удалить выбранный товар", command=remove_selected,
          font=("Arial", 11, "bold"), bg=LIGHT_GREEN, fg=DARK_GREEN,
          relief="flat", pady=9).pack(fill="x", padx=12, pady=(8, 4))
tk.Button(side, text="Очистить корзину", command=clear_cart,
          font=("Arial", 11), bg="#fceaea", fg=RED,
          relief="flat", pady=8).pack(fill="x", padx=12, pady=4)

tk.Label(side, text="К оплате", font=("Arial", 13), bg=WHITE, fg=GRAY).pack(pady=(14, 0))
total_label = tk.Label(side, text="0,00 ₽", font=("Arial", 29, "bold"),
                       bg=WHITE, fg=GREEN)
total_label.pack(pady=5)
tk.Button(side, text="ОПЛАТИТЬ", command=pay, font=("Arial", 18, "bold"),
          bg=GREEN, fg=WHITE, activebackground=DARK_GREEN,
          activeforeground=WHITE, relief="flat", pady=14).pack(fill="x", padx=12, pady=(8, 15))

footer = tk.Frame(root, bg=WHITE)
footer.pack(fill="x", side="bottom")
tk.Label(footer, text="ШТРИХКОД", font=("Arial", 12, "bold"),
         bg=WHITE, fg=TEXT).pack(side="left", padx=(18, 8), pady=12)
barcode_entry = tk.Entry(footer, font=("Arial", 15), width=15, relief="solid", bd=1)
barcode_entry.pack(side="left", ipady=5, pady=8)
barcode_entry.bind("<Return>", scan_barcode)
tk.Button(footer, text="СКАНИРОВАТЬ", command=scan_barcode,
          font=("Arial", 11, "bold"), bg=GREEN, fg=WHITE,
          relief="flat", padx=12, pady=9).pack(side="left", padx=8, pady=7)
status_label = tk.Label(footer, text="Готово к работе", font=("Arial", 11),
                        bg=WHITE, fg=GRAY)
status_label.pack(side="left", padx=8)
tk.Label(footer, text="F11 — экран  |  Esc — оконный режим",
         font=("Arial", 9), bg=WHITE, fg=GRAY).pack(side="right", padx=16)

root.bind("<F11>", toggle_fullscreen)
root.bind("<Escape>", lambda event: root.attributes("-fullscreen", False))
root.bind("<Control-q>", exit_app)
barcode_entry.focus_set()

# Download product photos in the background; fallback emojis remain visible.
start_image_downloads()
root.mainloop()
