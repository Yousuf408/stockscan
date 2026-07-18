from flask import Flask, request, jsonify, render_template_string
from flask_cors import CORS
import json

app = Flask(__name__)
CORS(app)

# ============================================
# YOUR mSTOCK API CONFIGURATION
# ============================================
# Replace with your actual mStock credentials
MSTOCK_API_KEY = "E5wDwGTEetqDyO52sUkD+ya8Xcvj2b+q5u1bmtqnS3g="
MSTOCK_SECRET = "YOUR_SECRET_HERE"

# Initialize mStock client (using your existing setup)
# Since you already have app.py, use your existing mStock connection
try:
    from Mconnect import Mconnect
    mconnect_obj = Mconnect()
    mconnect_obj.set_jwt_token(MSTOCK_API_KEY)
    print("✅ mStock connected successfully")
except Exception as e:
    print(f"⚠️ mStock connection error: {e}")
    # Fallback mock data for testing
    mconnect_obj = None

# ============================================
# HTML DASHBOARD (Embedded in Python)
# ============================================
HTML_TEMPLATE = """
<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <title>Trading Dashboard - Margin Calculator</title>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body {
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
            background: #0a0e1a;
            color: #fff;
            padding: 20px;
        }
        .container {
            max-width: 1400px;
            margin: 0 auto;
        }
        .header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 20px;
            flex-wrap: wrap;
            gap: 15px;
        }
        h1 {
            color: #00d4ff;
            font-size: 24px;
        }
        .capital-box {
            background: linear-gradient(135deg, #1a1f35, #2a3050);
            padding: 15px 25px;
            border-radius: 12px;
            border: 1px solid #00d4ff33;
        }
        .capital-box span {
            color: #00d4ff;
            font-size: 22px;
            font-weight: bold;
        }
        .controls {
            display: flex;
            gap: 15px;
            margin-bottom: 20px;
            flex-wrap: wrap;
            align-items: center;
        }
        .controls button {
            background: #00d4ff;
            color: #0a0e1a;
            border: none;
            padding: 10px 25px;
            border-radius: 8px;
            font-weight: bold;
            cursor: pointer;
            transition: 0.3s;
            font-size: 14px;
        }
        .controls button:hover {
            transform: scale(1.05);
            box-shadow: 0 0 20px #00d4ff66;
        }
        .controls button:disabled {
            opacity: 0.5;
            cursor: not-allowed;
        }
        .status-badge {
            background: #1a1f35;
            padding: 8px 15px;
            border-radius: 20px;
            font-size: 13px;
            color: #ffcc00;
        }
        table {
            width: 100%;
            border-collapse: collapse;
            background: #111827;
            border-radius: 12px;
            overflow: hidden;
        }
        th {
            background: #1a1f35;
            color: #00d4ff;
            padding: 12px;
            text-align: left;
            font-size: 12px;
            text-transform: uppercase;
            letter-spacing: 0.5px;
        }
        td {
            padding: 12px;
            border-bottom: 1px solid #1f2a40;
            font-size: 14px;
        }
        tr:hover {
            background: #1a1f35;
        }
        .leverage-high { color: #00ff88; }
        .leverage-medium { color: #ffcc00; }
        .leverage-low { color: #ff6b6b; }
        .status-loading { color: #ffcc00; }
        .status-success { color: #00ff88; }
        .status-error { color: #ff6b6b; }
        .margin-column {
            background: #1a1f3555;
            border-left: 2px solid #00d4ff33;
        }
        .buy-btn {
            background: #00d4ff;
            color: #0a0e1a;
            border: none;
            padding: 6px 15px;
            border-radius: 6px;
            cursor: pointer;
            font-weight: bold;
            transition: 0.3s;
        }
        .buy-btn:hover {
            background: #00ff88;
            transform: scale(1.05);
        }
        .buy-btn:disabled {
            background: #444;
            cursor: not-allowed;
        }
        .auto-fetch-indicator {
            color: #00ff88;
            font-size: 13px;
            animation: pulse 1.5s infinite;
        }
        @keyframes pulse {
            0% { opacity: 0.6; }
            50% { opacity: 1; }
            100% { opacity: 0.6; }
        }
        .stock-input {
            background: #1a1f35;
            border: 1px solid #2a3050;
            color: #fff;
            padding: 10px 15px;
            border-radius: 8px;
            flex: 1;
            min-width: 200px;
        }
        .stock-input::placeholder {
            color: #666;
        }
        .demo-table {
            margin-top: 20px;
            border: 1px solid #1f2a40;
            border-radius: 8px;
            overflow: hidden;
        }
        .demo-table caption {
            padding: 10px;
            color: #888;
            text-align: left;
            font-size: 14px;
        }
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>🚀 Live Margin Calculator</h1>
            <div class="capital-box">
                💰 Capital: <span id="capitalDisplay">₹0</span>
            </div>
        </div>
        
        <div class="controls">
            <button id="fetchBtn" onclick="fetchAllStocks()">🔄 Auto-Fetch Margins</button>
            <button onclick="refreshData()">↻ Refresh</button>
            <span id="statusBadge" class="status-badge">⏳ Ready</span>
            <span id="stockCount" class="auto-fetch-indicator">📊 0 stocks detected</span>
        </div>
        
        <div id="stockListContainer">
            <!-- Demo Table with your existing stock data -->
            <div class="demo-table">
                <table id="mainTable">
                    <caption>📋 Your Trading Dashboard (Auto-detect stocks from this table)</caption>
                    <thead>
                        <tr>
                            <th>Symbol</th>
                            <th>Max Qty</th>
                            <th>Price/Chg%</th>
                            <th>Volume/RelVol</th>
                            <th>Signal Time</th>
                            <th>POC/Gap</th>
                            <th>Signal Price/% Chg</th>
                            <th>Entry Signal</th>
                            <th>Prev High</th>
                            <th>Crossover</th>
                        </tr>
                    </thead>
                    <tbody>
                        <tr>
                            <td>GABRIEL</td>
                            <td>95</td>
                            <td>$1329.60 +6.49%</td>
                            <td>5.56x 9.7L</td>
                            <td>09:37</td>
                            <td>1,249.31 +6.4%</td>
                            <td>1,304.90 +1.89%</td>
                            <td>9:40 9:45 9:50</td>
                            <td>1,263.00 +5.3%</td>
                            <td>1,189.00 +1.9%</td>
                        </tr>
                        <tr>
                            <td>TIMETECHNO</td>
                            <td>690</td>
                            <td>$192.50 +6.29%</td>
                            <td>3.7M 1.18x</td>
                            <td>11:05</td>
                            <td>186.56 +3.2%</td>
                            <td>189.20 +1.74%</td>
                            <td>9:40 9:45 9:50</td>
                            <td>1,189.00 +1.9%</td>
                            <td>1,189.00 +1.9%</td>
                        </tr>
                        <tr>
                            <td>KMEW</td>
                            <td>50</td>
                            <td>$2452.00 +4.70%</td>
                            <td>1.8L 1.37x</td>
                            <td>09:44</td>
                            <td>2,355.21 +4.1%</td>
                            <td>2,475.00 -0.93%</td>
                            <td>9:40 9:45 9:50</td>
                            <td>2,396.00 +2.3%</td>
                            <td>2,396.00 +2.3%</td>
                        </tr>
                        <tr>
                            <td>SIGNATURE</td>
                            <td>143</td>
                            <td>$854.75 +3.91%</td>
                            <td>4.2M 6.79x</td>
                            <td>10:58</td>
                            <td>$822.70 +3.9%</td>
                            <td>869.90 -1.74%</td>
                            <td>9:40 9:45 9:50</td>
                            <td>1,843.95 +1.3%</td>
                            <td>1,843.95 +1.3%</td>
                        </tr>
                        <tr>
                            <td>ORCHPHARMA</td>
                            <td>118</td>
                            <td>$1087.50 +3.28%</td>
                            <td>2.3L 0.81x</td>
                            <td>11:22</td>
                            <td>1,052.69 +3.3%</td>
                            <td>1,112.05 -2.21%</td>
                            <td>9:40 9:45 9:50</td>
                            <td>1,106.95 1.8%</td>
                            <td>1,106.95 1.8%</td>
                        </tr>
                        <tr>
                            <td>JYOTICNC</td>
                            <td>159</td>
                            <td>$807.30 +3.13%</td>
                            <td>7.8L 1.47x</td>
                            <td>11:18</td>
                            <td>795.62 +1.5%</td>
                            <td>808.65 -0.17%</td>
                            <td>9:40 9:45 9:50</td>
                            <td>808.95 -0.2%</td>
                            <td>808.95 -0.2%</td>
                        </tr>
                    </tbody>
                </table>
            </div>
        </div>
    </div>

    <script>
        // ============================================
        // AUTO-DETECT STOCKS FROM YOUR TABLE
        // ============================================
        function getStockSymbolsFromTable() {
            const symbols = [];
            const rows = document.querySelectorAll('#mainTable tbody tr');
            
            rows.forEach(row => {
                const firstCell = row.querySelector('td:first-child');
                if (firstCell) {
                    const text = firstCell.textContent.trim();
                    // Match uppercase stock symbols (2-5 characters)
                    if (/^[A-Z]{2,5}$/.test(text)) {
                        symbols.push(text);
                    }
                }
            });
            
            return [...new Set(symbols)];
        }

        // ============================================
        // FETCH MARGIN DATA FROM BACKEND
        // ============================================
        async function fetchAllStocks() {
            const fetchBtn = document.getElementById('fetchBtn');
            const statusBadge = document.getElementById('statusBadge');
            
            const stockList = getStockSymbolsFromTable();
            
            if (stockList.length === 0) {
                statusBadge.innerHTML = '❌ No stocks found';
                statusBadge.style.color = '#ff6b6b';
                alert('No stock symbols detected. Make sure your table has symbols in the first column.');
                return;
            }
            
            document.getElementById('stockCount').textContent = `📊 ${stockList.length} stocks detected`;
            fetchBtn.disabled = true;
            statusBadge.innerHTML = '⏳ Calculating...';
            statusBadge.style.color = '#ffcc00';
            
            showLoading(stockList);
            
            try {
                const response = await fetch('/get_margin_data', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ stocks: stockList })
                });
                
                const data = await response.json();
                
                if (data.status === 'success') {
                    document.getElementById('capitalDisplay').textContent = 
                        `₹${data.available_capital.toLocaleString()}`;
                    renderTableWithMargins(data.data);
                    statusBadge.innerHTML = `✅ Updated (${new Date().toLocaleTimeString()})`;
                    statusBadge.style.color = '#00ff88';
                } else {
                    statusBadge.innerHTML = '❌ Error';
                    statusBadge.style.color = '#ff6b6b';
                    alert('Error: ' + data.message);
                }
            } catch (error) {
                statusBadge.innerHTML = '❌ Network Error';
                statusBadge.style.color = '#ff6b6b';
                alert('Failed to fetch data. Check if server is running.');
                console.error(error);
            } finally {
                fetchBtn.disabled = false;
            }
        }

        // ============================================
        // RENDER TABLE WITH MARGIN COLUMNS
        // ============================================
        function renderTableWithMargins(stocks) {
            const container = document.getElementById('stockListContainer');
            
            let html = `
                <div class="demo-table">
                    <table style="width:100%">
                        <thead>
                            <tr>
                                <th>Symbol</th>
                                <th>Price (₹)</th>
                                <th class="margin-column">Margin/Share (₹)</th>
                                <th class="margin-column">Leverage</th>
                                <th class="margin-column">Buying Power (₹)</th>
                                <th class="margin-column">Max Qty</th>
                                <th>Status</th>
                                <th>Action</th>
                            </tr>
                        </thead>
                        <tbody>
            `;
            
            stocks.forEach(stock => {
                if (stock.status === 'error') {
                    html += `
                        <tr>
                            <td><strong>${stock.symbol}</strong></td>
                            <td colspan="6" style="color: #ff6b6b;">${stock.error}</td>
                            <td>❌</td>
                        </tr>
                    `;
                } else {
                    const leverageClass = stock.leverage >= 4 ? 'leverage-high' : 
                                         stock.leverage >= 2.5 ? 'leverage-medium' : 'leverage-low';
                    
                    html += `
                        <tr>
                            <td><strong>${stock.symbol}</strong></td>
                            <td>₹${stock.price.toFixed(2)}</td>
                            <td class="margin-column">₹${stock.margin_per_share.toFixed(2)}</td>
                            <td class="margin-column ${leverageClass}">${stock.leverage}x</td>
                            <td class="margin-column">₹${stock.total_buying_power.toFixed(2)}</td>
                            <td class="margin-column"><strong>${stock.max_quantity}</strong></td>
                            <td class="status-success">✅ Ready</td>
                            <td><button class="buy-btn" onclick="placeOrder('${stock.symbol}', ${stock.max_quantity})">Buy</button></td>
                        </tr>
                    `;
                }
            });
            
            html += `
                        </tbody>
                    </table>
                </div>
            `;
            
            container.innerHTML = html;
        }

        // ============================================
        // SHOW LOADING STATE
        // ============================================
        function showLoading(stocks) {
            const container = document.getElementById('stockListContainer');
            let html = `
                <div class="demo-table">
                    <table style="width:100%">
                        <thead>
                            <tr>
                                <th>Symbol</th>
                                <th>Status</th>
                            </tr>
                        </thead>
                        <tbody>
            `;
            stocks.forEach(symbol => {
                html += `
                    <tr>
                        <td><strong>${symbol}</strong></td>
                        <td class="status-loading">⏳ Calculating...</td>
                    </tr>
                `;
            });
            html += `
                        </tbody>
                    </table>
                </div>
            `;
            container.innerHTML = html;
        }

        // ============================================
        // REFRESH & PLACE ORDER
        // ============================================
        function refreshData() {
            document.getElementById('statusBadge').innerHTML = '⏳ Refreshing...';
            document.getElementById('statusBadge').style.color = '#ffcc00';
            fetchAllStocks();
        }

        function placeOrder(symbol, maxQuantity) {
            const qty = prompt(`📈 Enter quantity for ${symbol} (Max: ${maxQuantity}):`, maxQuantity);
            if (qty && parseInt(qty) <= maxQuantity) {
                alert(`🟢 Order placed: ${symbol} - ${qty} shares\n(Simulation - Implement actual API here)`);
            } else if (qty) {
                alert(`❌ Quantity exceeds maximum allowed (${maxQuantity} shares)`);
            }
        }

        // ============================================
        // AUTO-FETCH ON PAGE LOAD
        // ============================================
        window.onload = function() {
            setTimeout(() => {
                const stocks = getStockSymbolsFromTable();
                if (stocks.length > 0) {
                    document.getElementById('stockCount').textContent = 
                        `📊 ${stocks.length} stocks detected`;
                    fetchAllStocks();
                }
            }, 1000);
        };
    </script>
</body>
</html>
"""

# ============================================
# FLASK ROUTES
# ============================================

@app.route('/')
def dashboard():
    """Serve the dashboard HTML"""
    return render_template_string(HTML_TEMPLATE)

@app.route('/get_margin_data', methods=['POST'])
def get_margin_data():
    """
    API endpoint that receives stock list and returns margin calculations
    """
    try:
        data = request.json
        stocks = data.get('stocks', [])
        
        if not stocks:
            return jsonify({
                'status': 'error',
                'message': 'No stocks provided'
            })
        
        # Get available capital
        if mconnect_obj:
            try:
                funds = mconnect_obj.get_fund_summary()
                available_capital = float(funds['data'][0]['MTF_AVAILABLE_BALANCE'])
            except Exception as e:
                # Fallback: use mock capital for testing
                available_capital = 10000.0
                print(f"⚠️ Using mock capital: ₹10,000 (Error: {e})")
        else:
            # Mock data for testing without real connection
            available_capital = 10000.0
            print("⚠️ Using mock capital: ₹10,000 (No mStock connection)")
        
        results = []
        
        for stock_symbol in stocks:
            try:
                if mconnect_obj:
                    # REAL API CALLS
                    quote = mconnect_obj.get_lttp(stock_symbol)
                    current_price = quote['data']['ltp']
                    
                    margin_data = mconnect_obj.calculate_order_margin(
                        exchange="NSE",
                        trading_symbol=stock_symbol,
                        transaction_type="BUY",
                        product_type="MIS",
                        order_type="MARKET",
                        quantity="1",
                        price="0",
                        trigger_price="0"
                    )
                    margin_per_share = float(margin_data['data']['total'])
                else:
                    # MOCK DATA for testing
                    import random
                    current_price = round(random.uniform(100, 5000), 2)
                    margin_per_share = round(current_price * random.uniform(0.2, 0.5), 2)
                
                # Calculate leverage and quantity
                leverage = current_price / margin_per_share
                total_buying_power = available_capital * leverage
                max_quantity = int(total_buying_power / current_price)
                
                results.append({
                    'symbol': stock_symbol,
                    'price': round(current_price, 2),
                    'margin_per_share': round(margin_per_share, 2),
                    'leverage': round(leverage, 1),
                    'total_buying_power': round(total_buying_power, 2),
                    'max_quantity': max_quantity,
                    'status': 'success'
                })
                
            except Exception as e:
                results.append({
                    'symbol': stock_symbol,
                    'status': 'error',
                    'error': str(e)
                })
        
        return jsonify({
            'status': 'success',
            'available_capital': available_capital,
            'data': results
        })
        
    except Exception as e:
        return jsonify({
            'status': 'error',
            'message': str(e)
        })

# ============================================
# RUN THE SERVER
# ============================================
if __name__ == '__main__':
    print("=" * 50)
    print("🚀 Starting Margin Calculator Dashboard")
    print("=" * 50)
    print(f"📊 Stocks in demo table: GABRIEL, TIMETECHNO, KMEW, SIGNATURE, ORCHPHARMA, JYOTICNC")
    print(f"🔗 Open browser at: http://localhost:5000")
    print("=" * 50)
    app.run(debug=True, port=5000)
