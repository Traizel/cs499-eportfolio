"""CS 499 enhancement of the CS 350 thermostat; no hardware dependencies."""
from collections import deque
from dataclasses import dataclass, field
from enum import Enum
import heapq
import itertools
import math
import time
from typing import Callable


def finite_number(value, low, high):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError("Expected a numeric value")
    if not math.isfinite(value) or not low <= value <= high:
        raise ValueError("Value outside supported range")
    return float(value)


class MovingAverage:
    """Bounded O(w) storage, O(1) update and average lookup."""
    def __init__(self, window=5):
        if type(window) is not int or not 1 <= window <= 1000:
            raise ValueError("Window must be an integer from 1 to 1000")
        self.samples = deque(maxlen=window)
        self.total = 0.0

    def add(self, value):
        value = finite_number(value, -40, 185)  # AHT20 operating range in F
        # Subtract before maxlen would automatically discard the oldest value.
        if len(self.samples) == self.samples.maxlen:
            self.total -= self.samples.popleft()
        self.samples.append(value)
        self.total += value
        return self.average

    @property
    def average(self):
        return self.total / len(self.samples) if self.samples else None

    def clear(self):
        self.samples.clear()
        self.total = 0.0


class Mode(Enum):
    OFF = "off"
    HEAT = "heat"
    COOL = "cool"


class Thermostat:
    """Single-owner state machine. GPIO callbacks must enqueue commands."""
    def __init__(self, setpoint=72, hysteresis=0.5, window=5):
        self.setpoint = finite_number(setpoint, 50, 90)
        self.hysteresis = finite_number(hysteresis, 0.1, 5)
        self.filter = MovingAverage(window)
        self.mode = Mode.OFF
        self.active = False
        self.fault = True  # No valid reading yet.

    def sample(self, fahrenheit):
        try:
            self.filter.add(fahrenheit)
        except ValueError:
            self.sensor_fault()
            raise
        self.fault = False
        self.evaluate()

    def sensor_fault(self):
        self.fault = True
        self.active = False
        self.filter.clear()  # Do not reuse pre-failure samples on recovery.

    def cycle(self):
        modes = (Mode.OFF, Mode.HEAT, Mode.COOL)
        self.mode = modes[(modes.index(self.mode) + 1) % len(modes)]
        self.active = False
        self.evaluate()

    def set_target(self, value):
        self.setpoint = finite_number(value, 50, 90)
        self.evaluate()

    def adjust(self, delta):
        delta = finite_number(delta, -1, 1)
        self.set_target(max(50, min(90, self.setpoint + delta)))

    def evaluate(self):
        temp = self.filter.average
        if self.fault or temp is None or self.mode is Mode.OFF:
            self.active = False
        elif self.mode is Mode.HEAT:
            if temp <= self.setpoint - self.hysteresis:
                self.active = True
            elif temp >= self.setpoint + self.hysteresis:
                self.active = False
        elif self.mode is Mode.COOL:
            if temp >= self.setpoint + self.hysteresis:
                self.active = True
            elif temp <= self.setpoint - self.hysteresis:
                self.active = False

    def serial_line(self):
        if self.fault or self.filter.average is None:
            return None  # Suppress invalid readings; LCD/log reports the fault.
        temperature = finite_number(self.filter.average, -40, 185)
        target = finite_number(self.setpoint, 50, 90)
        return f"{self.mode.value},{temperature:.1f},{target:g}\n"


@dataclass(order=True)
class Event:
    due: float
    sequence: int
    interval: float = field(compare=False)
    callback: Callable[[], None] = field(compare=False)
    name: str = field(compare=False)


class Scheduler:
    """Cooperative min-heap scheduler; tasks are registered before run().

    O(log k) insertion/removal, O(1) earliest-deadline lookup, O(k) space.
    Fixed-rate deadlines skip missed periods instead of replaying a backlog.
    Callback failure propagates so the application can clean up and stop.
    """
    def __init__(self, clock=time.monotonic, sleep=time.sleep):
        self.clock, self.sleep = clock, sleep
        self.events = []
        self.sequence = itertools.count()

    def every(self, name, interval, callback, delay=0):
        interval = finite_number(interval, 0.001, 86400)
        delay = finite_number(delay, 0, 86400)
        if not callable(callback):
            raise ValueError("Task must be callable")
        heapq.heappush(self.events, Event(self.clock() + delay,
                       next(self.sequence), interval, callback, name))

    def run(self, duration):
        duration = finite_number(duration, 0, 86400)
        end = self.clock() + duration
        while self.events:
            now = self.clock()
            due = self.events[0].due
            if now >= end:
                return
            if due >= end:
                self.sleep(end - now)
                continue
            if due > now:
                self.sleep(due - now)
                continue  # Recheck the clock; sleep may return early.
            event = heapq.heappop(self.events)
            event.callback()
            now = self.clock()
            periods = max(1, math.floor((now - event.due) / event.interval) + 1)
            event.due += periods * event.interval
            heapq.heappush(self.events, event)
