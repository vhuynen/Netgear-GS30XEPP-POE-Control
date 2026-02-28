#!/usr/bin/env python3

import sys
import time
import hashlib

# Make local libraries available (packages copied under /config/python-libs)
# Required folders to exist under /config/python-libs:
#   requests/, urllib3/, idna/, certifi/, charset_normalizer/ (or chardet/), bs4/, soupsieve/
sys.path.insert(0, "/config/python-libs")

import requests
from bs4 import BeautifulSoup

# --- CONSTANTS ---
# General parameters for PoE configuration
ACTION = 'Apply'
PORT_PRIO = '0'
POW_MOD = '3'
POW_LIMT_TYP = '2'
POW_LIMT = '30.0'
DETEC_TYP = '2'
DISCONNECT_TYP = '2'

# Connection robustness settings
TIMEOUT_SEC = 35     # Generous timeout to handle slow switch startup
MAX_RETRIES = 3      # Maximum attempts for the initial dynamic-hash step
RETRY_DELAY = 5      # Seconds to wait between retries


def control_poe(base_url, user, password, physical_port, state):
    """
    Controls the PoE state (on/off) for a specific physical port on the Netgear switch.

    Args:
        base_url (str): Switch base URL (e.g., http://192.168.0.2).
        user (str): Username (not used in this flow, kept for compatibility).
        password (str): Plain-text password.
        physical_port (int): Physical port number (1..N).
        state (str): 'on' or 'off'.
    """

    # Map requested state to the switch's ADMIN_MODE value
    admin_mode = '1' if state.lower() == 'on' else '0'

    # Compute the internal portID expected by the switch (physical port - 1)
    port_id = str(physical_port - 1)

    # --- URL DEFINITIONS ---
    URL_LOGIN_GET = f"{base_url}/login.cgi"       # GET to obtain challenge 'rand'
    URL_LOGIN_POST = f"{base_url}/login.cgi"      # POST to authenticate with the hash
    URL_GET_DASH = f"{base_url}/dashboard.cgi"    # GET to retrieve session CSRF hash
    URL_APPLY_POE = f"{base_url}/PoEPortConfig.cgi"
    URL_LOGOUT_POST = f"{base_url}/logout.cgi"

    with requests.Session() as s:

        # 1) Retrieve the dynamic challenge and compute the dynamic hash (with retries)
        dynamic_hash = None
        attempt = 0

        while attempt < MAX_RETRIES and dynamic_hash is None:
            attempt += 1
            try:
                print(f"[Step 1] Fetching login challenge 'rand' (attempt {attempt}/{MAX_RETRIES})...")
                resp = s.get(URL_LOGIN_GET, timeout=TIMEOUT_SEC)
                resp.raise_for_status()

                soup = BeautifulSoup(resp.text, 'html.parser')
                rand_field = soup.find('input', {'id': 'rand'})

                if not rand_field or not rand_field.get('value'):
                    raise RuntimeError("Missing 'rand' field on login page.")

                rand_value = rand_field['value']

                # Netgear merge algorithm: interleave password and rand characters
                merged_chars = []
                max_len = max(len(password), len(rand_value))
                for i in range(max_len):
                    if i < len(password):
                        merged_chars.append(password[i])
                    if i < len(rand_value):
                        merged_chars.append(rand_value[i])

                merged = ''.join(merged_chars)
                dynamic_hash = hashlib.md5(merged.encode('utf-8')).hexdigest()

            except (requests.exceptions.Timeout, requests.exceptions.ConnectionError) as e:
                if attempt < MAX_RETRIES:
                    print(f"Timeout/connection error while retrieving hash: {e}. "
                          f"Retrying in {RETRY_DELAY}s...")
                    time.sleep(RETRY_DELAY)
                else:
                    print(f"FATAL: Failed to obtain dynamic hash after {MAX_RETRIES} attempts.",
                          file=sys.stderr)
                    sys.exit(1)

            except Exception as e:
                if attempt < MAX_RETRIES:
                    print(f"Challenge not ready ('{e}'). Retrying in {RETRY_DELAY}s...")
                    time.sleep(RETRY_DELAY)
                else:
                    print(f"FATAL: Unable to get login challenge after {MAX_RETRIES} attempts: {e}",
                          file=sys.stderr)
                    sys.exit(1)

        # 2) Authenticate with the dynamic hash (no retry by design)
        try:
            print("[Step 2] Authenticating with dynamic hash...")
            payload = {'password': dynamic_hash}
            resp_login = s.post(URL_LOGIN_POST, data=payload, timeout=TIMEOUT_SEC)
            resp_login.raise_for_status()
        except requests.exceptions.Timeout:
            print("FATAL: Timeout during authentication.", file=sys.stderr)
            sys.exit(1)
        except requests.exceptions.RequestException as e:
            print(f"FATAL: Authentication error: {e}", file=sys.stderr)
            sys.exit(1)

        # 3) Retrieve session-wide CSRF hash from dashboard
        try:
            print("[Step 3] Retrieving session CSRF hash...")
            response_hash = s.get(URL_GET_DASH, timeout=TIMEOUT_SEC)
            response_hash.raise_for_status()

            soup = BeautifulSoup(response_hash.text, 'html.parser')
            hash_input = soup.find('input', {'type': 'hidden', 'name': 'hash'})

            if not hash_input or not hash_input.get('value'):
                print("FATAL: Hidden 'hash' (CSRF) field not found.", file=sys.stderr)
                sys.exit(1)

            security_hash = hash_input.get('value')

        except requests.exceptions.RequestException as e:
            print(f"FATAL: Error while retrieving CSRF hash from dashboard: {e}", file=sys.stderr)
            sys.exit(1)

        # 4) Send PoE control command
        try:
            print("[Step 4] Applying PoE configuration...")
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
            if response_apply.status_code == 200:
                print(f"SUCCESS: PoE for physical port {physical_port} set to {state.upper()}.")
            else:
                print(f"ERROR: PoE command failed. Status code: {response_apply.status_code}", file=sys.stderr)
                sys.exit(1)

        except requests.exceptions.RequestException as e:
            print(f"FATAL: Error while sending PoE command: {e}", file=sys.stderr)
            sys.exit(1)

        # 5) Logout
        try:
            s.post(URL_LOGOUT_POST, verify=False)
            print("SUCCESS: Logout !")
        except requests.exceptions.ConnectionError:
            print("SUCCESS: Logout !")


if __name__ == "__main__":
    if len(sys.argv) != 6:
        print("Usage: python netgear_poe_control.py [URL] [USER] [PASSWORD] [PORT_ID] [STATE (on/off)]", file=sys.stderr)
        print("Note: Provide the plain-text password, not a hash.", file=sys.stderr)
        sys.exit(1)

    base_url = sys.argv[1]
    user = sys.argv[2]
    password = sys.argv[3]
    try:
        physical_port = int(sys.argv[4])
    except ValueError:
        print("FATAL: Port number must be an integer.", file=sys.stderr)
        sys.exit(1)

    state = sys.argv[5]
    control_poe(base_url, user, password, physical_port, state)