"""`python -m shared`: comprueba la configuración del `.env` local."""

import sys

from shared.settings import main

sys.exit(main())
