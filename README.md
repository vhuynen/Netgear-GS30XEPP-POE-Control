# Netgear GS30XEPP PoE Control Hack for Home Assistant

This repository provides a **hacky integration** to control the PoE (Power over Ethernet) ports of Netgear GS30XEPP series switches directly from **Home Assistant**.  
It leverages a Python script to interact with the switch’s API and a set of Home Assistant configuration files to expose each port as a controllable entity.

## Tables Of Contents

- [Netgear GS30XEPP PoE Control Hack for Home Assistant](#netgear-gs30xepp-poe-control-hack-for-home-assistant)
  - [Tables Of Contents](#tables-of-contents)
  - [Overview](#overview)
  - [Prerequisite: Retrieve the Login Hash](#prerequisite-retrieve-the-login-hash)
  - [Python Script Logic](#python-script-logic)
    - [1. Login](#1-login)
    - [2. CSRF Protection](#2-csrf-protection)
    - [3. PoE Control](#3-poe-control)
    - [4. Logout](#4-logout)
    - [Deployment of the Python Script](#deployment-of-the-python-script)
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

## Prerequisite: Retrieve the Login Hash

The login requires only the **hashed password**.  

To obtain it:

1. Open browser developer tools.
2. Go to the **Network** tab and enable **Preserve Log**.  
3. Perform a login attempt and locate the `login.cgi` call.  
4. In the **Payload**, copy the value of the `password` attribute.  

This hash is used directly by the script.

## Python Script Logic

The Python script follows a **4-step process**:

### 1. Login

- Performs login with a **35-second timeout**.  
- Implements **retry** logic because the web server may take time to wake up on the first call.

### 2. CSRF Protection

- Retrieves a hidden hash field required to prevent **CSRF attacks**.  
- This token is mandatory for subsequent API modification calls.

### 3. PoE Control

- Sends an API call to **enable or disable PoE** on the target port.

### 4. Logout

- Logs out to release the session.

> 💡 The script includes a shebang (`#!/usr/bin/env python3`) to simplify execution within Home Assistant.

### Deployment of the Python Script

Before using the script in Home Assistant, you need to:

1. Copy the Python script (Netgear_GS30XEPP_POE_Control.py) into the same directory as your Home Assistant configuration, typically alongside configuration.yaml.
2. Make the script executable by running the following command on your Home Assistant host:

```shell
chmod +x /config/Netgear_GS30XEPP_POE_Control.py
```

## Home Assistant Configuration

The integration is designed to be **dynamic per port**. Several configuration files are used:

### shell-command.yaml

Defines the shell command to call the Python script with the required arguments:

```yaml
netgear_poe: "bash -c '/config/Netgear_GS30XEPP_POE_Control.py {{ url }} {{ user }} {{ pass_hash }} {{ port }} {{ state }}'"
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
        pass_hash: !secret hash_netgear_GS308EEP
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
hash_netgear_GS308EEP: "your_password_hash_here"
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
