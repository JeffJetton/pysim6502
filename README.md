# PySim6502

PySim6502 simulates a simple computer system based around the classic [MOS 6502 microprocessor](https://en.wikipedia.org/wiki/MOS_Technology_6502). It's particularly handy for iteratively developing and testing assembled 6502 code without having to transfer it over to actual hardware each time.

* Written entirely in Python for ease of modification and customization
* Aims for fairly loose coupling between components. A new system can be quickly created as a subclass of the `Bus` object, overriding just what is necessary to implement a particular memory map.
* Commands are similar to [simh](https://github.com/simh/simh):
    * Examine and deposit values into memory
    * View status of CPU registers
    * Single-step instructions
    * Set breakpoints

Type `help` at the `sim>` prompt to learn more.

### Example of Use

Run the `sim.py` file to start. Try entering `bus` to view details of the Bus object currently being used by the CPU:

    python sim.py
    sim> bus
    Apple 1 Bus
      0000-7FFF: Read/Write
      8000-DFFF: Not Used
      E000-FFFF: Read-Only
    Output Delay: 5000μs
    Memory Errors: ON
    Addresses D010-D013 used for input/output
    sim> 



As you can see, by default the simulator is set up to emulate an Apple 1 with 32K of RAM and 8K of ROM. 
  
>The WOZMON monitor and Integer BASIC are automatically written to ROM, although you can change this in the `SystemBus` constructor found in `apple1_bus.py`.

Examine the first few bytes of Integer BASIC, which starts at $E000:

    sim> examine e000 e01f
    E000: 4C B0 E2 AD 11 D0 10 FB
    E008: AD 10 D0 60 8A 29 20 F0
    E010: 23 A9 A0 85 E4 4C C9 E3
    E018: A9 20 C5 24 B0 0C A9 8D
    sim>

Input is case-insensitive, but hexadecimal is assumed for address arguments (do *not* prefix with `$` or `0x`, etc.)

Enter `start` to run the simulated system. You'll immediately drop into WOZMON. If you examine the same address range viewed previously (using WOZMON's "dot" syntax) you should see the same values:

    E000.E01F
    
    E000: 4C B0 E2 AD 11 D0 10 FB
    E008: AD 10 D0 60 8A 29 20 F0
    E010: 23 A9 A0 85 E4 4C C9 E3
    E018: A9 20 C5 24 B0 0C A9 8D

The difference is that now the simulated monitor is doing the examining rather than the simulator itself!

Start BASIC by entering its starting address (E000) followed by `R`. You should eventually be greeted by the `>` prompt:

    E000R
    
    E000: 4C
    >

Enter the first line of our test program:

    >10 FOR I = 1 TO 5
    >

Now type `Control + E` to exit back to the simulator prompt. The simulated system will be frozen in place where you left it, and you can enter `cpu` to view register and system status at that point:
  
    >cpu
    A: 80   X: FF   Y: 00    NV_BDIZC   HALTED
    S: FB  PC: E006          10000001   Delay: 1μs
    sim>


 Integer BASIC's input buffer, which holds everything you type in as you enter it, starts at $0200. If you examine memory there, you should see the remnants of the line you just wrote. Although it will be in Apple-1-style ASCII values, which have bit 7 always set:

    sim>e 200 210
    0200: B1 B0 A0 C6 CF D2 A0 C9
    0208: A0 BD A0 B1 A0 D4 CF A0
    0210: B5
    sim> 

Note that you can abbreviate `examine` to `exam` or just `e`.

Enter `start` (or `run` or just `r`) to pick up the simulation where you left off, then type in the remaining lines of the program:

    >20 PRINT "HELLO!", I
    >30 NEXT I
    >40 END
    >LIST
       10 FOR I=1 TO 5
       20 PRINT "HELLO!",I
       30 NEXT I
       40 END 
    
    >RUN
    HELLO!  1
    HELLO!  2
    HELLO!  3
    HELLO!  4
    HELLO!  5
    
`Control + R` performs a simulated 6502 reset, which will drop you out of BASIC and back into WOZMON. 
 
>Checking for Ctrl+R and Ctrl+E currently only happens when the simulated system is looking for keyboard input. In the case of an endless loop, you'll usually have to resort to quitting Python entirely with Ctrl+C.

