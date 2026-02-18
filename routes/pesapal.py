import os
import json
import uuid
import requests
import urllib3
from dotenv import load_dotenv

# Load environment variables early
load_dotenv()
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

class PesaPal:
    def __init__(self):
        self.auth_url = "https://pay.pesapal.com/v3/api/Auth/RequestToken"
        self.api_url = "https://pay.pesapal.com/v3/api/"
        self.token = None

        self.consumer_key = os.getenv("PESAPAL_CONSUMER_KEY")
        self.consumer_secret = os.getenv("PESAPAL_CONSUMER_SECRET")
        self.ipn_url = os.getenv("PESAPAL_IPN_URL", "https://yourdomain.com/ipn")

        # Register IPN only after authentication
        self.ipn_id = None

    def authenticate(self):
        """Authenticate with PesaPal and get access token"""
        try:
            payload = json.dumps({
                "consumer_key": self.consumer_key,
                "consumer_secret": self.consumer_secret
            })
            headers = {
                'Content-Type': 'application/json', 
                'Accept': 'application/json',
                'User-Agent': 'CapitalCollege/1.0'
            }

            print("🔄 Authenticating with PesaPal...")
            response = requests.post(
                self.auth_url, 
                headers=headers, 
                data=payload, 
                verify=False,
                timeout=30
            )
            response.raise_for_status()
            
            data = response.json()
            self.token = data['token']
            print("✅ PesaPal authentication successful")
            
            # Register IPN after getting token
            self.ipn_id = self.register_ipn_url()
            return self.token
            
        except requests.exceptions.RequestException as e:
            print(f"❌ PesaPal authentication failed: {e}")
            return None
        except Exception as e:
            print(f"❌ Unexpected error during authentication: {e}")
            return None

    def register_ipn_url(self):
        """Register IPN URL with PesaPal"""
        try:
            endpoint = "URLSetup/RegisterIPN"
            payload = json.dumps({
                "url": self.ipn_url, 
                "ipn_notification_type": "GET"
            })
            headers = {
                'Content-Type': 'application/json', 
                'Accept': 'application/json', 
                'Authorization': f"Bearer {self.token}",
                'User-Agent': 'CapitalCollege/1.0'
            }
            
            print("🔄 Registering IPN URL...")
            response = requests.post(
                self.api_url + endpoint, 
                headers=headers, 
                data=payload, 
                verify=False,
                timeout=30
            )
            response.raise_for_status()
            
            data = response.json()
            print(f"✅ IPN registered successfully: {data['ipn_id']}")
            return data['ipn_id']
            
        except Exception as e:
            print(f"❌ IPN Registration failed: {e}")
            return None

    def submit_order(self, amount, reference_id, callback_url, email, first_name, last_name):
        """Submit order to PesaPal for payment processing"""
        if not self.token:
            if not self.authenticate():
                return None

        try:
            endpoint = "Transactions/SubmitOrderRequest"
            payload = json.dumps({
                "id": reference_id,
                "currency": "UGX",
                "amount": str(amount),
                "description": "Student Payment - Capital College",
                "callback_url": callback_url,
                "notification_id": self.ipn_id,
                "billing_address": {
                    "email_address": email,
                    "phone_number": "",  # Optional
                    "country_code": "UG",
                    "first_name": first_name,
                    "middle_name": "",
                    "last_name": last_name,
                    "line_1": "Capital College",
                    "line_2": "",
                    "city": "Kampala",
                    "state": "",
                    "postal_code": "",
                    "zip_code": ""
                }
            })
            
            headers = {
                'Content-Type': 'application/json', 
                'Accept': 'application/json', 
                'Authorization': f"Bearer {self.token}",
                'User-Agent': 'CapitalCollege/1.0'
            }

            print(f"🔄 Submitting order to PesaPal: UGX {amount}, Ref: {reference_id}")
            response = requests.post(
                self.api_url + endpoint, 
                headers=headers, 
                data=payload, 
                verify=False,
                timeout=30
            )
            response.raise_for_status()
            
            data = response.json()
            print(f"✅ Order submitted successfully: {data['order_tracking_id']}")
            return data
            
        except requests.exceptions.RequestException as e:
            print(f"❌ Order submission failed: {e}")
            return None
        except Exception as e:
            print(f"❌ Unexpected error in order submission: {e}")
            return None

    def verify_transaction_status(self, order_tracking_id):
        """Verify transaction status with PesaPal"""
        if not self.token:
            if not self.authenticate():
                return None

        try:
            endpoint = f"Transactions/GetTransactionStatus?orderTrackingId={order_tracking_id}"
            headers = {
                'Content-Type': 'application/json', 
                'Accept': 'application/json', 
                'Authorization': f"Bearer {self.token}",
                'User-Agent': 'CapitalCollege/1.0'
            }

            print(f"🔄 Verifying transaction status: {order_tracking_id}")
            response = requests.get(
                self.api_url + endpoint, 
                headers=headers, 
                verify=False,
                timeout=30
            )
            response.raise_for_status()
            
            data = response.json()
            print(f"✅ Transaction status: {data.get('status', 'UNKNOWN')}")
            return data
            
        except requests.exceptions.RequestException as e:
            print(f"❌ Transaction verification failed: {e}")
            return None
        except Exception as e:
            print(f"❌ Unexpected error in transaction verification: {e}")
            return None