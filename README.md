# 🔥 Free Fire Like Bot – API Guide

This API allows you to automatically send likes to **Free Fire profiles** using guest accounts.

---

## 🚀 Quick Start

Follow these steps to set up and run the API:

1. **Clone this repository** (if using Git):
    ```bash
    git clone https://github.com/paulafredo/free-api-like-freefire
    cd free-api-like-freefire
    ```

2. **Create and activate a virtual environment** (recommended):
    ```bash
    python -m venv venv
    ```
    - On Windows:
      ```bash
      venv\Scripts\activate
      ```
    - On Linux/macOS:
      ```bash
      source venv/bin/activate
      ```

3. **Install Python dependencies**:
    Make sure you have a `requirements.txt` file in your project directory. If not, you can generate it with:
    ```bash
    pip freeze > requirements.txt
    ```
    Then install the dependencies:
    ```bash
    pip install -r requirements.txt
    ```
    *Typical dependencies include `Flask`, `aiohttp`, `requests`, `pycryptodome`, `cachetools`, `python-dotenv`.*

4. **Go to the config folder**:
    ```bash
    cd config
    ```

5. **Add your configuration JSON files**:
    Inside the `config` folder, create the following files with your guest accounts:
    - `ind_config.json`
    - `br_config.json`
    - `europe_config.json`

6. **Run the Flask app**:
    ```bash
    flask run 
    ```
    

---


## ⚙️ Prerequisites

Before using this API, you must **create Free Fire guest accounts**. Please refer to the previous tutorial video for detailed steps.

---
## 📁 Configuration Details

The API uses region-specific JSON files to manage guest accounts.

### `ind_config.json`

- **Used for**: Guest accounts from the **India (IND)** server.
- **Format**:
```json
[
  {
    "uid": "YOUR_UID_1",
    "password": "YOUR_PASSWORD_1"
  },
  {
    "uid": "YOUR_UID_2",
    "password": "YOUR_PASSWORD_2"
  }
]
```

---

### `br_config.json`

- **Used for**: Guest accounts from:
  - `BR` (Brazil)  
  - `US` (United States)  
  - `SAC` (South America)  
  - `NA` (North America)

- **Format**: Same as above.

---

### `europe_config.json`

- **Used for**: Guest accounts from all **other servers** (e.g., Europe).
- **Format**: Same as above.

> Replace `"YOUR_UID_X"` and `"YOUR_PASSWORD_X"` with the actual Free Fire guest account credentials.

---

## 🖥️ API Endpoints

### `GET /like`

**Description**: Sends a "like" to a specific Free Fire profile.

**Query Parameters**:
- `uid` (required): The numeric UID of the player to like.

#### Example Request:
```http
GET /like?uid=1234567890
```
## 📜 Credits

This project was created by [Paul Alfredo](https://github.com/paulafredo).  
Feel free to check out his GitHub profile for more projects and contributions.

