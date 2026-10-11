# file: macula.py

#!/usr/bin/env python3
"""
macula — a small, zero-dependency file server for pentesting.
"macula" (Latin): spot, focal point. Like the macula lutea in the retina.

DIRETTIVE:
 - nessun caricamento dall'esterno (nessuna libreria js, nessun file css esterno)
 - nessuna dipendenza che non sia nell'installazione standard di python
"""
from macula.cli import main

if __name__ == "__main__":
    main()