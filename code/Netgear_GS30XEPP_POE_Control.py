#!/usr/bin/env python3

import sys
import requests
from bs4 import BeautifulSoup
import time

# --- CONSTANTS ---
# General command parameters for PoE configuration
ACTION = 'Apply'
PORT_PRIO = '0'
POW_MOD = '3'
POW_LIMT_TYP = '2'
POW_LIMT = '30.0'
DETEC_TYP = '2'
DISCONNECT_TYP = '2'

# Robustness settings for connection
TIMEOUT_SEC = 35     # Generous timeout to handle slow switch startup
MAX_RETRIES = 3      # Max attempts for the initial login phase
RETRY_DELAY = 5      # Seconds to wait between retries

def control_poe(base_url, user, pass_hash, physical_port, state):
    """
    Controls the PoE state (on/off) for a specific physical port on the Netgear switch.

    Args:
        base_url (str): Switch's base URL (e.g., http://192.168.0.2).
        user (str): Username (not strictly needed for auth).
        pass_hash (str): The pre-hashed password for authentication.
        physical_port (int): The physical port number (1 to N).
        state (str): 'on' or 'off'.
    """
    
    # Map desired state to switch's internal ADMIN_MODE value
    admin_mode = '1' if state.lower() == 'on' else '0'
    
    # Calculate switch's internal portID (Physical Port - 1)
    port_id = str(physical_port - 1) 

    # --- URL DEFINITIONS ---
    URL_LOGIN_POST = f"{base_url}/login.cgi" 
    URL_GET_HASH = f"{base_url}/dashboard.cgi" 
    URL_APPLY_POE = f"{base_url}/PoEPortConfig.cgi" 
    URL_LOGOUT_POST = f"{base_url}/logout.cgi" 

    with requests.Session() as s:
        
        # --- 1. AUTHENTICATION LOOP (Robust Login - Direct POST) ---
        retry_count = 0
        logged_in = False
        
        while retry_count < MAX_RETRIES and not logged_in:
            try:
                print(f"Attempting direct POST login (Try {retry_count + 1}/{MAX_RETRIES})...")
                
                # Direct POST: Sends the password hash via URL parameter to establish session.
                login_url_with_hash = f"{URL_LOGIN_POST}?password={pass_hash}"
                s.post(login_url_with_hash, timeout=TIMEOUT_SEC) 
                
                # If POST succeeds without throwing an exception, we assume logged in.
                logged_in = True 
                
            except requests.exceptions.Timeout:
                retry_count += 1
                if retry_count < MAX_RETRIES:
                    print(f"Connection timed out. Retrying in {RETRY_DELAY}s...")
                    time.sleep(RETRY_DELAY)
                else:
                    print(f"FATAL: Failed to connect after {MAX_RETRIES} attempts due to timeout.", file=sys.stderr)
                    sys.exit(1)
            
            except requests.exceptions.RequestException as e:
                # Handle non-timeout critical errors (e.g., connection refused)
                print(f"FATAL: Critical connection error during login POST: {e}", file=sys.stderr)
                sys.exit(1)

        # --- 2. RETRIEVE GLOBAL CSRF HASH (GET Dashboard) ---
        # Must be done after successful login to get the hash for the new session.
        try:
            # Scrape the 'hash' attribute from the dashboard page for CSRF protection
            response_hash = s.get(URL_GET_HASH, timeout=TIMEOUT_SEC)
            soup = BeautifulSoup(response_hash.text, 'html.parser')
            
            # Look for the hidden input field named 'hash'
            hash_input = soup.find('input', {'type': 'hidden', 'name': 'hash'}) 
            
            if not hash_input:
                print("FATAL: Could not find the hidden 'hash' attribute.", file=sys.stderr)
                sys.exit(1)
                
            security_hash = hash_input.get('value')
            
        except requests.exceptions.RequestException as e:
            print(f"FATAL: Error retrieving dashboard/CSRF hash: {e}", file=sys.stderr); sys.exit(1)
        
        # --- 3. SEND POE CONTROL COMMAND (POST /PoEPortConfig.cgi) ---
        try:
            # All parameters, including the hash, are passed as URL parameters
            poe_params = {
                'hash': security_hash,
                'ACTION': ACTION, 
                'portID': port_id, 
                'ADMIN_MODE': admin_mode,
                'PORT_PRIO': PORT_PRIO,
                'POW_MOD': POW_MOD,
                'POW_LIMT_TYP': POW_LIMT_TYP,
                'POW_LIMT': POW_LIMT,
                'DETEC_TYP': DETEC_TYP,
                'DISCONNECT_TYP': DISCONNECT_TYP
            }
            
            response_apply = s.post(URL_APPLY_POE, params=poe_params, timeout=TIMEOUT_SEC)
            
            # 4. VERIFICATION
            if response_apply.status_code == 200:
                print(f"SUCCESS: PoE for physical port {physical_port} set to {state.upper()}.")
            else:
                print(f"ERROR: PoE command failed. Status code: {response_apply.status_code}", file=sys.stderr); sys.exit(1)

        except requests.exceptions.RequestException as e:
            print(f"FATAL: Error during POST PoE Command: {e}", file=sys.stderr); sys.exit(1)
        
        #--- 4. SEND LOGOUT COMMAND
        try:
            response_logout = s.post(URL_LOGOUT_POST, verify=False)
        except requests.exceptions.ConnectionError:
            print("SUCCESS: Logout !")

if __name__ == "__main__":
    if len(sys.argv) != 6:
        print("Usage: python netgear_poe_control.py [URL] [USER] [PASS_HASH] [PORT_ID] [STATE (on/off)]", file=sys.stderr)
        sys.exit(1)

    # Argument validation and assignment
    base_url = sys.argv[1]
    user = sys.argv[2]
    pass_hash = sys.argv[3]
    try:
        physical_port = int(sys.argv[4])
    except ValueError:
        print("FATAL: Port number must be an integer.", file=sys.stderr); sys.exit(1)
    
    state = sys.argv[5]
    
    control_poe(base_url, user, pass_hash, physical_port, state)
