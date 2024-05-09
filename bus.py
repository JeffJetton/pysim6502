################################################################################
#
#   Bus Class
#
#   Basically, all parts of the computer except the CPU.
#   Tracks RAM and ROM, handles reads/writes/input/output
#
#   Provides helper functions to read files into memory, convert hex, etc.
#
#   By design, models 64K of memory in member variable mem
#   Tracks access separately using is_writeable and is_readable
#   If throw_memory_errors is False, attempts to read/write unreadable or
#   unwriteable memory will just quietly fail (as in the real world),
#   otherwise, a SimError is raised
#
#   This class is designed to be subclassed, with the subclass taking care
#   of implementation details specific to a particular system being simulated.
#
################################################################################

import random
from sim_error import SimError

class Bus():

    mem_size = 0x10000

    def __init__(self, random_state=False, throw_memory_errors=True):
        self.mem = [0] * self.mem_size
        self.is_writeable = [True] * self.mem_size
        self.is_readable = [True] * self.mem_size
        if random_state:
            self.randomize_state()
        self.throw_memory_errors = throw_memory_errors
        self.interrupt = None
        self.delay = 0
        self.stdscr = None
        # Standard screen settings
        self.scr_settings = {'rows': 24,
                             'cols': 80,
                             'scroll_on': True,
                             'echo_on': True,
                             'wait_for_enter': True,
                             'keypad_on': True,
                             'input_delay_on': True}


    def __str__(self):
        def get_status_desc(r, w):
            if r and w:
                return 'Read/Write'
            if r:
                return 'Read-Only'
            if w:
                return 'Write-Only'
            return 'Not Used'
        s = ''
        prev_status = None
        block_start = 0
        block_end = 0
        for i in range(self.mem_size):
            current_status = get_status_desc(self.is_readable[i], self.is_writeable[i])
            if prev_status is None:
                prev_status = current_status
            if current_status != prev_status:
                s += f'  {block_start:04X}-{block_end:04X}: {prev_status}\n'
                block_start = i
                prev_status = current_status
            block_end = i
        # Close out last block
        s += f'  {block_start:04X}-{block_end:04X}: {prev_status}\n'
        # Show other bus settings
        s += f'Output Delay: {int(self.delay*1000000)}μs\n'
        s += 'Memory Errors: '
        s += 'ON' if self.throw_memory_errors else 'OFF'
        return s



    def randomize_state(self):
        for i in range(self.mem_size):
            self.mem[i] = random.randrange(0x100)


    def read(self, address):
        '''Returns contents of memory at address
    
        If address is not a readable location, raises SimError if throw_memory_errors is True, returns zero otherwise
        ''' 
        address = address & 0xFFFF
        if self.is_readable[address]:
            value = self.mem[address]
        else:
            if self.throw_memory_errors:
                raise SimError(f'Attempt to read from unreadable address ${address:04X}')
            else:
                value = 0
        return value


    def write(self, address, value):
        '''Write value to memory at address
    
        If address is not writeable, raises SimError if throw_memory_errors is True, does nothing otherwise
        '''
        address = address & 0xFFFF
        value = value & 0xFF
        if self.is_writeable[address]:
            self.mem[address] = value
        elif self.throw_memory_errors:
            raise SimError(f'Attempt to write value ${value:02X} to unwriteable address ${address:04X}')


    def parse_hex(self, s):
        """Helper function to parse a valid hex string into an integer
        Does not check to see if value is in the correct range
        """
        hexval = None
        try:
            hexval = int(s, 16)
        except ValueError:
            print('Invalid hex input')
        return hexval


    def read_file(self, filename, address_start=0, format=None, ignore_bytes=0):
        '''Read in the given file into memory, assuming the passed format,
        starting at addr_start. Can optionially ignore some number of leading
        bytes/characters in the file.
        
        Formats (pass as a string):
        
            raw - Raw binary file
            hex - Two-digit hex values, separated by whitespace (origin address ignored!)
            woz - Wozmonitor output format (hex with leading address) TODO:
            
        Default format is raw.
        
        Does not check to ensure all addresses are writeable and does not raise errors if not
        '''
        if format is None or format == 'raw':
            with open(filename, 'rb') as infile:
                # Read raw bytes into bin_data
                bin_data = infile.read()
                # Chop off any ignore bytes
                bin_data = bin_data[ignore_bytes:]
                
        elif format == 'woz':
            with open(filename, 'r') as infile:
                lines = infile.readlines()
                bin_data = []
                for line in lines:
                    bytes = line.split()
                    consumed_first = False
                    for byte in bytes:
                        if consumed_first:
                            bin_data.append(self.parse_hex(byte))
                        else:
                            consumed_first = True
        else:
            # TODO: Support other formats
            raise ValueError(f'"{format}" format is not supported')
            
        # By this point we should have the bytes in bin_data
        for i, b in enumerate(bin_data):
            address = (address_start + i) & 0xFFFF
            self.mem[address] = b


