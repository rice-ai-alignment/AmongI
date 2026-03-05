import os
from dotenv import load_dotenv
from google import genai

# 1. Load your .env file
load_dotenv()
api_key = os.getenv("GOOGLE_API_KEY")

if not api_key:
    print("❌ ERROR: GOOGLE_API_KEY not found in .env file.")
else:
    print(f"✅ API Key loaded (starts with: {api_key[:5]}...)")

# 2. Initialize the Client
client = genai.Client(api_key=api_key)

try:
    print("Sending test request to Gemini...")
    
    # 3. Simple request using the high-speed Flash model
    response = client.models.generate_content(
        model="gemini-2.5-flash", 
        contents="Say 'Connection Successful' if you can read this."
    )
    
    # 4. Print result
    print("-" * 30)
    print("GEMINI RESPONSE:", response.text)
    print("-" * 30)
    print("🚀 API is working perfectly!")

except Exception as e:
    print("❌ API REQUEST FAILED!")
    print(f"Error Details: {e}")