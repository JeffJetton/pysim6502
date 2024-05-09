################################################################################
#
#   Apple 1 Bus
#
#   Subclass of Bus Class that attempts to simulate an Apple 1
#
################################################################################

from bus import Bus
import curses
import time

class SystemBus(Bus):
    
    def __init__(self, random_state=False, throw_memory_errors=True):
        super().__init__(random_state, throw_memory_errors)
        # Adjust memory map.  Only first half of address space is RAM
        for i in range(0x8000, 0x10000):
            self.is_writeable[i] = False
        # Except for I/O (handled separately) first part of last half is unused
        for i in range(0x8000, 0xE000):
            self.is_readable[i] = False
        # Load WozMon
        self.read_file('./software/wozmon.bin', 0xFF00)
        # Load BASIC
        self.read_file('./software/intbasic.txt', 0xE000, format='woz')
        # Keyboard and display registers
        self.kbd = 0
        self.dsp = 0
        # A bit of authentic delay (not quite as much as the real thing though)
        self.delay = 0.005


    def __str__(self):
        s = 'Apple 1 Bus\n'
        s += super().__str__()
        s += '\nAddresses D010-D013 used for input/output'
        return s


    def read(self, address):
        address = address & 0xFFFF
        if address == 0xD010:    # KBD (Keyboard Data)
            # Return contents of buffer register and clear it
            temp = self.kbd
            self.kbd = 0
            return temp
        elif address == 0xD011:  # KBD CR (Keyboard Control)
            # We actually do the key input here, but don't return it.
            # Instead we return a signal that a key is ready. The CPU
            # will have to make another call (to 0x10) to fetch it.
            if self.stdscr is not None:
                k = self.stdscr.getch()
            else:
                k = curses.ERR
            if k == curses.ERR:
                # No key data available
                return 0
            # Control-R? (Reset computer)
            if k == 18:
                self.interrupt = 'RES'
            # Control-E? (Stop simulation)
            if k == 5:
                self.interrupt = 'HLT'
            # Convert lowercase to upper
            if 97 <= k <= 122:
                k -= 32
            # Convert linefeed to carriage return
            if k == 10:
                k = 13
            # Convert delete to underscore (for some reason)
            if k == 127:
                k = 95
            # Store the ASCII code with bit 7 flipped on, because
            # that's how the Apple 1's weird keyboard worked.
            self.kbd = k | 0x80
            # Return bit 7 high, signaling ready state
            return 0x80
        elif address == 0xD012:  # DSP (Display) register
            # Bit 7 is off when display is "ready" (and it's always ready!)
            return 0
        # Otherwise, let parent handle
        return super().read(address)


    def write(self, address, value):
        address = address & 0xFFFF
        value = value & 0xFF
        # Display Data Register
        if address == 0xD012:
            # Put it in the buffer for reference/debugging
            self.dsp = value
            # Strip off the top bit
            value = value & 0x7F
            # Shift lowercase range down to uppercase range
            if value > 95:
                value -= 32
            # Give it a bit of authentic delay
            time.sleep(self.delay)
            # Only print printable characters
            if (32 <= value <= 95) or value == 13:
                # Convert CR to LF
                if value == 13:
                    value = 10
                # Send to screen
                if self.stdscr is not None:
                    self.stdscr.addstr(chr(value))
            # Always refresh, whether we printed or not
            if self.stdscr is not None:
                self.stdscr.refresh()
            return
        if address in (0xD011, 0xD013):
            # ignore
            return
        # Pass all other addresses/values to parent...
        super().write(address, value)
