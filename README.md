© 2024 Alexandru Chiric. All rights reserved.

# Black-Scholes-Vanilla-Options
 A C++ calculator for vanilla option prices and the associated Greeks

# 1. How to Install
The installation consists of 3 steps:
* Install Python 3.9.
* Create a venv to download packages
* Download the Notebook and install required python modules

These steps can be customized and some advanced users may choose to use existing python, use different folder structure or may have additional settings in their _pip.ini_

## 1.1. Install Python 3.9
Run the following command in your Terminal:
MacOS:

```bash
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
brew --version
brew install python
python3 --version
```

You can Create a Symlink for python3 and pip3 using:
```bash
sudo ln -s $(which python3) /usr/local/bin/python
sudo ln -s $(which pip3) /usr/local/bin/pip
```

## 1.2. Create a venv to download packages
Open a fresh terminal and run:
```bash
cd path/to/your/project
python -m venv venv_name
source venv/bin/activate
```

## 1.3. Download the required modules
Run the following commands in Terminal:
```bash
pip install -r requirements.txt
```

## How to Run 
Use the following command
```
python -m shiny run app_main.py --port 8000
```

