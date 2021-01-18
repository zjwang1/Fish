# learning from perfbook

## questions
1. What is the READ_ONCE() and WRITE_ONCE()?

        These macros constrain the compiler so as to prevent it
        from carrying out optimizations that would be problematic
        for concurrently accessed shared variables. 
        They don’t constrain the CPU at all, other than by preventing reordering of accesses to a given single variable. 
        Note that this single-variable constraint does apply to the code shown in Listing 4.5 because only the variable x is accessed.
        In some cases, it is only necessary to ensure that the compiler avoids optimizing away a given memory read, in which case the READ_ONCE() primitive may be used, as it was on line 20 of Listing 4.5. Similarly, the WRITE_ONCE() primitive may be used to prevent the compiler from optimizing away a given memory write. These last three primitives are not provided directly by GCC, but may be implemented straightforwardly as shown in Listing 4.9, and all three are discussed at length in Section 4.3.4.

It might seem futile to prevent the compiler from changing the order of accesses in cases where the underlying hardware is free to reorder them. However, modern machines have exact exceptions and exact interrupts, meaning that any interrupt or exception will appear to have
happened at a specific place in the instruction stream.
This means that the handler will see the effect of all
prior instructions, but won’t see the effect of any subsequent instructions. READ_ONCE() and WRITE_ONCE()
can therefore be used to control communication between
interrupted code and interrupt handlers, independent of
the ordering provided by the underlying hardware.