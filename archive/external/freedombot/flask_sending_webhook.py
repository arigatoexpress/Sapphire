from flask import Flask, request, jsonify
import requests
import threading  # for parallel sending
import mysql.connector
import os

app = Flask(__name__)

# URLs of individual Flask setups
ENDPOINTS = [
    "http://endpoint_person_a/webhook",  # Person A
    "http://endpoint_person_b/webhook"  # Person B
]

# MySQL database configuration
db_params = {
    "host": os.environ.get("DB_HOST", "your_mysql_host"),
    "database": os.environ.get("DB_NAME", "your_database_name"),
    "user": os.environ.get("DB_USER", "your_username"),
    "password": os.environ.get("DB_PASSWORD", "your_password")
}

def get_db_connection():
    """Establish a connection to the database."""
    try:
        conn = mysql.connector.connect(**db_params)
        return conn
    except mysql.connector.Error as err:
        print(f"Error connecting to the database: {err}")
        return None

def save_to_database(data):
    """Save the incoming data to the database."""
    conn = get_db_connection()
    if not conn:
        print("Failed to connect to database")
        return
    
    try:
        cursor = conn.cursor()

        # Create the table if it doesn't exist
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS signals (
                id INT AUTO_INCREMENT PRIMARY KEY,
                ticker VARCHAR(50),
                action VARCHAR(10),
                price FLOAT,
                open_price FLOAT,
                high_price FLOAT,
                low_price FLOAT,
                close_price FLOAT,
                volume INT,
                time DATETIME,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # Insert data into the table
        cursor.execute("""
            INSERT INTO signals (ticker, action, price, open_price, high_price, low_price, close_price, volume, time)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
        """, (
            data.get("ticker", "unknown"),
            data.get("action", "unknown"),
            float(data.get("price", 0)),
            float(data.get("open", 0)),
            float(data.get("high", 0)),
            float(data.get("low", 0)),
            float(data.get("close", 0)),
            int(data.get("volume", 0)),
            data.get("time", None)
        ))
        
        conn.commit()
        cursor.close()
    except mysql.connector.Error as err:
        print(f"Database error: {err}")
    finally:
        conn.close()

def forward_signal(endpoint, data):
    """Send the signal to individual Flask setups."""
    try:
        response = requests.post(endpoint, json=data)
        print(f"Sent to {endpoint}: {response.status_code}")
    except Exception as e:
        print(f"Error sending to {endpoint}: {e}")

@app.route('/webhook', methods=['POST'])
def webhook():
    data = request.json

    # Validate payload
    required_fields = ['action', 'price', 'open', 'high', 'low', 'close', 'volume', 'time', 'ticker']
    if not data or not all(field in data for field in required_fields):
        return jsonify({"status": "Invalid payload"}), 400

    # Save to database
    threading.Thread(target=save_to_database, args=(data,)).start()

    # Forward to endpoints
    threads = []
    for endpoint in ENDPOINTS:
        t = threading.Thread(target=forward_signal, args=(endpoint, data))
        t.start()
        threads.append(t)

    for t in threads:
        t.join()

    return jsonify({"status": "Signal sent to all and saved to database"}), 200

if __name__ == "__main__":
    app.run(port=5000)
