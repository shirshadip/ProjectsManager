from dotenv import load_dotenv
import os

load_dotenv()

correct_username = os.getenv("USERNAME")
correct_password = os.getenv("PASSWORD")

username = input("Username: ")
password = input("Password: ")

if username.strip().lower() == correct_username.strip().lower() and password == correct_password:
    print("Login successful")
else:
    print("Invalid username or password")
    