# Netgear GS30XEPP PoE Control Hack for Home Assistant

This repository provides a **hacky integration** to control the PoE (Power over Ethernet) ports of Netgear GS30XEPP series switches directly from **Home Assistant**.  
It leverages a Python script to interact with the switch’s API and a set of Home Assistant configuration files to expose each port as a controllable entity.

## Tables Of Contents

- [Netgear GS30XEPP PoE Control Hack for Home Assistant](#netgear-gs30xepp-poe-control-hack-for-home-assistant)
  - [Tables Of Contents](#tables-of-contents)
  - [Overview](#overview)
  - [Python Script Logic](#python-script-logic)
    - [1. Hash Password](#1-hash-password)
    - [2. Login](#2-login)
    - [3. CSRF Protection](#3-csrf-protection)
    - [4. PoE Control](#4-poe-control)
    - [5. Logout](#5-logout)
    - [Deployment of the Python Script](#deployment-of-the-python-script)
      - [Installing Python Dependencies (requests \& beautifulsoup4)](#installing-python-dependencies-requests--beautifulsoup4)
  - [Home Assistant Configuration](#home-assistant-configuration)
    - [shell-command.yaml](#shell-commandyaml)
    - [scripts.yaml](#scriptsyaml)
    - [configuration.yaml](#configurationyaml)
    - [template.yaml](#templateyaml)
    - [secrets.yaml](#secretsyaml)
  - [Call Flow Diagram](#call-flow-diagram)
  - [API Testing with Bruno](#api-testing-with-bruno)
  - [Summary](#summary)
  - [Disclaimer](#disclaimer)

## Overview

- Control PoE per port on Netgear GS30XEPP switches.  
- Python script handles login, CSRF protection, API calls, and logout.  
- Home Assistant configuration integrates the script dynamically per port.  
- State management is handled via `input_boolean` entities to ensure reliability even if the script fails or Home Assistant restarts.

## Python Script Logic

The Python script follows a **5-step process**:

### 1. Hash Password

- Retrieve the hidden input element `rand`, which changes after each reboot of the switch.  
- Merge the plain-text `password` with the `rand` value using the Netgear interleaving algorithm.  
- Apply a standard MD5 hash to the merged string to generate the dynamic login hash.

### 2. Login

- Performs login with the hashed password calculated previously

### 3. CSRF Protection

- Retrieves a hidden hash field required to prevent **CSRF attacks**.  
- This token is mandatory for subsequent API modification calls.

### 4. PoE Control

- Sends an API call to **enable or disable PoE** on the target port.

### 5. Logout

- Logs out to release the session.

### Deployment of the Python Script

Before using the script in Home Assistant, you need to:

1. Copy the Python script [Netgear_GS30XEPP_POE_Control.py](/code/Home%20Assistant/Netgear_GS30XEPP_POE_Control.py) into the same directory as your Home Assistant configuration, typically alongside configuration.yaml.
2. Make the script executable by running the following command on your Home Assistant host:

```shell
chmod +x /config/Netgear_GS30XEPP_POE_Control.py
```

:warning: Make sure the file uses Unix-style line endings (LF) to ensure proper execution on Home Assistant OS.

#### Installing Python Dependencies (requests & beautifulsoup4)

Home Assistant OS does not include pip inside its system Python environment.
To run this script, you must manually install the required Python libraries in a persistent directory located under : `/config/python-libs/`

1. Create the local library directory

```shell
mkdir -p /config/python-libs
```

2. Install the dependencies using the Studio Code Server add-on (VS Code for Home Assistant) :

- Install the Studio Code Server add-on from the Home Assistant Add-on Store.
- Open the VS Code interface.
- Open a new terminal inside VS Code (Terminal → New Terminal).
- Install the required Python libraries directly into /config/python-libs : `pip install --target /config/python-libs requests beautifulsoup4`

## Home Assistant Configuration

The integration is designed to be **dynamic per port**. Several configuration files are used:

### shell-command.yaml

Defines the shell command to call the Python script with the required arguments:

```yaml
netgear_poe: '/usr/bin/python3 /config/Netgear_GS30XEPP_POE_Control.py {{ url }} {{ user }} {{ password }} {{ port }} {{ state }}'
```

Arguments :

- `url` : Switch URL
- `user` : Username (typically admin)
- `pass_hash` : Hashed password
- `port` : Target port number
- `state` : Desired state (on or off)

### scripts.yaml

Defines the poe_control service that:

- Calls the Python script to enable/disable PoE.
- Updates the associated `input_boolean` for the target port.

```yaml
poe_control:
  description: "Control PoE dynamically"
  fields:
    port:
      description: "Physical port number"
      example: 1
    state:
      description: "PoE state (on/off)"
      example: "on"
  sequence:
    - service: shell_command.netgear_poe
      data:
        url: !secret url_netgear_GS308EEP
        user: "admin"
        password: !secret pass_netgear_GS308EEP
        port: "{{ port }}"
        state: "{{ state }}"
    - service: "input_boolean.turn_{{ state }}" 
      target:
        entity_id: "input_boolean.gs308epp_poe_port{{ port }}_status"
  mode: queued
```

This ensures that the switch state is not updated if the script fails.
The script runs in mode: `queued` to buffer multiple activation/deactivation requests.

### configuration.yaml

Defines one `input_boolean` per port.

Each port’s `input_boolean` acts as a state holder:

- If the script fails, the switch entity does not incorrectly update its state.
- On restart, Home Assistant restores the last known state from the `input_boolean`.

```yaml
script: !include scripts.yaml
template: !include template.yaml
shell_command: !include shell-command.yaml

#-----------------input boolean-----------------
input_boolean:
  gs308epp_poe_port4_status:
    name: POE status GS308EPP PORT 4
  gs308epp_poe_port5_status:
    name: POE status GS308EPP PORT 5
  gs308epp_poe_port6_status:
    name: POE status GS308EPP PORT 6
  gs308epp_poe_port7_status:
    name: POE status GS308EPP PORT 7
  gs308epp_poe_port8_status:
    name: POE status GS308EPP PORT 8
```

### template.yaml

Defines the switch entities for each port.
These switches call the `poe_control` service from `scripts.yaml` with the correct arguments.

```yaml
- switch:
  - name: "POE Switch GS308EPP PORT 4"
    unique_id: gs308epp_poe_port4
    state: "{{ is_state('input_boolean.gs308epp_poe_port4_status', 'on') }}"
    turn_on:
      - service: script.poe_control
        data:
          port: 4
          state: "on"
    turn_off:
      - service: script.poe_control
        data:
          port: 4
          state: "off"
    icon: >
      {% if is_state('input_boolean.gs308epp_poe_port4_status', 'on') %}
        mdi:flash
      {% else %}
        mdi:flash-off
      {% endif %}
```

### secrets.yaml

Stores sensitive credentials:

```yaml
url_netgear_GS308EEP: "http://192.168.1.100"
pass_netgear_GS308EEP: "your_password_here"
```

## Call Flow Diagram

```yaml
User toggles switch in Home Assistant
        │
        ▼
script.poe_control (port, state)
        │
        ▼
shell_command.netgear_poe
        │
        ▼
Python script:
  - Compile Hash Password
  - Login
  - Get CSRF token
  - Send PoE command
  - Logout
        │
        ▼
Netgear GS30XEPP
```

## API Testing with Bruno

Before integrating the Python script into Home Assistant, it is recommended to test the Netgear GS30XEPP web API endpoints using an API client such as [Bruno](https://www.usebruno.com/).

- Bruno allows you to send HTTP requests to the switch’s web interface and validate responses.
- You can reproduce the sequence of calls used in the script via the [collection](https://github.com/vhuynen/Netgear-GS30XEPP-POE-Control/tree/main/Collection%20Bruno/Netgear%20GS30XEPP%20POE%20Control):
  - Login request with the hashed password.
  - Retrieval of the hidden CSRF token.
  - API call to enable/disable PoE on a specific port.
  - Logout request.
- This step ensures that your credentials, hash, and API parameters are correct before deploying the automation in Home Assistant.
- Using Bruno also makes it easier to debug issues if the firmware or API changes after an update.

## Summary

- Provides a hacky but effective way to control PoE ports on Netgear GS30XEPP switches.
- Python script handles login, CSRF token retrieval, PoE API calls, and logout.
- Home Assistant integration ensures dynamic port control, buffered requests, and reliable state management via input_boolean.
- Designed to be modular and easily extended to all ports of the switch.

## Disclaimer

This project is provided as a proof‑of‑concept hack to control PoE ports on Netgear GS30XEPP switches.

Please note the following:

- The Python script can be adjusted or extended depending on the parameters you want to manage on each port (Enabling/Disabling Port Power, Power Limit (W), Detection Type...).
- Netgear may update the switch firmware and change the underlying API. In such cases, the script logic (login, CSRF token retrieval, API calls) may need to be adapted to remain functional.
- This project is provided as-is for personal and educational use. Use at your own risk. Respect your device’s terms of service.

If you appreciate this project, please don’t hesitate to ⭐ it and feel free to provide your feedback !
