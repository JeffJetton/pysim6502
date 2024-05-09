################################################################################
#
#   Sim
#
#   Main engine for running and dealing with the simulated 6502 system
#
################################################################################


from apple1_bus import SystemBus
from cpu import CPU
import curses
from curses import wrapper
from sim_error import SimError




PROMPT = 'sim> '


def examine(bus, start, stop=None):
    '''Print bytes of bus's memory, from start to (optional) stop
    '''
    if stop is None:
        # Make start and stop the same
        stop = start
    else:
        # Make sure start is before stop
        if stop < start:
            start, stop = stop, start
    if not (0 <= start < bus.mem_size):
        print(f'Starting address {start:04X} is out of range')
        return
    if not (0 <= stop < bus.mem_size):
        print(f'Ending address {stop:04X} is out of range')
        return
    curr = start
    print_header = True
    while curr <= stop:
        if print_header:
            # Don't do a CR for the very first header
            if curr != start:
                print()
            print(f'{curr:04X}:', end='')
            print_header = False
        try:
            print(f' {bus.read(curr):02X}', end='')
        except SimError as err:
            print(err)
            return
        curr += 1
        # New header if we crossed a $00 or $80 boundary
        if (curr % 8) == 0:
            print_header = True
    # One last return
    print()


def _loop(stdscr, cpu, bus, max_steps=None):
    """Main loop that does some terminal window setup, then repeatedly
    steps the CPU.  Should be "wrapped" by curses rather than called
    directly.  See run() function.
    """
    # Set screen parameters based on Bus settings
    stdscr.resize(bus.scr_settings.get('rows', 24),
                  bus.scr_settings.get('cols', 20))
    stdscr.scrollok(bus.scr_settings.get('scroll_on', True))
    stdscr.nodelay(bus.scr_settings.get('input_delay_on', True))
    stdscr.keypad(bus.scr_settings.get('keypad_on', True))
    # Give the screen object back to the bus, so it can interact with it
    bus.stdscr = stdscr
    steps = 0
    while not cpu.halted and (max_steps is None or steps < max_steps):
        # If reset requested, clear screen
        if bus.interrupt == 'RES':
            stdscr.erase()
        cpu.step()
        if max_steps is not None:
            steps += 1



########  "Handle X" functions deal with simulator prompt commands  ###########

def handle_start(tokens, cpu, bus):
    '''Called when user enters START, GO, RUN, etc. at the simulator prompt.
    Kicks off a new curses window and starts stepping the cpu.
    Will try to set the program counter to the second token (if it exists)'''
    # Check for optional PC address
    if len(tokens) > 1:
        hexval = bus.parse_hex(tokens[1])
        if hexval is not None:
            cpu.pc = hexval & 0xFFFF
    cpu.halted = False
    try:
        # Call the loop function using the curses "wrapper",
        # which creates a Curses screen and passes it along.
        # This will restore "normal" terminal settings when any
        # exception is raised during the loop.
        wrapper(_loop, cpu, bus)
    except SimError as err:
        print(err)
    except BaseException:
        print(cpu)
        raise
    

def handle_cpu(tokens, cpu):
    if len(tokens) == 1:
        print(cpu)
    else:
        try:
            ms = int(tokens[1])
            cpu.delay = ms / 1000000
            print(f'CPU Instruction Delay: {int(cpu.delay*1000000)}μs')
        except ValueError:
            print(f'Invalid value for microseconds: {tokens[1]}')



def handle_bus(tokens, bus):
    if len(tokens) == 1:
        print(bus)
    else:
        try:
            us = int(tokens[1])
            bus.delay = us / 1000000
            print(f'Bus Output Delay: {int(bus.delay*1000000)}μs')
        except ValueError:
            print(f'Invalid value for microseconds: {tokens[1]}')



def handle_help():
    print()
    with open('help.txt', 'r') as helpfile:
        helplines = helpfile.readlines()
        for i, line in enumerate(helplines):
            if ((i+1) % 20) == 0:
                input('\nENTER for more...')
            print(line, end='')



def handle_pc(tokens, cpu, bus):
    if len(tokens) == 1:
        print(f'PC: {cpu.pc:04X}')
    else:
        hexval = bus.parse_hex(tokens[1])
        if hexval is not None:
            cpu.pc = hexval & 0xFFFF
        handle_pc([None], cpu, bus)


    
def handle_toggle(bus):
    bus.throw_memory_errors = not bus.throw_memory_errors
    print('Memory errors ', end='')
    print('ON' if bus.throw_memory_errors else 'OFF')



def handle_step(tokens, cpu, bus):
    if len(tokens) == 1:
        steps = 1
    else:
        try:
            steps = int(tokens[1])
        except ValueError:
            print(f'Invalid number of steps "{tokens[1]}"')
            return
    cpu.halted = False
    try:
        wrapper(_loop, cpu, bus, steps)
        handle_pc(['PC'], cpu, bus)
    except SimError as err:
        print(err)
    except BaseException:
        print(cpu)
        raise



def handle_examine(tokens, bus):
    if len(tokens) == 1:
        print('Provide an address, in hex, to examine (or two addresses for a range)')
    else:
        ex_start = bus.parse_hex(tokens[1])
        if ex_start is not None:
            if len(tokens) > 2:
                ex_stop = bus.parse_hex(tokens[2])
                if ex_stop is not None:
                    examine(bus, ex_start, ex_stop)
            else:
                examine(bus, ex_start)



def handle_deposit(tokens, cpu, bus):
    if len(tokens) == 1:
        print('Provide an address, in hex, to deposit value(s) into')
    elif len(tokens) == 2:
        print('Provide at least one deposit value after the address, in hex')
    else:
        address = bus.parse_hex(tokens[1])
        if address is None:
            print(f'Could not parse address {tokens[1]}')
            return
        if not (0 <= address < bus.mem_size):
            print(f'Address {tokens[1]} is out of range')
            return
        # Make sure all hex values are good before doing anything
        values = []
        for token in tokens[2:]:
            value = bus.parse_hex(token)
            if value is None:
                print(f'Could not parse value {token}')
            else:
                if 0 <= value <= 0xFF:
                    values.append(value)
                else:
                    print(f'Value {token} is out of range')
        if len(values) == (len(tokens) - 2):
            if address + len(values) > bus.mem_size:
                print(f'Not enough address space to deposit {len(values)} values starting at {address:04X}')
                return
            for value in values:
                try:
                    bus.write(address, value)
                    address += 1
                except SimError as err:
                    print(err)
                    return
            examine(bus, address - len(values), address - 1)



def handle_breakpoints(tokens, cpu, bus):
    if len(tokens) == 1:
        if len(cpu.breakpoints) == 0:
            print('No breakpoints have been set')
        else:
            cpu.breakpoints.sort()
            for b in cpu.breakpoints:
                print(f'{b:04X}')
    else:
        for token in tokens[1:]:
            address = bus.parse_hex(token)
            if address is not None:
                was_added = cpu.set_breakpoint(address)
                if was_added:
                    print(f'Breakpoint {address:04X} added')
                else:
                    print(f'Breakpoint {address:04X} removed')



def run(cpu, bus, reset=True, autostart=False):
    """Runs the simulator's REPL. By default, the CPU is reset and
    the user is in "prompt" mode where they can issue commands
    to the simulator itself.
    
    Pass True to autostart to launch the simulated system
    right off the bat, bypassing the simulator prompt.
    """
    if reset:
        cpu.reset()
    # REPL for communicating with the simulator itself.
    # At this point the simulated system is not running.
    # TODO: implement autostart? or have it execute any commandline arg as if typed in
    running = True
    while(running):
        tokens = input(PROMPT).upper().split()
        if len(tokens) == 0:
            continue
        if tokens[0] in ['START', 'GO', 'RUN', 'R', 'G']:
            handle_start(tokens, cpu, bus)
        elif tokens[0] in ['CPU', 'C']:
            handle_cpu(tokens, cpu)
        elif tokens[0] in ['BUS', 'B']:
            handle_bus(tokens, bus)
        elif tokens[0] in ['QUIT', 'EXIT', 'BYE']:
            running = False
        elif tokens[0] in ['HELP', 'H', '?', 'MAN']:
            handle_help()
        elif tokens[0] == 'PC':
            handle_pc(tokens, cpu, bus)
        elif tokens[0] in ['RESET', 'RES']:
            bus.interrupt = 'RES'
            handle_start(tokens, cpu, bus)
        elif tokens[0] in ['TOGGLE', 'ERROR', 'ERR', 'TOG', 'MEM', 'MEMORY']:
            handle_toggle(bus)
        elif tokens[0] in ['STEP', 'S']:
            handle_step(tokens, cpu, bus)
        elif tokens[0] in ['E', 'EX', 'EXAM', 'EXAMINE']:
            handle_examine(tokens, bus) 
        elif tokens[0] in ['D', 'DEP', 'DEPOSIT']:
            handle_deposit(tokens, cpu, bus)
        elif tokens[0] in ['BREAK', 'BRK', 'BR', 'BREAKPOINT', 'BREAKPOINTS']:
            handle_breakpoints(tokens, cpu, bus)
        elif tokens[0] in ['CLEAR', 'CLR']:
            print(f'Breakpoints cleared: {cpu.clear_breakpoints()}')
        elif tokens[0] == 'X':
            extra(cpu, bus)
        else:
            print(f'Unrecognized command "{tokens[0]}"')
    # End of run() loop



def main():
    bus = SystemBus() 
    cpu = CPU(bus)
    run(cpu, bus)




if __name__ == "__main__":
    main()
