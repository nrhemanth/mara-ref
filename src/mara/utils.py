from datetime import datetime, timedelta
import time
import threading

#--------------------------------------------------
# Timer to track annealing or incubation times for materials
#--------------------------------------------------
active_timers = {}

class TimerThread(threading.Thread):
    def __init__(self, material_id, duration_min):
        super().__init__()
        self.material_id = material_id
        self.duration = timedelta(minutes=duration_min)
        self.start_time = datetime.now()
        self.end_time = self.start_time + self.duration

    def run(self):
        time.sleep(self.duration.total_seconds())
        print(f"[{datetime.now().strftime('%H:%M:%S')}] Material {self.material_id} is done!")

def add_material(material_id, duration_min):
    print(f"[{datetime.now().strftime('%H:%M:%S')}] Timer started for {material_id} ({duration_min} min)")
    thread = TimerThread(material_id, duration_min)
    active_timers[material_id] = thread
    thread.start()

#--------------------------------------------------
# Deck management utilities
#--------------------------------------------------
def deck_snapshot(protocol):
    items = []
    for slot in protocol.deck:
        lw = protocol.deck[slot]
        if lw:
            items.append((slot,lw.load_name,getattr(lw,"display_name", "")))
    return sorted(items)

# Example usage:
# protocol = execute.get_protocol_api('2.27')
# robot = OpentronMara(protocol)
# print(deck_snapshot(protocol))

