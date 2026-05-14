import threading

# Globals
usage_data = {"character_count": 0, "character_limit": 0}
tray_icon = None
stop_event = threading.Event()
current_engine = "deepl"