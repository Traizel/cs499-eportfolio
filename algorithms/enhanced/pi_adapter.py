"""Hardware adapter retaining the wiring and LED semantics of the original.

Hardware imports occur only when explicitly running on a Raspberry Pi.
Physical integration has not been tested in the development container.
"""
from contextlib import ExitStack
from core import Mode


class RaspberryPi:
    def __init__(self):
        import board
        import digitalio
        import adafruit_ahtx0
        import adafruit_character_lcd.character_lcd as characterlcd
        import serial
        from gpiozero import Button, PWMLED

        self.resources = ExitStack()
        self.previous_lights = None
        try:
            i2c = board.I2C()
            self.resources.callback(i2c.deinit)
            self.sensor = adafruit_ahtx0.AHTx0(i2c)
            self.uart = serial.Serial('/dev/ttyS0', 115200, timeout=1, write_timeout=1)
            self.resources.callback(self.uart.close)
            self.red, self.blue = PWMLED(18), None
            self.resources.callback(self.red.close)
            self.blue = PWMLED(23)
            self.resources.callback(self.blue.close)
            pins = []
            for pin in (board.D17, board.D27, board.D5, board.D6, board.D13, board.D26):
                handle = digitalio.DigitalInOut(pin)
                pins.append(handle)
                self.resources.callback(handle.deinit)
            self.lcd = characterlcd.Character_LCD_Mono(*pins, 16, 2)
            self.resources.callback(self.lcd.clear)
            self.lcd.clear()
            self.buttons = []
            for pin in (24, 25, 12):
                button = Button(pin, bounce_time=0.05)
                self.resources.callback(button.close)
                self.buttons.append(button)
        except BaseException:
            self.resources.close()
            raise

    def bind_buttons(self, enqueue):
        for button, command in zip(self.buttons, ("cycle", "up", "down")):
            button.when_pressed = lambda cmd=command: enqueue(cmd)

    def read_temperature(self):
        return self.sensor.temperature * 9 / 5 + 32

    def display(self, first, second):
        self.lcd.cursor_position(0, 0)
        self.lcd.message = first + "\n" + second

    def lights(self, mode, active, fault):
        state = (mode, active, fault)
        if state == self.previous_lights:
            return  # Do not restart the PWM pulse at each scheduler tick.
        self.red.off()
        self.blue.off()
        if not fault and mode is not Mode.OFF:
            led = self.red if mode is Mode.HEAT else self.blue
            led.pulse() if active else led.on()
        self.previous_lights = state

    def serial(self, line):
        data = line.encode("ascii")
        if self.uart.write(data) != len(data):
            raise OSError("Incomplete UART write")

    def close(self):
        # ExitStack is idempotent and also releases partially opened hardware.
        self.resources.close()
