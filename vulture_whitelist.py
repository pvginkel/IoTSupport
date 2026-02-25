# Vulture whitelist — parameters required by callback/protocol signatures
# that vulture incorrectly reports as unused.
#
# Run vulture with: poetry run vulture app/ vulture_whitelist.py --min-confidence 80

# SQLAlchemy event listener signatures (before/after_cursor_execute)
context  # unused variable
cursor  # unused variable
executemany  # unused variable

# Signal handler signature (signum, frame)
frame  # unused variable

# Context manager __exit__(exc_type, exc_val, exc_tb)
exc_type  # unused variable
exc_val  # unused variable
exc_tb  # unused variable

# SQLAlchemy pool event listener signatures (checkout/checkin)
conn_proxy  # unused variable
conn_record  # unused variable

# Function parameters kept for API compatibility
encoding  # unused variable

# TYPE_CHECKING guard (unsatisfiable 'if' condition is expected)
from typing import TYPE_CHECKING

TYPE_CHECKING  # unused variable

# paho-mqtt callback signatures (on_connect, on_disconnect, on_message)
userdata  # unused variable
connect_flags  # unused variable
properties  # unused variable
disconnect_flags  # unused variable

# Tuple unpacking in LVGLImage.py (third-party utility)
ext  # unused variable
