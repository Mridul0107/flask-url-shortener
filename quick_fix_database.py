#!/usr/bin/env python3
"""
Quick fix for URL Shortener database schema
Run this script to add missing columns to your existing database
"""

import sqlite3
import os
import sys
from datetime import datetime

def quick_fix():
    """Quick fix for the missing is_active column issue"""
    
    db_path = 'urls.db'
    
    # Check if database exists
    if not os.path.exists(db_path):
        print("❌ Database 'urls.db' not found in current directory")
        print("Make sure you're running this script from your Flask app directory")
        return False
    
    try:
        print("🔧 Applying quick fix to database...")
        
        # Connect to database
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        # Check if is_active column exists
        cursor.execute("PRAGMA table_info(url)")
        columns = [col[1] for col in cursor.fetchall()]
        
        if 'is_active' not in columns:
            print("➕ Adding is_active column...")
            cursor.execute("ALTER TABLE url ADD COLUMN is_active BOOLEAN DEFAULT 1 NOT NULL")
            print("✅ Added is_active column")
        else:
            print("ℹ️  is_active column already exists")
        
        # Add other missing columns if they don't exist
        missing_columns = {
            'expires_at': 'DATETIME',
            'click_limit': 'INTEGER', 
            'description': 'TEXT',
            'category_id': 'INTEGER'
        }
        
        for col_name, col_type in missing_columns.items():
            if col_name not in columns:
                try:
                    cursor.execute(f"ALTER TABLE url ADD COLUMN {col_name} {col_type}")
                    print(f"✅ Added {col_name} column")
                except sqlite3.OperationalError as e:
                    print(f"⚠️  {col_name}: {e}")
        
        # Update existing records to be active
        cursor.execute("UPDATE url SET is_active = 1 WHERE is_active IS NULL OR is_active = 0")
        updated = cursor.rowcount
        if updated > 0:
            print(f"✅ Set {updated} existing URLs to active")
        
        # Create click_log table if it doesn't exist
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS click_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                url_id INTEGER NOT NULL,
                clicked_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                ip_address VARCHAR(100),
                user_agent TEXT,
                referrer TEXT,
                FOREIGN KEY (url_id) REFERENCES url (id)
            )
        ''')
        print("✅ Created/verified click_log table")
        
        # Create category table if needed
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS category (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name VARCHAR(50) UNIQUE NOT NULL,
                emoji VARCHAR(5),
                color VARCHAR(7) DEFAULT '#384361',
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        print("✅ Created/verified category table")
        
        # Commit changes
        conn.commit()
        conn.close()
        
        print("\n🎉 Quick fix completed successfully!")
        print("Your Flask app should now work without the column error.")
        
        return True
        
    except Exception as e:
        print(f"❌ Quick fix failed: {e}")
        return False

if __name__ == "__main__":
    print("🚀 URL Shortener Quick Database Fix")
    print("=" * 40)
    
    if quick_fix():
        print("\n💡 Next steps:")
        print("1. Your database has been updated")
        print("2. Restart your Flask application") 
        print("3. The 'is_active' column error should be resolved")
        print("\n🏃‍♂️ You can now run: python app.py")
    else:
        print("\n💥 Fix failed. Please check the error messages above.")
        sys.exit(1)