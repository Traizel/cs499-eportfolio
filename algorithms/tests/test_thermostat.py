"""Behavior and boundary tests, executable without Raspberry Pi libraries."""
import math
from pathlib import Path
import random
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "enhanced"))
from core import MovingAverage, Thermostat, Scheduler, Mode
from Thermostat import Application, VirtualClock


class FilterTests(unittest.TestCase):
    def test_warmup_and_eviction(self):
        f = MovingAverage(3)
        self.assertIsNone(f.average)
        self.assertEqual([f.add(x) for x in (60, 63, 66, 69)], [60, 61.5, 63, 66])
        self.assertEqual(list(f.samples), [63, 66, 69])

    def test_reference_agreement_long_stream(self):
        rng = random.Random(499)
        f = MovingAverage(17)
        reference = []
        for _ in range(10000):
            value = rng.uniform(50, 90)
            reference = (reference + [value])[-17:]
            self.assertAlmostEqual(f.add(value), sum(reference) / len(reference), places=9)
        self.assertEqual(len(f.samples), 17)

    def test_invalid_inputs_do_not_mutate_filter(self):
        f = MovingAverage(1)
        f.add(72)
        for value in (math.nan, math.inf, -41, 186, "72", True, None):
            with self.assertRaises(ValueError):
                f.add(value)
            self.assertEqual(f.average, 72)

    def test_window_bounds(self):
        for size in (0, -1, 1001, 2.5, True):
            with self.assertRaises(ValueError):
                MovingAverage(size)


class ControlTests(unittest.TestCase):
    def test_heat_hysteresis_and_boundaries(self):
        t = Thermostat(window=1)
        t.cycle()
        actual = []
        for temp in (71.5, 72, 72.49, 72.5, 72, 71.51, 71.5):
            t.sample(temp)
            actual.append(t.active)
        self.assertEqual(actual, [True, True, True, False, False, False, True])

    def test_cool_hysteresis_and_boundaries(self):
        t = Thermostat(window=1)
        t.cycle(); t.cycle()
        actual = []
        for temp in (72.5, 72, 71.51, 71.5, 72, 72.49, 72.5):
            t.sample(temp)
            actual.append(t.active)
        self.assertEqual(actual, [True, True, True, False, False, False, True])

    def test_mode_cycle_and_off(self):
        t = Thermostat(window=1)
        t.sample(65)
        t.cycle()
        self.assertTrue(t.active)
        t.cycle()
        self.assertFalse(t.active)
        t.cycle()
        self.assertEqual(t.mode, Mode.OFF)
        self.assertFalse(t.active)

    def test_setpoint_validation_and_button_clamp(self):
        t = Thermostat(setpoint=90)
        t.adjust(1)
        self.assertEqual(t.setpoint, 90)
        t.set_target(50); t.adjust(-1)
        self.assertEqual(t.setpoint, 50)
        for value in (49, 91, math.nan, "72", True):
            with self.assertRaises(ValueError):
                t.set_target(value)
            self.assertEqual(t.setpoint, 50)

    def test_fault_clears_history_and_recovers(self):
        t = Thermostat()
        t.cycle(); t.sample(60)
        self.assertTrue(t.active)
        with self.assertRaises(ValueError):
            t.sample(math.nan)
        self.assertFalse(t.active)
        self.assertIsNone(t.serial_line())
        t.sample(80)
        self.assertEqual(t.filter.average, 80)
        self.assertFalse(t.fault)
        self.assertFalse(t.active)

    def test_serial_format(self):
        t = Thermostat(window=1)
        self.assertIsNone(t.serial_line())
        t.sample(72.25); t.cycle()
        self.assertEqual(t.serial_line(), "heat,72.2,72\n")


class SchedulerTests(unittest.TestCase):
    def test_equal_deadlines_are_stable(self):
        clock = VirtualClock(); s = Scheduler(clock, clock.sleep); calls = []
        for name in ("sensor", "display", "serial"):
            s.every(name, 1, lambda n=name: calls.append((clock(), n)))
        s.run(2)
        self.assertEqual(calls, [(tick, name) for tick in (0, 1)
                                for name in ("sensor", "display", "serial")])
        self.assertEqual(len(s.events), 3)

    def test_mixed_intervals_and_sleep(self):
        clock = VirtualClock(); s = Scheduler(clock, clock.sleep); calls = []
        s.every("fast", 2, lambda: calls.append(("fast", clock())))
        s.every("slow", 5, lambda: calls.append(("slow", clock())), delay=5)
        s.run(11)
        self.assertEqual([t for n,t in calls if n == "fast"], [0,2,4,6,8,10])
        self.assertEqual([t for n,t in calls if n == "slow"], [5,10])
        self.assertEqual(clock(), 11)

    def test_overrun_skips_backlog_without_drift(self):
        clock = VirtualClock(); s = Scheduler(clock, clock.sleep); calls = []
        def slow():
            calls.append(clock()); clock.sleep(2.4)
        s.every("slow", 1, slow)
        s.run(7)
        self.assertEqual(calls, [0, 3, 6])
        self.assertEqual(s.events[0].due, 9)

    def test_early_sleep_return_does_not_run_early(self):
        clock = VirtualClock(); calls = []
        def interrupted_sleep(seconds):
            clock.sleep(min(seconds, 0.125))
        s = Scheduler(clock, interrupted_sleep)
        s.every("event", 1, lambda: calls.append(clock()), delay=1)
        s.run(1.5)
        self.assertEqual(calls, [1])

    def test_interval_validation(self):
        s = Scheduler()
        for interval in (0, -1, math.nan, math.inf, True):
            with self.assertRaises(ValueError):
                s.every("bad", interval, lambda: None)


class FakeDevice:
    def __init__(self):
        self.value = 68
        self.closed = False
        self.messages = []
        self.frames = []
        self.states = []

    def read_temperature(self):
        if isinstance(self.value, Exception):
            raise self.value
        return self.value

    def display(self, first, second): self.frames.append((first, second))
    def lights(self, mode, active, fault): self.states.append((mode, active, fault))
    def serial(self, line): self.messages.append(line)
    def close(self): self.closed = True


class ApplicationTests(unittest.TestCase):
    def test_end_to_end_cadence_and_cleanup(self):
        clock = VirtualClock(); device = FakeDevice()
        app = Application(device, clock, clock.sleep)
        app.enqueue("cycle"); app.run(61)
        self.assertEqual(app.counts["sensor"], 61)
        self.assertEqual(app.counts["serial"], 2)
        self.assertEqual(device.messages, ["heat,68.0,72\n"] * 2)
        self.assertEqual(app.counts["display"], 61)
        self.assertTrue(all(len(a) == len(b) == 16 for a,b in device.frames))
        self.assertTrue(device.closed)

    def test_sensor_failure_and_recovery(self):
        device = FakeDevice(); app = Application(device)
        app.enqueue("cycle"); app.process_commands(); app.sample()
        device.value = OSError("disconnected"); app.sample(); app.serial()
        self.assertTrue(app.model.fault)
        self.assertEqual(device.messages, [])
        self.assertEqual(device.states[-1], (Mode.HEAT, False, True))
        device.value = 80; app.sample(); app.serial()
        self.assertFalse(app.model.fault)
        self.assertEqual(device.messages, ["heat,80.0,72\n"])

    def test_queue_is_bounded_and_commands_validate(self):
        app = Application(FakeDevice())
        for _ in range(33): app.enqueue("up")
        self.assertEqual(app.commands.qsize(), 32)
        app.process_commands()
        self.assertEqual(app.model.setpoint, 90)
        with self.assertRaises(ValueError): app.enqueue("invalid")

    def test_unexpected_output_failure_closes_device(self):
        clock = VirtualClock(); device = FakeDevice()
        def fail(*args): raise OSError("display failed")
        device.display = fail
        app = Application(device, clock, clock.sleep)
        with self.assertRaises(OSError): app.run(2)
        self.assertTrue(device.closed)


if __name__ == "__main__":
    unittest.main(verbosity=2)
