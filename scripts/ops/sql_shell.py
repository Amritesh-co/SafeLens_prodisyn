import sqlite3
import sys

def run_query(query):
    try:
        conn = sqlite3.connect('db.sqlite3')
        cursor = conn.cursor()
        cursor.execute(query)
        columns = [description[0] for description in cursor.description] if cursor.description else []
        rows = cursor.fetchall()
        
        # Print header
        if columns:
            print(" | ".join(columns))
            print("-" * (len(" | ".join(columns))))
            
        # Print rows
        for row in rows:
            print(" | ".join(str(item) for item in row))
            
        conn.close()
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    if len(sys.argv) > 1:
        query = " ".join(sys.argv[1:])
        run_query(query)
    else:
        print("Usage: python3 sql_shell.py <SQL_QUERY>")
