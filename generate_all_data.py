"""
Quick script to generate all synthetic data for the Retail AI Agent.
Run this before starting the application for the first time.
"""

import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent))

from data.generate_data import main as generate_all_data

if __name__ == "__main__":
    print("=" * 60)
    print(" RETAIL AI AGENT - DATA GENERATION")
    print("=" * 60)
    print()
    
    try:
        generate_all_data()
        
        print("\n" + "=" * 60)
        print(" ✅ SUCCESS! All data files have been created.")
        print("=" * 60)
        print()
        print("Next steps:")
        print("1. Make sure your .env file is configured")
        print("2. Run: python app.py (to start API server)")
        print("3. Run: streamlit run streamlit_app.py (to start UI)")
        print()
        
    except Exception as e:
        print("\n" + "=" * 60)
        print(" ❌ ERROR during data generation")
        print("=" * 60)
        print(f"\nError: {str(e)}")
        print("\nPlease ensure:")
        print("- Python dependencies are installed (pip install -r requirements.txt)")
        print("- You have write permissions to the data directory")
        sys.exit(1)
