"""Run with --simulate (default) on a computer, or --hardware on the CS 350 Pi."""
import argparse
from collections import Counter
from datetime import datetime, timedelta
import logging
import math
from queue import Queue, Empty, Full
import time

from core import Scheduler, Thermostat, Mode


class VirtualClock:
    def __init__(self):
        self.now = 0.0

    def __call__(self):
        return self.now

    def sleep(self, seconds):
        self.now += seconds


class Simulation:
    def __init__(self, clock):
        self.clock = clock
        self.previous_lights = None

    def read_temperature(self):
        return 72 + 3 * math.sin(self.clock() / 5)

    def display(self, first, second):
        print(f"{self.clock():6.1f}s LCD |{first}|{second}|")

    def lights(self, mode, active, fault):
        state = (mode, active, fault)
        if state != self.previous_lights:
            print(f"{self.clock():6.1f}s LED mode={mode.value} active={active} fault={fault}")
            self.previous_lights = state

    def serial(self, line):
        print(f"{self.clock():6.1f}s UART {line.strip()}")

    def close(self):
        print("Simulation closed; indicators off.")


class Application:
    def __init__(self, device, clock=time.monotonic, sleep=time.sleep,
                 wall_clock=datetime.now):
        self.device = device
        self.clock = clock
        self.wall_clock = wall_clock
        self.started = clock()
        self.model = Thermostat()
        self.commands = Queue(maxsize=32)
        self.counts = Counter()
        self.scheduler = Scheduler(clock, sleep)
        for name, interval, callback, delay in (
            ("sensor", 1, self.sample, 0),
            ("commands", 0.1, self.process_commands, 0),
            ("display", 1, self.display, 0),
            ("lights", 0.25, self.lights, 0),
            ("serial", 30, self.serial, 30),
        ):
            def counted(fn=callback, task=name):
                self.counts[task] += 1
                fn()
            self.scheduler.every(name, interval, counted, delay)

    def enqueue(self, command):
        if command not in ("cycle", "up", "down"):
            raise ValueError("Unknown button command")
        try:
            self.commands.put_nowait(command)
        except Full:
            logging.warning("Button queue full; command dropped")

    def process_commands(self):
        # Bounded work per turn prevents button traffic starving other tasks.
        for _ in range(32):
            try:
                command = self.commands.get_nowait()
            except Empty:
                break
            if command == "cycle":
                self.model.cycle()
            else:
                self.model.adjust(1 if command == "up" else -1)
        self.lights()  # Apply button changes without another sampling delay.

    def sample(self):
        try:
            self.model.sample(self.device.read_temperature())
        except (OSError, RuntimeError, ValueError):
            self.model.sensor_fault()
            logging.warning("Sensor unavailable or invalid; indicators disabled")
        self.lights()

    def display(self):
        first = self.wall_clock().strftime("%b %d  %H:%M:%S")
        if self.model.fault:
            second = "SENSOR ERROR"
        elif int((self.clock() - self.started) // 5) % 2 == 0:
            second = f"Temp: {self.model.filter.average:.1f} F"
        else:
            second = f"{self.model.mode.value} Set:{self.model.setpoint:g} F"
        self.device.display(first[:16].ljust(16), second[:16].ljust(16))

    def lights(self):
        self.device.lights(self.model.mode, self.model.active, self.model.fault)

    def serial(self):
        line = self.model.serial_line()
        if line is not None:
            self.device.serial(line)

    def run(self, seconds):
        try:
            self.scheduler.run(seconds)
        finally:
            self.device.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--simulate", action="store_true")
    mode.add_argument("--hardware", action="store_true")
    parser.add_argument("--seconds", type=float, default=None)
    args = parser.parse_args()
    logging.basicConfig(level=logging.WARNING)
    if args.hardware:
        from pi_adapter import RaspberryPi
        device = RaspberryPi()
        try:
            app = Application(device)
            device.bind_buttons(app.enqueue)
            app.run(args.seconds if args.seconds is not None else 3600)
        finally:
            device.close()
    else:
        clock = VirtualClock()
        device = Simulation(clock)
        app = Application(device, clock, clock.sleep,
                          lambda: datetime(2026, 9, 27, 12) + timedelta(seconds=clock()))
        app.enqueue("cycle")  # Begin demonstration in heat mode.
        app.scheduler.every("demo_mode", 20, lambda: app.enqueue("cycle"), delay=20)
        app.run(args.seconds if args.seconds is not None else 65)
        print("Task counts:", dict(app.counts))


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("Stopped.")
