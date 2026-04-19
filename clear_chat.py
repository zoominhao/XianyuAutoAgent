import sqlite3, sys
db = sys.argv[1] if len(sys.argv) > 1 else "data/chat_history.db"
conn = sqlite3.connect(db)
conn.execute("DELETE FROM messages")
conn.execute("DELETE FROM chat_bargain_counts")
conn.execute("DELETE FROM agreed_prices")
conn.execute("DELETE FROM pending_orders")
conn.commit()
conn.close()
print("cleared chat data, kept items cache")
