# Algorithms and Data Structures

The completed CS 350 baseline is original/Thermostat.py. The enhanced implementation is in enhanced/Thermostat.py, enhanced/core.py, and enhanced/pi_adapter.py. The baseline and enhanced source are preserved from the supplied milestone; no separate starter or Thermostat_Completed.py file is included.

## Run without hardware

Use Python 3.10 or newer. From this category folder:

```bash
python3 -m unittest discover -s tests -v
python3 enhanced/Thermostat.py --simulate --seconds 65
```

The offline suite uses the Python standard library and has 19 tests. The simulation runs on a virtual clock; 65 seconds of simulated time complete quickly. Expected scheduled callbacks: sensor 65, commands 650, display 65, lights 260, serial 2. The scheduled light count excludes immediate light updates triggered by sampling or commands.

## Algorithm choices

The min heap gives O(1) access to the next deadline, O(log k) insertion/removal, and O(k) storage for k tasks. Monotonic deadlines skip missed periods instead of replaying a backlog. A fixed-size deque with a rolling sum gives O(1) average updates and O(w) storage for w samples. The five-sample default introduces smoothing delay. Hysteresis uses a 0.5 F margin on either side of the setpoint. The command queue holds at most 32 entries and each processing turn handles at most 32.

## Hardware boundary

The hardware adapter retains the LCD, AHT sensor, GPIO buttons/LEDs, and serial connection for the original circuit. On the correctly configured CS 350 Raspberry Pi environment, the entry point is python3 enhanced/Thermostat.py --hardware --seconds 65. Hardware libraries and wiring must match enhanced/pi_adapter.py. Physical integration was not verified during final packaging, and simulation is not a hardware latency or HVAC safety test.

Current evidence is in evidence/final-test-results.txt and evidence/final-simulation.txt. Earlier test_results.txt and simulation_output.txt are retained as milestone records.
