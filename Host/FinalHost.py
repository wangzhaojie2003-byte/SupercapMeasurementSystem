#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import re, time, threading, queue, sys, csv, os
from collections import deque
from threading import Lock
from datetime import datetime
import serial
import matplotlib.pyplot as plt
from matplotlib.animation import FuncAnimation
from matplotlib.widgets import Slider, TextBox, Button

# ===== Serial configuration =====
PORT = "COM4"       # Change to your serial port (e.g., "COM4" or "/dev/ttyACM0")
BAUD = 115200
LINE_RE = re.compile(r'^\s*(-?\d+)\s*,\s*(-?\d+)\s*$')  # Expecting lines like: "mA,mV"

# Data buffer size (covers 60 s window)
MAX_POINTS = 128000

# ===== Data logging configuration =====
ENABLE_LOGGING = True  # Set to False to disable data logging
LOG_INTERVAL = 0.1     # Log data every 0.1 seconds (10 Hz)

# ===== Auto flip configuration =====
AUTO_FLIP_ENABLE = True     
V_FLIP_THRESH = 4.9         
FLIP_COOLDOWN = 1.0         

# ---------- Data logger ----------
class DataLogger:
    def __init__(self, filename=None):
        self.logging_enabled = ENABLE_LOGGING
        self.log_interval = LOG_INTERVAL
        self.last_log_time = 0

        if self.logging_enabled:
            if filename is None:
                # Generate filename with timestamp
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                filename = f"supercap_data_{timestamp}.csv"

            self.filename = filename
            self.csv_file = None
            self.csv_writer = None
            self._open_file()

    def _open_file(self):
        try:
            self.csv_file = open(self.filename, 'w', newline='', encoding='utf-8')
            self.csv_writer = csv.writer(self.csv_file)
            # Write header
            self.csv_writer.writerow([
                'Timestamp', 'Time_s', 'Current_A', 'Voltage_V',
                'Current_Set_A', 'Raw_mA', 'Raw_mV'
            ])
            self.csv_file.flush()
            print(f"[DataLogger] Logging to: {self.filename}")
        except Exception as e:
            print(f"[DataLogger] Failed to open file {self.filename}: {e}")
            self.logging_enabled = False

    def log_data(self, t, current_a, voltage_v, current_set_a, raw_ma, raw_mv):
        if not self.logging_enabled or self.csv_writer is None:
            return

        # Check if enough time has passed since last log
        current_time = time.perf_counter()
        if current_time - self.last_log_time < self.log_interval:
            return

        self.last_log_time = current_time

        try:
            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]  # millisecond precision
            self.csv_writer.writerow([
                timestamp, f"{t:.3f}", f"{current_a:.6f}", f"{voltage_v:.6f}",
                f"{current_set_a:.6f}", raw_ma, raw_mv
            ])
            self.csv_file.flush()  # Ensure data is written immediately
        except Exception as e:
            print(f"[DataLogger] Error writing data: {e}")

    def close(self):
        if self.csv_file:
            try:
                self.csv_file.close()
                print(f"[DataLogger] Closed log file: {self.filename}")
            except:
                pass

# ---------- Serial reader thread ----------
def serial_reader(ser: serial.Serial, q: queue.Queue, stop_evt: threading.Event):
    ser.reset_input_buffer()
    buf = b""
    t0 = None
    while not stop_evt.is_set():
        try:
            chunk = ser.read(256)
            if not chunk:
                continue
            buf += chunk
            while b'\n' in buf:
                raw, buf = buf.split(b'\n', 1)
                s = raw.strip().decode(errors="ignore").rstrip('\r')
                m = LINE_RE.match(s)
                if not m:
                    continue
                mA = int(m.group(1)); mV = int(m.group(2))
                t = time.perf_counter()
                if t0 is None:
                    t0 = t
                q.put((t - t0, mA, mV))
        except Exception as e:
            print("[SerialReader]", e, file=sys.stderr)
            break
    q.put(None)

def main():
    # Initialize data logger
    data_logger = DataLogger()

    # Open serial port
    try:
        ser = serial.Serial(PORT, BAUD, timeout=0.05)
    except Exception as e:
        print(f"[ERR] open {PORT}@{BAUD} failed: {e}")
        sys.exit(2)

    tx_lock = Lock()
    def send_cmd(cmd: str):
        with tx_lock:
            ser.write(cmd.encode())

    # ==== Current setting → DAC voltage mapping ====
    # I_set ∈ [-1, +1] A  →  Vdac ∈ [0, 3.3] V
    def current_to_vdac(i_set: float) -> float:
        i = max(-1.0, min(1.0, float(i_set)))
        return (i + 1.0) * 0.5 * 3.3

    # Send SET command (current in A → mapped to DAC voltage in V)
    set_i = 0.000  # A
    def send_set_current(i_set: float) -> float:
        nonlocal set_i
        set_i = max(-1.0, min(1.0, float(i_set)))
        v = current_to_vdac(set_i)
        send_cmd(f"SET {v:.3f}\r\n")
        return set_i

    # ===== Small helpers: status + unified set ====
    def update_status():
        auto_status = "ON" if AUTO_FLIP_ENABLE else "OFF"
        log_status = "ON" if data_logger.logging_enabled else "OFF"
        status.set_text(
            f"SET={set_i:.3f} A   Window={int(time_window)} s   Logging={log_status}   AutoFlip={auto_status}"
        )
        fig.canvas.draw_idle()

    def apply_set_current(i_new: float):
        nonlocal set_i, slider_event_enabled
        set_i = send_set_current(i_new)
        slider_event_enabled = False
        sI.set_val(set_i)
        slider_event_enabled = True
        tb.set_val(f"{set_i:.3f}")
        update_status()

    # Start reader thread
    stop_evt = threading.Event()
    q = queue.Queue(maxsize=20000)
    th = threading.Thread(target=serial_reader, args=(ser, q, stop_evt), daemon=True)
    th.start()

    # ======= UI layout =======
    fig = plt.figure("Supercap control", figsize=(11, 7))

    # Top: two plots
    axI = plt.axes([0.09, 0.62, 0.82, 0.25])   # [left, bottom, width, height]
    axV = plt.axes([0.09, 0.35, 0.82, 0.20])
    axI.grid(True); axV.grid(True)
    axI.set_ylabel("Current (A)")
    axV.set_ylabel("Voltage (V)")
    axV.set_xlabel("Time (s)")
    # Fixed y-axis ranges
    axI.set_ylim(-1.5, 1.5)
    axV.set_ylim(0.0, 6.0)

    # Status text (slightly lower at bottom=0.29)
    axStatus = plt.axes([0.09, 0.29, 0.82, 0.03]); axStatus.axis("off")
    time_window = 10.0
    log_status = "ON" if data_logger.logging_enabled else "OFF"
    auto_status = "ON" if AUTO_FLIP_ENABLE else "OFF"
    status = axStatus.text(0.0, 0.5,
        f"SET=0.000 A   Window={int(time_window)} s   Logging={log_status}   AutoFlip={auto_status}",
        fontsize=10, va="center", ha="left")

    # Time window slider (1–60 s)
    axWin = plt.axes([0.09, 0.25, 0.82, 0.04])
    sWin = Slider(axWin, "Time window (s)", 1.0, 60.0, valinit=time_window, valstep=1.0)

    # Current slider (instead of DAC (V))
    axDAC = plt.axes([0.09, 0.185, 0.82, 0.04])
    sI = Slider(axDAC, "Current (A)", -1.0, 1.0, valinit=set_i, valstep=0.001)
    slider_event_enabled = True

    # Go to (A) input box (instead of Go to (V))
    axTB = plt.axes([0.09, 0.135, 0.82, 0.045])
    tb = TextBox(axTB, "Go to (A):", initial=f"{set_i:.3f}")

    # GET and Save buttons
    axGET = plt.axes([0.09, 0.08, 0.40, 0.045])
    btn = Button(axGET, "GET")

    axSAVE = plt.axes([0.51, 0.08, 0.40, 0.045])
    btn_save = Button(axSAVE, "Save Data Now")

    # Data buffers
    tbuf = deque(maxlen=MAX_POINTS)
    ibuf = deque(maxlen=MAX_POINTS)
    vbuf = deque(maxlen=MAX_POINTS)
    lI, = axI.plot([], [], lw=1)
    lV, = axV.plot([], [], lw=1)

    # ---------- Backend scaling ----------
    # Incoming data: mA, mV values actually represent ADC voltage × 1000
    def v_adc_from_mA(mA: int) -> float:
        return mA / 1000.0
    def v_adc_from_mV(mV: int) -> float:
        return mV / 1000.0
    # Voltage: ADC 0–3.3 V → 0–5 V
    def scale_voltage(Vadc: float) -> float:
        return Vadc * (5.0 / 3.3)
    # Current: ADC 0–3.0 V → -1–+1 A
    def scale_current(Vadc: float) -> float:
        return (Vadc / 3.0) * 2.0 - 1.0

    # ---------- UI callbacks ----------
    def on_win(val):
        nonlocal time_window
        time_window = float(val)
        update_status()
    sWin.on_changed(on_win)

    def on_current_slider(val):
        if not slider_event_enabled:
            return
        apply_set_current(val)
    sI.on_changed(on_current_slider)

    def on_tb(text):
        try:
            i = float(text)
        except ValueError:
            tb.set_val(f"{set_i:.3f}")
            return
        apply_set_current(i)
    tb.on_submit(on_tb)

    def on_get(_):
        send_cmd("GET\r\n")
    btn.on_clicked(on_get)

    def on_save(_):
        if data_logger.logging_enabled and data_logger.csv_file:
            data_logger.csv_file.flush()
            print(f"[DataLogger] Data saved to: {data_logger.filename}")
        else:
            print("[DataLogger] Logging is disabled or file not open")
    btn_save.on_clicked(on_save)

    # Keyboard shortcuts: arrows for +/- current, g = GET, s = Save
    def on_key(evt):
        nonlocal set_i
        if evt.key == 'right':
            apply_set_current(min(1.0, set_i + 0.01)); return
        elif evt.key == 'left':
            apply_set_current(max(-1.0, set_i - 0.01)); return
        elif evt.key == 'up':
            apply_set_current(min(1.0, set_i + 0.10)); return
        elif evt.key == 'down':
            apply_set_current(max(-1.0, set_i - 0.10)); return
        elif evt.key == 'g':
            send_cmd("GET\r\n"); return
        elif evt.key == 's':
            on_save(None); return
        else:
            return
    fig.canvas.mpl_connect('key_press_event', on_key)

    # ---------- Animator ----------
    last_flip_time = 0.0  # perf_counter of last auto flip

    def on_timer(_):
        nonlocal last_flip_time
        got = False
        while True:
            try:
                item = q.get_nowait()
            except queue.Empty:
                break
            if item is None:
                plt.close(fig); return
            t, mA, mV = item
            Vi = v_adc_from_mA(mA)
            Vv = v_adc_from_mV(mV)
            I = scale_current(Vi)    # A
            V = scale_voltage(Vv)    # V
            tbuf.append(t); ibuf.append(I); vbuf.append(V)

            # Log data
            data_logger.log_data(t, I, V, set_i, mA, mV)

            # --- Auto flip (+I -> -I) when voltage reaches threshold ---
            if AUTO_FLIP_ENABLE:
                now = time.perf_counter()
                if (set_i > 0.0) and (V >= V_FLIP_THRESH) and (now - last_flip_time >= FLIP_COOLDOWN):
                    # Flip to negative with same magnitude
                    apply_set_current(-abs(set_i))
                    last_flip_time = now
                    print(f"[AutoFlip] V={V:.3f} V >= {V_FLIP_THRESH:.3f} V → current flipped to {set_i:.3f} A")

            got = True

        if got:
            lI.set_data(list(tbuf), list(ibuf))
            lV.set_data(list(tbuf), list(vbuf))
            if tbuf:
                tmax = tbuf[-1]
                tmin = max(0.0, tmax - time_window)
                axI.set_xlim(tmin, tmax)
                axV.set_xlim(tmin, tmax)
        return lI, lV

    ani = FuncAnimation(fig, on_timer, interval=10, blit=False)

    try:
        plt.show()
    finally:
        stop_evt.set()
        data_logger.close()  # Close the log file
        try:
            ser.close()
        except:
            pass

if __name__ == "__main__":
    main()
