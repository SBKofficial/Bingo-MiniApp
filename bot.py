import telebot
from telebot.types import InlineQueryResultArticle, InputTextMessageContent, InlineKeyboardMarkup, InlineKeyboardButton, InputMediaPhoto
import requests
import logging
import uuid
import time
from datetime import datetime
import json # Used for the chart payload

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
# 2. CLOUD CHART ENGINE (QuickChart.io)
# ==========================================
def generate_chart(symbol, prices, timestamps, period, change_pct):
    """Sends data to QuickChart.io and gets an image back"""
    print(f"🎨 Rendering Chart for {symbol}...")
    try:
        # 1. Downsample data (Phone screens are small, we don't need 365 points)
        # If we have too many points, the URL gets too long or the chart looks messy.
        step = 1
        if len(prices) > 100: step = len(prices) // 100 # Keep max ~100 points
        
        dates = [datetime.fromtimestamp(ts).strftime('%d %b') for ts in timestamps[::step]]
        values = prices[::step]
        
        # 2. Pick Color
        line_color = 'rgb(0, 255, 0)' if change_pct >= 0 else 'rgb(255, 0, 0)' # Bright Green/Red
        fill_color = 'rgba(0, 255, 0, 0.2)' if change_pct >= 0 else 'rgba(255, 0, 0, 0.2)'
        
        # 3. Construct the Chart Config (Chart.js format)
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
                    "pointRadius": 0 # Hide dots for a clean line
                }]
            },
            "options": {
                "title": {
                    "display": True,
                    "text": f"{symbol} ({period.upper()})",
                    "fontColor": "#fff"
                },
                "legend": { "display": False },
                "scales": {
                    "xAxes": [{ 
                        "gridLines": { "display": False },
                        "ticks": { "fontColor": "#ccc", "maxTicksLimit": 6 }
                    }],
                    "yAxes": [{ 
                        "gridLines": { "color": "rgba(255,255,255,0.1)" },
                        "ticks": { "fontColor": "#ccc" }
                    }]
                }
            }
        }
        
        # 4. Request the Image (Dark Mode URL)
        # We use a POST request because the data might be too long for a URL
        url = "https://quickchart.io/chart"
        payload = {
            "backgroundColor": "#151515", # Dark Background
            "width": 800,
            "height": 400,
            "format": "png",
            "chart": chart_config
        }
        
        response = requests.post(url, json=payload, timeout=5)
        
        if response.status_code == 200:
            return response.content # The raw image bytes
        else:
            print("❌ QuickChart Failed")
            return None

    except Exception as e:
        print(f"🔥 Chart Error: {e}")
        return None

# ==========================================
# 3. SEARCH ENGINE (Global Buckets)
# ==========================================
def search_yahoo_categorized(query):
    try:
        url = f"https://query2.finance.yahoo.com/v1/finance/search?q={query}&quotesCount=50&newsCount=0"
        headers = {"User-Agent": "Mozilla/5.0"}
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
    except: return {}, []

# ==========================================
# 4. DATA ENGINE
# ==========================================
def get_data(ticker, period="1y"):
    print(f"📉 Fetching {period} Data: {ticker}")
    try:
        url = f"https://query1.finance.yahoo.com/v8/finance/chart/{ticker}?interval=1d&range={period}"
        headers = {"User-Agent": "Mozilla/5.0"}
        response = requests.get(url, headers=headers, timeout=4)
        data = response.json()
        
        if not data['chart']['result']: return None

        result = data['chart']['result'][0]
        meta = result['meta']
        price = meta['regularMarketPrice']
        currency = meta.get('currency', '???')
        
        timestamps = result['timestamp']
        closes = result['indicators']['quote'][0]['close']
        
        clean_data = [(t, c) for t, c in zip(timestamps, closes) if c is not None]
        if not clean_data: return None
        
        timestamps, closes = zip(*clean_data)
        
        dma_200 = 0
        trend_text = "N/A"
        if len(closes) >= 200:
             dma_200 = sum(closes[-200:]) / 200
             trend = "🟢 BULLISH" if price > dma_200 else "🔴 BEARISH"
             trend_text = f"{trend} (Price > 200 DMA)" if price > dma_200 else f"{trend} (Price < 200 DMA)"
        elif len(closes) > 0:
             trend_text = "⚠️ New Listing (No 200 DMA)"

        start_price = closes[0]
        current_price = closes[-1]
        pct_change = ((current_price - start_price) / start_price) * 100

        return {
            "price": price, "dma": dma_200, "trend": trend_text,
            "currency": currency, "prices": closes, "timestamps": timestamps,
            "change": pct_change
        }
    except Exception as e:
        print(e)
        return None

def format_message(name, symbol, data, period):
    p = data['price']
    dma = data['dma']
    cur = "₹" if data['currency'] == "INR" else "$"
    emoji = "🟢" if data['change'] > 0 else "🔴"

    return (
        f"📊 <b>{name} ({symbol})</b>\n"
        f"💰 Price: {cur}{p:,.2f}\n"
        f"📏 200 DMA: {cur}{dma:,.2f}\n"
        f"📉 Trend: {data['trend']}\n\n"
        f"⏳ <b>{period.upper()} Return:</b> {emoji} {data['change']:+.2f}%\n"
        f"via @{bot.get_me().username}"
    )

# ==========================================
# 5. HANDLERS
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
                markup.add(InlineKeyboardButton(f"{label} ({len(items)})", callback_data=f"CAT_{cat}_{search_id}"))
        
        bot.edit_message_text(f"👇 <b>Select Market for '{query}':</b>", chat_id=message.chat.id, message_id=loading.message_id, reply_markup=markup, parse_mode="HTML")
    except: pass

@bot.callback_query_handler(func=lambda call: True)
def handle_clicks(call):
    try:
        parts = call.data.split('_')
        action = parts[0]
        
        if action == "CAT":
            cat = parts[1]
            if len(parts) > 3: cat = parts[1] + "_" + parts[2]; sid = parts[3]
            else: sid = parts[2]
            
            if sid not in SEARCH_CACHE: return
            items = SEARCH_CACHE[sid].get(cat, [])
            markup = InlineKeyboardMarkup()
            for item in items[:10]:
                markup.add(InlineKeyboardButton(f"{item['symbol']} - {item['name'][:20]}", callback_data=f"GET_{item['symbol']}_{sid}"))
            markup.add(InlineKeyboardButton("⬅️ Back", callback_data=f"BACK_{sid}"))
            bot.edit_message_text(f"📂 <b>{cat} Results:</b>", chat_id=call.message.chat.id, message_id=call.message.message_id, reply_markup=markup, parse_mode="HTML")

        elif action == "GET":
            symbol = parts[1]
            sid = parts[2]
            bot.answer_callback_query(call.id, f"Analyzing {symbol}...")
            
            data = get_data(symbol, "1y")
            if data:
                msg = format_message(symbol, symbol, data, "1y")
                markup = InlineKeyboardMarkup()
                markup.row(
                    InlineKeyboardButton("1M", callback_data=f"TIME_1mo_{symbol}_{sid}"),
                    InlineKeyboardButton("3M", callback_data=f"TIME_3mo_{symbol}_{sid}"),
                    InlineKeyboardButton("6M", callback_data=f"TIME_6mo_{symbol}_{sid}"),
                    InlineKeyboardButton("1Y", callback_data=f"TIME_1y_{symbol}_{sid}")
                )
                markup.add(InlineKeyboardButton("⬅️ Back", callback_data=f"CAT_INDIA_{sid}")) 
                bot.edit_message_text(msg, chat_id=call.message.chat.id, message_id=call.message.message_id, parse_mode="HTML", reply_markup=markup)

        elif action == "TIME":
            period = parts[1]
            symbol = parts[2]
            sid = parts[3]
            
            bot.answer_callback_query(call.id, f"Generating {period} Chart...")
            data = get_data(symbol, period)
            if data:
                # 🎨 RENDER VIA QUICKCHART (No Matplotlib required)
                img_data = generate_chart(symbol, data['prices'], data['timestamps'], period, data['change'])
                
                if img_data:
                    caption = format_message(symbol, symbol, data, period)
                    markup = InlineKeyboardMarkup()
                    markup.row(
                        InlineKeyboardButton("1M", callback_data=f"TIME_1mo_{symbol}_{sid}"),
                        InlineKeyboardButton("3M", callback_data=f"TIME_3mo_{symbol}_{sid}"),
                        InlineKeyboardButton("6M", callback_data=f"TIME_6mo_{symbol}_{sid}"),
                        InlineKeyboardButton("1Y", callback_data=f"TIME_1y_{symbol}_{sid}")
                    )
                    markup.add(InlineKeyboardButton("⬅️ Back Menu", callback_data=f"GET_{symbol}_{sid}"))
                    markup.add(InlineKeyboardButton("⚡ Join Group", url=GROUP_LINK))

                    try:
                        media = InputMediaPhoto(img_data, caption=caption, parse_mode="HTML")
                        bot.edit_message_media(media=media, chat_id=call.message.chat.id, message_id=call.message.message_id, reply_markup=markup)
                    except:
                        bot.delete_message(call.message.chat.id, call.message.message_id)
                        bot.send_photo(call.message.chat.id, img_data, caption=caption, reply_markup=markup, parse_mode="HTML")

        elif action == "BACK":
            sid = parts[1]
            if sid in SEARCH_CACHE:
                categories = SEARCH_CACHE[sid]
                markup = InlineKeyboardMarkup()
                for cat, items in categories.items():
                    if items:
                         markup.add(InlineKeyboardButton(f"{cat} ({len(items)})", callback_data=f"CAT_{cat}_{sid}"))
                bot.edit_message_text("👇 <b>Select Market:</b>", chat_id=call.message.chat.id, message_id=call.message.message_id, reply_markup=markup, parse_mode="HTML")

    except Exception as e:
        print(f"Error: {e}")

print("✅ Cloud-Rendered Bot is Live...")
while True:
    try:
        bot.infinity_polling(timeout=10, long_polling_timeout=5)
    except Exception as e:
        time.sleep(5)
