import serial
import time
import os
import pandas as pd
from datetime import datetime

# ===== CSV File Prompt =====
default_filename = "voltage_current_capacity_log.csv"
csv_input = input("Enter CSV file name or full path to store logging data (default: 'voltage_current_capacity_log.csv'): ").strip()
if csv_input == "":
    LOG_FILENAME = default_filename
else:
    LOG_FILENAME = csv_input

# Ensure the directory exists if a path was provided
log_dir = os.path.dirname(LOG_FILENAME)
if log_dir and not os.path.exists(log_dir):
    os.makedirs(log_dir)

print(f"\nCSV logging will be stored at: {os.path.abspath(LOG_FILENAME)}\n")

# --- Configuration ---
VOLTAGE_PORT = '/dev/ttyUSB0'       # Voltage meter port
CURRENT_PORT = '/dev/ttyUSB1'       # Current meter port
BAUDRATE = 9600
TIMEOUT = 1
INTERVAL = 1                      # Sampling interval in seconds

def log_data(timestamp, voltage, current, power, energy, capacity, filename=LOG_FILENAME):
    """Append a row with timestamp, voltage, current, power, energy (Wh), and capacity (mAh) to a CSV file."""
    df = pd.DataFrame([[timestamp, voltage, current, power, energy, capacity]],
                      columns=["Timestamp", "Voltage (V)", "Current (A)", "Power (W)", "Energy (Wh)", "Capacity (mAh)"])
    df.to_csv(filename, mode='a', index=False, header=not os.path.exists(filename))

def get_valid_reading(ser, timeout=0.8):
    """
    Try reading from the serial port until a valid float is obtained or timeout expires.
    Returns the float value if successful; otherwise, returns None.
    """
    start_time = time.time()
    while (time.time() - start_time) < timeout:
        line = ser.readline()
        if line:
            try:
                return float(line.decode().strip())
            except ValueError:
                continue
        else:
            time.sleep(0.05)
    return None

def setup_instrument(ser, func_command, range_command):
    """
    Disable echo, set the measurement function, and configure the manual range.
    """
    ser.write(b"SYST:COMM:ECHO OFF\r\n")
    time.sleep(0.3)
    ser.write(func_command)
    time.sleep(0.3)
    ser.write(range_command)
    time.sleep(0.3)

def main():
    cumulative_energy_Wh = 0.0      # Energy in Wh
    cumulative_capacity_mAh = 0.0     # Capacity in mAh
    last_valid_voltage = None
    last_valid_current = None

    try:
        # Open both serial ports
        ser_voltage = serial.Serial(VOLTAGE_PORT, BAUDRATE, timeout=TIMEOUT)
        ser_current = serial.Serial(CURRENT_PORT, BAUDRATE, timeout=TIMEOUT)
        time.sleep(2)
        print(f"✅ Connected to {VOLTAGE_PORT} (Voltage) and {CURRENT_PORT} (Current)\n")
        
        # Optional: Query instrument IDs for verification
        ser_voltage.write(b"*IDN?\r\n")
        time.sleep(0.5)
        idn_voltage = ser_voltage.readline().decode().strip()
        ser_current.write(b"*IDN?\r\n")
        time.sleep(0.5)
        idn_current = ser_current.readline().decode().strip()
        print(f"Voltage Meter ID: {idn_voltage}")
        print(f"Current Meter ID: {idn_current}\n")
        
        # Setup voltage instrument: DC Voltage mode, manual range 20V
        setup_instrument(ser_voltage, b":FUNC VOLT:DC\r\n", b":VOLT:DC:RANG 20\r\n")
        # Setup current instrument: DC Current mode, manual range 0.02A (20 mA)
        setup_instrument(ser_current, b":FUNC CURR:DC\r\n", b":CURR:DC:RANG 0.02\r\n")
        
        print("📡 Starting dual logging for Voltage, Current, Power (W), Energy (Wh), and Capacity (mAh)...")
        print("Ensure both meters are in remote mode and connected properly.")
        print("Press Ctrl + C to stop.\n")
        
        while True:
            loop_start = time.time()
            
            # --- Voltage Measurement ---
            ser_voltage.reset_input_buffer()
            ser_voltage.write(b":FETCh?\r\n")
            time.sleep(0.2)
            voltage_reading = get_valid_reading(ser_voltage)
            if voltage_reading is not None:
                last_valid_voltage = voltage_reading
            else:
                if last_valid_voltage is not None:
                    voltage_reading = last_valid_voltage
                    print("⚠️ No new valid voltage reading; using last valid value.")
                else:
                    voltage_reading = float("nan")
                    print("⚠️ No voltage reading available.")
            
            # --- Current Measurement ---
            ser_current.reset_input_buffer()
            ser_current.write(b":FETCh?\r\n")
            time.sleep(0.2)
            current_reading = get_valid_reading(ser_current)
            if current_reading is not None:
                last_valid_current = current_reading
            else:
                if last_valid_current is not None:
                    current_reading = last_valid_current
                    print("⚠️ No new valid current reading; using last valid value.")
                else:
                    current_reading = float("nan")
                    print("⚠️ No current reading available.")
            
            # --- Instantaneous Power Calculation (W) ---
            power = voltage_reading * current_reading if voltage_reading is not None and current_reading is not None else float("nan")
            
            # --- Calculate Energy (Wh) and Capacity (mAh) Increments ---
            # Energy increment (Wh): (Power (W) × INTERVAL (s)) / 3600
            if power == power:  # Ensures power is not NaN
                energy_increment = (power * INTERVAL) / 3600.0
            else:
                energy_increment = 0.0
            cumulative_energy_Wh += energy_increment
            
            # Capacity increment (mAh): (Current (A) × 1000 × INTERVAL (s)) / 3600
            if current_reading == current_reading:
                capacity_increment = (current_reading * 1000 * INTERVAL) / 3600.0
            else:
                capacity_increment = 0.0
            cumulative_capacity_mAh += capacity_increment
            
            # Use microsecond resolution in the timestamp to avoid repetition
            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")
            print(f"{timestamp} - Voltage: {voltage_reading:.6f} V, Current: {current_reading:.6f} A, "
                  f"Power: {power:.6f} W, Energy: {cumulative_energy_Wh:.6f} Wh, Capacity: {cumulative_capacity_mAh:.2f} mAh")
            log_data(timestamp, voltage_reading, current_reading, power, cumulative_energy_Wh, cumulative_capacity_mAh)
            
            # Maintain approximately a 1-second interval per loop
            elapsed = time.time() - loop_start
            sleep_time = max(0, INTERVAL - elapsed)
            time.sleep(sleep_time)
    
    except KeyboardInterrupt:
        print("\n🛑 Logging stopped by user.")
    except serial.SerialException as e:
        print(f"❌ Serial error: {e}")
    finally:
        if 'ser_voltage' in locals() and ser_voltage.is_open:
            ser_voltage.write(b":DISP:ENAB 1\r\n")
            ser_voltage.close()
        if 'ser_current' in locals() and ser_current.is_open:
            ser_current.write(b":DISP:ENAB 1\r\n")
            ser_current.close()
        print("🔌 Serial ports closed.")

if __name__ == "__main__":
    main()
