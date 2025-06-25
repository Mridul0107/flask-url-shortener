import sqlite3
import os

def create_database():
    """Create the database and tables for URL shortener"""
    
    # Create database directory if it doesn't exist
    db_dir = 'database'
    if not os.path.exists(db_dir):
        os.makedirs(db_dir)
    
    # Connect to database (creates if doesn't exist)
    conn = sqlite3.connect('database/urls.db')
    cursor = conn.cursor()
    
    # Create urls table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS urls (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            original_url TEXT NOT NULL,
            short_code TEXT UNIQUE NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            click_count INTEGER DEFAULT 0
        )
    ''')
    
    # Create index for faster lookups
    cursor.execute('''
        CREATE INDEX IF NOT EXISTS idx_short_code ON urls(short_code)
    ''')
    
    # Commit changes and close connection
    conn.commit()
    conn.close()
    
    print("✅ Database created successfully!")
    print("📁 Database location: database/urls.db")
    print("📋 Table 'urls' created with columns: id, original_url, short_code, created_at, click_count")

def check_database():
    """Check if database exists and show table info"""
    db_path = 'database/urls.db'
    
    if os.path.exists(db_path):
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        # Get table info
        cursor.execute("PRAGMA table_info(urls)")
        columns = cursor.fetchall()
        
        print(f"✅ Database exists at: {db_path}")
        print("📋 Table structure:")
        for col in columns:
            print(f"   - {col[1]} ({col[2]})")
        
        # Get record count
        cursor.execute("SELECT COUNT(*) FROM urls")
        count = cursor.fetchone()[0]
        print(f"📊 Records in database: {count}")
        
        conn.close()
    else:
        print("❌ Database not found!")
        return False
    
    return True

if __name__ == "__main__":
    print("🔧 URL Shortener Database Migration")
    print("=" * 40)
    
    if not check_database():
        print("\n🚀 Creating new database...")
        create_database()
    else:
        print("\n✨ Database already exists and is ready to use!")