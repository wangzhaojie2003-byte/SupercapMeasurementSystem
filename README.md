Supercapacitor Characterisation System
======================================

This project implements a compact supercapacitor charge/discharge characterisation platform.  
It consists of two parts:
- STM32 firmware (for real-time voltage/current sensing and DAC control)
- Python host software (for GUI control, data logging, and automation)

--------------------------------------
Features
--------------------------------------
- Constant-current charge/discharge with ±1 A range
- Real-time acquisition of voltage and current via dual ADCs (STM32F446RE)
- PC GUI with live plots and sliders for current control
- Automatic polarity reversal (AutoFlip) at configurable voltage threshold
- CSV data logging with timestamped records for analysis
- Lightweight serial protocol:
  - "SET <voltage>" → set DAC output
  - "GET" → read back current DAC setting
  - Continuous UART stream of "mA,mV" samples

--------------------------------------
Repository Structure
--------------------------------------
SupercapTester/
├── Firmware/          # STM32 firmware (STM32CubeIDE project)
│   └── main.c
├── Host/              # Python host software
│   └── FinalHost.py
└── README.txt

--------------------------------------
Requirements
--------------------------------------

Firmware:
- STM32CubeIDE
- Target board: STM32F446RE (Nucleo-F446RE)
- UART connection to PC (default: USART2, 115200 baud)

Host (PC/Mac):
- Python 3.9+
- Install dependencies:
  pip install pyserial matplotlib

--------------------------------------
Usage
--------------------------------------

1. Flash the Firmware
- Open the "Firmware/" project in STM32CubeIDE
- Compile and flash to the Nucleo-F446RE board
- The firmware will stream current/voltage samples via UART at 115200 baud

2. Run the Host GUI
- Connect the board via USB (check COM port, default: COM4)
- Launch the GUI:
  python FinalHost.py
- The GUI provides:
  - Current slider / TextBox → set current from -1.0 A to +1.0 A
  - Live plots of current and voltage
  - AutoFlip when voltage ≥ 4.9 V
  - Keyboard shortcuts:
    - Left / Right arrows : adjust ±0.01 A
    - Up / Down arrows : adjust ±0.1 A
    - g : send GET command
    - s : save data immediately

3. Data Logging
- CSV files are automatically created in the working directory:
  supercap_data_YYYYMMDD_HHMMSS.csv
- Columns include:
  Timestamp, Time_s, Current_A, Voltage_V, Current_Set_A, Raw_mA, Raw_mV

--------------------------------------
Example Screenshot
--------------------------------------
<img width="1909" height="1277" alt="GUIInterface" src="https://github.com/user-attachments/assets/ae0a1582-6263-4c48-b15c-4f9e02c2f3bc" />

--------------------------------------
