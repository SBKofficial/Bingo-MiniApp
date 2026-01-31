import telebot
from telebot.types import InlineQueryResultArticle, InputTextMessageContent, InlineKeyboardMarkup, InlineKeyboardButton, LinkPreviewOptions
import requests
import logging
import uuid
import time
from datetime import datetime
import json
import urllib.parse 

# ==========================================
# 1. CONFIGURATION
# ==========================================
BOT_TOKEN = "8266741813:AAEsSvUIQhdDVKudeBck28QOFpnuk2rTSzA"
GROUP_LINK = "https://t.me/traders_chat_group"

# Enable logs
telebot.logger.setLevel(logging.INFO)
bot = telebot.TeleBot(BOT_TOKEN)

# GLOBAL MEMORY
SEARCH_CACHE = {}

# ==========================================
# 2. URL GENERATOR (Optimized for Speed)
# ==========================================
def get_chart_url(symbol, prices, timestamps, period, change_pct):
    try:
        # 1. Ultra-Aggressive Downsampling (Max 40 points)
        # Fewer points = Shorter URL = Faster Telegram Preview
        max_points = 40 
        step = len(prices) // max_points if len(prices) > max_points else 1
        
        # 2. Round Numbers (Crucial optimization)
        # $420.5023 -> 420. Saves huge space in the URL.
        values = [int(p) for p in prices[::step]]
        dates = [datetime.fromtimestamp(ts).strftime('%d %b') for ts in timestamps[::step]]
        
        line_color = 'rgb(0, 255, 0)' if change_pct >= 0 else 'rgb(255, 0, 0)'
        fill_color = 'rgba(0, 255, 0, 0.2)' if change_pct >= 0 else 'rgba(255, 0, 0, 0.2)'
        
        chart_config = {
            "type": "line",
            "data": {
                "labels": dates,
                "datasets": [{
                    "label": symbol,
                    "data": values,
                    "borderColor": line_color,
                    "backgroundColor": fill_color,
                    "borderWidth": 2,
                    "fill": True,
                    "pointRadius": 0 
                }]
            },
            "options": {
                "title": { "display": True, "text": f"{symbol} ({period.upper()})", "fontColor": "#fff" },
                "legend": { "display": False },
                "scales": {
                    "xAxes": [{ "display": False }], 
                    "yAxes": [{ "gridLines": { "color": "rgba(255,255,255,0.1)" }, "ticks": { "fontColor": "#ccc" } }]
                }
            }
        }
        
        json_str = json.dumps(chart_config)
        encoded_json = urllib.parse.quote(json_str)
        return f"https://quickchart.io/chart?bkg=%23151515&w=800&h=400&c={encoded_json}"
    except: return ""

# ==========================================
# 3. SEARCH ENGINE
# ==========================================
def search_yahoo_categorized(query):
    print(f"🔎 Searching: {query}")
    try:
        url = f"https://query2.finance.yahoo.com/v1/finance/search?q={query}&quotesCount=50&newsCount=0"
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
        }
        response = requests.get(url, headers=headers, timeout=5)
        data = response.json()
        
        categories = {'INDIA': [], 'US_GLOBAL': [], 'CRYPTO': [], 'FUNDS': [], 'OTHER': []}
        all_results = []
        
        if 'quotes' in data:
            for item in data['quotes']:
                symbol = item.get('symbol', '')
                name = item.get('shortname', item.get('longname', symbol))
                q_type = item.get('quoteType', 'OTHER')
                
                if not symbol: continue
                obj = {'symbol': symbol, 'name': name, 'type': q_type}
                all_results.append(obj)
                
                if symbol.endswith('.NS') or symbol.endswith('.BO'): categories['INDIA'].append(obj)
                elif q_type == 'CRYPTOCURRENCY': categories['CRYPTO'].append(obj)
                elif q_type in ['ETF', 'MUTUALFUND']: categories['FUNDS'].append(obj)
                elif q_type == 'EQUITY': categories['US_GLOBAL'].append(obj)
                else: categories['OTHER'].append(obj)

        for key in categories: categories[key].sort(key=lambda x: len(x['symbol']))
        return categories, all_results
    except Exception as e:
        print(f"🔥 Search Failed: {e}")
        return {}, []

# ==========================================
# 4. DATA ENGINE (Robust)
# ==========================================
def get_data(ticker, requested_period="1y"):
    print(f"📉 Fetching Data: {ticker}")
    try:
        url = f"https://query1.finance.yahoo.com/v8/finance/chart/{ticker}?interval=1d&range=1y"
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
        }
        response = requests.get(url, headers=headers, timeout=5)
        
        if response.status_code != 200:
            print(f"❌ Yahoo Error: Status {response.status_code}")
            return None
            
        data = response.json()
        
        if not data['chart']['result']: 
            print("❌ No Data Found in JSON")
            return None

        result = data['chart']['result'][0]
        meta = result['meta']
        price = meta['regularMarketPrice']
        currency = meta.get('currency', '???')
        
        timestamps = result['timestamp']
        closes = result['indicators']['quote'][0]['close']
        
        clean_data = [(t, c) for t, c in zip(timestamps, closes) if c is not None]
        if not clean_data: return None
        
        all_timestamps, all_closes = zip(*clean_data)
        
        dma_200 = 0
        trend_text = "N/A"
        if len(all_closes) >= 200:
             dma_200 = sum(all_closes[-200:]) / 200
             trend = "🟢 BULLISH" if price > dma_200 else "🔴 BEARISH"
             trend_text = f"{trend} (Price > 200 DMA)" if price > dma_200 else f"{trend} (Price < 200 DMA)"
        else:
             trend_text = "⚠️ New Listing (No 200 DMA)"

        slice_map = { "1mo": 22, "3mo": 66, "6mo": 132, "1y": 252 }
        days_needed = slice_map.get(requested_period, 252)
        
        final_prices = all_closes[-days_needed:]
        final_timestamps = all_timestamps[-days_needed:]
        
        start_price = final_prices[0]
        current_price = final_prices[-1]
        pct_change = ((current_price - start_price) / start_price) * 100

        return {
            "price": price, "dma": dma_200, "trend": trend_text, "currency": currency, 
            "prices": final_prices, "timestamps": final_timestamps, "change": pct_change
        }
    except Exception as e:
        print(f"🔥 FETCH ERROR: {e}")
        return None

# ==========================================
# 5. FORMATTER
# ==========================================
def format_message(name, symbol, data, period, show_chart=False):
    p = data['price']
    dma = data['dma']
    cur = "₹" if data['currency'] == "INR" else "$"
    emoji = "🟢" if data['change'] > 0 else "🔴"
    
    text = (
        f"📊 <b>{name} ({symbol})</b>\n"
        f"💰 Price: {cur}{p:,.2f}\n"
        f"📏 200 DMA: {cur}{dma:,.2f}\n"
        f"📉 Trend: {data['trend']}\n\n"
        f"⏳ <b>{period.upper()} Return:</b> {emoji} {data['change']:+.2f}%\n"
        f"via @{bot.get_me().username}"
    )
    
    if show_chart:
        chart_url = get_chart_url(symbol, data['prices'], data['timestamps'], period, data['change'])
        if chart_url:
            text = f"<a href='{chart_url}'>&#8205;</a>" + text
            
    return text

# ==========================================
# 6. HANDLERS (With Error Feedback)
# ==========================================
@bot.message_handler(commands=['analyze', 'analyse'])
def start_search(message):
    try:
        parts = message.text.split(maxsplit=1)
        if len(parts) < 2:
            bot.reply_to(message, "⚠️ Type a name.\nExample: `/analyze btc`")
            return
            
        query = parts[1]
        loading = bot.reply_to(message, f"🔍 Searching markets for '{query}'...")
        categories, all_items = search_yahoo_categorized(query)
        
        if not all_items:
            bot.edit_message_text("❌ No results found.", chat_id=message.chat.id, message_id=loading.message_id)
            return

        search_id = str(uuid.uuid4())[:8] 
        SEARCH_CACHE[search_id] = categories
        
        markup = InlineKeyboardMarkup()
        for cat, items in categories.items():
            if items:
                label = {'INDIA': "🇮🇳 India", 'US_GLOBAL': "🌎 Global", 'CRYPTO': "₿ Crypto", 'FUNDS': "📉 Funds"}.get(cat, "📊 Other")
                markup.add(InlineKeyboardButton(f"{label} ({len(items)})", callback_data=f"CAT|{cat}|{search_id}"))
        
        bot.edit_message_text(f"👇 <b>Select Market for '{query}':</b>", chat_id=message.chat.id, message_id=loading.message_id, reply_markup=markup, parse_mode="HTML")
    except: pass

@bot.callback_query_handler(func=lambda call: True)
def handle_clicks(call):
    try:
        parts = call.data.split('|')
        action = parts[0]
        
        # --- SHOW CATEGORY ---
        if action == "CAT":
            cat = parts[1]; sid = parts[2]
            
            if sid not in SEARCH_CACHE:
                bot.answer_callback_query(call.id, "⚠️ Search expired. Try /analyze again.")
                return

            items = SEARCH_CACHE[sid].get(cat, [])
            markup = InlineKeyboardMarkup()
            for item in items[:10]:
                markup.add(InlineKeyboardButton(f"{item['symbol']} - {item['name'][:20]}", 
                                                callback_data=f"GET|{item['symbol']}|{sid}|{cat}"))
            markup.add(InlineKeyboardButton("⬅️ Back to Markets", callback_data=f"BACK|{sid}"))
            bot.edit_message_text(f"📂 <b>{cat.replace('_',' ')} Results:</b>", chat_id=call.message.chat.id, message_id=call.message.message_id, reply_markup=markup, parse_mode="HTML")

        # --- GET DATA (Text View) ---
        elif action == "GET" or action == "TEXT":
            symbol = parts[1]; sid = parts[2]; prev_cat = parts[3]
            
            if action == "TEXT": bot.answer_callback_query(call.id, "Switching to Text...")
            else: bot.answer_callback_query(call.id, f"Analyzing {symbol}...")
            
            data = get_data(symbol, "1y")
            
            if data:
                msg = format_message(symbol, symbol, data, "1y", show_chart=False)
                markup = InlineKeyboardMarkup()
                markup.row(
                    InlineKeyboardButton("1M", callback_data=f"TIME|1mo|{symbol}|{sid}|{prev_cat}"),
                    InlineKeyboardButton("3M", callback_data=f"TIME|3mo|{symbol}|{sid}|{prev_cat}"),
                    InlineKeyboardButton("6M", callback_data=f"TIME|6mo|{symbol}|{sid}|{prev_cat}"),
                    InlineKeyboardButton("1Y", callback_data=f"TIME|1y|{symbol}|{sid}|{prev_cat}")
                )
                markup.add(InlineKeyboardButton(f"⬅️ Back to {prev_cat.replace('_',' ')}", callback_data=f"CAT|{prev_cat}|{sid}"))
                
                no_preview = LinkPreviewOptions(is_disabled=True)
                
                if action == "TEXT":
                    bot.delete_message(call.message.chat.id, call.message.message_id)
                    bot.send_message(call.message.chat.id, msg, reply_markup=markup, parse_mode="HTML", link_preview_options=no_preview)
                else:
                    bot.edit_message_text(msg, chat_id=call.message.chat.id, message_id=call.message.message_id, parse_mode="HTML", reply_markup=markup, link_preview_options=no_preview)
            else:
                bot.send_message(call.message.chat.id, f"❌ Failed to fetch data for {symbol}. Try again later.")

        # --- UPDATE CHART (Preview Mode) ---
        elif action == "TIME":
            period = parts[1]; symbol = parts[2]; sid = parts[3]; prev_cat = parts[4]
            
            bot.answer_callback_query(call.id, f"Loading {period} Chart...")
            data = get_data(symbol, period)
            
            if data:
                msg = format_message(symbol, symbol, data, period, show_chart=True)
                markup = InlineKeyboardMarkup()
                markup.row(
                    InlineKeyboardButton("1M", callback_data=f"TIME|1mo|{symbol}|{sid}|{prev_cat}"),
                    InlineKeyboardButton("3M", callback_data=f"TIME|3mo|{symbol}|{sid}|{prev_cat}"),
                    InlineKeyboardButton("6M", callback_data=f"TIME|6mo|{symbol}|{sid}|{prev_cat}"),
                    InlineKeyboardButton("1Y", callback_data=f"TIME|1y|{symbol}|{sid}|{prev_cat}")
                )
                markup.add(InlineKeyboardButton("📄 Text View", callback_data=f"TEXT|{symbol}|{sid}|{prev_cat}"))
                markup.add(InlineKeyboardButton("⚡ Join Group", url=GROUP_LINK))

                show_preview = LinkPreviewOptions(is_disabled=False, prefer_large_media=True)
                bot.edit_message_text(msg, chat_id=call.message.chat.id, message_id=call.message.message_id, parse_mode="HTML", reply_markup=markup, link_preview_options=show_preview)
            else:
                bot.send_message(call.message.chat.id, f"❌ Failed to load chart for {symbol}.")

        # --- BACK NAV ---
        elif action == "BACK":
            sid = parts[1]
            if sid in SEARCH_CACHE:
                categories = SEARCH_CACHE[sid]
                markup = InlineKeyboardMarkup()
                for cat, items in categories.items():
                    if items:
                        label = {'INDIA': "🇮🇳 India", 'US_GLOBAL': "🌎 Global"}.get(cat, f"📂 {cat}")
                        markup.add(InlineKeyboardButton(f"{label} ({len(items)})", callback_data=f"CAT|{cat}|{sid}"))
                bot.edit_message_text("👇 <b>Select Market:</b>", chat_id=call.message.chat.id, message_id=call.message.message_id, reply_markup=markup, parse_mode="HTML")

    except Exception as e:
        print(f"Error: {e}")

print("✅ Bot Live (Optimized Charts)...")
while True:
    try:
        bot.infinity_polling(timeout=10, long_polling_timeout=5)
    except Exception as e:
        print(f"⚠️ Connection Lost: {e}. Retrying...")
        time.sleep(5)
