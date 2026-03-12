import vlc
import time

instance = vlc.Instance("--quiet", "--no-video", "--aout=pulse")
player = instance.media_player_new()

MP3 = "/tmp/test.mp3"

print("=== Starting playback ===")
media = instance.media_new(MP3)
player.set_media(media)
player.play()

# Warte auf State.Playing
start_time = time.time()
while player.get_state() != vlc.State.Playing:
    time.sleep(0.05)
state_playing_time = time.time() - start_time
print(f"State.Playing reached after: {state_playing_time*1000:.0f}ms")

# Tracke Position für 2 Sekunden
print("\n=== Position tracking (should see smooth progress) ===")
for i in range(20):
    pos = player.get_time()
    state = player.get_state()
    print(f"[{i*100:4d}ms] Position: {pos:5d}ms, State: {state}")
    time.sleep(0.1)

print("\n=== Did you hear stutter in the first ~500ms? (yes/no) ===")
player.stop()
