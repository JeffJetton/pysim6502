################################################################################
#
#   CPU Class
#
#   Attempts to emulate a MOS 6502
#
#   Expects a "bus" object that can respond to reads and writes
#
################################################################################

import random
from sim_error import SimError
import time


class CPU():           

    stack_location = 0x0100
    irq_vector = 0xFFFA
    reset_vector = 0xFFFC
    nmi_brk_vector = 0xFFFE

    def __init__(self, bus, random_state=False):
        self.bus = bus
        if random_state:
            self.randomize_registers()
        else:
            self.initialize_registers()
        self.halted = True
        self.delay = 2/1000000    # Default to 2 microsecond instruction delay
        self.breakpoints = []
        self.last_break = None


    def __str__(self):
        state = f"A: {self.a:02X}   X: {self.x:02X}   Y: {self.y:02X}    "
        state += "NV_BDIZC   "
        state += 'HALTED\n' if self.halted else 'RUNNING\n'
        state += f"S: {self.s:02X}  PC: {self.pc:04X}          "
        state = (state + str(int(self.n)) + str(int(self.v)) + "0" +
                         str(int(self.b)) + str(int(self.d)) +
                         str(int(self.i)) + str(int(self.z)) +
                         str(int(self.c)))
        state += f"   Delay: {int(self.delay * 1000000)}μs"
        return state


    def initialize_registers(self):
        self.a = 0
        self.x = 0
        self.y = 0
        self.pc = 0       # Program counter
        self.s = 0xFF     # Stack pointer
        # Flags are kept as numeric rather than boolean
        self.c = 0        # Carry flag
        self.z = 0        # Zero flag
        self.i = 0        # Disable interrupts
        self.d = 0        # Decimal mode flag
        self.b = 0        # Break flag (doesn't exist in real hardware)
        self.v = 0        # Overflow flag
        self.n = 0        # Negative flag


    def randomize_registers(self):
        self.a = random.randrange(0x100)
        self.x = random.randrange(0x100)
        self.y = random.randrange(0x100)
        self.pc = random.randrange(0x10000)
        self.s = random.randrange(0x100)
        self.c = random.randrange(2)
        self.z = random.randrange(2)
        self.i = random.randrange(2)
        self.d = random.randrange(2)
        self.b = random.randrange(2)
        self.v = random.randrange(2)
        self.n = random.randrange(2)


    def get_status_register(self):
        '''Return status register flags as a single, 8-bit byte'''
        # Flags should be 1 if they're not 0, but we won't assume that
        sr =  0x80 if self.n else 0
        sr += 0x40 if self.v else 0
        sr += 0x10 if self.b else 0
        sr += 0x08 if self.d else 0
        sr += 0x04 if self.i else 0
        sr += 0x02 if self.z else 0
        sr += 0x01 if self.c else 0
        return sr


    def set_status_register(self, sr):
        '''Set processor status flags from a single, 8-bit byte'''
        self.n = int(bool(sr & 0x80))
        self.v = int(bool(sr & 0x40))
        self.b = int(bool(sr & 0x10))
        self.d = int(bool(sr & 0x08))
        self.i = int(bool(sr & 0x04))
        self.z = int(bool(sr & 0x02))
        self.c = int(bool(sr & 0x01))


    def reset(self):
        '''Set interrupt disable flag and set program counter to address found at the reset vector ($FFFC & $FFFD)'''
        self.sei_and_set_pc(self.reset_vector)


    def interrupt(self, vector, set_break_flag=False):
        '''Handle an interrupt by pushing return address and status register
        onto the stack, then setting program counter to address at vector.
        Does not do any masking, so any call to this from an IRQ should
        first check the interrupt disable flag status.
        When called by BRK, set_break_flag is True and the status register
        is pushed with bits 4 (break flag) and 5 (unused) set.  When called
        by hardware interrupts (IRQ and NMI), that should remain False to push
        status register without those flags set.
        '''
        # Note that we push the actual return address onto the stack, which
        # is different rom the way JSR pushes return address minus one
        self.push(self.pc // 0x100)
        self.push(self.pc & 0xFF)
        if set_break_flag:
            # PHP always pushes with BRK flag set
            self.php()
        else:
            self.push(self.get_status_register() & 0b11001111)
        self.sei_and_set_pc(vector)
        # http://6502.org/tutorials/interrupts.html
        # https://en.wikipedia.org/wiki/Interrupts_in_65xx_processors
        # https://www.masswerk.at/6502/6502_instruction_set.html
        # https://www.pagetable.com/?p=410


    def sei_and_set_pc(self, vector):
        '''Disable interrupts and set program counter to address at given interrupt vector.
        Called by reset() and interrupt()
        '''
        self.sei()
        self.pc = self.bus.read(vector) + self.bus.read((vector + 1) & 0xFFFF) * 0x100

    def inc_pc(self):
        # Increment program counter, with wrapping
        self.pc = (self.pc + 1) & 0xFFFF


    def set_breakpoint(self, address):
        '''If passed address is not already a breakpoint, add to list and return True
        If it's already a breakpoint, remove it from list and return False'''
        address &= 0xFFFF
        if address in self.breakpoints:
            self.breakpoints.remove(address)
            return False
        else:
            self.breakpoints.append(address)
            return True
        

    def clear_breakpoints(self):
        '''Clear all breakpoints and return number of breakpoints cleared'''
        n = len(self.breakpoints)
        self.breakpoints = []
        return n


    def step(self):
        '''Perform one program step, based on data at current program counter'''
        if self.halted:
            raise SimError('Stepping attempted while CPU is halted.')
        
        # Check for interrupt condition
        if self.bus.interrupt is not None:
            if self.bus.interrupt == 'RES':
                self.reset()
            elif self.bus.interrupt == 'HLT':
                self.halted = True
            else:
                raise SimError(f'Unimplemented interrupt condition {self.bus.interrupt}')
            self.bus.interrupt = None
            return

        # Breakpoint?
        if self.pc in self.breakpoints:
            # If we didn't break on this same spot last time, break now...
            if self.last_break is None or self.pc != self.last_break:
                self.halted = True
                self.last_break = self.pc
                return
            else:
                # Keep going, but clear it out so we'll stop here next time
                self.last_break = None

        # Take care of any delay we need to do
        time.sleep(self.delay)
        
        # Get opcode from current program counter address (remember where PC was)
        opcode = self.bus.read(self.pc)
        saved_pc = self.pc
        self.inc_pc()
        
        # Get the instruction from the opcodes dictionary and execute
        key = f'{opcode:02X}'
        if key not in self.opcodes:
            self.halted = True
            raise SimError(f'Unrecognized opcode ${key} at ${saved_pc:04X}')
        instruction = self.opcodes[key]
        if isinstance(instruction, list):
            if len(instruction) == 1:
                instruction[0](self)
            elif len(instruction) > 1:
                instruction[0](self, instruction[1](self))
            else:
                raise SimError(f'Improperly formatted opcode instruction for ${key} at ${saved_pc:04X}')
        else:
            instruction(self)



#########  Address-Resolving Methods  #########################################

    # All address-resolving functions return the ADDRESS where the operand
    # is to be found (not the actual operand).  For stores, increments, etc.
    # the address returned is the address to modify.
    
    def absolute(self):
        # Absolute mode: Address is specified right after opcode
        address = self.bus.read(self.pc)
        self.inc_pc()
        address += self.bus.read(self.pc) * 0x100
        self.inc_pc()
        return address

    def absolute_x(self):
        # Absolute, X-indexed: X is added to address (with carry to next page)
        address = self.absolute()
        address = (address + self.x) & 0xFFFF
        return address

    def absolute_y(self):
        # Absolute, Y-indexed: Y is added to address (with carry to next page)
        address = self.absolute()
        address = (address + self.y) & 0xFFFF
        return address

    def accumulator(self):
        # Accumulator mode: Only used for shifts and rotates
        # Return None to tell operator function to use A instead of an address
        return None

    def immediate(self):
        # Immediate mode: Value is found at address right after opcode
        address = self.pc
        self.inc_pc()
        return address

    def indirect(self):
        # Regular (non-indexed) indirect mode:  Only used by JMP
        address_location = self.bus.read(self.pc)
        self.inc_pc()
        address_location += self.bus.read(self.pc) * 0x100
        self.inc_pc()
        address_lsb = self.bus.read(address_location)
        # Famously wraps around page for second byte if first is at end of page
        if address_location & 0xFF == 0xFF:
            address_location -= 0xFF
            print('******** WRAPPEROOO ********')
        else:
            address_location += 1
        address_msb = self.bus.read(address_location)
        return address_msb * 0x100 + address_lsb

    def indirect_x(self):
        # The operand is a zero-page starting location which is then indexed
        # as with zero_page_x.  But rather that this being actual address to,
        # use, it's a location that holds the address to use.
        address_location = self.zero_page_x()
        # Assumes that the second byte will wrap around to $00 if the
        # first byte winds up being at $FF  TODO: is this true?
        if address_location == 0xFF:
            print('******* WRAPTASTIC *****')
        return self.bus.read((address_location + 1) & 0xFF) * 0x100 + self.bus.read(address_location)

    def indirect_y(self):
        # The operand is a zero-page location of a two-byte address, which
        # is then incremented by y with carry to get final address
        address_location = self.zero_page()
        # Assumes that the second byte will wrap around to $00 if the
        # indexed first byte winds up being at $FF  TODO: is this true?
        if address_location == 0xFF:
            print('******* WRAPTASTICLY *****')
        address = self.bus.read((address_location + 1) & 0xFF) * 0x100 + self.bus.read(address_location)
        return (address + self.y) & 0xFFFF

    def zero_page(self):
        # Zero Page mode: LSB of address specified right after opcode, MSB = 00
        address = self.bus.read(self.pc)
        self.inc_pc()
        return address

    def zero_page_x(self):
        # Zero Page, X-indexed: X is added to zero-page address (no carry!)
        address = self.bus.read(self.pc)
        self.inc_pc()
        address = (address + self.x) & 0xFF  # Wraps to zero-page
        return address

    def zero_page_y(self):
        # Zero Page, Y-indexed: Only used with LDX instruction
        address = self.bus.read(self.pc)
        self.inc_pc()
        address = (address + self.y) & 0xFF  # Wraps to zero-page
        return address



########   Utility/Helper Functions for Operator Methods  #####################

    def bin2bcd(self, n):
        return ((n // 10) * 16 + (n % 10)) & 0xFF

    def bcd2bin(self, n):
        return (n // 16) * 10 + (n & 0x0F)

    def branch(self, take_branch):
        # Called by the various branch operations
        displacement = self.bus.read(self.pc)
        self.inc_pc()
        if take_branch:
            if displacement >= 0x80:
                displacement = -(0x100 - displacement)
            self.pc = (self.pc + displacement) & 0xFFFF

    def compare(self, reg_value, n):
        # Similar to sub(), except:
        #  - Doesn't assume register is A. Can work with X or Y too.
        #  - Doesn't store value back in A. Just sets (most) flags.
        #  - Doesn't affect the overflow flag
        result = reg_value - n
        # Set carry prior to wrapping
        self.c = int(result >= 0)
        result &= 0xFF
        self.set_nz(result)
        
    def shift_left(self, value, carry_fill):
        # ASL: carry_fill is False
        # ROL: carry_fill is True
        saved_carry = self.c
        # Original bit 7 is always moved to Carry
        self.c = int(value >= 0x80)
        # Shift left, with 0 coming in on the right (ASL)
        value = (value * 2) & 0xFF
        # Put saved carry in bit 0? (ROL?)
        if carry_fill and saved_carry:
            value += 1
        self.set_nz(value)
        return value

    def shift_right(self, value, carry_fill):
        # LSR: carry_fill is False
        # ROR: carry_fill is True
        saved_carry = self.c
        # Original bit 0 is always moved to Carry
        self.c = value & 1
        # Shift right, with 0 coming in on the right (LSR)
        value = (value // 2) & 0xFF
        # Put saved carry in bit 7 (ROR)
        if carry_fill and saved_carry:
            value += 0x80
        self.set_nz(value)
        return value

    def pull(self):
        # AKA "pop". Since the stack pointer points to the next empty spot,
        # we have to increment it prior to fetching the value.
        # And yes, this sucker WILL wrap if you over-pop
        self.s = (self.s + 1) & 0xFF
        return self.bus.read(self.stack_location + self.s)

    def push(self, value):
        # The stack always lives on page one as far as the CPU is concerned
        # The pointer grows downward and always points to the next empty spot
        # in the stack, NOT at the end of existing data
        self.bus.write(self.stack_location + self.s, value)
        self.s = (self.s - 1) & 0xFF

    def set_nz(self, result):
        self.z = int(result == 0)
        self.n = int(result >= 0x80)
        return



#########  Operator Methods  ##################################################

    def adc(self, address):
        # Add to register A, overwriting it.  Always add carry flag.
        value = self.bus.read(address)
        if self.d:
            result = self.bcd2bin(self.a) + self.bcd2bin(value) + self.c
            if result >= 100:
                result -= 100
                self.c = 1
            else:
                self.c = 0
        else:
            result = self.a + value + self.c
            self.c = int(result > 255)
            result &= 0xFF
        # http://www.6502.org/tutorials/vflag.html#5
        # http://www.righto.com/2012/12/the-6502-overflow-flag-explained.html
        # Overflow happens when the inputs are both positive and result is
        # negative, or inputs are negative and result is positive. That is,
        # if the signs of both inputs don't match the result.
        self.v = int((self.a & 0x80 != result & 0x80) and
                     (value & 0x80 != result & 0x80))
        self.set_nz(result)
        if self.d:
            self.a = self.bin2bcd(result)
        else:
            self.a = result

    # Note that the AND operation has an awkward uppercase N to avoid
    # conflicting with the Python keyword "and"
    def aNd(self, address):
        value = self.bus.read(address)
        self.a = (self.a & value) & 0xFF
        self.set_nz(self.a)

    def asl(self, address):
        value = self.a if address is None else self.bus.read(address)
        value = self.shift_left(value, carry_fill=False)
        if address is None:
            self.a = value
        else:
            self.bus.write(address, value)

    def bcc(self):
        self.branch(not self.c)

    def bcs(self):
        self.branch(self.c)

    def beq(self):
        self.branch(self.z)

    def bit(self, address):
        value = self.bus.read(address)
        self.z = int((value & self.a) == 0)
        self.n = int(value >= 0x80)
        self.v = int((value & 0x40) == 0x40)

    def bmi(self):
        self.branch(self.n)

    def bne(self):
        self.branch(not self.z)

    def bpl(self):
        self.branch(not self.n)

    def brk(self):
        # Byte after break opcode is reserved for marking
        # break condition and is skipped over
        self.inc_pc()
        self.interrupt(vector=self.nmi_brk_vector, set_break_flag=True)

    def bvc(self):
        self.branch(not self.v)

    def bvs(self):
        self.branch(self.v)

    def clc(self):
        self.c = 0

    def cld(self):
        self.d = 0

    def cli(self):
        # Clear interrupt disable flag (i.e. enable interrupts)
        self.i = 0

    def clv(self):
        self.v = 0

    def cmp(self, address):
        self.compare(self.a, self.bus.read(address))

    def cpx(self, address):
        self.compare(self.x, self.bus.read(address))

    def cpy(self, address):
        self.compare(self.y, self.bus.read(address))

    def dec(self, address):
        value = (self.bus.read(address) - 1) & 0xFF
        self.bus.write(address, value)
        self.set_nz(value)

    def dex(self):
        self.x = (self.x - 1) & 0xFF
        self.set_nz(self.x)

    def dey(self):
        self.y = (self.y - 1) & 0xFF
        self.set_nz(self.y)

    def eor(self, address):
        value = self.bus.read(address)
        self.a = (self.a ^ value) & 0xFF
        self.set_nz(self.a)

    def inc(self, address):
        value = (self.bus.read(address) + 1) & 0xFF
        self.bus.write(address, value)
        self.set_nz(value)

    def inx(self):
        self.x = (self.x + 1) & 0xFF
        self.set_nz(self.x)

    def iny(self):
        self.y = (self.y + 1) & 0xFF
        self.set_nz(self.y)

    def jmp(self, address):
        self.pc = address

    def jsr(self, address):
        # The 6502 JSR pushes the address of the next instruction, minus one
        return_address = (self.pc - 1) & 0xFFFF
        self.push(return_address // 0x100)  # Big end first
        self.push(return_address & 0xFF)
        # Point the PC to the subroutine
        self.pc = address

    def lda(self, address):
        self.a = self.bus.read(address)
        self.set_nz(self.a)

    def ldx(self, address):
        self.x = self.bus.read(address)
        self.set_nz(self.x)

    def ldy(self, address):
        self.y = self.bus.read(address)
        self.set_nz(self.y)

    def lsr(self, address):
        value = self.a if address is None else self.bus.read(address)
        value = self.shift_right(value, carry_fill=False)
        if address is None:
            self.a = value
        else:
            self.bus.write(address, value)

    def nop(self):
        pass

    def ora(self, address):
        value = self.bus.read(address)
        self.a = (self.a | value) & 0xFF
        self.set_nz(self.a)

    def pha(self):
        self.push(self.a)

    def php(self):
        # Always pushed with break flag (bit 4) and bit 5 set to 1
        self.push(self.get_status_register() | 0b00110000)

    def pla(self):
        self.a = self.pull()
        self.set_nz(self.a)

    def plp(self):
        self.set_status_register(self.pull())

    def rol(self, address):
        value = self.a if address is None else self.bus.read(address)
        value = self.shift_left(value, carry_fill=True)
        if address is None:
            self.a = value
        else:
            self.bus.write(address, value)

    def ror(self, address):
        value = self.a if address is None else self.bus.read(address)
        value = self.shift_right(value, carry_fill=True)
        if address is None:
            self.a = value
        else:
            self.bus.write(address, value)

    def rti(self):
        self.plp()
        lsb = self.pull()
        self.pc = self.pull() * 0x100 + lsb

    def rts(self):
        lsb = self.pull()
        self.pc = self.pull() * 0x100 + lsb
        # Bump the PC to the NEXT address
        self.inc_pc()

    def sbc(self, address):
        # Subtraction is always from register A and uses the carry
        # flag as an inverse borrow. Results always assigned to A.
        value = self.bus.read(address)
        if self.d:
            result = self.bcd2bin(self.a) - self.bcd2bin(value) + self.c - 1
            self.v = int((self.a & 0x80 != result & 0x80) and
                         (value & 0x80 == result & 0x80))
            if result < 0:
                self.c = 0
                result += 100
            else:
                self.c = 1
        else:
            result = self.a - value + self.c - 1
            self.c = int(result >= 0)
            self.v = int((self.a & 0x80 != result & 0x80) and
                         (value & 0x80 == result & 0x80))
            result &= 0xFF
        # http://www.6502.org/tutorials/vflag.html#5
        # http://www.righto.com/2012/12/the-6502-overflow-flag-explained.html
        # Overflow formula is same as with addition, only n is effectively
        # ones-complemented (that is, bit 7 of n must match bit 7 of result,
        # rather than be different)
        self.set_nz(result)
        if self.d:
            self.a = self.bin2bcd(result)
        else:
            self.a = result

    def sec(self):
        self.c = 1

    def sed(self):
        self.d = 1

    def sei(self):
        # Set interrupt disable flag (i.e. prevent interrupts)
        self.i = 1

    def sta(self, address):
        self.bus.write(address, self.a)

    def stx(self, address):
        self.bus.write(address, self.x)

    def sty(self, address):
        self.bus.write(address, self.y)

    def tax(self):
        self.x = self.a
        self.set_nz(self.x)

    def tay(self):
        self.y = self.a
        self.set_nz(self.y)

    def tsx(self):
        self.x = self.s
        self.set_nz(self.x)

    def txa(self):
        self.a = self.x
        self.set_nz(self.a)

    def txs(self):
        self.s = self.x

    def tya(self):
        self.a = self.y
        self.set_nz(self.a)


    # The "opcodes" dictionary translates an opcode key into an instruction
    # containing either a reference to an operation function or a list
    # with both an operation function reference and a reference to an
    # operand address-resolving function (i.e. an addressing mode handler).
    # Implemented as a class variable, even though the functions themselves
    # are all instance methods.  When using , we'll have to explicitly
    # pass them the "self" argument they expect.
    opcodes = {'00': brk,
               '01':[ora, indirect_x],
               '05':[ora, zero_page],
               '06':[asl, zero_page],
               '08': php,
               '09':[ora, immediate],
               '0A':[asl, accumulator],
               '0D':[ora, absolute],
               '0E':[asl, absolute],
               '10': bpl,
               '11':[ora, indirect_y],
               '15':[ora, zero_page_x],
               '16':[asl, zero_page_x],
               '18': clc,
               '19':[ora, absolute_y],
               '1D':[ora, absolute_x],
               '1E':[asl, absolute_x],
               '20':[jsr, absolute],
               '21':[aNd, indirect],
               '24':[bit, zero_page],
               '25':[aNd, zero_page],
               '26':[rol, zero_page],
               '28': plp,
               '29':[aNd, immediate],
               '2A':[rol, accumulator],
               '2C':[bit, absolute],
               '2D':[aNd, absolute],
               '2E':[rol, absolute],
               '30': bmi,
               '31':[aNd, indirect_y],
               '35':[aNd, zero_page_x],
               '36':[rol, zero_page_x],
               '38': sec,
               '39':[aNd, absolute_y],
               '3D':[aNd, absolute_x],
               '3E':[rol, absolute_x],

               '40': rti,
               '41':[eor, indirect_x],
               '45':[eor, zero_page],
               '46':[lsr, zero_page],
               '48': pha,
               '49':[eor, immediate],
               '4A':[lsr, accumulator],
               '4C':[jmp, absolute],
               '4D':[eor, absolute],
               '4E':[lsr, absolute],
               '50': bvc,
               '51':[eor, indirect_y],
               '55':[eor, zero_page_x],
               '56':[lsr, zero_page_x],
               '58': cli,
               '59':[eor, absolute_y],
               '5D':[eor, absolute_x],
               '5E':[lsr, absolute_x],
               '60': rts,
               '61':[adc, indirect_x],
               '65':[adc, zero_page],
               '66':[ror, zero_page],
               '68': pla,
               '69':[adc, immediate],
               '6A':[ror, accumulator],
               '6C':[jmp, indirect],
               '6D':[adc, absolute],
               '6E':[ror, absolute],
               '70': bvs,
               '71':[adc, indirect_y],
               '75':[adc, zero_page_x],
               '76':[ror, zero_page_x],
               '78': sei,
               '79':[adc, absolute_y],
               '7D':[adc, absolute_x],
               '7E':[ror, absolute_x],

               '81':[sta, indirect_x],
               '84':[sty, zero_page],
               '85':[sta, zero_page],
               '86':[stx, zero_page],
               '88': dey,
               '8A': txa,
               '8C':[sty, absolute],
               '8D':[sta, absolute],
               '8E':[stx, absolute],
               '90': bcc,
               '91':[sta, indirect_y],
               '94':[sty, zero_page_x],
               '95':[sta, zero_page_x],
               '96':[stx, zero_page_y],
               '98': tya,
               '99':[sta, absolute_y],
               '9A': txs,
               '9D':[sta, absolute_x],
               'A0':[ldy, immediate],
               'A1':[lda, indirect_x],
               'A2':[ldx, immediate],
               'A4':[ldy, zero_page],
               'A5':[lda, zero_page],
               'A6':[ldx, zero_page],
               'A8': tay,
               'A9':[lda, immediate],
               'AA': tax,
               'AC':[ldy, absolute],
               'AD':[lda, absolute],
               'AE':[ldx, absolute],
               'B0': bcs,
               'B1':[lda, indirect_y],
               'B4':[ldy, zero_page_x],
               'B5':[lda, zero_page_x],
               'B6':[ldx, zero_page_y],
               'B8': clv,
               'B9':[lda, absolute_y],
               'BA': tsx,
               'BC':[ldy, absolute_x],
               'BD':[lda, absolute_x],
               'BE':[ldx, absolute_y],

               'C0':[cpy, immediate],
               'C1':[cmp, indirect_x],
               'C4':[cpy, zero_page],
               'C5':[cmp, zero_page],
               'C6':[dec, zero_page],
               'C8': iny,
               'C9':[cmp, immediate],
               'CA': dex,
               'CC':[cpy, absolute],
               'CD':[cmp, absolute],
               'CE':[dec, absolute],
               'D0': bne,
               'D1':[cmp, indirect_y],
               'D5':[cmp, zero_page_x],
               'D6':[dec, zero_page_x],
               'D8': cld,
               'D9':[cmp, absolute_y],
               'DD':[cmp, absolute_x],
               'DE':[dec, absolute_x],
               'E0':[cpx, immediate],
               'E1':[sbc, indirect_x],
               'E4':[cpx, zero_page],
               'E5':[sbc, zero_page],
               'E6':[inc, zero_page],
               'E8': inx,
               'E9':[sbc, immediate],
               'EA': nop,
               'EC':[cpx, absolute],
               'ED':[sbc, absolute],
               'EE':[inc, absolute],
               'F0': beq,
               'F1':[sbc, indirect_y],
               'F5':[sbc, zero_page_x],
               'F6':[inc, zero_page_x],
               'F8': sed,
               'F9':[sbc, absolute_y],
               'FD':[sbc, absolute_x],
               'FE':[inc, absolute_x],
              }

