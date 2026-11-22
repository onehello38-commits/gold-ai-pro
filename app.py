import os, time, threading, requests
from flask import Flask, jsonify

app = Flask(__name__)

API = os.getenv("TWELVEDATA_API_KEY", "")
BOT = os.getenv("TELEGRAM_BOT_TOKEN", "")
CHAT = os.getenv("TELEGRAM_CHAT_ID", "")
SYMBOL = os.getenv("GOLD_SYMBOL", "XAU/USD")
last_signal = ""

def get_data():
    r = requests.get(
        "https://api.twelvedata.com/time_series",
        params={
            "symbol": SYMBOL,
            "interval": "15min",
            "outputsize": 60,
            "apikey": API
        },
        timeout=20
    )
    r.raise_for_status()
    j = r.json()
    if "values" not in j:
        raise Exception(j.get("message", "Data unavailable"))
    return list(reversed(j["values"]))

def ema(values, period):
    k = 2 / (period + 1)
    result = values[0]
    for v in values[1:]:
        result = v * k + result * (1-k)
    return result

def analysis():
    candles = get_data()
    closes = [float(c["close"]) for c in candles]
    e20 = ema(closes[-50:], 20)
    e50 = ema(closes[-50:], 50)
    price = closes[-1]

    changes = [
        closes[i] - closes[i-1]
        for i in range(len(closes)-14, len(closes))
    ]
    gains = [max(x, 0) for x in changes]
    losses = [max(-x, 0) for x in changes]
    avg_gain = sum(gains) / 14
    avg_loss = sum(losses) / 14
    rsi = 100 if avg_loss == 0 else (
        100 - 100 / (1 + avg_gain / avg_loss)
    )

    bullish = price > e20 > e50 and rsi > 50
    bearish = price < e20 < e50 and rsi < 50

    signal = "BUY" if bullish else (
        "SELL" if bearish else "WAIT"
    )

    return {
        "price": price,
        "ema20": e20,
        "ema50": e50,
        "rsi": rsi,
        "signal": signal,
        "time": candles[-1]["datetime"]
    }

def send_telegram(message):
    if BOT and CHAT:
        requests.post(
            f"https://api.telegram.org/bot{BOT}/sendMessage",
            json={"chat_id": CHAT, "text": message},
            timeout=15
        ).raise_for_status()

def monitor():
    global last_signal
    while True:
        try:
            data = analysis()
            s = data["signal"]
            if s in ("BUY", "SELL") and s != last_signal:
                send_telegram(
                    f"Gold AI Pro\n{s}\n"
                    f"Price: {data['price']}\n"
                    f"RSI: {data['rsi']:.2f}"
                )
                last_signal = s
            elif s == "WAIT":
                last_signal = ""
        except Exception as e:
            print("Monitor error:", e)
        time.sleep(300)

@app.route("/")
def home():
    return """
    <html>
    <meta name="viewport" content="width=device-width,initial-scale=1">
    <body style="background:#101827;color:white;font-family:Arial;padding:20px">
    <h1>Gold AI Pro</h1>
    <button onclick="load()">Refresh Analysis</button>
    <button onclick="test()">Telegram Test</button>
    <pre id="out">Loading...</pre>
    <script>
    async function load(){
      let r=await fetch('/analysis');
      document.getElementById('out').textContent=
        JSON.stringify(await r.json(),null,2);
    }
    async function test(){
      let r=await fetch('/test');
      alert(JSON.stringify(await r.json()));
    }
    load();
    setInterval(load,60000);
    </script>
    </body></html>
    """

@app.route("/analysis")
def show_analysis():
    try:
        return jsonify(analysis())
    except Exception as e:
        return jsonify({"error":str(e)}), 500

@app.route("/test")
def test():
    try:
        send_telegram("Gold AI Pro: Test alert successful.")
        return jsonify({"ok":True})
    except Exception as e:
        return jsonify({"error":str(e)}), 500

@app.route("/health")
def health():
    return jsonify({"ok":True})

if __name__ == "__main__":
    threading.Thread(target=monitor, daemon=True).start()
    app.run(host="0.0.0.0", port=int(os.getenv("PORT",10000)))
